"""Doc 21 sections 8/10: Board-oracle wiring tests (T-BO2..T-BO8,
T-SN3, T-SN4). T-BO1 (the shared eligibility rules) lives in
shared-python's test_expectation_gates.py."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).parent))  # for grounding_fakes

import pytest

from markettwin_execution_orchestrator.workflow import app_plan, harness_run
from markettwin_execution_orchestrator.workflow.harness_items import (
    case_for_item,
    case_id_for,
)
from markettwin_execution_orchestrator.workflow.harness_state import (
    item_id_for,
    new_harness_state,
)

pytestmark = pytest.mark.asyncio

START = "https://app.example.com/"
OTHER = "https://app.example.com/checkout"


def make_entry(**overrides):
    entry = {
        "id": str(uuid4()),
        "subject_kind": "element",
        "subject_id": str(uuid4()),
        "page_url": START,
        "statement": "'Buy now' is present and visible",
        "oracle_source": "documentation",
        "source_ref": "entry-1:0",
        "status": "unverified",
        "verdict_eligible": True,
        "conflicted": False,
        "has_open_conflict": False,
        "assertion": {
            "kind": "element_state",
            "subject": {
                "element_id": str(uuid4()),
                "state_id": str(uuid4()),
                "role": "button",
                "name": "Buy now",
                "locators": [],
            },
            "params": {"oracle": "visible"},
        },
        "assertion_kind": "element_state",
        "assertion_origin": "deterministic",
        "promoted": False,
    }
    entry.update(overrides)
    return entry


def _board_with_buy_item():
    state = new_harness_state()
    page = state.add_state(
        url=START, elements=[("button", "Buy now")], form_fields=()
    )
    item = state.add_item(
        state_id=page.state_id,
        case_id=case_id_for(item_id_for(page.state_id, "button", "Buy now", 0)),
        role="button",
        name="Buy now",
        occurrence_index=0,
    )
    cases = {
        item.case_id: case_for_item(
            item=item, state_url=START, feature_key="feat", start_url=START
        )
    }
    return state, item, cases


def test_t_bo2_element_expectation_attaches_to_inventory_item():
    state, item, cases = _board_with_buy_item()
    entry = make_entry()
    before = len(cases[item.case_id].expected)
    seeded = harness_run._seed_expectation_items(
        state,
        cases,
        app_map={"expectations": [entry]},
        feature_key="feat",
        start_url=START,
        safety_mode="read_only",
    )
    assert seeded == []  # attached, not a new item
    assert len(state.ordered_items()) == 1
    assert len(cases[item.case_id].expected) == before + 1
    assert cases[item.case_id].expected[-1].assertion_id == "expectation"
    assert item.locator["expectation_id"] == entry["id"]


def test_t_bo3_dedicated_expectation_item_and_case():
    state, _item, cases = _board_with_buy_item()
    entry = make_entry(
        subject_kind="page",
        page_url=OTHER,
        statement="The checkout page shows 'Payment'",
        assertion={
            "kind": "page_text",
            "subject": {"page_id": str(uuid4())},
            "params": {"text": "Payment", "present": True},
        },
        assertion_kind="page_text",
    )
    seeded = harness_run._seed_expectation_items(
        state,
        cases,
        app_map={"expectations": [entry]},
        feature_key="feat",
        start_url=START,
        safety_mode="read_only",
    )
    assert len(seeded) == 1
    item, case = seeded[0]
    assert item.locator["item_kind"] == "expectation"
    assert item.locator["expectation_id"] == entry["id"]
    assert case.steps[0].action == "navigate"
    assert case.steps[0].url == OTHER
    assert case.expected[0].oracle == "visible_text"


def test_t_bo4_ineligible_conflicted_and_journey_terminal_not_seeded():
    state, _item, cases = _board_with_buy_item()
    entries = [
        make_entry(verdict_eligible=False),
        make_entry(verdict_eligible=False, conflicted=True, status="conflicted"),
        make_entry(
            subject_kind="journey",
            assertion={
                "kind": "journey_terminal",
                "subject": {"journey_id": str(uuid4()), "success_state_id": str(uuid4())},
                "params": {},
            },
            assertion_kind="journey_terminal",
        ),
        make_entry(
            assertion={
                "kind": "field_validation",
                "subject": {"field_id": str(uuid4()), "label": "Email"},
                "params": {"probe_case": "empty", "expected_error_text": "Required"},
            },
            assertion_kind="field_validation",
            subject_kind="field",
        ),
    ]
    seeded = harness_run._seed_expectation_items(
        state,
        cases,
        app_map={"expectations": entries},
        feature_key="feat",
        start_url=START,
        safety_mode="read_only",  # field_validation needs standard mode
    )
    assert seeded == []
    assert len(state.ordered_items()) == 1


def test_t_bo5_statement_only_expectation_not_seeded():
    state, _item, cases = _board_with_buy_item()
    entry = make_entry(assertion=None, assertion_kind=None, assertion_origin=None)
    seeded = harness_run._seed_expectation_items(
        state,
        cases,
        app_map={"expectations": [entry]},
        feature_key="feat",
        start_url=START,
        safety_mode="standard",
    )
    assert seeded == []


async def test_t_bo6_graph_checks_without_prose_fallback():
    """R0: the prose fallback is retired. A map carrying a
    verdict-eligible expectation marks the plan graph-sourced and no
    checks are generated in the plan itself; without one, the plan
    generates no checks at all (build_app_plan makes no model call).
    """

    def request(app_map):
        return SimpleNamespace(
            app_map=app_map,
            allowed_origins=[],
            network_policy=None,
            start_url=START,
            study_brief="Study the app",
        )

    plan = await app_plan.build_app_plan(
        request({"routes": [], "expectations": [make_entry()]})
    )
    assert plan["checks"] == []
    assert plan["expectation_checks"] == "graph"

    plan2 = await app_plan.build_app_plan(request({"routes": []}))
    assert plan2["expectation_checks"] == "none"
    assert plan2["checks"] == []


class FakeFeedbackSession:
    def __init__(self, row):
        self.row = row
        self.added: list = []
        self.flushed = False

    async def get(self, model, key):
        return self.row

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True

    async def rollback(self):
        pass

    async def execute(self, stmt):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(first=lambda: None)
        )


def _feedback_item(state, item, status, entries):
    item.status = status
    item.locator["expectations"] = entries
    item.locator["expectation_id"] = entries[0]["id"]
    return item


def _expectation_row(entry, **overrides):
    from markettwin_database.models.knowledge import MapExpectation

    values = dict(
        id=UUID(entry["id"]),
        workspace_id=uuid4(),
        application_id=uuid4(),
        target_id=uuid4(),
        app_map_id=uuid4(),
        subject_kind="element",
        subject_id=uuid4(),
        statement=entry["statement"],
        oracle_source="documentation",
        status="unverified",
        source_ref="entry-1:0",
        confidence="high",
    )
    values.update(overrides)
    return MapExpectation(**values)


async def test_t_bo7_feedback_writes_back_only_worked_or_broken():
    state, item, _cases = _board_with_buy_item()
    entry = make_entry()
    row = _expectation_row(entry)
    session = FakeFeedbackSession(row)
    await harness_run._record_expectation_check(
        session=session,
        run_id=uuid4(),
        item=_feedback_item(state, item, "worked", [entry]),
    )
    assert row.status == "replay-verified"
    assert row.last_check_result == "passed"
    assert row.last_checked_at is not None
    assert [e.event_type for e in session.added] == ["checked"]

    # Broken documentation: conflict opens, status conflicted.
    entry2 = make_entry()
    row2 = _expectation_row(entry2)
    session2 = FakeFeedbackSession(row2)
    state2, item2, _ = _board_with_buy_item()
    await harness_run._record_expectation_check(
        session=session2,
        run_id=uuid4(),
        item=_feedback_item(state2, item2, "broken", [entry2]),
    )
    assert row2.status == "conflicted"
    assert row2.last_check_result == "failed"
    kinds = [type(e).__name__ for e in session2.added]
    assert "MapConflict" in kinds

    # could_not_check writes nothing.
    entry3 = make_entry()
    row3 = _expectation_row(entry3)
    session3 = FakeFeedbackSession(row3)
    state3, item3, _ = _board_with_buy_item()
    await harness_run._record_expectation_check(
        session=session3,
        run_id=uuid4(),
        item=_feedback_item(state3, item3, "could_not_check", [entry3]),
    )
    assert session3.added == []
    assert row3.status == "unverified"
    assert row3.last_checked_at is None

    # Observation records never move toward eligibility.
    entry4 = make_entry(oracle_source="observation")
    row4 = _expectation_row(entry4, oracle_source="observation")
    session4 = FakeFeedbackSession(row4)
    state4, item4, _ = _board_with_buy_item()
    await harness_run._record_expectation_check(
        session=session4,
        run_id=uuid4(),
        item=_feedback_item(state4, item4, "worked", [entry4]),
    )
    assert row4.status == "unverified"
    assert row4.last_check_result == "passed"


async def test_t_bo8_board_result_cites_expectation_id(monkeypatch):
    captured: dict = {}

    class FakeEvents:
        def __init__(self, session):
            pass

        async def create(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(harness_run, "RunEventRepository", FakeEvents)
    state, item, _cases = _board_with_buy_item()
    entry = make_entry()
    item.locator["expectation_id"] = entry["id"]
    await harness_run._publish_board_item_result(
        session=None, run_id=uuid4(), item=item, execution_id=None
    )
    assert captured["payload"]["expectation_id"] == entry["id"]

    captured.clear()
    state2, item2, _ = _board_with_buy_item()
    await harness_run._publish_board_item_result(
        session=None, run_id=uuid4(), item=item2, execution_id=None
    )
    assert "expectation_id" not in captured["payload"]


def _brief(app_map):
    request = SimpleNamespace(app_map=app_map)
    return app_plan.build_map_brief({}, request)


def test_t_sn3_phase2_brief_lines():
    entry = make_entry()
    brief = _brief(
        {
            "journeys": [{"name": "Buy", "intent": "Buy"}],
            "counts": {"expected": 2, "reachable": 2},
            "expectations": [entry],
            "open_conflicts": [{"id": str(uuid4())}],
            "coverage": {
                "journeys_total": 1,
                "journeys_with_expectations": 1,
                "journeys_without_expectations": [],
            },
        }
    )
    assert (
        "Expectations from the map: 1 (1 doc-sourced, 0 owner rules, "
        "1 verdict-grade, 1 conflicted-open)." in brief
    )
    assert "Journey coverage: 1/1 journeys carry ≥1 expectation." in brief
    assert "Open conflicts: 1." in brief
    assert "Expectation checks: graph-sourced (prose fallback not used)." in brief


def test_t_sn4_pre_phase2_brief_is_byte_identical():
    brief = _brief(
        {
            "journeys": [{"name": "Buy"}],
            "counts": {"expected": 2, "reachable": 2, "expectations": 3},
        }
    )
    assert (
        "Expectations from the map: 3 (map expectations arrive in Phase 2)."
        in brief
    )
    assert "Open conflicts: not tracked yet (Phase 2)." in brief
