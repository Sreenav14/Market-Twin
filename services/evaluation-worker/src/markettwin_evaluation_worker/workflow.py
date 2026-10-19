"""Top-level MarketTwin evaluation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from markettwin_database.models import TestRun
from markettwin_shared.feature_plan import FeatureScope
from markettwin_shared.observability import use_observability_correlation
from opentelemetry import trace
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
from markettwin_evaluation_worker.run_assessment import assess_completed_run
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
    """Trace deterministic evaluation, visual checks, and final report generation."""
    initialize_litellm_observability()
    with use_observability_correlation(test_run_id=test_run_id):
        with trace.get_tracer(__name__).start_as_current_span("evaluation.run") as span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("markettwin.test_run_id", str(test_run_id))
            return await _evaluate_and_generate_report(
                test_run_id=test_run_id,
                session=session,
                visual_storage=visual_storage,
            )


async def _evaluate_and_generate_report(
    *,
    test_run_id: UUID,
    session: AsyncSession,
    visual_storage: VisualArtifactStorage | None = None,
) -> EvaluationWorkflowResult:
    """Persist immutable provenance first, then atomically commit findings/report.

    A failure after the provenance commit leaves its deduplicated runtime snapshot
    available for retry; findings and the final report roll back together.
    """

    try:
        run = await session.get(TestRun, test_run_id)
        if (
            run is not None
            and run.configuration_snapshot.get("execution_mode") == "deep_feature_v1"
        ):
            from markettwin_evaluation_worker.deep_evaluator import evaluate_deep_run

            await EvaluationRepository(session).validate_run_ready(test_run_id=test_run_id)
            frozen_scope = run.configuration_snapshot.get("feature_scope")
            scope = FeatureScope.model_validate(frozen_scope) if frozen_scope is not None else None
            finding_ids, report_id = await evaluate_deep_run(
                test_run_id=test_run_id, session=session, trusted_scope=scope,
            )
            await session.commit()
            return EvaluationWorkflowResult(
                test_run_id=test_run_id, finding_ids=finding_ids, report_id=report_id,
            )
        readiness_repository = EvaluationRepository(session)

        await readiness_repository.validate_run_ready(
            test_run_id=test_run_id,
        )

        snapshot_repository = EvaluationRuntimeSnapshotRepository(session)

        visual_snapshot = build_visual_runtime_snapshot_payload()

        visual_snapshot_id = uuid4()
        visual_snapshot_id = await snapshot_repository.ensure_run_level_snapshot(
            snapshot_id=visual_snapshot_id,
            test_run_id=test_run_id,
            payload=visual_snapshot,
        )

        await session.commit()

        evaluation = await evaluate_completed_run(
            test_run_id=test_run_id,
            session=session,
        )

        repository = EvaluationRepository(session)

        storage = visual_storage or VisualArtifactStorage.from_environment()

        visual_evaluation = await evaluate_visual_criteria_for_run(
            test_run_id=test_run_id,
            agent_snapshot_id=visual_snapshot_id,
            repository=repository,
            storage=storage,
        )

        visual_finding_ids = await persist_visual_findings(
            test_run_id=test_run_id,
            visual_result=visual_evaluation,
            repository=repository,
        )
        evaluation_records: tuple[dict[str, object], ...] = tuple(
            {
                "kind": "visual",
                "journey_id": str(item.journey_id),
                "execution_id": str(item.execution_id),
                "criterion": item.evaluation.criterion,
                "reported_status": item.reported_status,
                "status": item.evaluation.status,
                "rationale": item.evaluation.rationale,
                "observed_details": list(item.evaluation.observed_details),
                "evidence": {
                    "step_ids": [item.evaluation.evidence_step_id]
                    if item.evaluation.evidence_step_id is not None
                    else [],
                    "artifact_ids": [str(value) for value in item.evaluation.artifact_ids],
                },
            }
            for item in visual_evaluation.evaluations
        )
        assessment = await assess_completed_run(
            test_run_id=test_run_id,
            session=session,
            evaluation_records=evaluation_records,
        )
        report = await generate_deterministic_report(
            test_run_id=test_run_id,
            session=session,
            evaluation_records=evaluation_records,
            assessment=assessment,
        )

        await session.commit()

    except Exception:
        await session.rollback()
        raise

    return EvaluationWorkflowResult(
        test_run_id=test_run_id,
        finding_ids=(evaluation.finding_ids + visual_finding_ids),
        report_id=report.report_id,
        visual_evaluation_count=len(visual_evaluation.evaluations),
    )
