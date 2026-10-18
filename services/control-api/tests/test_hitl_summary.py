"""Authentication cannot inflate protected feature test coverage."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from markettwin_control_api.api import hitl_summary
from markettwin_execution_orchestrator.workflow.test_case_planner import (
    DeepFeaturePlanningRequest, fixture_case_candidates, fixture_feature_scope, select_feature_cases,
)


def test_login_only_has_no_passed_or_executed_feature_cases() -> None:
    scope = fixture_feature_scope("http://127.0.0.1:5191/index.html")
    plan = select_feature_cases(
        request=DeepFeaturePlanningRequest(test_run_id=uuid4(), scope=scope, allow_fixture_truth=True),
        candidates=fixture_case_candidates(scope),
    )
    response = hitl_summary.summarize_authenticated_coverage([
        ("test_plan.created", plan.model_dump(mode="json")),
        ("test_case.authenticated", {
            "case_id": plan.cases[0].case_id, "role": "member", "auth_source": "reused_session",
        }),
    ])
    assert response["full_application_coverage"] is False
    assert response["reused_auth_cases"] == 1
    row = response["role_coverage"][0]
    assert row["authenticated"] == 1
    assert row["executed"] == row["passed"] == 0
    assert row["not_run"] == len(plan.cases)
    assert "fixture@example.test" not in str(response)
    assert "safe_test_data" not in str(response)


async def test_summary_rejects_foreign_run_before_reading_events(monkeypatch) -> None:
    session = SimpleNamespace(execute=AsyncMock())

    class Context:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr(hitl_summary, "get_authenticated_user_id", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(hitl_summary, "get_database_runtime", lambda _: SimpleNamespace(session_factory=Context))
    monkeypatch.setattr(hitl_summary, "TestRunRepository", lambda _: SimpleNamespace(get_for_user=AsyncMock(return_value=None)))
    with pytest.raises(HTTPException) as error:
        await hitl_summary.get_hitl_summary(uuid4(), SimpleNamespace())
    assert error.value.status_code == 404
    session.execute.assert_not_awaited()


def test_skipped_assistance_counts_as_not_tested_not_inconclusive() -> None:
    from markettwin_shared.deep_testing import CaseExecutionResult

    scope = fixture_feature_scope("http://127.0.0.1:5191/index.html")
    plan = select_feature_cases(
        request=DeepFeaturePlanningRequest(test_run_id=uuid4(), scope=scope, allow_fixture_truth=True),
        candidates=fixture_case_candidates(scope),
    )
    skipped = CaseExecutionResult(
        case_id=plan.cases[0].case_id, execution_id=uuid4(), execution_status="skipped",
        verdict="unverified", blocker="human_assistance_skipped", elapsed_ms=10,
    )
    response = hitl_summary.summarize_authenticated_coverage([
        ("test_plan.created", plan.model_dump(mode="json")),
        ("test_case.authenticated", {"case_id": skipped.case_id, "role": "member"}),
        ("test_case.completed", skipped.model_dump(mode="json")),
    ])
    row = response["role_coverage"][0]
    assert row["executed"] == row["passed"] == row["inconclusive"] == row["blocked"] == 0
    assert row["not_run"] == len(plan.cases)
    assert response["inventory"][0]["not_explored"] == len(plan.cases) + len(plan.skipped)
