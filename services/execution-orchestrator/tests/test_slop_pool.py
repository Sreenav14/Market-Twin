"""Speed S1 (doc 18 sections 8/10/15): lane pool, claim ledger,
absorber accounting, circuit-breaker, and the lane factory pins.
Fake controllers/queues/sessions throughout — no network, no real
browser, no real model."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.slop.pool import (
    ClaimLedger,
    HostCircuitBreaker,
    LaneDiedError,
    LanePool,
    PoolExhaustedError,
)
from markettwin_execution_orchestrator.workflow import slop_run
from markettwin_execution_orchestrator.workflow.slop_run import (
    _PageContext,
    _PageRecord,
    _SlopAbsorber,
)


def test_desktop_route_rotation_survives_queue_reload():
    ledger = ClaimLedger(canonical=lambda url: url, rotate_routes=True)
    variants = [f"https://example.test/research/bench?q={index}" for index in range(1000)]
    sibling = "https://example.test/research/overview"
    primary = "https://example.test/product/"
    ledger.seed([*variants, sibling, primary])
    first = ledger.claim_next(0)
    assert first is not None and first.url == variants[0]
    ledger.finish(first)

    resumed = ClaimLedger(canonical=lambda url: url, rotate_routes=True)
    resumed.seed(ledger.pending_urls)
    resumed.set_visited(ledger.visited_keys)
    assert resumed.enqueue("https://example.test/research/bench?q=1000")
    assert resumed.enqueue("https://example.test/research/overview#/settings")
    claims = [resumed.claim_next(0) for _ in range(4)]
    assert [claim.url for claim in claims if claim is not None] == [
        primary, sibling, variants[1], "https://example.test/research/overview#/settings",
    ]
    assert len(resumed.pending_urls) == 999


def test_desktop_section_roots_precede_deep_sitemap_routes():
    ledger = ClaimLedger(canonical=lambda url: url, rotate_routes=True)
    root = "https://x.test"
    ledger.seed([root, f"{root}/blog/article", f"{root}/docs/guide",
                 f"{root}/blog", f"{root}/docs"])
    assert [ledger.claim_next(0).url for _ in range(5)] == [
        root, f"{root}/blog", f"{root}/docs", f"{root}/blog/article", f"{root}/docs/guide",
    ]


# ----------------------------------------------------------------
# Pool harness: a ClaimLedger-backed claim source + recording
# absorber callbacks, mirroring the production wiring in slop_run.
# ----------------------------------------------------------------

class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_ledger_rotates_sections_without_losing_or_repeating_pages():
    ledger = ClaimLedger(canonical=lambda url: url.rstrip("/"))
    root = "https://x.test"
    ledger.seed([f"{root}/product", f"{root}/blog/a", f"{root}/blog/b",
                 f"{root}/blog/b/", f"{root}/docs/a"])
    assert not ledger.enqueue(f"{root}/blog/b/")
    assert ledger.enqueue(f"{root}/pricing")
    assert [ledger.claim_next(0).url for _ in range(5)] == [
        f"{root}/product", f"{root}/blog/a", f"{root}/docs/a",
        f"{root}/pricing", f"{root}/blog/b",
    ]
    assert ledger.claim_next(0) is None


class PoolHarness:
    def __init__(self, urls, *, lane_count=2, clock=None, breaker=None,
                 stall_seconds=420, check_seconds=30):
        self.ledger = ClaimLedger(canonical=lambda url: url)
        self.ledger.seed(list(urls))
        self.completed = []
        self.failures = []
        self.released = []
        self.events = []
        self.clock = clock or (lambda: 0.0)

        async def claim_next(lane_id):
            return self.ledger.claim_next(lane_id)

        async def complete_claim(claim):
            self.ledger.finish(claim)
            self.completed.append(claim)

        async def fail_claim(claim, *, site, lane_id):
            self.ledger.finish(claim)
            self.failures.append((claim, site, lane_id))

        async def release_claim(claim):
            self.ledger.release(claim)
            self.released.append(claim)

        async def on_event(event_type, payload):
            self.events.append((event_type, payload))

        self.claim_next = claim_next
        self.pool_kwargs = dict(
            lane_count=lane_count,
            claim_next=claim_next,
            work_remaining=self.ledger.work_remaining,
            should_stop=lambda: False,
            complete_claim=complete_claim,
            fail_claim=fail_claim,
            release_claim=release_claim,
            breaker=breaker,
            on_event=on_event,
            clock=self.clock,
            stall_seconds=stall_seconds,
            check_seconds=check_seconds,
        )

    def pool(self, *, process_page, session_factory=None, work_paused=None):
        async def factory(lane_index):
            return SimpleNamespace(
                handle=SimpleNamespace(session_id=uuid4()),
                close=AsyncMock())

        return LanePool(
            session_factory=session_factory or factory,
            process_page=process_page, work_paused=work_paused, **self.pool_kwargs)


# ----------------------------------------------------------------
# T-P1: claims are issued in queue order, exactly once each.
# ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_t_p1_claims_in_queue_order_exactly_once():
    urls = [f"https://x.test/p{i}" for i in range(10)]
    harness = PoolHarness(urls, lane_count=3)
    seen = []

    async def process(claim, session, heartbeat):
        seen.append((claim.url, claim.claim_seq, claim.claimed_by,
                     claim.attempt))
        await asyncio.sleep(0)

    result = await harness.pool(process_page=process).run()
    assert result.drained and not result.stopped
    assert sorted(url for url, *_ in seen) == sorted(urls)
    by_seq = sorted(seen, key=lambda entry: entry[1])
    assert [url for url, *_ in by_seq] == urls  # claim order == queue order
    assert [seq for _, seq, *_ in by_seq] == list(range(1, 11))
    assert all(attempt == 1 for *_, attempt in seen)
    assert {lane for _, _, lane, _ in seen} <= {0, 1, 2}


# ----------------------------------------------------------------
# Lane factory pins (I1, I6) + proof parity (I3): the real
# controller, a fake Room. Storage state is seeded iff the Room is
# authenticated; both guardrail handlers are attached to every
# sibling context, worker and proof alike.
# ----------------------------------------------------------------

def _fake_context():
    return SimpleNamespace(
        route=AsyncMock(), route_web_socket=AsyncMock(), on=Mock(),
        add_init_script=AsyncMock(),
        new_page=AsyncMock(return_value=SimpleNamespace()),
        set_default_timeout=Mock(), set_default_navigation_timeout=Mock())


@pytest.mark.asyncio
@pytest.mark.parametrize("authenticated", [True, False])
async def test_lane_factory_seeding_and_guardrails(
        monkeypatch, tmp_path, authenticated):
    from markettwin_execution_orchestrator.browser import (
        controller as controller_module,
    )

    monkeypatch.setattr(controller_module, "start_trace", AsyncMock())
    monkeypatch.setattr(BrowserController, "_configure_page", AsyncMock())
    controller = BrowserController(artifact_root=tmp_path)
    context = _fake_context()
    room = SimpleNamespace(
        authenticated_session=authenticated,
        context=SimpleNamespace(storage_state=AsyncMock(
            return_value={"cookies": ["a"]})),
        browser=SimpleNamespace(
            new_context=AsyncMock(return_value=context)),
        timeout_ms=5000, allowed_origins=(), network_policy="public_only",
        auth_only_origins=(), fixture_action_rules=())
    room_id = uuid4()
    controller._sessions[room_id] = room

    handle = await controller.create_worker_session(
        room_session_id=room_id, execution_id=uuid4(),
        journey_id=uuid4(), lane_index=2)
    kwargs = room.browser.new_context.await_args.kwargs
    if authenticated:
        room.context.storage_state.assert_awaited_once()
        assert kwargs["storage_state"] == {"cookies": ["a"]}
    else:
        room.context.storage_state.assert_not_awaited()
        assert kwargs["storage_state"] is None
    # I6: both guardrail route handlers, attached at birth.
    context.route.assert_awaited_once()
    assert context.route.await_args.args[0] == "**/*"
    context.route_web_socket.assert_awaited_once()
    assert context.route_web_socket.await_args.args[0] == "**/*"
    assert controller._session_purposes[handle.session_id] == "worker"

    # I3: proof sessions ride the same factory, unchanged.
    proof_context = _fake_context()
    room.browser.new_context = AsyncMock(return_value=proof_context)
    proof = await controller.create_proof_session(
        room_session_id=room_id, execution_id=uuid4(), journey_id=uuid4())
    assert controller._session_purposes[proof.session_id] == "proof"
    proof_context.route.assert_awaited_once()
    proof_context.route_web_socket.assert_awaited_once()


# ----------------------------------------------------------------
# Absorber harness.
# ----------------------------------------------------------------

def make_absorber(*, synchronous, lane_count=2, desktop_scan=False):
    request = SimpleNamespace(
        run_id=uuid4(),
        allowed_origins=(), network_policy="public_only",
        study_brief="Audit UI", app_map=None)
    created = []

    async def create(**kwargs):
        created.append(kwargs)

    events = SimpleNamespace(create=create)
    session = SimpleNamespace(commit=AsyncMock())
    run = SimpleNamespace(configuration_snapshot={})
    absorber = _SlopAbsorber(
        request=request, session=session, events=events, run=run,
        journey_id=uuid4(), execution_id=uuid4(),
        controller=SimpleNamespace(), lane_count=lane_count,
        synchronous=synchronous, desktop_scan=desktop_scan)
    absorber.created_events = created
    return absorber


def _progress(n, *, lane_url="https://x.test/"):
    return {"url": lane_url, "viewport": "mobile320", "path": f"path {n}",
            "pending_paths": 3, "result": "observed"}


def _checkpoint_evidence(**overrides):
    evidence = {"url": "https://x.test/", "viewport": "mobile320",
                "checked_items": 15, "checked_delta": 15,
                "attempted_delta": 15, "productive_delta": 15,
                "states_measured": 0, "routes_discovered": 0,
                "pending_paths": 3}
    evidence.update(overrides)
    return evidence


# ----------------------------------------------------------------
# T-P2: a forced duplicate absorption keeps the first record and
# counts the duplicate (section 9.1 defence-in-depth).
# ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_t_p2_duplicate_absorption_counted_not_absorbed():
    absorber = make_absorber(synchronous=False)
    state = {"url": "https://x.test/", "viewport": "mobile320",
             "interaction_path": "Open", "elements": [{"name": "a"}],
             "page_signals": [], "js_errors": []}
    ledger = absorber.ledger
    ledger.seed(["https://x.test/"])
    claim_a = ledger.claim_next(0)
    claim_b = ledger.claim_next(1)  # same URL re-claimed after release
    ledger.release(claim_a)
    claim_b = ledger.claim_next(1)
    for claim in (claim_a, claim_b):
        record = _PageRecord(claim=claim, url="https://x.test/",
                             states=[dict(state)], links=[],
                             entry_state=None, load_status=200)
        await absorber.absorb_inspected(record)
    assert len(absorber.states) == 1
    assert absorber.duplicate_absorptions == 1


# ----------------------------------------------------------------
# T-P3 (absorber): a checkpoint is requested exactly once per 15
# GLOBAL absorbed paths, never more than one in flight; the
# stagnation gate consumes global deltas; the queue guard reads the
# global queue.
# ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_t_p3_global_checkpoint_cadence_and_single_flight(monkeypatch):
    review = AsyncMock(return_value={"decision": "continue",
                                     "reason": "ok", "source": "lead"})
    monkeypatch.setattr(slop_run, "review_checkpoint", review)
    absorber = make_absorber(synchronous=False)
    ctx = _PageContext()
    # states_measured grows at every fire so the stagnation gate
    # (pinned separately below) stays out of the cadence assertions.
    measured = {"count": 0}

    async def absorb_paths(lane, count, start):
        for n in range(start, start + count):
            await absorber.absorb_progress(lane, _progress(n))

    async def request():
        measured["count"] += 5
        return await absorber.request_checkpoint(
            _checkpoint_evidence(states_measured=measured["count"]),
            page_ctx=ctx)

    # First cadence window, split across two lanes: exactly one fire.
    await absorb_paths(0, 8, 0)
    await absorb_paths(1, 7, 8)
    await request()
    assert len(absorber._review_tasks) == 1
    await asyncio.gather(*list(absorber._review_tasks))
    assert review.await_count == 1

    # Second window: exactly one more.
    await absorb_paths(1, 15, 15)
    await request()
    await asyncio.gather(*list(absorber._review_tasks))
    assert review.await_count == 2

    # Single flight: a blocking review suppresses the next window's
    # fire; its deltas accumulate and ride the following fire.
    gate = asyncio.Event()

    async def blocking_review(**kwargs):
        await gate.wait()
        return {"decision": "continue", "reason": "ok", "source": "lead"}

    review.side_effect = blocking_review
    await absorb_paths(0, 15, 30)
    await request()
    await absorb_paths(1, 15, 45)
    await request()
    assert len(absorber._review_tasks) == 1  # suppressed, not queued twice
    gate.set()
    await asyncio.gather(*list(absorber._review_tasks))
    review.side_effect = None
    review.return_value = {"decision": "continue", "reason": "ok",
                           "source": "lead"}
    await absorb_paths(0, 1, 60)
    await request()
    await asyncio.gather(*list(absorber._review_tasks))
    assert review.await_count == 4
    # The suppressed window's deltas were summed into the next fire.
    assert review.await_args_list[-1].kwargs["evidence"]["checked_delta"] == 30


@pytest.mark.asyncio
async def test_t_p3_stagnation_gate_is_global_across_pages(monkeypatch):
    review = AsyncMock(return_value={"decision": "continue",
                                     "reason": "Keep going",
                                     "source": "lead"})
    monkeypatch.setattr(slop_run, "review_checkpoint", review)
    absorber = make_absorber(synchronous=True)
    ctx_a, ctx_b = _PageContext(), _PageContext()
    # Productive totals never move, checks are attempted, pending
    # paths keep growing — alternating between two pages' traversals.
    # Per-(url, viewport) keying would reset the count per page; the
    # global history must trip the gate on the fourth checkpoint.
    for index, ctx in enumerate((ctx_a, ctx_b, ctx_a, ctx_b)):
        result = await absorber.request_checkpoint(
            _checkpoint_evidence(checked_delta=5, pending_paths=10 + index),
            page_ctx=ctx)
    assert review.await_count == 3
    third = review.await_args_list[2].kwargs["evidence"]
    assert third["stagnation"] is True
    assert result["source"] == "stagnation_gate"
    assert absorber.stop_requested


@pytest.mark.asyncio
async def test_t_p3_queue_guard_reads_the_global_queue(monkeypatch):
    review = AsyncMock(return_value={"decision": "stop",
                                     "reason": "halt", "source": "lead"})
    monkeypatch.setattr(slop_run, "review_checkpoint", review)
    absorber = make_absorber(synchronous=True)
    absorber.ledger.seed([f"https://x.test/p{i}" for i in range(12)])
    ctx = _PageContext()
    ctx.entry_state = {"page_signals": []}
    await absorber._process_checkpoint(
        {"url": "https://x.test/"}, page_ctx=ctx, kind="traversal")
    assert not absorber.stop_requested
    assert ctx.stop_overruled
    assert any(signal["rule_id"] == "AUDIT_LEAD_STOP_OVERRULED"
               for signal in ctx.entry_state["page_signals"])
    # At or below the threshold the same stop stands.
    while len(absorber.ledger.pending_urls) > 10:
        absorber.ledger.claim_next(0)
    ctx2 = _PageContext()
    ctx2.entry_state = {"page_signals": []}
    await absorber._process_checkpoint(
        {"url": "https://x.test/"}, page_ctx=ctx2, kind="traversal")
    assert absorber.stop_requested
    assert ctx2.stop_honoured


# ----------------------------------------------------------------
# T-P4: racing lanes never overrun the model-call budget. The
# production ledger (markettwin_database.model_budget) reserves
# under a per-run PostgreSQL advisory lock — there is no in-memory
# counter to race; this pins the concurrent-debit pattern the ask
# door relies on, plus the budget-expiry honesty shape: pages
# completed after exhaustion are deterministically checked and
# carry the vision-unassessed marker.
# ----------------------------------------------------------------

class _BudgetExhausted(Exception):
    pass


class _FakeBudgetLedger:
    """The model_budget reservation pattern in miniature: one lock,
    reserve-before-send, cap enforced at reservation time."""

    def __init__(self, cap):
        self.cap = cap
        self.used = 0
        self._lock = asyncio.Lock()

    async def debit(self):
        async with self._lock:
            if self.used >= self.cap:
                raise _BudgetExhausted
            self.used += 1


@pytest.mark.asyncio
async def test_t_p4_racing_lanes_never_exceed_the_budget_cap():
    ledger = _FakeBudgetLedger(cap=10)
    urls = [f"https://x.test/p{i}" for i in range(8)]
    harness = PoolHarness(urls, lane_count=4)
    records = []

    async def process(claim, session, heartbeat):
        record = {"url": claim.url, "vision_unassessed": False}
        for _ in range(2):  # entry review + batched review
            try:
                await ledger.debit()
            except _BudgetExhausted:
                record["vision_unassessed"] = True
        records.append(record)

    await harness.pool(process_page=process).run()
    assert ledger.used == 10
    assert len(records) == 8
    assert any(record["vision_unassessed"] for record in records)


# ----------------------------------------------------------------
# T-P5: a lane's death is not the run's death; all lanes dead with
# work remaining fails the run through the failure path.
# ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_desktop_policy_refusals_keep_all_four_lanes_available():
    urls = [f"https://x.test/section-{index}" for index in range(8)]
    absorber = make_absorber(synchronous=False, lane_count=4, desktop_scan=True)
    harness = PoolHarness(urls, lane_count=4)
    first_wave = asyncio.Barrier(4)
    followup = asyncio.Barrier(4)
    controller = SimpleNamespace(navigate=AsyncMock(
        side_effect=slop_run.TargetUrlValidationError("private error detail"),
    ))

    async def process(claim, session, heartbeat):
        if claim.claim_seq <= 4:
            await first_wave.wait()
            if claim.claim_seq <= 3:
                await slop_run._inspect_page(
                    absorber=absorber, controller=controller, handle=session.handle, claim=claim,
                )
        else:
            await followup.wait()

    result = await asyncio.wait_for(harness.pool(process_page=process).run(), timeout=5)
    assert result.drained
    assert not result.retired_lanes
    assert {claim.claimed_by for claim in harness.completed if claim.claim_seq > 4} == {0, 1, 2, 3}
    assert len(absorber.states) == 3
    assert all(state["policy_code"] == "target_url" for state in absorber.states)
    # Fix A contract: the exception's class and bounded detail ARE
    # recorded now, through the named diagnostic fields — and only
    # there. This fake controller has no session registry, so the
    # current page URL falls back to "".
    assert all(state["policy_error_class"] == "TargetUrlValidationError"
               for state in absorber.states)
    assert all(state["policy_error_detail"] == "private error detail"
               for state in absorber.states)
    assert all(state["policy_claim_url"] == state["url"] for state in absorber.states)
    assert all(state["policy_current_url"] == "" for state in absorber.states)
    stripped = [{key: value for key, value in state.items()
                 if key != "policy_error_detail"} for state in absorber.states]
    assert "private error detail" not in repr(stripped)


@pytest.mark.asyncio
async def test_desktop_policy_refusal_records_current_page_url():
    absorber = make_absorber(synchronous=False, lane_count=1, desktop_scan=True)
    absorber.ledger.seed(["https://x.test/wedged"])
    claim = absorber.ledger.claim_next(0)
    session = SimpleNamespace(page=SimpleNamespace(url="chrome-error://chromewebdata/"))
    controller = SimpleNamespace(
        navigate=AsyncMock(side_effect=slop_run.TargetUrlValidationError(
            "resting page refused")),
        _get_session=lambda session_id: session,
    )
    handle = SimpleNamespace(session_id=uuid4())
    await slop_run._inspect_page(
        absorber=absorber, controller=controller, handle=handle, claim=claim)
    assert len(absorber.states) == 1
    state = absorber.states[0]
    assert state["policy_code"] == "target_url"
    assert state["policy_error_class"] == "TargetUrlValidationError"
    assert state["policy_error_detail"] == "resting page refused"
    assert state["policy_claim_url"] == "https://x.test/wedged"
    assert state["policy_current_url"] == "chrome-error://chromewebdata/"


@pytest.mark.asyncio
async def test_desktop_policy_refusal_truncates_error_detail():
    absorber = make_absorber(synchronous=False, lane_count=1, desktop_scan=True)
    absorber.ledger.seed(["https://x.test/long"])
    claim = absorber.ledger.claim_next(0)
    controller = SimpleNamespace(navigate=AsyncMock(
        side_effect=slop_run.TargetUrlValidationError("x" * 400)))
    handle = SimpleNamespace(session_id=uuid4())
    await slop_run._inspect_page(
        absorber=absorber, controller=controller, handle=handle, claim=claim)
    assert len(absorber.states) == 1
    assert absorber.states[0]["policy_error_detail"] == "x" * 300


@pytest.mark.asyncio
async def test_desktop_load_failure_records_error_diagnostics(monkeypatch):
    monkeypatch.setattr(slop_run, "review_checkpoint", AsyncMock(
        return_value={"decision": "continue", "reason": "ok", "source": "lead"}))
    absorber = make_absorber(synchronous=False, lane_count=1, desktop_scan=True)
    absorber.ledger.seed(["https://x.test/broken"])
    claim = absorber.ledger.claim_next(0)
    session = SimpleNamespace(page=SimpleNamespace(url="https://x.test/broken"))
    controller = SimpleNamespace(
        navigate=AsyncMock(side_effect=slop_run.BrowserActionError(
            "net::ERR_CONNECTION_REFUSED", reason_code="navigation_failed")),
        _get_session=lambda session_id: session,
    )
    handle = SimpleNamespace(session_id=uuid4())
    await slop_run._inspect_page(
        absorber=absorber, controller=controller, handle=handle, claim=claim)
    await absorber.aclose(wait=True)
    assert len(absorber.states) == 1
    state = absorber.states[0]
    assert state["load_error_class"] == "BrowserActionError"
    assert state["load_error_detail"] == "net::ERR_CONNECTION_REFUSED"
    assert state["load_error_current_url"] == "https://x.test/broken"


@pytest.mark.asyncio
async def test_desktop_dead_session_is_replaced_once_without_replaying_failed_pages():
    urls = [f"https://x.test/page-{index}" for index in range(4)]
    harness = PoolHarness(urls, lane_count=1)
    sessions = []

    async def factory(lane_index):
        session = SimpleNamespace(close=AsyncMock())
        sessions.append(session)
        return session

    async def process(claim, session, heartbeat):
        if claim.url in {urls[0], urls[2]}:
            raise LaneDiedError(site="browser_session")

    harness.pool_kwargs["replace_browser_sessions"] = True
    with pytest.raises(PoolExhaustedError):
        await harness.pool(process_page=process, session_factory=factory).run()
    assert len(sessions) == 2
    assert all(session.close.await_count == 1 for session in sessions)
    assert [claim.url for claim in harness.completed] == [urls[1]]
    assert [claim.url for claim, _, _ in harness.failures] == [urls[0], urls[2]]
    assert harness.ledger.pending_urls == [urls[3]]
    assert [kind for kind, _ in harness.events] == [
        "slop.lane.replacement_scheduled", "slop.lane.retired",
    ]


@pytest.mark.asyncio
async def test_t_p5_lane_death_retires_lane_and_run_completes():
    urls = [f"https://x.test/p{i}" for i in range(4)]
    harness = PoolHarness(urls, lane_count=2)
    done = []

    async def process(claim, session, heartbeat):
        if claim.url == urls[0]:
            raise LaneDiedError(site="target_closed")
        done.append(claim.url)

    result = await harness.pool(process_page=process).run()
    assert result.drained
    assert sorted(done) == sorted(urls[1:])
    assert [(claim.url, site) for claim, site, _ in harness.failures] == [
        (urls[0], "target_closed")]
    claim, _, lane_id = harness.failures[0]
    assert ("slop.lane.retired", {
        "lane_id": lane_id, "claim_seq": claim.claim_seq,
        "cause": "lane_died", "phase": "inspection",
        "remaining_lanes": 1, "replacement_scheduled": False,
    }) in harness.events


@pytest.mark.asyncio
async def test_t_p5_all_lanes_dead_fails_the_run():
    urls = [f"https://x.test/p{i}" for i in range(4)]
    harness = PoolHarness(urls, lane_count=2)

    async def process(claim, session, heartbeat):
        raise LaneDiedError(site="target_closed")

    with pytest.raises(PoolExhaustedError):
        await harness.pool(process_page=process).run()


# ----------------------------------------------------------------
# T-P6: the lane stall guard cancels a silent lane while a sibling
# keeps producing; the run completes. (The worker-level watchdog is
# a different process layer and is not invoked — by construction.)
# ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_t_p6_lane_stall_guard_cancels_only_the_silent_lane():
    clock = FakeClock()
    hang = "https://x.test/hang"
    urls = [hang] + [f"https://x.test/p{i}" for i in range(30)]
    harness = PoolHarness(urls, lane_count=2, clock=clock,
                          stall_seconds=100, check_seconds=0.02)
    done = []

    async def ticker():
        while True:
            clock.advance(10)
            await asyncio.sleep(0.01)

    async def process(claim, session, heartbeat):
        if claim.url == hang:
            await asyncio.Event().wait()  # never answers, never reports
        heartbeat()
        done.append(claim.url)
        await asyncio.sleep(0.01)

    ticker_task = asyncio.create_task(ticker())
    try:
        result = await harness.pool(process_page=process).run()
    finally:
        ticker_task.cancel()
    assert result.drained
    assert sorted(done) == sorted(urls[1:])
    assert [(claim.url, site) for claim, site, _ in harness.failures] == [
        (hang, "lane_watchdog")]


@pytest.mark.asyncio
async def test_lane_watchdog_does_not_count_coordinated_human_wait():
    clock = FakeClock()
    urls = ["https://x.test/protected", "https://x.test/public"]
    harness = PoolHarness(urls, lane_count=2, clock=clock,
                          stall_seconds=100, check_seconds=0.005)
    active_handoff = asyncio.Event()
    release_handoff = asyncio.Event()
    public_started = asyncio.Event()

    async def process(claim, session, heartbeat):
        if claim.url.endswith("/protected"):
            active_handoff.set()
            await release_handoff.wait()
        else:
            public_started.set()
            await release_handoff.wait()
            heartbeat()

    pool = harness.pool(process_page=process, work_paused=active_handoff.is_set)
    running = asyncio.create_task(pool.run())
    try:
        await asyncio.wait_for(active_handoff.wait(), timeout=2)
        await asyncio.wait_for(public_started.wait(), timeout=2)
        clock.advance(8 * 60)
        pool.note_progress(1)
        await asyncio.sleep(0.03)
    finally:
        active_handoff.clear()
        release_handoff.set()
    result = await asyncio.wait_for(running, timeout=2)
    assert result.drained
    assert not result.retired_lanes
    assert not harness.failures


# ----------------------------------------------------------------
# T-P7: the aggregate is permutation-invariant. The three family
# numbers and the verdict table must not depend on absorption
# order; page_signals are compared as a multiset (their list order
# is absorption order by design, section 9.2 — disclosed, not
# smoothed over).
# ----------------------------------------------------------------

def _fixture_states():
    def state(url, viewport, elements, errors, signals):
        return {"url": url, "viewport": viewport, "elements": elements,
                "js_errors": errors, "page_signals": signals}

    return [
        state("https://x.test/a", "desktop1280",
              [{"verdict": "clean", "area": 10.0},
               {"verdict": "slop", "area": 4.0},
               {"verdict": "cant_tell", "area": 1.0}],
              [{"rule_id": "DEF_JS_CONSOLE_ERROR", "severity": "minor",
                "count": 2}],
              [{"rule_id": "UI_STATE_UNASSESSED", "severity": "info"}]),
        state("https://x.test/a", "mobile320",
              [{"verdict": "slop_minor", "area": 2.0},
               {"verdict": "clean", "area": 8.0}],
              [{"rule_id": "DEF_JS_CONSOLE_ERROR", "severity": "serious",
                "count": 1}],
              []),
        state("https://x.test/b", "desktop1280",
              [{"verdict": "clean", "area": 5.0},
               {"verdict": "clean", "area": 5.0},
               {"verdict": "slop", "area": 3.0},
               {"verdict": "clean", "area": 5.0},
               {"verdict": "clean", "area": 5.0},
               {"verdict": "clean", "area": 5.0},
               {"verdict": "clean", "area": 5.0},
               {"verdict": "clean", "area": 5.0},
               {"verdict": "clean", "area": 5.0},
               {"verdict": "clean", "area": 5.0}],
              [{"rule_id": "DEF_JS_UNCAUGHT", "severity": "serious",
                "count": 1}],
              [{"rule_id": "AUDIT_PARTIAL_COVERAGE", "severity": "info"}]),
        state("https://x.test/c", "mobile320",
              [{"verdict": "slop_minor", "area": 1.5},
               {"verdict": "cant_tell", "area": None}],
              [],
              [{"rule_id": "UI_VISUAL_UNASSESSED", "severity": "info"}]),
    ]


def test_t_p7_aggregate_is_permutation_invariant():
    from markettwin_shared.slop_aggregate import aggregate_run

    states = _fixture_states()
    baseline = aggregate_run([dict(state) for state in states])
    permutations = [
        list(reversed(states)),
        [states[2], states[0], states[3], states[1]],
        [states[1], states[3], states[0], states[2]],
    ]
    for permuted in permutations:
        result = aggregate_run([dict(state) for state in permuted])
        for family in ("slop", "defects", "effort"):
            expected = {key: value for key, value in
                        baseline[family].items() if key != "page_signals"}
            actual = {key: value for key, value in
                      result[family].items() if key != "page_signals"}
            assert actual == expected, family
        assert result["states_visited"] == baseline["states_visited"]
        signals = lambda out: sorted(
            json.dumps(signal, sort_keys=True)
            for signal in out["slop"]["page_signals"])
        assert signals(result) == signals(baseline)


# ----------------------------------------------------------------
# T-P8: the host circuit-breaker. 429/503 outcomes across lanes
# trip one shared breaker; claims pause for the backoff (doubling
# per consecutive trip); a success resets the doubling; affected
# pages are attempted-failed with reason rate_limited.
# ----------------------------------------------------------------

def test_t_p8_breaker_trips_pauses_and_resets():
    clock = FakeClock()
    breaker = HostCircuitBreaker(clock=clock)
    assert breaker.note_outcome(200) == 0
    assert breaker.note_outcome(429) == 0
    assert breaker.note_outcome(503) == 0
    assert breaker.note_outcome(429) == 30  # third in the window trips
    assert breaker.paused_remaining() == 30
    clock.advance(31)
    assert breaker.paused_remaining() == 0
    # A success resets the doubling: the next trip pauses 30, not 60.
    assert breaker.note_outcome(200) == 0
    clock.advance(61)  # let the counting window drain
    assert breaker.note_outcome(429) == 0
    assert breaker.note_outcome(429) == 0
    assert breaker.note_outcome(429) == 30
    # Without an intervening success the next trip doubles.
    clock.advance(31)
    assert breaker.note_outcome(503) == 0
    assert breaker.note_outcome(503) == 0
    assert breaker.note_outcome(503) == 60


@pytest.mark.asyncio
async def test_t_p8_pool_pauses_claims_while_breaker_is_open():
    clock = FakeClock()
    breaker = HostCircuitBreaker(clock=clock)
    urls = [f"https://x.test/p{i}" for i in range(5)]
    harness = PoolHarness(urls, lane_count=1, clock=clock, breaker=breaker)
    claim_times = []
    base_claim_next = harness.claim_next

    async def timed_claim_next(lane_id):
        claim = await base_claim_next(lane_id)
        if claim is not None:
            claim_times.append((claim.url, clock.now))
        return claim

    attempts = []

    async def process(claim, session, heartbeat):
        if len(attempts) < 3:
            attempts.append((claim.url, "rate_limited"))
            breaker.note_outcome(429)
        else:
            attempts.append((claim.url, "ok"))
            breaker.note_outcome(200)

    async def on_event(event_type, payload):
        harness.events.append((event_type, payload))
        clock.advance(31)  # time passes while claims are paused

    # Build directly: the harness pool() cannot override callbacks.
    async def factory(lane_index):
        return SimpleNamespace(handle=SimpleNamespace(session_id=uuid4()),
                               close=AsyncMock())

    pool = LanePool(
        lane_count=1, session_factory=factory, process_page=process,
        claim_next=timed_claim_next,
        work_remaining=harness.ledger.work_remaining,
        should_stop=lambda: False,
        complete_claim=harness.pool_kwargs["complete_claim"],
        fail_claim=harness.pool_kwargs["fail_claim"],
        release_claim=harness.pool_kwargs["release_claim"],
        breaker=breaker, on_event=on_event, clock=clock)
    result = await pool.run()
    assert result.drained
    pauses = [payload for event_type, payload in harness.events
              if event_type == "slop.rate_limit.pause"]
    assert len(pauses) == 1
    assert pauses[0]["pause_seconds"] == 30
    assert pauses[0]["reason"] == "rate_limited"
    # No claim was issued inside the pause window: the fourth claim
    # lands at or after trip time + the 30 s backoff.
    assert claim_times[3][1] >= claim_times[2][1] + 30
    assert [reason for _, reason in attempts[:3]] == ["rate_limited"] * 3
