"""A case verdict alone never establishes source-grounded product evidence."""

import json
from uuid import uuid4

import pytest
from markettwin_database.models import Artifact, ExecutionStep
from markettwin_evaluation_worker.deep_evaluator import grounded_failure, valid_case_evidence
from markettwin_shared.deep_testing import AssertionResult, CaseExecutionResult
from markettwin_shared.discovery_contract import (
    ContractAssertion,
    FrozenJourneyContract,
    TestContract,
)
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
        assertion_id="error",
        oracle="visible_text",
        target=target,
        expected_value="Email required",
        origin="fixture_truth",
        requirement_refs=("email",),
    )
    scope = FeatureScope(
        feature_key="form",
        goal="Check validation",
        starting_url="http://127.0.0.1:5191/",
        allowed_origins=("http://127.0.0.1:5191",),
        requirements=(
            Requirement(
                requirement_id="email",
                source="fixture",
                source_id="deep-fixture-v1",
                text="Empty email shows Email required",
                assertions=(expected,),
            ),
        ),
    )
    case = CaseSpec(
        case_id="empty_email",
        feature_key="form",
        title="Empty email validation",
        kind="negative",
        requirement_refs=("email",),
        steps=(
            CaseAction(
                action="click",
                target=SemanticTarget(
                    role="button",
                    name="Check",
                ),
            ),
        ),
        expected=(expected,),
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


def recorded_precondition_failure():
    case, _, _, _, _ = recorded_case()
    expected = ExpectedAssertion(
        assertion_id="primary_enabled",
        oracle="enabled",
        target=case.steps[0].target,
        expected_value=True,
        after_step_ordinal=0,
        origin="user_approved",
    )
    case = case.model_copy(update={"expected": (expected,)})
    execution_id, artifact_id = uuid4(), uuid4()
    observed = AssertionResult(
        case_id=case.case_id,
        assertion_id=expected.assertion_id,
        oracle="enabled",
        expected_value=True,
        observed_value=False,
        status="not_satisfied",
        execution_id=execution_id,
        step_id=2,
        artifact_ids=(artifact_id,),
        origin="user_approved",
        elapsed_ms=10,
    )
    result = CaseExecutionResult(
        case_id=case.case_id,
        execution_id=execution_id,
        execution_status="completed",
        verdict="not_satisfied",
        action_step_ids=(1,),
        assertion_results=(observed,),
        elapsed_ms=20,
        blocker="assertion_precondition_failed",
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
            id=2,
            execution_id=execution_id,
            step_number=2,
            action_type="assertion",
            status="completed",
            observation_summary=json.dumps(observed.model_dump(mode="json")),
        ),
    }
    artifacts = {
        artifact_id: Artifact(
            id=artifact_id,
            execution_id=execution_id,
            step_id=2,
            artifact_type="screenshot",
            metadata_json={"kind": "viewport"},
        )
    }
    return case, result, steps, artifacts


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


def test_precondition_failure_accepts_only_the_exact_evidence_backed_prefix() -> None:
    case, result, steps, artifacts = recorded_precondition_failure()
    assert valid_case_evidence(case, result, steps, artifacts)

    forged_target = CaseAction(
        action="click",
        target=SemanticTarget(
            role="button",
            name="Different control",
        ),
    )
    mismatched_case = CaseSpec(
        case_id=case.case_id,
        feature_key=case.feature_key,
        title=case.title,
        kind=case.kind,
        requirement_refs=case.requirement_refs,
        steps=(forged_target,),
        expected=case.expected,
    )
    assert not valid_case_evidence(mismatched_case, result, steps, artifacts)

    missing_artifact = dict(artifacts)
    missing_artifact.clear()
    assert not valid_case_evidence(case, result, steps, missing_artifact)

    missing_prefix = dict(steps)
    missing_prefix.pop(1)
    assert not valid_case_evidence(case, result, missing_prefix, artifacts)


@pytest.mark.parametrize("oracle", ["url_path_v1", "visible_text"])
def test_new_oracle_semantics_preserve_exact_frozen_expectations(oracle: str) -> None:
    case, result, steps, artifacts, plan = recorded_case()
    expected = ExpectedAssertion(
        assertion_id="error",
        oracle=oracle,  # type: ignore[arg-type]
        target=None if oracle == "url_path_v1" else case.expected[0].target,
        expected_value="http://127.0.0.1:5191/guide" if oracle == "url_path_v1" else "One  two",
        origin="fixture_truth",
        requirement_refs=("email",),
    )
    case = case.model_copy(update={"expected": (expected,)})
    scope = plan.scope.model_copy(
        update={
            "requirements": (
                plan.scope.requirements[0].model_copy(update={"assertions": (expected,)}),
            )
        }
    )
    plan = plan.model_copy(update={"scope": scope, "cases": (case,)})
    payload = result.assertion_results[0].model_dump()
    payload.update(
        oracle=oracle,
        expected_value=expected.expected_value,
        status="satisfied",
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
        case,
        result.model_copy(update={"assertion_results": (altered,)}),
        steps,
        artifacts,
    )


@pytest.mark.parametrize(
    "recorded_action,valid",
    [
        ("registration_submit", True),
        ("click", False),
        ("get_state", False),
    ],
)
def test_fixture_approval_step_must_match_the_frozen_action_identity(
    recorded_action: str,
    valid: bool,
) -> None:
    case, result, steps, artifacts, _ = recorded_case()
    approved_action = CaseAction(
        action="click",
        action_id="registration_submit",
        target=SemanticTarget(
            role="button",
            name="Save",
            scope_role="form",
            scope_name="Registration",
        ),
    )
    case = case.model_copy(update={"steps": (approved_action,)})
    steps[2].action_type = recorded_action
    assert valid_case_evidence(case, result, steps, artifacts) is valid


@pytest.mark.parametrize(
    "fault",
    [
        "artifact_step",
        "artifact_owner",
        "step_owner",
        "observed",
        "action_failed",
        "action_type",
        "missing_assertion",
    ],
)
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


@pytest.mark.parametrize(
    "overrides",
    [
        {"verdict": "satisfied"},
        {"blocker": None},
        {"execution_status": "failed"},
    ],
)
def test_skipped_human_assistance_cannot_fabricate_an_assertion_verdict(overrides) -> None:
    payload = dict(
        case_id="login",
        execution_id=uuid4(),
        execution_status="skipped",
        verdict="unverified",
        blocker="human_assistance_skipped",
        elapsed_ms=100,
    )
    assert CaseExecutionResult.model_validate(payload).assertion_results == ()
    with pytest.raises(ValidationError):
        CaseExecutionResult.model_validate({**payload, **overrides})


@pytest.mark.parametrize("blocked", [False, True])
async def test_human_assistance_evaluation_preserves_reason_without_findings(
    monkeypatch,
    blocked,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from markettwin_evaluation_worker import deep_evaluator

    case, result, _steps, _artifacts, plan = recorded_case()
    skipped = CaseExecutionResult(
        case_id=case.case_id,
        execution_id=result.execution_id,
        execution_status="policy_blocked" if blocked else "skipped",
        verdict="unverified",
        blocker="authentication_challenge_blocked" if blocked else "human_assistance_skipped",
        elapsed_ms=100,
    )
    journey_id = uuid4()
    events = [
        SimpleNamespace(event_type="test_plan.created", payload=plan.model_dump(mode="json")),
        SimpleNamespace(
            event_type="test_case.completed",
            payload=skipped.model_dump(mode="json"),
            execution_id=result.execution_id,
            journey_id=journey_id,
        ),
    ]
    batches = [
        events,
        [SimpleNamespace(id=journey_id, ordinal=1)],
        [SimpleNamespace(id=result.execution_id, journey_id=journey_id)],
        [],
        [],
    ]
    session = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[SimpleNamespace(all=lambda items=items: items) for items in batches]
        )
    )
    create_report = AsyncMock(return_value=uuid4())
    create_finding = AsyncMock()
    monkeypatch.setattr(
        deep_evaluator,
        "ReportRepository",
        lambda _: SimpleNamespace(
            create_completed_report=create_report,
        ),
    )
    monkeypatch.setattr(
        deep_evaluator,
        "EvaluationRepository",
        lambda _: SimpleNamespace(
            create_linked_finding=create_finding,
        ),
    )
    finding_ids, _report_id = await deep_evaluator.evaluate_deep_run(
        test_run_id=uuid4(),
        session=session,
        trusted_scope=plan.scope,
    )
    assert finding_ids == ()
    create_finding.assert_not_awaited()
    payload = create_report.await_args.kwargs["report_payload"]
    assert payload["coverage"]["executed"] == int(blocked)
    assert payload["coverage"]["blocked"] == int(blocked)
    assert payload["coverage"]["not_run"] == int(not blocked)
    assert payload["coverage"]["human_assistance_skipped"] == int(not blocked)
    assert payload["coverage"]["failed_assertions"] == 0
    assert payload["coverage"]["inconclusive"] == 0
    assert payload["cases"][0]["reason"] == (
        "authentication_challenge_blocked" if blocked else "human_assistance_skipped"
    )
    assert payload["cases"][0]["verdict"] == ("blocked" if blocked else "not_run")


def test_user_approved_assertion_is_grounded_against_frozen_contract():
    target = SemanticTarget(role="alert", name="Validation")
    approved_assertion = ExpectedAssertion(
        assertion_id="error",
        oracle="visible_text",
        target=target,
        expected_value="Email required",
        origin="user_approved",
    )
    case = CaseSpec(
        case_id="empty_email",
        feature_key="form",
        title="Empty email validation",
        kind="negative",
        steps=(CaseAction(action="click", target=SemanticTarget(role="button", name="Check")),),
        expected=(approved_assertion,),
    )
    plan = DeepFeaturePlan(
        scope=FeatureScope(
            feature_key="form",
            goal="Check validation",
            starting_url="http://127.0.0.1:5191/",
            allowed_origins=("http://127.0.0.1:5191",),
        ),
        budget=PlanBudget(),
        cases=(case,),
    )

    contract_assertion = ContractAssertion(
        assertion_id="error",
        oracle="visible_text",
        target_role="alert",
        target_name="Validation",
        expected_value="Email required",
        plain_language="After clicking check, alert appears.",
        origin="user_approved",
        source_step_ordinal=1,
    )
    frozen_contract = TestContract(
        contract_id=uuid4(),
        test_run_id=uuid4(),
        version=1,
        status="frozen",
        journeys=(
            FrozenJourneyContract(
                journey_key="form_check",
                title="Form Check",
                feature_key="form",
                steps=case.steps,
                assertions=(contract_assertion,),
            ),
        ),
    )

    # (a) user-approved assertion with matching frozen contract -> grounded
    assert grounded_failure(case, plan, None, frozen_contract=frozen_contract) is True

    # (b) identical assertion without approval (origin is inferred or contract
    # not approved) -> NOT grounded
    inferred_assertion = ExpectedAssertion(
        assertion_id="error",
        oracle="visible_text",
        target=target,
        expected_value="Email required",
        origin="inferred",
    )
    inferred_case = case.model_copy(update={"expected": (inferred_assertion,)})
    assert grounded_failure(inferred_case, plan, None, frozen_contract=frozen_contract) is False

    draft_contract = frozen_contract.model_copy(update={"status": "draft"})
    assert grounded_failure(case, plan, None, frozen_contract=draft_contract) is False


def test_contract_edited_after_freeze_fails_evidence_validation():
    case, result, steps, artifacts, _plan = recorded_case()
    frozen_contract = TestContract(
        contract_id=uuid4(),
        test_run_id=uuid4(),
        version=1,
        status="frozen",
        journeys=(),
    )
    original_hash = frozen_contract.content_hash()

    # Valid when hash matches
    assert (
        valid_case_evidence(
            case,
            result,
            steps,
            artifacts,
            frozen_contract=frozen_contract,
            expected_contract_hash=original_hash,
        )
        is True
    )

    # (c) Contract edited after freeze (hash mismatch) -> NOT valid
    mismatched_hash = "0" * 64
    assert (
        valid_case_evidence(
            case,
            result,
            steps,
            artifacts,
            frozen_contract=frozen_contract,
            expected_contract_hash=mismatched_hash,
        )
        is False
    )
