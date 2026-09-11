"""Top-level MarketTwin evaluation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_evaluation_worker.deterministic_evaluator import (
    evaluate_completed_run,
)
from markettwin_evaluation_worker.report_generator import (
    generate_deterministic_report,
)


@dataclass(frozen=True, slots=True)
class EvaluationWorkflowResult:
    """Result of one complete evaluation workflow."""

    test_run_id: UUID
    finding_ids: tuple[UUID, ...]
    report_id: UUID


async def evaluate_and_generate_report(
    *,
    test_run_id: UUID,
    session: AsyncSession,
) -> EvaluationWorkflowResult:
    """Create findings and report in one transaction."""

    try:
        evaluation = await evaluate_completed_run(
            test_run_id=test_run_id,
            session=session,
        )

        report = (
            await generate_deterministic_report(
                test_run_id=test_run_id,
                session=session,
            )
        )

        await session.commit()

    except Exception:
        await session.rollback()
        raise

    return EvaluationWorkflowResult(
        test_run_id=test_run_id,
        finding_ids=(
            evaluation.finding_ids
        ),
        report_id=report.report_id,
    )