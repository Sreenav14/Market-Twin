"""Top-level MarketTwin evaluation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_evaluation_worker.deterministic_evaluator import (
    evaluate_completed_run,
)
from markettwin_evaluation_worker.observability import (
    initialize_litellm_observability,
)
from markettwin_evaluation_worker.persistence import (
    EvaluationRuntimeSnapshotRepository,
)
from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
)
from markettwin_evaluation_worker.report_generator import (
    generate_deterministic_report,
)
from markettwin_evaluation_worker.visual_artifact_storage import (
    VisualArtifactStorage,
)
from markettwin_evaluation_worker.visual_batch_evaluator import (
    evaluate_visual_criteria_for_run,
)
from markettwin_evaluation_worker.visual_findings import (
    persist_visual_findings,
)
from markettwin_evaluation_worker.visual_verifier import (
    build_visual_runtime_snapshot_payload,
)


@dataclass(frozen=True, slots=True)
class EvaluationWorkflowResult:
    """Result of one complete evaluation workflow."""

    test_run_id: UUID
    finding_ids: tuple[UUID, ...]
    report_id: UUID
    visual_evaluation_count: int = 0


async def evaluate_and_generate_report(
    *,
    test_run_id: UUID,
    session: AsyncSession,
    visual_storage: VisualArtifactStorage | None = None,
) -> EvaluationWorkflowResult:
    """Create findings and report in one transaction."""

    try:
        initialize_litellm_observability()
        readiness_repository = EvaluationRepository(
            session
        )
        
        await readiness_repository.validate_run_ready(
            test_run_id=test_run_id,
        )
        
        snapshot_repository = (
            EvaluationRuntimeSnapshotRepository(
                session
            )
        )
        
        visual_snapshot = (
            build_visual_runtime_snapshot_payload()
        )

        visual_snapshot_id = uuid4()
        visual_snapshot_id = (
            await snapshot_repository.ensure_run_level_snapshot(
                snapshot_id=visual_snapshot_id,
                test_run_id=test_run_id,
                payload=visual_snapshot,
            )
        )
        
        await session.commit()
        
        evaluation = await evaluate_completed_run(
            test_run_id=test_run_id,
            session=session,
        )

        repository = EvaluationRepository(
            session
        )

        storage = (
            visual_storage
            or VisualArtifactStorage.from_environment()
        )

        visual_evaluation = (
            await evaluate_visual_criteria_for_run(
                test_run_id=test_run_id,
                agent_snapshot_id=visual_snapshot_id,
                repository=repository,
                storage=storage,
            )
        )

        visual_finding_ids = (
            await persist_visual_findings(
                test_run_id=test_run_id,
                visual_result=visual_evaluation,
                repository=repository,
            )
        )
        report = await generate_deterministic_report(
            test_run_id=test_run_id,
            session=session,
        )

        await session.commit()

    except Exception:
        await session.rollback()
        raise

    return EvaluationWorkflowResult(
        test_run_id=test_run_id,
        finding_ids=(evaluation.finding_ids + visual_finding_ids),
        report_id=report.report_id,
        visual_evaluation_count=len(
            visual_evaluation.evaluations
        ),
    )
