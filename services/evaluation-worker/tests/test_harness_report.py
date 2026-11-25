from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from markettwin_evaluation_worker import harness_report, workflow
from markettwin_evaluation_worker.persistence.evaluation_repository import EvaluationRepository


@pytest.mark.parametrize("as_mapping", [True, False])
async def test_report_supports_both_boards_and_only_links_owned_journeys(monkeypatch, as_mapping):
    run_id, owned, foreign, report_id = uuid4(), uuid4(), uuid4(), uuid4()
    items = [
        {"item_id": "0", "name": "Save", "status": "worked", "journey_id": str(owned),
         "css_path": "#save", "occurrence_index": 0,
         "locator": {"role": "button", "tier": "confirmed", "skill_body_md": "execution input"},
         "durations_ms": [300], "mission_id": "unused"},
        {"item_id": "1", "name": "Delete", "status": "broken", "journey_id": str(foreign),
         "reason": "observed_once"},
        {"item_id": "2", "name": "Next", "status": "blocked", "journey_id": "bad"},
    ]
    board = {"items": {str(i): item for i, item in enumerate(items)} if as_mapping else items,
             "budget_counters": {"items_started": 1}}
    session = Mock(scalars=AsyncMock(side_effect=[
        Mock(all=Mock(return_value=[owned])),
        [{"decision": "continue", "reason": "Board advanced", "source": "lead"},
         {"decision": "stop", "reason": "Access blocked"}],
    ]))
    proof = {
        "safety_class": "read_only", "test_value_key": "query", "attempts": 1,
        "duration_ms": 300, "requirement_refs": ["R1"], "js_errors": [],
        "state_id": "home", "skill_replay": False, "expectation_id": "E1",
    }
    reports = Mock(create_completed_report=AsyncMock(return_value=report_id))
    monkeypatch.setattr(harness_report, "EvaluationRepository", lambda _: Mock(
        list_board_item_results=AsyncMock(return_value={
            item["item_id"]: {"board_status": item["status"], **proof} for item in items
        }),
    ))
    monkeypatch.setattr(harness_report, "ReportRepository", lambda _: reports)
    assert await harness_report.generate_harness_report(
        test_run_id=run_id, snapshot={"harness_state": board}, session=session,
    ) == report_id
    payload = reports.create_completed_report.await_args.kwargs["report_payload"]
    assert payload["mode"] == "harness_v1"
    assert [item["status"] for item in payload["items"]] == ["worked", "could_not_check", "blocked"]
    assert [item["journey_id"] for item in payload["items"]] == [str(owned), None, None]
    assert payload["items"][1]["reason"] == "missing_result_event"
    assert payload["verdict"] == "Can't tell yet"
    assert payload["board"]["coverage"]["checked"] == 1
    assert payload["items"][2]["reason"] is None
    worked, foreign_result, _ = payload["board"]["items"]
    assert {key: worked[key] for key in proof} == proof
    assert worked["css_path"] == "#save"
    assert worked["occurrence_index"] == 0
    assert worked["locator"] == {"role": "button", "tier": "confirmed"}
    assert "durations_ms" not in worked and "mission_id" not in worked
    assert "attempts" not in foreign_result
    assert payload["budget_counters"] == {"items_started": 1}
    assert payload["activity_checkpoints"] == [
        {"decision": "continue", "reason": "Board advanced"},
        {"decision": "stop", "reason": "Access blocked"},
    ]


async def test_empty_board_is_honest_and_missing_board_is_rejected(monkeypatch):
    reports = Mock(create_completed_report=AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(harness_report, "ReportRepository", lambda _: reports)
    monkeypatch.setattr(harness_report, "EvaluationRepository", lambda _: Mock(
        list_board_item_results=AsyncMock(return_value={}),
    ))
    session = Mock(scalars=AsyncMock(side_effect=[Mock(all=Mock(return_value=[])), []]))
    await harness_report.generate_harness_report(
        test_run_id=uuid4(), snapshot={"harness_state": {"items": []}}, session=session,
    )
    assert reports.create_completed_report.await_args.kwargs["report_payload"]["items"] == []
    payload = reports.create_completed_report.await_args.kwargs["report_payload"]
    assert payload["verdict"] == "Can't tell yet"
    assert "budget_counters" not in payload and "activity_checkpoints" not in payload
    # W1 (doc 19): the market_verdict key is present even when the honest
    # answer is cannot-tell — readers never infer from a missing key.
    assert payload["market_verdict"] == {
        "verdict": "insufficient_evidence", "coverage": 0.0, "confirmed_defects": 0,
    }
    with pytest.raises(ValueError, match="no recorded work board"):
        await harness_report.generate_harness_report(
            test_run_id=uuid4(), snapshot={}, session=session,
        )


@pytest.mark.parametrize("native", [False, True])
async def test_workflow_dispatches_harness_without_legacy_evaluation(monkeypatch, native):
    run_id, report_id = uuid4(), uuid4()
    snapshot = {"harness_state": {"items": []}}
    if not native:
        snapshot["execution_mode"] = "harness_v1"
    session = Mock(get=AsyncMock(return_value=SimpleNamespace(
        run_kind="explore_test" if native else None, configuration_snapshot=snapshot,
    )), commit=AsyncMock(), rollback=AsyncMock())
    repo = Mock(validate_run_ready=AsyncMock())
    monkeypatch.setattr(workflow, "EvaluationRepository", lambda _: repo)
    generate = AsyncMock(return_value=report_id)
    monkeypatch.setattr(harness_report, "generate_harness_report", generate)
    result = await workflow._evaluate_and_generate_report(test_run_id=run_id, session=session)
    assert result.report_id == report_id and result.finding_ids == ()
    generate.assert_awaited_once()
    session.commit.assert_awaited_once()


async def test_harness_report_failure_rolls_back_without_commit(monkeypatch):
    session = Mock(get=AsyncMock(return_value=SimpleNamespace(
        run_kind="explore_test", configuration_snapshot={},
    )), commit=AsyncMock(), rollback=AsyncMock())
    monkeypatch.setattr(workflow, "EvaluationRepository", lambda _: Mock(
        validate_run_ready=AsyncMock(),
    ))
    with pytest.raises(ValueError, match="no recorded work board"):
        await workflow._evaluate_and_generate_report(test_run_id=uuid4(), session=session)
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.parametrize("ids", [["same", "same"], [None], [""]])
async def test_report_rejects_ambiguous_board_item_identity(ids):
    session = Mock()
    with pytest.raises(ValueError, match="item identity"):
        await harness_report.generate_harness_report(
            test_run_id=uuid4(), session=session,
            snapshot={"harness_state": {"items": [
                {"item_id": item_id, "status": "worked"} for item_id in ids
            ]}},
        )


@pytest.mark.parametrize("kind", ["duplicate", "missing_identity", "foreign_journey", "foreign_execution", "unproved_broken"])
async def test_strict_board_results_reject_invalid_records(kind):
    run_id, journey_id, execution_id = uuid4(), uuid4(), uuid4()
    event = SimpleNamespace(payload={"board_item_id": "item", "board_status": "worked"},
                            journey_id=journey_id, execution_id=execution_id)
    if kind == "missing_identity":
        event.execution_id = None
    if kind == "unproved_broken":
        event.payload["board_status"] = "broken"
    rows = [event, event] if kind == "duplicate" else [event]
    async def get(model, identity):
        if identity == journey_id:
            return SimpleNamespace(test_run_id=uuid4() if kind == "foreign_journey" else run_id)
        return SimpleNamespace(journey_id=uuid4() if kind == "foreign_execution" else journey_id,
                               status="completed", outcome="failed")
    session = Mock(scalars=AsyncMock(return_value=Mock(all=Mock(return_value=rows))),
                   get=AsyncMock(side_effect=get))
    with pytest.raises(ValueError):
        await EvaluationRepository(session).list_board_item_results(test_run_id=run_id, strict=True)


async def test_harness_report_payload_contains_market_verdict(monkeypatch):
    """W1 (doc 19 section 6.2): a completed Board report's stored payload
    carries the projected market_verdict — the reader vocabulary, the Board
    coverage, and the reproduced-broken count — with no journey fields."""
    run_id, owned, report_id = uuid4(), uuid4(), uuid4()
    items = [
        {"item_id": "0", "name": "Search submits", "status": "worked",
         "journey_id": str(owned)},
        {"item_id": "1", "name": "Pay button submits", "status": "broken",
         "journey_id": str(owned)},
    ]
    session = Mock(scalars=AsyncMock(side_effect=[Mock(all=Mock(return_value=[owned])), []]))
    reports = Mock(create_completed_report=AsyncMock(return_value=report_id))
    monkeypatch.setattr(harness_report, "EvaluationRepository", lambda _: Mock(
        list_board_item_results=AsyncMock(return_value={
            "0": {"board_status": "worked"},
            "1": {"board_status": "broken"},
        }),
    ))
    monkeypatch.setattr(harness_report, "ReportRepository", lambda _: reports)

    await harness_report.generate_harness_report(
        test_run_id=run_id, snapshot={"harness_state": {"items": items}},
        session=session,
    )

    payload = reports.create_completed_report.await_args.kwargs["report_payload"]
    assert payload["verdict"] == "Not ready yet"
    assert payload["market_verdict"] == {
        "verdict": "not_ready", "coverage": 1.0, "confirmed_defects": 1,
    }
