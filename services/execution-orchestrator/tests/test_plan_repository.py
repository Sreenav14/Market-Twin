"""Tests for persisted Meta Agent planning."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_database.models.testing import (
    PersonaJourney,
    RunMission,
    RunPersona,
)
from markettwin_execution_orchestrator.agents.schemas.mission import (
    TestMissionSpec,
)
from markettwin_execution_orchestrator.agents.schemas.persona import (
    PersonaSpec,
)
from markettwin_execution_orchestrator.agents.schemas.plan import (
    MetaAgentPlan,
)
from markettwin_execution_orchestrator.persistence.plan_repository import (
    PlanRepository,
)


@pytest.mark.asyncio
async def test_plan_repository_flushes_parents_before_journeys() -> None:
    """Persona and mission parents must exist before Journey rows."""

    session = MagicMock(spec=AsyncSession)

    session.get = AsyncMock(return_value=object())
    session.scalar = AsyncMock(
        side_effect=[
            None,
            None,
            None,
        ]
    )
    session.flush = AsyncMock()

    plan = MetaAgentPlan(
        mission_summary="Verify the target.",
        personas=(
            PersonaSpec(
                persona_id="persona_one",
                name="Persona One",
                perspective="First perspective.",
                behavior_traits=("careful",),
                priorities=("clarity",),
            ),
            PersonaSpec(
                persona_id="persona_two",
                name="Persona Two",
                perspective="Second perspective.",
                behavior_traits=("direct",),
                priorities=("speed",),
            ),
            PersonaSpec(
                persona_id="persona_three",
                name="Persona Three",
                perspective="Third perspective.",
                behavior_traits=("methodical",),
                priorities=("accuracy",),
            ),
        ),
        missions=(
            TestMissionSpec(
                mission_id="mission_one",
                name="Verify target",
                objective="Verify the target is accessible.",
                success_criteria=("Target is accessible.",),
                priority="high",
            ),
        ),
    )

    repository = PlanRepository(session)

    result = await repository.create_from_plan(
        test_run_id=uuid4(),
        plan=plan,
    )

    assert len(result.personas) == 3
    assert len(result.missions) == 1
    assert len(result.journeys) == 3

    assert session.add_all.call_count == 2
    assert session.flush.await_count == 2

    first_batch = session.add_all.call_args_list[0].args[0]
    second_batch = session.add_all.call_args_list[1].args[0]

    assert len(first_batch) == 4
    assert all(
        isinstance(row, (RunPersona, RunMission))
        for row in first_batch
    )
    assert not any(
        isinstance(row, PersonaJourney)
        for row in first_batch
    )

    assert len(second_batch) == 3
    assert all(
        isinstance(row, PersonaJourney)
        for row in second_batch
    )