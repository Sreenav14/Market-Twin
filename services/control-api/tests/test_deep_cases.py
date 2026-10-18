"""Case access inherits run ownership; private fixture data is never serialized."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from markettwin_control_api.api import deep_cases
from markettwin_execution_orchestrator.workflow.test_case_planner import (
    DeepFeaturePlanningRequest,
    fixture_case_candidates,
    fixture_feature_scope,
    select_feature_cases,
)
from markettwin_shared.deep_testing import CaseExecutionResult


class Context:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_):
        return False


@pytest.mark.parametrize("code", ["model_not_found", "private-provider-payload"])
async def test_failed_plan_exposes_only_reviewed_diagnostics(code):
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(status="failed")),
        scalar=AsyncMock(side_effect=[None, SimpleNamespace(payload={
            "code": code, "message": "SECRET_CANARY_DO_NOT_EXPOSE",
        })]),
    )
    response = await deep_cases.case_view(session, uuid4())
    assert response["available"] is False
    assert response["cases"] == []
    assert "SECRET_CANARY" not in str(response)
    assert "private-provider-payload" not in str(response)
    assert response["failure"]["code"] == (
        "model_not_found" if code == "model_not_found" else "execution_failed"
    )


async def test_failed_plan_appends_only_a_reviewed_validation_reason():
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(status="failed")),
        scalar=AsyncMock(side_effect=[None, SimpleNamespace(payload={
            "code": "invalid_plan",
            "reason": "Feature planner returned no schema-valid cases. "
            "(1:expected.0.target:value_error)",
            "message": "SECRET_CANARY",
        })]),
    )
    response = await deep_cases.case_view(session, uuid4())
    assert "expected.0.target:value_error" in response["failure"]["message"]
    assert "SECRET_CANARY" not in str(response)


async def test_historical_failed_plan_has_truthful_missing_error_fallback():
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(status="failed")),
        scalar=AsyncMock(side_effect=[None, None]),
    )
    response = await deep_cases.case_view(session, uuid4())
    assert "original error was not retained" in response["failure"]["message"]


@pytest.mark.parametrize("accessible", [False, True])
async def test_case_reads_authorize_before_reading_events(monkeypatch, accessible):
    run_id, user_id = uuid4(), uuid4()
    authenticate = AsyncMock(return_value=user_id)
    get_run = AsyncMock(return_value=object() if accessible else None)
    view = AsyncMock(return_value={"cases": [{"case_id": "owned"}], "available": True})
    monkeypatch.setattr(deep_cases, "get_authenticated_user_id", authenticate)
    monkeypatch.setattr(deep_cases, "get_database_runtime", lambda _: SimpleNamespace(session_factory=Context))
    monkeypatch.setattr(deep_cases, "TestRunRepository", lambda _: SimpleNamespace(get_for_user=get_run))
    monkeypatch.setattr(deep_cases, "case_view", view)
    if accessible:
        assert (await deep_cases.get_case(run_id, "owned", SimpleNamespace()))["case_id"] == "owned"
        with pytest.raises(HTTPException) as error:
            await deep_cases.get_case(run_id, "foreign", SimpleNamespace())
        assert error.value.status_code == 404
    else:
        with pytest.raises(HTTPException) as error:
            await deep_cases.get_cases(run_id, SimpleNamespace())
        assert error.value.status_code == 404
        view.assert_not_awaited()
    get_run.assert_awaited_with(test_run_id=run_id, user_id=user_id)


async def test_partial_plan_omits_private_scope_data_and_never_claims_pass() -> None:
    scope = fixture_feature_scope("http://127.0.0.1:5191/index.html?variant=good")
    plan = select_feature_cases(
        request=DeepFeaturePlanningRequest(test_run_id=uuid4(), scope=scope, allow_fixture_truth=True),
        candidates=fixture_case_candidates(scope),
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[SimpleNamespace(payload=plan.model_dump(mode="json")), None]),
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
    )
    response = await deep_cases.case_view(session, uuid4())
    assert response["evaluation_pending"] is True
    assert len(response["cases"]) == 8
    assert all(item["verdict"] == "not_run" for item in response["cases"])
    assert "safe_test_data" not in str(response)
    assert "fixture@example.test" not in str(response)
    assert "starting_url" not in str(response)
    assert "private_prompt" not in str(response)


def test_case_pages_are_bounded() -> None:
    cases = [{"case_id": f"case_{index}"} for index in range(5)]
    page = deep_cases.page_cases({"cases": cases}, 2, 2)
    assert [item["case_id"] for item in page["cases"]] == ["case_2", "case_3"]
    assert page["next_cursor"] == 4
    with pytest.raises(HTTPException) as error:
        deep_cases.page_cases({"cases": cases}, 0, 21)
    assert error.value.status_code == 422


async def test_recorded_result_is_visible_but_not_confirmed() -> None:
    scope = fixture_feature_scope("http://127.0.0.1:5191/index.html?variant=good")
    plan = select_feature_cases(
        request=DeepFeaturePlanningRequest(
            test_run_id=uuid4(), scope=scope, allow_fixture_truth=True
        ),
        candidates=fixture_case_candidates(scope),
    )
    case = plan.cases[0]
    journey_id = uuid4()
    recorded = CaseExecutionResult(
        case_id=case.case_id,
        execution_id=uuid4(),
        execution_status="policy_blocked",
        verdict="unverified",
        action_step_ids=(11,),
        elapsed_ms=5,
        blocker="policy_blocked",
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[SimpleNamespace(payload=plan.model_dump(mode="json")), None]),
        execute=AsyncMock(side_effect=[
            SimpleNamespace(all=lambda: []),
            SimpleNamespace(all=lambda: [(recorded.model_dump(mode="json"), journey_id)]),
            SimpleNamespace(all=lambda: [(11, "policy_blocked")]),
        ]),
    )
    response = await deep_cases.case_view(session, uuid4())
    shown = next(item for item in response["cases"] if item["case_id"] == case.case_id)
    assert response["evaluation_pending"] is True
    assert shown["verdict"] == "awaiting_verification"
    assert shown["recorded_verdict"] == "unverified"
    assert shown["journey_id"] == str(journey_id)
    assert shown["steps"] == [{"step_id": 11, "action": "navigate", "result": "policy_blocked"}]


async def test_case_steps_reject_invalid_pages(monkeypatch) -> None:
    view = AsyncMock(
        return_value={
            "cases": [{"case_id": "owned", "steps": [{"step_id": 1}, {"step_id": 2}]}]
        }
    )
    monkeypatch.setattr(deep_cases, "authorized_cases", view)
    page = await deep_cases.get_case_steps(uuid4(), "owned", SimpleNamespace(), cursor=1, limit=1)
    assert page == {"steps": [{"step_id": 2}], "next_cursor": None}
    with pytest.raises(HTTPException) as error:
        await deep_cases.get_case_steps(uuid4(), "owned", SimpleNamespace(), cursor=-1, limit=1)
    assert error.value.status_code == 422


async def test_legacy_run_has_explicit_unavailable_cases() -> None:
    response = await deep_cases.case_view(SimpleNamespace(
        scalar=AsyncMock(return_value=None), get=AsyncMock(return_value=SimpleNamespace(status="completed")),
    ), uuid4())
    assert response["available"] is False
    assert response["cases"] == []


async def test_skipped_human_assistance_is_not_run_before_evaluation() -> None:
    scope = fixture_feature_scope("http://127.0.0.1:5191/index.html?variant=good")
    plan = select_feature_cases(
        request=DeepFeaturePlanningRequest(
            test_run_id=uuid4(), scope=scope, allow_fixture_truth=True,
        ), candidates=fixture_case_candidates(scope),
    )
    recorded = CaseExecutionResult(
        case_id=plan.cases[0].case_id, execution_id=uuid4(), execution_status="skipped",
        verdict="unverified", blocker="human_assistance_skipped", elapsed_ms=10,
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[SimpleNamespace(payload=plan.model_dump(mode="json")), None]),
        execute=AsyncMock(side_effect=[
            SimpleNamespace(all=lambda: []),
            SimpleNamespace(all=lambda: [(recorded.model_dump(mode="json"), uuid4())]),
        ]),
    )
    response = await deep_cases.case_view(session, uuid4())
    shown = response["cases"][0]
    assert shown["verdict"] == "not_run"
    assert shown["execution_status"] == "skipped"
    assert shown["reason"] == "human_assistance_skipped"
    assert shown["assertions"] == []
