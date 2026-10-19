"""A case verdict alone never establishes source-grounded product evidence."""

import json
from uuid import uuid4

import pytest
from markettwin_database.models import Artifact, ExecutionStep
from markettwin_evaluation_worker.deep_evaluator import grounded_failure, valid_case_evidence
from markettwin_shared.deep_testing import AssertionResult, CaseExecutionResult
from markettwin_shared.feature_plan import (
    CaseAction,
    DeepFeaturePlan,
    ExpectedAssertion,
    FeatureScope,
    PlanBudget,
    Requirement,
    SemanticTarget,
)
from markettwin_shared.feature_plan import (
    TestCaseSpec as CaseSpec,
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
        case_id=case.case_id,
        assertion_id="error",
        oracle="visible_text",
        expected_value="Email required",
        observed_value="absent",
        status="not_satisfied",
        execution_id=execution_id,
        step_id=3,
        artifact_ids=(artifact_id,),
        origin="fixture_truth",
        requirement_refs=("email",),
        elapsed_ms=1500,
    )
    result = CaseExecutionResult(
        case_id=case.case_id,
        execution_id=execution_id,
        execution_status="completed",
        verdict="not_satisfied",
        action_step_ids=(1, 2),
        assertion_results=(observed,),
        elapsed_ms=2000,
    )
    steps = {
        1: ExecutionStep(
            id=1,
            execution_id=execution_id,
            step_number=1,
            action_type="navigate",
            status="completed",
        ),
        2: ExecutionStep(
            id=2, execution_id=execution_id, step_number=2, action_type="click", status="completed"
        ),
        3: ExecutionStep(
            id=3,
            execution_id=execution_id,
            step_number=3,
            action_type="assertion",
            status="completed",
            observation_summary=json.dumps(observed.model_dump(mode="json")),
        ),
    }
    artifacts = {
        artifact_id: Artifact(
            id=artifact_id,
            execution_id=execution_id,
            step_id=3,
            artifact_type="screenshot",
            metadata_json={"kind": "viewport"},
        )
    }
    return (
        case,
        result,
        steps,
        artifacts,
        DeepFeaturePlan(scope=scope, budget=PlanBudget(), cases=(case,)),
    )


def test_exact_observation_actions_and_source_support_case() -> None:
    case, result, steps, artifacts, plan = recorded_case()
    assert valid_case_evidence(case, result, steps, artifacts)
    assert grounded_failure(case, plan, plan.scope)
    assert not grounded_failure(case, plan, None)
    inferred_assertion = case.expected[0].model_copy(
        update={"origin": "inferred", "requirement_refs": ()}
    )
    inferred = case.model_copy(update={"expected": (inferred_assertion,)})
    inferred_plan = plan.model_copy(update={"cases": (inferred,)})
    assert not grounded_failure(inferred, inferred_plan, plan.scope)


@pytest.mark.parametrize("oracle", ["url_path_v1", "visible_text"])
def test_new_oracle_semantics_preserve_exact_frozen_expectations(oracle: str) -> None:
    case, result, steps, artifacts, plan = recorded_case()
    expected = ExpectedAssertion(
        assertion_id="error", oracle=oracle,  # type: ignore[arg-type]
        target=None if oracle == "url_path_v1" else case.expected[0].target,
        expected_value="http://127.0.0.1:5191/guide" if oracle == "url_path_v1" else "One  two",
        origin="fixture_truth", requirement_refs=("email",),
    )
    case = case.model_copy(update={"expected": (expected,)})
    scope = plan.scope.model_copy(update={"requirements": (
        plan.scope.requirements[0].model_copy(update={"assertions": (expected,)}),
    )})
    plan = plan.model_copy(update={"scope": scope, "cases": (case,)})
    payload = result.assertion_results[0].model_dump()
    payload.update(
        oracle=oracle, expected_value=expected.expected_value, status="satisfied",
        observed_value=expected.expected_value if oracle == "url_path_v1" else "One\ntwo",
    )
    observed = AssertionResult.model_validate(payload)
    result = result.model_copy(update={"verdict": "satisfied", "assertion_results": (observed,)})
    steps[3].observation_summary = observed.model_dump_json()
    assert valid_case_evidence(case, result, steps, artifacts)
    assert grounded_failure(case, plan, scope)
    # Normalized equality is not permission to rewrite the frozen expectation.
    altered = observed.model_copy(update={"expected_value": "One two"})
    assert not valid_case_evidence(
        case, result.model_copy(update={"assertion_results": (altered,)}), steps, artifacts,
    )


@pytest.mark.parametrize("recorded_action,valid", [
    ("registration_submit", True), ("click", False), ("get_state", False),
])
def test_fixture_approval_step_must_match_the_frozen_action_identity(
    recorded_action: str, valid: bool,
) -> None:
    case, result, steps, artifacts, _ = recorded_case()
    approved_action = CaseAction(
        action="click", action_id="registration_submit",
        target=SemanticTarget(
            role="button", name="Save", scope_role="form", scope_name="Registration",
        ),
    )
    case = case.model_copy(update={"steps": (approved_action,)})
    steps[2].action_type = recorded_action
    assert valid_case_evidence(case, result, steps, artifacts) is valid


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


def test_unsupported_inspection_cannot_become_a_product_failure() -> None:
    _, result, _, _, _ = recorded_case()
    payload = result.assertion_results[0].model_dump()
    payload["reason"] = "unsupported_safe_url_read"
    with pytest.raises(ValidationError, match="cannot establish a verdict"):
        AssertionResult.model_validate(payload)


@pytest.mark.parametrize("overrides", [
    {"verdict": "satisfied"}, {"blocker": None}, {"execution_status": "failed"},
])
def test_skipped_human_assistance_cannot_fabricate_an_assertion_verdict(overrides) -> None:
    payload = dict(case_id="login", execution_id=uuid4(), execution_status="skipped",
                   verdict="unverified", blocker="human_assistance_skipped", elapsed_ms=100)
    assert CaseExecutionResult.model_validate(payload).assertion_results == ()
    with pytest.raises(ValidationError):
        CaseExecutionResult.model_validate({**payload, **overrides})


async def test_skipped_case_evaluation_persists_not_run_without_findings(monkeypatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from markettwin_evaluation_worker import deep_evaluator

    case, result, _steps, _artifacts, plan = recorded_case()
    skipped = CaseExecutionResult(
        case_id=case.case_id, execution_id=result.execution_id, execution_status="skipped",
        verdict="unverified", blocker="human_assistance_skipped", elapsed_ms=100,
    )
    journey_id = uuid4()
    events = [
        SimpleNamespace(event_type="test_plan.created", payload=plan.model_dump(mode="json")),
        SimpleNamespace(event_type="test_case.completed", payload=skipped.model_dump(mode="json"),
                        execution_id=result.execution_id, journey_id=journey_id),
    ]
    batches = [events, [SimpleNamespace(id=journey_id, ordinal=1)],
               [SimpleNamespace(id=result.execution_id, journey_id=journey_id)], [], []]
    session = SimpleNamespace(scalars=AsyncMock(side_effect=[
        SimpleNamespace(all=lambda items=items: items) for items in batches
    ]))
    create_report = AsyncMock(return_value=uuid4())
    create_finding = AsyncMock()
    monkeypatch.setattr(deep_evaluator, "ReportRepository", lambda _: SimpleNamespace(
        create_completed_report=create_report,
    ))
    monkeypatch.setattr(deep_evaluator, "EvaluationRepository", lambda _: SimpleNamespace(
        create_linked_finding=create_finding,
    ))
    finding_ids, _report_id = await deep_evaluator.evaluate_deep_run(
        test_run_id=uuid4(), session=session, trusted_scope=plan.scope,
    )
    assert finding_ids == ()
    create_finding.assert_not_awaited()
    payload = create_report.await_args.kwargs["report_payload"]
    assert payload["coverage"]["executed"] == 0
    assert payload["coverage"]["not_run"] == 1
    assert payload["coverage"]["human_assistance_skipped"] == 1
    assert payload["coverage"]["failed_assertions"] == 0
    assert payload["coverage"]["inconclusive"] == 0
    assert payload["cases"][0]["reason"] == "human_assistance_skipped"
    assert payload["cases"][0]["verdict"] == "not_run"
