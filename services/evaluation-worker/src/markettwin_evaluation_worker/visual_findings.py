"""Persist evidence-backed findings from visual verification."""

from __future__ import annotations

from uuid import UUID

from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
    EvidenceReference,
)
from markettwin_evaluation_worker.visual_batch_evaluator import (
    VisualBatchEvaluationResult,
)


async def persist_visual_findings(
    *,
    test_run_id: UUID,
    visual_result: VisualBatchEvaluationResult,
    repository: EvaluationRepository,
) -> tuple[UUID, ...]:
    """Create findings only for visually confirmed failures."""

    finding_ids: list[UUID] = []

    for item in visual_result.evaluations:
        evaluation = item.evaluation

        if evaluation.status != "unsatisfied":
            continue

        if not evaluation.artifact_ids:
            # An authoritative visual Finding must have
            # the exact image evidence used by the verifier.
            continue

        evidence = tuple(
            EvidenceReference(
                artifact_id=artifact_id,
            )
            for artifact_id in evaluation.artifact_ids
        )

        criterion = evaluation.criterion

        title_criterion = criterion

        if len(title_criterion) > 220:
            title_criterion = (
                title_criterion[:217]
                + "..."
            )

        finding_id = (
            await repository.create_linked_finding(
                test_run_id=test_run_id,
                journey_ids=(
                    item.journey_id,
                ),
                severity="medium",
                category="visual_criterion",
                title=(
                    "Visual criterion not satisfied: "
                    f"{title_criterion}"
                ),
                summary=(
                    "Visual verification of the captured "
                    "browser evidence found that the "
                    f'criterion "{criterion}" was not '
                    "satisfied. "
                    f"{evaluation.rationale}"
                ),
                recommendation=(
                    "Review the linked viewport and focused "
                    "visual evidence and correct the visible "
                    "product issue before rerunning this "
                    "Journey."
                ),
                evidence=evidence,
            )
        )

        finding_ids.append(
            finding_id
        )

    return tuple(finding_ids)