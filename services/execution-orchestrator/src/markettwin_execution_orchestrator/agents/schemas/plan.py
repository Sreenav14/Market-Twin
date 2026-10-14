""" Structured Meta Agent Plan for MarketTwin."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

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

    @model_validator(mode="after")
    def unique_assignments(self) -> Self:
        for label, values in (
            ("persona IDs", [persona.persona_id for persona in self.personas]),
            ("mission IDs", [mission.mission_id for mission in self.missions]),
        ):
            normalized = [" ".join(value.split()).casefold() for value in values]
            if len(set(normalized)) != len(normalized):
                raise ValueError(f"The plan must have distinct {label}.")
        return self
    
