"""Executor wiring with a scripted controller; no live browser or provider."""

import asyncio
import time
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from markettwin_database.models import TestRun
from markettwin_execution_orchestrator.browser import AllowedOrigin
from markettwin_execution_orchestrator.browser.errors import BrowserActionBlockedError, BrowserActionError
from markettwin_execution_orchestrator.workflow import slop_run


@pytest.fixture(autouse=True)
def _degenerate_lane_shape(monkeypatch):
    """Doc 18 section 8.6: the incumbent tests in this module pin
    the degenerate single-lane shape — their fake controllers have
    no lane factory and their assertions describe sequential
    execution exactly. The pooled shape is pinned in
    test_slop_pool.py and in the lane test below, which opts back
    in by setting LANE_COUNT itself."""
    monkeypatch.setattr(slop_run, "LANE_COUNT", 1)


def _patch_run_state(monkeypatch, completed):
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.persistence.run_state_repository.RunStateRepository",
        lambda _: SimpleNamespace(mark_running=AsyncMock(),
                                  mark_completed=completed))
    monkeypatch.setattr(slop_run, "ExecutionRepository", lambda _: SimpleNamespace(
        create_agent_execution=AsyncMock(), create_browser_session=AsyncMock(),
        mark_browser_session_closed=AsyncMock(), finish_agent_execution=AsyncMock()))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario", ["retirement", "lead_stop", "no_evidence", "restart", "owner_stop"],
)
async def test_desktop_lane_retirement_finalizes_committed_evidence(monkeypatch, scenario):
    monkeypatch.setattr(slop_run, "LANE_COUNT", 4)
    target = "https://app.test/"
    run = TestRun(id=uuid4(), status="running", configuration_snapshot={})
    request = SimpleNamespace(
        run_id=run.id, start_url=target, study_brief="Audit UI",
        allowed_origins=(AllowedOrigin("https", "app.test", None),), network_policy="public_only",
    )
    routes = [f"{target}route-{index}" for index in range(8)]
    controller = SimpleNamespace(
        open_room_session=AsyncMock(return_value=SimpleNamespace(session_id=uuid4())),
        create_worker_session=AsyncMock(side_effect=lambda **_: SimpleNamespace(session_id=uuid4())),
        sitemap_locations=AsyncMock(return_value=routes),
        close_room=AsyncMock(), close_session=AsyncMock(),
    )

    class Context:
        async def __aenter__(self):
            return controller

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(slop_run, "BrowserController", Context)
    monkeypatch.setattr(slop_run, "review_checkpoint", AsyncMock(return_value={
        "decision": "stop", "source": "fallback", "reason": "Lead review unavailable.",
    }))
    entry_saved = asyncio.Event()
    lanes_entered = asyncio.Event()
    stop_applied = asyncio.Event()
    failing_lanes = set()
    evidence_id = str(uuid4())

    async def inspect(*, absorber, controller, handle, claim, watched_browser=None):
        if claim.url == target and scenario != "no_evidence":
            state = {"url": target, "viewport": "desktop1280", "elements": [],
                     "page_signals": [], "js_errors": [], "screenshot_artifact_id": evidence_id}
            await absorber.absorb_inspected(slop_run._PageRecord(
                claim=claim, url=target, states=[state], links=[], entry_state=state, load_status=200,
            ))
            entry_saved.set()
            return
        if scenario != "no_evidence":
            await entry_saved.wait()
        failing_lanes.add(claim.claimed_by)
        if len(failing_lanes) == 4:
            lanes_entered.set()
        await lanes_entered.wait()
        if scenario == "lead_stop":
            if claim.claimed_by == 0:
                await absorber._process_checkpoint({}, page_ctx=None, kind="load_error")
                stop_applied.set()
            await stop_applied.wait()
        if scenario == "owner_stop" and claim.claimed_by == 0:
            run.configuration_snapshot = {
                **run.configuration_snapshot, "owner_stop": {"requested_at": "test"},
            }
        site = "private browser details" if scenario == "retirement" else "browser_action"
        raise slop_run.LaneDiedError(site) from RuntimeError("private browser details")

    monkeypatch.setattr(slop_run, "_inspect_page", inspect)
    stored = []
    pending = []

    async def create_event(**kwargs):
        pending.append(SimpleNamespace(**deepcopy(kwargs)))

    async def commit():
        stored.extend(pending)
        pending.clear()

    async def rollback():
        pending.clear()

    def collection():
        return next((event for event in stored if event.event_type == "run.collection"), None)

    async def scalar(query):
        if "run.collection" in query.compile().params.values():
            return collection()
        return None

    async def read_checkpoints(query):
        return SimpleNamespace(scalars=lambda: [
            event for event in stored if event.event_type == "slop.page.checkpoint"
        ])

    completed = AsyncMock()
    _patch_run_state(monkeypatch, completed)
    failed = AsyncMock()
    cancelled = AsyncMock()

    async def mark_completed(**kwargs):
        if scenario == "restart" and completed.await_count == 1:
            raise RuntimeError("injected publication failure")
        run.status = "completed"

    completed.side_effect = mark_completed
    monkeypatch.setattr(slop_run.run_state_repository, "RunStateRepository",
        lambda _: SimpleNamespace(
            mark_completed=completed, mark_failed=failed, mark_cancelled=cancelled,
        ))
    monkeypatch.setattr(slop_run, "RunEventRepository",
        lambda _: SimpleNamespace(create=create_event))
    session = Mock(
        get=AsyncMock(return_value=run), scalar=AsyncMock(side_effect=scalar),
        execute=AsyncMock(side_effect=read_checkpoints), add=Mock(), flush=AsyncMock(),
        commit=AsyncMock(side_effect=commit), rollback=AsyncMock(side_effect=rollback),
    )

    if scenario == "restart":
        with pytest.raises(slop_run.SlopFinalizationError) as error:
            await slop_run.execute_slop_run(request=request, session=session, desktop_scan=True)
        assert error.value.stage == "publication"
        await session.rollback()
        assert collection() is not None
        assert not any(event.event_type == "slop.state.result" for event in stored)
    await asyncio.wait_for(
        slop_run.execute_slop_run(request=request, session=session, desktop_scan=True), timeout=2,
    )
    controller.open_room_session.assert_awaited_once()
    coverage = collection().payload
    assert coverage["partial"]
    assert coverage["all_lanes_retired"]
    cause = "lane_died" if scenario == "retirement" else "browser_action"
    assert coverage["retired_lanes"] == [{"lane_id": lane_id, "cause": cause} for lane_id in range(4)]
    expected_stop_reason = {
        "lead_stop": "Lead review unavailable.",
        "owner_stop": "stopped by owner",
    }.get(scenario)
    assert coverage["stop_reason"] == expected_stop_reason
    assert coverage["pages_unverified"] == 4
    results = [event.payload for event in stored if event.event_type == "slop.state.result"]
    if scenario == "no_evidence":
        failed.assert_awaited_once()
        completed.assert_not_awaited()
        assert coverage["pages_recorded"] == 0
        assert coverage["pages_pending"] == 5
        assert not results
        failure = next(event for event in stored if event.event_type == "run.failed")
        assert failure.payload["code"] == "slop_lanes_exhausted"
    else:
        failed.assert_not_awaited()
        assert coverage["pages_recorded"] == 1
        assert coverage["pages_pending"] == 4
        assert len(results) == 5
        entry_artifacts = [
            state["screenshot_artifact_id"] for state in results if state["url"] == target
        ]
        assert entry_artifacts == [evidence_id]
        if scenario == "owner_stop":
            cancelled.assert_awaited_once()
            completed.assert_not_awaited()
            assert coverage["owner_stopped"]
        else:
            await slop_run.execute_slop_run(request=request, session=session, desktop_scan=True)
            assert sum(event.event_type == "run.collection" for event in stored) == 1
            assert sum(event.event_type == "slop.state.result" for event in stored) == len(results)
    assert "private browser details" not in repr(stored)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["navigation", "review", "zero", "restart"])
async def test_desktop_cutoff_keeps_observations_and_pending_claims(monkeypatch, stage):
    monkeypatch.setattr(slop_run, "DESKTOP_TARGET_SECONDS", 0.20)
    monkeypatch.setattr(slop_run, "DESKTOP_FINALIZATION_RESERVE_SECONDS", 0.05)
    target = "https://app.test/"
    later = f"{target}later"
    run_id = uuid4()
    run = TestRun(id=run_id, status="running", configuration_snapshot={})
    events = AsyncMock()
    measured = {"url": target, "viewport": "desktop1280", "elements": [],
                "page_signals": [], "js_errors": []}
    original_budget = None
    if stage == "restart":
        original_budget = {"worker_started_at": time.time() - 600,
                           "scan_cutoff_at": time.time() - 1,
                           "target_seconds": 600, "finalization_reserve_seconds": 45}
        run.configuration_snapshot = {
            "slop_desktop_budget": original_budget,
            "slop_checkpoint": {"visited": [target, later], "pending": [],
                                "in_flight": [{"url": later}], "discovery_finished": True},
        }
    saved_events = [SimpleNamespace(event_type="slop.page.checkpoint", payload={"states": [measured]})]
    session = Mock(
        get=AsyncMock(return_value=run), scalar=AsyncMock(return_value=None),
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: saved_events)),
        commit=AsyncMock(), add=Mock(), flush=AsyncMock(), rollback=AsyncMock(),
    )
    current = None

    async def navigate(**kwargs):
        nonlocal current
        current = kwargs["url"]
        if stage == "zero" or current == later:
            await asyncio.Event().wait()

    async def review(*args, **kwargs):
        if stage == "review":
            await asyncio.Event().wait()
        return []

    controller = SimpleNamespace(
        open_room_session=AsyncMock(return_value=SimpleNamespace(session_id=uuid4())),
        sitemap_locations=AsyncMock(return_value=[later]), navigate=AsyncMock(side_effect=navigate),
        wait=AsyncMock(), probe_page=AsyncMock(side_effect=lambda **_: {
            "url": current, "elements": [], "words": 52,
        }),
        harvest_js_records=AsyncMock(return_value=[]), page_links=AsyncMock(return_value=[later]),
        capture_evidence_screenshot=AsyncMock(return_value=""), close_room=AsyncMock(),
    )

    class Context:
        async def __aenter__(self):
            return controller

        async def __aexit__(self, *args):
            return False

    completed = AsyncMock(side_effect=lambda **_: setattr(run, "status", "completed"))
    failed = AsyncMock()
    _patch_run_state(monkeypatch, completed)
    monkeypatch.setattr(slop_run.run_state_repository, "RunStateRepository",
        lambda _: SimpleNamespace(mark_completed=completed, mark_failed=failed))
    monkeypatch.setattr(slop_run, "BrowserController", Context)
    monkeypatch.setattr(slop_run, "RunEventRepository", lambda _: SimpleNamespace(create=events))
    monkeypatch.setattr(slop_run, "review_screenshots", review)
    request = SimpleNamespace(
        run_id=run_id, start_url=target, study_brief="Audit UI",
        allowed_origins=(AllowedOrigin("https", "app.test", None),), network_policy="public_only",
    )
    await asyncio.wait_for(
        slop_run.execute_slop_run(request=request, session=session, desktop_scan=True), timeout=2,
    )
    payloads = [(call.kwargs["event_type"], call.kwargs["payload"])
                for call in events.await_args_list]
    [coverage] = [payload for kind, payload in payloads if kind == "run.collection"]
    assert coverage["partial"] and coverage["budget_exhausted"]
    assert coverage["stop_reason"] == slop_run.DESKTOP_BUDGET_STOP_REASON
    assert not coverage["retired_lanes"]
    assert coverage["pages_unverified"] == 0
    assert set(coverage["pending_urls"]) == ({target, later} if stage == "zero" else {later})
    assert coverage["pages_recorded"] == (0 if stage == "zero" else 1)
    assert coverage["visual_reviews_unfinished"] == int(stage == "review")
    assert run.configuration_snapshot["slop_checkpoint"]["in_flight"] == []
    if stage == "zero":
        failed.assert_awaited_once_with(test_run_id=run_id)
        assert ("run.failed", {
            "code": "slop_budget_without_evidence",
            "message": "The desktop scan reached its time budget before recording a usable measurement.",
        }) in payloads
    else:
        completed.assert_awaited_once_with(test_run_id=run_id)
        assert [payload["url"] for kind, payload in payloads if kind == "slop.state.result"] == [target]
    if stage == "restart":
        assert coverage["desktop_budget"]["scan_cutoff_at"] == original_budget["scan_cutoff_at"]
        controller.navigate.assert_not_awaited()
        controller.sitemap_locations.assert_not_awaited()
        await slop_run.execute_slop_run(request=request, session=session, desktop_scan=True)
        controller.open_room_session.assert_awaited_once()
        assert run.configuration_snapshot["slop_checkpoint"]["pending"] == [later]


@pytest.mark.asyncio
async def test_desktop_cutoff_does_not_cancel_human_control():
    budget = slop_run._DesktopScanBudget(time.time() + 0.02)

    async def human_control():
        with budget.human_wait():
            await asyncio.sleep(0.04)
            assert budget.reached()

    await budget.wait(human_control())
    assert budget.human_wait_seconds >= 0.04
    with pytest.raises(slop_run.SlopBudgetReached):
        await budget.wait(asyncio.sleep(0))


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "desktop_scan", "policy", "control", "sitemap", "resume", "interrupted", "navigation"])
async def test_audit_measures_viewports_and_discovers_unlinked_sitemap_page(monkeypatch, failure):
    blocked = failure == "policy"
    run_id = uuid4()
    handle = SimpleNamespace(session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4())
    current = {"url": "https://app.test/"}

    async def navigate(**kwargs):
        if failure == "navigation" and kwargs["url"] == "https://app.test/unlinked":
            raise BrowserActionError("Page failed", reason_code="navigation_failed")
        current["url"] = kwargs["url"]

    async def probe(**kwargs):
        return {"url": current["url"], "elements": [], "words": 50}

    controller = SimpleNamespace(
        open_room_session=AsyncMock(return_value=handle), navigate=AsyncMock(side_effect=navigate),
        wait=AsyncMock(), probe_page=AsyncMock(side_effect=probe), set_viewport=AsyncMock(),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=[]),
        ui_state_targets=AsyncMock(return_value=[{"role": "tab", "name": "Details"}]
                                  if failure in {"policy", "control"} else []),
        click=AsyncMock(side_effect=BrowserActionBlockedError("Blocked") if blocked else
                       BrowserActionError("Ambiguous menu", reason_code="ambiguous_target")
                       if failure else None),
        sitemap_locations=AsyncMock(return_value=["https://app.test/unlinked"]),
        harvest_js_records=AsyncMock(return_value=[]), close_room=AsyncMock(),
    )

    class Context:
        async def __aenter__(self):
            return controller

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(slop_run, "BrowserController", Context)
    monkeypatch.setattr(slop_run, "review_screenshots", AsyncMock(return_value=[]))
    monkeypatch.setattr(slop_run, "review_checkpoint", AsyncMock(
        return_value={"decision": "continue", "reason": "Progress is useful"}))
    if failure == "sitemap":
        async def locations(**kwargs):
            return [f"https://app.test/map{controller.sitemap_locations.await_count}.xml"]
        controller.sitemap_locations.side_effect = locations
        monkeypatch.setattr(slop_run, "review_checkpoint", AsyncMock(
            return_value={"decision": "stop", "reason": "Stop sitemap loop"}))
    completed = AsyncMock()
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.persistence.run_state_repository.RunStateRepository",
        lambda _: SimpleNamespace(mark_running=AsyncMock(), mark_completed=completed))
    monkeypatch.setattr(slop_run, "ExecutionRepository", lambda _: SimpleNamespace(
        create_agent_execution=AsyncMock(), create_browser_session=AsyncMock(),
        mark_browser_session_closed=AsyncMock(), finish_agent_execution=AsyncMock()))
    events = AsyncMock()
    monkeypatch.setattr(slop_run, "RunEventRepository", lambda _: SimpleNamespace(create=events))
    session = Mock(get=AsyncMock(return_value=TestRun(id=run_id, configuration_snapshot={})),
        scalar=AsyncMock(return_value=None),
        flush=AsyncMock(), commit=AsyncMock(), add=Mock())
    if failure in {"resume", "interrupted"}:
        session.get.return_value.status = "running"
        session.get.return_value.configuration_snapshot = {"slop_attempt": 1,
            "slop_checkpoint": {"visited": ["https://app.test/"],
                "pending": ["https://app.test/unlinked"],
                "active_url": "https://app.test/uncertain" if failure == "interrupted" else None}}
        old_states = [{"url": "https://app.test/", "viewport": viewport,
            "elements": [], "page_signals": [], "js_errors": []}
            for viewport in ("desktop1280", "mobile320")]
        saved_events = [SimpleNamespace(event_type="slop.page.checkpoint",
                                       payload={"states": old_states})]
        if failure == "interrupted":
            saved_events.append(SimpleNamespace(event_type="slop.page.inspected", payload={
                "url": "https://app.test/uncertain",
                "pending_urls": ["https://app.test/unlinked", "https://app.test/found"]}))
        session.execute = AsyncMock(return_value=SimpleNamespace(scalars=lambda: saved_events))
    request = SimpleNamespace(run_id=run_id, start_url="https://app.test/", study_brief="Audit UI",
        allowed_origins=(AllowedOrigin("https", "app.test", None),), network_policy="public_only")
    desktop_scan = failure == "desktop_scan"
    if desktop_scan:
        async def discover_after_entry_starts(**kwargs):
            await entry_started.wait()
            return ["https://app.test/unlinked"]

        entry_started = asyncio.Event()

        async def navigate_and_signal(**kwargs):
            await navigate(**kwargs)
            entry_started.set()

        controller.navigate.side_effect = navigate_and_signal
        controller.sitemap_locations.side_effect = discover_after_entry_starts
    await slop_run.execute_slop_run(request=request, session=session, desktop_scan=desktop_scan)
    if desktop_scan:
        assert controller.navigate.await_count == 2
        controller.set_viewport.assert_not_awaited()
        controller.ui_state_targets.assert_not_awaited()
        assert all(len(call.args[0]) == 1 for call in slop_run.review_screenshots.await_args_list)
        snapshot = session.get.return_value.configuration_snapshot["slop_checkpoint"]
        assert snapshot["discovery_sources"]["https://app.test/unlinked"] == "https://app.test/sitemap.xml"

    assert all(not call.kwargs["url"].endswith(".xml") for call in controller.navigate.await_args_list)
    for call in slop_run.review_checkpoint.await_args_list:
        assert call.kwargs["objective"] == request.study_brief
    states = [call.kwargs["payload"] for call in events.await_args_list
              if call.kwargs["event_type"] == "slop.state.result"]
    urls = {"https://app.test/"}
    if not blocked and failure not in {"sitemap", "navigation"}:
        urls.add("https://app.test/unlinked")
    expected = {(url, "desktop1280") for url in urls}
    if failure in {"resume", "interrupted"}:
        expected.add(("https://app.test/", "mobile320"))  # Historical evidence.
    if failure == "interrupted":
        expected.update({("https://app.test/found", "desktop1280"), ("https://app.test/uncertain", None)})
    if failure == "navigation":
        expected.add(("https://app.test/unlinked", None))
    assert {(state["url"], state.get("viewport")) for state in states} == expected
    if blocked:
        # Harvest-first: the sitemap is consulted once during seeding,
        # before the policy stop ends the run on the first page.
        controller.sitemap_locations.assert_awaited_once()
    if failure in {"policy", "control", "sitemap", "navigation"}:
        assert any(signal["rule_id"] == "AUDIT_PARTIAL_COVERAGE"
                   for state in states for signal in state["page_signals"])
    if failure == "sitemap":
        assert controller.sitemap_locations.await_count == 5
    if blocked:
        assert any(signal["rule_id"] == "UI_STATE_UNASSESSED"
                   for state in states for signal in state["page_signals"])
    if failure == "control":
        assert any("ambiguous_target" in signal["detail"]
                   for state in states for signal in state["page_signals"])
        assert any(call.kwargs["url"] == "https://app.test/unlinked"
                   for call in controller.navigate.await_args_list)
        progress = [call.kwargs["payload"] for call in events.await_args_list
                    if call.kwargs["event_type"] == "slop.state.progress"]
        assert progress and all("ambiguous_target" in entry["result"] for entry in progress)
    if not blocked and not desktop_scan:
        assert any(call.kwargs["event_type"] == "lead.checkpoint"
                   for call in events.await_args_list)
    completed.assert_awaited_once()
    collection = [call.kwargs["payload"] for call in events.await_args_list
                  if call.kwargs["event_type"] == "run.collection"]
    assert len(collection) == 1
    assert collection[0]["states_recorded"] == len(states)
    if desktop_scan:
        performance = collection[0]["desktop_performance"]
        for phase in ("navigation", "settle", "dom_probe", "measurement", "inspection_commit"):
            assert performance["phases"][phase]["count"] == 2
            assert performance["phases"][phase]["total_ms"] >= 0
        assert performance["checkpoint_writes"] >= 2
        assert performance["checkpoint_samples"] == 1
        assert performance["checkpoint_max_sample_bytes"] > 0
    controller.close_room.assert_awaited_once()
    if failure in {"resume", "interrupted"}:
        assert all(call.kwargs["url"] != "https://app.test/"
                   for call in controller.navigate.await_args_list)
        assert session.add.call_args.args[0].ordinal == 2
    if failure == "interrupted":
        assert all(call.kwargs["url"] != "https://app.test/uncertain"
                   for call in controller.navigate.await_args_list)
        assert any("not replayed" in signal["detail"]
                   for state in states for signal in state["page_signals"])


@pytest.mark.asyncio
async def test_menu_toggles_mint_no_states_and_queue_reaches_second_page(monkeypatch):
    """MT-000147 regression, end to end: page 1's nav menu (five items,
    mirroring the live glean.com run) must mint zero states, the Lead
    checkpoint must carry true crawl facts, and the linked second page
    must actually be visited."""
    run_id = uuid4()
    handle = SimpleNamespace(session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4())
    current = {"url": "https://app.test/"}
    menu = {"open": False}
    menu_items = ["Healthcare", "Retail", "Technology", "Industrials", "Consulting"]

    def el(kind, tag, role, name, region, **extra):
        element = {"kind": kind, "tag": tag, "role": role, "name": name, "region": region,
                   "disabled": False, "selected": None, "expanded": None, "invalid": None,
                   "text": name if kind == "text" else ""}
        element.update(extra)
        return element

    async def navigate(**kwargs):
        current["url"] = kwargs["url"]
        menu["open"] = False

    async def probe(**kwargs):
        if current["url"] != "https://app.test/":
            return {"url": current["url"], "words": 60, "elements": [
                el("text", "h1", "h1", "Second page", "main")]}
        elements = [el("interactive", "button", "button", "Industries", "nav",
                       expanded="true" if menu["open"] else "false"),
                    el("text", "h1", "h1", "Home", "main")]
        if menu["open"]:
            elements += [el("interactive", "a", "menuitem", name, "nav")
                         for name in menu_items]
        return {"url": current["url"], "words": 60, "elements": elements}

    async def targets(**kwargs):
        if current["url"] != "https://app.test/":
            return []
        found = [{"role": "button", "name": "Industries"}]
        if menu["open"]:
            found += [{"role": "menuitem", "name": name} for name in menu_items]
        return found

    async def click(**kwargs):
        if kwargs["name"] == "Industries":
            menu["open"] = True

    async def page_links(**kwargs):
        return ["https://app.test/second"] if current["url"] == "https://app.test/" else []

    controller = SimpleNamespace(
        open_room_session=AsyncMock(return_value=handle), navigate=AsyncMock(side_effect=navigate),
        wait=AsyncMock(), probe_page=AsyncMock(side_effect=probe), set_viewport=AsyncMock(),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(side_effect=page_links),
        ui_state_targets=AsyncMock(side_effect=targets), click=AsyncMock(side_effect=click),
        sitemap_locations=AsyncMock(return_value=[]),
        harvest_js_records=AsyncMock(return_value=[]), close_room=AsyncMock(),
    )

    class Context:
        async def __aenter__(self):
            return controller

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(slop_run, "BrowserController", Context)
    monkeypatch.setattr(slop_run, "review_screenshots", AsyncMock(return_value=[]))
    monkeypatch.setattr(slop_run, "review_checkpoint", AsyncMock(
        return_value={"decision": "continue", "reason": "Progress is useful"}))
    completed = AsyncMock()
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.persistence.run_state_repository.RunStateRepository",
        lambda _: SimpleNamespace(mark_running=AsyncMock(), mark_completed=completed))
    monkeypatch.setattr(slop_run, "ExecutionRepository", lambda _: SimpleNamespace(
        create_agent_execution=AsyncMock(), create_browser_session=AsyncMock(),
        mark_browser_session_closed=AsyncMock(), finish_agent_execution=AsyncMock()))
    events = AsyncMock()
    monkeypatch.setattr(slop_run, "RunEventRepository", lambda _: SimpleNamespace(create=events))
    session = Mock(get=AsyncMock(return_value=TestRun(id=run_id, configuration_snapshot={})),
        scalar=AsyncMock(return_value=None),
        flush=AsyncMock(), commit=AsyncMock(), add=Mock())
    request = SimpleNamespace(run_id=run_id, start_url="https://app.test/", study_brief="Audit UI",
        allowed_origins=(AllowedOrigin("https", "app.test", None),), network_policy="public_only")
    await slop_run.execute_slop_run(request=request, session=session)

    started = [call.kwargs["payload"]["url"] for call in events.await_args_list
               if call.kwargs["event_type"] == "slop.page.started"]
    assert started == ["https://app.test/", "https://app.test/second"]
    states = [call.kwargs["payload"] for call in events.await_args_list
              if call.kwargs["event_type"] == "slop.state.result"]
    assert len(states) == 2  # two desktop pages; zero traversal states
    assert all(state.get("interaction_path") is None for state in states)
    progress = [call.kwargs["payload"] for call in events.await_args_list
                if call.kwargs["event_type"] == "slop.state.progress"]
    assert len(progress) == 6  # desktop toggle and five menu items
    assert all(entry["result"] == "duplicate_state" for entry in progress)
    assert all(entry["actual_url"] == "https://app.test/" for entry in progress)
    # Six paths per viewport stay under the 15-path Lead checkpoint
    # cadence, so no traversal checkpoint fires on this crawl; the
    # page-end reviews below carry the true crawl facts instead.
    page_reviews = [call.kwargs["evidence"] for call in slop_run.review_checkpoint.await_args_list
                    if "visited_urls" in call.kwargs.get("evidence", {})]
    assert page_reviews
    assert len(page_reviews[-1]["visited_urls"]) == 2
    assert page_reviews[-1]["pending_urls"] == []
    completed.assert_awaited_once()
    collection = [call.kwargs["payload"] for call in events.await_args_list
                  if call.kwargs["event_type"] == "run.collection"]
    assert len(collection) == 1
    assert collection[0]["pages_pending"] == 0
    assert collection[0]["paths_activated"] == 6
    assert collection[0]["paths_not_assessed"] == 0


async def test_stagnating_traversal_is_stopped_by_the_gate(monkeypatch):
    """Issue 2: a traversal that keeps generating paths but produces no
    new states and no new routes (the MT-000147 shape, generalised) is
    stopped by the harness gate — the Lead is consulted with stagnation
    flagged, and when nothing changes the gate stops the run itself.
    The run ends partial, not failed."""
    run_id = uuid4()
    handle = SimpleNamespace(session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4())
    spawned = {"count": 1}

    def el(kind, tag, role, name, region, **extra):
        element = {"kind": kind, "tag": tag, "role": role, "name": name, "region": region,
                   "disabled": False, "selected": None, "expanded": None, "invalid": None,
                   "text": name if kind == "text" else ""}
        element.update(extra)
        return element

    async def probe(**kwargs):
        return {"url": "https://app.test/", "words": 40, "elements": [
            el("text", "h1", "h1", "Home", "main")]}

    async def targets(**kwargs):
        found = [{"role": "button", "name": f"Spawn {i}"} for i in range(spawned["count"])]
        spawned["count"] += 1
        return found

    controller = SimpleNamespace(
        open_room_session=AsyncMock(return_value=handle), navigate=AsyncMock(),
        wait=AsyncMock(), probe_page=AsyncMock(side_effect=probe), set_viewport=AsyncMock(),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=[]),
        ui_state_targets=AsyncMock(side_effect=targets), click=AsyncMock(),
        sitemap_locations=AsyncMock(return_value=[]),
        harvest_js_records=AsyncMock(return_value=[]), close_room=AsyncMock(),
    )

    class Context:
        async def __aenter__(self):
            return controller

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(slop_run, "BrowserController", Context)
    monkeypatch.setattr(slop_run, "review_screenshots", AsyncMock(return_value=[]))
    monkeypatch.setattr(slop_run, "review_checkpoint", AsyncMock(
        return_value={"decision": "continue", "reason": "Keep going", "source": "lead"}))
    completed = AsyncMock()
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.persistence.run_state_repository.RunStateRepository",
        lambda _: SimpleNamespace(mark_running=AsyncMock(), mark_completed=completed))
    monkeypatch.setattr(slop_run, "ExecutionRepository", lambda _: SimpleNamespace(
        create_agent_execution=AsyncMock(), create_browser_session=AsyncMock(),
        mark_browser_session_closed=AsyncMock(), finish_agent_execution=AsyncMock()))
    events = AsyncMock()
    monkeypatch.setattr(slop_run, "RunEventRepository", lambda _: SimpleNamespace(create=events))
    session = Mock(get=AsyncMock(return_value=TestRun(id=run_id, configuration_snapshot={})),
        scalar=AsyncMock(return_value=None),
        flush=AsyncMock(), commit=AsyncMock(), add=Mock())
    request = SimpleNamespace(run_id=run_id, start_url="https://app.test/", study_brief="Audit UI",
        allowed_origins=(AllowedOrigin("https", "app.test", None),), network_policy="public_only")
    await slop_run.execute_slop_run(request=request, session=session)

    # The Lead was consulted for the first three checkpoints; the fourth
    # was stopped by the gate without a model call. The third consultation
    # carried the stagnation flag.
    assert slop_run.review_checkpoint.await_count == 3
    third = slop_run.review_checkpoint.await_args_list[2].kwargs["evidence"]
    assert third["stagnation"] is True
    gate_events = [call.kwargs["payload"] for call in events.await_args_list
                   if call.kwargs["event_type"] == "lead.checkpoint"
                   and call.kwargs["payload"].get("source") == "stagnation_gate"]
    assert len(gate_events) == 1
    assert gate_events[0]["decision"] == "stop"
    progress = [call.kwargs["payload"] for call in events.await_args_list
                if call.kwargs["event_type"] == "slop.state.progress"]
    assert 0 < len(progress) < 75  # bounded: the gate fired, no endless crawl
    completed.assert_awaited_once()
def _guard_fixture(monkeypatch, *, extra_links):
    """A spawning-duplicate crawl (the stagnation fixture's shape) whose
    Lead stops every traversal checkpoint. Returns (events, completed)."""
    run_id = uuid4()
    handle = SimpleNamespace(session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4())
    spawned = {"count": 1}

    async def probe(**kwargs):
        return {"url": "https://app.test/", "words": 40, "elements": [
            {"kind": "text", "tag": "h1", "role": "h1", "name": "Home", "region": "main",
             "disabled": False, "selected": None, "expanded": None, "invalid": None,
             "text": "Home"}]}

    async def targets(**kwargs):
        found = [{"role": "button", "name": f"Spawn {i}"} for i in range(spawned["count"])]
        spawned["count"] += 1
        return found

    controller = SimpleNamespace(
        open_room_session=AsyncMock(return_value=handle), navigate=AsyncMock(),
        wait=AsyncMock(), probe_page=AsyncMock(side_effect=probe), set_viewport=AsyncMock(),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=list(extra_links)),
        ui_state_targets=AsyncMock(side_effect=targets), click=AsyncMock(),
        sitemap_locations=AsyncMock(return_value=[]),
        harvest_js_records=AsyncMock(return_value=[]), close_room=AsyncMock(),
    )

    class Context:
        async def __aenter__(self):
            return controller

        async def __aexit__(self, *args):
            return False

    async def review(**kwargs):
        if "checked_items" in kwargs["evidence"]:
            return {"decision": "stop", "reason": "Lead calls a stop", "source": "lead"}
        return {"decision": "continue", "reason": "Progress is useful", "source": "lead"}

    monkeypatch.setattr(slop_run, "BrowserController", Context)
    monkeypatch.setattr(slop_run, "review_screenshots", AsyncMock(return_value=[]))
    monkeypatch.setattr(slop_run, "review_checkpoint", AsyncMock(side_effect=review))
    completed = AsyncMock()
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.persistence.run_state_repository.RunStateRepository",
        lambda _: SimpleNamespace(mark_running=AsyncMock(), mark_completed=completed))
    monkeypatch.setattr(slop_run, "ExecutionRepository", lambda _: SimpleNamespace(
        create_agent_execution=AsyncMock(), create_browser_session=AsyncMock(),
        mark_browser_session_closed=AsyncMock(), finish_agent_execution=AsyncMock()))
    events = AsyncMock()
    monkeypatch.setattr(slop_run, "RunEventRepository", lambda _: SimpleNamespace(create=events))
    session = Mock(get=AsyncMock(return_value=TestRun(id=run_id, configuration_snapshot={})),
        scalar=AsyncMock(return_value=None),
        flush=AsyncMock(), commit=AsyncMock(), add=Mock())
    request = SimpleNamespace(run_id=run_id, start_url="https://app.test/", study_brief="Audit UI",
        allowed_origins=(AllowedOrigin("https", "app.test", None),), network_policy="public_only")
    return events, completed, session, request


@pytest.mark.asyncio
async def test_lead_stop_does_not_end_crawl_with_large_pending_queue(monkeypatch):
    """Spec 10 queue guard (the MT-000149 lesson): a Lead stop is
    recorded but not applied while more than ten discovered pages
    remain uninspected; the crawl moves on to the next page."""
    links = [f"https://app.test/link{i}" for i in range(1, 13)]
    events, completed, session, request = _guard_fixture(monkeypatch, extra_links=links)
    await slop_run.execute_slop_run(request=request, session=session)
    started = [call.kwargs["payload"]["url"] for call in events.await_args_list
               if call.kwargs["event_type"] == "slop.page.started"]
    assert started[0] == "https://app.test/"
    assert "https://app.test/link1" in started
    states = [call.kwargs["payload"] for call in events.await_args_list
              if call.kwargs["event_type"] == "slop.state.result"]
    assert any(signal["rule_id"] == "AUDIT_LEAD_STOP_OVERRULED"
               for state in states for signal in state["page_signals"])
    completed.assert_awaited_once()


@pytest.mark.asyncio
async def test_lead_stop_stands_when_pending_queue_is_small(monkeypatch):
    """The same Lead stop ends the crawl when the pending queue is at
    or below the guard threshold."""
    events, completed, session, request = _guard_fixture(monkeypatch, extra_links=[])
    await slop_run.execute_slop_run(request=request, session=session)
    started = [call.kwargs["payload"]["url"] for call in events.await_args_list
               if call.kwargs["event_type"] == "slop.page.started"]
    assert started == ["https://app.test/"]
    states = [call.kwargs["payload"] for call in events.await_args_list
              if call.kwargs["event_type"] == "slop.state.result"]
    assert not any(signal["rule_id"] == "AUDIT_LEAD_STOP_OVERRULED"
                   for state in states for signal in state["page_signals"])
    assert any(signal["rule_id"] == "AUDIT_PARTIAL_COVERAGE"
               for state in states for signal in state["page_signals"])
    completed.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("with_map", [False, True])
async def test_lead_objective_is_the_study_brief_at_both_checkpoint_sites(monkeypatch, with_map):
    """T-L1 (Phase 1a section 10.5): both review_checkpoint call sites
    — the in-traversal checkpoint (its evidence carries checked_items)
    and the page-end review (its evidence carries visited_urls) —
    receive the run's study brief as their objective, with and without
    an application map on the request. Page one has no traversal
    targets, so it ends in a page-end review; page two's spawning
    targets drive traversal checkpoints."""
    run_id = uuid4()
    handle = SimpleNamespace(session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4())
    current = {"url": "https://app.test/"}
    spawned = {"count": 1}

    async def navigate(**kwargs):
        current["url"] = kwargs["url"]

    async def probe(**kwargs):
        return {"url": current["url"], "words": 40, "elements": [
            {"kind": "text", "tag": "h1", "role": "h1", "name": "Home", "region": "main",
             "disabled": False, "selected": None, "expanded": None, "invalid": None,
             "text": "Home"}]}

    async def targets(**kwargs):
        if current["url"] != "https://app.test/second":
            return []
        found = [{"role": "button", "name": f"Spawn {i}"} for i in range(spawned["count"])]
        spawned["count"] += 1
        return found

    async def page_links(**kwargs):
        return ["https://app.test/second"] if current["url"] == "https://app.test/" else []

    controller = SimpleNamespace(
        open_room_session=AsyncMock(return_value=handle), navigate=AsyncMock(side_effect=navigate),
        wait=AsyncMock(), probe_page=AsyncMock(side_effect=probe), set_viewport=AsyncMock(),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(side_effect=page_links),
        ui_state_targets=AsyncMock(side_effect=targets), click=AsyncMock(),
        sitemap_locations=AsyncMock(return_value=[]),
        harvest_js_records=AsyncMock(return_value=[]), close_room=AsyncMock(),
    )

    class Context:
        async def __aenter__(self):
            return controller

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(slop_run, "BrowserController", Context)
    monkeypatch.setattr(slop_run, "review_screenshots", AsyncMock(return_value=[]))
    monkeypatch.setattr(slop_run, "review_checkpoint", AsyncMock(
        return_value={"decision": "continue", "reason": "Progress is useful"}))
    completed = AsyncMock()
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.persistence.run_state_repository.RunStateRepository",
        lambda _: SimpleNamespace(mark_running=AsyncMock(), mark_completed=completed))
    monkeypatch.setattr(slop_run, "ExecutionRepository", lambda _: SimpleNamespace(
        create_agent_execution=AsyncMock(), create_browser_session=AsyncMock(),
        mark_browser_session_closed=AsyncMock(), finish_agent_execution=AsyncMock()))
    events = AsyncMock()
    monkeypatch.setattr(slop_run, "RunEventRepository", lambda _: SimpleNamespace(create=events))
    session = Mock(get=AsyncMock(return_value=TestRun(id=run_id, configuration_snapshot={})),
        scalar=AsyncMock(return_value=None),
        flush=AsyncMock(), commit=AsyncMock(), add=Mock())
    request = SimpleNamespace(run_id=run_id, start_url="https://app.test/", study_brief="Audit UI",
        allowed_origins=(AllowedOrigin("https", "app.test", None),), network_policy="public_only",
        app_map=({"map_id": "map-1", "version_number": 1, "routes": ["https://app.test/"],
                  "pages": [], "counts": {"expected": 0, "reachable": 0, "blocked_auth": 0,
                                          "blocked_wall": 0, "gone": 0}}
                 if with_map else None))
    await slop_run.execute_slop_run(request=request, session=session)

    calls = slop_run.review_checkpoint.await_args_list
    traversal = [call for call in calls if "checked_items" in call.kwargs["evidence"]]
    page_end = [call for call in calls if "visited_urls" in call.kwargs["evidence"]]
    assert traversal, "the traversal checkpoint site never fired"
    assert page_end, "the page-end review site never fired"
    assert all(call.kwargs["objective"] == request.study_brief for call in traversal)
    assert all(call.kwargs["objective"] == request.study_brief for call in page_end)
    completed.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [True, False])
async def test_interrupted_crawl_rolls_back_before_closing(monkeypatch, cancel):
    """MT-000151 regression (F5): the worker cancels the crawl task
    after the browser dies (host sleep); the Room close then awaits a
    dead driver forever. The cancellation must still reach the run's
    terminal bookkeeping — the execution finishes as failed and the
    CancelledError propagates to the worker, whose handler emits
    run.failed — instead of wedging in the executor's finally."""
    monkeypatch.setattr(slop_run, "TEARDOWN_TIMEOUT_SECONDS", 0.2)
    run_id = uuid4()
    handle = SimpleNamespace(session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4())
    probe_entered = asyncio.Event()
    close_attempted = asyncio.Event()

    async def probe(**kwargs):
        probe_entered.set()
        if cancel:
            await asyncio.Event().wait()  # the visit never answers
        return {"url": "https://app.test/", "elements": [], "words": 50}

    async def close_room(**kwargs):
        close_attempted.set()
        await asyncio.Event().wait()  # the dead driver never answers

    controller = SimpleNamespace(
        open_room_session=AsyncMock(return_value=handle), navigate=AsyncMock(),
        wait=AsyncMock(), probe_page=AsyncMock(side_effect=probe),
        set_viewport=AsyncMock(),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=[]),
        ui_state_targets=AsyncMock(return_value=[]),
        click=AsyncMock(),
        sitemap_locations=AsyncMock(return_value=[]),
        harvest_js_records=AsyncMock(return_value=[]),
        close_room=AsyncMock(side_effect=close_room),
    )

    class Context:
        async def __aenter__(self):
            return controller

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(slop_run, "BrowserController", Context)
    monkeypatch.setattr(slop_run, "review_screenshots", AsyncMock(return_value=[]))
    monkeypatch.setattr(slop_run, "review_checkpoint", AsyncMock(
        return_value={"decision": "continue", "reason": "Progress is useful"}))
    completed = AsyncMock()
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.persistence.run_state_repository.RunStateRepository",
        lambda _: SimpleNamespace(mark_running=AsyncMock(), mark_completed=completed))
    finish = AsyncMock()
    rollback = AsyncMock()

    async def mark_closed(**kwargs):
        rollback.assert_awaited_once()

    monkeypatch.setattr(slop_run, "ExecutionRepository", lambda _: SimpleNamespace(
        create_agent_execution=AsyncMock(), create_browser_session=AsyncMock(),
        mark_browser_session_closed=AsyncMock(side_effect=mark_closed), finish_agent_execution=finish))
    events = AsyncMock()
    original = RuntimeError("Database write failed during collection")

    async def persist_event(**kwargs):
        if not cancel and kwargs["event_type"] == "run.collection":
            raise original

    events.side_effect = persist_event
    monkeypatch.setattr(slop_run, "RunEventRepository", lambda _: SimpleNamespace(create=events))
    session = Mock(get=AsyncMock(return_value=TestRun(id=run_id, configuration_snapshot={})),
        scalar=AsyncMock(return_value=None),
        flush=AsyncMock(), commit=AsyncMock(), rollback=rollback, add=Mock())
    request = SimpleNamespace(run_id=run_id, start_url="https://app.test/",
        study_brief="Audit UI",
        allowed_origins=(AllowedOrigin("https", "app.test", None),),
        network_policy="public_only")
    task = asyncio.create_task(slop_run.execute_slop_run(request=request, session=session))
    await asyncio.wait_for(probe_entered.wait(), timeout=5)
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError) as error:
        await asyncio.wait_for(task, timeout=10)
    if not cancel:
        assert error.value is original
    assert close_attempted.is_set()
    finish.assert_awaited_once()
    assert finish.await_args.kwargs["status"] == "failed"
    completed.assert_not_awaited()


@pytest.mark.asyncio
async def test_page_model_call_inventory_after_s0_batching(monkeypatch):
    """T-V3 (doc 18 sections 13/15): one page with five traversal states
    per viewport costs exactly the surviving inventory — one entry review,
    one batched review per viewport, one page-end checkpoint — and the
    batch findings land only on each viewport's batch leader."""
    from markettwin_execution_orchestrator.slop import interactions as interactions_module

    run_id = uuid4()
    handle = SimpleNamespace(session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4())
    clicks = {"count": 0}

    async def navigate(**kwargs):
        clicks["count"] = 0

    async def probe(**kwargs):
        growth = min(clicks["count"], 5)
        return {"url": "https://app.test/", "words": 50, "elements": [
            {"kind": "interactive", "tag": "button", "role": "button",
             "name": f"Section {i}", "region": "main", "disabled": False,
             "selected": None, "expanded": None, "invalid": None}
            for i in range(growth + 1)]}

    async def targets(**kwargs):
        growth = min(clicks["count"], 5)
        return [{"role": "button", "name": f"Section {i}"} for i in range(growth + 1)]

    async def click(**kwargs):
        clicks["count"] += 1

    controller = SimpleNamespace(
        open_room_session=AsyncMock(return_value=handle), navigate=AsyncMock(side_effect=navigate),
        wait=AsyncMock(), probe_page=AsyncMock(side_effect=probe), set_viewport=AsyncMock(),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=[]),
        ui_state_targets=AsyncMock(side_effect=targets), click=AsyncMock(side_effect=click),
        sitemap_locations=AsyncMock(return_value=[]),
        harvest_js_records=AsyncMock(return_value=[]), close_room=AsyncMock(),
    )

    class Context:
        async def __aenter__(self):
            return controller

        async def __aexit__(self, *args):
            return False

    review_calls = []

    async def review(states, **kwargs):
        review_calls.append([state.get("interaction_path") for state in states])
        if any(state.get("interaction_path") for state in states):
            return [{"rule_id": "UI_VISUAL_REVIEW", "severity": "minor",
                     "detail": "stub finding"}]
        return []

    checkpoint = AsyncMock(return_value={"decision": "continue", "reason": "Progress is useful"})
    monkeypatch.setattr(slop_run, "BrowserController", Context)
    monkeypatch.setattr(slop_run, "review_screenshots", review)
    monkeypatch.setattr(interactions_module, "review_screenshots", review)
    monkeypatch.setattr(slop_run, "review_checkpoint", checkpoint)
    completed = AsyncMock()
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.persistence.run_state_repository.RunStateRepository",
        lambda _: SimpleNamespace(mark_running=AsyncMock(), mark_completed=completed))
    monkeypatch.setattr(slop_run, "ExecutionRepository", lambda _: SimpleNamespace(
        create_agent_execution=AsyncMock(), create_browser_session=AsyncMock(),
        mark_browser_session_closed=AsyncMock(), finish_agent_execution=AsyncMock()))
    events = AsyncMock()
    monkeypatch.setattr(slop_run, "RunEventRepository", lambda _: SimpleNamespace(create=events))
    session = Mock(get=AsyncMock(return_value=TestRun(id=run_id, configuration_snapshot={})),
        scalar=AsyncMock(return_value=None),
        flush=AsyncMock(), commit=AsyncMock(), add=Mock())
    request = SimpleNamespace(run_id=run_id, start_url="https://app.test/", study_brief="Audit UI",
        allowed_origins=(AllowedOrigin("https", "app.test", None),), network_policy="public_only")

    await slop_run.execute_slop_run(request=request, session=session)

    assert [len(call) for call in review_calls] == [1, 5]
    assert checkpoint.await_count == 1
    assert len(review_calls) + checkpoint.await_count == 3
    results = [call.kwargs["payload"] for call in events.await_args_list
               if call.kwargs["event_type"] == "slop.state.result"]
    traversal = [payload for payload in results if payload.get("interaction_path")]
    assert len(traversal) == 5
    leaders = [payload for payload in traversal
               if any(signal["rule_id"] == "UI_VISUAL_REVIEW"
                      for signal in payload["page_signals"])]
    assert len(leaders) == 1
    assert {payload["viewport"] for payload in leaders} == {"desktop1280"}


# --- Phase 1b section 7: slop inventory accounting (T-SL1, T-SL2) ---

from markettwin_execution_orchestrator.slop.inventory import (
    account_for_page,
    inventory_for_page,
)

_SLOP_MAP_BLOCK = {
    "pages": [
        {
            "url": "https://app.test/",
            "effective_url": "https://app.test/",
            "elements": [
                {"state_key": "default", "state_id": "s1", "elements": [
                    {"role": "link", "name": "Pricing"},
                    {"role": "button", "name": "Open menu"},
                    {"role": "button", "name": "Delete account"},
                ]},
                {"state_key": "observed-1", "state_id": "s2", "elements": [
                    {"role": "link", "name": "Pricing"},
                    {"role": "link", "name": "Ghost"},
                ]},
            ],
        },
        {"url": "https://app.test/plain", "effective_url": "https://app.test/plain",
         "states": []},
    ],
}


def test_inventory_for_page_none_without_map_inventory():
    """T-SL1: no map, an unknown page, and a census-only page all
    yield None — the caller emits no accounting event and behaviour
    is byte-identical to a mapless run. A harvested page flattens
    across states with state keys kept."""
    assert inventory_for_page(None, "https://app.test/") is None
    assert inventory_for_page({}, "https://app.test/") is None
    assert inventory_for_page(_SLOP_MAP_BLOCK, "https://app.test/nope") is None
    assert inventory_for_page(_SLOP_MAP_BLOCK, "https://app.test/plain") is None
    items = inventory_for_page(_SLOP_MAP_BLOCK, "https://app.test")
    assert items is not None
    assert [(i["role"], i["name"], i["state_key"]) for i in items] == [
        ("link", "Pricing", "default"),
        ("button", "Open menu", "default"),
        ("button", "Delete account", "default"),
        ("link", "Pricing", "observed-1"),
        ("link", "Ghost", "observed-1"),
    ]


def test_account_for_page_partitions_with_named_reasons():
    """T-SL2: every inventoried element is accounted for exactly
    once — judged in its own state, or unjudged with one of the three
    named reasons; the partition is exact."""
    inventory = inventory_for_page(_SLOP_MAP_BLOCK, "https://app.test/")
    assert inventory is not None
    judged = [
        {"role": "link", "name": "Pricing", "state_key": "default",
         "verdict": "clean"},
        {"role": "button", "name": "Open menu", "state_key": "default",
         "verdict": "cant_tell"},
    ]
    result = account_for_page(inventory, judged)
    assert result["inventory_total"] == 5
    assert result["judged"] == 1
    assert result["judged"] + len(result["unjudged"]) == result["inventory_total"]
    reasons = {
        (item["name"], item["state_key"]): item["reason"]
        for item in result["unjudged"]
    }
    assert reasons == {
        ("Open menu", "default"): "not_visible_in_review",
        ("Delete account", "default"): "inventory_stale_mismatch",
        ("Pricing", "observed-1"): "duplicate_of_judged",
        ("Ghost", "observed-1"): "inventory_stale_mismatch",
    }


def test_account_for_page_floating_judged_entries_claim_first_match():
    """T-SL2 (floating half): a judged entry with no state key — a
    live state the caller could not key to a harvested state — claims
    the first matching inventory item; the same element inventoried
    in a second state is then a duplicate, not a second judgement."""
    inventory = inventory_for_page(_SLOP_MAP_BLOCK, "https://app.test/")
    assert inventory is not None
    judged = [
        {"role": "link", "name": "Pricing", "state_key": None,
         "verdict": "slop"},
    ]
    result = account_for_page(inventory, judged)
    assert result["judged"] == 1
    assert result["judged"] + len(result["unjudged"]) == result["inventory_total"]
    reasons = {
        (item["name"], item["state_key"]): item["reason"]
        for item in result["unjudged"]
    }
    assert reasons[("Pricing", "observed-1")] == "duplicate_of_judged"
@pytest.mark.asyncio
async def test_t_p3_lanes_claim_each_page_once(monkeypatch):
    """Doc 18 section 15 T-P3 (workflow level): two lanes over a
    per-session fake controller. Every page is claimed exactly once,
    traversal states are duplicates of their entry states (counted,
    never re-absorbed), and every lead.checkpoint payload records
    its application point."""
    monkeypatch.setattr(slop_run, "LANE_COUNT", 2)
    run_id = uuid4()
    room_handle = SimpleNamespace(session_id=uuid4(), execution_id=uuid4(),
                                  journey_id=uuid4())
    sessions = {room_handle.session_id: {"url": "https://app.test/"}}
    worker_opened = asyncio.Event()

    def el(name):
        return {"kind": "button", "tag": "button", "role": "button",
                "name": name, "region": "main", "disabled": False,
                "selected": None, "expanded": None, "invalid": None,
                "text": name}

    async def create_worker_session(**kwargs):
        handle = SimpleNamespace(session_id=uuid4(), execution_id=uuid4(),
                                 journey_id=uuid4())
        sessions[handle.session_id] = {"url": "https://app.test/"}
        worker_opened.set()
        return handle

    async def navigate(**kwargs):
        if kwargs["session_id"] == room_handle.session_id:
            await asyncio.wait_for(worker_opened.wait(), timeout=2)
        sessions[kwargs["session_id"]]["url"] = kwargs["url"]

    async def probe_page(**kwargs):
        return {"url": sessions[kwargs["session_id"]]["url"],
                "elements": [el("Heading")], "words": 50}

    async def page_links(**kwargs):
        if sessions[kwargs["session_id"]]["url"] == "https://app.test/":
            return ["https://app.test/b", "https://app.test/c"]
        return []

    controller = SimpleNamespace(
        open_room_session=AsyncMock(return_value=room_handle),
        create_worker_session=create_worker_session,
        close_session=AsyncMock(), close_room=AsyncMock(),
        navigate=navigate, wait=AsyncMock(), probe_page=probe_page,
        set_viewport=AsyncMock(), page_links=page_links,
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        ui_state_targets=AsyncMock(return_value=[
            {"role": "button", "name": f"Item {index}", "kind": "button"}
            for index in range(20)]),
        click=AsyncMock(),
        dismiss_blocking_surface=AsyncMock(return_value=False),
        harvest_js_records=AsyncMock(return_value=[]),
        sitemap_locations=AsyncMock(return_value=["https://app.test/b", "https://app.test/c"]))

    class Context:
        async def __aenter__(self):
            return controller

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(slop_run, "BrowserController", Context)
    monkeypatch.setattr(slop_run, "review_screenshots",
                        AsyncMock(return_value=[]))
    monkeypatch.setattr(slop_run, "review_checkpoint", AsyncMock(
        return_value={"decision": "continue", "reason": "On track",
                      "source": "lead"}))
    completed = AsyncMock()
    _patch_run_state(monkeypatch, completed)
    events = AsyncMock()
    monkeypatch.setattr(slop_run, "RunEventRepository",
                        lambda _: SimpleNamespace(create=events))
    session = Mock(
        get=AsyncMock(return_value=TestRun(id=run_id,
                                           configuration_snapshot={})),
        scalar=AsyncMock(return_value=None),
        flush=AsyncMock(), commit=AsyncMock(), add=Mock())
    request = SimpleNamespace(
        run_id=run_id, start_url="https://app.test/", study_brief="Audit UI",
        allowed_origins=(AllowedOrigin("https", "app.test", None),),
        network_policy="public_only")
    await slop_run.execute_slop_run(request=request, session=session)

    completed.assert_awaited_once()
    payloads = [(call.kwargs["event_type"], call.kwargs["payload"])
                for call in events.await_args_list]
    collection = next(p for t, p in payloads if t == "run.collection")
    assert collection["lane_count"] == 2
    assert collection["duplicate_absorptions"] == 0
    assert collection["states_recorded"] == 3
    assert collection["pages_pending"] == 0
    inspected = [p for t, p in payloads if t == "slop.page.inspected"]
    assert len(inspected) == 3
    assert {entry["claim_seq"] for entry in inspected} == {1, 2, 3}
    assert {entry["lane_id"] for entry in inspected} <= {0, 1}
    starts = [p for t, p in payloads if t == "slop.page.started"]
    assert {p["watched_browser"] for p in starts} == {True, False}
    entry = session.get.return_value.configuration_snapshot["slop_entry_assessment"]
    assert entry["url"] == request.start_url
    assert entry["viewports"] == ["desktop1280"]
    checkpoints = [p for t, p in payloads if t == "lead.checkpoint"]
    assert checkpoints
    for payload in checkpoints:
        application = payload["application"]
        assert (application["pages_claimed_at_application"]
                >= application["pages_claimed_at_decision"])
    states = [p for t, p in payloads if t == "slop.state.result"]
    assert {(state["url"], state.get("viewport")) for state in states} == {
        (url, "desktop1280")
        for url in ("https://app.test/", "https://app.test/b",
                    "https://app.test/c")}


@pytest.mark.asyncio
async def test_t_r1_s1_snapshot_requeues_in_flight_pages(monkeypatch):
    """Doc 18 section 15 T-R1: a snapshot written by the pooled
    executor names its in-flight claims; on resume those pages are
    re-queued and inspected — never minted as unassessed
    'not replayed' states, and no page is counted twice. A pre-S1
    snapshot (no lane fields) keeps the interrupted semantics."""
    run_id = uuid4()
    handle = SimpleNamespace(session_id=uuid4(), execution_id=uuid4(),
                             journey_id=uuid4())
    current = {"url": "https://app.test/"}
    navigated = []

    async def navigate(**kwargs):
        navigated.append(kwargs["url"])
        current["url"] = kwargs["url"]

    async def probe_page(**kwargs):
        return {"url": current["url"], "elements": [], "words": 50}

    controller = SimpleNamespace(
        open_room_session=AsyncMock(return_value=handle),
        close_room=AsyncMock(), navigate=navigate, wait=AsyncMock(),
        probe_page=probe_page, set_viewport=AsyncMock(),
        page_links=AsyncMock(return_value=[]),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        ui_state_targets=AsyncMock(return_value=[]), click=AsyncMock(),
        dismiss_blocking_surface=AsyncMock(return_value=False),
        harvest_js_records=AsyncMock(return_value=[]),
        sitemap_locations=AsyncMock(return_value=[]))

    class Context:
        async def __aenter__(self):
            return controller

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(slop_run, "BrowserController", Context)
    monkeypatch.setattr(slop_run, "review_screenshots",
                        AsyncMock(return_value=[]))
    monkeypatch.setattr(slop_run, "review_checkpoint", AsyncMock(
        return_value={"decision": "continue", "reason": "On track",
                      "source": "lead"}))
    completed = AsyncMock()
    _patch_run_state(monkeypatch, completed)
    events = AsyncMock()
    monkeypatch.setattr(slop_run, "RunEventRepository",
                        lambda _: SimpleNamespace(create=events))
    old_states = [{"url": "https://app.test/", "viewport": viewport,
                   "elements": [], "page_signals": [], "js_errors": []}
                  for viewport in ("desktop1280", "mobile320")]
    saved_events = [
        SimpleNamespace(event_type="slop.page.checkpoint",
                        payload={"states": old_states}),
        SimpleNamespace(event_type="slop.page.inspected", payload={
            "url": "https://app.test/a",
            "pending_urls": ["https://app.test/unlinked",
                             "https://app.test/found"]})]
    run_row = TestRun(id=run_id, configuration_snapshot={})
    run_row.status = "running"
    run_row.configuration_snapshot = {
        "slop_attempt": 1, "slop_checkpoint": {
            "visited": ["https://app.test/"],
            "pending": ["https://app.test/unlinked"],
            "active_url": "https://app.test/a",
            "lane_count": 2,
            "in_flight": [{"url": "https://app.test/a", "claimed_by": 1,
                           "attempt": 1, "claim_seq": 2}]}}
    session = Mock(
        get=AsyncMock(return_value=run_row),
        scalar=AsyncMock(return_value=None),
        flush=AsyncMock(), commit=AsyncMock(), add=Mock(),
        execute=AsyncMock(return_value=SimpleNamespace(
            scalars=lambda: saved_events)))
    request = SimpleNamespace(
        run_id=run_id, start_url="https://app.test/", study_brief="Audit UI",
        allowed_origins=(AllowedOrigin("https", "app.test", None),),
        network_policy="public_only")
    await slop_run.execute_slop_run(request=request, session=session)

    completed.assert_awaited_once()
    assert session.add.call_args.args[0].ordinal == 2
    # The in-flight page is re-inspected, the visited page is not,
    # and the pages it had discovered join the queue.
    assert set(navigated) == {"https://app.test/a",
                              "https://app.test/unlinked",
                              "https://app.test/found"}
    states = [call.kwargs["payload"] for call in events.await_args_list
              if call.kwargs["event_type"] == "slop.state.result"]
    assert {(state["url"], state.get("viewport")) for state in states} == {
        (url, "desktop1280")
        for url in ("https://app.test/", "https://app.test/a",
                    "https://app.test/unlinked", "https://app.test/found")} | {("https://app.test/", "mobile320")}
    assert not any("not replayed" in signal.get("detail", "")
                   for state in states
                   for signal in state["page_signals"])


@pytest.mark.asyncio
async def test_a1_redelivery_after_publication_does_not_republish(monkeypatch):
    """Astra A1 regression: an attempt that published its final state
    results and then died before the completion commit is redelivered
    (the run is still "running" with a checkpoint and nothing left to
    crawl). The redelivery must complete the run WITHOUT publishing
    the states a second time — evaluation aggregates every published
    slop.state.result row, so a republication doubles every defect
    count and the states_visited total."""
    from markettwin_shared.slop_aggregate import aggregate_run

    run_id = uuid4()
    handle = SimpleNamespace(session_id=uuid4(), execution_id=uuid4(),
                             journey_id=uuid4())
    controller = SimpleNamespace(
        open_room_session=AsyncMock(return_value=handle), navigate=AsyncMock(),
        wait=AsyncMock(),
        probe_page=AsyncMock(return_value={"url": "https://app.test/",
                                           "elements": [], "words": 50}),
        set_viewport=AsyncMock(),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=[]),
        ui_state_targets=AsyncMock(return_value=[]), click=AsyncMock(),
        sitemap_locations=AsyncMock(return_value=[]),
        harvest_js_records=AsyncMock(return_value=[]), close_room=AsyncMock(),
    )

    class Context:
        async def __aenter__(self):
            return controller

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(slop_run, "BrowserController", Context)
    monkeypatch.setattr(slop_run, "review_screenshots", AsyncMock(return_value=[]))
    monkeypatch.setattr(slop_run, "review_checkpoint", AsyncMock(
        return_value={"decision": "continue", "reason": "Progress is useful"}))
    completed = AsyncMock()
    _patch_run_state(monkeypatch, completed)
    events = AsyncMock()
    monkeypatch.setattr(slop_run, "RunEventRepository",
                        lambda _: SimpleNamespace(create=events))
    published_states = [
        {"url": "https://app.test/", "viewport": viewport, "elements": [],
         "page_signals": [],
         "js_errors": [{"rule_id": "DEF_JS_CONSOLE_ERROR",
                        "severity": "serious", "message": "boom", "count": 3}]
         if viewport == "desktop1280" else []}
        for viewport in ("desktop1280", "mobile320")]
    published_payloads = [
        {"url": state["url"], "title": None, "elements": [],
         "page_signals": [], "js_errors": state["js_errors"],
         "viewport": state["viewport"], "screenshot_path": None,
         "screenshot_artifact_id": None, "measurement_evidence": None,
         "interaction_path": None}
        for state in published_states]
    saved_events = [SimpleNamespace(
        event_type="slop.page.checkpoint",
        payload={"states": published_states})]
    run_row = TestRun(id=run_id, configuration_snapshot={})
    run_row.status = "running"
    run_row.configuration_snapshot = {"slop_attempt": 1, "slop_checkpoint": {
        "visited": ["https://app.test/"], "pending": []}}
    published_id = uuid4()

    async def scalar(statement, *args, **kwargs):
        try:
            sql = str(statement.compile(
                compile_kwargs={"literal_binds": True}))
        except Exception:
            return None
        return published_id if "slop.state.result" in sql else None

    session = Mock(get=AsyncMock(return_value=run_row),
        scalar=AsyncMock(side_effect=scalar),
        flush=AsyncMock(), commit=AsyncMock(), add=Mock(),
        execute=AsyncMock(return_value=SimpleNamespace(
            scalars=lambda: saved_events)))
    request = SimpleNamespace(run_id=run_id, start_url="https://app.test/",
        study_brief="Audit UI",
        allowed_origins=(AllowedOrigin("https", "app.test", None),),
        network_policy="public_only")
    await slop_run.execute_slop_run(request=request, session=session)

    new_results = [call.kwargs["payload"] for call in events.await_args_list
                   if call.kwargs["event_type"] == "slop.state.result"]
    assert new_results == []
    before = aggregate_run(published_payloads)
    after = aggregate_run(published_payloads + new_results)
    assert after["defects"] == before["defects"]
    assert after["states_visited"] == before["states_visited"] == 2
    completed.assert_awaited_once()


@pytest.mark.asyncio
async def test_owner_stop_ends_the_crawl_and_cancels_the_run(monkeypatch):
    """Owner stop (the Stop run button): the flag ctl records in the
    run's configuration snapshot is honoured at the next claim — the
    page in flight finishes, no further page starts, the pending
    pages stay named in the collection, and the run closes
    cancelled, never completed. Unlike a Lead stop, the queue guard
    never overrules it."""
    run_id = uuid4()
    run_row = TestRun(id=run_id, configuration_snapshot={})
    handle = SimpleNamespace(session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4())

    async def probe(**kwargs):
        # The ctl write landing while the first page is measured:
        # the snapshot the absorber fresh-reads at the next claim
        # now carries the flag.
        run_row.configuration_snapshot = {
            **run_row.configuration_snapshot,
            "owner_stop": {"requested_at": "2026-11-18T20:34:00+00:00",
                           "requested_by": "owner"},
        }
        return {"url": "https://app.test/", "words": 40, "elements": [
            {"kind": "text", "tag": "h1", "role": "h1", "name": "Home", "region": "main",
             "disabled": False, "selected": None, "expanded": None, "invalid": None,
             "text": "Home"}]}

    controller = SimpleNamespace(
        open_room_session=AsyncMock(return_value=handle), navigate=AsyncMock(),
        wait=AsyncMock(), probe_page=AsyncMock(side_effect=probe), set_viewport=AsyncMock(),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=["https://app.test/link1",
                                           "https://app.test/link2"]),
        ui_state_targets=AsyncMock(return_value=[]), click=AsyncMock(),
        sitemap_locations=AsyncMock(return_value=[]),
        harvest_js_records=AsyncMock(return_value=[]), close_room=AsyncMock(),
    )

    class Context:
        async def __aenter__(self):
            return controller

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(slop_run, "BrowserController", Context)
    monkeypatch.setattr(slop_run, "review_screenshots", AsyncMock(return_value=[]))
    monkeypatch.setattr(slop_run, "review_checkpoint", AsyncMock(
        return_value={"decision": "continue",
                      "reason": "Progress is useful", "source": "lead"}))
    completed = AsyncMock()
    cancelled = AsyncMock()
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.persistence.run_state_repository.RunStateRepository",
        lambda _: SimpleNamespace(mark_running=AsyncMock(),
                                  mark_completed=completed,
                                  mark_cancelled=cancelled))
    monkeypatch.setattr(slop_run, "ExecutionRepository", lambda _: SimpleNamespace(
        create_agent_execution=AsyncMock(), create_browser_session=AsyncMock(),
        mark_browser_session_closed=AsyncMock(), finish_agent_execution=AsyncMock()))
    events = AsyncMock()
    monkeypatch.setattr(slop_run, "RunEventRepository", lambda _: SimpleNamespace(create=events))
    session = Mock(get=AsyncMock(return_value=run_row),
        scalar=AsyncMock(return_value=None),
        flush=AsyncMock(), commit=AsyncMock(), add=Mock())
    request = SimpleNamespace(run_id=run_id, start_url="https://app.test/", study_brief="Audit UI",
        allowed_origins=(AllowedOrigin("https", "app.test", None),), network_policy="public_only")
    await slop_run.execute_slop_run(request=request, session=session)
    started = [call.kwargs["payload"]["url"] for call in events.await_args_list
               if call.kwargs["event_type"] == "slop.page.started"]
    assert started == ["https://app.test/"]
    event_types = [call.kwargs["event_type"] for call in events.await_args_list]
    assert "run.owner_stop" in event_types
    collections = [call.kwargs["payload"] for call in events.await_args_list
                   if call.kwargs["event_type"] == "run.collection"]
    assert len(collections) == 1
    assert collections[0]["owner_stopped"] is True
    assert collections[0]["partial"] is True
    assert sorted(collections[0]["pending_urls"]) == [
        "https://app.test/link1", "https://app.test/link2"]
    cancelled.assert_awaited_once()
    completed.assert_not_awaited()
