"""The tiered preflight sweep (doc 23 sections 6.4 and 4.3).

Tier 0 re-collects the target's expected-URL set through the shared
census collection (``markettwin_shared.census_sources`` — the same
implementation census runs, doc 23 section 6.6); the traversal's
fetches double as tier-1 page-fingerprint fetches for the pages they
coincide with, and the tier-1 remainder is fetched directly. Tier 2
renders only the candidates (tier-1 differences, ``new`` URLs, and
tier-0 anomalies), bounded by the render cap and the wall budget.

The sweep is browser-free by construction: the rendered comparison
goes through the injected ``render`` callable (the job wires the
production one over the browser stack; tests inject a fake), and all
database writes go through ``FreshnessRepository``. This module makes
zero model calls (T-FJ8 pins the whole package).
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from markettwin_shared.app_map_common import canonical_url
from markettwin_shared.census_sources import (
    CandidateSet,
    CensusCandidate,
    FetchCallable,
    FetchResult,
    _fetch_with_retry,
    _response_content_type,
    _scan_html,
    collect_sources,
    traverse_link_graph,
)

from markettwin_execution_orchestrator.freshness.phash import visual_distance

# Mirrors census CENSUS_FETCH_TIMEOUT_SECONDS (doc 23 section 11: the
# same fetcher discipline, the same value, cited not duplicated — the
# sweep's own fetcher in freshness_job applies it per request).
PREFLIGHT_FETCH_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class PageFingerprint:
    """The census-grade page fingerprint (doc 23 section 4.1)."""

    http_status: int | None
    redirect_target: str | None
    content_type: str | None
    title: str | None
    html_sha256: str | None


def page_fingerprint(result: FetchResult, requested_canonical: str) -> PageFingerprint:
    """Derive the live page fingerprint from one fetch result, using
    census's disposition derivations (redirect target only when the
    chain lands somewhere else; title/sha only when a body arrived)."""

    status = result.status
    received = status is not None
    body = result.body or b""
    final_canonical = canonical_url(result.final_url) if result.final_url else None
    redirect_target = (
        final_canonical
        if result.redirect_chain
        and final_canonical is not None
        and final_canonical != requested_canonical
        else None
    )
    return PageFingerprint(
        http_status=status,
        redirect_target=redirect_target,
        content_type=_response_content_type(result.headers) if received else None,
        title=_scan_html(body).title if received and body else None,
        html_sha256=hashlib.sha256(body).hexdigest() if received and body else None,
    )


@dataclass
class RenderedState:
    """One live state's fingerprints, as the render stage computed them."""

    state_id: str | None
    state_key: str = "default"
    dom_structure_hash: str | None = None
    aria_hash: str | None = None
    screenshot_hash: str | None = None
    screenshot_phash: str | None = None
    capture: Any = None  # the retained StateCapture (reconcile's working set)


@dataclass
class RenderOutcome:
    """The render stage's answer for one candidate URL."""

    kind: str  # 'ok' | 'blocked_auth' | 'blocked_wall' | 'fetch_error' | 'browser_lost'
    states: list[RenderedState] = field(default_factory=list)  # default state first
    title: str | None = None


RenderCallable = Callable[[str], Awaitable[RenderOutcome]]
EmitCallable = Callable[[str, dict], Awaitable[None]]


@dataclass
class SweepResult:
    status: str  # 'ready' | 'partial'
    tier1: dict[str, dict] = field(default_factory=dict)
    tier2: dict[str, dict] = field(default_factory=dict)
    recollected: dict[str, tuple[str, ...]] = field(default_factory=dict)
    deferred: list[dict] = field(default_factory=list)
    tier_counts: dict[str, int] = field(default_factory=dict)
    history_rows: list[dict] = field(default_factory=list)
    captures: dict[str, RenderOutcome] = field(default_factory=dict)
    page_fingerprints: dict[str, PageFingerprint] = field(default_factory=dict)
    spend_seconds: float = 0.0


def _recorded_fingerprint(page: Any) -> PageFingerprint:
    return PageFingerprint(
        http_status=page.http_status,
        redirect_target=page.redirect_target,
        content_type=page.content_type,
        title=page.title,
        html_sha256=page.html_sha256,
    )


async def run_sweep(
    *,
    repository,
    preflight: Any,
    app_map: Any,
    pages: list,
    states_by_page: Mapping[Any, list],
    fetch: FetchCallable,
    sitemap_fetch: FetchCallable | None,
    render: RenderCallable,
    validate: Callable[[str], object],
    resolve_link: Callable[[str, str, str], str | None],
    emit: EmitCallable,
    render_cap: int,
    wall_budget_seconds: float,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    retry_delay: float = 1.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> SweepResult:
    """Run tiers 0-2 over one map version and return the sweep result.

    ``pages`` are the swept version's page rows (the expected set E);
    ``states_by_page`` maps page id -> its recorded state rows.
    """

    started = time.monotonic()
    result = SweepResult(status="ready")
    base_url = app_map.base_url
    expected = {page.canonical_url: page for page in pages}
    recorded = {page.canonical_url: _recorded_fingerprint(page) for page in pages}

    def wall_exceeded() -> bool:
        return time.monotonic() - started > wall_budget_seconds

    # -- Tier 0: re-collection (shared implementation) + the traversal
    # fetches, which double as tier-1 records for the pages they visit.
    candidate_set = CandidateSet(
        base_canonical=canonical_url(base_url), validate=validate
    )
    facts = await collect_sources(
        candidate_set,
        base_url=base_url,
        fetch=fetch,
        sitemap_fetch=sitemap_fetch,
        retry_delay=retry_delay,
        sleep=sleep,
    )
    tier1_live: dict[str, PageFingerprint] = {}
    tier1_errors: dict[str, bool] = {}

    async def on_fetch(candidate: CensusCandidate, ref: Any, fetched: FetchResult) -> None:
        # Every fetched URL's fingerprint is kept: tier 1 reads the
        # expected ones, reconcile reads the new pages' census facts.
        tier1_live[candidate.canonical_url] = page_fingerprint(
            fetched, candidate.canonical_url
        )
        tier1_errors[candidate.canonical_url] = (
            fetched.error is not None and fetched.status is None
        )

    async def on_discovered(candidate: CensusCandidate) -> Any:
        return candidate

    await traverse_link_graph(
        candidate_set,
        fetch=fetch,
        robots=facts.robots,
        base_result=facts.base_result,
        base_url=base_url,
        initial=[
            (candidate, candidate)
            for candidate in candidate_set.candidates.values()
        ],
        resolve_link=resolve_link,
        retry_delay=retry_delay,
        sleep=sleep,
        on_fetch=on_fetch,
        on_discovered=on_discovered,
    )
    result.recollected = {
        url: tuple(sorted(candidate.source_kinds))
        for url, candidate in candidate_set.candidates.items()
    }
    await emit(
        "preflight.tier.completed",
        {"tier": 0, "counts": {"tier0_urls": len(result.recollected)}},
    )

    # -- Tier 1 remainder: every expected URL the traversal never
    # visited still gets its one fingerprint fetch (canonical order).
    for url in sorted(expected):
        if url in tier1_live:
            continue
        if wall_exceeded():
            result.deferred.append({"url": url, "reason": "wall_budget"})
            continue
        fetched = await _fetch_with_retry(
            fetch, url, retry_delay=retry_delay, sleep=sleep
        )
        tier1_live[url] = page_fingerprint(fetched, url)
        tier1_errors[url] = fetched.error is not None and fetched.status is None

    result.page_fingerprints = dict(tier1_live)
    for url, page in expected.items():
        live = tier1_live.get(url)
        if live is None:
            continue  # deferred by the wall budget; the delta skips it
        result.tier1[url] = {
            "http_status": live.http_status,
            "fetch_error": bool(tier1_errors.get(url)),
            "differs": live != recorded[url],
        }
    await emit(
        "preflight.tier.completed",
        {"tier": 1, "counts": {"tier1_fetched": len(result.tier1)}},
    )

    # -- Tier 2 candidates: tier-1 differences, new URLs, and tier-0
    # anomalies (expected, absent from the collection, but fetched OK).
    candidates: list[str] = []
    for url in sorted(expected):
        record = result.tier1.get(url)
        if record is None:
            continue
        if record["fetch_error"] or record["http_status"] in (404, 410):
            # Already dispositioned by tier 1 (the delta's missing /
            # unreachable rules): a gone page has no tier-2 result by
            # construction (doc 23 section 6.5's order note).
            continue
        anomaly = url not in result.recollected \
            and record["http_status"] is not None and record["http_status"] < 400
        if record["differs"] or anomaly:
            candidates.append(url)
    new_urls = sorted(url for url in result.recollected if url not in expected)
    candidates.extend(new_urls)
    render_queue = candidates[:render_cap]
    for url in candidates[render_cap:]:
        result.deferred.append({"url": url, "reason": "render_cap"})
    if len(candidates) > render_cap:
        result.status = "partial"
        await emit(
            "preflight.cap.reached",
            {"kind": "render", "deferred_count": len(candidates) - render_cap},
        )

    for url in render_queue:
        if wall_exceeded():
            result.deferred.append({"url": url, "reason": "wall_budget"})
            result.status = "partial"
            await emit(
                "preflight.cap.reached",
                {"kind": "wall", "deferred_count": 1},
            )
            continue
        try:
            outcome = await render(url)
        except Exception:
            # One page's capture failure is that page's outcome
            # (fetch_error -> unreachable in _record_render), never
            # the whole preflight's failure (ORC1-02). Cancellation
            # is a BaseException and still propagates.
            outcome = RenderOutcome(kind="fetch_error")
        await _record_render(
            result,
            repository=repository,
            preflight=preflight,
            app_map=app_map,
            url=url,
            page=expected.get(url),
            recorded_states=states_by_page.get(expected[url].id, []) if url in expected else [],
            tier1_record=result.tier1.get(url),
            outcome=outcome,
            observed_at=now(),
        )
        entry = result.tier2.get(url)
        if entry is not None:
            await emit(
                "preflight.page.outcome",
                {
                    "url": url,
                    "outcome": entry.get("outcome"),
                    "basis": entry.get("basis"),
                    "html_drift": entry.get("html_drift"),
                    "visual_distance": entry.get("visual_distance"),
                },
            )
    await emit(
        "preflight.tier.completed",
        {
            "tier": 2,
            "counts": {
                "tier2_rendered": len(result.tier2),
                "tier2_candidates": len(candidates),
            },
        },
    )

    result.tier_counts = {
        "tier0_urls": len(result.recollected),
        "tier1_fetched": len(result.tier1),
        "tier2_rendered": len(result.tier2),
        "tier2_candidates": len(candidates),
    }
    if result.deferred:
        result.status = "partial"
    result.spend_seconds = time.monotonic() - started
    _append_page_grade_history(result, app_map=app_map, preflight=preflight,
                               pages=pages, observed_at=now())
    # Unreachable attempts are recorded too (doc 23 section 7.2 step 5):
    # one page-grade row per rendered-but-unreachable page.
    for url, entry in result.tier2.items():
        if entry.get("outcome") != "unreachable" or url not in expected:
            continue
        page = expected[url]
        result.history_rows.append(
            {
                "workspace_id": app_map.workspace_id,
                "application_id": app_map.application_id,
                "target_id": app_map.target_id,
                "app_map_id": app_map.id,
                "map_page_id": page.id,
                "map_page_state_id": None,
                "canonical_url": url,
                "state_key": "page",
                "state_id": None,
                "dom_structure_hash": None,
                "aria_hash": None,
                "screenshot_hash": None,
                "screenshot_phash": None,
                "html_sha256": None,
                "source": "preflight",
                "preflight_id": preflight.id,
                "observed_at": now(),
            }
        )
    return result


async def _record_render(
    result: SweepResult,
    *,
    repository,
    preflight: Any,
    app_map: Any,
    url: str,
    page: Any,
    recorded_states: list,
    tier1_record: dict | None,
    outcome: RenderOutcome,
    observed_at: datetime,
) -> None:
    """Fold one rendered candidate into tier-2 records + history."""

    if outcome.kind != "ok":
        reason = {
            "blocked_auth": "blocked_auth",
            "blocked_wall": "blocked_wall",
            "browser_lost": "browser_lost",
        }.get(outcome.kind, "fetch_error")
        if page is not None:
            result.tier2[url] = {"outcome": "unreachable", "reason": reason}
        return

    result.captures[url] = outcome
    live_default = outcome.states[0] if outcome.states else None
    if page is None:
        return  # a new URL: the capture is reconcile's disposition input

    recorded_default = recorded_states[0] if recorded_states else None
    signature_less = recorded_default is None or not recorded_default.state_id
    if signature_less:
        # Unharvested page: the tier-1 difference stands (basis 'html'),
        # honestly labelled; an identical fetch is present.
        if tier1_record is not None and tier1_record["differs"]:
            result.tier2[url] = {
                "outcome": "changed",
                "recorded_state_id": None,
                "live_state_id": None,
                "basis": "html",
            }
        else:
            result.tier2[url] = {"outcome": "present", "html_drift": False}
    else:
        recorded_ids = {state.state_id for state in recorded_states}
        live_ids = {state.state_id for state in outcome.states}
        if live_ids == recorded_ids:
            entry: dict[str, Any] = {
                "outcome": "present",
                "html_drift": bool(tier1_record and tier1_record["differs"]),
            }
            entry["visual_distance"] = visual_distance(
                recorded_default.screenshot_phash,
                live_default.screenshot_phash if live_default else None,
            )
            result.tier2[url] = entry
        else:
            result.tier2[url] = {
                "outcome": "changed",
                "recorded_state_id": recorded_default.state_id,
                "live_state_id": live_default.state_id if live_default else None,
                "basis": "state",
            }

    # Per-state history appends for the tier-2 observation, and the
    # section 5.4 touches on states the render proved identical.
    recorded_by_identity = {state.state_id: state for state in recorded_states}
    for live_state in outcome.states:
        recorded_state = recorded_by_identity.get(live_state.state_id)
        result.history_rows.append(
            {
                "workspace_id": app_map.workspace_id,
                "application_id": app_map.application_id,
                "target_id": app_map.target_id,
                "app_map_id": app_map.id,
                "map_page_id": page.id,
                "map_page_state_id": recorded_state.id if recorded_state else None,
                "canonical_url": url,
                "state_key": recorded_state.state_key if recorded_state else live_state.state_key,
                "state_id": live_state.state_id,
                "dom_structure_hash": live_state.dom_structure_hash,
                "aria_hash": live_state.aria_hash,
                "screenshot_hash": live_state.screenshot_hash,
                "screenshot_phash": live_state.screenshot_phash,
                "html_sha256": None,
                "source": "preflight",
                "preflight_id": preflight.id,
                "observed_at": observed_at,
            }
        )
        if (
            recorded_state is not None
            and live_state.state_id is not None
            and live_state.state_id == recorded_state.state_id
        ):
            await repository.touch_verified_state(
                recorded_state.id,
                last_verified_at=observed_at,
                screenshot_phash=live_state.screenshot_phash,
            )


def _append_page_grade_history(
    result: SweepResult,
    *,
    app_map: Any,
    preflight: Any,
    pages: list,
    observed_at: datetime,
) -> None:
    """Page-grade history rows for tier-1-only pages (section 6.4)."""

    rendered = set(result.tier2)
    for page in pages:
        url = page.canonical_url
        record = result.tier1.get(url)
        if record is None or url in rendered:
            continue
        result.history_rows.append(
            {
                "workspace_id": app_map.workspace_id,
                "application_id": app_map.application_id,
                "target_id": app_map.target_id,
                "app_map_id": app_map.id,
                "map_page_id": page.id,
                "map_page_state_id": None,
                "canonical_url": url,
                "state_key": "page",
                "state_id": None,
                "dom_structure_hash": None,
                "aria_hash": None,
                "screenshot_hash": None,
                "screenshot_phash": None,
                "html_sha256": (
                    result.page_fingerprints[url].html_sha256
                    if url in result.page_fingerprints
                    else None
                ),
                "source": "preflight",
                "preflight_id": preflight.id,
                "observed_at": observed_at,
            }
        )
