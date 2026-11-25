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
from markettwin_execution_orchestrator.browser.errors import (
    BrowserSessionNotFoundError,
)
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
from markettwin_execution_orchestrator.workflow.coverage_delta import (
    build_coverage_delta,
)
from markettwin_shared.deep_testing import AssertionResult, CaseExecutionResult


@pytest.fixture(autouse=True)
def isolate_lead_model(monkeypatch):
    monkeypatch.setattr(harness_run, "review_checkpoint", AsyncMock(return_value={
        "decision": "continue", "reason": "Fixture", "source": "test",
    }))


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
    session = Mock(get=AsyncMock(return_value=run),
                   scalar=AsyncMock(side_effect=_room_scalar), add=Mock(),
                   flush=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock())
    request = MarketTwinRunRequest(
        run_id=run_id, study_brief="Check the controlled benchmark fixture",
        target_snapshot={}, start_url=FIXTURE_URL,
        allowed_origins=(AllowedOrigin("http", "127.0.0.1", 5191),),
        network_policy="local_development",
        fixture_truth=True,
    )
    return run, session, request


async def _room_scalar(statement):
    if "execution_steps" in str(statement):
        return None
    if "run_events" in str(statement):
        # Offsite supervision state restore: no prior offsite events.
        return None
    return 1 if "max(" in str(statement) else uuid4()


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


@pytest.mark.parametrize("saved_step", [None, 42])
async def test_kill_and_resume_checks_recorded_input_before_replaying(
    monkeypatch, saved_step,
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
    running = next(item for item in interrupted.items.values() if item.status == "running")

    async def scalar(statement):
        if "execution_steps" in str(statement):
            return saved_step
        return await _room_scalar(statement)

    session.scalar.side_effect = scalar

    monkeypatch.setattr(harness_run, "execute_test_case", real_execute)
    results = await harness_run.execute_harness_run(request=request, session=session)
    expected = set(GROUND_TRUTH)
    if saved_step is not None:
        expected.remove(running.case_id)
    assert len(results) == len(expected) - 2
    assert set(calls) == expected
    assert len(calls) == len(expected)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    assert loaded.counts()["pending"] == 0
    assert loaded.counts()["running"] == 0
    if saved_step is not None:
        recovered = loaded.items[running.item_id]
        assert recovered.status == "could_not_check"
        assert "Verify the effect" in recovered.blocker
        assert recovered.locator["board_result_published"] is True
    finished = [
        call.kwargs["payload"]["item_id"]
        for call in events.create.await_args_list
        if call.kwargs["event_type"] == "harness.item.finished"
    ]
    assert len(finished) == len(expected)
    assert len(set(finished)) == len(expected)


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


def test_unnamed_controls_become_structural_items() -> None:
    # Doc 24 section 6.2 (supersedes the old skip-at-ingest rule):
    # unnamed controls form structural items, accounted
    # could_not_check/unnamed_control — never silently dropped.
    from markettwin_execution_orchestrator.workflow.harness_items import (
        case_for_item,
        ingest_page_index,
        structural_reason,
    )

    board = new_harness_state()
    items = ingest_page_index(board, url=INDEX_URL, entries=[
        {"role": "button", "name": ""}, {"role": "link", "name": "  "},
        {"role": "button", "name": "Save"},
    ])
    named = [item for item in items if item.name]
    structural = [item for item in items if not item.name]
    assert [item.name for item in named] == ["Save"]
    assert len(structural) == 2
    for item in structural:
        assert item.locator["structural_identity"] is True
        assert structural_reason(item) == "unnamed_control"
    case_for_item(item=named[0], state_url=INDEX_URL, feature_key="board",
                  start_url=INDEX_URL)


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
        assert case.expected[0].after_step_ordinal == 0
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
    assert moved.expected[0].after_step_ordinal == 1


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
        self.authentication_handlers = {}
        self.pause_handlers = {}

    def bind_authentication_handler(self, handle, callback):
        self.authentication_handlers[handle.session_id] = callback

    def bind_cooperative_pause_handler(self, handle, callback):
        self.pause_handlers[handle.session_id] = callback

    async def __aenter__(self):
        return self

    async def page_links(self, **kwargs):
        return [target for (role, name), target in self.link_targets.items()
                if any(entry["role"] == role and entry["name"] == name
                       for entry in self.pages.get(self.current_url, ()))]

    async def discovery_page_signals(self, **kwargs):
        return {"text": "Synthetic application", "scripts": [], "controls": 3}

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
        if self.logged_in and not authenticated_session:
            from markettwin_execution_orchestrator.browser.errors import BrowserPolicyError
            raise BrowserPolicyError("Full-page discovery excludes authenticated sessions.")
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
        self.scroll_calls = getattr(self, "scroll_calls", 0) + 1
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

    async def create_worker_session(
        self, *, room_session_id, execution_id, journey_id, lane_index,
    ):
        return SimpleNamespace(session_id=uuid4())

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


def _lane_test_session(session):
    """The lane-session seam for the doubles: lanes run on the
    test's own session object (doc 18 section 11.1), whose close
    must be awaitable like the real AsyncSession's."""
    if not isinstance(session.close, AsyncMock):
        session.close = AsyncMock()
    return session


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
                       record_reproduced_failure=AsyncMock(),
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
    monkeypatch.setattr(harness_run, "_new_lane_session", _lane_test_session)
    return events


def _inventory_run(run_id, *, start_url, target_id=None):
    run = TestRun(
        id=run_id, status="queued",
        configuration_snapshot={"harness_run_mode": "standard"},
    )
    session = Mock(get=AsyncMock(return_value=run),
                   scalar=AsyncMock(side_effect=_room_scalar), add=Mock(),
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


async def test_inventory_gate_resumes_the_same_room_before_indexing(monkeypatch) -> None:
    route = "http://127.0.0.1:5199/protected"
    controller = _FakeInventoryController(
        pages={route: ()}, start_url=route,
        dashboard_entries=(_entry(1, "button", "Search"),),
    )
    run_id = uuid4()
    _, session, request = _inventory_run(run_id, start_url=route, target_id=uuid4())
    calls: list[str] = []
    _install_inventory_doubles(
        monkeypatch, controller=controller, script={"Check Search": _worked}, calls=calls,
    )
    original_navigate = controller.navigate
    resumptions = []

    async def handoff(**kwargs):
        assert kwargs["handle"] == controller.room_handle
        assert kwargs["expected_url"] == route
        controller.logged_in = True
        resumptions.append(kwargs["handle"].session_id)

    async def navigate(**kwargs):
        result = await original_navigate(**kwargs)
        if kwargs["url"] == route and not controller.logged_in:
            await controller.authentication_handlers[kwargs["session_id"]]()
        return result

    monkeypatch.setattr(controller, "navigate", navigate)
    monkeypatch.setattr(harness_run, "request_browser_handoff", handoff)

    await harness_run.execute_harness_run(request=request, session=session)

    assert resumptions == [controller.room_handle.session_id]
    assert controller.index_authenticated[0] is True
    assert calls == ["Check Search"]


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
    assert controller.scroll_calls == 2  # Initial reveal only, not after every control check.
    # Only Subscribe has an outcome assertion; readiness is not behavioral success.
    assert loaded.counts()["worked"] == 1
    assert loaded.counts()["could_not_check"] == 12
    assert sum(loaded.counts().values()) == 13
    assert loaded.counts()["pending"] == 0
    assert run.configuration_snapshot["harness_stage"] == "done"


async def test_inventory_crawl_skips_links_that_land_off_the_allowlist(monkeypatch) -> None:
    from markettwin_execution_orchestrator.browser.policy import validate_target_url

    class _PolicyController(_FakeInventoryController):
        async def navigate(self, *, session_id, url, **kwargs):
            validate_target_url(url, request.allowed_origins, request.network_policy)
            return await super().navigate(session_id=session_id, url=url, **kwargs)

    entries = (_entry(1, "link", "Help"), _entry(2, "button", "Save settings"))
    controller = _PolicyController(pages={INVENTORY_URL: entries}, start_url=INVENTORY_URL)
    controller.link_targets = {("link", "Help"): "https://help.other.test/"}
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller, calls=calls,
                               script={"Check Help": _worked, "Check Save settings": _worked})
    await harness_run.execute_harness_run(request=request, session=session)
    assert run.configuration_snapshot["harness_stage"] == "done"
    assert sorted(calls) == ["Check Help", "Check Save settings"]


async def test_inventory_tests_first_page_before_discovering_next(monkeypatch):
    next_url = INVENTORY_URL + "/details"
    calls = []

    class Controller(_FakeInventoryController):
        async def navigate(self, *, session_id, url, **kwargs):
            if url == next_url:
                assert "Check Save settings" in calls
            return await super().navigate(session_id=session_id, url=url, **kwargs)

        async def click(self, **kwargs):
            pytest.fail("Discovery must not click links")

    controller = Controller(pages={
        INVENTORY_URL: (_entry(1, "button", "Save settings"), _entry(2, "link", "Details")),
        next_url: (_entry(1, "button", "Save preferences"),),
    }, start_url=INVENTORY_URL)
    controller.link_targets = {("link", "Details"): next_url}
    run, session, request = _inventory_run(uuid4(), start_url=INVENTORY_URL)
    _install_inventory_doubles(monkeypatch, controller=controller, calls=calls,
        script={name: _worked for name in ("Check Save settings", "Check Details", "Check Save preferences")})
    await harness_run.execute_harness_run(request=request, session=session)
    assert "Check Save preferences" in calls


async def test_inventory_gives_next_route_a_turn_before_draining_busy_page(monkeypatch):
    next_url = INVENTORY_URL + "/details"
    controls = [f"Search option {index}" for index in range(1, 8)]
    calls: list[str] = []

    class Controller(_FakeInventoryController):
        async def navigate(self, *, session_id, url, **kwargs):
            if url == next_url and "Check Save preferences" not in calls:
                assert 0 < len(calls) <= 4
            return await super().navigate(session_id=session_id, url=url, **kwargs)

    controller = Controller(pages={
        INVENTORY_URL: tuple(_entry(index, "button", name)
                             for index, name in enumerate(controls, 1)),
        next_url: (_entry(1, "button", "Save preferences"),),
    }, start_url=INVENTORY_URL)
    run, session, request = _inventory_run(uuid4(), start_url=INVENTORY_URL)
    request = replace(request, app_plan={"routes": [INVENTORY_URL, next_url], "checks": []})
    _install_inventory_doubles(monkeypatch, controller=controller, calls=calls, script={
        f"Check {name}": _worked for name in [*controls, "Save preferences"]
    })

    await harness_run.execute_harness_run(request=request, session=session)

    assert sorted(calls) == sorted(f"Check {name}" for name in [*controls, "Save preferences"])
    assert run.configuration_snapshot["discovery_frontier"]["pending"] == []


async def test_inventory_return_commits_database_binding_before_navigation(monkeypatch):
    class Controller(_FakeInventoryController):
        bound_execution = None

        async def rebind_session(self, **kwargs):
            self.bound_execution = kwargs["execution_id"]
            return await super().rebind_session(**kwargs)

        async def navigate(self, **kwargs):
            if self.bound_execution is not None:
                assert repository.rebind_browser_session.await_args.kwargs["execution_id"] == self.bound_execution
            return await super().navigate(**kwargs)

    controller = Controller(pages={INVENTORY_URL: (_entry(1, "button", "Save settings"),)}, start_url=INVENTORY_URL)
    run, session, request = _inventory_run(uuid4(), start_url=INVENTORY_URL)
    _install_inventory_doubles(monkeypatch, controller=controller, calls=[],
                               script={"Check Save settings": _worked})
    repository = harness_run.ExecutionRepository(session)
    monkeypatch.setattr(harness_run, "ExecutionRepository", lambda _: repository)
    await harness_run.execute_harness_run(request=request, session=session)


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


@pytest.mark.parametrize(("confirmation_id", "expected_status"), [
    ("target_enabled", "broken"),
    ("target_visible", "could_not_check"),
])
async def test_proof_requires_the_same_failed_assertion(
    monkeypatch, confirmation_id, expected_status,
) -> None:
    entries = (_entry(1, "button", "Search"),)
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)

    def failure(assertion_id):
        def result(case, execution_id):
            failed = _result_for(case, execution_id, verdict="not_satisfied")
            return CaseExecutionResult.model_validate({
                **failed.model_dump(),
                "assertion_results": tuple(a for a in failed.assertion_results
                                           if a.assertion_id == assertion_id),
            })
        return result

    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
        script={"Check Search": [failure("target_enabled"), failure(confirmation_id)]},
        calls=calls)
    await harness_run.execute_harness_run(request=request, session=session)
    board = await load_harness_state(session, run_id)
    assert board is not None
    item = next(iter(board.items.values()))
    assert item.status == expected_status
    assert item.attempts == 2
    assert len(item.evidence_refs) == 4
    if expected_status == "could_not_check":
        assert item.locator["tier"] == "observed_once"


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
    states = Mock(mark_running=AsyncMock(), mark_completed=AsyncMock())
    monkeypatch.setattr(harness_run, "RunStateRepository", lambda _: states)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    by_name = {item.name: item for item in loaded.ordered_items()}
    assert by_name["Confirm booking"].status == "needs_human_login"
    assert by_name["Search"].status == "could_not_check"
    assert by_name["Search"].locator["tier"] == "outcome_not_established"
    assert by_name["Save settings"].status == "could_not_check"
    # Other work may finish, but the owner's Close contract forbids a
    # completed run while any Board item still needs human input.
    assert run.configuration_snapshot["harness_stage"] == "needs_login"
    assert run.status == "awaiting_human"
    assert run.configuration_snapshot["harness_park"]["item_id"] == (
        by_name["Confirm booking"].item_id
    )
    states.mark_completed.assert_not_awaited()


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
    assert by_name["Sign in"].status == "could_not_check"

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
    assert resumed.counts()["could_not_check"] == 7
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


async def test_failed_handoff_does_not_recrawl_as_authenticated(monkeypatch):
    controller = _FakeInventoryController(
        pages={INVENTORY_URL: (_entry(1, "button", "Show details"),)},
        start_url=INVENTORY_URL)

    def failed_handoff(case, execution_id):
        return _worked(case, execution_id).model_copy(update={
            "human_wait_ms": 1000, "execution_status": "policy_blocked",
            "verdict": "unverified", "blocker": "policy_blocked"})

    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    _install_inventory_doubles(monkeypatch, controller=controller,
        script={"Check Show details": failed_handoff}, calls=[])
    await harness_run.execute_harness_run(request=request, session=session)
    assert True not in controller.index_authenticated
    assert run.configuration_snapshot["lead_stop"]["source"] == "handoff"


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
    assert final.counts()["could_not_check"] == 7
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
    assert by_name["Save settings"].status == "could_not_check"
    # S2: with a worker lane live, the two items' executions start
    # concurrently (one laned, one on the Room) — the pin is that
    # both were attempted and accounted, not their start order.
    assert sorted(calls) == ["Check Save settings", "Check Search"]
    assert sum(loaded.counts().values()) == 2
    assert loaded.counts()["pending"] == 0
    assert run.configuration_snapshot["harness_stage"] == "done"
    assert len(seen) == 1
    finished = seen[0].finish_agent_execution.await_args_list
    # The bootstrap journey's skipped accounting record finishes first
    # (journey-result wiring). S2: the two items finish in either
    # order (lane vs Room), so the pin is the status multiset — the
    # exhausted item's execution is finished timed_out on the record.
    assert len(finished) == 4
    assert finished[0].kwargs["status"] == "skipped"
    assert sorted(f.kwargs["status"] for f in finished[1:]) == [
        "completed", "completed", "timed_out"]


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


async def test_room_execution_uses_a_new_attempt_on_start_and_resume(monkeypatch) -> None:
    """Discovery accounting and each Room must have distinct persisted attempts."""
    controller = _FakeInventoryController(
        pages={INVENTORY_URL: (_entry(1, "button", "Search"),)},
        start_url=INVENTORY_URL)
    run_id, journey_id = uuid4(), uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script={"Check Search": _worked}, calls=[])
    record = PersistedJourneyRecord(journey_id, uuid4(), uuid4(),
                                    "browser_discovery__observe_starting_page", 10000)
    monkeypatch.setattr(harness_run, "PlanRepository", lambda _: Mock(
        create_auth_bootstrap=AsyncMock(return_value=record)))
    attempts = []
    execution_keys = set()

    async def create_execution(**kwargs):
        attempt = kwargs.get("attempt_number", 1)
        key = (kwargs["journey_id"], attempt)
        if key in execution_keys:
            raise ValueError("uq_agent_executions_journey_attempt")
        execution_keys.add(key)
        if kwargs["journey_id"] == journey_id:
            attempts.append(attempt)

    async def scalar(statement):
        if "run_events" in str(statement):
            return None
        if "max(" in str(statement):
            assert journey_id in statement.compile().params.values()
            return max(attempts, default=0)
        return journey_id

    session.scalar = AsyncMock(side_effect=scalar)
    executions = Mock(create_agent_execution=AsyncMock(side_effect=create_execution),
                      finish_agent_execution=AsyncMock(),
                      create_browser_session=AsyncMock(),
                      mark_browser_session_closed=AsyncMock(),
                      rebind_browser_session=AsyncMock())
    monkeypatch.setattr(harness_run, "ExecutionRepository", lambda _: executions)
    await harness_run.execute_harness_run(request=request, session=session)
    assert attempts == [1, 2]
    room = next(call.kwargs for call in executions.create_agent_execution.await_args_list
                if call.kwargs["runtime_name"] == "harness_inventory_v1")
    executions.finish_agent_execution.assert_any_await(
        execution_id=room["execution_id"], status="completed",
    )
    # A resumed worker must not reuse the previous Room's attempt either.
    await harness_run.execute_harness_run(request=request, session=session)
    assert attempts == [1, 2, 3]


async def test_empty_entry_continues_to_seeded_route(monkeypatch) -> None:
    next_url = INVENTORY_URL + "/details"
    controller = _FakeInventoryController(
        pages={INVENTORY_URL: (), next_url: (_entry(1, "button", "Search"),)},
        start_url=INVENTORY_URL,
    )
    run, session, request = _inventory_run(uuid4(), start_url=INVENTORY_URL)
    request = replace(request, app_plan={"routes": [INVENTORY_URL, next_url], "checks": []})
    calls: list[str] = []
    _install_inventory_doubles(
        monkeypatch, controller=controller, calls=calls, script={"Check Search": _worked},
    )

    await harness_run.execute_harness_run(request=request, session=session)

    assert calls == ["Check Search"]
    assert run.configuration_snapshot["discovery_frontier"] == {
        "visited": [INVENTORY_URL, next_url], "pending": [],
    }
    state = await load_harness_state(session, run.id)
    assert state is not None
    assert state.counts()["pending"] == 0
    assert len(state.items) == 1


async def test_empty_discovery_stops_before_evaluation_and_finishes_room(monkeypatch) -> None:
    from markettwin_shared.run_failure import failure_event_payload

    controller = _FakeInventoryController(pages={INVENTORY_URL: ()},
                                          start_url=INVENTORY_URL)
    run, session, request = _inventory_run(uuid4(), start_url=INVENTORY_URL)
    events = _install_inventory_doubles(monkeypatch, controller=controller,
                                        script={}, calls=[])
    executions = Mock(create_agent_execution=AsyncMock(),
                      finish_agent_execution=AsyncMock(),
                      create_browser_session=AsyncMock(),
                      mark_browser_session_closed=AsyncMock(),
                      rebind_browser_session=AsyncMock())
    states = Mock(mark_running=AsyncMock(), mark_completed=AsyncMock())
    monkeypatch.setattr(harness_run, "ExecutionRepository", lambda _: executions)
    monkeypatch.setattr(harness_run, "RunStateRepository", lambda _: states)
    with pytest.raises(RuntimeError) as caught:
        await harness_run.execute_harness_run(request=request, session=session)
    assert failure_event_payload(caught.value)["code"] == "browser_discovery_empty"
    states.mark_completed.assert_not_awaited()
    assert not any(call.kwargs["event_type"] == "harness.run.evaluating"
                   for call in events.create.await_args_list)
    room = next(call.kwargs for call in executions.create_agent_execution.await_args_list
                if call.kwargs["runtime_name"] == "harness_inventory_v1")
    executions.finish_agent_execution.assert_any_await(
        execution_id=room["execution_id"], status="failed",
        error_code="browser_discovery_empty",
    )
    executions.mark_browser_session_closed.assert_awaited_once()
    assert run.configuration_snapshot["harness_state"]["items"] == {}


@pytest.mark.parametrize("fixture, code", [
    ("wall", "browser_discovery_checkpoint"),
    ("empty", "browser_discovery_empty"),
    ("normal", None),
    ("exception", "execution_failed"),
])
async def test_inventory_fixture_always_finishes_its_execution(monkeypatch, fixture, code):
    """Checkpoint HTML is not an app; blank HTML is a distinct failure."""
    fixtures = {
        "wall": {"text": "Please enable JS and disable any ad blocker",
                 "scripts": ["https://ct.captcha-delivery.com/c.js"], "controls": 0},
        "empty": {"text": "", "scripts": [], "controls": 0},
        "normal": {"text": "Search our catalog", "scripts": [], "controls": 1},
        "exception": {"text": "", "scripts": [], "controls": 0},
    }
    entries = (_entry(1, "button", "Search"),) if fixture == "normal" else ()
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries}, start_url=INVENTORY_URL)
    controller.discovery_page_signals = AsyncMock(return_value=fixtures[fixture])
    if fixture == "exception":
        controller.navigate = AsyncMock(side_effect=RuntimeError("Synthetic navigation failure"))
    run, session, request = _inventory_run(uuid4(), start_url=INVENTORY_URL)
    _install_inventory_doubles(monkeypatch, controller=controller,
                              script={"Check Search": _worked}, calls=[])
    executions = Mock(create_agent_execution=AsyncMock(), finish_agent_execution=AsyncMock(),
        create_browser_session=AsyncMock(), mark_browser_session_closed=AsyncMock(),
        rebind_browser_session=AsyncMock())
    states = Mock(mark_running=AsyncMock(), mark_completed=AsyncMock())
    monkeypatch.setattr(harness_run, "ExecutionRepository", lambda _: executions)
    monkeypatch.setattr(harness_run, "RunStateRepository", lambda _: states)
    if code:
        from markettwin_shared.run_failure import failure_event_payload
        with pytest.raises(RuntimeError) as error:
            await harness_run.execute_harness_run(request=request, session=session)
        assert failure_event_payload(error.value)["code"] == code
        states.mark_completed.assert_not_awaited()
    else:
        await harness_run.execute_harness_run(request=request, session=session)
        states.mark_completed.assert_awaited_once()
    room = next(call.kwargs for call in executions.create_agent_execution.await_args_list
                if call.kwargs["runtime_name"] == "harness_inventory_v1")
    finishes = [call.kwargs for call in executions.finish_agent_execution.await_args_list
                if call.kwargs["execution_id"] == room["execution_id"]]
    assert len(finishes) == 1
    assert finishes[0]["status"] == ("completed" if code is None else "failed")


# === end of harness tests ===


async def test_register_items_persists_missions_before_journeys() -> None:
    """The journey's composite FK must reference an already persisted mission."""
    from markettwin_database.models import PersonaJourney, RunMission

    board = new_harness_state()
    page = board.add_state(url=INVENTORY_URL, elements=())
    entries = harness_run.v1_benchmark_work_list(INVENTORY_URL)[:2]
    pairs = []
    for entry in entries:
        case = harness_run.TestCaseSpec.model_validate(entry["case"])
        role, name, occurrence = entry["role_name"]
        item = board.add_item(state_id=page.state_id, case_id=case.case_id,
                              role=role, name=name, occurrence_index=occurrence)
        pairs.append((item, case))
    pending = []
    persisted_missions = set()
    persisted_journeys = []

    async def flush():
        # Independent mappers can flush journeys first; no ORM relationship
        # exists to guarantee their ordering within one flush.
        for row in pending:
            if isinstance(row, PersonaJourney):
                assert (row.test_run_id, row.mission_id) in persisted_missions
                persisted_journeys.append(row)
        persisted_missions.update((row.test_run_id, row.id) for row in pending
                                  if isinstance(row, RunMission))
        pending.clear()

    session = Mock(add=pending.append, add_all=pending.extend, flush=AsyncMock(side_effect=flush))
    run_id, persona_id = uuid4(), uuid4()
    await harness_run._register_items(session=session, run_id=run_id,
        persona_id=persona_id, first_ordinal=1, pairs=pairs)
    assert len(persisted_journeys) == 2
    assert {str(row.id) for row in persisted_journeys} == {item.journey_id for item, _ in pairs}


async def test_inventory_completion_names_the_unvisited_frontier(monkeypatch) -> None:
    """Issue 2 (D7): when the 20-page discovery cap stops the crawl, the
    pages it found but never visited are named in a
    harness.coverage.frontier event — counted in the open, never
    silently dropped from the coverage denominator."""
    page_urls = [f"{INVENTORY_URL}/p{i}" for i in range(1, 26)]
    start_entries = [_entry(1, "button", "Save settings")] + [
        _entry(i + 2, "link", f"Page {i}") for i in range(1, 26)
    ]
    pages = {INVENTORY_URL: tuple(start_entries)}
    for i, url in enumerate(page_urls, start=1):
        pages[url] = (_entry(1, "button", f"Widget {i}"),)
    controller = _FakeInventoryController(pages=pages, start_url=INVENTORY_URL)
    controller.link_targets = {
        ("link", f"Page {i}"): url for i, url in enumerate(page_urls, start=1)
    }
    script = {"Check Save settings": _worked}
    script.update({f"Check Page {i}": _worked for i in range(1, 26)})
    script.update({f"Check Widget {i}": _worked for i in range(1, 26)})
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    events = _install_inventory_doubles(monkeypatch, controller=controller,
                                        script=script, calls=calls)
    await harness_run.execute_harness_run(request=request, session=session)
    assert run.configuration_snapshot["harness_stage"] == "done"
    frontier = [call.kwargs["payload"] for call in events.create.await_args_list
                if call.kwargs.get("event_type") == "harness.coverage.frontier"]
    assert len(frontier) == 1
    assert frontier[0]["visited_count"] == 20
    assert frontier[0]["reason"] == "discovery_cap"
    assert sorted(frontier[0]["not_visited"]) == sorted(page_urls[19:])


# ---------------------------------------------------------------------------
# Issue 3 — outcome layer: the driver judges a generated item by what
# its action observably did (post-action re-observation + JS records),
# not by its enabled/visible assertions alone. The layer activates only
# when the controller carries the JS-error channel (harvest_js_records),
# so these tests use a fake that adds that channel to the scripted
# inventory controller; builders model effects by mutating the fake
# (page entries, current URL, JS buffer) before returning their result.
# ---------------------------------------------------------------------------


class _OutcomeController(_FakeInventoryController):
    """Scripted inventory controller plus the U-P6-03 JS channel.

    ``js_buffer`` is the session's pending JS records; every harvest
    returns and drains it, exactly like the real controller. One
    buffer serves every session id (room and proof alike): each
    window is drained before the next begins.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.js_buffer: list[SimpleNamespace] = []
        self.proof_session_id = None
        self.proof_entries = None

    def push_js(self, *, kind="pageerror", message="Boom", stack="stack"):
        self.js_buffer.append(SimpleNamespace(
            url=self.current_url, kind=kind, message=message, stack=stack))

    async def create_proof_session(self, **kwargs):
        handle = await super().create_proof_session(**kwargs)
        self.proof_session_id = handle.session_id
        return handle

    async def get_page_index(self, *, session_id, **kwargs):
        # The proof runs in a fresh context: its page state is its own
        # and never leaks into the Room's page (or the driver's
        # post-item re-inventory would discover it as a new state).
        if (session_id == self.proof_session_id
                and self.proof_entries is not None):
            saved = self.pages.get(self.current_url)
            self.pages[self.current_url] = self.proof_entries
            try:
                return await super().get_page_index(
                    session_id=session_id, **kwargs)
            finally:
                self.pages[self.current_url] = saved
        return await super().get_page_index(session_id=session_id, **kwargs)

    async def harvest_js_records(self, *, session_id, **kwargs):
        records, self.js_buffer = self.js_buffer, []
        return records


async def test_issue3_click_view_change_proves_worked(monkeypatch) -> None:
    entries = (_entry(1, "button", "Save settings"),)
    controller = _OutcomeController(pages={INVENTORY_URL: entries},
                                    start_url=INVENTORY_URL)

    def changer(case, execution_id):
        # The click visibly re-renders the page under the same URL.
        controller.pages[INVENTORY_URL] = (_entry(1, "button", "Settings saved"),)
        return _worked(case, execution_id)

    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script={"Check Save settings": changer},
                               calls=calls)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    item = next(iter(loaded.items.values()))
    # A satisfied click whose effect the re-observation can see is
    # worked — no confirmation run is needed.
    assert item.status == "worked"
    assert item.locator["outcome"] == "view_changed"
    assert calls == ["Check Save settings"]


async def test_same_url_revealed_control_replays_its_opener_for_both_attempts(monkeypatch):
    opener = _entry(1, "button", "Open details")
    search = _entry(2, "button", "Search details")
    controller = _OutcomeController(pages={INVENTORY_URL: (opener,)}, start_url=INVENTORY_URL)

    def open_details(case, execution_id):
        controller.pages[INVENTORY_URL] = (opener, search)
        return _worked(case, execution_id)

    def search_details(case, execution_id):
        assert [step.action for step in case.steps] == ["navigate", "click", "click"]
        assert [step.target.name for step in case.steps[1:]] == ["Open details", "Search details"]
        assert case.expected[0].after_step_ordinal == 2
        controller.pages[INVENTORY_URL] = (opener, search)
        # A fresh proof context needs the same visible state.
        controller.proof_entries = (opener, search)
        return _worked(case, execution_id)

    run_id = uuid4()
    _, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(
        monkeypatch, controller=controller, calls=calls,
        script={"Check Open details": open_details, "Check Search details": search_details},
    )
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert sum("button|Search details" in page.element_signature for page in loaded.states.values()) == 1
    assert calls == ["Check Open details", "Check Search details", "Check Search details"]
    item = next(item for item in loaded.items.values() if item.name == "Search details")
    assert item.status == "broken" and item.attempts == 2
    assert item.locator["entry_steps"][0]["target"]["name"] == "Open details"


async def test_issue3_do_nothing_button_reproduces_to_broken(monkeypatch) -> None:
    entries = (_entry(1, "button", "Save settings"),)
    controller = _OutcomeController(pages={INVENTORY_URL: entries},
                                    start_url=INVENTORY_URL)
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script={"Check Save settings": _worked},
                               calls=calls)
    execution_repository = harness_run.ExecutionRepository(session)
    monkeypatch.setattr(harness_run, "ExecutionRepository", lambda _: execution_repository)
    events = _capture_run_events(monkeypatch)
    checked_checkpoint = False

    async def check_commit():
        nonlocal checked_checkpoint
        if not checked_checkpoint and (published := _payloads(events, "board.item.result")):
            snapshot = run.configuration_snapshot["harness_state"]
            checkpoint = snapshot["items"][published[0]["board_item_id"]]
            assert checkpoint["status"] == "broken"
            assert checkpoint["locator"]["board_result_published"] is True
            checked_checkpoint = True

    session.commit.side_effect = check_commit
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    item = next(iter(loaded.items.values()))
    # Satisfied assertions, but the click observably does nothing —
    # and the fresh-context proof does nothing either: broken.
    assert item.status == "broken"
    assert item.locator["outcome_suspicion"] == "no_effect"
    assert item.locator["tier"] == "no_visible_effect_on_either_attempt"
    assert item.attempts == 2
    assert checked_checkpoint
    proof_id, execution_id = (UUID(value) for value in item.evidence_refs[:2])
    execution_repository.record_reproduced_failure.assert_awaited_once_with(
        execution_id=execution_id, proof_id=proof_id,
    )
    assert calls == ["Check Save settings", "Check Save settings"]


async def test_issue3_no_effect_not_reproduced_becomes_observed_once(
    monkeypatch,
) -> None:
    entries = (_entry(1, "button", "Save settings"),)
    controller = _OutcomeController(pages={INVENTORY_URL: entries},
                                    start_url=INVENTORY_URL)

    def changer(case, execution_id):
        # Only the proof session's page changes (fresh context): the
        # Room's page — and its re-inventory — never sees this.
        controller.proof_entries = (
            _entry(1, "button", "Save settings"),
            _entry(2, "button", "Saved"),
        )
        return _worked(case, execution_id)

    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script={"Check Save settings": [_worked, changer]},
                               calls=calls)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    item = next(iter(loaded.items.values()))
    # Attempt 1 showed no effect, but the proof run's click changed
    # the page: the suspicion does not reproduce.
    assert item.status == "could_not_check"
    assert item.locator["tier"] == "observed_once"
    assert "outcome_suspicion" not in item.locator
    assert item.attempts == 2


@pytest.mark.parametrize("role", ["link", "button"])
async def test_action_navigation_explains_disappearance_and_expands_inventory(monkeypatch, role) -> None:
    other_url = "http://127.0.0.1:5199/other.html"
    controller = _OutcomeController(
        pages={
            INVENTORY_URL: (_entry(1, role, "Help"),),
            other_url: (_entry(1, "button", "Search details"),),
        },
        start_url=INVENTORY_URL,
    )

    def vanished(case, execution_id):
        # The link navigated away, so the post-action visible check on
        # the link itself fails — the only failed assertion.
        base = _result_for(case, execution_id, verdict="not_satisfied")
        assertions = tuple(
            _assertion(
                case=case, expected=expected,
                status=("not_satisfied"
                        if expected.assertion_id == "target_visible"
                        else "satisfied"),
                execution_id=execution_id, step_id=10 + index)
            for index, expected in enumerate(case.expected)
        )
        controller.current_url = other_url
        return CaseExecutionResult.model_validate({
            **base.model_dump(), "assertion_results": assertions,
        })

    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script={"Check Help": vanished}, calls=calls)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    item = next(iter(loaded.items.values()))
    # The disappearance is explained by the navigation itself: the
    # link worked, and no proof execution is created.
    assert item.status == "worked"
    assert item.locator["outcome"] == "navigated"
    assert other_url in run.configuration_snapshot["discovery_frontier"]["visited"]
    assert calls[:2] == ["Check Help", "Check Search details"]
    assert item.attempts == 1


async def test_issue3_new_js_error_reproduces_to_broken_and_publishes(
    monkeypatch,
) -> None:
    entries = (_entry(1, "button", "Save settings"),)
    controller = _OutcomeController(pages={INVENTORY_URL: entries},
                                    start_url=INVENTORY_URL)

    def boom(case, execution_id):
        controller.push_js(message="TypeError: x is not a function")
        return _worked(case, execution_id)

    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    events = _install_inventory_doubles(monkeypatch, controller=controller,
                                        script={"Check Save settings": boom},
                                        calls=calls)
    monkeypatch.setattr(harness_run, "RunEventRepository", lambda _: events)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    item = next(iter(loaded.items.values()))
    # A satisfied click that throws a NEW page error — reproduced with
    # the same signature in the proof context — is broken.
    assert item.status == "broken"
    assert item.locator["outcome_suspicion"] == "js_error"
    assert item.attempts == 2
    # D6: the board result publishes the deciding attempt's errors.
    published = [
        call.kwargs["payload"]
        for call in events.create.await_args_list
        if call.kwargs["event_type"] == "board.item.result"
    ]
    assert len(published) == 1
    assert published[0]["board_status"] == "broken"
    assert published[0]["js_errors"]
    assert published[0]["js_errors"][0]["message"] == \
        "TypeError: x is not a function"


async def test_issue3_field_fill_success_is_worked(monkeypatch) -> None:
    entries = (_entry(1, "textbox", "Display name"),)
    controller = _OutcomeController(pages={INVENTORY_URL: entries},
                                    start_url=INVENTORY_URL)
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script={"Check Display name": _worked},
                               calls=calls)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    item = next(iter(loaded.items.values()))
    # A field's outcome is its fill's own success (the value read-back
    # stays unverified by design): satisfied + no error = worked.
    assert item.status == "worked"
    assert item.locator["outcome"] == "no_effect"
    assert calls == ["Check Display name"]


async def test_issue3_field_js_error_reproduces_to_broken(monkeypatch) -> None:
    entries = (_entry(1, "textbox", "Display name"),)
    controller = _OutcomeController(pages={INVENTORY_URL: entries},
                                    start_url=INVENTORY_URL)

    def boom(case, execution_id):
        controller.push_js(message="TypeError: x is not a function")
        return _worked(case, execution_id)

    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script={"Check Display name": boom},
                               calls=calls)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    item = next(iter(loaded.items.values()))
    assert item.status == "broken"
    assert item.locator["outcome_suspicion"] == "js_error"
    assert item.attempts == 2


async def test_issue3_baselined_js_record_is_not_an_outcome(monkeypatch) -> None:
    entries = (_entry(1, "textbox", "Display name"),)
    controller = _OutcomeController(pages={INVENTORY_URL: entries},
                                    start_url=INVENTORY_URL)
    # The route already throws this error on load: discovery's drain
    # folds it into the per-route baseline before any item runs.
    controller.push_js(message="Chunk load failed")

    def again(case, execution_id):
        controller.push_js(message="Chunk load failed")
        return _worked(case, execution_id)

    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script={"Check Display name": again},
                               calls=calls)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    item = next(iter(loaded.items.values()))
    # The same signature in the item's window is the route's history,
    # not the field's outcome: no suspicion is raised.
    assert item.status == "worked"
    assert item.locator["outcome"] == "no_effect"
    assert "outcome_suspicion" not in item.locator


async def test_failed_baseline_drain_cannot_confirm_an_old_js_error(monkeypatch):
    controller = _OutcomeController(
        pages={INVENTORY_URL: (_entry(1, "textbox", "Display name"),)},
        start_url=INVENTORY_URL,
    )
    controller.push_js(message="Old route error")
    original = controller.harvest_js_records
    calls = 0

    async def harvest(**kwargs):
        nonlocal calls
        calls += 1
        if calls <= 2:  # discovery and pre-action drains are unavailable
            raise RuntimeError("temporarily unavailable")
        return await original(**kwargs)

    controller.harvest_js_records = harvest
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script={"Check Display name": _worked}, calls=[])
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    item = next(iter(loaded.items.values()))
    assert item.status == "worked"
    assert "outcome_suspicion" not in item.locator


async def test_issue3_observation_failure_is_fail_open(monkeypatch) -> None:
    class _BlindOutcomeController(_OutcomeController):
        """Index reads fail once the case has run (discovery worked)."""

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.blind = False

        async def get_page_index(self, **kwargs):
            if self.blind:
                # One-shot: the outcome observation's first read
                # fails; the driver's later re-inventory reads —
                # which are not the observation — must still work.
                self.blind = False
                raise RuntimeError("Scripted index failure")
            return await super().get_page_index(**kwargs)

    entries = (_entry(1, "button", "Save settings"),)
    controller = _BlindOutcomeController(pages={INVENTORY_URL: entries},
                                         start_url=INVENTORY_URL)

    def blinding(case, execution_id):
        controller.blind = True
        return _worked(case, execution_id)

    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script={"Check Save settings": blinding},
                               calls=calls)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    item = next(iter(loaded.items.values()))
    # Observation failed, so the item keeps exactly the verdict its
    # assertions earned before Issue 3 — nothing is recorded.
    assert item.status == "could_not_check"
    assert item.locator["tier"] == "outcome_not_established"
    assert "outcome" not in item.locator


# --- Phase 1a consumption (spec 14 section 10.4): T-H1..T-H6 ---------

from dataclasses import replace

from markettwin_execution_orchestrator.browser.errors import (
    BrowserActionError,
    BrowserDiscoveryCheckpointError,
)

CHAIN_BASE = "http://127.0.0.1:5199"


def _map_block(*, routes, pages):
    return {
        "map_id": str(uuid4()), "version_number": 1,
        "release_state": "partial", "release_scope": "inventory",
        "built_at": "2026-11-13T12:00:00+00:00",
        "base_url": routes[0] if routes else "",
        "routes": list(routes), "routes_truncated": False,
        "pages": list(pages),
        "counts": {"expected": len(pages), "reachable": len(pages),
                   "blocked_auth": 0, "blocked_wall": 0, "gone": 0},
    }


def _map_page(url, *, status="fetch_ok", states=()):
    return {"url": url, "effective_url": url, "pattern": "/p",
            "status": status, "requires_auth": False, "states": list(states)}


def _capture_run_events(monkeypatch):
    """Capture the events harness_run writes through its own
    RunEventRepository (persist_harness_state events travel the
    harness_state repository the inventory doubles already install)."""
    events = Mock(create=AsyncMock())
    monkeypatch.setattr(harness_run, "RunEventRepository", lambda _: events)
    return events


def _payloads(events, event_type):
    return [call.kwargs["payload"] for call in events.create.await_args_list
            if call.kwargs["event_type"] == event_type]


def _chain_site(n):
    """A chain of n pages: each page links to the next and carries one
    button, so the crawl can only finish the chain by visiting every
    page. Returns (controller, script)."""
    pages = {}
    link_targets = {}
    script = {}
    for i in range(1, n + 1):
        url = f"{CHAIN_BASE}/p{i}"
        entries = []
        if i < n:
            entries.append(_entry(len(entries) + 1, "link", f"To p{i + 1}"))
            link_targets[("link", f"To p{i + 1}")] = f"{CHAIN_BASE}/p{i + 1}"
            script[f"Check To p{i + 1}"] = _worked
        entries.append(_entry(len(entries) + 1, "button", f"Action {i}"))
        script[f"Check Action {i}"] = _worked
        pages[url] = tuple(entries)
    controller = _FakeInventoryController(
        pages=pages, start_url=f"{CHAIN_BASE}/p1")
    controller.link_targets = link_targets
    return controller, script


def test_seed_known_states_registers_claim_states_without_items() -> None:
    """Section 10.4 state seeding (decision D4): a fabricated
    signature-bearing state registers with the same state_id a live
    observation would mint, and mints no Board items; NULL-signature
    states — every state in a pure census map — seed nothing."""
    board = new_harness_state()
    url = "https://app.test/settings"
    app_map = {"pages": [
        {"url": url, "states": [{
            "state_key": "default", "state_id": None,
            "element_signature": "button|Save;link|Help",
            "form_signature": "field|Email",
        }]},
        {"url": "https://app.test/plain", "states": [{
            "state_key": "default", "state_id": None,
            "element_signature": None, "form_signature": None,
        }]},
    ]}
    seeded = harness_run._seed_known_states(board, app_map)
    assert seeded == 1
    assert len(board.items) == 0
    expected_id = state_id_for(
        url, (("button", "Save"), ("link", "Help")), ("Email",))
    assert list(board.states) == [expected_id]
    assert board.states[expected_id].url == canonical_url(url)
    # A live observation of the same page lands on the same state.
    again = board.add_state(
        url=url, elements=(("link", "Help"), ("button", "Save")),
        form_fields=("Email",))
    assert again.state_id == expected_id
    assert len(board.states) == 1


async def test_map_seeded_crawl_visits_beyond_the_flat_cap(monkeypatch) -> None:
    """T-H1: with a map seeding all 30 pages of a chain, the crawl
    bound is the seeded frontier plus the discovery allowance — every
    page is visited, past the unmapped cap of 20, and the completion
    delta reconciles all 30 as present."""
    controller, script = _chain_site(30)
    routes = [f"{CHAIN_BASE}/p{i}" for i in range(1, 31)]
    app_map = _map_block(routes=routes, pages=[_map_page(u) for u in routes])
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=routes[0])
    request = replace(request, app_map=app_map)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script=script, calls=calls)
    run_events = _capture_run_events(monkeypatch)
    await harness_run.execute_harness_run(request=request, session=session)
    visited = run.configuration_snapshot["discovery_frontier"]["visited"]
    assert len(visited) == 30
    assert run.configuration_snapshot["harness_stage"] == "done"
    deltas = _payloads(run_events, "harness.coverage.delta")
    assert len(deltas) == 1
    assert deltas[0]["counts"]["present"] == 30
    assert deltas[0]["missing"] == []


async def test_unmapped_crawl_keeps_the_flat_cap(monkeypatch) -> None:
    """T-H2 (C9 regression pin): the same 30-page chain without a map
    stops at exactly 20 visited pages, names the next page on the
    frontier event, and emits no coverage delta."""
    controller, script = _chain_site(30)
    run_id = uuid4()
    run, session, request = _inventory_run(
        run_id, start_url=f"{CHAIN_BASE}/p1")
    calls: list[str] = []
    events = _install_inventory_doubles(monkeypatch, controller=controller,
                                        script=script, calls=calls)
    run_events = _capture_run_events(monkeypatch)
    await harness_run.execute_harness_run(request=request, session=session)
    visited = run.configuration_snapshot["discovery_frontier"]["visited"]
    assert len(visited) == 20
    frontier = _payloads(events, "harness.coverage.frontier")
    assert len(frontier) == 1
    assert frontier[0]["visited_count"] == 20
    assert frontier[0]["not_visited"] == [f"{CHAIN_BASE}/p21"]
    assert frontier[0]["reason"] == "discovery_cap"
    assert _payloads(run_events, "harness.coverage.delta") == []


async def test_navigate_failure_is_accounted_and_the_crawl_continues(monkeypatch) -> None:
    """T-H3: a seeded page whose navigate raises BrowserActionError
    emits harness.inventory.page_failed with its URL, is never
    retried, lands in the delta's unreachable set, and the crawl
    still completes the remaining pages."""
    start = f"{CHAIN_BASE}/p1"
    bad = f"{CHAIN_BASE}/bad"
    good = f"{CHAIN_BASE}/good"
    attempts: list[str] = []

    class Controller(_FakeInventoryController):
        async def navigate(self, *, session_id, url, **kwargs):
            attempts.append(url)
            if url == bad:
                raise BrowserActionError(
                    "Connection reset", reason_code="navigation_failed")
            return await super().navigate(
                session_id=session_id, url=url, **kwargs)

    # Button names carry read-class verbs on purpose: the safety
    # classifier never executes a verb-less button (uncertain is
    # classified irreversible - harness_items.classify_action).
    controller = Controller(pages={
        start: (_entry(1, "button", "Search start"),),
        good: (_entry(1, "button", "Search good"),),
    }, start_url=start)
    routes = [start, bad, good]
    app_map = _map_block(routes=routes, pages=[_map_page(u) for u in routes])
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=start)
    request = replace(request, app_map=app_map)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller, calls=calls,
                               script={"Check Search start": _worked,
                                       "Check Search good": _worked})
    run_events = _capture_run_events(monkeypatch)
    await harness_run.execute_harness_run(request=request, session=session)
    assert run.configuration_snapshot["harness_stage"] == "done"
    assert "Check Search good" in calls
    assert attempts.count(bad) == 1
    failed = _payloads(run_events, "harness.inventory.page_failed")
    assert len(failed) == 1
    assert failed[0]["url"] == bad
    assert failed[0]["error_site"].startswith("harness_run.py:")
    deltas = _payloads(run_events, "harness.coverage.delta")
    assert len(deltas) == 1
    assert deltas[0]["unreachable"] == [bad]
    assert deltas[0]["present"] == sorted([start, good])
    assert deltas[0]["missing"] == []


async def test_bot_wall_checkpoint_still_parks_the_crawl(monkeypatch) -> None:
    """T-H4: the navigate guard must not swallow the bot-wall park —
    a checkpoint page still raises BrowserDiscoveryCheckpointError
    out of the crawl, and no page_failed event is emitted for it."""
    class Controller(_FakeInventoryController):
        async def discovery_page_signals(self, **kwargs):
            return {"text": "Verify you are human", "scripts": [],
                    "controls": 0}

    controller = Controller(
        pages={INVENTORY_URL: (_entry(1, "button", "Save settings"),)},
        start_url=INVENTORY_URL)
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    _install_inventory_doubles(monkeypatch, controller=controller, calls=[],
                               script={"Check Save settings": _worked})
    run_events = _capture_run_events(monkeypatch)
    with pytest.raises(BrowserDiscoveryCheckpointError):
        await harness_run.execute_harness_run(request=request, session=session)
    assert _payloads(run_events, "harness.inventory.page_failed") == []


async def test_crawl_dns_failure_is_accounted_and_the_crawl_continues(monkeypatch) -> None:
    """T-H3b: a seeded page whose navigate raises HostResolutionError
    (a BrowserPolicyError, NOT a BrowserActionError) is accounted
    exactly like a page-load failure: page_failed event, delta
    unreachable, never retried, and the crawl completes the remaining
    pages. Live evidence: MT-000161 died when DNS for the target host
    failed seconds before the host laptop slept."""
    from markettwin_execution_orchestrator.browser.errors import (
        HostResolutionError,
    )

    start = f"{CHAIN_BASE}/p1"
    bad = f"{CHAIN_BASE}/bad"
    good = f"{CHAIN_BASE}/good"
    attempts: list[str] = []

    class Controller(_FakeInventoryController):
        async def navigate(self, *, session_id, url, **kwargs):
            attempts.append(url)
            if url == bad:
                raise HostResolutionError(
                    'Unable to resolve target hostname "bad".')
            return await super().navigate(
                session_id=session_id, url=url, **kwargs)

    controller = Controller(pages={
        start: (_entry(1, "button", "Search start"),),
        good: (_entry(1, "button", "Search good"),),
    }, start_url=start)
    routes = [start, bad, good]
    app_map = _map_block(routes=routes, pages=[_map_page(u) for u in routes])
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=start)
    request = replace(request, app_map=app_map)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller, calls=calls,
                               script={"Check Search start": _worked,
                                       "Check Search good": _worked})
    run_events = _capture_run_events(monkeypatch)
    await harness_run.execute_harness_run(request=request, session=session)
    assert run.configuration_snapshot["harness_stage"] == "done"
    assert "Check Search good" in calls
    assert attempts.count(bad) == 1
    failed = _payloads(run_events, "harness.inventory.page_failed")
    assert len(failed) == 1
    assert failed[0]["url"] == bad
    deltas = _payloads(run_events, "harness.coverage.delta")
    assert len(deltas) == 1
    assert deltas[0]["unreachable"] == [bad]
    assert deltas[0]["present"] == sorted([start, good])
    assert deltas[0]["missing"] == []


async def test_reinventory_navigation_failure_is_absorbed_and_the_run_continues(
    monkeypatch,
) -> None:
    """After a link/button item executes, the harness returns the Room
    to the start page and re-indexes. If that return navigation fails
    (TargetUrlValidationError in MT-000160, HostResolutionError in
    MT-000161, both escaping controller.navigate at the same call),
    the failure is recorded as harness.inventory.page_failed, the
    re-index is skipped, and the run still completes every item."""
    from markettwin_execution_orchestrator.browser.errors import (
        TargetUrlValidationError,
    )

    navigations: list[str] = []

    class Controller(_FakeInventoryController):
        async def navigate(self, *, session_id, url, **kwargs):
            navigations.append(url)
            if url == INVENTORY_URL and navigations.count(INVENTORY_URL) == 2:
                raise TargetUrlValidationError(
                    "Only HTTP and HTTPS URLs are supported.")
            return await super().navigate(
                session_id=session_id, url=url, **kwargs)

    controller = Controller(pages={
        INVENTORY_URL: (
            _entry(1, "link", "Help"),
            _entry(2, "button", "Save settings"),
        ),
    }, start_url=INVENTORY_URL)
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller, calls=calls,
                               script={"Check Help": _worked,
                                       "Check Save settings": _worked})
    run_events = _capture_run_events(monkeypatch)
    await harness_run.execute_harness_run(request=request, session=session)
    assert run.configuration_snapshot["harness_stage"] == "done"
    assert sorted(calls) == ["Check Help", "Check Save settings"]
    failed = _payloads(run_events, "harness.inventory.page_failed")
    assert len(failed) == 1
    assert failed[0]["url"] == INVENTORY_URL


async def test_reinventory_index_timeout_is_absorbed_and_the_run_continues(
    monkeypatch,
) -> None:
    """MT-000169: the post-item re-inventory's get_page_index sat in
    the authentication checkpoint on a Playwright locator send-wait
    that never returned, and the stall watchdog killed the run. The
    bounded inspection now surfaces BrowserTimeoutError (a
    BrowserActionError) out of get_page_index; the re-inventory absorb
    must record it as harness.inventory.page_failed — the same
    accounting as a failed return navigation — and the run still
    completes every item."""
    from markettwin_execution_orchestrator.browser.errors import (
        BrowserTimeoutError,
    )

    navigations: list[str] = []

    class Controller(_FakeInventoryController):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.index_timeouts = 0

        async def navigate(self, *, session_id, url, **kwargs):
            navigations.append(url)
            return await super().navigate(
                session_id=session_id, url=url, **kwargs)

        async def get_page_index(self, **kwargs):
            if navigations.count(INVENTORY_URL) >= 2 and self.index_timeouts == 0:
                self.index_timeouts += 1
                raise BrowserTimeoutError(
                    "Timed out inspecting the page for an active challenge.")
            return await super().get_page_index(**kwargs)

    controller = Controller(pages={
        INVENTORY_URL: (
            _entry(1, "link", "Help"),
            _entry(2, "button", "Save settings"),
        ),
    }, start_url=INVENTORY_URL)
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    _install_inventory_doubles(monkeypatch, controller=controller, calls=calls,
                               script={"Check Help": _worked,
                                       "Check Save settings": _worked})
    run_events = _capture_run_events(monkeypatch)
    await harness_run.execute_harness_run(request=request, session=session)
    assert run.configuration_snapshot["harness_stage"] == "done"
    assert sorted(calls) == ["Check Help", "Check Save settings"]
    failed = _payloads(run_events, "harness.inventory.page_failed")
    assert len(failed) == 1
    assert failed[0]["url"] == INVENTORY_URL


async def test_login_reset_rebuilds_the_queue_from_map_routes(monkeypatch) -> None:
    """T-H5: when a human logs in mid-run, the rebuilt crawl queue is
    planned_routes — which section 10.2 fills from the map — so the
    page only the map knows is crawled and inventoried after the
    reset, in the same dispatch."""
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
    admin_url = INVENTORY_URL + "/admin"
    controller = _FakeInventoryController(
        pages={INVENTORY_URL: login_entries,
               admin_url: (_entry(1, "button", "Search admin"),)},
        start_url=INVENTORY_URL, dashboard_entries=dashboard_entries,
    )
    controller.link_targets = {("link", "Admin console"): admin_url}

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
        "Check Search admin": _worked,
    }
    app_map = _map_block(routes=[INVENTORY_URL, admin_url],
                         pages=[_map_page(INVENTORY_URL),
                                _map_page(admin_url)])
    app_plan = {"version": 1, "status": "map_seeded", "sources": [],
                "checks": [], "routes": [INVENTORY_URL, admin_url],
                "omitted_segments": 0, "route_source": "app_map"}
    run_id = uuid4()
    run, session, request = _inventory_run(
        run_id, start_url=INVENTORY_URL, target_id=uuid4(),
    )
    request = replace(request, app_map=app_map, app_plan=app_plan)
    calls: list[str] = []
    _install_inventory_doubles(
        monkeypatch, controller=controller, script=script, calls=calls,
    )
    await harness_run.execute_harness_run(request=request, session=session)
    assert "Check Search admin" in calls
    assert run.configuration_snapshot["harness_stage"] == "done"


async def test_delta_event_emitted_iff_a_map_was_present(monkeypatch) -> None:
    """T-H6: completion emits harness.coverage.delta exactly when the
    run carried a map; harness.coverage.frontier keeps its existing
    behaviour — emitted when pages remain unvisited — in both cases.
    A Lead stop leaves a queued third page unvisited in each variant."""
    # Read-verb names: verb-less buttons are classified irreversible
    # and skipped, which would also starve the Lead checkpoint below.
    entries = tuple(
        _entry(i + 1, "button", f"Search {i}") for i in range(6)
    ) + (_entry(7, "link", "Second page"),)
    second = INVENTORY_URL + "/second"
    third = INVENTORY_URL + "/third"
    pages = {INVENTORY_URL: entries,
             second: (_entry(1, "button", "Search second"), _entry(2, "link", "Third page")),
             third: (_entry(1, "button", "Search third"),)}
    script = {f"Check Search {i}": _worked for i in range(6)}
    script["Check Second page"] = _worked
    script["Check Search second"] = _worked
    script["Check Third page"] = _worked
    script["Check Search third"] = _worked

    async def run_once(*, with_map):
        controller = _FakeInventoryController(
            pages=pages, start_url=INVENTORY_URL)
        controller.link_targets = {("link", "Second page"): second, ("link", "Third page"): third}
        run_id = uuid4()
        run, session, request = _inventory_run(
            run_id, start_url=INVENTORY_URL)
        if with_map:
            request = replace(request, app_map=_map_block(
                routes=[INVENTORY_URL, second, third],
                pages=[_map_page(url) for url in (INVENTORY_URL, second, third)]))
        calls: list[str] = []
        events = _install_inventory_doubles(
            monkeypatch, controller=controller, script=script, calls=calls)
        run_events = _capture_run_events(monkeypatch)
        monkeypatch.setattr(harness_run, "review_checkpoint", AsyncMock(
            return_value={"decision": "stop", "reason": "Enough",
                          "source": "lead"}))
        await harness_run.execute_harness_run(request=request, session=session)
        return events, run_events

    events, run_events = await run_once(with_map=True)
    frontier = _payloads(events, "harness.coverage.frontier")
    assert len(frontier) == 1
    assert frontier[0]["not_visited"] == [third]
    deltas = _payloads(run_events, "harness.coverage.delta")
    assert len(deltas) == 1
    assert deltas[0]["present"] == [INVENTORY_URL, second]
    assert deltas[0]["missing"] == [{"url": third, "status": "fetch_ok"}]
    assert deltas[0]["counts"] == {"present": 2, "missing": 1,
                                   "unreachable": 0, "changed": 0, "new": 0}

    events, run_events = await run_once(with_map=False)
    assert len(_payloads(events, "harness.coverage.frontier")) == 1
    assert _payloads(run_events, "harness.coverage.delta") == []


# ---------------------------------------------------------------------------
# Doc 17 (D3 writer): run mode + approved test data. T-D3-H1..H8.
# ---------------------------------------------------------------------------


def _d3_mode_events(events) -> list[dict[str, object]]:
    return [
        call.kwargs
        for call in events.create.await_args_list
        if call.kwargs["event_type"] == "harness.run_mode"
    ]


@pytest.mark.parametrize("snapshot", [
    {},
    {"harness_run_mode": "STANDARD"},
    {"harness_run_mode": "read_only"},
])
async def test_d3_h1_absent_or_inexact_mode_means_read_only(
    monkeypatch, snapshot,
) -> None:
    """T-D3-H1 (C1): fail-closed — only the exact string unlocks standard."""
    from markettwin_execution_orchestrator.workflow.harness_items import (
        NOT_EXERCISED_IRREVERSIBLE,
        NOT_EXERCISED_READ_ONLY,
    )

    entries = (
        _entry(1, "link", "Help"),
        _entry(2, "textbox", "Display name"),
        _entry(3, "button", "Save settings"),
        _entry(4, "button", "Delete workspace"),
        _entry(5, "textbox", "Contact address"),
    )
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)
    script = {"Check Help": _worked}
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    run.configuration_snapshot = snapshot
    calls: list[str] = []
    events = _install_inventory_doubles(monkeypatch, controller=controller,
                                        script=script, calls=calls)
    monkeypatch.setattr(
        harness_run, "RunEventRepository", lambda _: events, raising=False,
    )
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    assert calls == ["Check Help"]
    by_name = {item.name: item for item in loaded.ordered_items()}
    assert by_name["Help"].status == "could_not_check"
    for name in ("Display name", "Save settings", "Contact address"):
        assert by_name[name].status == "not_checked"
        assert by_name[name].blocker == NOT_EXERCISED_READ_ONLY
    assert by_name["Delete workspace"].status == "not_checked"
    assert by_name["Delete workspace"].blocker == NOT_EXERCISED_IRREVERSIBLE
    assert sum(loaded.counts().values()) == 5
    mode_events = _d3_mode_events(events)
    assert len(mode_events) == 1
    assert mode_events[0]["payload"]["mode"] == "read_only"


def test_d3_h2_approved_test_data_parse_round_trip() -> None:
    """T-D3-H2 (C7): the pinned shape parses; anything else is forgiven."""
    from markettwin_execution_orchestrator.workflow.run_request import (
        _parse_approved_test_data,
        build_run_request,
    )
    from markettwin_shared.feature_plan import SafeTestValue

    assert _parse_approved_test_data({}) == ()
    assert _parse_approved_test_data({"approved_test_data": "nope"}) == ()
    assert _parse_approved_test_data({"approved_test_data": [
        {"key": "valid_name", "value": "Gatekeeper Ada"},
        {"key": "Bad Key", "value": "x"},
        {"key": "company_name"},
        {"key": "company_name", "value": 42},
        "junk",
        {"key": "ok_key", "value": "v" * 300},
        {"key": "ok_key", "value": "v"},
    ]}) == (
        SafeTestValue(key="valid_name", value="Gatekeeper Ada"),
        SafeTestValue(key="ok_key", value="v"),
    )
    run = TestRun(
        id=uuid4(),
        configuration_snapshot={
            "study_brief": "Check the signup form",
            "approved_test_data": [
                {"key": "valid_name", "value": "Gatekeeper Ada"},
                {"key": "company_name", "value": "Thread & Co. Test"},
            ],
        },
        target_snapshot={
            "base_url": INVENTORY_URL,
            "name": "Fixture",
            "environment": "local",
            "allowed_origins": [
                {"scheme": "http", "hostname": "127.0.0.1", "port": 5199,
                 "include_subdomains": False},
            ],
        },
    )
    request = build_run_request(run)
    assert request.approved_test_data == (
        SafeTestValue(key="valid_name", value="Gatekeeper Ada"),
        SafeTestValue(key="company_name", value="Thread & Co. Test"),
    )


async def test_d3_h3_standard_mode_merges_owner_data_over_defaults(
    monkeypatch,
) -> None:
    """T-D3-H3 (sections 6.3/7.3): the executor's scope carries the merged
    table; the board payload carries the safety class and the KEY only."""
    from dataclasses import replace

    from markettwin_shared.feature_plan import SafeTestValue

    entries = (_entry(1, "textbox", "Display name"),)
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    request = replace(
        request,
        approved_test_data=(
            SafeTestValue(key="valid_name", value="Gatekeeper Ada"),
        ),
    )
    calls: list[str] = []
    events = _install_inventory_doubles(monkeypatch, controller=controller,
                                        script={}, calls=calls)
    monkeypatch.setattr(
        harness_run, "RunEventRepository", lambda _: events, raising=False,
    )
    captured: dict[str, object] = {}

    async def execute(**kwargs) -> CaseExecutionResult:
        captured["scope"] = kwargs["scope"]
        case = kwargs["case"]
        calls.append(case.title)
        return _worked(case, kwargs["request"].execution_id)

    monkeypatch.setattr(
        harness_run, "execute_test_case", AsyncMock(side_effect=execute),
    )
    await harness_run.execute_harness_run(request=request, session=session)
    assert calls == ["Check Display name"]
    scope = captured["scope"]
    values = {entry.key: entry.value for entry in scope.safe_test_data}
    assert values["valid_name"] == "Gatekeeper Ada"
    assert values["valid_email"] == "fixture@example.test"
    board_payloads = [
        call.kwargs["payload"]
        for call in events.create.await_args_list
        if call.kwargs["event_type"] == "board.item.result"
    ]
    assert len(board_payloads) == 1
    assert board_payloads[0]["safety_class"] == "reversible"
    assert board_payloads[0]["test_value_key"] == "valid_name"
    assert all(
        "Gatekeeper Ada" not in repr(call.kwargs)
        for call in events.create.await_args_list
    )


async def test_d3_h4_irreversible_is_refused_in_standard_mode_too(
    monkeypatch,
) -> None:
    """T-D3-H4 (C3): the classifier ceiling holds in EVERY mode."""
    from markettwin_execution_orchestrator.workflow.harness_items import (
        NOT_EXERCISED_IRREVERSIBLE,
    )

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
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    assert calls == ["Check Search"]
    by_name = {item.name: item for item in loaded.ordered_items()}
    assert by_name["Delete account"].status == "not_checked"
    assert by_name["Delete account"].blocker == NOT_EXERCISED_IRREVERSIBLE
    mode_events = _d3_mode_events(events)
    assert len(mode_events) == 1
    assert mode_events[0]["payload"]["mode"] == "standard"


async def test_d3_h5_unapproved_key_is_accounted_never_executed(
    monkeypatch,
) -> None:
    """T-D3-H5 (section 6.4): a case needing a key no approved value
    resolves is not_checked with the data-guard reason; the executor
    never sees it; the accounting still reconciles."""
    from markettwin_execution_orchestrator.workflow.harness_items import (
        NOT_EXERCISED_UNAPPROVED_DATA,
    )

    entries = (_entry(1, "textbox", "Display name"),)
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    events = _install_inventory_doubles(monkeypatch, controller=controller,
                                        script={}, calls=calls)
    monkeypatch.setattr(
        harness_run, "RunEventRepository", lambda _: events, raising=False,
    )
    real_case_for_item = harness_run.case_for_item

    def unapproved_case(**kwargs):
        case = real_case_for_item(**kwargs)
        steps = tuple(
            step.model_copy(update={"test_value_key": "company_name"})
            if step.action in {"fill", "select"}
            else step
            for step in case.steps
        )
        return case.model_copy(update={"steps": steps})

    monkeypatch.setattr(harness_run, "case_for_item", unapproved_case)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    assert calls == []
    (item,) = loaded.ordered_items()
    assert item.status == "not_checked"
    assert item.blocker == NOT_EXERCISED_UNAPPROVED_DATA
    assert sum(loaded.counts().values()) == 1
    published = [
        call.kwargs
        for call in events.create.await_args_list
        if call.kwargs["event_type"] == "journey.result"
    ]
    entry = next(
        (e for e in published
         if e["journey_id"] == UUID(str(item.journey_id))),
        None,
    )
    assert entry is not None
    assert entry["payload"]["status"] == "skipped"
    assert entry["payload"]["outcome"] is None


async def test_d3_h6_mode_event_is_written_once_per_dispatch(
    monkeypatch,
) -> None:
    """T-D3-H6 (section 7.2): one harness.run_mode event per dispatch,
    keys sorted, in both modes."""
    from dataclasses import replace

    from markettwin_shared.feature_plan import SafeTestValue

    entries = (_entry(1, "link", "Help"),)
    script = {"Check Help": _worked}
    # read_only dispatch (snapshot without the key)
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    run.configuration_snapshot = {}
    calls: list[str] = []
    events = _install_inventory_doubles(monkeypatch, controller=controller,
                                        script=script, calls=calls)
    monkeypatch.setattr(
        harness_run, "RunEventRepository", lambda _: events, raising=False,
    )
    await harness_run.execute_harness_run(request=request, session=session)
    mode_events = _d3_mode_events(events)
    assert len(mode_events) == 1
    assert mode_events[0]["payload"] == {
        "mode": "read_only",
        "source": "configuration_snapshot",
        "approved_test_data_keys": [],
    }
    # standard dispatch with declared data (keys land sorted)
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    request = replace(
        request,
        approved_test_data=(
            SafeTestValue(key="valid_name", value="Gatekeeper Ada"),
            SafeTestValue(key="company_name", value="Thread & Co. Test"),
        ),
    )
    calls = []
    events = _install_inventory_doubles(monkeypatch, controller=controller,
                                        script=script, calls=calls)
    monkeypatch.setattr(
        harness_run, "RunEventRepository", lambda _: events, raising=False,
    )
    await harness_run.execute_harness_run(request=request, session=session)
    mode_events = _d3_mode_events(events)
    assert len(mode_events) == 1
    assert mode_events[0]["payload"] == {
        "mode": "standard",
        "source": "configuration_snapshot",
        "approved_test_data_keys": ["company_name", "valid_name"],
    }


async def test_d3_h7_approved_values_never_reach_events_or_the_lead(
    monkeypatch,
) -> None:
    """T-D3-H7 (C5): the value exists in the executor's scope and nowhere
    else — no event payload, no Lead brief, carries it."""
    from dataclasses import replace

    from markettwin_shared.feature_plan import SafeTestValue

    entries = (_entry(1, "textbox", "Display name"),)
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    request = replace(
        request,
        approved_test_data=(
            SafeTestValue(key="valid_name", value="Gatekeeper Ada"),
        ),
    )
    calls: list[str] = []
    events = _install_inventory_doubles(monkeypatch, controller=controller,
                                        script={}, calls=calls)
    monkeypatch.setattr(
        harness_run, "RunEventRepository", lambda _: events, raising=False,
    )
    captured: dict[str, object] = {}

    async def execute(**kwargs) -> CaseExecutionResult:
        captured["scope"] = kwargs["scope"]
        case = kwargs["case"]
        calls.append(case.title)
        return _worked(case, kwargs["request"].execution_id)

    monkeypatch.setattr(
        harness_run, "execute_test_case", AsyncMock(side_effect=execute),
    )
    reviews: list[dict[str, object]] = []

    async def review(**kwargs):
        reviews.append(kwargs)
        return {"decision": "continue", "reason": "Fixture", "source": "test"}

    monkeypatch.setattr(
        harness_run, "review_checkpoint", AsyncMock(side_effect=review),
    )
    await harness_run.execute_harness_run(request=request, session=session)
    # Positive control: the run really carried the value.
    scope = captured["scope"]
    values = {entry.key: entry.value for entry in scope.safe_test_data}
    assert values["valid_name"] == "Gatekeeper Ada"
    assert all(
        "Gatekeeper Ada" not in repr(call.kwargs)
        for call in events.create.await_args_list
    )
    assert "Gatekeeper Ada" not in request.study_brief
    assert "Gatekeeper Ada" not in repr(reviews)


def test_d3_h8_creation_is_the_only_harness_run_mode_writer() -> None:
    """T-D3-H8 (C2): in orchestrator source the snapshot key is read in
    exactly one place (run_safety_mode in harness_items) and assigned
    nowhere — the creation path in control-api is the only writer."""
    import ast
    from pathlib import Path

    source_root = (
        Path(__file__).resolve().parents[1]
        / "src" / "markettwin_execution_orchestrator"
    )
    mentions: dict[str, int] = {}
    writes = 0
    for path in sorted(source_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and node.value == "harness_run_mode"
            ):
                mentions[path.name] = mentions.get(path.name, 0) + 1
            if isinstance(node, ast.Subscript) and isinstance(
                node.ctx, ast.Store,
            ):
                if (
                    isinstance(node.slice, ast.Constant)
                    and node.slice.value == "harness_run_mode"
                ):
                    writes += 1
    assert mentions == {"harness_items.py": 1}
    assert writes == 0


def test_coverage_delta_uses_harvested_state_ids():
    """T-H7 (Phase 1b section 8): the coverage delta seeds from the
    snapshot's harvested state ids — a live state whose identity
    equals the harvested one is present; a differing identity is
    changed, with both ids named."""
    block = {
        "map_id": "map-1", "version_number": 2,
        "routes_truncated": False, "counts": {"expected": 2},
        "pages": [
            {"url": "https://app.test/", "status": "fetch_ok",
             "states": [{"state_key": "default", "state_id": "harvested-a",
                         "element_signature": "link|Home",
                         "form_signature": None}]},
            {"url": "https://app.test/pricing", "status": "fetch_ok",
             "states": [{"state_key": "default", "state_id": "harvested-b",
                         "element_signature": "link|Home",
                         "form_signature": None}]},
        ],
    }
    delta = build_coverage_delta(
        map_block=block,
        absorbed={"https://app.test/": "harvested-a",
                  "https://app.test/pricing": "live-b"},
        attempted_failed=[], frontier_remaining=[],
    )
    assert delta["present"] == ["https://app.test/"]
    assert delta["changed"] == [{
        "url": "https://app.test/pricing",
        "seeded_state_id": "harvested-b", "live_state_id": "live-b",
    }]
    assert delta["counts"] == {
        "present": 1, "missing": 0, "unreachable": 0, "changed": 1,
        "new": 0,
    }


async def test_assistance_timeout_blocks_one_item_and_the_run_continues(monkeypatch) -> None:
    entries = (
        _entry(1, "link", "Privacy Policy"),
        _entry(2, "button", "Search"),
        _entry(3, "button", "Save settings"),
    )
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)

    def timed_out_assistance(case, execution_id):
        return _worked(case, execution_id).model_copy(update={
            "human_wait_ms": 1000, "execution_status": "policy_blocked",
            "verdict": "unverified", "blocker": "human_assistance_timeout"})

    script = {
        "Check Privacy Policy": timed_out_assistance,
        "Check Search": _worked,
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
    # The timed-out item is terminal, named, and published as blocked.
    assert by_name["Privacy Policy"].status == "blocked"
    assert by_name["Privacy Policy"].blocker == "human_assistance_timeout"
    # P1: no handoff stop was recorded and nothing was mass-marked.
    assert "lead_stop" not in run.configuration_snapshot
    # Every later item was still attempted (S2: start order under
    # a live worker lane is concurrent, not Board order).
    assert sorted(calls) == [
        "Check Privacy Policy", "Check Save settings", "Check Search"]
    counts = loaded.counts()
    assert counts["blocked"] == 1
    assert counts["pending"] == 0
    assert run.configuration_snapshot["harness_stage"] == "done"
    # P2/P3: nobody logged in during the timed-out item, so the Room
    # never counts as authenticated and no authenticated re-crawl ran.
    assert True not in controller.index_authenticated


async def test_resumed_board_does_not_requeue_assistance_timeout_blocked_item(monkeypatch) -> None:
    login_entries = (
        _entry(1, "link", "Privacy Policy"),
        _entry(2, "link", "Sign in"),
        _entry(3, "textbox", "Username"),
        _entry(4, "textbox", "Password"),
        _entry(5, "button", "Continue"),
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

    def timed_out_assistance(case, execution_id):
        return _worked(case, execution_id).model_copy(update={
            "human_wait_ms": 1000, "execution_status": "policy_blocked",
            "verdict": "unverified", "blocker": "human_assistance_timeout"})

    def continue_result(case, execution_id):
        if controller.logged_in:
            return _worked(case, execution_id)
        return _result_for(case, execution_id, verdict="unverified",
                           status="policy_blocked",
                           blocker="authentication_challenge_blocked")

    script = {
        "Check Privacy Policy": timed_out_assistance,
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

    # First dispatch: the timeout blocks item 1 and the run CONTINUES
    # until the login wall parks it — both semantics in one dispatch.
    await harness_run.execute_harness_run(request=request, session=session)
    assert run.status == "awaiting_human"
    parked = await load_harness_state(session, run_id)
    assert parked is not None
    by_name = {item.name: item for item in parked.ordered_items()}
    assert by_name["Privacy Policy"].status == "blocked"
    assert by_name["Privacy Policy"].blocker == "human_assistance_timeout"
    assert by_name["Continue"].status == "needs_human_login"
    assert calls.count("Check Privacy Policy") == 1

    # Resume after the scripted human login (the :1108 pattern): the
    # parked login item re-queues; the timeout-blocked item does not —
    # blocked is terminal and is never re-executed.
    controller.complete_human_login()
    await harness_run.execute_harness_run(request=request, session=session)
    assert run.configuration_snapshot["harness_stage"] == "done"
    resumed = await load_harness_state(session, run_id)
    assert resumed is not None
    by_name = {item.name: item for item in resumed.ordered_items()}
    assert by_name["Privacy Policy"].status == "blocked"
    assert by_name["Privacy Policy"].blocker == "human_assistance_timeout"
    assert calls.count("Check Privacy Policy") == 1
    assert resumed.counts()["blocked"] == 1
    assert resumed.counts()["pending"] == 0
    assert resumed.counts()["needs_human_login"] == 0



class _LaneController(_OutcomeController):
    """_OutcomeController plus S1's worker-session factory (doc 18
    section 11) and per-session JS scripting.

    The parent double drains ONE shared JS buffer for every session
    (its own docstring says so) — T-H2 needs each context's harvest
    to differ, so harvests here pop the next scripted list for the
    session's key: "room", "worker", or "proof". An exhausted or
    unscripted queue reads as no records.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.worker_session_ids: list[UUID] = []
        self.closed_session_ids: list[UUID] = []
        self.js_script: dict[str, list[list[SimpleNamespace]]] = {}

    async def create_worker_session(
        self, *, room_session_id, execution_id, journey_id, lane_index,
    ):
        handle = SimpleNamespace(session_id=uuid4())
        self.worker_session_ids.append(handle.session_id)
        return handle

    async def close_session(self, *, session_id):
        self.closed_session_ids.append(session_id)
        return None

    def _script_key(self, session_id) -> str:
        if session_id == self.room_handle.session_id:
            return "room"
        if (self.proof_session_id is not None
                and session_id == self.proof_session_id):
            return "proof"
        if session_id in self.worker_session_ids:
            return "worker"
        return "room"

    async def harvest_js_records(self, session_id):
        queue = self.js_script.get(self._script_key(session_id), [])
        return queue.pop(0) if queue else []


def _install_lane_doubles(
    monkeypatch, *, controller, script, calls, sessions,
) -> None:
    """The inventory doubles, with an executor that records WHICH
    session each item's own execution ran on, and the lane DB
    session factory pointed at the test's session (R-3's seam)."""

    _install_inventory_doubles(
        monkeypatch, controller=controller, script=script, calls=calls)

    async def execute_test_case(**kwargs):
        case = kwargs["case"]
        calls.append(case.title)
        sessions.setdefault(case.title, []).append(
            kwargs["session_handle"].session_id)
        builder = script[case.title]
        return builder(case, kwargs["request"].execution_id)

    monkeypatch.setattr(harness_run, "execute_test_case", execute_test_case)
    monkeypatch.setattr(
        harness_run, "_new_lane_session", _lane_test_session)


async def test_harness_lanes_same_route_dedupes_and_partitions(
    monkeypatch,
) -> None:
    """T-H1 (doc 18 section 15), translated per spec R-4: item
    executions never mint states in the as-built harness — states
    come only from the absorber. So: while lane 1 executes View
    alpha, the Room executes View beta, whose click changes the
    page; the absorber's re-inventory mints exactly one new state
    for the changed route (repeated absorptions of the unchanged
    route dedupe onto it), and the new item is claimed exactly
    once. No item's own execution ever runs on two lanes."""

    entries = (
        _entry(1, "button", "View alpha"),
        _entry(2, "button", "View beta"),
    )
    controller = _LaneController(
        pages={INVENTORY_URL: entries}, start_url=INVENTORY_URL)

    def changer(case, execution_id):
        controller.pages[INVENTORY_URL] = (
            _entry(1, "button", "View alpha"),
            _entry(2, "button", "View beta"),
            _entry(3, "button", "View gamma"),
        )
        return _worked(case, execution_id)

    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    sessions: dict[str, list[UUID]] = {}
    _install_lane_doubles(
        monkeypatch, controller=controller,
        script={
            "Check View alpha": _worked,
            "Check View beta": changer,
            "Check View gamma": _worked,
        },
        calls=calls, sessions=sessions)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    # Exactly one worker lane ever opened; the first claim lanned,
    # the second executed on the Room while the lane was busy.
    assert len(controller.worker_session_ids) == 1
    worker_id = controller.worker_session_ids[0]
    room_id = controller.room_handle.session_id
    assert sessions["Check View alpha"][0] == worker_id
    assert sessions["Check View beta"][0] == room_id
    # Partition: attempt-1 executions happened on exactly the two
    # lanes — never a third context, never both lanes for one item.
    first_sessions = {
        sessions[title][0]
        for title in (
            "Check View alpha", "Check View beta", "Check View gamma")
    }
    assert first_sessions == {worker_id, room_id}
    assert calls.count("Check View beta") >= 1
    # The changed route dedupes to exactly one new state across
    # every absorption; the discovered item sits on it.
    states = [s for s in loaded.states.values() if s.url == INVENTORY_URL]
    # The Board also holds the map-seeded state for this URL (the
    # fixture map's page, a different signature); the dedupe claim
    # is about the live page's states: exactly the pre-change and
    # post-change states, however often each was absorbed.
    live_states = [
        s for s in states if "button|View alpha" in s.element_signature]
    assert len(live_states) == 2
    gamma_items = [
        item for item in loaded.items.values() if item.name == "View gamma"]
    assert len(gamma_items) == 1
    new_state = next(
        s for s in live_states
        if "button|View gamma" in s.element_signature)
    old_state = next(
        s for s in live_states
        if "button|View gamma" not in s.element_signature)
    assert gamma_items[0].state_id == new_state.state_id
    assert new_state.state_id != old_state.state_id
    assert all(
        item.status not in {"pending", "running"}
        for item in loaded.items.values()
    )


async def test_harness_lanes_js_baselines_stay_per_lane(
    monkeypatch,
) -> None:
    """T-H2 (doc 18 section 15): a JS error baselined on lane 1
    during its pre-action drain must not suppress the same error
    when the Room surfaces it as another item's evidence. With
    URL-only keying this test fails: the Room's item reads lane
    1's baseline and its js_error is silently swallowed.

    Reconciled to the as-built outcome machinery at S2 wiring:
    alpha is a field (a clean fill outcome — a plain _worked
    button would itself raise a no_effect suspicion and land in
    the confirmation machinery), and the queues script BOTH of
    beta's attempts (an observed-once item is re-executed once
    more, proof included, before the run settles it)."""

    entries = (
        _entry(1, "textbox", "Search alpha"),
        _entry(2, "button", "View beta"),
    )
    controller = _LaneController(
        pages={INVENTORY_URL: entries}, start_url=INVENTORY_URL)

    def changer(case, execution_id):
        controller.pages[INVENTORY_URL] = (
            _entry(1, "textbox", "Search alpha"),
            _entry(2, "button", "View beta"),
            _entry(3, "button", "View gamma"),
        )
        return _worked(case, execution_id)

    boom = SimpleNamespace(
        url=INVENTORY_URL, kind="pageerror", message="Boom",
        stack="stack")
    controller.js_script = {
        # Lane 1: alpha's pre-action drain baselines Boom; its
        # post-action harvest is clean. (Gamma's pair, when it
        # lanes, is clean too.)
        "worker": [[boom], [], [], []],
        # Room: crawl drain clean, beta's pre-action drain clean,
        # beta's post-action harvest surfaces Boom as evidence —
        # in attempt 1 and in the observed-once re-execution alike.
        "room": [[], [], [boom], [], [boom]],
        # Proof contexts: clean — beta's error does not reproduce.
        "proof": [[], [], [], [], [], []],
    }
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    sessions: dict[str, list[UUID]] = {}
    _install_lane_doubles(
        monkeypatch, controller=controller,
        script={
            "Check Search alpha": _worked,
            "Check View beta": changer,
            "Check View gamma": _worked,
        },
        calls=calls, sessions=sessions)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    by_name = {item.name: item for item in loaded.items.values()}
    alpha = by_name["Search alpha"]
    beta = by_name["View beta"]
    # Lane 1's own item is untouched by the error it baselined.
    assert alpha.locator.get("outcome") != "js_error"
    # The Room's item surfaces the error, is suspected, is
    # proof-executed in each attempt (calls: 2 attempts x item +
    # proof), and — the proof context being clean — lands
    # observed-once, never a defect.
    assert beta.locator["outcome"] == "js_error"
    assert calls.count("Check View beta") == 4
    assert beta.status == "could_not_check"
    assert beta.locator["tier"] == "observed_once"


async def test_harness_lanes_reseed_after_room_reauthentication(
    monkeypatch,
) -> None:
    """T-H3 (doc 18 section 15): when the Room re-authenticates
    mid-run (U-P4: a human login lands during a Room item), lanes
    seeded from the old storage state close before their next
    claim and re-open seeded fresh; and an authentication wall
    inside a lane is that item's could-not-check — the run never
    parks for a lane item."""

    entries = (
        _entry(1, "button", "View alpha"),
        _entry(2, "button", "View beta"),
        _entry(3, "button", "View delta"),
        _entry(4, "button", "View gamma"),
    )
    controller = _LaneController(
        pages={INVENTORY_URL: entries}, start_url=INVENTORY_URL)

    def login_wall(case, execution_id):
        # A satisfied Room item during which a human logged in:
        # human_wait_ms > 0 is the harness's re-authentication
        # signal (the U-P4 marking block in the tail).
        return _worked(case, execution_id).model_copy(
            update={"human_wait_ms": 5000})

    def auth_blocked(case, execution_id):
        return _result_for(
            case, execution_id, verdict="not_satisfied",
            blocker="authentication_challenge_blocked")

    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    sessions: dict[str, list[UUID]] = {}
    _install_lane_doubles(
        monkeypatch, controller=controller,
        script={
            "Check View alpha": _worked,
            "Check View beta": login_wall,
            "Check View delta": auth_blocked,
            "Check View gamma": _worked,
        },
        calls=calls, sessions=sessions)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    # Two worker sessions over the run: the stale one closed at
    # re-seed, the fresh one opened for the next lane claim.
    assert len(controller.worker_session_ids) == 2
    first_lane, second_lane = controller.worker_session_ids
    assert first_lane in controller.closed_session_ids
    assert sessions["Check View alpha"][0] == first_lane
    assert sessions["Check View delta"][0] == second_lane
    # The lane item that hit the wall: recorded, not parked.
    by_name = {item.name: item for item in loaded.items.values()}
    delta = by_name["View delta"]
    assert delta.status == "could_not_check"
    assert delta.blocker == "authentication_challenge_blocked"
    # Nothing parked and nothing was left behind: every item
    # reached a terminal status (a park returns early and would
    # leave View gamma pending forever).
    assert all(
        item.status not in {"pending", "running"}
        for item in loaded.items.values()
    )

# ------------------------------------------------------------------
# Phase 3 consumption wiring (doc 22 sections 8.2-8.4): the Board
# side of skill replay — seeding, the satisfied/diverged records,
# the mode filter, and the T-N2 live re-check. Written against the
# incumbent doubles above; execute_skill_replay's own contract is
# pinned by tests/test_skill_consumption.py. The skill's URLs live
# on the harness fixture's own origin (a skill is harvested from
# the app the run targets).
# ------------------------------------------------------------------

_CS_PRICING_URL = INVENTORY_URL.rsplit("/", 1)[0] + "/pricing"
_CS_ALT_URL = INVENTORY_URL.rsplit("/", 1)[0] + "/pricing-alt"
_CS_ELSEWHERE_URL = INVENTORY_URL.rsplit("/", 1)[0] + "/elsewhere"

def _cs_definition(**overrides):
    """The reach-pricing skill definition (the same shape
    tests/test_skill_consumption.py replays)."""
    definition = {
        "case_id": "reach_pricing_x",
        "feature_key": "map_journey_x",
        "title": "Journey: Reach pricing",
        "kind": "happy_path",
        "steps": [
            {"action": "navigate", "url": INVENTORY_URL},
            {
                "action": "click",
                "target": {"role": "link", "name": "Pricing"},
            },
        ],
        "expected": [
            {
                "assertion_id": "terminal_url",
                "oracle": "url",
                "expected_value": _CS_PRICING_URL,
                "origin": "inferred",
            }
        ],
        "safety": "non_destructive",
        "estimated_seconds": 30,
        "success_assertion": {
            "kind": "terminal_state",
            "url": _CS_PRICING_URL,
            "state_id": "state-goal",
            "element_signature": [],
            "signature_superset_fallback": False,
        },
    }
    definition.update(overrides)
    return definition


def _cs_map(*, definition=None):
    """A map block serving one active journey skill, joined to its
    journey. Returns (app_map, entry, skill_id, version_id)."""
    skill_id, version_id = uuid4(), uuid4()
    entry = {
        "name": "reach-pricing",
        "skill_id": str(skill_id),
        "skill_version_id": str(version_id),
        "version_number": 1,
        "skill_kind": "journey",
        "lifecycle_status": "active",
        "catalogue": {"name": "reach-pricing", "description": "Reach pricing"},
        "definition": definition if definition is not None else _cs_definition(),
        "package": {"name": "reach-pricing", "body_md": "# Reach pricing"},
    }
    app_map = _map_block(
        routes=[INVENTORY_URL], pages=[_map_page(INVENTORY_URL)])
    app_map["skills"] = [entry]
    app_map["skills_withheld"] = 0
    app_map["journeys"] = [{
        "name": "Reach pricing", "skill_id": str(skill_id),
        "terminal_url": _CS_PRICING_URL,
    }]
    return app_map, entry, skill_id, version_id


def _cs_version(version_id, skill_id):
    from markettwin_database.models.knowledge import SkillVersion

    return SkillVersion(
        id=version_id, workspace_id=uuid4(), skill_id=skill_id,
        version_number=1, status="draft", definition_json={},
        generation_metadata={}, lifecycle_status="active", package={},
        heal_count=0, replay_count=0,
    )


def _cs_dispatch_get(session, *, run, version):
    """session.get answers the run for every model except
    SkillVersion, which answers the test's version row (the same
    object execute_skill_replay mutates)."""
    from markettwin_database.models.knowledge import SkillVersion

    async def get(model, ident, **kwargs):
        if model is SkillVersion:
            return version
        return run

    session.get = AsyncMock(side_effect=get)


def _install_skill_replay_doubles(
    monkeypatch, *, action=None, capture_url=_CS_PRICING_URL,
):
    """Drive execute_skill_replay's browser side: step actions via
    case_execution.perform_case_action, the terminal capture via
    the harvest capture/inventory seams (the consumption tests'
    patch points), and assertion reads via the controller seam,
    answered from the same terminal page the capture reports. (The
    lane fake never implemented read_assertion; the replay's
    terminal assertion check raised AttributeError, which the
    replay recorded as a locator-shaped failure — the CS3/CS4
    regression.)"""
    from markettwin_execution_orchestrator.harvest import (
        harvest_capture,
        harvest_inventory,
    )
    from markettwin_execution_orchestrator.workflow import case_execution

    async def ok_action(controller, handle, act, scope):
        return SimpleNamespace(ok=True)

    async def fake_capture(controller, handle, *, execution_id, journey_id):
        return SimpleNamespace(url=capture_url)

    monkeypatch.setattr(
        case_execution, "perform_case_action", action or ok_action)
    monkeypatch.setattr(harvest_capture, "capture_state", fake_capture)
    monkeypatch.setattr(harvest_inventory, "distil_elements", lambda c: [])
    monkeypatch.setattr(harvest_inventory, "distil_forms", lambda c: [])
    monkeypatch.setattr(
        harvest_inventory, "identity_for",
        lambda url, e, f: ("state-goal", None, None))

    async def read_assertion(self, *, assertion, **kwargs):
        if assertion.oracle == "url":
            expected = str(assertion.expected_value or "")
            expected = expected.split("?")[0].split("#")[0]
            actual = capture_url.split("?")[0].split("#")[0]
            status = "satisfied" if expected == actual else "not_satisfied"
        else:
            status = "unverified"
        return None, SimpleNamespace(status=status)

    monkeypatch.setattr(
        _LaneController, "read_assertion", read_assertion, raising=False)


async def _cs_run(
    monkeypatch, *, app_map, version=None, snapshot=None, app_plan=None,
    script=None,
):
    """One inventory-driven harness run over a one-button page,
    with the map (and optionally a literal plan) pinned."""
    controller = _LaneController(
        pages={INVENTORY_URL: (_entry(1, "button", "View pricing"),)},
        start_url=INVENTORY_URL)
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    if snapshot is not None:
        run.configuration_snapshot = snapshot
    if version is not None:
        _cs_dispatch_get(session, run=run, version=version)
    request = replace(request, app_map=app_map, app_plan=app_plan)
    calls: list[str] = []
    _install_lane_doubles(
        monkeypatch, controller=controller,
        script=script or {"Check View pricing": _worked},
        calls=calls, sessions={})
    events = _capture_run_events(monkeypatch)
    await harness_run.execute_harness_run(request=request, session=session)
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    return run, session, loaded, events


def _board_projection(loaded):
    """The Board, minus run-scoped ids (persona/mission/journey
    uuids differ per run by construction): states and items in
    their deterministic v1 identity, with terminal accounting."""
    states = sorted(
        (s.state_id, s.url, tuple(s.element_signature),
         tuple(s.form_signature))
        for s in loaded.states.values()
    )
    items = sorted(
        (i.item_id, i.case_id, i.name, i.status, i.blocker,
         tuple(sorted((k, str(v)) for k, v in i.locator.items())))
        for i in loaded.items.values()
    )
    return {"states": states, "items": items,
            "counts": dict(loaded.counts())}


def _added_rows(session, model):
    return [call.args[0] for call in session.add.call_args_list
            if call.args and isinstance(call.args[0], model)]


async def test_cs1_board_seeds_exactly_one_skill_replay_item(monkeypatch):
    """T-CS1 (doc 22 section 8.2): a snapshot serving an active
    journey skill seeds exactly one skill_replay Board item; the
    journey's pages keep their ordinary element items and no item
    represents the journey's per-step path."""
    from markettwin_execution_orchestrator.workflow.skill_filter import (
        plan_skills_section,
    )

    app_map, entry, skill_id, version_id = _cs_map()
    section = plan_skills_section(app_map, mode="standard", approved_keys=set())
    assert len(section["replay_items"]) == 1
    version = _cs_version(version_id, skill_id)
    _install_skill_replay_doubles(monkeypatch)
    run, session, loaded, events = await _cs_run(
        monkeypatch, app_map=app_map, version=version)
    skill_items = [
        item for item in loaded.items.values()
        if item.locator.get("skill_item") is True
    ]
    assert len(skill_items) == 1
    assert skill_items[0].case_id == f"skill_replay:{skill_id}"
    assert skill_items[0].locator["item_kind"] == "skill_replay"
    by_name = {item.name: item for item in loaded.items.values()}
    assert "View pricing" in by_name  # the page's ordinary element item
    assert "Pricing" not in by_name  # no per-step path item
    assert all(
        item.case_id != "reach_pricing_x" for item in loaded.items.values()
    )


async def test_cs2_mode_filtered_skill_never_reaches_the_board(monkeypatch):
    """T-CS2 (doc 22 sections 8.1.2/8.2): in a read_only run a
    skill with a reversible step (a fill) is not selected — the
    plan names the doc-17 skip reason for it (section 8.1.2's
    recorded reason for a mode refusal) — no skill item is seeded,
    and the Board is the no-skill Board."""
    from markettwin_execution_orchestrator.workflow.harness_items import (
        NOT_EXERCISED_READ_ONLY,
    )
    from markettwin_execution_orchestrator.workflow.skill_filter import (
        plan_skills_section,
    )

    definition = _cs_definition(steps=[
        {"action": "navigate", "url": INVENTORY_URL},
        {"action": "fill", "target": {"role": "textbox", "name": "Display name"}},
    ])
    app_map, entry, skill_id, version_id = _cs_map(definition=definition)
    section = plan_skills_section(app_map, mode="read_only", approved_keys=set())
    assert section["replay_items"] == []
    assert section["not_selected_reasons"]["reach-pricing"] == (
        NOT_EXERCISED_READ_ONLY)
    version = _cs_version(version_id, skill_id)
    run, session, loaded, events = await _cs_run(
        monkeypatch, app_map=app_map, version=version,
        snapshot={"harness_run_mode": "read_only"})
    assert not any(
        item.locator.get("skill_item") for item in loaded.items.values())
    bare_map = _map_block(
        routes=[INVENTORY_URL], pages=[_map_page(INVENTORY_URL)])
    bare_map["skills"] = []
    bare_map["skills_withheld"] = 0
    bare_map["journeys"] = []
    _, _, bare_loaded, _ = await _cs_run(
        monkeypatch, app_map=bare_map,
        snapshot={"harness_run_mode": "read_only"})
    assert _board_projection(loaded) == _board_projection(bare_loaded)


async def test_cs3_successful_replay_closes_the_item_worked(monkeypatch):
    """T-CS3 (doc 22 section 8.3): a replay reaching the recorded
    terminal state closes its item worked; the Board record carries
    the section 8.3 provenance; the consumption replay row is
    context 'run' with zero model calls."""
    from markettwin_database.models.knowledge import SkillReplay

    app_map, entry, skill_id, version_id = _cs_map()
    version = _cs_version(version_id, skill_id)
    _install_skill_replay_doubles(monkeypatch)
    run, session, loaded, events = await _cs_run(
        monkeypatch, app_map=app_map, version=version)
    skill_item = next(
        item for item in loaded.items.values()
        if item.locator.get("skill_item") is True)
    assert skill_item.status == "worked"
    assert skill_item.locator["skill_body_md"] == "# Reach pricing"
    payloads = [
        p for p in _payloads(events, "board.item.result")
        if "skill_replay" in p
    ]
    assert len(payloads) == 1
    assert payloads[0]["skill_replay"] == {
        "outcome": "satisfied_by_replay",
        "skill_id": str(skill_id),
        "skill_version_id": str(version_id),
        "version_number": 1,
        "app_map_id": app_map["map_id"],
        "context": "run",
        "per_step": [
            {"order": 0, "result": "passed"},
            {"order": 1, "result": "passed"},
        ],
        "terminal_state_match": True,
    }
    replays = _added_rows(session, SkillReplay)
    assert len(replays) == 1
    replay = replays[0]
    assert replay.context_kind == "run"
    assert replay.run_id == run.id
    assert replay.board_item_ref == skill_item.item_id
    assert replay.model_calls == 0
    assert version.lifecycle_status == "active"
    assert version.replay_count == 1


async def test_active_task_replays_a_matching_case_without_a_map_journey(monkeypatch):
    from markettwin_database.models.knowledge import SkillReplay
    from markettwin_shared.task_skill import task_contract_digest

    definition = _cs_definition(steps=[{"action": "navigate", "url": _CS_PRICING_URL}])
    definition["expected"][0]["origin"] = "user_approved"
    case = {key: value for key, value in definition.items() if key != "success_assertion"}
    definition["steps"] = [{"action": "navigate", "url": INVENTORY_URL}, *case["steps"]]
    definition["task"] = {"cleanup": {"kind": "none_required"}}
    definition["task"]["contract_digest"] = task_contract_digest(definition)
    app_map, entry, skill_id, version_id = _cs_map(definition=definition)
    entry["skill_kind"] = "task"
    app_map["journeys"] = []
    version = _cs_version(version_id, skill_id)
    version.app_map_id = UUID(app_map["map_id"])
    _install_skill_replay_doubles(monkeypatch)

    _, session, loaded, _ = await _cs_run(
        monkeypatch, app_map=app_map, version=version,
        snapshot={
            "app_map": app_map,
            "learn_task": True,
            "harness_work_list": [{"case": case, "role_name": ("page", "Pricing", 0)}],
        },
    )
    item = next(item for item in loaded.items.values() if item.case_id == case["case_id"])
    assert item.status == "worked"
    assert item.locator["skill_version_id"] == str(version_id)
    replay, = _added_rows(session, SkillReplay)
    assert replay.result == "passed" and replay.model_calls == 0


async def test_cs4_locator_divergence_demotes_and_falls_back(monkeypatch):
    """T-CS4a (doc 22 section 8.4.3): a step whose element no
    longer resolves closes the item could_not_check naming the
    step; the version demotes to suspect; the replay row, the
    demotion and run_replay usage events, and the run-side
    divergence event (shape 'locator', fallback named) are all
    written; the journey is not counted replay-satisfied."""
    from markettwin_database.models.knowledge import (
        SkillReplay,
        SkillUsageEvent,
    )

    async def failing_action(controller, handle, act, scope):
        if act.action == "click":
            raise RuntimeError("element not found")
        return SimpleNamespace(ok=True)

    app_map, entry, skill_id, version_id = _cs_map()
    version = _cs_version(version_id, skill_id)
    _install_skill_replay_doubles(monkeypatch, action=failing_action)
    run, session, loaded, events = await _cs_run(
        monkeypatch, app_map=app_map, version=version)
    skill_item = next(
        item for item in loaded.items.values()
        if item.locator.get("skill_item") is True)
    assert skill_item.status == "could_not_check"
    assert "step 1" in (skill_item.blocker or "")
    assert "case_execution:RuntimeError" in (skill_item.blocker or "")
    assert version.lifecycle_status == "suspect"
    replays = _added_rows(session, SkillReplay)
    assert len(replays) == 1
    assert replays[0].result == "failed"
    assert replays[0].failure_step == 1
    usage = _added_rows(session, SkillUsageEvent)
    kinds = [row.kind for row in usage]
    assert "demotion" in kinds and "run_replay" in kinds
    assert "quarantine" not in kinds
    demotion = next(row for row in usage if row.kind == "demotion")
    assert demotion.from_status == "active"
    assert demotion.to_status == "suspect"
    diverged = _payloads(events, "harness.skill.diverged")
    assert len(diverged) == 1
    assert diverged[0]["shape"] == "locator"
    assert diverged[0]["fallback"] == "live_exploration"
    payloads = [
        p for p in _payloads(events, "board.item.result")
        if "skill_replay" in p
    ]
    assert payloads[0]["skill_replay"]["outcome"] == "diverged"


async def test_cs4_assertion_divergence_quarantines_without_heal(monkeypatch):
    """T-CS4b (doc 22 section 8.4.2): steps complete but the
    terminal state differs — the version quarantines at once, no
    heal is attempted, and the divergence event names the
    assertion shape."""
    from markettwin_database.models.knowledge import (
        SkillReplay,
        SkillUsageEvent,
    )

    app_map, entry, skill_id, version_id = _cs_map()
    version = _cs_version(version_id, skill_id)
    _install_skill_replay_doubles(
        monkeypatch, capture_url=_CS_ELSEWHERE_URL)
    run, session, loaded, events = await _cs_run(
        monkeypatch, app_map=app_map, version=version)
    skill_item = next(
        item for item in loaded.items.values()
        if item.locator.get("skill_item") is True)
    assert skill_item.status == "could_not_check"
    assert version.lifecycle_status == "quarantined"
    replays = _added_rows(session, SkillReplay)
    assert len(replays) == 1
    assert replays[0].result == "failed"
    assert replays[0].heal_cycle is False
    usage = _added_rows(session, SkillUsageEvent)
    kinds = [row.kind for row in usage]
    assert "quarantine" in kinds and "run_replay" in kinds
    assert "demotion" not in kinds
    assert not any(kind.startswith("heal") for kind in kinds)
    diverged = _payloads(events, "harness.skill.diverged")
    assert len(diverged) == 1
    assert diverged[0]["shape"] == "assertion"
    assert diverged[0]["fallback"] == "live_exploration"


async def test_cs5_irreversible_skill_is_unselectable_in_both_modes(
    monkeypatch,
):
    """T-CS5 (doc 22 sections 8.1/8.3): a skill with an
    irreversible step is refused at planning in standard mode too,
    and execute_skill_replay's execution-time re-check refuses it
    without recording anything."""
    from markettwin_execution_orchestrator.workflow import case_execution
    from markettwin_execution_orchestrator.workflow.harness_items import (
        NOT_EXERCISED_IRREVERSIBLE,
    )
    from markettwin_execution_orchestrator.workflow.skill_filter import (
        plan_skills_section,
    )

    definition = _cs_definition(steps=[
        {"action": "navigate", "url": INVENTORY_URL},
        {
            "action": "click",
            "target": {"role": "button", "name": "Delete account"},
        },
    ])
    app_map, entry, skill_id, version_id = _cs_map(definition=definition)
    section = plan_skills_section(app_map, mode="standard", approved_keys=set())
    assert section["replay_items"] == []
    assert section["not_selected_reasons"]["reach-pricing"] == (
        NOT_EXERCISED_IRREVERSIBLE)

    class _FakeSession:
        def __init__(self, *, run, version):
            self._run = run
            self._version = version
            self.added: list = []

        async def get(self, model, ident):
            from markettwin_database.models.knowledge import SkillVersion

            if model is SkillVersion:
                return self._version
            return self._run

        def add(self, row):
            self.added.append(row)

        async def flush(self):
            return None

        async def commit(self):
            return None

        async def rollback(self):
            return None

    run = SimpleNamespace(
        id=uuid4(),
        configuration_snapshot={
            "harness_run_mode": "standard",
            "app_map": {"map_id": str(uuid4())},
        },
        run_kind="explore_test",
    )
    version = _cs_version(version_id, skill_id)
    session = _FakeSession(run=run, version=version)
    request = SimpleNamespace(
        test_run_id=run.id, journey_id=uuid4(), execution_id=uuid4(),
        allowed_origins=(
            SimpleNamespace(scheme="http", hostname="127.0.0.1", port=5199),
        ),
    )
    outcome = await case_execution.execute_skill_replay(
        request=request, controller=SimpleNamespace(),
        handle=SimpleNamespace(
            session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4()),
        session=session,
        skill_entry={
            "name": "reach-pricing",
            "skill_id": str(skill_id),
            "skill_version_id": str(version_id),
            "definition": definition,
        },
        board_item_ref="board:skill:1",
    )
    assert outcome["status"] == "mode_filtered"
    assert session.added == []
    assert version.lifecycle_status == "active"


async def test_cs6_no_active_skills_matches_the_pre_phase3_board(monkeypatch):
    """T-CS6 (doc 22 section 8.2): a snapshot with an empty skills
    block changes nothing — the Board equals the Board a
    pre-Phase-3 snapshot (no skills keys at all) produces."""
    from markettwin_execution_orchestrator.workflow.skill_filter import (
        plan_skills_section,
    )

    map_a = _map_block(
        routes=[INVENTORY_URL], pages=[_map_page(INVENTORY_URL)])
    map_a["skills"] = []
    map_a["skills_withheld"] = 0
    map_a["journeys"] = []
    section = plan_skills_section(map_a, mode="standard", approved_keys=set())
    assert section["replay_items"] == []
    assert section["active"] == 0
    _, _, loaded_a, _ = await _cs_run(monkeypatch, app_map=map_a)
    map_b = _map_block(
        routes=[INVENTORY_URL], pages=[_map_page(INVENTORY_URL)])
    _, _, loaded_b, _ = await _cs_run(monkeypatch, app_map=map_b)
    assert _board_projection(loaded_a) == _board_projection(loaded_b)


async def test_n2_mid_run_demotion_is_never_reselected(monkeypatch):
    """T-N2 (doc 22 section 8.3): two replay items share one
    version; the first item's replay diverges and demotes it, so
    the second item closes not_checked naming the demotion and
    writes no second replay row."""
    from markettwin_database.models.knowledge import SkillReplay

    async def failing_action(controller, handle, act, scope):
        if act.action == "click":
            raise RuntimeError("element not found")
        return SimpleNamespace(ok=True)

    app_map, entry, skill_id, version_id = _cs_map()
    replay_items = [
        {
            "skill_id": str(skill_id),
            "skill_version_id": str(version_id),
            "journey_name": "Reach pricing",
            "terminal_url": _CS_PRICING_URL,
        },
        {
            "skill_id": str(skill_id),
            "skill_version_id": str(version_id),
            "journey_name": "Reach pricing (alt)",
            "terminal_url": _CS_ALT_URL,
        },
    ]
    app_plan = {
        "checks": [],
        "skills": {
            "active": 1,
            "replay_items": replay_items,
            "mode_filtered": [],
            "not_selected_reasons": {},
            "withheld": 0,
        },
    }
    version = _cs_version(version_id, skill_id)
    _install_skill_replay_doubles(monkeypatch, action=failing_action)
    run, session, loaded, events = await _cs_run(
        monkeypatch, app_map=app_map, version=version, app_plan=app_plan)
    skill_items = [
        item for item in loaded.items.values()
        if item.locator.get("skill_item") is True
    ]
    assert len(skill_items) == 2
    by_journey = {
        item.locator.get("journey_name"): item for item in skill_items}
    first = by_journey["Reach pricing"]
    second = by_journey["Reach pricing (alt)"]
    assert first.status == "could_not_check"
    assert version.lifecycle_status == "suspect"
    assert second.status == "not_checked"
    assert "no longer active" in (second.blocker or "")
    assert len(_added_rows(session, SkillReplay)) == 1


async def test_harness_close_lanes_tolerates_pre_closed_lane_session(
    monkeypatch,
) -> None:
    """Regression (MT-000159, 2026-11-18): a lane session that case
    execution already closed and removed (fatal browser error) must
    not fail the whole run when _close_lanes closes lanes at
    teardown - the close goal is already met, the row is still
    marked closed, and the run completes."""

    entries = (
        _entry(1, "button", "View alpha"),
        _entry(2, "button", "View beta"),
    )
    controller = _LaneController(
        pages={INVENTORY_URL: entries}, start_url=INVENTORY_URL)

    def changer(case, execution_id):
        controller.pages[INVENTORY_URL] = (
            _entry(1, "button", "View alpha"),
            _entry(2, "button", "View beta"),
            _entry(3, "button", "View gamma"),
        )
        return _worked(case, execution_id)

    close_attempts: list[UUID] = []

    async def close_session(*, session_id):
        close_attempts.append(session_id)
        if session_id in controller.worker_session_ids:
            raise BrowserSessionNotFoundError(
                f"Browser session {session_id} does not exist.")
        return None

    controller.close_session = close_session

    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    sessions: dict[str, list[UUID]] = {}
    _install_lane_doubles(
        monkeypatch, controller=controller,
        script={
            "Check View alpha": _worked,
            "Check View beta": changer,
            "Check View gamma": _worked,
        },
        calls=calls, sessions=sessions)
    await harness_run.execute_harness_run(request=request, session=session)
    assert len(controller.worker_session_ids) == 1
    assert controller.worker_session_ids[0] in close_attempts
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    assert loaded.counts()["pending"] == 0



def _record_persisted_events(monkeypatch):
    """Record (event_type, payload) for every persist_harness_state
    call in the run, delegating to the real function. The _cs_run
    event capture only sees harness_run's own RunEventRepository;
    persist events travel the harness_state repository instead."""
    persisted: list = []
    real_persist = harness_run.persist_harness_state

    async def recording_persist(session, run, state, **kwargs):
        persisted.append((kwargs.get("event_type"), kwargs.get("payload") or {}))
        return await real_persist(session, run, state, **kwargs)

    monkeypatch.setattr(harness_run, "persist_harness_state", recording_persist)
    return persisted


async def test_fix1_task_skill_with_inputs_replays_via_general_matcher(monkeypatch):
    """FIX-1(a): a task skill declaring inputs is refused by the
    read-only matcher (task.inputs non-empty) but consumed by the
    general matcher when the run's approved values cover the
    declared keys: the planned case replays with zero model calls."""
    import copy

    from markettwin_database.models.knowledge import SkillReplay
    from markettwin_shared.task_skill import task_contract_digest

    definition = _cs_definition(steps=[
        {"action": "fill", "target": {"label": "Display name"},
         "test_value_key": "valid_name"},
        {"action": "navigate", "url": _CS_PRICING_URL},
    ])
    definition["expected"][0]["origin"] = "user_approved"
    case = {key: value for key, value in definition.items() if key != "success_assertion"}
    definition["steps"] = [{"action": "navigate", "url": INVENTORY_URL}, *case["steps"]]
    definition["task"] = {
        "cleanup": {"kind": "none_required"},
        "inputs": [{"key": "valid_name", "required": True}],
    }
    # (snapshot gains harness_run_mode below: the fill is
    # state-changing, so the run must be standard, not the
    # fail-closed read_only default.)
    definition["task"]["contract_digest"] = task_contract_digest(definition)
    app_map, entry, skill_id, version_id = _cs_map(definition=definition)
    entry["skill_kind"] = "task"
    app_map["journeys"] = []
    version = _cs_version(version_id, skill_id)
    version.app_map_id = UUID(app_map["map_id"])
    _install_skill_replay_doubles(monkeypatch)
    stored_before = copy.deepcopy(definition)

    _, session, loaded, _ = await _cs_run(
        monkeypatch, app_map=app_map, version=version,
        snapshot={
            "app_map": app_map,
            "learn_task": True,
            "harness_run_mode": "standard",
            "approved_test_data": [{"key": "valid_name", "value": "Visitor"}],
            "harness_work_list": [{"case": case, "role_name": ("page", "Pricing", 0)}],
        },
    )
    item = next(item for item in loaded.items.values() if item.case_id == case["case_id"])
    assert item.status == "worked"
    assert item.locator["skill_version_id"] == str(version_id)
    replay, = _added_rows(session, SkillReplay)
    assert replay.result == "passed" and replay.model_calls == 0
    # The matcher rebound a copy: the stored definition is untouched.
    assert entry["definition"] == stored_before


async def test_fix1_non_match_records_not_selected_and_executes_live(monkeypatch):
    """FIX-1(b): when the general matcher declines (the planned
    case's contract differs from the skill's), the run records
    harness.skill.not_selected with the matcher's reason and the
    case still executes live through the normal loop."""
    from markettwin_database.models.knowledge import SkillReplay
    from markettwin_shared.task_skill import task_contract_digest

    definition = _cs_definition(steps=[{"action": "navigate", "url": _CS_PRICING_URL}])
    definition["expected"][0]["origin"] = "user_approved"
    case = {key: value for key, value in definition.items() if key != "success_assertion"}
    definition["steps"] = [{"action": "navigate", "url": INVENTORY_URL}, *case["steps"]]
    definition["task"] = {"cleanup": {"kind": "none_required"}}
    definition["task"]["contract_digest"] = task_contract_digest(definition)
    # The planned case diverges from the skill's contract: a step
    # the skill does not perform.
    case = {**case, "steps": [*case["steps"],
            {"action": "navigate", "url": _CS_ALT_URL}]}
    app_map, entry, skill_id, version_id = _cs_map(definition=definition)
    entry["skill_kind"] = "task"
    app_map["journeys"] = []
    version = _cs_version(version_id, skill_id)
    version.app_map_id = UUID(app_map["map_id"])
    _install_skill_replay_doubles(monkeypatch)
    persisted = _record_persisted_events(monkeypatch)

    _, session, loaded, events = await _cs_run(
        monkeypatch, app_map=app_map, version=version,
        snapshot={
            "app_map": app_map,
            "learn_task": True,
            "harness_work_list": [{"case": case, "role_name": ("page", "Pricing", 0)}],
        },
        script={"Check View pricing": _worked, case["title"]: _worked},
    )
    not_selected = [
        p for event_type, p in persisted
        if event_type == "harness.skill.not_selected"
        and p.get("case_id") == case["case_id"]
    ]
    assert len(not_selected) == 1
    assert not_selected[0]["reason"] == "contract_mismatch"
    item = next(item for item in loaded.items.values() if item.case_id == case["case_id"])
    assert item.status == "worked"
    assert "skill_version_id" not in item.locator
    assert _added_rows(session, SkillReplay) == []


async def test_fix1_diverged_task_replay_falls_back_to_live_exploration(monkeypatch):
    """FIX-1(c): a matched task replay that diverges does not end
    the case. The replay's record stands (failed row, divergence
    event, version quarantined) and the same item is then explored
    live in the same run -- no extra Board item is created."""
    from markettwin_database.models.knowledge import SkillReplay
    from markettwin_shared.task_skill import task_contract_digest

    definition = _cs_definition(steps=[{"action": "navigate", "url": _CS_PRICING_URL}])
    definition["expected"][0]["origin"] = "user_approved"
    case = {key: value for key, value in definition.items() if key != "success_assertion"}
    definition["steps"] = [{"action": "navigate", "url": INVENTORY_URL}, *case["steps"]]
    definition["task"] = {"cleanup": {"kind": "none_required"}}
    definition["task"]["contract_digest"] = task_contract_digest(definition)
    app_map, entry, skill_id, version_id = _cs_map(definition=definition)
    entry["skill_kind"] = "task"
    app_map["journeys"] = []
    version = _cs_version(version_id, skill_id)
    version.app_map_id = UUID(app_map["map_id"])
    # The replay's terminal capture lands elsewhere: the recorded
    # outcome no longer holds -- assertion-shaped divergence.
    _install_skill_replay_doubles(monkeypatch, capture_url=_CS_ELSEWHERE_URL)

    _, session, loaded, events = await _cs_run(
        monkeypatch, app_map=app_map, version=version,
        snapshot={
            "app_map": app_map,
            "learn_task": True,
            "harness_work_list": [{"case": case, "role_name": ("page", "Pricing", 0)}],
        },
        script={"Check View pricing": _worked, case["title"]: _worked},
    )
    case_items = [i for i in loaded.items.values() if i.case_id == case["case_id"]]
    assert len(case_items) == 1
    item = case_items[0]
    assert item.status == "worked"  # the live outcome, not could_not_check
    assert version.lifecycle_status == "quarantined"
    replay, = _added_rows(session, SkillReplay)
    assert replay.result == "failed" and replay.model_calls == 0
    diverged = _payloads(events, "harness.skill.diverged")
    assert len(diverged) == 1 and diverged[0]["shape"] == "assertion"


async def test_owner_stop_drains_the_board_and_cancels_the_run(monkeypatch) -> None:
    """Owner stop (the Stop run button): ctl records an owner_stop
    flag in the run's configuration snapshot mid-run; the engine
    honours it at the next item boundary — the item in flight
    finishes, the remaining items close named not_checked with the
    blocker "stopped by owner", every item still publishes its
    board.item.result, and the run closes cancelled, never
    completed."""
    entries = (
        _entry(1, "button", "Search alpha"),
        _entry(2, "button", "Search beta"),
        _entry(3, "button", "Search gamma"),
    )
    controller = _FakeInventoryController(
        pages={INVENTORY_URL: entries}, start_url=INVENTORY_URL)
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)

    def stop_after_first(case, execution_id):
        # The ctl write landing while Alpha executes: the snapshot
        # the engine fresh-reads at the next boundary now carries
        # the flag (the fixture session returns this same run row).
        run.configuration_snapshot = {
            **run.configuration_snapshot,
            "owner_stop": {"requested_at": "2026-11-18T20:34:00+00:00",
                           "requested_by": "owner"},
        }
        return _worked(case, execution_id)

    calls: list[str] = []
    _install_inventory_doubles(
        monkeypatch, controller=controller, calls=calls,
        script={"Check Search alpha": stop_after_first,
                "Check Search beta": _worked, "Check Search gamma": _worked})
    states = Mock(mark_running=AsyncMock(), mark_completed=AsyncMock(),
                  mark_cancelled=AsyncMock())
    monkeypatch.setattr(harness_run, "RunStateRepository", lambda _: states)
    # One lane: execution is sequential, so the boundary the flag
    # lands on is exact — beta and gamma are still pending when it
    # lands (with worker lanes they could already be in flight,
    # which is the drain case, not this one).
    monkeypatch.setattr(harness_run, "HARNESS_LANE_COUNT", 1)
    run_events = _capture_run_events(monkeypatch)
    await harness_run.execute_harness_run(request=request, session=session)
    assert calls == ["Check Search alpha"]
    loaded = await load_harness_state(session, run_id)
    assert loaded is not None
    stopped_items = [
        item for item in loaded.items.values()
        if item.blocker == "stopped by owner"
    ]
    assert len(stopped_items) == 2
    assert all(item.status == "not_checked" for item in stopped_items)
    assert loaded.counts()["pending"] == 0
    results = _payloads(run_events, "board.item.result")
    assert len(results) == 3
    assert _payloads(run_events, "harness.run.owner_stop")
    states.mark_cancelled.assert_awaited_once()
    states.mark_completed.assert_not_awaited()
    assert run.configuration_snapshot["harness_stage"] == "done"

async def test_lead_checkpoint_opens_requested_knowledge_file(monkeypatch) -> None:
    """SKR step 1: at a Lead checkpoint the harness offers the
    collection manifest minus already-loaded files as candidates,
    and executes the Lead's approved opens against the plan before
    the next item runs."""
    entries = tuple(_entry(i + 1, "button", f"Search {i}") for i in range(6))
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    loaded_id, wanted_id = str(uuid4()), str(uuid4())
    app_plan = {"checks": [], "routes": [INVENTORY_URL], "source_knowledge": {
        "files": [{"file_id": loaded_id, "slug": "pricing", "title": "Pricing",
                   "text": "# Pricing", "token_count": 3, "via": "direct"}],
        "collections": [{"entry_id": str(uuid4()), "version": 1, "manifest": [
            {"file_id": loaded_id, "slug": "pricing", "title": "Pricing",
             "description": "Plan prices."},
            {"file_id": wanted_id, "slug": "refunds", "title": "Refunds",
             "description": "Refund windows and exceptions."},
        ]}],
        "budget": {"limit": 24000, "used_tokens": 3},
    }}
    request = replace(request, app_plan=app_plan)
    calls: list[str] = []
    script = {f"Check Search {i}": _worked for i in range(6)}
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script=script, calls=calls)
    reviews: list[dict[str, object]] = []

    async def review(**kwargs):
        reviews.append(kwargs)
        return {"decision": "continue", "reason": "Need refunds.",
                "source": "test", "knowledge_open_requests": [wanted_id]}

    monkeypatch.setattr(
        harness_run, "review_checkpoint", AsyncMock(side_effect=review))
    opens: list[dict[str, object]] = []

    async def fake_open(**kwargs):
        opens.append(kwargs)
        kwargs["plan"]["source_knowledge"]["files"].append(
            {"file_id": kwargs["file_id"], "slug": "refunds", "via": "midrun"})
        return {"status": "opened", "file_id": kwargs["file_id"]}

    monkeypatch.setattr(
        harness_run, "open_knowledge_file", AsyncMock(side_effect=fake_open))
    await harness_run.execute_harness_run(request=request, session=session)
    assert reviews, "the Lead checkpoint never fired"
    assert reviews[0]["knowledge_candidates"] == [
        {"file_id": wanted_id, "title": "Refunds",
         "description": "Refund windows and exceptions."},
    ]
    assert len(opens) == 1
    assert opens[0]["file_id"] == wanted_id
    assert opens[0]["run_id"] == run_id
    assert opens[0]["plan"] is app_plan
    assert opens[0]["session"] is session
    loaded = app_plan["source_knowledge"]["files"]
    assert [f["file_id"] for f in loaded] == [loaded_id, wanted_id]
    assert run.configuration_snapshot["harness_stage"] == "done"


async def test_lead_checkpoint_without_source_knowledge_passes_no_candidates(
    monkeypatch,
) -> None:
    """SKR step 1: a run with no app plan offers no candidates and
    never touches the open tool (pre-doc-33 behaviour, unchanged)."""
    entries = tuple(_entry(i + 1, "button", f"Search {i}") for i in range(6))
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    calls: list[str] = []
    script = {f"Check Search {i}": _worked for i in range(6)}
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script=script, calls=calls)
    reviews: list[dict[str, object]] = []

    async def review(**kwargs):
        reviews.append(kwargs)
        return {"decision": "continue", "reason": "Fixture", "source": "test"}

    monkeypatch.setattr(
        harness_run, "review_checkpoint", AsyncMock(side_effect=review))
    open_mock = AsyncMock()
    monkeypatch.setattr(harness_run, "open_knowledge_file", open_mock)
    await harness_run.execute_harness_run(request=request, session=session)
    assert reviews, "the Lead checkpoint never fired"
    assert reviews[0]["knowledge_candidates"] is None
    open_mock.assert_not_called()

async def test_lead_checkpoint_refused_knowledge_open_does_not_fail_the_run(
    monkeypatch,
) -> None:
    """SKR step 1: a refused mid-run open (the loader returns its
    refusal dict, e.g. budget) is absorbed by the harness - the run
    completes and the file simply stays unloaded."""
    entries = tuple(_entry(i + 1, "button", f"Search {i}") for i in range(6))
    controller = _FakeInventoryController(pages={INVENTORY_URL: entries},
                                          start_url=INVENTORY_URL)
    run_id = uuid4()
    run, session, request = _inventory_run(run_id, start_url=INVENTORY_URL)
    wanted_id = str(uuid4())
    app_plan = {"checks": [], "routes": [INVENTORY_URL], "source_knowledge": {
        "files": [],
        "collections": [{"entry_id": str(uuid4()), "version": 1, "manifest": [
            {"file_id": wanted_id, "slug": "refunds", "title": "Refunds",
             "description": "Refund windows and exceptions."},
        ]}],
        "budget": {"limit": 24000, "used_tokens": 0},
    }}
    request = replace(request, app_plan=app_plan)
    calls: list[str] = []
    script = {f"Check Search {i}": _worked for i in range(6)}
    _install_inventory_doubles(monkeypatch, controller=controller,
                               script=script, calls=calls)

    async def review(**kwargs):
        return {"decision": "continue", "reason": "Need refunds.",
                "source": "test", "knowledge_open_requests": [wanted_id]}

    monkeypatch.setattr(
        harness_run, "review_checkpoint", AsyncMock(side_effect=review))
    opens: list[dict[str, object]] = []

    async def fake_open(**kwargs):
        opens.append(kwargs)
        return {"status": "refused", "reason": "budget",
                "file_id": kwargs["file_id"]}

    monkeypatch.setattr(
        harness_run, "open_knowledge_file", AsyncMock(side_effect=fake_open))
    await harness_run.execute_harness_run(request=request, session=session)
    assert len(opens) == 1
    assert opens[0]["file_id"] == wanted_id
    assert app_plan["source_knowledge"]["files"] == []
    assert run.configuration_snapshot["harness_stage"] == "done"
