"""Deep-mode collection accounts for unstarted and uncertain cases honestly."""

from uuid import uuid4

import pytest
from markettwin_database.models.testing import TestRun
from markettwin_execution_orchestrator.workflow.deep_run import (
    authorized_scope_snapshot,
    case_journey,
    coverage_summary,
    knowledge_requirements,
    skip_reason,
)
from markettwin_execution_orchestrator.workflow.run_request import build_run_request
from markettwin_execution_orchestrator.workflow.test_case_planner import (
    DeepFeaturePlanningRequest,
    fixture_case_candidates,
    fixture_feature_scope,
    select_feature_cases,
)
from markettwin_shared.auth_verification import AuthVerificationPolicy
from markettwin_shared.deep_testing import AssertionResult, CaseExecutionResult


def test_approved_scope_keeps_late_content_skills_and_evidence() -> None:
    content = "This source establishes the workflow. " * 45 + "Final observable outcome."
    requirements, omitted = knowledge_requirements(({
        "id": "source-1",
        "application_knowledge": [{"content": content, "evidence_ordinals": [7]}],
        "skills": [{
            "name": "Checkout", "evidence_ordinals": [9],
            "definition": {"expected_outcomes": ["Order confirmation is visible"]},
        }],
    },))
    assert omitted == 0
    assert any("Final observable outcome." in item.text for item in requirements)
    assert any("Order confirmation is visible" in item.text for item in requirements)
    assert all(item.source_id == "source-1" for item in requirements)
    assert all(len(item.text) <= 1000 for item in requirements)
    assert all("evidence_ordinals=" in item.text for item in requirements)


def test_approved_scope_reports_budget_omissions() -> None:
    requirements, omitted = knowledge_requirements(({
        "id": "source-1",
        "application_knowledge": [
            {"content": f"Requirement {index}", "evidence_ordinals": [index + 1]}
            for index in range(40)
        ],
    },))
    assert len(requirements) == 32
    assert omitted == 8
    assert len({item.requirement_id for item in requirements}) == 32


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


def test_authorized_scope_is_frozen_without_replacement() -> None:
    scope = fixture_feature_scope("http://127.0.0.1:5191/index.html?variant=good")
    snapshot: dict[str, object] = {"study_brief": "Test the form."}
    frozen = authorized_scope_snapshot(snapshot, scope)
    assert frozen["study_brief"] == "Test the form."
    assert authorized_scope_snapshot(frozen, scope) == frozen
    changed = scope.model_copy(update={"goal": "Different goal"})
    with pytest.raises(ValueError, match="authorized snapshot"):
        authorized_scope_snapshot(frozen, changed)


def test_failed_assertion_metric_counts_checks_not_cases() -> None:
    scope = fixture_feature_scope("http://127.0.0.1:5191/index.html?variant=good")
    plan = select_feature_cases(
        request=DeepFeaturePlanningRequest(
            test_run_id=uuid4(), scope=scope, allow_fixture_truth=True
        ),
        candidates=fixture_case_candidates(scope),
    )
    execution_id = uuid4()
    assertions = tuple(
        AssertionResult(
            case_id=plan.cases[0].case_id,
            assertion_id=name,
            oracle="visible_text",
            expected_value="Expected",
            observed_value="absent",
            status="not_satisfied",
            execution_id=execution_id,
            step_id=step_id,
            artifact_ids=(uuid4(),),
            origin="inferred",
            elapsed_ms=1,
        )
        for name, step_id in (("first_check", 3), ("second_check", 4))
    )
    result = CaseExecutionResult(
        case_id=plan.cases[0].case_id,
        execution_id=execution_id,
        execution_status="completed",
        verdict="not_satisfied",
        action_step_ids=(1,),
        assertion_results=assertions,
        elapsed_ms=5,
    )
    assert coverage_summary(plan, (result,))["failed_assertions"] == 2


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


def test_fixture_authority_requires_dedicated_persisted_flag_and_loopback_target() -> None:
    run = TestRun(
        id=uuid4(),
        created_by_user_id=uuid4(),
        synthetic_fixture_approval_enabled=True,
        target_snapshot={
            "environment": "test",
            "base_url": "http://127.0.0.1:5191/index.html",
            "allowed_origins": [
                {
                    "scheme": "http",
                    "hostname": "127.0.0.1",
                    "port": 5191,
                    "include_subdomains": False,
                },
            ],
        },
        configuration_snapshot={
            "execution_mode": "deep_feature_v1",
            "study_brief": "Test synthetic registration.",
            "fixture_truth": False,
        },
    )
    request = build_run_request(run)
    assert request.fixture_truth is True
    assert request.network_policy == "local_development"
    assert request.synthetic_fixture_approval_enabled is True
    assert request.created_by_user_id == run.created_by_user_id
    run.target_snapshot = {
        **run.target_snapshot,
        "allowed_origins": [
            {"scheme": "https", "hostname": "app.example.test", "port": None,
             "include_subdomains": False},
        ],
    }
    with pytest.raises(ValueError, match="all-loopback"):
        build_run_request(run)


def test_build_run_request_restores_frozen_auth_verification_policy() -> None:
    policy = AuthVerificationPolicy(
        origin="https://example.invalid",
        marker_selector="[data-testid='signed-in-role']",
        expected_marker="member",
        role="member",
        account_reference="fixture-member-1",
    )
    run = TestRun(
        id=uuid4(),
        target_snapshot={
            "base_url": "https://example.invalid/",
            "allowed_origins": [
                {
                    "scheme": "https",
                    "hostname": "example.invalid",
                    "port": None,
                    "include_subdomains": False,
                },
            ],
        },
        configuration_snapshot={
            "study_brief": "Test authenticated account behavior.",
            "auth_verification": policy.model_dump(mode="json"),
        },
    )
    assert build_run_request(run).auth_verification == policy


def test_build_run_request_rejects_auth_policy_outside_frozen_allowlist() -> None:
    policy = AuthVerificationPolicy(
        origin="https://elsewhere.invalid",
        marker_selector="[data-testid='signed-in-role']",
        expected_marker="member",
        role="member",
        account_reference="fixture-member-1",
    )
    run = TestRun(
        id=uuid4(),
        target_snapshot={
            "base_url": "https://example.invalid/",
            "allowed_origins": [
                {
                    "scheme": "https",
                    "hostname": "example.invalid",
                    "port": None,
                    "include_subdomains": False,
                },
            ],
        },
        configuration_snapshot={
            "study_brief": "Test authenticated account behavior.",
            "auth_verification": policy.model_dump(mode="json"),
        },
    )
    with pytest.raises(ValueError, match="outside the authorized target"):
        build_run_request(run)


@pytest.mark.parametrize(
    "updates",
    [
        {"origin": "https://example.invalid/path"},
        {"origin": "https://user@example.invalid"},
        {"account_reference": "production-password-value"},
        {"unapproved_runtime_selector": "body"},
    ],
)
def test_auth_verification_policy_rejects_unsafe_or_unknown_values(
    updates: dict[str, str],
) -> None:
    values = {
        "origin": "https://example.invalid",
        "marker_selector": "[data-testid='signed-in-role']",
        "expected_marker": "member",
        "role": "member",
        "account_reference": "fixture-member-1",
    }
    with pytest.raises(ValueError):
        AuthVerificationPolicy.model_validate({**values, **updates})


def test_auth_verification_policy_repr_redacts_exact_marker_and_account_reference() -> None:
    policy = AuthVerificationPolicy(
        origin="https://example.invalid",
        marker_selector="[data-testid='signed-in-role']",
        expected_marker="internal-marker-value",
        role="member",
        account_reference="fixture-member-1",
    )
    assert "internal-marker-value" not in repr(policy)
    assert "fixture-member-1" not in repr(policy)
