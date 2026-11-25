"""The freshness preflight job: poller, claim, supervision, lifecycle.

Mirrors the harvest job's shape (doc 23 section 9, doc 16 section 6):
a poller task in the worker claims one ``building`` map_preflights
row at a time under a Postgres advisory lock, runs the sweep, folds
the outcome into the preflight delta, writes the swept version's
freshness fields, and — only when the outcome carries changed,
missing or new pages — hands off to reconcile to mint the successor.

Zero model calls happen anywhere in this package (T-FJ8 pins it):
the sweep compares fingerprints, reconcile copies and re-observes,
and the only model-adjacent step, scoped re-enrichment, rides the
harvest package's existing allowlisted entry point inside reconcile.
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from markettwin_execution_orchestrator.freshness.freshness_repository import (
    FreshnessRepository,
)
from markettwin_execution_orchestrator.worker import STALL_WATCHDOG_SECONDS

logger = logging.getLogger(__name__)

# Orchestrator poller settings (doc 23 section 11) [J]. They live here,
# beside the poller — the orchestrator has no config module; the
# harvest poller's HARVEST_POLL_SECONDS / HARVEST_SLOTS are the
# precedent.
PREFLIGHT_POLL_SECONDS = 5
PREFLIGHT_SLOTS = 1

# Freshness engine constants (doc 23 section 11) [J].
PREFLIGHT_WALL_BUDGET_SECONDS = 1800
PREFLIGHT_RENDER_CAP = 150
PREFLIGHT_NEW_PAGE_CAP = 100
PREFLIGHT_PAGE_BUDGET_SECONDS = 60
PREFLIGHT_ORPHAN_EVENT_MINUTES = 30

# A stage is an async callable the job invokes at its seam; tests
# inject fakes, production wires the sweep/reconcile composition.
SweepStage = Callable[..., Awaitable[dict]]
ReconcileStage = Callable[..., Awaitable[UUID | None]]


def _failure_site() -> str:
    """``"<module>:<function>"`` of the catching frame (doc 23 §10).

    Called directly from the ``except`` block, so the catching frame
    is one above this helper on the stack.
    """

    frame = traceback.extract_stack()[-2]
    return f"{Path(frame.filename).stem}:{frame.name}"


async def execute_preflight(
    repository: FreshnessRepository,
    preflight: Any,
    *,
    sweep_stage: SweepStage,
    reconcile_stage: ReconcileStage | None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    """Run one claimed preflight to a terminal state; return the status.

    Stage contract: ``sweep_stage(repository, preflight, app_map)``
    returns ``{result, delta}`` (the SweepResult and the preflight
    delta payload); ``reconcile_stage(repository, preflight, app_map,
    result, delta)`` mints the successor when the outcome requires one
    and returns its id. Any exception escaping a stage is a job crash
    (doc 23 section 10): the preflight closes ``failed`` with the
    retained-error trio. Repository stages commit independently: a later
    failure can leave a successor, demotions, history or freshness already
    persisted. The failed preflight is not a successful verification receipt;
    callers must disclose its failure rather than infer success from map fields.
    """

    started = time.monotonic()
    app_map = await repository.get_map(preflight.app_map_id)
    if app_map is None:
        await repository.fail_preflight(
            preflight.id,
            failure_code="map_missing",
            failure_message=f"swept map {preflight.app_map_id} no longer exists",
            failure_site="freshness_job:execute_preflight",
            completed_at=now(),
        )
        await repository.record_event(
            preflight.id,
            "preflight.failed",
            {"failure_code": "map_missing",
             "failure_site": "freshness_job:execute_preflight"},
        )
        return "failed"

    async def emit(event_type: str, payload: dict) -> None:
        await repository.record_event(preflight.id, event_type, payload)

    try:
        pages = await repository.list_pages(app_map.id)
        await emit(
            "preflight.started",
            {"pages_total": len(pages), "trigger": preflight.trigger},
        )
        swept = await sweep_stage(repository, preflight, app_map)
        result, delta = swept["result"], swept["delta"]
        counts = delta["counts"]

        resulting_map_id: UUID | None = None
        needs_successor = bool(
            counts["changed"] or counts["missing"] or counts["new"]
        )
        if needs_successor and reconcile_stage is not None:
            await emit("preflight.reconcile.started", {"base_map_id": str(app_map.id)})
            resulting_map_id = await reconcile_stage(
                repository, preflight, app_map, result, delta
            )
            await emit(
                "preflight.reconcile.completed",
                {
                    "resulting_map_id": str(resulting_map_id)
                    if resulting_map_id
                    else None,
                },
            )

        completed_at = now()
        status = result.status  # 'ready' | 'partial' from the sweep
        # Freshness state on the swept version (doc 23 section 4.4): a
        # completed all-present outcome with no new pages is 'current';
        # any other completed outcome is measured drift — 'stale'. A
        # partial never sets 'current' (C11).
        all_present = (
            status == "ready"
            and counts["present"] == delta["expected_in_snapshot"]
            and counts["new"] == 0
        )
        await repository.update_map_freshness(
            app_map.id,
            freshness_state="current" if all_present else "stale",
            last_preflight_at=completed_at,
            freshness_metrics={
                "preflight_id": str(preflight.id),
                "outcome_counts": counts,
                "deferred_count": len(result.deferred),
                "basis_counts": delta["basis_counts"],
                "completed_at": completed_at.isoformat(),
            },
        )
        if result.history_rows:
            await repository.append_history(result.history_rows)
        await repository.complete_preflight(
            preflight.id,
            status=status,
            outcome=delta,
            deferred=result.deferred,
            tier_counts=result.tier_counts,
            spend_seconds=time.monotonic() - started,
            completed_at=completed_at,
        )
        await emit(
            "preflight.completed", {"status": status, "outcome_counts": counts}
        )
        return status
    except Exception as exc:  # job crash: terminal write, never a raise
        failure_site = _failure_site()
        await repository.fail_preflight(
            preflight.id,
            failure_code=type(exc).__name__,
            failure_message=str(exc),
            failure_site=failure_site,
            completed_at=now(),
        )
        await repository.record_event(
            preflight.id,
            "preflight.failed",
            {"failure_code": type(exc).__name__, "failure_site": failure_site},
        )
        logger.exception("preflight %s failed", preflight.id)
        return "failed"


async def reap_orphans(
    repository: FreshnessRepository,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    orphan_event_minutes: int = PREFLIGHT_ORPHAN_EVENT_MINUTES,
    skip_ids: frozenset = frozenset(),
) -> int:
    """Fail ``building`` rows whose latest event is too old (doc 23
    section 9.2). Aliveness is measured by events, never started_at:
    a healthy long job keeps emitting and is never reaped. Rows this
    poller is currently running are skipped — their supervision is
    the stall watchdog's, below."""

    reaped = 0
    cutoff = now() - timedelta(minutes=orphan_event_minutes)
    for preflight in await repository.list_building_preflights(limit=50):
        if preflight.id in skip_ids:
            continue
        latest = await repository.latest_event_at(preflight.id)
        if latest is not None and latest >= cutoff:
            continue
        if latest is None and preflight.started_at >= cutoff:
            continue  # just created; its first event is imminent
        await repository.fail_preflight(
            preflight.id,
            failure_code="preflight_orphaned",
            failure_message=(
                "no preflight event for "
                f"{orphan_event_minutes} minutes and no live claim"
            ),
            failure_site="freshness_job:reap_orphans",
            completed_at=now(),
        )
        reaped += 1
    return reaped


async def run_preflight_poller(
    session_factory,
    *,
    sweep_stage: SweepStage | None = None,
    reconcile_stage: ReconcileStage | None = None,
    poll_seconds: float = PREFLIGHT_POLL_SECONDS,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
    """Poll for building preflights and run them one at a time.

    The claim is a Postgres advisory lock (``pg_try_advisory_lock`` on
    ``hashtext('preflight:' || id)``, doc 23 section 9.1) held on a
    dedicated session for the job's whole duration. Supervision (same
    section): a running job whose latest event is older than
    ``STALL_WATCHDOG_SECONDS`` — imported from worker, never
    re-declared — is cancelled and closed ``preflight_stalled``;
    event-silent rows nobody is running are orphan-reaped. A failed
    job never blocks the queue: the claim dies with its session and
    polling continues.
    """

    repository = FreshnessRepository(session_factory)
    if sweep_stage is None or reconcile_stage is None:
        sweep_stage, reconcile_stage = _build_production_stages(session_factory)
    running: dict[UUID, asyncio.Task] = {}
    await reap_orphans(repository, now=now)
    while True:
        try:
            # Stall supervision over this poller's own running jobs.
            for preflight_id, task in list(running.items()):
                if task.done():
                    del running[preflight_id]
                    continue
                latest = await repository.latest_event_at(preflight_id)
                if (
                    latest is not None
                    and (now() - latest).total_seconds() > STALL_WATCHDOG_SECONDS
                ):
                    task.cancel()
                    # Await the cancelled job before its terminal
                    # write, bounded by the same teardown bound its
                    # stage room uses: the job's teardown must not
                    # race the close or the next claim (ORC1-04).
                    from markettwin_execution_orchestrator.workflow.slop_run import (
                        TEARDOWN_TIMEOUT_SECONDS,
                    )

                    await asyncio.wait(
                        {task}, timeout=TEARDOWN_TIMEOUT_SECONDS
                    )
                    if task.done() and not task.cancelled():
                        task_error = task.exception()
                        if task_error is not None:
                            logger.warning(
                                "stalled preflight %s ended with %r",
                                preflight_id, task_error,
                            )
                    await repository.fail_preflight(
                        preflight_id,
                        failure_code="preflight_stalled",
                        failure_message=(
                            "no preflight event for "
                            f"{STALL_WATCHDOG_SECONDS} seconds"
                        ),
                        failure_site="freshness_job:stall_watchdog",
                        completed_at=now(),
                    )
                    del running[preflight_id]
            await reap_orphans(
                repository, now=now, skip_ids=frozenset(running)
            )
            if len(running) < PREFLIGHT_SLOTS:
                for preflight in await repository.list_building_preflights(
                    limit=PREFLIGHT_SLOTS
                ):
                    if preflight.id in running:
                        continue
                    task = asyncio.create_task(
                        _run_claimed(
                            session_factory,
                            repository,
                            preflight,
                            sweep_stage=sweep_stage,
                            reconcile_stage=reconcile_stage,
                        )
                    )
                    running[preflight.id] = task
                    break  # one claim per poll; slots refill next pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("preflight poller iteration failed; continuing")
        await asyncio.sleep(poll_seconds)


async def _run_claimed(
    session_factory,
    repository: FreshnessRepository,
    preflight: Any,
    *,
    sweep_stage: SweepStage,
    reconcile_stage: ReconcileStage | None,
) -> None:
    """Hold the advisory lock for one job, then run it.

    A transaction-scoped lock lives on a separate session. Closing that
    session rolls back the claim transaction and releases the lock.
    """

    from sqlalchemy import text

    async with session_factory() as lock_session:
        acquired = await lock_session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
            {"key": f"preflight:{preflight.id}"},
        )
        if not acquired:
            return  # another worker holds this sweep; polling continues
        await execute_preflight(
            repository,
            preflight,
            sweep_stage=sweep_stage,
            reconcile_stage=reconcile_stage,
        )


BUILDER_VERSION = "freshness-4.1"
_SWEEP_FETCH_MAX_BYTES = 2_000_000
_SWEEP_USER_AGENT = "MarketTwinCensus/1a"


def _build_production_stages(
    session_factory,
) -> tuple[SweepStage, ReconcileStage]:
    """Production stage wiring (doc 23 sections 6/7): the sweep stage
    runs the shared census collection over the recorded pages with a
    room-bound renderer for tier 2; the reconcile stage re-observes
    through the harvest visit seam. Every heavy import is deferred —
    the browser, the harvest package and the model door load only
    when a preflight actually runs (the deferred-import discipline of
    harvest_job.production_stages)."""

    from markettwin_execution_orchestrator.freshness.preflight_sweep import (
        PREFLIGHT_FETCH_TIMEOUT_SECONDS,
    )
    from markettwin_execution_orchestrator.workflow.coverage_delta import (
        build_preflight_delta,
    )

    repository = FreshnessRepository(session_factory)

    async def sweep_stage(repository, preflight, app_map):
        from markettwin_shared.census_sources import CENSUS_SITEMAP_MAX_BYTES

        from markettwin_execution_orchestrator.freshness.preflight_sweep import (
            run_sweep,
        )

        pages = await repository.list_pages(app_map.id)
        states_by_page: dict[UUID, list] = {}
        for state in await repository.list_states(app_map.id):
            states_by_page.setdefault(state.map_page_id, []).append(state)
        for page_states in states_by_page.values():
            # The landing state leads: the sweep treats the first
            # recorded state as the page's default.
            page_states.sort(key=lambda row: row.state_key != "default")

        room = _StageRoom(
            run_key=preflight.id,
            base_url=app_map.base_url,
            page_budget_seconds=PREFLIGHT_PAGE_BUDGET_SECONDS,
            capture_network=False,
        )
        fetch = _SweepFetcher(
            max_bytes=_SWEEP_FETCH_MAX_BYTES,
            timeout_seconds=PREFLIGHT_FETCH_TIMEOUT_SECONDS,
            validate=room.validate,
        )
        sitemap_fetch = _SweepFetcher(
            max_bytes=CENSUS_SITEMAP_MAX_BYTES,
            timeout_seconds=PREFLIGHT_FETCH_TIMEOUT_SECONDS,
            validate=room.validate,
        )
        try:
            result = await run_sweep(
                repository=repository,
                preflight=preflight,
                app_map=app_map,
                pages=pages,
                states_by_page=states_by_page,
                fetch=fetch,
                sitemap_fetch=sitemap_fetch,
                render=room.render,
                validate=room.validate,
                resolve_link=_resolve_same_site,
                emit=lambda event_type, payload: repository.record_event(
                    preflight.id, event_type, payload),
                render_cap=PREFLIGHT_RENDER_CAP,
                wall_budget_seconds=PREFLIGHT_WALL_BUDGET_SECONDS,
            )
        finally:
            await room.close()
        block = {
            "map_id": str(app_map.id),
            "version_number": app_map.version_number,
            "routes_truncated": False,
            "counts": {"expected": len(pages)},
            "pages": [
                {
                    "url": page.canonical_url,
                    "status": page.crawl_status,
                    "states": [
                        {"state_id": state.state_id}
                        for state in states_by_page.get(page.id, [])
                    ],
                }
                for page in pages
            ],
        }
        delta = build_preflight_delta(
            map_block=block,
            tier1=result.tier1,
            tier2=result.tier2,
            recollected=result.recollected,
        )
        return {"result": result, "delta": delta}

    async def reconcile_stage(repository, preflight, app_map, result, delta):
        from markettwin_execution_orchestrator.freshness.reconcile import (
            reconcile_preflight,
        )
        from markettwin_execution_orchestrator.harvest.harvest_repository import (
            HarvestRepository,
        )

        harvest_repository = HarvestRepository(session_factory)
        room = _StageRoom(
            run_key=preflight.id,
            base_url=app_map.base_url,
            page_budget_seconds=PREFLIGHT_PAGE_BUDGET_SECONDS,
            capture_network=True,
        )

        async def persist_changed_pages(
            repository, successor, result, changed_urls, observed_at
        ):
            return await _visit_pages(
                harvest_repository=harvest_repository,
                room=room,
                repository=repository,
                successor=successor,
                urls=changed_urls,
                observed_at=observed_at,
                mark_reconciled=True,
            )

        async def visit_new_pages(repository, successor, urls, observed_at):
            return await _visit_pages(
                harvest_repository=harvest_repository,
                room=room,
                repository=repository,
                successor=successor,
                urls=urls,
                observed_at=observed_at,
                mark_reconciled=False,
            )

        async def enrich_touched(repository, successor, changed_urls, scoped_new):
            await _enrich_touched(
                harvest_repository=harvest_repository,
                successor=successor,
                urls=set(changed_urls) | {entry["url"] for entry in scoped_new},
                aria_excerpts=room.aria_excerpts,
            )

        async def demote_skills(repository, successor, delta, observed_at):
            return await _demote_skills(
                freshness_repository=repository,
                harvest_repository=harvest_repository,
                successor=successor,
                delta=delta,
            )

        try:
            return await reconcile_preflight(
                repository,
                preflight,
                app_map,
                result,
                delta,
                persist_changed_pages=persist_changed_pages,
                visit_new_pages=visit_new_pages,
                enrich_touched=enrich_touched,
                demote_skills=demote_skills,
                new_page_cap=PREFLIGHT_NEW_PAGE_CAP,
            )
        finally:
            await room.close()

    return sweep_stage, reconcile_stage


class _SweepFetcher:
    """The sweep's fetcher: the census fetch contract (doc 16 section
    6.1) on the orchestrator side — manual redirects with per-hop
    validation, a streamed byte cap, and CensusFetchError on
    transport failure, so the shared collection's retry treats it
    exactly as it treats control-api's fetcher."""

    def __init__(self, *, max_bytes: int, timeout_seconds: float, validate):
        self._max_bytes = max_bytes
        self._timeout_seconds = timeout_seconds
        self._validate = validate

    async def __call__(self, url: str):
        from urllib.parse import urljoin

        import httpx
        from markettwin_shared.census_sources import (
            CensusFetchError,
            FetchHop,
            FetchResult,
        )

        chain: list[FetchHop] = []
        current = url
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=self._timeout_seconds,
            headers={"User-Agent": _SWEEP_USER_AGENT},
        ) as client:
            for _hop in range(6):
                try:
                    self._validate(current)
                except ValueError:
                    return FetchResult(
                        requested_url=url,
                        final_url=None,
                        status=None,
                        headers={},
                        body=b"",
                        redirect_chain=tuple(chain),
                        blocked_hop=True,
                    )
                try:
                    async with client.stream("GET", current) as response:
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > self._max_bytes:
                                raise CensusFetchError(
                                    f"Response from {current} exceeded the "
                                    "byte cap."
                                )
                        headers = {
                            key.lower(): value
                            for key, value in response.headers.items()
                        }
                        status = response.status_code
                except httpx.RequestError as exc:
                    raise CensusFetchError(
                        f"GET {current} failed: {exc}"
                    ) from exc
                location = headers.get("location")
                if status in (301, 302, 303, 307, 308) and location:
                    following = urljoin(current, location)
                    chain.append(
                        FetchHop(url=current, status=status)
                    )
                    current = following
                    continue
                return FetchResult(
                    requested_url=url,
                    final_url=current,
                    status=status,
                    headers=headers,
                    body=bytes(body),
                    redirect_chain=tuple(chain),
                )
        return FetchResult(
            requested_url=url,
            final_url=current,
            status=None,
            headers={},
            body=b"",
            redirect_chain=tuple(chain),
            error="Too many redirects.",
        )


def _resolve_same_site(base_url: str, href: str | None, crawl_base: str | None = None) -> str | None:
    """Resolve a link against the crawl base, same-origin only (the
    collection re-validates origin itself; this only shapes the
    candidate)."""

    from urllib.parse import urljoin

    if href is None:
        return None
    resolved = urljoin(base_url, href)
    base_parts = urlsplit(crawl_base or base_url)
    parts = urlsplit(resolved)
    if (base_parts.scheme, base_parts.hostname, base_parts.port) != (
        parts.scheme,
        parts.hostname,
        parts.port,
    ):
        return None
    return resolved


class _StageRoom:
    """One browser room for a stage (doc 23 section 6.3): opened
    lazily, shared by every render in the stage, closed under the
    teardown bound. A lost browser ends the room; the next render
    opens a fresh one (section 9.2). The render walk mirrors the
    harvest visit's fence — read/reversible controls only, the same
    caps — but keeps captures in memory: the sweep classifies, it
    does not persist (reconcile re-observes what changed)."""

    def __init__(
        self,
        *,
        run_key: UUID,
        base_url: str,
        page_budget_seconds: float,
        capture_network: bool,
    ):
        from markettwin_execution_orchestrator.browser.controller import (
            AllowedOrigin,
        )

        parts = urlsplit(base_url)
        self._origin = AllowedOrigin(parts.scheme, parts.hostname, parts.port)
        self._run_key = run_key
        self._page_budget_seconds = page_budget_seconds
        self._capture_network = capture_network
        self._controller = None
        self._handle = None
        self.execution_id = uuid4()
        self.journey_id = uuid4()
        self.network = None
        self.aria_excerpts: dict[str, str] = {}

    @property
    def controller(self):
        return self._controller

    @property
    def handle(self):
        return self._handle

    def validate(self, url: str) -> None:
        """The collection's validator contract: raise ValueError on a
        forbidden target. The run's own browser policy is the rule —
        guardrail G1 (never fetch internal/private/loopback/link-local
        addresses) plus same-origin for this crawl."""

        from markettwin_execution_orchestrator.browser.policy import (
            TargetUrlValidationError,
            validate_target_url,
        )

        try:
            validate_target_url(url, (self._origin,), "public_only")
        except TargetUrlValidationError as exc:
            raise ValueError(str(exc)) from exc

    async def ensure(self):
        from markettwin_execution_orchestrator.browser.controller import (
            BrowserController,
        )
        from markettwin_execution_orchestrator.harvest.harvest_capture import (
            NetworkCapture,
        )

        if self._handle is None:
            self._controller = BrowserController()
            self._handle = await self._controller.open_room_session(
                run_id=self._run_key,
                execution_id=self.execution_id,
                journey_id=self.journey_id,
                allowed_origins=[self._origin],
                network_policy="public_only",
                js_capture=True,
            )
            if self._capture_network:
                # Reconcile's visits record harvest evidence (the
                # network capture the visit seam reads). The sweep
                # renders without one — no HAR in preflight
                # (doc 23 section 6.3).
                session = self._controller._get_session(
                    session_id=self._handle.session_id
                )
                self.network = NetworkCapture()
                self.network.install(session.context)
        return self._handle

    def _dead(self) -> bool:
        try:
            session = self._controller._get_session(
                session_id=self._handle.session_id
            )
            return session is None or session.page.is_closed()
        except Exception:
            return True

    async def close(self) -> None:
        from markettwin_execution_orchestrator.workflow.slop_run import (
            TEARDOWN_TIMEOUT_SECONDS,
        )

        if self._controller is None or self._handle is None:
            return
        try:
            async with asyncio.timeout(TEARDOWN_TIMEOUT_SECONDS):
                await self._controller.close_room(run_id=self._run_key)
        except Exception:
            pass
        self._handle = None
        self._controller = None
        self.network = None

    async def render(self, url: str):
        import hashlib
        from pathlib import Path

        from markettwin_shared.app_map_common import (
            canonical_url,
            has_wall_markers,
            is_login_path,
        )

        from markettwin_execution_orchestrator.freshness.phash import screenshot_phash
        from markettwin_execution_orchestrator.freshness.preflight_sweep import (
            RenderedState,
            RenderOutcome,
        )
        from markettwin_execution_orchestrator.harvest.harvest_capture import (
            capture_state,
        )
        from markettwin_execution_orchestrator.harvest.harvest_inventory import (
            _FENCE_ACTIONABILITY,
            _FENCE_SAFETY,
            HARVEST_PAGE_STATE_CAP,
            HARVEST_STATE_ACTION_CAP,
            _body_text,
            _current_url,
            _dismiss_consent,
            distil_elements,
            distil_forms,
            identity_for,
        )

        try:
            handle = await self.ensure()
        except Exception:
            return RenderOutcome(kind="browser_lost")
        controller = self._controller

        async def capture_once(state_key: str):
            capture = await capture_state(
                controller,
                handle,
                execution_id=self.execution_id,
                journey_id=self.journey_id,
            )
            elements = distil_elements(capture)
            state_id, _, _ = identity_for(
                capture.url, elements, distil_forms(capture)
            )
            raw = b""
            if capture.screenshot_path:
                raw = await asyncio.to_thread(
                    Path(capture.screenshot_path).read_bytes
                )
            rendered = RenderedState(
                state_id=state_id,
                state_key=state_key,
                dom_structure_hash=capture.dom_structure_hash,
                aria_hash=capture.aria_hash,
                screenshot_hash=hashlib.sha256(raw).hexdigest() if raw else None,
                screenshot_phash=screenshot_phash(raw) if raw else None,
                capture=capture,
            )
            return rendered, elements

        def fence_candidates(elements):
            return [
                element
                for element in elements
                if element["actionability"] in _FENCE_ACTIONABILITY
                and element["safety_class"] in _FENCE_SAFETY
            ]

        try:
            navigation = await controller.navigate(
                session_id=handle.session_id,
                url=url,
                execution_id=self.execution_id,
                journey_id=self.journey_id,
                observe=True,
            )
        except Exception:
            if self._dead():
                await self.close()
                return RenderOutcome(kind="browser_lost")
            return RenderOutcome(kind="fetch_error")
        landed = (
            navigation.observation.url
            if navigation.observation is not None
            else await _current_url(controller, handle)
        )
        if is_login_path(urlsplit(landed).path):
            return RenderOutcome(kind="blocked_auth")
        if has_wall_markers(await _body_text(controller, handle)):
            return RenderOutcome(kind="blocked_wall")
        await _dismiss_consent(
            controller, handle, execution_id=self.execution_id, journey_id=self.journey_id)

        deadline = time.monotonic() + self._page_budget_seconds
        landing, landing_elements = await capture_once("default")
        states = [landing]
        known = {landing.state_id: landing}
        elements_by_identity = {landing.state_id: landing_elements}
        openers: dict[str, tuple[str, str]] = {}
        current = landing
        queue = [
            (element["role"], element["name"])
            for element in fence_candidates(landing_elements)
        ]
        attempted: set[tuple[str, str]] = set()
        actions = 0
        while (
            queue
            and len(states) < HARVEST_PAGE_STATE_CAP
            and actions < HARVEST_STATE_ACTION_CAP
            and time.monotonic() < deadline
        ):
            key = queue.pop(0)
            if key in attempted:
                continue
            attempted.add(key)
            actions += 1
            live = next(
                (
                    element
                    for element in elements_by_identity[current.state_id]
                    if (element["role"], element["name"]) == key
                ),
                None,
            )
            if live is None:
                continue
            try:
                outcome = await controller.click(
                    session_id=handle.session_id,
                    role=live["role"], name=live["name"],
                    execution_id=self.execution_id,
                    journey_id=self.journey_id,
                    observe=True,
                )
            except Exception:
                if self._dead():
                    await self.close()
                    return RenderOutcome(kind="browser_lost")
                continue
            await asyncio.sleep(0.3)
            landed_now = (
                outcome.observation.url
                if outcome.observation is not None
                else await _current_url(controller, handle)
            )
            if canonical_url(landed_now) != canonical_url(url):
                # The control navigated away: return to the page and
                # reopen the state we were standing on, exactly as
                # the harvest visit recovers.
                try:
                    await controller.navigate(
                        session_id=handle.session_id,
                        url=url,
                        execution_id=self.execution_id,
                        journey_id=self.journey_id,
                        observe=True,
                    )
                except Exception:
                    break
                opener_key = openers.get(current.state_id)
                if opener_key is not None:
                    opener = next(
                        (
                            element
                            for element in elements_by_identity[
                                landing.state_id
                            ]
                            if (element["role"], element["name"]) == opener_key
                        ),
                        None,
                    )
                    if opener is None:
                        break
                    try:
                        await controller.click(
                            session_id=handle.session_id,
                            role=opener["role"], name=opener["name"],
                            execution_id=self.execution_id,
                            journey_id=self.journey_id,
                            observe=True,
                        )
                        await asyncio.sleep(0.3)
                    except Exception:
                        break
                continue
            probe, probe_elements = await capture_once(
                f"observed-{len(states)}"
            )
            if probe.state_id == current.state_id:
                continue
            if probe.state_id in known:
                current = known[probe.state_id]
            else:
                states.append(probe)
                known[probe.state_id] = probe
                elements_by_identity[probe.state_id] = probe_elements
                openers[probe.state_id] = key
                current = probe
            queue.extend(
                (element["role"], element["name"])
                for element in fence_candidates(
                    elements_by_identity[current.state_id]
                )
                if (element["role"], element["name"]) not in attempted
            )
        return RenderOutcome(
            kind="ok", states=states, title=landing.capture.title
        )


def _evidence_store():
    from markettwin_execution_orchestrator.harvest.harvest_capture import (
        S3EvidenceStore,
    )
    from markettwin_execution_orchestrator.persistence.artifact_storage import S3ArtifactStorage

    return S3EvidenceStore(S3ArtifactStorage.from_environment())


async def _visit_pages(
    *,
    harvest_repository,
    room: _StageRoom,
    repository: FreshnessRepository,
    successor,
    urls,
    observed_at: datetime,
    mark_reconciled: bool,
) -> dict[str, str]:
    """Re-observe pages on the successor through the harvest visit
    seam (doc 23 section 7.2 steps 2-3): each visit dispositions the
    page, lands its inventory and evidence, and appends the page's
    fingerprint history (section 8.3)."""

    from markettwin_execution_orchestrator.harvest.harvest_inventory import (
        visit_page,
    )

    outcomes: dict[str, str] = {}
    if not urls:
        return outcomes
    handle = await room.ensure()
    store = _evidence_store()
    preflight_ref = (successor.census_config or {}).get("preflight_id")
    preflight_id = UUID(preflight_ref) if preflight_ref else None
    for url in sorted(urls):
        page = await repository.get_page_by_url(successor.id, url)
        if page is None:
            continue
        outcome = await visit_page(
            controller=room.controller,
            handle=handle,
            repository=harvest_repository,
            store=store,
            app_map=successor,
            page=page,
            execution_id=room.execution_id,
            journey_id=room.journey_id,
            network=room.network,
            deadline=time.monotonic() + PREFLIGHT_PAGE_BUDGET_SECONDS,
        )
        await harvest_repository.mark_page_harvest(page.id, outcome.disposition)
        outcomes[url] = outcome.disposition
        room.aria_excerpts[url] = outcome.aria_excerpt
        if mark_reconciled:
            await repository.mark_reconciled_states(
                successor.id, page.id, observed_at=observed_at
            )
        states = await harvest_repository.list_states(page.id)
        await repository.append_history(
            [
                dict(
                    workspace_id=successor.workspace_id,
                    application_id=successor.application_id,
                    target_id=successor.target_id,
                    app_map_id=successor.id,
                    map_page_id=page.id,
                    map_page_state_id=state.id,
                    canonical_url=page.canonical_url,
                    state_key=state.state_key,
                    state_id=state.state_id,
                    dom_structure_hash=state.dom_structure_hash,
                    aria_hash=state.aria_hash,
                    screenshot_hash=state.screenshot_hash,
                    screenshot_phash=state.screenshot_phash,
                    html_sha256=None,
                    source="reconcile",
                    preflight_id=preflight_id,
                    observed_at=observed_at,
                )
                for state in states
            ],
        )
    return outcomes


async def _enrich_touched(
    *, harvest_repository, successor, urls: set[str],
    aria_excerpts: dict[str, str] | None = None,
) -> None:
    """Scoped enrichment for the pages reconcile touched (doc 23
    section 7.4): the harvest enrichment, over the touched pages
    only, accounting on the successor's own row."""

    from markettwin_execution_orchestrator.harvest.harvest_enrich import (
        Exemplar,
        ModelApiDoor,
        default_accountant,
        enrich_map,
        group_pages,
    )

    if not urls:
        return
    pages = [
        page
        for page in await harvest_repository.work_list(successor)
        if page.canonical_url in urls
    ]
    if not pages:
        return
    entries = []
    exemplars = {}
    for page in pages:
        default_state = await harvest_repository.get_default_state(page.id)
        entries.append(
            (page, default_state.dom_structure_hash if default_state else None)
        )
        if default_state is None:
            continue
        elements = await harvest_repository.list_elements_for_state(
            default_state.id
        )
        fields = await harvest_repository.list_fields_for_state(default_state.id)
        exemplars[page.id] = Exemplar(
            url=page.canonical_url,
            route_pattern=page.route_pattern,
            title=page.title or "",
            element_names=[element.name for element in elements],
            form_labels=[field.label for field in fields],
            aria_excerpt=(aria_excerpts or {}).get(page.canonical_url, ""),
        )
    await enrich_map(
        repository=harvest_repository,
        app_map=successor,
        groups=group_pages(entries),
        exemplars=exemplars,
        door=ModelApiDoor(),
        accountant=default_accountant,
    )


async def _demote_skills(
    *,
    freshness_repository: FreshnessRepository,
    harvest_repository,
    successor,
    delta: dict,
) -> list[str]:
    """Demote the active skills whose verified fingerprints touch a
    changed state (doc 23 section 7.5): the six-state lifecycle's own
    transition authority is the only writer, with the demotion
    evidence the transition table requires. A skill whose journey
    crosses a missing page is exposed the same way — its start and
    terminal states join the changed set."""

    from markettwin_execution_orchestrator.harvest.skill_library import (
        transition_version,
    )

    base_ref = (successor.census_config or {}).get("base_map_id")
    if not base_ref:
        return []
    base = await freshness_repository.get_map(UUID(base_ref))
    if base is None:
        return []
    changed_urls = {entry["url"] for entry in delta.get("changed", [])}
    missing_urls = {entry["url"] for entry in delta.get("missing", [])}
    base_pages = await freshness_repository.list_pages(base.id)
    page_by_id = {page.id: page for page in base_pages}
    base_states = await freshness_repository.list_states(base.id)
    state_by_row = {state.id: state for state in base_states}
    changed_state_ids = {
        state.state_id
        for state in base_states
        if state.state_id
        and state.map_page_id in page_by_id
        and page_by_id[state.map_page_id].canonical_url in changed_urls
    }
    affected_page_ids = {
        page.id for page in base_pages if page.canonical_url in missing_urls | changed_urls
    }
    if affected_page_ids:
        for journey in await freshness_repository.list_journeys(base.id):
            steps = [
                step
                for step in (journey.steps or [])
                if isinstance(step, dict) and step.get("map_page_state_id")
            ]
            step_states = [
                state_by_row.get(UUID(str(step["map_page_state_id"])))
                for step in steps
            ]
            crosses = (
                journey.success_state_id in state_by_row
                and state_by_row[journey.success_state_id].map_page_id
                in affected_page_ids
            ) or any(
                state is not None and state.map_page_id in affected_page_ids
                for state in step_states
            )
            if not crosses:
                continue
            if (
                step_states
                and step_states[0] is not None
                and step_states[0].state_id
            ):
                changed_state_ids.add(step_states[0].state_id)
            terminal = state_by_row.get(journey.success_state_id)
            if terminal is not None and terminal.state_id:
                changed_state_ids.add(terminal.state_id)
    if not changed_state_ids:
        return []
    preflight_ref = (successor.census_config or {}).get("preflight_id")
    demoted: list[str] = []
    skills = await harvest_repository.list_skills_for_scope(
        workspace_id=base.workspace_id,
        application_id=base.application_id,
        target_id=base.target_id,
    )
    for skill in skills:
        versions = await harvest_repository.list_versions_for_skill(skill.id)
        for version in versions:
            if version.lifecycle_status != "active":
                continue
            fingerprint = version.verified_fingerprint or {}
            start = fingerprint.get("start_state_id")
            terminal = fingerprint.get("terminal_state_id")
            if start not in changed_state_ids and terminal not in changed_state_ids:
                continue
            await transition_version(
                harvest_repository,
                version.id,
                to_status="suspect",
                kind="demotion",
                evidence={
                    "demotion": {
                        "start_state_id": start,
                        "terminal_state_id": terminal,
                        "changed_state_ids": sorted(changed_state_ids),
                    }
                },
                job_ref=f"preflight:{preflight_ref}",
            )
            demoted.append(str(version.id))
    return demoted
