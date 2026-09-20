"""Evidence-backed visual evaluation for MarketTwin criteria."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
    VisualEvidenceSet,
)
from markettwin_evaluation_worker.visual_artifact_storage import (
    VisualArtifactStorage,
)
from markettwin_evaluation_worker.visual_verifier import (
    VisualVerificationStatus,
    verify_visual_criterion,
)


@dataclass(frozen=True, slots=True)
class VisualCriterionEvaluation:
    """Visual judgment with exact evidence provenance."""

    criterion: str
    status: VisualVerificationStatus
    rationale: str
    observed_details: tuple[str, ...]

    evidence_step_id: int | None
    artifact_ids: tuple[UUID, ...]


def _select_visual_evidence(
    evidence: tuple[VisualEvidenceSet, ...],
) -> VisualEvidenceSet | None:
    """Prefer viewport + crop, then fall back to viewport-only evidence."""

    for item in evidence:
        if (
            item.viewport is not None
            and item.element_crop is not None
        ):
            return item

    for item in evidence:
        if item.viewport is not None:
            return item

    return None


async def evaluate_visual_criterion_from_evidence(
    *,
    criterion: str,
    evidence: tuple[VisualEvidenceSet, ...],
    storage: VisualArtifactStorage,
) -> VisualCriterionEvaluation:
    """Verify one criterion from already-selected visual evidence."""

    selected = _select_visual_evidence(
        evidence
    )

    if (
        selected is None
        or selected.viewport is None
    ):
        return VisualCriterionEvaluation(
            criterion=criterion,
            status="unverified",
            rationale=(
                "No viewport screenshot evidence was available "
                "for the referenced browser steps."
            ),
            observed_details=(),
            evidence_step_id=None,
            artifact_ids=(),
        )

    with TemporaryDirectory(
        prefix="markettwin-visual-"
    ) as temporary_directory:
        directory = Path(
            temporary_directory
        )

        viewport_path = await storage.download(
            artifact=selected.viewport,
            directory=directory,
        )

        focused_path: Path | None = None

        if selected.element_crop is not None:
            focused_path = await storage.download(
                artifact=selected.element_crop,
                directory=directory,
            )

        verification = await verify_visual_criterion(
            criterion=criterion,
            viewport_path=viewport_path,
            focused_path=focused_path,
        )

    artifact_ids = [
        selected.viewport.artifact_id,
    ]

    if selected.element_crop is not None:
        artifact_ids.append(
            selected.element_crop.artifact_id
        )

    return VisualCriterionEvaluation(
        criterion=criterion,
        status=verification.status,
        rationale=verification.rationale,
        observed_details=(
            verification.observed_details
        ),
        evidence_step_id=selected.step_id,
        artifact_ids=tuple(
            artifact_ids
        ),
    )
    
async def evaluate_visual_criterion_from_steps(
    *,
    criterion: str,
    execution_id: UUID,
    step_ids: tuple[int, ...],
    repository: EvaluationRepository,
    storage: VisualArtifactStorage,
) -> VisualCriterionEvaluation:
    """Load referenced screenshots and visually verify one criterion."""

    evidence = await repository.list_visual_evidence(
        execution_id=execution_id,
        step_ids=step_ids,
    )

    return await evaluate_visual_criterion_from_evidence(
        criterion=criterion,
        evidence=evidence,
        storage=storage,
    )