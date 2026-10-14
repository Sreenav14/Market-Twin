"""A case verdict alone never establishes source-grounded product evidence."""

import json
from uuid import uuid4

import pytest
from markettwin_database.models import Artifact, ExecutionStep
from markettwin_evaluation_worker.deep_evaluator import grounded_failure, valid_case_evidence
from markettwin_shared.deep_testing import AssertionResult, CaseExecutionResult
from markettwin_shared.feature_plan import (
    CaseAction, DeepFeaturePlan, ExpectedAssertion, FeatureScope, PlanBudget, Requirement,
    SemanticTarget, TestCaseSpec as CaseSpec,
)
from pydantic import ValidationError


def recorded_case():
    target = SemanticTarget(role="alert", name="Validation")
    expected = ExpectedAssertion(
        assertion_id="error", oracle="visible_text", target=target, expected_value="Email required",
        origin="fixture_truth", requirement_refs=("email",),
    )
    scope = FeatureScope(
        feature_key="form", goal="Check validation", starting_url="http://127.0.0.1:5191/",
        allowed_origins=("http://127.0.0.1:5191",), requirements=(Requirement(
            requirement_id="email", source="fixture", source_id="deep-fixture-v1",
            text="Empty email shows Email required", assertions=(expected,),
        ),),
    )
    case = CaseSpec(
        case_id="empty_email", feature_key="form", title="Empty email validation", kind="negative",
        requirement_refs=("email",), steps=(CaseAction(action="click", target=SemanticTarget(
            role="button", name="Check",
        )),), expected=(expected,),
    )
    execution_id, artifact_id = uuid4(), uuid4()
    observed = AssertionResult(
        case_id=case.case_id, assertion_id="error", oracle="visible_text",
        expected_value="Email required", observed_value="absent", status="not_satisfied",
        execution_id=execution_id, step_id=3, artifact_ids=(artifact_id,),
        origin="fixture_truth", requirement_refs=("email",), elapsed_ms=1500,
    )
    result = CaseExecutionResult(
        case_id=case.case_id, execution_id=execution_id, execution_status="completed",
        verdict="not_satisfied", action_step_ids=(1, 2), assertion_results=(observed,), elapsed_ms=2000,
    )
    steps = {
        1: ExecutionStep(id=1, execution_id=execution_id, step_number=1,
                         action_type="navigate", status="completed"),
        2: ExecutionStep(id=2, execution_id=execution_id, step_number=2,
                         action_type="click", status="completed"),
        3: ExecutionStep(id=3, execution_id=execution_id, step_number=3,
                         action_type="assertion", status="completed",
                         observation_summary=json.dumps(observed.model_dump(mode="json"))),
    }
    artifacts = {artifact_id: Artifact(id=artifact_id, execution_id=execution_id, step_id=3,
                                      artifact_type="screenshot", metadata_json={"kind": "viewport"})}
    return case, result, steps, artifacts, DeepFeaturePlan(scope=scope, budget=PlanBudget(), cases=(case,))


def test_exact_observation_actions_and_source_support_case() -> None:
    case, result, steps, artifacts, plan = recorded_case()
    assert valid_case_evidence(case, result, steps, artifacts)
    assert grounded_failure(case, plan, plan.scope)
    assert not grounded_failure(case, plan, None)


@pytest.mark.parametrize("fault", ["artifact_step", "artifact_owner", "step_owner", "observed",
                                    "action_failed", "action_type", "missing_assertion"])
def test_wrong_or_missing_proof_never_verifies(fault: str) -> None:
    case, result, steps, artifacts, _ = recorded_case()
    artifact = next(iter(artifacts.values()))
    if fault == "artifact_step":
        artifact.step_id = 2
    elif fault == "artifact_owner":
        artifact.execution_id = uuid4()
    elif fault == "step_owner":
        steps[3].execution_id = uuid4()
    elif fault == "observed":
        steps[3].observation_summary = "{}"
    elif fault == "action_failed":
        steps[2].status = "failed"
    elif fault == "action_type":
        steps[2].action_type = "get_state"
    else:
        result = result.model_copy(update={"assertion_results": ()})
    assert not valid_case_evidence(case, result, steps, artifacts)


def test_boolean_integer_coercion_and_foreign_provenance_are_rejected() -> None:
    case, result, _, _, _ = recorded_case()
    payload = result.assertion_results[0].model_dump(mode="json")
    payload.update(oracle="visible", expected_value=True, observed_value=1, status="satisfied")
    with pytest.raises(ValidationError):
        AssertionResult.model_validate(payload)
    payload = result.model_dump(mode="json")
    payload["assertion_results"][0]["case_id"] = case.case_id + "_foreign"
    with pytest.raises(ValidationError):
        CaseExecutionResult.model_validate(payload)
