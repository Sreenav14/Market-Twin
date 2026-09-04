""" structured final report returned by one MarketTwin Persona Agent."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

JourneyReportedOutcome = Literal[
    "passed",
    "failed",
    "partial",
    "inconclusive",
]

class PersonaAgentReport(BaseModel):
    """Model-produced observations for one completed Persona Journey."""
    
    model_config = ConfigDict(
        extra = "forbid",
        frozen = True,
    )
    
    outcome: JourneyReportedOutcome 
    
    summary: str = Field(
        min_length = 1,
        max_length = 2_000,
    )
    
    actions : tuple[str,...] = ()
    observations: tuple[str,...] = ()
    friction_points: tuple[str,...] = ()
    blockers: tuple[str,...] = ()
    
    satisfied_criteria: tuple[str,...] = ()
    unsatisfied_criteria: tuple[str,...] = ()
    
    final_url: str | None = None