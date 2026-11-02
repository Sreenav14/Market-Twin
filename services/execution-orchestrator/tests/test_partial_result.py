"""Incomplete model output cannot erase persisted execution progress."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from markettwin_database.models import ExecutionStep
from markettwin_execution_orchestrator.agents.schemas.journey import PersonaJourneySpec
from markettwin_execution_orchestrator.agents.schemas.mission import TestMissionSpec
from markettwin_execution_orchestrator.agents.schemas.persona import PersonaSpec
from markettwin_execution_orchestrator.workflow.partial_result import salvage_partial_result
from markettwin_execution_orchestrator.workflow.persona_result import JourneyExecutionStatus


@pytest.mark.parametrize(
    "status", [JourneyExecutionStatus.TIMED_OUT, JourneyExecutionStatus.FAILED],
)
async def test_salvage_counts_only_completed_owned_steps(status) -> None:
    execution_id = uuid4()
    journey = PersonaJourneySpec(
        journey_key="new__pricing",
        persona=PersonaSpec(persona_id="new", name="New user", perspective="First visit",
                            behavior_traits=("careful",), priorities=("clarity",)),
        mission=TestMissionSpec(mission_id="pricing", name="Pricing", objective="Find pricing",
                                success_criteria=("Pricing found",), priority="high"),
    )
    rows = [ExecutionStep(id=index, execution_id=owner, step_number=index, status=state,
                          action_type="click", action_summary="click Pricing")
            for index, owner, state in [(1, execution_id, "completed"),
                                        (2, execution_id, "failed"),
                                        (3, uuid4(), "completed")]]
    session = AsyncMock()
    session.scalars.return_value = Mock(all=Mock(return_value=rows))
    result = await salvage_partial_result(
        session=session, execution_id=execution_id, journey=journey, status=status,
    )
    assert result.partial
    assert result.status == status
    assert result.outcome is None
    assert result.steps_completed == 1
    assert result.last_completed_step_id == 1
    assert "1 completed steps (last: click Pricing)" in result.summary
