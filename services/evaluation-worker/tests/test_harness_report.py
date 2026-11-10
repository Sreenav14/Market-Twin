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
        {"item_id": "0", "name": "Save", "status": "worked", "journey_id": str(owned)},
        {"item_id": "1", "name": "Delete", "status": "broken", "journey_id": str(foreign),
         "reason": "observed_once"},
        {"item_id": "2", "name": "Next", "status": "blocked", "journey_id": "bad"},
    ]
    board = {"items": {str(i): item for i, item in enumerate(items)} if as_mapping else items}
    session = Mock(scalars=AsyncMock(return_value=Mock(all=Mock(return_value=[owned]))))
    reports = Mock(create_completed_report=AsyncMock(return_value=report_id))
    monkeypatch.setattr(harness_report, "EvaluationRepository", lambda _: Mock(
        list_board_item_results=AsyncMock(return_value={
            item["item_id"]: {"board_status": item["status"]} for item in items
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


async def test_empty_board_is_honest_and_missing_board_is_rejected(monkeypatch):
    reports = Mock(create_completed_report=AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(harness_report, "ReportRepository", lambda _: reports)
    monkeypatch.setattr(harness_report, "EvaluationRepository", lambda _: Mock(
        list_board_item_results=AsyncMock(return_value={}),
    ))
    session = Mock(scalars=AsyncMock(return_value=Mock(all=Mock(return_value=[]))))
    await harness_report.generate_harness_report(
        test_run_id=uuid4(), snapshot={"harness_state": {"items": []}}, session=session,
    )
    assert reports.create_completed_report.await_args.kwargs["report_payload"]["items"] == []
    payload = reports.create_completed_report.await_args.kwargs["report_payload"]
    assert payload["verdict"] == "Can't tell yet"
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
