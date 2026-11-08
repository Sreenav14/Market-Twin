"""Harness driver mechanics: state round-trip, fixture board, dispatch, resume.

These tests use hand-built doubles in this file: a Mock session,
Mock repositories, an AsyncMock browser controller, and a fake
execute_test_case. They measure driver mechanics, not model quality.
"""

import json
import statistics
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from markettwin_database.models import TestRun
from markettwin_execution_orchestrator.browser import AllowedOrigin
from markettwin_execution_orchestrator.persistence.plan_repository import (
    PersistedJourneyRecord,
)
from markettwin_execution_orchestrator.workflow import (
    harness_run,
    harness_state,
    run_executor,
)
from markettwin_execution_orchestrator.workflow.harness_state import (
    HarnessState,
    canonical_url,
    item_id_for,
    load_harness_state,
    new_harness_state,
    persist_harness_state,
    state_id_for,
)
from markettwin_execution_orchestrator.workflow.run_executor import (
    MarketTwinRunRequest,
)
from markettwin_shared.deep_testing import AssertionResult, CaseExecutionResult


def _board() -> HarnessState:
    board = new_harness_state()
    page = board.add_state(
        url="https://example.test/app?b=2&a=1",
        elements=(("button", "Save"), ("link", "Help"), ("textbox", "Email")),
        form_fields=("Email",),
    )
    save = board.add_item(state_id=page.state_id, case_id="save_case",
                          role="button", name="Save")
    save.status = "worked"
    save.attempts = 1
    save.evidence_refs = ["execution-1", "artifact-1"]
    save.durations_ms = [1250]
    help_item = board.add_item(state_id=page.state_id, case_id="help_case",
                               role="link", name="Help")
    help_item.status = "broken"
    help_item.attempts = 2
    help_item.blocker = "assertion_precondition_failed"
    board.add_item(state_id=page.state_id, case_id="email_case",
                   role="textbox", name="Email")
    board.budget_counters["items_started"] = 3
    board.budget_counters["items_finished"] = 2
    board.budget_counters["total_elapsed_ms"] = 2500
    return board


def test_state_and_item_identity_follow_the_v1_scheme() -> None:
    elements = (("button", "Save"), ("link", "Help"))
    first = state_id_for("https://EXAMPLE.test/app/?b=2&a=1#frag", elements, ("Email",))
    second = state_id_for("https://example.test/app?a=1&b=2",
                          tuple(reversed(elements)), ("Email",))
    assert first == second
    assert len(first) == 64
    assert canonical_url("https://example.test/app/") == "https://example.test/app"
    assert item_id_for(first, "button", "Save", 0) == f"{first}:button:Save:0"
    assert item_id_for(first, "button", "Save", 1) != item_id_for(first, "button", "Save", 0)
    board = new_harness_state()
    assert board.state_abstraction_version == "v1"
    assert board.budget_counters["item_budget"] == 300
    assert board.next_pending() is None


async def test_harness_state_round_trips_through_the_snapshot() -> None:
    run_id = uuid4()
    run = TestRun(id=run_id, status="queued", configuration_snapshot={})
    session = Mock(add=Mock(), flush=AsyncMock(), commit=AsyncMock(),
                   get=AsyncMock(return_value=run))
    board = _board()
    await persist_harness_state(session, run, board,
                                event_type="harness.run.initialised", stage="exploring")
    assert run.configuration_snapshot["harness_stage"] == "exploring"
    added = [call.args[0] for call in session.add.call_args_list]
    assert [event.event_type for event in added] == ["harness.run.initialised"]
    # The snapshot is JSONB: the board must survive a JSON round trip intact.
    snapshot = json.loads(json.dumps(run.configuration_snapshot))
    reloaded_run = TestRun(id=run_id, status="queued", configuration_snapshot=snapshot)
    session.get = AsyncMock(return_value=reloaded_run)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    assert loaded.to_document() == board.to_document()
    assert loaded.counts() == board.counts()
    assert loaded.counts()["worked"] == 1
    assert loaded.counts()["broken"] == 1
    assert loaded.counts()["pending"] == 1
    assert loaded.budget_counters == board.budget_counters


def test_harness_state_round_trips_an_owner_disabled_item() -> None:
    document = _board().to_document()
    items = document["items"]
    assert isinstance(items, dict)
    first = next(iter(items.values()))
    assert isinstance(first, dict)
    first["status"] = "owner_disabled"
    loaded = HarnessState.from_document(document)
    assert loaded.counts()["owner_disabled"] == 1
    assert loaded.to_document() == document


def test_harness_state_rejects_an_unknown_item_status() -> None:
    document = _board().to_document()
    items = document["items"]
    assert isinstance(items, dict)
    first = next(iter(items.values()))
    assert isinstance(first, dict)
    first["status"] = "somehow_done"
    with pytest.raises(ValueError, match="Unknown harness item status"):
        HarnessState.from_document(document)


FIXTURE_URL = "http://127.0.0.1:5191/index.html"

# Ground truth for the v1_benchmark fixture, per twin. The broken twin is
# the retained index.html as written; the good twin is the same page with
# the four seeded defects repaired (the FixtureHandler patch in
# scripts/run_contract_fixture_benchmark.py). The ambiguous section has no
# final delivery evidence on either twin, and the restricted link is
# outside the authorized origin on either twin.
GROUND_TRUTH: dict[str, dict[str, str]] = {
    "guide_navigation": {"broken": "worked", "good": "worked"},
    "working_form": {"broken": "worked", "good": "worked"},
    "primary_action": {"broken": "broken", "good": "worked"},
    "contact_validation": {"broken": "broken", "good": "worked"},
    "billing_navigation": {"broken": "broken", "good": "worked"},
    "preview_confirmation": {"broken": "broken", "good": "worked"},
    "delivery_state": {"broken": "could_not_check", "good": "could_not_check"},
    "restricted_destination": {"broken": "blocked", "good": "blocked"},
}
FIXTURE_ELAPSED_MS: dict[str, int] = {
    "guide_navigation": 900, "working_form": 2100, "primary_action": 400,
    "contact_validation": 700, "billing_navigation": 1100,
    "preview_confirmation": 600, "delivery_state": 300,
    "restricted_destination": 200,
}


def _assertion(*, case, expected, status, execution_id, step_id) -> AssertionResult:
    observed = expected.expected_value
    if status == "not_satisfied":
        observed = False if type(expected.expected_value) is bool else "Wrong value"
    return AssertionResult(
        case_id=case.case_id, assertion_id=expected.assertion_id,
        oracle=expected.oracle, expected_value=expected.expected_value,
        observed_value=observed, status=status, execution_id=execution_id,
        step_id=step_id, artifact_ids=(uuid4(),), origin="user_approved",
        elapsed_ms=1,
    )


def _fixture_result(*, case, twin, execution_id) -> CaseExecutionResult:
    """The result the real executor produces for one case on one twin."""

    truth = GROUND_TRUTH[case.case_id][twin]
    elapsed = FIXTURE_ELAPSED_MS[case.case_id]
    if truth == "blocked":
        return CaseExecutionResult(
            case_id=case.case_id, execution_id=execution_id,
            execution_status="policy_blocked", verdict="unverified",
            action_step_ids=(1,), elapsed_ms=elapsed, blocker="policy_blocked",
        )
    if truth == "could_not_check":
        unverified = AssertionResult(
            case_id=case.case_id, assertion_id=case.expected[0].assertion_id,
            oracle=case.expected[0].oracle,
            expected_value=case.expected[0].expected_value, observed_value=None,
            status="unverified", execution_id=execution_id, step_id=2,
            origin="user_approved", elapsed_ms=1, reason="missing_evidence",
        )
        return CaseExecutionResult(
            case_id=case.case_id, execution_id=execution_id,
            execution_status="completed", verdict="unverified",
            action_step_ids=(1,), assertion_results=(unverified,),
            elapsed_ms=elapsed,
        )
    if truth == "broken" and case.case_id == "primary_action":
        assertions = tuple(
            _assertion(case=case, expected=expected, status="not_satisfied",
                       execution_id=execution_id, step_id=10 + index)
            for index, expected in enumerate(case.expected)
            if expected.assertion_id == "primary_enabled"
        )
        return CaseExecutionResult(
            case_id=case.case_id, execution_id=execution_id,
            execution_status="completed", verdict="not_satisfied",
            action_step_ids=(1,), assertion_results=assertions,
            elapsed_ms=elapsed, blocker="assertion_precondition_failed",
        )
    assertions = tuple(
        _assertion(case=case, expected=expected,
                   status="not_satisfied" if truth == "broken" and index == 0
                   else "satisfied",
                   execution_id=execution_id, step_id=10 + index)
        for index, expected in enumerate(case.expected)
    )
    return CaseExecutionResult(
        case_id=case.case_id, execution_id=execution_id,
        execution_status="completed",
        verdict="not_satisfied" if truth == "broken" else "satisfied",
        action_step_ids=(1,), assertion_results=assertions, elapsed_ms=elapsed,
    )


def _install_driver_doubles(monkeypatch, *, twin, calls) -> Mock:
    """Patch every repository/controller the driver touches; return events."""

    record = PersistedJourneyRecord(uuid4(), uuid4(), uuid4(),
                                    "browser_discovery__observe_starting_page", 10000)
    monkeypatch.setattr(
        harness_run, "PlanRepository",
        lambda _: Mock(create_auth_bootstrap=AsyncMock(return_value=record)),
    )
    monkeypatch.setattr(
        harness_run, "ExecutionRepository",
        lambda _: Mock(create_agent_execution=AsyncMock(),
                       finish_agent_execution=AsyncMock(),
                       create_browser_session=AsyncMock(),
                       mark_browser_session_closed=AsyncMock(),
                       rebind_browser_session=AsyncMock()),
    )
    monkeypatch.setattr(
        harness_run, "RunStateRepository",
        lambda _: Mock(mark_running=AsyncMock(), mark_completed=AsyncMock()),
    )
    monkeypatch.setattr(harness_run, "BrowserController", lambda: AsyncMock())
    events = Mock(create=AsyncMock())
    monkeypatch.setattr(harness_state, "RunEventRepository", lambda _: events)

    async def execute(**kwargs) -> CaseExecutionResult:
        case = kwargs["case"]
        calls.append(case.case_id)
        return _fixture_result(case=case, twin=twin,
                               execution_id=kwargs["request"].execution_id)

    monkeypatch.setattr(harness_run, "execute_test_case", AsyncMock(side_effect=execute))
    return events


def _fixture_run(run_id):
    run = TestRun(id=run_id, status="queued", configuration_snapshot={})
    session = Mock(get=AsyncMock(return_value=run), add=Mock(),
                   flush=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock())
    request = MarketTwinRunRequest(
        run_id=run_id, study_brief="Check the controlled benchmark fixture",
        target_snapshot={}, start_url=FIXTURE_URL,
        allowed_origins=(AllowedOrigin("http", "127.0.0.1", 5191),),
        network_policy="local_development",
        fixture_truth=True,
    )
    return run, session, request


@pytest.mark.parametrize("twin", ["broken", "good"])
async def test_harness_fixture_board_agrees_with_ground_truth(monkeypatch, twin) -> None:
    run_id = uuid4()
    run, session, request = _fixture_run(run_id)
    calls: list[str] = []
    _install_driver_doubles(monkeypatch, twin=twin, calls=calls)
    results = await harness_run.execute_harness_run(request=request, session=session)
    assert len(results) == 8
    assert sorted(calls) == sorted(GROUND_TRUTH)
    assert run.configuration_snapshot["harness_stage"] == "done"
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    assert len(loaded.items) == 8
    agreement = 0
    for item in loaded.ordered_items():
        assert item.status in {"worked", "broken", "could_not_check",
                               "not_checked", "blocked"}
        assert item.status == GROUND_TRUTH[item.case_id][twin]
        agreement += item.status == GROUND_TRUTH[item.case_id][twin]
    assert agreement == 8
    assert loaded.budget_counters["items_finished"] == 8


async def test_harness_mode_dispatches_through_the_executor(monkeypatch) -> None:
    run_id = uuid4()
    run = TestRun(id=run_id, status="queued", configuration_snapshot={})
    session = Mock(get=AsyncMock(return_value=run), flush=AsyncMock(),
                   commit=AsyncMock())
    harness = AsyncMock(return_value=())
    monkeypatch.setattr(harness_run, "execute_harness_run", harness)
    request = MarketTwinRunRequest(
        run_id=run_id, study_brief="Check the controlled benchmark fixture",
        target_snapshot={}, start_url=FIXTURE_URL,
        allowed_origins=(AllowedOrigin("http", "127.0.0.1", 5191),),
        network_policy="local_development",
    )
    result = await run_executor.execute_markettwin_run(request, session=session)
    assert result == ()
    harness.assert_awaited_once_with(request=request, session=session)


async def test_unified_native_explore_test_dispatches_to_the_board_engine(
    monkeypatch,
) -> None:
    run_id = uuid4()
    run = TestRun(id=run_id, status="queued", configuration_snapshot={})
    session = Mock(get=AsyncMock(return_value=run), flush=AsyncMock(),
                   commit=AsyncMock())
    harness = AsyncMock(return_value=())
    monkeypatch.setattr(harness_run, "execute_harness_run", harness)
    request = MarketTwinRunRequest(
        run_id=run_id, study_brief="Explore and test everything",
        target_snapshot={}, start_url=FIXTURE_URL,
        allowed_origins=(AllowedOrigin("http", "127.0.0.1", 5191),),
        network_policy="local_development",
        run_kind="explore_test", unified_native=True,
    )
    result = await run_executor.execute_markettwin_run(request, session=session)
    assert result == ()
    harness.assert_awaited_once_with(request=request, session=session)


async def test_unified_dispatch_contract(monkeypatch) -> None:
    """U-P8 dispatch: translated explore_test modes (discovery/deep/
    harness) all run on the Board engine — the unified successor;
    a legacy persona request refuses loudly."""

    from markettwin_execution_orchestrator.workflow import harness_run
    from markettwin_shared.run_kind import translate_execution_mode

    run_id = uuid4()
    session = Mock(get=AsyncMock(return_value=None), flush=AsyncMock(),
                   commit=AsyncMock())
    board_mock = AsyncMock(return_value="board-result")
    monkeypatch.setattr(harness_run, "execute_harness_run", board_mock)
    monkeypatch.setattr(
        run_executor, "execute_harness_run", board_mock, raising=False,
    )
    base = {
        "run_id": run_id, "study_brief": "Check the fixture", "target_snapshot": {},
        "start_url": FIXTURE_URL,
        "allowed_origins": (AllowedOrigin("http", "127.0.0.1", 5191),),
        "network_policy": "local_development",
    }
    for mode in ("discovery_contract_v1", "deep_feature_v1", "harness_v1"):
        # build_run_request resolves each legacy mode to a kind before
        # dispatch; the executor only ever sees the resolved kind.
        request = MarketTwinRunRequest(
            **base, run_kind=translate_execution_mode(mode),
        )
        assert await run_executor.execute_markettwin_run(
            request, session=session,
        ) == "board-result"
    legacy_persona = MarketTwinRunRequest(
        **base, run_kind="persona", unified_native=False,
    )
    with pytest.raises(ValueError, match="retired"):
        await run_executor.execute_markettwin_run(
            legacy_persona, session=session,
        )


class _SimulatedKill(BaseException):
    """Stands in for the worker process dying between two items."""


async def test_kill_and_resume_executes_no_item_twice_and_loses_none(
    monkeypatch,
) -> None:
    run_id = uuid4()
    run, session, request = _fixture_run(run_id)
    calls: list[str] = []
    events = _install_driver_doubles(monkeypatch, twin="broken", calls=calls)
    real_execute = harness_run.execute_test_case

    async def killing_execute(**kwargs) -> CaseExecutionResult:
        if len(calls) >= 2 and kwargs["case"].case_id not in calls:
            raise _SimulatedKill
        return await real_execute(**kwargs)

    monkeypatch.setattr(
        harness_run, "execute_test_case", AsyncMock(side_effect=killing_execute),
    )
    with pytest.raises(_SimulatedKill):
        await harness_run.execute_harness_run(request=request, session=session)
    assert len(calls) == 2
    interrupted = await load_harness_state(session, run_id)
    assert interrupted is not None
    assert interrupted.counts()["worked"] + interrupted.counts()["broken"] == 2
    assert interrupted.counts()["running"] == 1

    monkeypatch.setattr(harness_run, "execute_test_case", real_execute)
    results = await harness_run.execute_harness_run(request=request, session=session)
    assert len(results) == 6
    assert sorted(calls) == sorted(GROUND_TRUTH)
    assert len(calls) == len(set(calls)) == 8
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    assert loaded.counts()["pending"] == 0
    assert loaded.counts()["running"] == 0
    finished = [
        call.kwargs["payload"]["item_id"]
        for call in events.create.await_args_list
        if call.kwargs["event_type"] == "harness.item.finished"
    ]
    assert len(finished) == 8
    assert len(set(finished)) == 8


async def test_seconds_per_item_are_measured_from_the_fixture_run(
    monkeypatch, capsys,
) -> None:
    run_id = uuid4()
    run, session, request = _fixture_run(run_id)
    calls: list[str] = []
    _install_driver_doubles(monkeypatch, twin="good", calls=calls)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    seconds = sorted(
        duration / 1000
        for item in loaded.ordered_items()
        for duration in item.durations_ms
    )
    assert len(seconds) == 8
    median = statistics.median(seconds)
    rank = -(-9 * len(seconds) // 10)  # nearest-rank p90 position (1-based)
    p90 = seconds[rank - 1]
    with capsys.disabled():
        print(f"seconds-per-item: median={median:.3f}s p90={p90:.3f}s "
              f"across {len(seconds)} items")
    assert median == pytest.approx(0.65)
    assert p90 == pytest.approx(2.1)


INDEX_URL = "https://example.test/app"
INDEX_ENTRIES: tuple[dict[str, object], ...] = (
    {"ordinal": 1, "role": "link", "name": "Help", "name_source": "playwright"},
    {"ordinal": 2, "role": "textbox", "name": "Display name", "name_source": "playwright"},
    {"ordinal": 3, "role": "textbox", "name": "Contact address", "name_source": "playwright"},
    {"ordinal": 4, "role": "button", "name": "Save", "name_source": "playwright"},
    {"ordinal": 5, "role": "button", "name": "Save", "name_source": "playwright"},
    {"ordinal": 6, "role": "button", "name": "Search", "name_source": "playwright"},
    {"ordinal": 7, "role": "checkbox", "name": "Subscribe", "name_source": "playwright"},
    {"ordinal": 8, "role": "button", "name": "Delete account", "name_source": "playwright"},
    {"ordinal": 9, "role": "button", "name": "Pay now", "name_source": "playwright"},
    {"ordinal": 10, "role": "button", "name": "Send invite", "name_source": "playwright"},
    {"ordinal": 11, "role": "button", "name": "Frobnicate", "name_source": "playwright"},
    {"ordinal": 12, "role": "heading", "name": "Welcome", "name_source": "playwright"},
)


def test_inventory_becomes_items_under_the_v1_identity() -> None:
    from markettwin_execution_orchestrator.workflow.harness_items import (
        ingest_page_index,
    )

    board = new_harness_state()
    items = ingest_page_index(board, url=INDEX_URL, entries=INDEX_ENTRIES)
    # The heading is not an actionable role: 12 entries become 11 items.
    assert len(items) == 11
    assert len(board.items) == 11
    assert len(board.states) == 1
    page = next(iter(board.states.values()))
    expected_state = state_id_for(
        INDEX_URL,
        tuple((str(e["role"]), str(e["name"])) for e in INDEX_ENTRIES
              if e["role"] != "heading"),
        ("Display name", "Contact address"),
    )
    assert page.state_id == expected_state
    saves = [item for item in items if item.name == "Save"]
    assert [item.occurrence_index for item in saves] == [0, 1]
    assert saves[0].item_id != saves[1].item_id
    # Fingerprint dedupe: re-ingesting the same index adds nothing.
    assert ingest_page_index(board, url=INDEX_URL, entries=INDEX_ENTRIES) == []
    assert len(board.items) == 11


def test_generated_cases_stay_inside_the_schema_ceilings() -> None:
    from markettwin_execution_orchestrator.workflow.harness_items import (
        case_for_item,
        ingest_page_index,
    )

    board = new_harness_state()
    items = ingest_page_index(board, url=INDEX_URL, entries=INDEX_ENTRIES)
    for item in items:
        case = case_for_item(
            item=item, state_url=INDEX_URL,
            feature_key="selected_feature", start_url=INDEX_URL,
        )
        assert case.case_id == item.case_id
        assert case.feature_key == "selected_feature"
        assert len(case.steps) <= 24
        assert len(case.expected) <= 8
        preconditions = [step for step in case.steps[:-1]]
        assert len(preconditions) <= 3
        assert case.steps[-1].action in {
            "click", "fill", "select", "check",
        }
    moved = case_for_item(
        item=items[0], state_url="https://example.test/other",
        feature_key="selected_feature", start_url=INDEX_URL,
    )
    assert moved.steps[0].action == "navigate"
    assert len(moved.steps) == 2


def test_item_budget_marks_overflow_pending_items_not_checked() -> None:
    from markettwin_execution_orchestrator.workflow.harness_items import (
        ingest_page_index,
    )
    from markettwin_execution_orchestrator.workflow.harness_run import (
        _enforce_item_budget,
    )

    board = new_harness_state()
    items = ingest_page_index(board, url=INDEX_URL, entries=INDEX_ENTRIES)
    assert len(items) == 11
    board.budget_counters["item_budget"] = 5
    assert _enforce_item_budget(board) == 6
    counts = board.counts()
    assert counts["pending"] == 5
    assert counts["not_checked"] == 6
    overflow = [i for i in board.ordered_items() if i.status == "not_checked"]
    assert all(i.blocker == "over item budget (5)" for i in overflow)
    # Idempotent: a second pass marks nothing new.
    assert _enforce_item_budget(board) == 0
    # Under budget: nothing is marked.
    board2 = new_harness_state()
    ingest_page_index(board2, url=INDEX_URL, entries=INDEX_ENTRIES)
    assert _enforce_item_budget(board2) == 0


def test_checkable_items_get_an_outcome_assertion() -> None:
    from markettwin_execution_orchestrator.workflow.harness_items import (
        case_for_item,
        ingest_page_index,
    )

    board = new_harness_state()
    items = ingest_page_index(board, url=INDEX_URL, entries=INDEX_ENTRIES)
    by_role: dict[str, object] = {}
    for item in items:
        by_role.setdefault(item.role, item)
    checkbox_case = case_for_item(
        item=by_role["checkbox"], state_url=INDEX_URL,
        feature_key="selected_feature", start_url=INDEX_URL,
    )
    oracles = {a.assertion_id: a.oracle for a in checkbox_case.expected}
    assert oracles.get("target_checked") == "checked"
    button_case = case_for_item(
        item=by_role["button"], state_url=INDEX_URL,
        feature_key="selected_feature", start_url=INDEX_URL,
    )
    assert {a.assertion_id for a in button_case.expected} == {
        "target_enabled", "target_visible",
    }


def test_safety_classification_follows_rule_3() -> None:
    from markettwin_execution_orchestrator.workflow.harness_items import (
        classify_action,
        execution_allowed,
        skip_reason,
    )

    for name in ("Delete account", "Pay now", "Send invite", "Publish post"):
        assert classify_action(role="button", name=name) == "irreversible"
    assert classify_action(role="link", name="Delete account") == "irreversible"
    assert classify_action(role="button", name="Search") == "read"
    assert classify_action(role="link", name="Help") == "read"
    assert classify_action(role="button", name="Save") == "reversible"
    assert classify_action(role="textbox", name="Display name") == "reversible"
    assert classify_action(role="button", name="Remove from cart") == "reversible"
    assert classify_action(role="button", name="Remove filters") == "reversible"
    # Uncertain defaults to irreversible.
    assert classify_action(role="button", name="Frobnicate") == "irreversible"
    assert classify_action(role="heading", name="Save") == "irreversible"
    assert execution_allowed("read", "read_only") is True
    assert execution_allowed("reversible", "read_only") is False
    assert execution_allowed("reversible", "standard") is True
    assert execution_allowed("irreversible", "standard") is False
    assert skip_reason("irreversible", "standard") == (
        "not exercised — requires approval or test mode"
    )
    assert skip_reason("read", "standard") is None


from types import SimpleNamespace


def _entry(ordinal: int, role: str, name: str) -> dict[str, object]:
    return {
        "ordinal": ordinal, "role": role, "name": name,
        "name_source": "playwright",
    }


def _result_for(case, execution_id, *, verdict, status="completed", blocker=None):
    assertions = ()
    if status == "completed":
        assertions = tuple(
            _assertion(
                case=case, expected=expected,
                status="satisfied" if verdict == "satisfied" else "not_satisfied",
                execution_id=execution_id, step_id=10 + index,
            )
            for index, expected in enumerate(case.expected)
        )
    return CaseExecutionResult(
        case_id=case.case_id, execution_id=execution_id,
        execution_status=status, verdict=verdict,
        action_step_ids=(1,), assertion_results=assertions,
        elapsed_ms=100, blocker=blocker,
    )


def _worked(case, execution_id):
    return _result_for(case, execution_id, verdict="satisfied")


class _FakeInventoryController:
    """BrowserController double serving scripted page indexes.

    ``pages`` maps a URL to its index entries; ``reveal`` entries are
    served only after a scroll. When ``logged_in`` is set, the start
    URL serves ``dashboard_entries`` instead, and the in-memory broker
    holds a human snapshot until ``expire_broker`` — the scripted
    human login through the takeover path is ``complete_human_login``.
    """

    def __init__(self, *, pages, start_url, dashboard_entries=()):
        self.pages = pages
        self.start_url = start_url
        self.dashboard_entries = dashboard_entries
        self.reveal: dict[str, tuple[dict[str, object], ...]] = {}
        self.link_targets: dict[tuple[str, str], str] = {}
        self.current_url = start_url
        self.logged_in = False
        self.broker_snapshot: object | None = None
        self.broker_expired = False
        self.takes: list[str] = []
        self.index_authenticated: list[bool] = []
        self.scrolled = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def create_session(self, **kwargs):
        return SimpleNamespace(
            session_id=uuid4(),
            execution_id=kwargs["execution_id"],
            journey_id=kwargs["journey_id"],
        )

    # Room API (U-P2): the fake's room is its inventory session.
    async def open_room_session(self, **kwargs):
        self.room_handle = await self.create_session(
            execution_id=kwargs["execution_id"],
            journey_id=kwargs["journey_id"],
        )
        return self.room_handle

    async def rebind_session(self, *, session_id, execution_id, journey_id):
        return SimpleNamespace(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )

    async def create_proof_session(self, *, room_session_id, execution_id, journey_id):
        return SimpleNamespace(
            session_id=uuid4(),
            execution_id=execution_id,
            journey_id=journey_id,
        )

    async def close_room(self, *, run_id):
        return None

    async def navigate(self, *, session_id, url, **kwargs):
        self.current_url = url
        return SimpleNamespace(observation=SimpleNamespace(url=url))

    async def get_page_index(
        self, *, session_id, cursor=0, authenticated_session=False, **kwargs,
    ):
        self.index_authenticated.append(authenticated_session)
        if self.current_url == self.start_url and self.logged_in:
            entries = self.dashboard_entries
        else:
            entries = self.pages.get(self.current_url, ())
        visible = list(entries)
        if self.scrolled:
            visible += list(self.reveal.get(self.current_url, ()))
        return SimpleNamespace(
            page_index=tuple(visible[cursor:cursor + 80]),
            next_cursor=cursor + 80 if cursor + 80 < len(visible) else None,
            observation=SimpleNamespace(url=self.current_url),
        )

    async def scroll(self, *, session_id, **kwargs):
        self.scrolled = True
        return SimpleNamespace(observation=SimpleNamespace(url=self.current_url))

    async def click(self, *, session_id, role=None, name=None, **kwargs):
        destination = self.link_targets.get((role, name), self.current_url)
        self.current_url = destination
        return SimpleNamespace(observation=SimpleNamespace(url=destination))

    async def go_back(self, *, session_id, **kwargs):
        return SimpleNamespace(observation=SimpleNamespace(url=self.current_url))

    async def close_session(self, *, session_id, **kwargs):
        return None

    def take_human_session_snapshot(self, *, run_id, target_id, case_id):
        if self.broker_snapshot is None or self.broker_expired:
            raise RuntimeError("No operator-established session is available.")
        self.takes.append(case_id)
        return self.broker_snapshot

    def complete_human_login(self) -> None:
        self.logged_in = True
        self.broker_snapshot = object()
        self.broker_expired = False

    def expire_broker(self) -> None:
        self.logged_in = False
        self.broker_expired = True


def _install_inventory_doubles(monkeypatch, *, controller, script, calls) -> Mock:
    record = PersistedJourneyRecord(uuid4(), uuid4(), uuid4(),
                                    "browser_discovery__observe_starting_page", 10000)
    monkeypatch.setattr(
        harness_run, "PlanRepository",
        lambda _: Mock(create_auth_bootstrap=AsyncMock(return_value=record)),
    )
    monkeypatch.setattr(
        harness_run, "ExecutionRepository",
        lambda _: Mock(create_agent_execution=AsyncMock(),
                       finish_agent_execution=AsyncMock(),
                       create_browser_session=AsyncMock(),
                       mark_browser_session_closed=AsyncMock(),
                       rebind_browser_session=AsyncMock()),
    )
    monkeypatch.setattr(
        harness_run, "RunStateRepository",
        lambda _: Mock(mark_running=AsyncMock(), mark_completed=AsyncMock()),
    )
    monkeypatch.setattr(harness_run, "BrowserController", lambda: controller)
    events = Mock(create=AsyncMock())
    monkeypatch.setattr(harness_state, "RunEventRepository", lambda _: events)

    async def execute(**kwargs) -> CaseExecutionResult:
        case = kwargs["case"]
        calls.append(case.title)
        builder = script[case.title]
        if isinstance(builder, list):
            builder = builder.pop(0)
        return builder(case, kwargs["request"].execution_id)

    monkeypatch.setattr(harness_run, "execute_test_case", AsyncMock(side_effect=execute))
    return events


def _inventory_run(run_id, *, start_url, target_id=None):
    run = TestRun(
        id=run_id, status="queued",
        configuration_snapshot={"harness_run_mode": "standard"},
    )
    session = Mock(get=AsyncMock(return_value=run), add=Mock(),
                   flush=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock())
    request = MarketTwinRunRequest(
        run_id=run_id, study_brief="Inventory-driven harness run",
        target_snapshot={"target_id": str(target_id)} if target_id else {},
        start_url=start_url,
        allowed_origins=(AllowedOrigin("http", "127.0.0.1", 5199),),
        network_policy="local_development",
        runtime_human_assistance=target_id is not None,
    )
    return run, session, request


INVENTORY_URL = "http://127.0.0.1:5199/index.html"


async def test_inventory_run_executes_every_item_it_discovers(monkeypatch) -> None:
    names = [
        ("link", "Help"), ("textbox", "Display name"), ("button", "Save settings"),
        ("button", "Search"), ("checkbox", "Subscribe"), ("link", "Billing"),
        ("button", "Generate preview"), ("textbox", "Contact address"),
        ("button", "Apply filters"), ("link", "Reports"), ("button", "Create draft"),
        ("combobox", "Country"),
    ]
    base = tuple(
        _entry(index + 1, role, name) for index, (role, name) in enumerate(names)
    )
    controller = _FakeInventoryController(pages={INVENTORY_URL: base},
                                          start_url=INVENTORY_URL)
    # The scroll-reveal surfaces one more item after the first scroll.
    controller.reveal = {INVENTORY_URL: (_entry(13, "button", "Load more"),)}
    script = {f"Check {name}": _worked for _, name in names}
    script["Check Load more"] = _worked
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script=script, calls=calls)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    # Count equality: 13 discovered items (a >8-check journey, all
    # executed), zero items unaccounted for.
    assert len(loaded.items) == 13
    assert len(calls) == 13
    assert loaded.counts()["worked"] == 13
    assert sum(loaded.counts().values()) == 13
    assert loaded.counts()["pending"] == 0
    assert run.configuration_snapshot["harness_stage"] == "done"


async def test_attempt_two_separates_confirmed_from_observed_once(
    monkeypatch,
) -> None:
    entries = (
        _entry(1, "button", "Save settings"),
        _entry(2, "button", "Generate preview"),
    )
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)

    def broken(case, execution_id):
        return _result_for(case, execution_id, verdict="not_satisfied",
                           blocker="assertion_precondition_failed")

    script = {
        "Check Save settings": [broken, _worked],
        "Check Generate preview": [broken, broken],
    }
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script=script, calls=calls)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    by_name = {item.name: item for item in loaded.ordered_items()}
    # Reproduced in a fresh context → broken (confirmed).
    assert by_name["Generate preview"].status == "broken"
    assert by_name["Generate preview"].attempts == 2
    # Not reproduced → observed-once tier: not counted as confirmed,
    # full trace of both executions retained.
    seen_once = by_name["Save settings"]
    assert seen_once.status == "could_not_check"
    assert seen_once.locator.get("tier") == "observed_once"
    assert seen_once.attempts == 2
    # Both executions are in the trace: per attempt, the execution id
    # plus one artifact id per assertion (2 assertions per case).
    assert len(seen_once.evidence_refs) == 6
    assert calls.count("Check Save settings") == 2
    assert calls.count("Check Generate preview") == 2


async def test_one_opaque_confirmation_parks_one_item_only(monkeypatch) -> None:
    entries = (
        _entry(1, "button", "Search"),
        _entry(2, "button", "Confirm booking"),
        _entry(3, "button", "Save settings"),
    )
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)

    def takeover(case, execution_id):
        return _result_for(case, execution_id, verdict="unverified",
                           status="policy_blocked",
                           blocker="human_takeover_required")

    script = {
        "Check Search": _worked,
        "Check Confirm booking": takeover,
        "Check Save settings": _worked,
    }
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script=script, calls=calls)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    by_name = {item.name: item for item in loaded.ordered_items()}
    assert by_name["Confirm booking"].status == "needs_human_login"
    assert by_name["Search"].status == "worked"
    assert by_name["Save settings"].status == "worked"
    # The run completed the rest of the list instead of parking whole.
    assert run.configuration_snapshot["harness_stage"] == "done"
    assert run.status == "queued"


async def test_irreversible_items_are_inventoried_never_executed(
    monkeypatch,
) -> None:
    entries = (
        _entry(1, "button", "Search"),
        _entry(2, "button", "Delete account"),
        _entry(3, "button", "Pay now"),
        _entry(4, "button", "Send invite"),
    )
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)
    script = {"Check Search": _worked}
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script=script, calls=calls)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    assert calls == ["Check Search"]
    by_name = {item.name: item for item in loaded.ordered_items()}
    for name in ("Delete account", "Pay now", "Send invite"):
        assert by_name[name].status == "not_checked"
        assert by_name[name].blocker == (
            "not exercised — requires approval or test mode"
        )
    assert sum(loaded.counts().values()) == 4


async def test_login_wall_parks_then_resumes_the_same_session(monkeypatch) -> None:
    login_entries = (
        _entry(1, "link", "Sign in"),
        _entry(2, "textbox", "Username"),
        _entry(3, "textbox", "Password"),
        _entry(4, "button", "Continue"),
    )
    dashboard_entries = (
        _entry(1, "link", "Admin console"),
        _entry(2, "textbox", "Display name"),
        _entry(3, "button", "Save settings"),
    )
    controller = _FakeInventoryController(
        pages={INVENTORY_URL: login_entries}, start_url=INVENTORY_URL,
        dashboard_entries=dashboard_entries,
    )

    def continue_result(case, execution_id):
        if controller.logged_in:
            return _worked(case, execution_id)
        return _result_for(case, execution_id, verdict="unverified",
                           status="policy_blocked",
                           blocker="authentication_challenge_blocked")

    script = {
        "Check Sign in": _worked,
        "Check Username": _worked,
        "Check Password": _worked,
        "Check Continue": continue_result,
        "Check Admin console": _worked,
        "Check Display name": _worked,
        "Check Save settings": _worked,
    }
    target_id = uuid4()
    run_id = uuid4()
    run, session, request = _inventory_run(
        run_id, start_url=INVENTORY_URL, target_id=target_id,
    )
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script=script, calls=calls)

    # First dispatch: the run parks at the login wall (asserted in
    # harness_state); the items behind the wall are deferred, not failed.
    await harness_run.execute_harness_run(request=request, session=session)
    assert run.status == "awaiting_human"
    assert run.configuration_snapshot["harness_stage"] == "needs_login"
    # U-P4: the park carries its deadline for the countdown/Extend UI.
    park_meta = run.configuration_snapshot["harness_park"]
    assert park_meta["deadline_at"] > park_meta["parked_at"]
    parked = await load_harness_state(session, run_id)
    assert parked is not None
    by_name = {item.name: item for item in parked.ordered_items()}
    assert by_name["Continue"].status == "needs_human_login"
    assert by_name["Sign in"].status == "worked"

    # Scripted human login through the takeover path, then resume:
    # the same run takes the broker-held session (zero new handoffs),
    # the inventory reads the logged-in app, and the post-login items
    # complete.
    controller.complete_human_login()
    await harness_run.execute_harness_run(request=request, session=session)
    assert controller.takes == ["harness_inventory"]
    assert True in controller.index_authenticated
    assert run.configuration_snapshot["harness_stage"] == "done"
    resumed = await load_harness_state(session, run_id)
    assert resumed is not None
    assert len(resumed.items) == 7
    assert resumed.counts()["worked"] == 7
    assert resumed.counts()["pending"] == 0
    assert resumed.counts()["needs_human_login"] == 0

    # After the broker TTL expires, a fresh run parks again instead
    # of failing.
    controller.expire_broker()
    run2_id = uuid4()
    run2, session2, request2 = _inventory_run(
        run2_id, start_url=INVENTORY_URL, target_id=target_id,
    )
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script=script, calls=calls)
    await harness_run.execute_harness_run(request=request2, session=session2)
    assert run2.status == "awaiting_human"
    assert run2.configuration_snapshot["harness_stage"] == "needs_login"


async def test_live_login_recrawls_the_app_behind_the_wall_in_one_dispatch(
    monkeypatch,
) -> None:
    """U-P4: when a human logs in DURING an item (the inline wait on
    the Room), the driver re-crawls in the same session, authenticated
    — the post-login items are discovered and checked in the SAME
    dispatch, not deferred to a later run."""
    login_entries = (
        _entry(1, "link", "Sign in"),
        _entry(2, "textbox", "Username"),
        _entry(3, "textbox", "Password"),
        _entry(4, "button", "Continue"),
    )
    dashboard_entries = (
        _entry(1, "link", "Admin console"),
        _entry(2, "textbox", "Display name"),
        _entry(3, "button", "Save settings"),
    )
    controller = _FakeInventoryController(
        pages={INVENTORY_URL: login_entries}, start_url=INVENTORY_URL,
        dashboard_entries=dashboard_entries,
    )

    def continue_with_login(case, execution_id):
        controller.logged_in = True
        return _worked(case, execution_id).model_copy(
            update={"human_wait_ms": 5000},
        )

    script = {
        "Check Sign in": _worked,
        "Check Username": _worked,
        "Check Password": _worked,
        "Check Continue": continue_with_login,
        "Check Admin console": _worked,
        "Check Display name": _worked,
        "Check Save settings": _worked,
    }
    run_id = uuid4()
    run, session, request = _inventory_run(
        run_id, start_url=INVENTORY_URL, target_id=uuid4(),
    )
    calls: list[str] = []
    _install_inventory_doubles(
        monkeypatch, controller=controller, script=script, calls=calls,
    )
    await harness_run.execute_harness_run(request=request, session=session)
    assert run.status != "awaiting_human"
    final = await load_harness_state(session, run_id)
    assert final is not None
    assert len(final.items) == 7
    assert final.counts()["worked"] == 7
    assert True in controller.index_authenticated


async def test_budget_exhausted_item_is_timed_out_on_the_record_and_could_not_check_on_the_board(
    monkeypatch,
) -> None:
    """D-1: a fake executor returning ``budget_exhausted`` for one item.

    The execution record for that item must be finished as ``timed_out``
    (the ``budget_exhausted`` -> ``timed_out`` translation in
    ``harness_run.py``), while the board item itself lands on
    ``could_not_check`` — ``ItemStatus`` has no ``timed_out`` value
    (``harness_state.py``), so the item cannot carry that word; the
    timed-out fact lives on the execution record only. The remaining
    items still complete and the run finishes.
    """
    entries = (
        _entry(1, "button", "Search"),
        _entry(2, "button", "Save settings"),
    )
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)

    def exhausted(case, execution_id):
        return _result_for(case, execution_id, verdict="unverified",
                           status="budget_exhausted", blocker="action_limit")

    script = {
        "Check Search": exhausted,
        "Check Save settings": _worked,
    }
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script=script, calls=calls)
    # Retain the ExecutionRepository double so the test can read back
    # the status each execution was finished with.
    factory = harness_run.ExecutionRepository
    seen: list[Mock] = []

    def recording(session):
        repo = factory(session)
        seen.append(repo)
        return repo

    monkeypatch.setattr(harness_run, "ExecutionRepository", recording)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    by_name = {item.name: item for item in loaded.ordered_items()}
    assert by_name["Search"].status == "could_not_check"
    assert by_name["Search"].blocker == "action_limit"
    assert by_name["Save settings"].status == "worked"
    assert calls == ["Check Search", "Check Save settings"]
    assert sum(loaded.counts().values()) == 2
    assert loaded.counts()["pending"] == 0
    assert run.configuration_snapshot["harness_stage"] == "done"
    assert len(seen) == 1
    finished = seen[0].finish_agent_execution.await_args_list
    # The bootstrap journey's skipped accounting record finishes first
    # (journey-result wiring); the two item records follow, in order.
    assert len(finished) == 3
    assert finished[0].kwargs["status"] == "skipped"
    assert finished[1].kwargs["status"] == "timed_out"
    assert finished[2].kwargs["status"] == "completed"


async def test_completed_harness_run_publishes_a_journey_result_for_every_journey(
    monkeypatch,
) -> None:
    """Evaluation reads one journey.result per journey; a completed
    harness run must publish them all, or no report can ever be built."""
    run_id = uuid4()
    run, session, request = _fixture_run(run_id)
    calls: list[str] = []
    events = _install_driver_doubles(monkeypatch, twin="broken", calls=calls)
    # The driver publishes journey results through its own repository
    # handle; route it into the same capture as the harness.* events.
    monkeypatch.setattr(
        harness_run, "RunEventRepository", lambda _: events, raising=False,
    )
    record = PersistedJourneyRecord(
        uuid4(), uuid4(), uuid4(),
        "browser_discovery__observe_starting_page", 10000,
    )
    monkeypatch.setattr(
        harness_run, "PlanRepository",
        lambda _: Mock(create_auth_bootstrap=AsyncMock(return_value=record)),
    )
    await harness_run.execute_harness_run(request=request, session=session)
    published = [
        call.kwargs
        for call in events.create.await_args_list
        if call.kwargs["event_type"] == "journey.result"
    ]
    by_journey = {entry["journey_id"]: entry for entry in published}
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    assert run.configuration_snapshot["harness_stage"] == "done"
    for item in loaded.ordered_items():
        entry = by_journey.get(UUID(str(item.journey_id)))
        assert entry is not None, f"no journey.result published for {item.case_id}"
        assert entry["execution_id"] is not None
        payload = entry["payload"]
        assert payload["journey_key"] == item.case_id
        if item.status == "worked":
            assert payload["status"] == "completed"
            assert payload["outcome"] == "passed"
        elif item.status == "broken":
            assert payload["status"] == "completed"
            assert payload["outcome"] == "failed"
            unsatisfied = [
                evidence for evidence in payload["criterion_evidence"]
                if evidence["status"] == "unsatisfied"
            ]
            assert unsatisfied
            assert all(evidence["evidence_step_ids"] for evidence in unsatisfied)
        elif item.status == "could_not_check":
            assert payload["outcome"] == "inconclusive"
        elif item.status == "blocked":
            assert payload["status"] == "policy_blocked"
            assert payload["outcome"] is None
    # The discovery/bootstrap journey carries persona ownership only; it
    # is accounted for as skipped, never as a check that passed or failed.
    bootstrap = by_journey.get(record.journey_id)
    assert bootstrap is not None
    assert bootstrap["execution_id"] is not None
    assert bootstrap["payload"]["status"] == "skipped"


async def test_completed_harness_run_publishes_a_board_result_for_every_item(
    monkeypatch,
) -> None:
    """The unified contract: exactly one board.item.result per Board
    item, carrying the item's final Board status (U-P1-04)."""
    run_id = uuid4()
    run, session, request = _fixture_run(run_id)
    calls: list[str] = []
    events = _install_driver_doubles(monkeypatch, twin="broken", calls=calls)
    monkeypatch.setattr(
        harness_run, "RunEventRepository", lambda _: events, raising=False,
    )
    record = PersistedJourneyRecord(
        uuid4(), uuid4(), uuid4(),
        "browser_discovery__observe_starting_page", 10000,
    )
    monkeypatch.setattr(
        harness_run, "PlanRepository",
        lambda _: Mock(create_auth_bootstrap=AsyncMock(return_value=record)),
    )
    await harness_run.execute_harness_run(request=request, session=session)
    published = [
        call.kwargs["payload"]
        for call in events.create.await_args_list
        if call.kwargs["event_type"] == "board.item.result"
    ]
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    by_item = {p["board_item_id"]: p for p in published}
    assert len(published) == len(loaded.items)
    for item in loaded.ordered_items():
        payload = by_item[item.item_id]
        assert payload["run_kind"] == "explore_test"
        assert payload["board_version"] == 2
        assert payload["board_status"] == item.status
        assert payload["state_id"] == item.state_id
        assert payload["quotes"] == []
        assert payload["verdict_rows"] == []
        assert payload["js_errors"] == []
        if item.status in {"worked", "broken"}:
            assert payload["assertions"], item.case_id


async def test_safety_skipped_items_publish_skipped_journey_results(
    monkeypatch,
) -> None:
    """An item the safety gate never exercises still owes evaluation a
    journey.result (status skipped), backed by a real execution record."""
    entries = (
        _entry(1, "button", "Search"),
        _entry(2, "button", "Delete account"),
    )
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)
    script = {"Check Search": _worked}
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    events = _install_inventory_doubles(monkeypatch, controller=controller,
                                        script=script, calls=calls)
    monkeypatch.setattr(
        harness_run, "RunEventRepository", lambda _: events, raising=False,
    )
    executions = Mock(create_agent_execution=AsyncMock(),
                      finish_agent_execution=AsyncMock(),
                      create_browser_session=AsyncMock(),
                      mark_browser_session_closed=AsyncMock(),
                      rebind_browser_session=AsyncMock())
    monkeypatch.setattr(harness_run, "ExecutionRepository", lambda _: executions)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    assert calls == ["Check Search"]
    skipped = next(
        item for item in loaded.ordered_items() if item.status == "not_checked"
    )
    published = [
        call.kwargs
        for call in events.create.await_args_list
        if call.kwargs["event_type"] == "journey.result"
    ]
    entry = next(
        (e for e in published if e["journey_id"] == UUID(str(skipped.journey_id))),
        None,
    )
    assert entry is not None
    assert entry["execution_id"] is not None
    assert entry["payload"]["status"] == "skipped"
    assert entry["payload"]["outcome"] is None
    finishes = [
        call.kwargs for call in executions.finish_agent_execution.await_args_list
    ]
    assert any(
        finish["execution_id"] == entry["execution_id"]
        and finish["status"] == "skipped"
        for finish in finishes
    )


# === end of harness tests ===
