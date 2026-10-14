"""Deep-mode collection accounts for unstarted and uncertain cases honestly."""

from uuid import uuid4

import pytest
from markettwin_database.models.testing import TestRun
from markettwin_execution_orchestrator.workflow.deep_run import (
    case_journey,
    coverage_summary,
    skip_reason,
)
from markettwin_execution_orchestrator.workflow.run_request import build_run_request
from markettwin_execution_orchestrator.workflow.test_case_planner import (
    DeepFeaturePlanningRequest,
    fixture_case_candidates,
    fixture_feature_scope,
    select_feature_cases,
)
from markettwin_shared.deep_testing import CaseExecutionResult


def test_case_bridge_keys_and_assertion_criteria_are_distinct() -> None:
    scope = fixture_feature_scope("http://127.0.0.1:5191/index.html?variant=good")
    case = fixture_case_candidates(scope).cases[0]
    journey = case_journey(case)
    assert journey.journey_key == f"feature_tester_v1__{case.case_id}"
    assert journey.mission.mission_id == case.case_id
    assert len(set(journey.mission.success_criteria)) == len(case.expected)


def test_missing_case_results_remain_not_run_and_blocks_do_not_become_failures() -> None:
    scope = fixture_feature_scope("http://127.0.0.1:5191/index.html?variant=good")
    plan = select_feature_cases(
        request=DeepFeaturePlanningRequest(
            test_run_id=uuid4(), scope=scope, allow_fixture_truth=True
        ),
        candidates=fixture_case_candidates(scope),
    )
    result = CaseExecutionResult(
        case_id=plan.cases[0].case_id,
        execution_id=uuid4(),
        execution_status="policy_blocked",
        verdict="unverified",
        action_step_ids=(1,),
        elapsed_ms=10,
        blocker="policy_blocked",
    )
    coverage = coverage_summary(plan, (result,))
    assert coverage["planned"] == len(plan.cases)
    assert coverage["executed"] == 1
    assert coverage["covered"] == 0
    assert coverage["blocked"] == 1
    assert coverage["failed_assertions"] == 0
    assert coverage["inconclusive"] == 0
    assert coverage["not_run"] == len(plan.cases) - 1
    with pytest.raises(ValueError, match="duplicate or foreign"):
        coverage_summary(plan, (result, result))


def test_case_budget_stops_before_starting_another_case() -> None:
    scope = fixture_feature_scope("http://127.0.0.1:5191/index.html?variant=good")
    case = fixture_case_candidates(scope).cases[0]
    required = len(case.steps) + len(case.expected) + 1
    assert skip_reason(remaining_seconds=0.2, remaining_steps=required, case=case) == "time_budget"
    assert (
        skip_reason(remaining_seconds=30, remaining_steps=required - 1, case=case)
        == "step_budget"
    )
    assert skip_reason(remaining_seconds=30, remaining_steps=required, case=case) is None


def test_run_mode_is_opt_in_and_fixture_authority_not_loaded_from_configuration() -> None:
    run = TestRun(
        id=uuid4(),
        target_snapshot={
            "base_url": "https://example.test/",
            "allowed_origins": [
                {
                    "scheme": "https",
                    "hostname": "example.test",
                    "port": None,
                    "include_subdomains": False,
                },
            ],
        },
        configuration_snapshot={"study_brief": "Test the form.", "fixture_truth": True},
    )
    assert build_run_request(run).execution_mode == "legacy_persona"
    run.configuration_snapshot = {**run.configuration_snapshot, "execution_mode": "deep_feature_v1"}
    request = build_run_request(run)
    assert request.execution_mode == "deep_feature_v1"
    assert request.fixture_truth is False
    run.configuration_snapshot = {**run.configuration_snapshot, "execution_mode": "unknown"}
    with pytest.raises(ValueError, match="Unsupported execution mode"):
        build_run_request(run)
