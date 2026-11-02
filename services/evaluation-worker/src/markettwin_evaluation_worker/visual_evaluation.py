"""Evidence-backed visual evaluation for MarketTwin criteria."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from markettwin_shared.observability import (
    use_observability_correlation,
)

from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
    VisualEvidenceSet,
)
from markettwin_evaluation_worker.persistence.visual_cache import VisualResultCache
from markettwin_evaluation_worker.visual_artifact_storage import (
    VisualArtifactStorage,
)
from markettwin_evaluation_worker.visual_verifier import (
    VisualVerificationStatus,
    build_visual_runtime_snapshot_payload,
    build_visual_verifier_prompt,
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
    test_run_id: UUID,
    journey_id: UUID,
    execution_id: UUID,
    agent_snapshot_id: UUID,
    criterion: str,
    evidence: tuple[VisualEvidenceSet, ...],
    storage: VisualArtifactStorage,
    execution_context: tuple[VisualEvidenceSet, ...] = (),
    cache: VisualResultCache | None = None,
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

        with use_observability_correlation(
            test_run_id=test_run_id,
            journey_id=journey_id,
            execution_id=execution_id,
            agent_snapshot_id=agent_snapshot_id,
            agent_role="visual_verifier",
        ):
            context: tuple[dict[str, object], ...] = tuple(
                {"step_id": item.step_id, "action_type": item.action_type,
                 "status": item.step_status,
                 **({"target": item.action_summary} if item.action_summary is not None else {})}
                for item in sorted(execution_context or evidence, key=lambda item: item.step_id)
                if item.step_id <= selected.step_id
            )
            fingerprint = hashlib.sha256(json.dumps({
                "schema_version": 1,
                "runtime_sha256": build_visual_runtime_snapshot_payload().sha256(),
                "prompt": build_visual_verifier_prompt(criterion, context),
                "viewport_sha256": hashlib.sha256(viewport_path.read_bytes()).hexdigest(),
                "focused_sha256": hashlib.sha256(focused_path.read_bytes()).hexdigest()
                if focused_path is not None else None,
            }, sort_keys=True, default=str).encode()).hexdigest()
            verification = await cache.get(
                run_id=test_run_id, execution_id=execution_id, key=fingerprint,
            ) if cache is not None else None
            if verification is None:
                verification = await verify_visual_criterion(
                    criterion=criterion,
                    viewport_path=viewport_path,
                    focused_path=focused_path,
                    execution_context=context,
                )
                if cache is not None:
                    await cache.put(
                        run_id=test_run_id, execution_id=execution_id,
                        key=fingerprint, result=verification,
                    )

    artifact_ids = [
        selected.viewport.artifact_id,
    ]

    if selected.element_crop is not None:
        artifact_ids.append(
            selected.element_crop.artifact_id
        )

    status = verification.status
    rationale = verification.rationale
    if status == "unsatisfied" and selected.element_crop is None:
        status = "unverified"
        rationale = (
            "Confirmation requires focused evidence of the relevant result region; "
            "a general viewport is insufficient. Visual observation: " + rationale
        )

    return VisualCriterionEvaluation(
        criterion=criterion,
        status=status,
        rationale=rationale,
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
    test_run_id: UUID,
    journey_id: UUID,
    criterion: str,
    execution_id: UUID,
    agent_snapshot_id: UUID,
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
        test_run_id=test_run_id,
        journey_id=journey_id,
        execution_id=execution_id,
        agent_snapshot_id=agent_snapshot_id,
        criterion=criterion,
        evidence=evidence,
        storage=storage,
    )
