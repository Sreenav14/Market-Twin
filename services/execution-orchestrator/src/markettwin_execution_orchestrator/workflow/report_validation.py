"""Reconcile agent claims with the mission and persisted browser execution."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from markettwin_database.models import Artifact, ExecutionStep
from markettwin_shared.deep_testing import AssertionResult
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.agents.schemas.persona_report import (
    CriterionEvidence,
    JourneyReportedOutcome,
    PersonaAgentReport,
)


@dataclass(frozen=True, slots=True)
class ReportValidationResult:
    """Execution consistency is not independent verification of product behavior."""

    report: PersonaAgentReport
    issues: tuple[str, ...]
    policy_blocked: bool


def validate_persona_report(
    *,
    report: PersonaAgentReport,
    success_criteria: tuple[str, ...],
    execution_id: UUID,
    steps: Sequence[ExecutionStep],
    evidence_step_ids: frozenset[int],
    assertion_results: Sequence[AssertionResult] = (),
) -> ReportValidationResult:
    """Keep unsupported claims unverified; never rewrite a failed browser action."""
    owned_steps = {step.id: step for step in steps if step.execution_id == execution_id}
    issues: list[str] = []
    assigned = {criterion.strip() for criterion in success_criteria}
    for item in report.criterion_evidence:
        if item.criterion.strip() not in assigned:
            issues.append(f'Unassigned criterion was reported: "{item.criterion}".')

    checked: list[CriterionEvidence] = []
    for criterion in success_criteria:
        entries = [
            item
            for item in report.criterion_evidence
            if item.criterion.strip() == criterion.strip()
        ]
        status = entries[0].status if len(entries) == 1 else "unverified"
        if len(entries) != 1:
            issues.append(
                f'Expected exactly one report for criterion: "{criterion}"; '
                f"received {len(entries)}."
            )
        cited_ids = tuple(
            dict.fromkeys(step_id for entry in entries for step_id in entry.evidence_step_ids)
        )
        valid_ids = tuple(step_id for step_id in cited_ids if step_id in owned_steps)
        if len(valid_ids) != len(cited_ids):
            issues.append(f'Criterion references steps outside this execution: "{criterion}".')
            status = "unverified"
        if status != "unverified" and (
            not valid_ids
            or any(owned_steps[step_id].status != "completed" for step_id in valid_ids)
            or any(step_id not in evidence_step_ids for step_id in valid_ids)
        ):
            issues.append(
                f'Criterion lacks completed actions with recorded evidence: "{criterion}".'
            )
            status = "unverified"
        checked.append(
            CriterionEvidence(
                criterion=criterion,
                status=status,
                evidence_step_ids=valid_ids,
            )
        )

    satisfied = tuple(item.criterion for item in checked if item.status == "satisfied")
    unsatisfied = tuple(item.criterion for item in checked if item.status == "unsatisfied")
    if sorted(item.strip() for item in report.satisfied_criteria) != sorted(satisfied):
        issues.append("Satisfied criteria do not agree with the checked criterion evidence.")
    if sorted(item.strip() for item in report.unsatisfied_criteria) != sorted(unsatisfied):
        issues.append("Unsatisfied criteria do not agree with the checked criterion evidence.")

    unverified = any(item.status == "unverified" for item in checked)
    outcome: JourneyReportedOutcome = report.outcome
    if (
        (outcome == "passed" and (unverified or len(satisfied) != len(success_criteria)))
        or (outcome == "failed" and (unverified or not unsatisfied))
        or (outcome == "partial" and (unverified or not satisfied or not unsatisfied))
    ):
        issues.append("Reported outcome contradicts the available criterion evidence.")
    policy_blocked = any(step.status == "policy_blocked" for step in owned_steps.values())
    if policy_blocked:
        issues.append("Browser policy blocked this execution; this is not a product defect.")
    if any(item.execution_id != execution_id for item in assertion_results):
        issues.append("Deterministic assertions belong to another execution.")
    elif assertion_results:
        failed = any(item.status == "not_satisfied" for item in assertion_results)
        passed = all(item.status == "satisfied" for item in assertion_results)
        if outcome == "passed" and failed:
            issues.append(
                "Persona report claims success while a deterministic assertion is not satisfied."
            )
        if outcome == "failed" and passed:
            issues.append(
                "Persona report claims failure while every deterministic assertion passed."
            )
    if issues:
        outcome = "inconclusive"
    return ReportValidationResult(
        report=report.model_copy(
            update={
                "outcome": outcome,
                "criterion_evidence": tuple(checked),
                "satisfied_criteria": satisfied,
                "unsatisfied_criteria": unsatisfied,
            }
        ),
        issues=tuple(issues),
        policy_blocked=policy_blocked,
    )


async def validate_execution_report(
    *,
    report: PersonaAgentReport,
    success_criteria: tuple[str, ...],
    execution_id: UUID,
    session: AsyncSession,
) -> ReportValidationResult:
    """Read authoritative execution records before the journey result is persisted."""
    steps = tuple(
        (
            await session.scalars(
                select(ExecutionStep).where(
                    ExecutionStep.execution_id == execution_id,
                )
            )
        ).all()
    )
    artifacts = tuple(
        (
            await session.scalars(
                select(Artifact).where(
                    Artifact.execution_id == execution_id,
                    Artifact.step_id.in_(tuple(step.id for step in steps)),
                )
            )
        ).all()
    )
    evidence_step_ids = frozenset(
        artifact.step_id
        for artifact in artifacts
        if artifact.step_id is not None
        and (
            artifact.artifact_type == "screenshot"
            or artifact.metadata_json.get("kind") == "accessibility_snapshot"
        )
    )
    assertions: list[AssertionResult] = []
    for step in steps:
        if step.action_type != "assertion" or not step.observation_summary:
            continue
        try:
            assertions.append(AssertionResult.model_validate(json.loads(step.observation_summary)))
        except (TypeError, ValueError, ValidationError):
            continue
    return validate_persona_report(
        report=report,
        success_criteria=success_criteria,
        execution_id=execution_id,
        steps=steps,
        evidence_step_ids=evidence_step_ids,
        assertion_results=tuple(assertions),
    )
