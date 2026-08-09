""" Structured Meta Agent Plan for MarketTwin."""

from pydantic import BaseModel, ConfigDict, Field

from markettwin_execution_orchestrator.agents.schemas.mission import (
    TestMissionSpec,
)
from markettwin_execution_orchestrator.agents.schemas.persona import (
    PersonaSpec,
)


class MetaAgentPlan(BaseModel):
    """ Structured testing plan produced by the MarketTwin Meta Agent."""
    
    model_config = ConfigDict(
        extra = "forbid",
        frozen = True,
    )
    
    mission_summary: str = Field(
        min_length = 1,
        max_length = 500,
    )
    
    personas: tuple[PersonaSpec,...] = Field(
        min_length = 3,
        max_length = 3,
    )
    
    missions: tuple[TestMissionSpec,...] = Field(
        min_length = 1,
        max_length = 4,
    )
    