"""Persona reports must agree with mission criteria and execution records."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_database.models import ExecutionStep
from markettwin_execution_orchestrator.agents.schemas.persona_report import (
    CriterionEvidence,
    PersonaAgentReport,
)
from markettwin_execution_orchestrator.workflow.report_validation import (
    validate_execution_report,
    validate_persona_report,
)
from markettwin_shared.deep_testing import AssertionResult
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.parametrize("step_id", [0, -1, True, "7"])
def test_criterion_step_ids_must_be_positive_integers(step_id: object) -> None:
    with pytest.raises(ValidationError):
        CriterionEvidence.model_validate(
            {
                "criterion": "Confirmation visible",
                "status": "satisfied",
                "evidence_step_ids": [step_id],
            }
        )


def _report() -> PersonaAgentReport:
    return PersonaAgentReport(
        outcome="passed",
        summary="Confirmation observed.",
        satisfied_criteria=("Confirmation visible",),
        criterion_evidence=(
            CriterionEvidence(
                criterion="Confirmation visible",
                status="satisfied",
                evidence_step_ids=(7,),
            ),
        ),
    )


def test_assertion_contradiction_stays_diagnostic() -> None:
    execution_id = uuid4()
    assertion = AssertionResult(
        case_id="empty_email",
        assertion_id="error",
        oracle="visible_text",
        expected_value="Email required",
        observed_value="absent",
        status="not_satisfied",
        execution_id=execution_id,
        step_id=3,
        artifact_ids=(uuid4(),),
        origin="fixture_truth",
        requirement_refs=("email",),
        elapsed_ms=10,
    )
    result = validate_persona_report(
        report=_report(),
        success_criteria=("Confirmation visible",),
        execution_id=execution_id,
        steps=(ExecutionStep(id=7, execution_id=execution_id, status="completed"),),
        evidence_step_ids=frozenset({7}),
        assertion_results=(assertion,),
    )
    assert result.report.outcome == "inconclusive"
    assert any("deterministic assertion" in issue for issue in result.issues)
    foreign = assertion.model_copy(update={"execution_id": uuid4()})
    rejected = validate_persona_report(
        report=_report(),
        success_criteria=("Confirmation visible",),
        execution_id=execution_id,
        steps=(ExecutionStep(id=7, execution_id=execution_id, status="completed"),),
        evidence_step_ids=frozenset({7}),
        assertion_results=(foreign,),
    )
    assert any("another execution" in issue for issue in rejected.issues)


def test_grounded_report_is_retained_without_claiming_independent_verification() -> None:
    execution_id = uuid4()
    report = _report()
    original = report.model_dump()
    result = validate_persona_report(
        report=report,
        success_criteria=("Confirmation visible",),
        execution_id=execution_id,
        steps=(ExecutionStep(id=7, execution_id=execution_id, status="completed"),),
        evidence_step_ids=frozenset({7}),
    )
    assert result.report == report
    assert result.issues == ()
    assert result.policy_blocked is False
    assert report.model_dump() == original


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "duplicate",
        "invented",
        "cross_execution",
        "nonexistent_step",
        "failed_action",
        "missing_artifact",
        "contradictory_lists",
        "contradictory_outcome",
        "pending_action",
    ],
)
def test_unsupported_report_is_inconclusive(case: str) -> None:
    execution_id = uuid4()
    report = _report()
    step = ExecutionStep(id=7, execution_id=execution_id, status="completed")
    steps = (step,)
    evidence_step_ids = frozenset({7})
    if case == "missing":
        report = report.model_copy(update={"criterion_evidence": ()})
    elif case == "duplicate":
        report = report.model_copy(update={"criterion_evidence": report.criterion_evidence * 2})
    elif case == "invented":
        report = report.model_copy(
            update={
                "criterion_evidence": report.criterion_evidence
                + (
                    CriterionEvidence(
                        criterion="People love the product",
                        status="satisfied",
                        evidence_step_ids=(7,),
                    ),
                )
            }
        )
    elif case == "cross_execution":
        step.execution_id = uuid4()
    elif case == "nonexistent_step":
        steps = ()
    elif case == "failed_action":
        step.status = "failed"
    elif case == "pending_action":
        step.status = "running"
    elif case == "missing_artifact":
        evidence_step_ids = frozenset()
    elif case == "contradictory_lists":
        report = report.model_copy(update={"unsatisfied_criteria": ("Confirmation visible",)})
    elif case == "contradictory_outcome":
        report = report.model_copy(update={"outcome": "failed"})
    result = validate_persona_report(
        report=report,
        success_criteria=("Confirmation visible",),
        execution_id=execution_id,
        steps=steps,
        evidence_step_ids=evidence_step_ids,
    )
    assert result.report.outcome == "inconclusive"
    assert result.issues
    assert len(result.report.criterion_evidence) == 1
    assert result.report.criterion_evidence[0].criterion == "Confirmation visible"
    if case in {
        "missing",
        "duplicate",
        "cross_execution",
        "nonexistent_step",
        "failed_action",
        "missing_artifact",
        "pending_action",
    }:
        assert result.report.criterion_evidence[0].status == "unverified"
    # The original report object remains a model claim, independent of correction.
    assert report.outcome == ("failed" if case == "contradictory_outcome" else "passed")


def test_policy_block_cannot_be_reported_as_product_success_or_failure() -> None:
    execution_id = uuid4()
    result = validate_persona_report(
        report=_report(),
        success_criteria=("Confirmation visible",),
        execution_id=execution_id,
        steps=(ExecutionStep(id=7, execution_id=execution_id, status="policy_blocked"),),
        evidence_step_ids=frozenset({7}),
    )
    assert result.policy_blocked is True
    assert result.report.outcome == "inconclusive"
    assert result.report.criterion_evidence[0].status == "unverified"


def test_explicit_unverified_result_without_evidence_remains_inconclusive() -> None:
    report = PersonaAgentReport(
        outcome="inconclusive",
        summary="Evidence unavailable.",
        criterion_evidence=(
            CriterionEvidence(criterion="Confirmation visible", status="unverified"),
        ),
    )
    result = validate_persona_report(
        report=report,
        success_criteria=("Confirmation visible",),
        execution_id=uuid4(),
        steps=(),
        evidence_step_ids=frozenset(),
    )
    assert result.report == report
    assert result.issues == ()


def test_successful_recovery_does_not_rewrite_or_cite_the_failed_action() -> None:
    execution_id = uuid4()
    failed = ExecutionStep(id=6, execution_id=execution_id, status="failed")
    completed = ExecutionStep(id=7, execution_id=execution_id, status="completed")
    result = validate_persona_report(
        report=_report(), success_criteria=("Confirmation visible",),
        execution_id=execution_id, steps=(failed, completed),
        evidence_step_ids=frozenset({6, 7}),
    )
    assert result.report.outcome == "passed"
    assert result.issues == ()
    assert result.report.criterion_evidence[0].evidence_step_ids == (7,)
    assert failed.status == "failed"


async def test_runtime_boundary_reads_actual_steps_and_recorded_artifacts() -> None:
    execution_id = uuid4()
    step = ExecutionStep(id=7, execution_id=execution_id, status="completed")
    artifact = SimpleNamespace(step_id=7, artifact_type="screenshot", metadata_json={})
    session = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                SimpleNamespace(all=lambda: [step]),
                SimpleNamespace(all=lambda: [artifact]),
            ]
        )
    )
    result = await validate_execution_report(
        report=_report(),
        success_criteria=("Confirmation visible",),
        execution_id=execution_id,
        session=cast(AsyncSession, session),
    )
    assert result.issues == ()
    assert result.report.outcome == "passed"


async def test_runtime_boundary_uses_recorded_assertion_results() -> None:
    execution_id = uuid4()
    assertion = AssertionResult(
        case_id="empty_email",
        assertion_id="error",
        oracle="visible_text",
        expected_value="Email required",
        observed_value="absent",
        status="not_satisfied",
        execution_id=execution_id,
        step_id=3,
        artifact_ids=(uuid4(),),
        origin="fixture_truth",
        requirement_refs=("email",),
        elapsed_ms=10,
    )
    step = ExecutionStep(
        id=7,
        execution_id=execution_id,
        status="completed",
        action_type="assertion",
        observation_summary=assertion.model_dump_json(),
    )
    artifact = SimpleNamespace(step_id=7, artifact_type="screenshot", metadata_json={})
    session = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                SimpleNamespace(all=lambda: [step]),
                SimpleNamespace(all=lambda: [artifact]),
            ]
        )
    )
    result = await validate_execution_report(
        report=_report(),
        success_criteria=("Confirmation visible",),
        execution_id=execution_id,
        session=cast(AsyncSession, session),
    )
    assert result.report.outcome == "inconclusive"
    assert any("deterministic assertion" in issue for issue in result.issues)
