"""Deterministic expansion of a Meta Agent Plan into journeys."""

from markettwin_execution_orchestrator.agents.schemas.journey import (
    PersonaJourneySpec,
)
from markettwin_execution_orchestrator.agents.schemas.plan import (
    MetaAgentPlan,
)


def build_persona_journeys(
    plan: MetaAgentPlan,
) -> tuple[PersonaJourneySpec,...]:
    """ Create one journey for every persona/mission combination."""
    
    return tuple(
        PersonaJourneySpec(
            journey_key = (
                f"{persona.persona_id}__{mission.mission_id}"
            ),
            persona = persona,
            mission = mission,
        )
        for persona in plan.personas
        for mission in plan.missions
    )
    