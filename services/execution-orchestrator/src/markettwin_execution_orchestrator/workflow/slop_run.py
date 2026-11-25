"""Slop run executor (U-P6-05): crawl the app on the Room, measure
every visited state, publish verdict rows. Judging is deterministic
code (slop/measure.py); aggregation happens in evaluation from the
published rows — the executor emits no percentage of its own.
"""

import asyncio
import hashlib
import json
import logging
import re
import time

from contextlib import asynccontextmanager, contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4
from urllib.parse import urljoin, urlsplit

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import PendingRollbackError

from markettwin_database.models import TestRun, RunEvent
from markettwin_shared.run_failure import failure_details
from markettwin_shared.run_kind import UI_AUDIT_OBJECTIVE
from markettwin_shared.slop_aggregate import SLOP_EVALUATION_CONTRACT_VERSION

from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.browser.auth_verifier import is_account_entry_route
from markettwin_execution_orchestrator.browser.errors import (
    BrowserActionBlockedError,
    BrowserActionError,
    BrowserPolicyError,
    BrowserSessionNotFoundError,
    BrowserSessionStateError,
    BrowserTimeoutError,
    HostResolutionError,
    HumanAssistanceSkipped,
    HumanControlActiveError,
    SuspiciousEgressError,
    TargetUrlValidationError,
    UnsafeDestinationAddressError,
)
from markettwin_execution_orchestrator.browser.offsite import OffsiteJourneyStopped
from markettwin_execution_orchestrator.browser.policy import validate_target_url
from markettwin_execution_orchestrator.workflow.case_execution import (
    AuthenticationVerificationBlocked,
    BrowserHandoffExecution,
    request_browser_handoff,
)
from markettwin_execution_orchestrator.workflow.cooperative_pause import cooperative_pause_checkpoint
from markettwin_execution_orchestrator.workflow.offsite_browsing import configure_offsite
from markettwin_execution_orchestrator.workflow.app_plan import planned_routes
from markettwin_execution_orchestrator.persistence import ExecutionRepository, PlanRepository
from markettwin_execution_orchestrator.slop.interactions import audit_url as canonical_url
from markettwin_execution_orchestrator.workflow.lead_review import review_checkpoint
from markettwin_execution_orchestrator.slop.visual_review import review_screenshots
from markettwin_execution_orchestrator.slop.probe import non_html_type
from markettwin_execution_orchestrator.slop.inventory import (
    account_for_page,
    inventory_for_page,
)
from markettwin_execution_orchestrator.slop.interactions import inspect_interactions, view_fingerprint
from markettwin_execution_orchestrator.slop.evidence import retain_finding_evidence, save_state_evidence
from markettwin_execution_orchestrator.persistence.run_event_repository import (
    RunEventRepository,
)
from markettwin_execution_orchestrator.persistence import run_state_repository
from markettwin_execution_orchestrator.slop.measure import (
    dedupe_js_errors,
    measure_state,
    compare_components,
)
from markettwin_execution_orchestrator.slop.pool import (
    MAX_LANE_COUNT,
    SLOP_LANE_COUNT,
    ClaimLedger,
    HostCircuitBreaker,
    LaneDiedError,
    LanePool,
    PageClaim,
    PoolExhaustedError,
    SlopBudgetReached,
    SlopPersistenceError,
    safe_lane_cause,
)

if TYPE_CHECKING:
    from markettwin_execution_orchestrator.workflow.run_executor import (
        MarketTwinRunRequest,
    )

AUDIT_OBJECTIVE = UI_AUDIT_OBJECTIVE

# Per-viewport traversal budget for one page (pace): a page whose
# disclosure traversal cannot finish inside this budget is bounded, and
# its unattempted paths are reported as not inspected instead of letting
# a single page consume the run (MT-000150).
TRAVERSAL_BUDGET_SECONDS = 180

# Browser teardown bound (F5): closing a Room whose browser died with
# the host (sleep/crash) can await a dead driver forever. The close is
# best-effort; the run's terminal bookkeeping in the same finally is
# not, so the close gets a hard bound (MT-000151).
TEARDOWN_TIMEOUT_SECONDS = 30

# Speed S0 (doc 18 sections 8.4/12): slop.state.progress events are
# flushed in batches — one commit per PROGRESS_FLUSH_EVENTS events or
# PROGRESS_FLUSH_SECONDS seconds — instead of one commit per path.
# Explicit flush points ahead of checkpoints and results keep the
# persisted event order identical for resume.
PROGRESS_FLUSH_EVENTS = 10
PROGRESS_FLUSH_SECONDS = 2

# Speed S1 (doc 18 sections 8/12): the crawl loop is driven by a lane
# pool (slop/pool.py). LANE_COUNT is the module seam for the value in
# force — the pool's SLOP_LANE_COUNT by default — and the value
# actually used is recorded in every slop_checkpoint snapshot.
# lane_count == 1 is the degenerate shape (section 8.6): one lane on
# the Room session itself, checkpoints applied synchronously at page
# end exactly as in S0, per-page event flushing as today.
LANE_COUNT = SLOP_LANE_COUNT
MAX_SITEMAP_DOCUMENTS = 20
SITEMAP_DISCOVERY_SECONDS = 30
NON_PAGE_SUFFIXES = (".xml", ".json", ".rss", ".atom", ".pdf", ".xml.gz")
DESKTOP_TARGET_SECONDS = 600
DESKTOP_FINALIZATION_RESERVE_SECONDS = 45
DESKTOP_BUDGET_STOP_REASON = "The desktop scan reached its time budget before all work finished."


class SlopFinalizationError(RuntimeError):
    """Desktop audit collection or publication can be retried."""

    def __init__(self, stage: str) -> None:
        super().__init__(stage)
        self.stage = stage


class _DesktopScanBudget:
    def __init__(self, cutoff_at: float) -> None:
        self._loop = asyncio.get_running_loop()
        self._deadline = self._loop.time() + cutoff_at - time.time()
        self._operations: set[asyncio.Timeout] = set()
        self._human_started: float | None = None
        self.human_wait_seconds = 0.0

    def reached(self) -> bool:
        return self._loop.time() >= self._deadline

    async def wait(self, operation):
        if self.reached() and self._human_started is None:
            operation.close()
            raise SlopBudgetReached
        try:
            async with asyncio.timeout_at(
                None if self._human_started is not None else self._deadline,
            ) as timeout:
                self._operations.add(timeout)
                try:
                    return await operation
                finally:
                    self._operations.discard(timeout)
        except TimeoutError as error:
            if timeout.expired():
                raise SlopBudgetReached from error
            raise

    @contextmanager
    def human_wait(self):
        started = self._loop.time()
        self._human_started = started
        for timeout in self._operations:
            if not timeout.expired():
                timeout.reschedule(None)
        try:
            yield
        finally:
            self.human_wait_seconds += self._loop.time() - started
            self._human_started = None
            for timeout in self._operations:
                if not timeout.expired():
                    timeout.reschedule(self._deadline)


def _is_unassessed(state: dict) -> bool:
    return any(signal.get("rule_id") == "UI_STATE_UNASSESSED"
               for signal in state["page_signals"])


async def _publish_states(events, *, run_id, journey_id, execution_id, states):
    for state in states:
        await events.create(
            test_run_id=run_id, event_type="slop.state.result",
            journey_id=journey_id, execution_id=execution_id,
            payload={
                "url": state["url"], "elements": state["elements"],
                "page_signals": state["page_signals"], "js_errors": state["js_errors"],
                **{key: state.get(key) for key in (
                    "title", "viewport", "screenshot_artifact_id",
                    "measurement_evidence", "interaction_path", "catalogue_version",
                    "tier_context",
                )},
                **{key: state[key] for key in (
                    "lane_id", "policy_code", "failure_site",
                    "policy_error_class", "policy_error_detail",
                    "policy_claim_url", "policy_current_url",
                    "load_error_class", "load_error_detail",
                    "load_error_current_url",
                    "challenge_check_timed_out",
                ) if key in state},
            },
        )


async def _publish_desktop_audit(
    session, *, run_id, coverage, journey_id, execution_id, states=None,
):
    """Publish from the prepared collection and its committed page checkpoints."""
    try:
        events = RunEventRepository(session)
        run_state = run_state_repository.RunStateRepository(session)
        if not coverage["pages_recorded"] and not coverage["owner_stopped"]:
            if coverage.get("budget_exhausted"):
                code = "slop_budget_without_evidence"
            elif coverage["all_lanes_retired"]:
                code = "slop_lanes_exhausted"
            elif coverage.get("stop_reason"):
                code = "slop_stopped_without_evidence"
            else:
                code = "slop_no_evidence"
            await events.create(
                test_run_id=run_id, event_type="run.failed", journey_id=None, execution_id=None,
                payload=failure_details(code),
            )
            await run_state.mark_failed(test_run_id=run_id)
        else:
            if states is None:
                rows = await session.execute(select(RunEvent).where(
                    RunEvent.test_run_id == run_id,
                    RunEvent.event_type == "slop.page.checkpoint",
                ).order_by(RunEvent.id))
                states_by_key = {}
                for row in rows.scalars():
                    for state in row.payload["states"]:
                        states_by_key.setdefault(_state_content_key(state), state)
                states = list(states_by_key.values())
            if states and coverage["partial"]:
                states[-1]["page_signals"].append({
                    "rule_id": "AUDIT_PARTIAL_COVERAGE", "severity": "info",
                    "detail": f"Partial audit: {coverage['pages_pending']} discovered pages remain uninspected.",
                })
            for signal, first, second in compare_components(
                [state for state in states if not _is_unassessed(state)]
            ):
                signal["evidence_artifact_ids"] = [
                    state["screenshot_artifact_id"] for state in (first, second)
                    if state.get("screenshot_artifact_id")
                ]
            await _publish_states(
                events, run_id=run_id, journey_id=journey_id,
                execution_id=execution_id, states=states,
            )
            if coverage["owner_stopped"]:
                await run_state.mark_cancelled(test_run_id=run_id)
            else:
                await run_state.mark_completed(test_run_id=run_id)
        await session.commit()
    except Exception as error:
        raise SlopFinalizationError("publication") from error


def _is_page_candidate(url: str) -> bool:
    return not urlsplit(url).path.lower().endswith(NON_PAGE_SUFFIXES)


def _desktop_url_key(url: str) -> str:
    """Preserve ordered queries, path spelling and conventional hash routes."""
    parsed = urlsplit(url)
    origin = canonical_url(f"{parsed.scheme}://{parsed.netloc}/").rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    route = f"#{parsed.fragment}" if parsed.fragment.startswith(("/", "!/")) else ""
    return f"{origin}{parsed.path or '/'}{query}{route}"


class _PageContext:
    """One page's checkpoint bookkeeping, shared between the lane
    running the page and the absorber processing its checkpoints:
    whether a traversal checkpoint fired for this page (the pace
    rule), the latest review it produced, how its stop was applied,
    and the page's entry state — the dict stop processing appends
    audit signals to, exactly as the sequential loop appended to the
    page's measured entry state."""

    def __init__(self) -> None:
        self.entry_state: dict | None = None
        self.fired = False
        self.review: dict | None = None
        self.stop_honoured = False
        self.stop_overruled = False


@dataclass
class _PageRecord:
    """One claimed page's absorbed unit: the page's states (entry
    states first, then traversal states), the links its traversal
    discovered, and its load outcome for the host circuit-breaker.
    Absorption is the run's only commit point, and it is per-page
    atomic (doc 18 section 8.6)."""

    claim: PageClaim
    url: str
    states: list
    links: list
    entry_state: dict | None
    load_status: int | None = None
    load_error: str | None = None


def _state_content_key(state: dict) -> tuple:
    """Absorber defence-in-depth (doc 18 section 9.1): if a state is
    ever absorbed twice — a claim race the page-granular claim design
    says cannot happen — the first-absorbed record is kept and the
    duplicate counted in duplicate_absorptions, never silently
    absorbed. The key is content identity: url + viewport + the
    interaction path that reached the state + a hash of its measured
    elements."""
    digest = hashlib.sha256(
        json.dumps(state.get("elements") or [], sort_keys=True,
                   default=str).encode()).hexdigest()
    return (state.get("url"), state.get("viewport"),
            state.get("interaction_path"), digest)


def _load_status_of(error: BrowserActionError) -> int | None:
    """The HTTP status a page-load failure carried, when the error
    surfaces one (attribute or reason code); otherwise None. Only an
    explicit 429/503 feeds the host circuit-breaker (doc 18 section
    10.4) — an unknown load outcome never trips it."""
    status = getattr(error, "status", None)
    if isinstance(status, int):
        return status
    code = str(getattr(error, "reason_code", "") or "")
    for candidate in (429, 503):
        if str(candidate) in code:
            return candidate
    return None


def _failure_fields(kind, error, controller, handle, *, claim_url=None):
    """The bounded diagnostics an absorbed failure state records
    (Fix A): the exception's class name, its message truncated to
    300 characters, and the lane page's current URL — read directly
    off the session, never through an agent action, so a wedged
    page still names where it rests. The current-URL read is
    defensive: any failure records "". These named fields are the
    whole of what may carry exception text into a run record —
    never a traceback, headers or page content."""
    try:
        session = controller._get_session(  # pyright: ignore[reportPrivateUsage]
            session_id=handle.session_id)
        current_url = str(session.page.url)
    except Exception:
        current_url = ""
    detail = str(error)[:300]
    if kind == "policy":
        return {"policy_error_class": type(error).__name__,
                "policy_error_detail": detail,
                "policy_claim_url": claim_url,
                "policy_current_url": current_url}
    return {"load_error_class": type(error).__name__,
            "load_error_detail": detail,
            "load_error_current_url": current_url}


class _SlopAbsorber:
    """Single writer of slop run state (doc 18 section 8.4).

    Owns the claim ledger (queue/visited), the accumulated states,
    control results, checkpoint accounting, the slop_checkpoint
    snapshot writes, and run-event emission. Lanes hand it records;
    they never touch the DB. Every method that touches the run's DB
    session runs under one lock, so the run keeps today's
    one-session-per-execution shape. The model-call budget stays the
    single DB-mediated ledger behind the ask door: the reservation
    in markettwin_database.model_budget takes a per-run PostgreSQL
    advisory lock, so concurrent lanes cannot overrun it — there is
    no in-memory counter in that path to move (section 8.5 duty,
    verified at build time).
    """

    def __init__(self, *, request, session, events, run, journey_id,
                 execution_id, controller, lane_count, synchronous, desktop_scan=False, budget=None):
        self.request = request
        self.session = session
        self.events = events
        self.run = run
        self.journey_id = journey_id
        self.execution_id = execution_id
        self.controller = controller
        self.lane_count = lane_count
        self.synchronous = synchronous
        self.desktop_scan = desktop_scan
        self.budget = budget
        self.discovery_running = False
        self.discovery_finished = False
        self.discovery_sources: dict[str, str] = {}
        self.reviewed_layouts: set[tuple] = set()
        self.phase_samples: dict[str, dict[str, int | float]] = {}
        self.snapshot_writes = 0
        self.snapshot_bytes: list[int] = []
        self.url_key = _desktop_url_key if desktop_scan else canonical_url
        self.ledger = ClaimLedger(canonical=self.url_key, rotate_routes=desktop_scan)
        self.states: list[dict] = []
        self.control_results: dict = {}
        self.duplicate_absorptions = 0
        self._absorbed_state_keys: set = set()
        self._absorbed_claims: set = set()
        self._lock = asyncio.Lock()
        self._review_lock = asyncio.Lock()
        self._review_tasks: set[asyncio.Task] = set()
        self._review_error: BaseException | None = None
        self._review_in_flight = False
        self._progress_buffer: list[dict] = []
        self._progress_flush_clock = time.monotonic()
        # Stagnation-gate history, keyed GLOBALLY (doc 18 section
        # 8.5): under lanes the sequential loop's per-(url, viewport)
        # keying would fragment the signal into noise. This keying
        # change is deliberate and pinned by T-P3.
        self._gate_history = {"productive_total": None, "pending": None,
                              "unproductive": 0}
        self._paths_since_review = 0
        self._delta_since_review = {"checked": 0, "attempted": 0,
                                    "productive": 0}
        self._pending_by_traversal: dict = {}
        self._links_discovered_total = 0
        self.excluded_documents: dict[str, str] = {}
        self.sitemap_failures = 0
        self.sitemaps_pending = 0
        self.review_captures: set[str] = set()
        self.stop_requested = False
        self.owner_stopped = False
        self.stop_reason: str | None = None
        self.seeding_stop_reason: str | None = None
        self.seeding_stop_source: str | None = None
        self._seeding_stop_pending = False
        self._consumed: dict = {}
        self.breaker = HostCircuitBreaker()
        self.progress_hook = None
        self._first_absorb_done = False
        self._pages_since_lead_review = 0

    # -- queue growth (section 8.4: absorb_links semantics unchanged,
    #    one caller now — the absorber, serially) --
    @contextmanager
    def time_phase(self, name: str):
        if not self.desktop_scan:
            yield
            return
        started = time.monotonic()
        try:
            yield
        finally:
            milliseconds = (time.monotonic() - started) * 1000
            sample = self.phase_samples.setdefault(name, {"count": 0, "total_ms": 0, "max_ms": 0})
            sample["count"] += 1
            sample["total_ms"] += milliseconds
            sample["max_ms"] = max(sample["max_ms"], milliseconds)

    # Only the absorber grows the queue.
    def absorb_links(self, destinations, *, source=None) -> None:
        for destination in destinations:
            try:
                validate_target_url(destination, self.request.allowed_origins,
                                    self.request.network_policy)
            except BrowserPolicyError:
                continue
            if not _is_page_candidate(destination):
                self.excluded_documents[destination] = "non_page_url"
                continue
            if self.ledger.enqueue(destination):
                self._links_discovered_total += 1
                if self.desktop_scan and source:
                    self.discovery_sources[self.url_key(destination)] = source

    def note_seeded_queue(self) -> None:
        self._links_discovered_total = len(self.ledger.pending_urls)

    # -- JS record attribution: records are attributed by the URL
    #    captured ON the record, never by harvest order (a slow timer
    #    from page A can fire while page B is being measured, and it
    #    still belongs to A). Consumption is tracked per browser
    #    session: a lane harvests only its own context's records; in
    #    the degenerate shape the lane session IS the Room session,
    #    so the crawl and the post-crawl revisit pass share one
    #    consumption counter exactly as the sequential loop did. --
    async def fresh_records_for(self, *, session_id, url) -> list[dict]:
        records = await self.controller.harvest_js_records(
            session_id=session_id,
        )
        key = canonical_url(url)
        mine = [
            r for r in records if canonical_url(r.url) == key
        ]
        consumed = self._consumed.setdefault(session_id, {})
        start = consumed.get(key, 0)
        consumed[key] = len(mine)
        return [
            {"kind": r.kind, "message": r.message, "stack": r.stack}
            for r in mine[start:]
        ]

    # -- snapshot (section 8.6: additive lane fields; on resume,
    #    in-flight pages are simply pending again) --
    def _write_snapshot(self) -> None:
        in_flight = [{"url": claim.url, "claimed_by": claim.claimed_by,
                      "attempt": claim.attempt, "claim_seq": claim.claim_seq}
                     for claim in self.ledger.in_flight_claims]
        self.run.configuration_snapshot = {
            **self.run.configuration_snapshot,
            "slop_checkpoint": {
                "visited": sorted(self.ledger.visited_keys),
                "pending": list(self.ledger.pending_urls),
                "active_url": in_flight[0]["url"] if in_flight else None,
                "lane_count": self.lane_count,
                "in_flight": in_flight,
                "excluded_documents": dict(self.excluded_documents),
                "sitemap_failures": self.sitemap_failures,
                "sitemaps_pending": self.sitemaps_pending,
                **({"discovery_finished": self.discovery_finished,
                    "discovery_sources": dict(self.discovery_sources)} if self.desktop_scan else {}),
                **({"human_wait_seconds": self.budget.human_wait_seconds} if self.budget else {}),
            },
        }

        if self.desktop_scan:
            self.snapshot_writes += 1
            if self.snapshot_writes == 1 or self.snapshot_writes % 64 == 0:
                checkpoint = self.run.configuration_snapshot["slop_checkpoint"]
                self.snapshot_bytes.append(len(json.dumps(checkpoint).encode("utf-8")))

    def register_restored(self, states, control_results) -> None:
        self.states.extend(states)
        for state in states:
            self._absorbed_state_keys.add(_state_content_key(state))
        self.control_results.update(control_results)

    @asynccontextmanager
    async def _write_lock(self, operation: str, lane_id: int | None = None):
        with self.time_phase("database_lock_wait"):
            await self._lock.acquire()
        try:
            warning = asyncio.get_running_loop().call_later(
                30, logging.getLogger(__name__).warning,
                "UI audit %s progress lock held for at least 30s: operation=%s lane=%s",
                self.request.run_id, operation, lane_id,
            )
            try:
                yield
            except Exception as error:
                if not self.desktop_scan:
                    raise
                raise SlopPersistenceError(operation) from error
            finally:
                warning.cancel()
        finally:
            self._lock.release()

    # -- claims (the pool's claim source) --
    async def claim_next(self, lane_id):
        async with self._write_lock("claim next page", lane_id):
            if not self.stop_requested:
                await self._poll_owner_stop()
            if self.should_stop():
                return None
            claim = self.ledger.claim_next(lane_id)
            if claim is not None:
                self._write_snapshot()
            return claim

    async def _poll_owner_stop(self) -> None:
        """Owner stop (the Stop run button): ctl records the request
        in the run's configuration snapshot. Unlike a Lead stop, an
        owner stop is never overruled by the queue guard — the crawl
        ends at the lanes' next page boundary and the run closes
        cancelled, with the pending pages named by the partial
        accounting."""
        fresh = await self.session.get(
            TestRun, self.request.run_id, populate_existing=True)
        if fresh is None:
            return
        flag = (fresh.configuration_snapshot or {}).get("owner_stop")
        if not isinstance(flag, dict):
            return
        self.owner_stopped = True
        self.stop_requested = True
        self.stop_reason = "stopped by owner"
        await self.events.create(
            test_run_id=self.request.run_id, event_type="run.owner_stop",
            journey_id=self.journey_id, execution_id=self.execution_id,
            payload={"requested_at": flag.get("requested_at")})
        await self.session.commit()

    async def page_started(self, claim, *, watched_browser=None) -> None:
        if watched_browser is None:
            watched_browser = claim.claimed_by == 0
        async with self._write_lock("save page start", claim.claimed_by):
            await self.events.create(
                test_run_id=self.request.run_id, event_type="slop.page.started",
                journey_id=self.journey_id, execution_id=self.execution_id,
                payload={"url": claim.url,
                         "pages_pending": len(self.ledger.pending_urls),
                         "lane_id": claim.claimed_by,
                         "watched_browser": watched_browser,
                         "claim_seq": claim.claim_seq,
                         "attempt": claim.attempt})
            await self.session.commit()

    async def complete_claim(self, claim) -> None:
        async with self._write_lock("complete page claim", claim.claimed_by):
            if self.ledger.finish(claim):
                self._write_snapshot()
                await self.session.commit()

    async def release_claim(self, claim) -> None:
        async with self._write_lock("release page claim", claim.claimed_by):
            self.ledger.release(claim)
            self._write_snapshot()
            await self.session.commit()

    def work_remaining(self) -> bool:
        return self.discovery_running or self.ledger.work_remaining()

    def should_stop(self) -> bool:
        return self.stop_requested or (self.budget is not None and self.budget.reached())

    async def crawl_operation(self, operation):
        if self.budget is None:
            return await operation
        return await self.budget.wait(operation)

    # -- progress: lanes hand records here; the absorber flushes in
    #    batches (section 8.4) so the run's event stream keeps a
    #    <= PROGRESS_FLUSH_SECONDS cadence while any lane works --
    async def absorb_progress(self, lane_id, progress) -> None:
        progress = {**progress, "lane_id": lane_id}
        async with self._write_lock("save interaction progress", lane_id):
            self.control_results[(progress["url"], progress["viewport"],
                                  progress["path"])] = progress
            self._progress_buffer.append(progress)
            self._paths_since_review += 1
            self._pending_by_traversal[(progress["url"],
                                        progress["viewport"])] = \
                progress.get("pending_paths", 0)
            if (len(self._progress_buffer) >= PROGRESS_FLUSH_EVENTS
                    or time.monotonic() - self._progress_flush_clock
                    >= PROGRESS_FLUSH_SECONDS):
                await self._flush_progress_locked()
        if self.progress_hook is not None:
            self.progress_hook(lane_id)

    async def _flush_progress_locked(self) -> None:
        if self._progress_buffer:
            for payload in self._progress_buffer:
                await self.events.create(
                    test_run_id=self.request.run_id,
                    event_type="slop.state.progress",
                    journey_id=self.journey_id,
                    execution_id=self.execution_id,
                    payload=payload)
            self._progress_buffer.clear()
            await self.session.commit()
        self._progress_flush_clock = time.monotonic()

    async def flush_progress(self) -> None:
        async with self._write_lock("flush interaction progress"):
            await self._flush_progress_locked()

    async def save_evidence(self, state) -> None:
        await save_state_evidence(state, session=self.session,
                                  execution_id=self.execution_id,
                                  write_lock=self._write_lock("save screenshot metadata"))

    async def review_desktop_page(self, claim, probe, state, *, session_id) -> None:
        entry = self.url_key(claim.url) == self.url_key(self.request.start_url)
        section = urlsplit(claim.url).path.strip("/").partition("/")[0]
        layout = (section, tuple(item["tag"] for item in probe.get("sections", [])))
        review = entry or (len(self.reviewed_layouts) < 24 and layout not in self.reviewed_layouts)
        if review:
            self.reviewed_layouts.add(layout)
        measured_issue = (
            any(signal.get("severity") == "severe" for signal in state["page_signals"])
            or any(element.get("verdict") == "slop" for element in state["elements"])
        )
        if not review and not measured_issue:
            return
        path = None
        try:
            with self.time_phase("screenshot_capture"):
                path = await self.crawl_operation(self.capture_for_review(session_id=session_id))
            state["screenshot_path"] = path
            findings = []
            if review:
                with self.time_phase("visual_review"):
                    findings = await self.crawl_operation(review_screenshots(
                        [state], context=getattr(self.request, "app_plan", None)))
            with self.time_phase("evidence_retention"):
                await retain_finding_evidence([state], findings, self.save_evidence)
            state["page_signals"].extend(findings)
        except SlopBudgetReached:
            if review:
                state["page_signals"].append({
                    "rule_id": "UI_VISUAL_REVIEW_UNFINISHED", "severity": "info",
                    "detail": "The scan cutoff ended visual review. Desktop measurements were recorded.",
                })
            else:
                state["page_signals"].append({
                    "rule_id": "UI_EVIDENCE_UNFINISHED", "severity": "info",
                    "detail": "The scan cutoff ended screenshot capture. Desktop measurements were recorded.",
                })
        finally:
            state.pop("screenshot_path", None)
            if path:
                try:
                    await asyncio.to_thread(Path(path).unlink, missing_ok=True)
                    self.review_captures.discard(path)
                except OSError:
                    logging.getLogger(__name__).warning("Could not remove temporary desktop capture")

    async def publish_entry_assessment(self, claim, states) -> None:
        if self.url_key(claim.url) != self.url_key(self.request.start_url):
            return
        async with self._write_lock("save submitted page assessment", claim.claimed_by):
            if self.run.configuration_snapshot.get("slop_entry_assessment"):
                return
            findings = []
            for state in states:
                viewport = state["viewport"]
                for signal in state["page_signals"]:
                    if signal["severity"] in {"severe", "minor", "review"}:
                        findings.append({
                            "detail": signal["detail"], "severity": signal["severity"],
                            "viewports": signal.get("viewports") or (
                                [] if signal["severity"] == "review" else [viewport]),
                            "artifact_ids": signal.get("evidence_artifact_ids") or (
                                [state["screenshot_artifact_id"]]
                                if signal["severity"] != "review"
                                and state.get("screenshot_artifact_id") else []),
                        })
                for element in state["elements"]:
                    if element["verdict"] in {"slop", "slop_minor"}:
                        for rule in element["rules_fired"]:
                            findings.append({
                                "detail": rule.get("detail") or rule["rule_id"].removeprefix("SLOP_").replace("_", " ").capitalize(),
                                "element": element["label"], "viewports": [viewport],
                                "severity": "severe" if element["verdict"] == "slop" else "minor",
                                "artifact_ids": [state["screenshot_artifact_id"]]
                                if state.get("screenshot_artifact_id") else [],
                            })
            rank = {"severe": 0, "minor": 1, "review": 2}
            findings.sort(key=lambda finding: rank[finding["severity"]])
            unique = {}
            for finding in findings:
                key = (finding["detail"], finding.get("element"))
                existing = unique.setdefault(key, finding)
                for field in ("viewports", "artifact_ids"):
                    existing[field] = list(dict.fromkeys(existing[field] + finding[field]))
            self.run.configuration_snapshot = {
                **self.run.configuration_snapshot,
                "slop_entry_assessment": {
                    "url": states[0]["url"],
                    "published_at": time.time(),
                    "viewports": [state["viewport"] for state in states],
                    "elements_judged": sum(
                        element["verdict"] != "cant_tell"
                        for state in states for element in state["elements"]),
                    "findings": list(unique.values())[:5],
                    "findings_count": len(unique),
                },
            }
            await self.session.commit()

    async def capture_for_review(self, *, session_id) -> str:
        path = await self.controller.capture_evidence_screenshot(session_id=session_id)
        if path:
            self.review_captures.add(path)
        return path

    async def emit_pool_event(self, event_type, payload) -> None:
        async with self._write_lock("save pool event"):
            await self.events.create(
                test_run_id=self.request.run_id, event_type=event_type,
                journey_id=self.journey_id, execution_id=self.execution_id,
                payload=payload)
            await self.session.commit()


    # -- checkpoints (section 8.5): notebook counters are global,
    #    computed here from absorbed results; at most one checkpoint
    #    is in flight; a stop takes effect at each lane's next page
    #    boundary, and the lead.checkpoint payload records the
    #    application point (pages claimed at decision vs at
    #    application). Veto + stagnation gate + queue guard all run
    #    here, on global evidence, in the sequential loop's order. --
    def _globalise(self, evidence) -> dict:
        self._delta_since_review["checked"] += evidence.get("checked_delta", 0)
        self._delta_since_review["attempted"] += evidence.get("attempted_delta", 0)
        self._delta_since_review["productive"] += evidence.get("productive_delta", 0)
        self._pending_by_traversal[(evidence.get("url"),
                                    evidence.get("viewport"))] = \
            evidence.get("pending_paths", 0)
        return {**evidence,
                "checked_delta": self._delta_since_review["checked"],
                "attempted_delta": self._delta_since_review["attempted"],
                "productive_delta": self._delta_since_review["productive"],
                "checked_items": self._delta_since_review["checked"],
                "states_measured": len(self.states)
                + evidence.get("states_measured", 0),
                "routes_discovered": len(self.ledger.visited_keys)
                + len(self.ledger.pending_urls),
                "pending_paths": len(self.ledger.pending_urls)
                + sum(self._pending_by_traversal.values())}

    def _reset_review_counters(self) -> None:
        self._paths_since_review = 0
        self._delta_since_review = {"checked": 0, "attempted": 0,
                                    "productive": 0}

    async def _review_phase(self, evidence, *, page_ctx):
        await self.flush_progress()
        evidence = {**evidence,
                    "pages_visited": len(self.ledger.visited_keys),
                    "pages_pending": len(self.ledger.pending_urls),
                    "pages_discovered": len(self.ledger.visited_keys)
                    + len(self.ledger.pending_urls)}
        claims_at_decision = self.ledger.claims_issued
        review = None
        if "checked_items" in evidence:
            # Notebook accounting (Issue 2): a traversal checkpoint is
            # unproductive when its states measured + routes discovered
            # total has not moved, checks were attempted, and the
            # pending paths are not draining (new paths keep being
            # generated). Two consecutive unproductive checkpoints flag
            # stagnation for the Lead; a third stops the traversal
            # outright, with no further model call. The history is the
            # absorber's GLOBAL history (section 8.5 keying change).
            history = self._gate_history
            productive_total = evidence["states_measured"] \
                + evidence["routes_discovered"]
            if (history["productive_total"] is not None
                    and productive_total == history["productive_total"]
                    and evidence["checked_delta"] > 0
                    and evidence["pending_paths"] >= history["pending"]):
                history["unproductive"] += 1
            else:
                history["unproductive"] = 0
            history["productive_total"] = productive_total
            history["pending"] = evidence["pending_paths"]
            if history["unproductive"] >= 3:
                review = {"decision": "stop",
                          "reason": "Stagnation: repeated checkpoints produced no new states or routes and the queue was not draining, and no effective change followed; stopped with partial coverage.",
                          "source": "stagnation_gate"}
            elif history["unproductive"] >= 2:
                evidence = {**evidence, "stagnation": True,
                            "stagnation_detail": "No new states measured and no new routes discovered across repeated checkpoints while checks were attempted and pending paths were not draining."}
        if review is None:
            try:
                review = await self.crawl_operation(review_checkpoint(
                    objective=self.request.study_brief, evidence=evidence))
            except SlopBudgetReached:
                review = {"decision": "continue", "source": "budget",
                          "reason": "Lead review ended at the desktop scan cutoff."}
        if page_ctx is not None and "checked_items" in evidence:
            page_ctx.fired = True
            page_ctx.review = review
        return review, evidence, claims_at_decision

    def _apply_stop(self, review, *, page_ctx, kind) -> bool:
        """Stop processing shared by every checkpoint kind. Returns
        True when the stop stands. The queue guard (spec 10) reads
        the GLOBAL queue: a Lead stop does not end the crawl while
        many discovered pages remain uninspected; harness-sourced
        stops (stagnation gate, fallback) always end it."""
        if kind == "discovery":
            return False
        if review.get("source") == "lead" \
                and len(self.ledger.pending_urls) > 10:
            if page_ctx is not None:
                page_ctx.stop_overruled = True
                if page_ctx.entry_state is not None:
                    page_ctx.entry_state["page_signals"].append({
                        "rule_id": "AUDIT_LEAD_STOP_OVERRULED",
                        "severity": "info",
                        "detail": f"Lead stop not applied: {len(self.ledger.pending_urls)} discovered pages remain uninspected. Lead reason: {review['reason']}"})
            return False
        if self.owner_stopped:
            return False
        self.stop_requested = True
        self.stop_reason = review["reason"]
        if page_ctx is not None:
            page_ctx.stop_honoured = True
            if kind == "page_end" and page_ctx.entry_state is not None:
                page_ctx.entry_state["page_signals"].append({
                    "rule_id": "AUDIT_LEAD_STOP", "severity": "info",
                    "detail": review["reason"]})
        return True

    async def _process_checkpoint(self, evidence, *, page_ctx, kind):
        async with self._review_lock:
            review, evidence, claims_at_decision = await self._review_phase(
                evidence, page_ctx=page_ctx)
            applied = False
            if review["decision"] == "stop":
                applied = self._apply_stop(review, page_ctx=page_ctx,
                                           kind=kind)
            async with self._write_lock("save lead decision"):
                await self.events.create(
                    test_run_id=self.request.run_id,
                    event_type="lead.checkpoint",
                    journey_id=self.journey_id,
                    execution_id=self.execution_id,
                    payload={**review, "progress": evidence,
                             "application": {
                                 "pages_claimed_at_decision":
                                     claims_at_decision,
                                 "pages_claimed_at_application":
                                     self.ledger.claims_issued,
                                 "stop_applied": applied}})
                await self.session.commit()
            return review

    async def request_checkpoint(self, evidence, *, page_ctx):
        """The traversal checkpoint callback lanes pass to
        inspect_interactions. Synchronous shape (lane_count == 1):
        the review is processed inline and its real decision returns,
        exactly as in S0. Pool shape: the request is accumulated into
        the global counters and a review fires only when the global
        absorbed-path count reaches the cadence with no checkpoint
        already in flight; the calling traversal is never blocked and
        the stop, when it comes, applies at page boundaries."""
        if self.synchronous:
            globalised = self._globalise(evidence)
            self._reset_review_counters()
            return await self._process_checkpoint(
                globalised, page_ctx=page_ctx, kind="traversal")
        globalised = self._globalise(evidence)
        if self._paths_since_review >= 15 and not self._review_in_flight:
            self._review_in_flight = True
            self._reset_review_counters()
            page_ctx.fired = True
            task = asyncio.create_task(
                self._async_checkpoint(globalised, page_ctx))
            self._review_tasks.add(task)
            task.add_done_callback(self._review_finished)
        return {"decision": "continue",
                "reason": "Checkpoint review requested.",
                "source": "absorber"}

    async def _async_checkpoint(self, evidence, page_ctx, kind="traversal"):
        try:
            await self._process_checkpoint(
                evidence, page_ctx=page_ctx, kind=kind)
        finally:
            self._review_in_flight = False

    async def checkpoint_sync(self, evidence):
        """Sequential-phase checkpoints (sitemap discovery): always
        processed inline, whatever the lane shape — the queue must
        exist before claims, so discovery stays pre-pool."""
        return await self._process_checkpoint(
            evidence, page_ctx=None, kind="discovery")

    async def page_end_review(self, *, page_ctx):
        """M4, same treatment as the traversal checkpoint: skipped
        when the page's traversal already fired one (the pace rule,
        decided by the caller), synchronous in the degenerate shape,
        asynchronous under the pool."""
        if self.stop_requested:
            return None
        if not self.synchronous:
            self._pages_since_lead_review += 1
            if self._review_in_flight:
                return None
            if (self.ledger.pending_urls and len(self._absorbed_claims) > 1
                    and self._pages_since_lead_review < self.lane_count):
                return None
            self._pages_since_lead_review = 0
        evidence = {
            "pages_inspected": len(self.ledger.visited_keys),
            "states_inspected": len(self.states),
            "pages_pending": len(self.ledger.pending_urls),
            "routes_discovered": len(self.ledger.visited_keys)
            + len(self.ledger.pending_urls),
            "visited_urls": sorted(self.ledger.visited_keys),
            "pending_urls": list(self.ledger.pending_urls),
            "recent_pages": [{"url": page["url"],
                              "signals": page["page_signals"]}
                             for page in self.states[-5:]],
        }
        if self.synchronous:
            return await self._process_checkpoint(
                evidence, page_ctx=page_ctx, kind="page_end")
        self._review_in_flight = True
        task = asyncio.create_task(self._async_checkpoint(evidence, page_ctx, "page_end"))
        self._review_tasks.add(task)
        task.add_done_callback(self._review_finished)
        return None

    # -- page absorption: the run's only commit point --
    def _absorb_states_locked(self, states) -> None:
        for state in states:
            key = _state_content_key(state)
            if key in self._absorbed_state_keys:
                self.duplicate_absorptions += 1
                continue
            self._absorbed_state_keys.add(key)
            self.states.append(state)

    async def absorb_inspected(self, record) -> None:
        async with self._write_lock("save page inspection", record.claim.claimed_by):
            self.absorb_links(record.links, source=record.url)
            self._absorb_states_locked(record.states)
            self._absorbed_claims.add(record.claim.claim_seq)
            self._pending_by_traversal.pop((record.url, "mobile320"), None)
            self._pending_by_traversal.pop((record.url, "desktop1280"), None)
            if record.entry_state is not None:
                record.entry_state["finished_at"] = time.time()
            await self.events.create(
                test_run_id=self.request.run_id,
                event_type="slop.page.inspected",
                journey_id=self.journey_id, execution_id=self.execution_id,
                payload={"url": record.url,
                         "pages_inspected": len(self.ledger.visited_keys),
                         "pages_pending": len(self.ledger.pending_urls),
                         **({"final_url": (record.entry_state or {}).get("url"),
                             "outcome": ("excluded" if record.entry_state is None else
                                         "unverified" if any(
                                             signal.get("rule_id") == "UI_STATE_UNASSESSED"
                                             for signal in record.entry_state["page_signals"]
                                         ) else "measured")} if self.desktop_scan else
                            {"pending_urls": list(self.ledger.pending_urls),
                             "visited_urls": sorted(self.ledger.visited_keys)}),
                         "lane_id": record.claim.claimed_by,
                         "claim_seq": record.claim.claim_seq})
            if self.desktop_scan:
                await self.events.create(
                    test_run_id=self.request.run_id,
                    event_type="slop.page.checkpoint",
                    journey_id=self.journey_id, execution_id=self.execution_id,
                    payload={"states": record.states})
                self.ledger.finish(record.claim)
                self._write_snapshot()
            with self.time_phase("inspection_commit"):
                await self.session.commit()
        self.breaker.note_outcome(record.load_status)
        if not self._first_absorb_done:
            self._first_absorb_done = True
            self._apply_seeding_stop(record.entry_state)
        if self.progress_hook is not None:
            self.progress_hook(record.claim.claimed_by)

    def _apply_seeding_stop(self, entry_state) -> None:
        """A Lead stop during up-front sitemap discovery is honoured
        here, after the first page is inspected — the same point
        where discovery used to happen (sequential semantics)."""
        if not self._seeding_stop_pending:
            return
        self._seeding_stop_pending = False
        if self.seeding_stop_source == "lead" \
                and len(self.ledger.pending_urls) > 10:
            if entry_state is not None:
                entry_state["page_signals"].append({
                    "rule_id": "AUDIT_LEAD_STOP_OVERRULED",
                    "severity": "info",
                    "detail": f"Lead stop not applied: {len(self.ledger.pending_urls)} discovered pages remain uninspected. Lead reason: {self.seeding_stop_reason}"})
            self.seeding_stop_reason = None
            self.seeding_stop_source = None
        else:
            self.stop_requested = True
            self.stop_reason = self.seeding_stop_reason
            if entry_state is not None:
                entry_state["page_signals"].append({
                    "rule_id": "AUDIT_LEAD_STOP", "severity": "info",
                    "detail": self.seeding_stop_reason})

    async def absorb_page_checkpoint(self, record) -> None:
        async with self._write_lock("save page checkpoint", record.claim.claimed_by):
            # Phase 1b section 7: account this page's judged
            # elements against the map's harvested inventory, so
            # a barely-touched page cannot look fully reviewed.
            # Verdicts are never carried from the map into the
            # run — carried_verdicts is structurally 0.
            page_inventory = inventory_for_page(
                getattr(self.request, "app_map", None), record.url)
            if page_inventory is not None:
                judged_entries = []
                for judged_state in record.states:
                    for judged_element in judged_state.get("elements") or []:
                        component = judged_element.get("component")
                        if isinstance(component, dict):
                            judged_entries.append({
                                "role": component.get("role"),
                                "name": component.get("name"),
                                "state_key": judged_state.get("state_key"),
                                "verdict": judged_element.get("verdict"),
                            })
                accounting = account_for_page(
                    page_inventory, judged_entries)
                await self.events.create(
                    test_run_id=self.request.run_id,
                    event_type="slop.inventory.accounting",
                    journey_id=self.journey_id,
                    execution_id=self.execution_id,
                    payload={"url": record.url, **accounting,
                             "carried_verdicts": 0},
                )
            await self.events.create(
                test_run_id=self.request.run_id,
                event_type="slop.page.checkpoint",
                journey_id=self.journey_id, execution_id=self.execution_id,
                payload={"states": record.states})
            self.ledger.finish(record.claim)
            self._write_snapshot()
            await self.session.commit()

    async def absorb_load_error(self, record, *, page_ctx):
        async with self._write_lock("save page load failure", record.claim.claimed_by):
            self._absorb_states_locked(record.states)
            self._absorbed_claims.add(record.claim.claim_seq)
            if record.entry_state is not None:
                record.entry_state["finished_at"] = time.time()
            await self.events.create(
                test_run_id=self.request.run_id,
                event_type="slop.page.checkpoint",
                journey_id=self.journey_id, execution_id=self.execution_id,
                payload={"states": record.states})
            self.ledger.finish(record.claim)
            self._write_snapshot()
            await self.session.commit()
        self.breaker.note_outcome(record.load_status)
        evidence = {"url": record.url, "load_error": record.load_error,
                    "pages_pending": len(self.ledger.pending_urls),
                    "pages_inspected": len(self.ledger.visited_keys) - 1}
        if self.synchronous:
            return await self._process_checkpoint(
                evidence, page_ctx=page_ctx, kind="load_error")
        task = asyncio.create_task(self._process_checkpoint(
            evidence, page_ctx=page_ctx, kind="load_error"))
        self._review_tasks.add(task)
        task.add_done_callback(self._review_finished)
        return None

    async def absorb_attempted_failed(self, claim, *, site, lane_id, policy_code=None,
                                      diagnostics=None) -> None:
        """A dead lane's in-flight page (section 10.1): recorded
        attempted-failed with the failure site naming the lane and
        the death site. Exception detail reaches the record only
        through the caller's bounded diagnostic fields (Fix A:
        class name and a 300-character-truncated message) — never
        a traceback."""
        if self.desktop_scan:
            site = safe_lane_cause(site)
        async with self._write_lock("save lane failure", lane_id):
            if claim.claim_seq in self._absorbed_claims:
                self.ledger.finish(claim)
                return
            reason = f"{site}: {policy_code}" if policy_code else site
            state = {"url": claim.url, "elements": [], "js_errors": [],
                     "page_signals": [{
                         "rule_id": "UI_STATE_UNASSESSED",
                         "severity": "info",
                         "detail": f"Page could not be inspected ({reason})."}],
                     "lane_id": lane_id, "claim_seq": claim.claim_seq,
                     "claimed_at": claim.claimed_at,
                     "finished_at": time.time(),
                     "failure_site": f"lane {lane_id}: {site}"}
            if policy_code:
                state["policy_code"] = policy_code
            if diagnostics:
                state.update(diagnostics)
            self._absorb_states_locked([state])
            self._absorbed_claims.add(claim.claim_seq)
            await self.events.create(
                test_run_id=self.request.run_id,
                event_type="slop.page.checkpoint",
                journey_id=self.journey_id, execution_id=self.execution_id,
                payload={"states": [state]})
            self.ledger.finish(claim)
            self._write_snapshot()
            await self.session.commit()

    def _review_finished(self, task: asyncio.Task) -> None:
        self._review_tasks.discard(task)
        if not task.cancelled():
            error = task.exception()
            if error is not None and self._review_error is None:
                self._review_error = error

    async def aclose(self, *, wait: bool = False) -> None:
        """Settle pending checkpoint reviews. On a clean finish the
        executor waits for them: a late Lead stop still marks the
        run partial, and its lead.checkpoint event is part of the
        audit record. On the failure/cancellation path they are
        cancelled — their stop has no page boundary left to apply
        at, and teardown must never wedge on them (F5)."""
        if wait:
            if self._review_tasks:
                await asyncio.gather(*list(self._review_tasks),
                                     return_exceptions=True)
            if self._review_error is not None:
                raise self._review_error
            return
        for task in list(self._review_tasks):
            task.cancel()
        if self._review_tasks:
            await asyncio.gather(*list(self._review_tasks),
                                 return_exceptions=True)



class _RoomLaneSession:
    """The degenerate lane's session (section 8.6): the Room session
    itself. The pool must not close it — the executor's finally
    closes the Room exactly as today."""

    def __init__(self, handle):
        self.handle = handle

    async def close(self) -> None:
        return None


class _ControllerLaneSession:
    """A lane's worker session on the controller. Closed by the pool
    under its bounded-teardown discipline (section 8.2)."""

    def __init__(self, controller, handle, *, session_factory=None):
        self._controller = controller
        self.handle = handle
        self._session_factory = session_factory

    async def close(self) -> None:
        try:
            await self._controller.close_session(session_id=self.handle.session_id)
        finally:
            if self._session_factory is not None:
                async with self._session_factory() as session:
                    await ExecutionRepository(session).mark_browser_session_closed(
                        browser_session_id=self.handle.session_id,
                    )
                    await session.commit()


async def _inspect_page(*, absorber, controller, handle, claim, watched_browser=None) -> None:
    """Measure the desktop entry and inspect its interaction states on this lane."""
    request = absorber.request
    url = claim.url
    lane_id = claim.claimed_by
    page_ctx = _PageContext()
    await absorber.page_started(claim, watched_browser=watched_browser)
    if (
        getattr(request, "runtime_human_assistance", False)
        and absorber.url_key(url) != absorber.url_key(request.start_url)
        and is_account_entry_route(url)
    ):
        await absorber.absorb_inspected(_PageRecord(
            claim=claim, url=url, states=[], links=[], entry_state=None, load_status=None,
        ))
        return
    try:
        try:
            with absorber.time_phase("navigation"):
                await absorber.crawl_operation(controller.navigate(
                    session_id=handle.session_id, url=url, observe=False))
        except BrowserActionError as error:
            load_status = _load_status_of(error)
            reason_code = "rate_limited" if load_status in (429, 503) \
                else error.reason_code
            unassessed = {"url": url, "elements": [], "js_errors": [],
                "page_signals": [{"rule_id": "UI_STATE_UNASSESSED",
                    "severity": "info",
                    "detail": f"Page could not be loaded ({reason_code}); other pages remain eligible."}],
                "lane_id": lane_id, "claim_seq": claim.claim_seq,
                "claimed_at": claim.claimed_at,
                **_failure_fields("load", error, controller, handle)}
            page_ctx.entry_state = unassessed
            record = _PageRecord(
                claim=claim, url=url, states=[unassessed], links=[],
                entry_state=unassessed, load_status=load_status,
                load_error=error.reason_code)
            await absorber.absorb_load_error(record, page_ctx=page_ctx)
            return
        # Let the page settle: scripts that throw on a timer
        # just after load are part of the visit's evidence.
        with absorber.time_phase("settle"):
            await absorber.crawl_operation(controller.wait(
                session_id=handle.session_id, milliseconds=300, observe=False))
        with absorber.time_phase("dom_probe"):
            probe = await absorber.crawl_operation(controller.probe_page(session_id=handle.session_id))
        if content_type := non_html_type(probe):
            absorber.excluded_documents[url] = content_type
            await absorber.absorb_inspected(_PageRecord(
                claim=claim, url=url, states=[], links=[], entry_state=None, load_status=200,
            ))
            return
        viewport_height = probe.get("client_height", 0)
        if absorber.desktop_scan and any(
            not image.get("complete", True)
            and image.get("y", viewport_height) < viewport_height
            and image.get("y", 0) + image.get("height", 0) > 0
            for image in probe.get("images", [])
        ):
            with absorber.time_phase("image_settle"):
                await absorber.crawl_operation(controller.wait(
                    session_id=handle.session_id, milliseconds=250, observe=False))
                probe = await absorber.crawl_operation(
                    controller.probe_page(session_id=handle.session_id))
        observed_url = probe.get("url") or url
        new_records = await absorber.crawl_operation(absorber.fresh_records_for(
            session_id=handle.session_id, url=observed_url))
        with absorber.time_phase("measurement"):
            measured = measure_state(
                probe,
                brand_tokens=getattr(request, "brand_tokens", None),
                slop_classes_enabled=getattr(request, "slop_classes_enabled", None),
            )
            measured["js_errors"] = dedupe_js_errors(
                new_records, state_url=url,
            )
        measured["viewport"] = "desktop1280"
        measured["lane_id"] = lane_id
        measured["claim_seq"] = claim.claim_seq
        measured["claimed_at"] = claim.claimed_at
        page_ctx.entry_state = measured
        take_challenge_timeout = getattr(
            controller, "take_challenge_check_timeout", None)
        if take_challenge_timeout is not None and take_challenge_timeout(
                session_id=handle.session_id):
            measured["challenge_check_timed_out"] = True
        if absorber.desktop_scan:
            if not probe.get("words") and not probe.get("elements") and not probe.get("images"):
                measured["page_signals"].append({
                    "rule_id": "UI_STATE_UNASSESSED", "severity": "info",
                    "detail": "No measurable content rendered during this visit.",
                })
            try:
                discovered_links = await absorber.crawl_operation(
                    controller.page_links(session_id=handle.session_id))
            except SlopBudgetReached:
                discovered_links = []
                measured["page_signals"].append({
                    "rule_id": "UI_LINK_DISCOVERY_UNFINISHED", "severity": "info",
                    "detail": "The scan cutoff ended link discovery on this page.",
                })
            await absorber.review_desktop_page(claim, probe, measured, session_id=handle.session_id)
            await absorber.publish_entry_assessment(claim, [measured])
            await absorber.absorb_inspected(_PageRecord(
                claim=claim, url=url, states=[measured], links=discovered_links,
                entry_state=measured, load_status=200,
            ))
            return
        measured["screenshot_path"] = await absorber.capture_for_review(
            session_id=handle.session_id)
        page_states = [measured]
        findings = await review_screenshots(page_states, context=getattr(request, "app_plan", None))
        await retain_finding_evidence(page_states, findings, absorber.save_evidence)
        measured["page_signals"].extend(findings)
        await absorber.publish_entry_assessment(claim, page_states)
        discovered_links = await controller.page_links(
            session_id=handle.session_id)
        absorber.absorb_links(discovered_links)
        extra, traversal_links, skipped, traversal_stopped = await inspect_interactions(
            controller=controller, handle=handle, url=url,
            viewport=measured["viewport"],
            deadline=time.monotonic() + TRAVERSAL_BUDGET_SECONDS,
            page_ready=True,
            checkpoint=lambda evidence: absorber.request_checkpoint(
                evidence, page_ctx=page_ctx),
            on_progress=lambda progress: absorber.absorb_progress(
                lane_id, progress),
            on_state=absorber.save_evidence,
            capture=absorber.capture_for_review,
            known_fingerprints={view_fingerprint(probe)},
        )
        await absorber.flush_progress()
        for state in extra:
            state["lane_id"] = lane_id
            state["claim_seq"] = claim.claim_seq
            state["claimed_at"] = claim.claimed_at
        page_states.extend(extra)
        measured["page_signals"].extend(
            {"rule_id": "UI_STATE_UNASSESSED", "severity": "info",
             "detail": f"desktop1280: {entry['state']}: {entry['reason']}"}
            for entry in skipped)
        # Entry harvest excludes errors raised by interactions. Attribute the
        # remaining records to this page before its measured states are absorbed.
        interaction_records = await absorber.fresh_records_for(
            session_id=handle.session_id, url=url,
        )
        measured["js_errors"].extend(dedupe_js_errors(interaction_records, state_url=url))
        record = _PageRecord(
            claim=claim, url=url, states=page_states,
            links=traversal_links, entry_state=measured, load_status=200)
        await absorber.absorb_inspected(record)
        if traversal_stopped and not page_ctx.stop_overruled:
            # The traversal itself stopped (browser policy): the
            # crawl ends with this page — no page-end review and no
            # page checkpoint event, the sequential loop's shape.
            # The only traversal stop that continues is a Lead stop
            # the queue guard overruled.
            absorber.stop_requested = True
            absorber.stop_reason = "Traversal stopped (browser policy)."
            return
        if absorber.synchronous and absorber.stop_requested:
            # A stop landed on or before this page (its own traversal
            # checkpoint, or the seeding stop applied at absorption):
            # the crawl breaks here, before the page-end review and
            # the page checkpoint event — the sequential loop's exact
            # shape. In the pool shape an absorbed page always
            # finishes (below); the pool claims no further pages on a
            # stopped run.
            return
        # Pace: a page whose traversal already fired a Lead
        # checkpoint does not get a second, page-end review.
        if absorber.ledger.visited_keys and not page_ctx.fired:
            await absorber.page_end_review(page_ctx=page_ctx)
            if absorber.synchronous and page_ctx.stop_honoured:
                return
        await absorber.absorb_page_checkpoint(record)
    except asyncio.CancelledError:
        raise
    except (AuthenticationVerificationBlocked, HumanAssistanceSkipped):
        # A gated page must not generate content findings or an entry score.
        absorber.stop_requested = True
        absorber.stop_reason = "A required browser step was not verified."
        unassessed = {
            "url": url, "viewport": "desktop1280", "elements": [], "js_errors": [],
            "page_signals": [{
                "rule_id": "UI_STATE_UNASSESSED", "severity": "info",
                "detail": absorber.stop_reason,
            }],
            "lane_id": lane_id, "claim_seq": claim.claim_seq, "claimed_at": claim.claimed_at,
        }
        await absorber.absorb_inspected(_PageRecord(
            claim=claim, url=url, states=[unassessed], links=[],
            entry_state=unassessed, load_status=None,
        ))
    except (BrowserPolicyError, HumanControlActiveError) as error:
        if absorber.desktop_scan:
            policy_codes = (
                (HumanControlActiveError, "human_control_active"),
                (UnsafeDestinationAddressError, "unsafe_destination"),
                (HostResolutionError, "host_resolution"),
                (TargetUrlValidationError, "target_url"),
                (OffsiteJourneyStopped, "offsite_limit"),
                (SuspiciousEgressError, "suspicious_egress"),
                (BrowserActionBlockedError, "action_refused"),
            )
            code = next(
                (code for kind, code in policy_codes if isinstance(error, kind)), "policy_refused",
            )
            if isinstance(error, OffsiteJourneyStopped):
                absorber.stop_requested = True
                absorber.stop_reason = "A browsing policy stopped the journey."
            await absorber.absorb_attempted_failed(
                claim, site="browser_policy", lane_id=lane_id, policy_code=code,
                diagnostics=_failure_fields(
                    "policy", error, controller, handle, claim_url=claim.url),
            )
            return
        # Guardrail refusals keep the sequential semantics: the run
        # fails through the normal failure path in every shape.
        raise
    except (LaneDiedError, SlopBudgetReached, SlopPersistenceError):
        raise
    except Exception as error:
        if absorber.synchronous:
            raise
        # Failure isolation (section 10.1): one lane's death is not
        # the run's death. The site names the failure class only —
        # no raw exception text reaches run records.
        if isinstance(error, BrowserTimeoutError):
            cause = "browser_timeout"
        elif isinstance(error, BrowserActionError):
            cause = "browser_action"
        elif isinstance(error, (BrowserSessionNotFoundError, BrowserSessionStateError)):
            cause = "browser_session"
        else:
            cause = "lane_error"
        raise LaneDiedError(site=cause) from error



async def execute_slop_run(
    *, request: "MarketTwinRunRequest", session: AsyncSession, desktop_scan: bool = False,
) -> None:
    run_state = run_state_repository.RunStateRepository(session)
    run = await session.get(TestRun, request.run_id)
    if run is None:
        raise ValueError("Slop run requires a persisted test run.")
    if run.status in {"completed", "failed", "cancelled"}:
        return
    already_published = await session.scalar(
        select(RunEvent.id).where(
            RunEvent.test_run_id == request.run_id,
            RunEvent.event_type == "slop.state.result",
        ).limit(1)
    )
    if already_published is not None:
        # A previous attempt published the final state results and
        # died before the completion commit landed (publication and
        # completion are separate transactions). The published rows
        # are the durable finalization marker: complete the run and
        # never republish — evaluation aggregates every published
        # row, so a second publication would double every defect
        # count downstream.
        if run.status == "running":
            await run_state.mark_completed(
                test_run_id=request.run_id)
            await session.commit()
        return
    if desktop_scan and run.status == "running":
        collection = await session.scalar(select(RunEvent).where(
            RunEvent.test_run_id == request.run_id,
            RunEvent.event_type == "run.collection",
            RunEvent.execution_id.is_not(None),
        ).order_by(RunEvent.id.desc()).limit(1))
        if collection is not None:
            await _publish_desktop_audit(
                session, run_id=request.run_id, coverage=collection.payload,
                journey_id=collection.journey_id, execution_id=collection.execution_id,
            )
            return
    if run.status != "running":
        await run_state.mark_running(test_run_id=request.run_id)
    budget_snapshot = None
    if desktop_scan:
        budget_snapshot = (run.configuration_snapshot or {}).get("slop_desktop_budget")
        if budget_snapshot is None:
            worker_started = run.started_at.timestamp() if run.started_at else time.time()
            budget_snapshot = {
                "worker_started_at": worker_started,
                "scan_cutoff_at": (worker_started + DESKTOP_TARGET_SECONDS
                                   - DESKTOP_FINALIZATION_RESERVE_SECONDS),
                "target_seconds": DESKTOP_TARGET_SECONDS,
                "finalization_reserve_seconds": DESKTOP_FINALIZATION_RESERVE_SECONDS,
            }
            run.configuration_snapshot = {
                **(run.configuration_snapshot or {}), "slop_desktop_budget": budget_snapshot,
            }
    await session.commit()
    budget = _DesktopScanBudget(budget_snapshot["scan_cutoff_at"]) if budget_snapshot else None

    executions = ExecutionRepository(session)
    events = RunEventRepository(session)
    execution_id = uuid4()
    ordinal = int((run.configuration_snapshot or {}).get("slop_attempt", 0)) + 1
    run.configuration_snapshot = {**run.configuration_snapshot, "slop_attempt": ordinal}
    await session.commit()
    journey = await PlanRepository(session).create_browser_journey(
        test_run_id=request.run_id, ordinal=ordinal, name="Slop checker",
        objective="Inspect authorized pages for visual quality and JavaScript errors.",
        attributes={"runtime_name": "slop_crawl_v1"},
    )
    journey_id = journey.journey_id
    await executions.create_agent_execution(
        execution_id=execution_id, journey_id=journey_id,
        runtime_name="slop_crawl_v1",
    )
    await session.commit()

    desktop_coverage = None
    async with BrowserController() as controller:
        await configure_offsite(controller, run, session)
        handle = await controller.open_room_session(
            run_id=request.run_id, execution_id=execution_id,
            journey_id=journey_id, allowed_origins=request.allowed_origins,
            network_policy=request.network_policy, js_capture=True,
        )
        await executions.create_browser_session(
            browser_session_id=handle.session_id, execution_id=execution_id,
            test_run_id=request.run_id, session_role="room",
        )
        await session.commit()
        lane_count = max(1, min(int(LANE_COUNT), MAX_LANE_COUNT))
        browser_ready = asyncio.Event()
        browser_ready.set()
        handoff_lock = asyncio.Lock()
        current_routes = {}

        def assistance_session():
            return AsyncSession(bind=session.bind, expire_on_commit=False)

        def bind_browser_handoff(browser_handle, *, watch: bool = False) -> None:
            identity = BrowserHandoffExecution(
                request.run_id, execution_id, journey_id, request.allowed_origins,
            )

            async def request_help() -> None:
                async with handoff_lock:
                    if not desktop_scan:
                        browser_ready.clear()
                    try:
                        with budget.human_wait() if budget else nullcontext():
                            async with assistance_session() as handoff_session:
                                route = current_routes.get(browser_handle.session_id)
                                await request_browser_handoff(
                                    request=identity, controller=controller,
                                    handle=browser_handle, session=handoff_session,
                                    expected_url=route if route and not is_account_entry_route(route) else None,
                                )
                    finally:
                        if not desktop_scan:
                            browser_ready.set()

            async def operator_checkpoint() -> None:
                await browser_ready.wait()
                if watch and not (desktop_scan and handoff_lock.locked()):
                    async with handoff_lock:
                        browser_ready.clear()
                        try:
                            async with assistance_session() as handoff_session:
                                await cooperative_pause_checkpoint(
                                    request=identity, controller=controller,
                                    handle=browser_handle, session=handoff_session,
                                    wait_context=budget.human_wait if budget else None,
                                )
                        finally:
                            browser_ready.set()

            controller.bind_authentication_handler(browser_handle, request_help)
            controller.bind_cooperative_pause_handler(browser_handle, operator_checkpoint)

        human_assistance = getattr(request, "runtime_human_assistance", False)
        if human_assistance:
            bind_browser_handoff(handle, watch=True)
        absorber = _SlopAbsorber(
            request=request, session=session, events=events, run=run,
            journey_id=journey_id, execution_id=execution_id,
            controller=controller, lane_count=lane_count,
            synchronous=lane_count == 1, desktop_scan=desktop_scan, budget=budget,
        )
        if desktop_scan:
            absorber.absorb_links([request.start_url], source="submitted")
        absorber.absorb_links(planned_routes(request), source="app plan")
        # Explicit URLs in the study brief can name otherwise unlinked routes.
        for candidate in re.findall(r'https?://[^\s<>"\)]+', request.study_brief):
            candidate = candidate.rstrip(".,;")
            try:
                validate_target_url(candidate, request.allowed_origins,
                                    request.network_policy)
            except BrowserPolicyError:
                continue
            absorber.absorb_links([candidate], source="study brief")
        absorber.note_seeded_queue()
        saved = (run.configuration_snapshot or {}).get("slop_checkpoint")
        if saved:
            if budget is not None:
                budget.human_wait_seconds = saved.get("human_wait_seconds", 0.0)
            absorber.discovery_finished = saved.get("discovery_finished", "discovery_finished" not in saved)
            absorber.discovery_sources.update(saved.get("discovery_sources", {}))
            absorber.excluded_documents.update(saved.get("excluded_documents", {}))
            absorber.sitemap_failures = saved.get("sitemap_failures", 0)
            absorber.sitemaps_pending = saved.get("sitemaps_pending", 0)
            result = await session.execute(select(RunEvent).where(
                RunEvent.test_run_id == request.run_id,
                RunEvent.event_type.in_(("slop.page.checkpoint", "slop.page.inspected", "slop.state.progress")),
            ).order_by(RunEvent.id))
            restored_states: list[dict] = []
            restored_results: dict = {}
            inspected_payloads: dict = {}
            for event in result.scalars():
                if event.event_type == "slop.page.checkpoint":
                    restored_states.extend(event.payload["states"])
                elif event.event_type == "slop.state.progress":
                    record = event.payload
                    restored_results[(record["url"], record["viewport"],
                                      record["path"])] = record
                elif event.event_type == "slop.page.inspected":
                    inspected_payloads[event.payload.get("url")] = event.payload
            absorber.register_restored(restored_states, restored_results)
            if "in_flight" in saved or "lane_count" in saved:
                # S1 snapshot (section 8.6): in-flight pages were
                # claimed but never absorbed, so they are simply
                # pending again — nothing double-counts, and no
                # unassessed state is minted for them.
                visited = set(saved["visited"])
                pending = list(saved["pending"])
                in_flight_urls = [entry["url"]
                                  for entry in saved.get("in_flight", [])]
                if saved.get("active_url") and not in_flight_urls:
                    in_flight_urls = [saved["active_url"]]
                for in_flight_url in in_flight_urls:
                    visited.discard(absorber.url_key(in_flight_url))
                    payload = inspected_payloads.get(in_flight_url) or {}
                    for candidate in payload.get("pending_urls", []):
                        if absorber.url_key(candidate) not in visited \
                                and candidate not in pending:
                            pending.append(candidate)
                queue = in_flight_urls + [url for url in pending
                                          if url not in in_flight_urls]
                absorber.ledger.seed(queue)
                absorber.ledger.set_visited(visited)
            else:
                visited = set(saved["visited"])
                queue = list(saved["pending"])
                absorber.ledger.seed(queue)
                absorber.ledger.set_visited(visited)
                if saved.get("active_url"):
                    payload = inspected_payloads.get(saved["active_url"]) or {}
                    for candidate in payload.get("pending_urls", []):
                        if absorber.url_key(candidate) not in visited \
                                and candidate not in queue:
                            queue.append(candidate)
                            absorber.ledger.enqueue(candidate)
                    interrupted = saved["active_url"]
                    absorber.ledger.set_visited(
                        visited | {canonical_url(interrupted)})
                    unassessed = {"url": interrupted, "elements": [],
                        "js_errors": [],
                        "page_signals": [{"rule_id": "UI_STATE_UNASSESSED",
                            "severity": "info",
                            "detail": "Interrupted page was not replayed; its outcome is unverified."}]}
                    absorber.states.append(unassessed)
                    absorber._absorbed_state_keys.add(
                        _state_content_key(unassessed))
                    await events.create(
                        test_run_id=request.run_id,
                        event_type="slop.page.checkpoint",
                        journey_id=journey_id, execution_id=execution_id,
                        payload={"states": [unassessed]})
                    absorber._write_snapshot()
                    await session.commit()
            absorber.note_seeded_queue()
        elif desktop_scan:
            absorber._write_snapshot()
            await session.commit()
        crawl_failed = False
        finalization_started = False
        discovery_task = None
        try:
            async def discover_sitemaps():
                # Include listed routes that lack a rendered link.
                sitemaps = [urljoin(request.start_url, "/sitemap.xml")]
                maps_seen: set[str] = set()
                sitemap_deadline = time.monotonic() + SITEMAP_DISCOVERY_SECONDS
                while (sitemaps and absorber.seeding_stop_reason is None
                       and (budget is None or not budget.reached())
                       and len(maps_seen) < MAX_SITEMAP_DOCUMENTS
                       and time.monotonic() < sitemap_deadline):
                    sitemap = sitemaps.pop(0)
                    if sitemap in maps_seen:
                        continue
                    maps_seen.add(sitemap)
                    try:
                        validate_target_url(sitemap, request.allowed_origins,
                                            request.network_policy)
                        async with asyncio.timeout(max(0, sitemap_deadline - time.monotonic())):
                            locations = await absorber.crawl_operation(controller.sitemap_locations(
                                session_id=handle.session_id, url=sitemap))
                    except SlopBudgetReached:
                        sitemaps.insert(0, sitemap)
                        break
                    except (BrowserActionError, BrowserPolicyError, TimeoutError):
                        absorber.sitemap_failures += 1
                        continue
                    for location in locations:
                        try:
                            validate_target_url(
                                location, request.allowed_origins,
                                request.network_policy)
                        except BrowserPolicyError:
                            continue
                        if urlsplit(location).path.lower().endswith((".xml", ".xml.gz")):
                            sitemaps.append(location)
                        else:
                            absorber.absorb_links([location], source=sitemap)
                    if not desktop_scan and len(maps_seen) % 5 == 0:
                        review = await absorber.checkpoint_sync(
                            {"phase": "sitemap_discovery",
                             "sitemaps_inspected": len(maps_seen),
                             "sitemaps_pending": len(sitemaps),
                             "pages_pending": len(absorber.ledger.pending_urls)})
                        if review["decision"] == "stop":
                            absorber.seeding_stop_reason = review["reason"]
                            absorber.seeding_stop_source = review.get("source")
                            absorber._seeding_stop_pending = True
                absorber.sitemaps_pending = len(sitemaps)
                absorber.discovery_finished = True

            async def discover_while_scanning():
                try:
                    await discover_sitemaps()
                finally:
                    absorber.discovery_running = False

            if desktop_scan and not absorber.discovery_finished:
                absorber.discovery_running = True
                discovery_task = asyncio.create_task(discover_while_scanning())
            elif not saved:
                await discover_sitemaps()

            room_assigned = False

            async def _session_factory(lane_index):
                nonlocal room_assigned
                await browser_ready.wait()
                if lane_index == 0 and not room_assigned:
                    room_assigned = True
                    return _RoomLaneSession(handle)
                worker_handle = await absorber.crawl_operation(controller.create_worker_session(
                    room_session_id=handle.session_id,
                    execution_id=execution_id, journey_id=journey_id,
                    lane_index=lane_index, js_capture=True,
                    **({"reuse_room_auth": False} if human_assistance else {}),
                ))
                if not human_assistance:
                    return _ControllerLaneSession(controller, worker_handle)
                try:
                    async with assistance_session() as handoff_session:
                        await ExecutionRepository(handoff_session).create_browser_session(
                            browser_session_id=worker_handle.session_id, execution_id=execution_id,
                            test_run_id=request.run_id, session_role="worker",
                        )
                        await handoff_session.commit()
                    bind_browser_handoff(worker_handle)
                except BaseException:
                    await controller.close_session(session_id=worker_handle.session_id)
                    raise
                return _ControllerLaneSession(
                    controller, worker_handle, session_factory=assistance_session,
                )

            async def _process_page(claim, lane_session, heartbeat):
                await browser_ready.wait()
                if budget is not None and budget.reached():
                    raise SlopBudgetReached
                browser_handle = lane_session.handle
                current_routes[browser_handle.session_id] = claim.url
                try:
                    await _inspect_page(
                        absorber=absorber, controller=controller,
                        handle=browser_handle, claim=claim,
                        watched_browser=isinstance(lane_session, _RoomLaneSession))
                finally:
                    current_routes.pop(browser_handle.session_id, None)

            pool = LanePool(
                lane_count=lane_count,
                session_factory=_session_factory,
                process_page=_process_page,
                claim_next=absorber.claim_next,
                work_remaining=absorber.work_remaining,
                should_stop=absorber.should_stop,
                complete_claim=absorber.complete_claim,
                fail_claim=absorber.absorb_attempted_failed,
                release_claim=absorber.release_claim,
                breaker=absorber.breaker,
                on_event=absorber.emit_pool_event,
                work_paused=lambda: not browser_ready.is_set() or handoff_lock.locked(),
                replace_browser_sessions=desktop_scan,
            )
            absorber.progress_hook = pool.note_progress
            try:
                pool_result = await pool.run()
                retired_lanes = pool_result.retired_lanes
            except PoolExhaustedError as error:
                if not desktop_scan:
                    raise
                retired_lanes = error.retired_lanes
            if discovery_task is not None:
                await discovery_task
            # Settle any checkpoint review still in flight before
            # the completion accounting reads the stop state: its
            # decision is part of this run's record.
            await absorber.aclose(wait=True)
            states = absorber.states
            if desktop_scan:
                finalization_started = True
                if not absorber.owner_stopped:
                    await absorber._poll_owner_stop()
                for claim in absorber.ledger.in_flight_claims:
                    absorber.ledger.release(claim)
                absorber._write_snapshot()
            queue = absorber.ledger.pending_urls
            stopped_by_supervision = absorber.stop_requested
            measured_states = [state for state in states if not _is_unassessed(state)] if desktop_scan else states
            pages_recorded = {state["url"] for state in measured_states}
            pages_unverified = {state["url"] for state in states if _is_unassessed(state)}
            unfinished_phases = [
                signal["rule_id"]
                for state in states for signal in state["page_signals"]
                if signal["rule_id"] in {
                    "UI_VISUAL_REVIEW_UNFINISHED", "UI_LINK_DISCOVERY_UNFINISHED",
                    "UI_EVIDENCE_UNFINISHED",
                }
            ]
            budget_exhausted = bool(budget is not None and budget.reached() and (
                queue or absorber.sitemaps_pending or unfinished_phases
            ))
            partial = bool(stopped_by_supervision or queue or pages_unverified
                           or absorber.sitemaps_pending or absorber.sitemap_failures
                           or budget_exhausted)
            if states and not desktop_scan and (queue or stopped_by_supervision or pages_unverified):
                states[-1]["page_signals"].append({
                    "rule_id": "AUDIT_PARTIAL_COVERAGE", "severity": "info",
                    "detail": f"Partial audit: {len(queue)} discovered pages remain uninspected; "
                              "some UI states may also be blocked or unassessed. See page details.",
                })
                states[-1]["page_signals"].extend({
                    "rule_id": "AUDIT_PENDING_PAGE", "severity": "info",
                    "detail": f"Not inspected: {pending_url}",
                } for pending_url in queue)
            # Console-error severity pass: a console error that
            # reproduces on a re-visit is serious (catalogue rule);
            # a one-off stays minor. The pass runs even when
            # supervision stopped the crawl: it only re-visits pages
            # already inspected, and a stop must not silently
            # downgrade reproduced errors to minor.
            for signal, first, second in compare_components([] if desktop_scan else states):
                signal["evidence_indexes"] = [0, 1]
                await retain_finding_evidence([first, second], [signal], absorber.save_evidence)
            for measured in ([] if desktop_scan else states):
                console_entries = [
                    e for e in measured["js_errors"]
                    if e["rule_id"] == "DEF_JS_CONSOLE_ERROR"
                ]
                if not console_entries:
                    continue
                await controller.navigate(
                    session_id=handle.session_id, url=str(measured["url"]),
                    observe=False,
                )
                await controller.probe_page(session_id=handle.session_id)
                revisit = await absorber.fresh_records_for(
                    session_id=handle.session_id, url=str(measured["url"]))
                reproduced = {
                    e["message"] for e in dedupe_js_errors(
                        revisit, state_url=str(measured["url"]),
                    ) if e["rule_id"] == "DEF_JS_CONSOLE_ERROR"
                }
                for entry in console_entries:
                    if entry["message"] in reproduced:
                        entry["severity"] = "serious"
            await absorber.flush_progress()
            if not desktop_scan:
                await _publish_states(events, run_id=request.run_id, journey_id=journey_id,
                                      execution_id=execution_id, states=states)
            interactions = list(absorber.control_results.values())
            paths_activated = sum(record["result"] in {"observed", "duplicate_state", "navigated"}
                                  for record in interactions)
            coverage = {
                "run_kind": "slop",
                "journey_count": 1,
                "states_recorded": len(measured_states),
                "pages_recorded": len(pages_recorded),
                "screenshots_recorded": sum(
                    bool(state.get("screenshot_artifact_id")) for state in measured_states),
                "excluded_documents": absorber.excluded_documents,
                "sitemap_failures": absorber.sitemap_failures,
                "sitemaps_pending": absorber.sitemaps_pending,
                "pages_pending": len(queue),
                "pending_urls": queue,
                "interaction_coverage": interactions,
                "paths_activated": paths_activated,
                "paths_not_assessed": len(interactions) - paths_activated,
                "lane_count": lane_count,
                "duplicate_absorptions": absorber.duplicate_absorptions,
                "owner_stopped": absorber.owner_stopped,
                "partial": partial,
            }
            if desktop_scan:
                coverage.update(
                    desktop_scan=True,
                    evaluation_contract={
                        "version": SLOP_EVALUATION_CONTRACT_VERSION,
                        "expected_states": len(states),
                    },
                    pages_unverified=len(pages_unverified - pages_recorded),
                    stop_reason=(absorber.stop_reason
                                 or (DESKTOP_BUDGET_STOP_REASON if budget_exhausted else None)),
                    budget_exhausted=budget_exhausted,
                    visual_reviews_unfinished=unfinished_phases.count("UI_VISUAL_REVIEW_UNFINISHED"),
                    all_lanes_retired=len(retired_lanes) == lane_count,
                    retired_lanes=[{"lane_id": lane_id, "cause": cause}
                                   for lane_id, cause in sorted(retired_lanes.items())],
                    desktop_performance={
                        "phases": absorber.phase_samples,
                        "checkpoint_writes": absorber.snapshot_writes,
                        "checkpoint_samples": len(absorber.snapshot_bytes),
                        "checkpoint_max_sample_bytes": max(absorber.snapshot_bytes, default=0),
                    },
                )
            if budget_snapshot is not None and budget is not None:
                elapsed = time.time() - budget_snapshot["worker_started_at"]
                coverage["desktop_budget"] = {
                    **budget_snapshot,
                    "worker_elapsed_seconds": round(elapsed, 2),
                    "human_wait_seconds": round(budget.human_wait_seconds, 2),
                    "active_elapsed_seconds": round(max(0.0, elapsed - budget.human_wait_seconds), 2),
                    "stop_reason": DESKTOP_BUDGET_STOP_REASON if budget_exhausted else None,
                }
            # A desktop collection with an execution ID marks a committed
            # checkpoint ready for report publication without browser replay.
            await events.create(test_run_id=request.run_id, event_type="run.collection",
                journey_id=journey_id if desktop_scan else None,
                execution_id=execution_id if desktop_scan else None, payload=coverage)
            if desktop_scan:
                run.configuration_snapshot = {
                    **(run.configuration_snapshot or {}),
                    "slop_evaluation_contract_required": True,
                }
                await executions.mark_browser_session_closed(browser_session_id=handle.session_id)
                await executions.finish_agent_execution(
                    execution_id=execution_id,
                    status="completed" if measured_states or absorber.owner_stopped else "failed",
                    outcome=None,
                )
            await session.commit()
            if desktop_scan:
                desktop_coverage = coverage
        except BaseException as error:
            crawl_failed = True
            if (finalization_started and isinstance(error, Exception)
                    or isinstance(error, SlopPersistenceError)):
                raise SlopFinalizationError("collection") from error
            if isinstance(error, PendingRollbackError) and absorber._review_error is not None:
                raise absorber._review_error from error
            raise
        finally:
            if discovery_task is not None:
                if not discovery_task.done():
                    discovery_task.cancel()
                await asyncio.gather(discovery_task, return_exceptions=True)
            # The success path already drained reviews and persisted progress.
            # On failure, cancel the remaining writers before rolling back.
            if crawl_failed:
                await absorber.aclose()
            for path in absorber.review_captures:
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    logging.getLogger(__name__).warning("Could not remove temporary UI review capture")
            # Bounded, best-effort teardown (F5): if the browser died
            # with the host, close_room can await a dead driver forever
            # and hold the run open (MT-000151). The bookkeeping below
            # is what closes the run; it must always be reached.
            try:
                async with asyncio.timeout(TEARDOWN_TIMEOUT_SECONDS):
                    await controller.close_room(run_id=request.run_id)
            except Exception:
                pass
            if desktop_coverage is None:
                try:
                    if crawl_failed:
                        await session.rollback()
                    await executions.mark_browser_session_closed(
                        browser_session_id=handle.session_id,
                    )
                    await executions.finish_agent_execution(
                        execution_id=execution_id,
                        status="failed" if crawl_failed else "completed",
                        outcome=None,
                    )
                    await session.commit()
                except Exception as error:
                    if not crawl_failed:
                        raise
                    logging.getLogger(__name__).warning(
                        "UI audit %s cleanup could not persist (%s)", request.run_id, type(error).__name__,
                    )
    if desktop_coverage is not None:
        await _publish_desktop_audit(
            session, run_id=request.run_id, coverage=desktop_coverage,
            journey_id=journey_id, execution_id=execution_id, states=states,
        )
        return
    # Reached only when the crawl finished: like the Board engine,
    # the executor owns the run's terminal state. Without this the
    # run stays "running" forever and a Kafka redelivery would mark
    # the finished run failed.
    if absorber.owner_stopped:
        await run_state.mark_cancelled(
            test_run_id=request.run_id)
    else:
        await run_state.mark_completed(
            test_run_id=request.run_id)
    await session.commit()
