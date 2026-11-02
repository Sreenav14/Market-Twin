"""Recover progress only from this execution's persisted steps."""

from uuid import UUID

from markettwin_database.models import ExecutionStep
from markettwin_shared.deep_testing import AssertionResult
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.agents.schemas.journey import PersonaJourneySpec
from markettwin_execution_orchestrator.workflow.persona_result import (
    JourneyExecutionStatus,
    PersonaJourneyResult,
)


async def salvage_partial_result(
    *, session: AsyncSession, execution_id: UUID, journey: PersonaJourneySpec,
    status: JourneyExecutionStatus,
) -> PersonaJourneyResult:
    steps = tuple((await session.scalars(
        select(ExecutionStep).where(ExecutionStep.execution_id == execution_id)
        .order_by(ExecutionStep.step_number)
    )).all())
    completed = [s for s in steps if s.execution_id == execution_id and s.status == "completed"]
    assertions: list[AssertionResult] = []
    for step in completed:
        if step.action_type != "assertion" or not step.observation_summary:
            continue
        try:
            assertion = AssertionResult.model_validate_json(step.observation_summary)
        except ValidationError:
            continue
        if assertion.execution_id == execution_id and assertion.step_id == step.id:
            assertions.append(assertion)
    last = completed[-1] if completed else None
    prefix = "Timed out" if status == JourneyExecutionStatus.TIMED_OUT else "Invalid report"
    # Use the recorder's action summary, which already omits sensitive form values.
    detail = f" (last: {last.action_summary[:300]})" if last else ""
    return PersonaJourneyResult(
        journey=journey, status=status, partial=True, steps_completed=len(completed),
        last_completed_step_id=last.id if last else None,
        assertion_results=tuple(assertions),
        summary=f"{prefix} after {len(completed)} completed steps{detail}",
    )
