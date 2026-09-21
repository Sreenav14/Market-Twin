"""Top-level MarketTwin evaluation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_evaluation_worker.deterministic_evaluator import (
    evaluate_completed_run,
)
from markettwin_evaluation_worker.observability import (
    VisualInvocationRecorder,
    VisualModelConfig,
    build_visual_runtime_snapshot,
)
from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
)
from markettwin_evaluation_worker.persistence.observability_repository import (
    EvaluationObservabilityRepository,
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
    VISUAL_MAX_TOKENS,
    VISUAL_RATE_LIMIT_MAX_ATTEMPTS,
    VISUAL_TEMPERATURE,
    build_visual_prompt,
    visual_model_name,
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

        visual_config = VisualModelConfig(
            model_name=visual_model_name(),
            max_tokens=VISUAL_MAX_TOKENS,
            temperature=VISUAL_TEMPERATURE,
            max_attempts=VISUAL_RATE_LIMIT_MAX_ATTEMPTS,
        )
        visual_snapshot_id = uuid4()
        observability_repository = (
            EvaluationObservabilityRepository(
                session
            )
        )
        await observability_repository.create_agent_snapshot(
            snapshot_id=visual_snapshot_id,
            snapshot=build_visual_runtime_snapshot(
                test_run_id=test_run_id,
                config=visual_config,
                effective_instruction=build_visual_prompt(
                    "{{criterion}}"
                ),
            ),
        )
        visual_invocation_recorder = VisualInvocationRecorder(
            repository=observability_repository,
            test_run_id=test_run_id,
            agent_snapshot_id=visual_snapshot_id,
            config=visual_config,
        )

        visual_evaluation = (
            await evaluate_visual_criteria_for_run(
                test_run_id=test_run_id,
                repository=repository,
                storage=storage,
                invocation_recorder=(
                    visual_invocation_recorder
                ),
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
