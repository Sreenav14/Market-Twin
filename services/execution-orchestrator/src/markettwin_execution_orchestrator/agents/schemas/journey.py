"""Persona journey execution contracts"""

from pydantic import BaseModel, ConfigDict, Field

from markettwin_execution_orchestrator.agents.schemas.mission import (
    TestMissionSpec,
)
from markettwin_execution_orchestrator.agents.schemas.persona import (
    PersonaSpec,
)


class PersonaJourneySpec(BaseModel):
    """One persona executing one bounded mission."""
    
    model_config = ConfigDict(
        extra = "forbid",
        frozen = True,
    )
    
    journey_key: str = Field(
        min_length = 3,
        max_length = 64,
        pattern = r"[a-z][a-z0-9]*$"
    )
    
    persona: PersonaSpec 
    mission: TestMissionSpec