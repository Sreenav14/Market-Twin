""" Execution results for one MarketTwin persona journey."""

from enum import StrEnum

from pydantic import BaseModel,ConfigDict,Field

from markettwin_execution_orchestrator.agents.schemas.persona import (
    PersonaSpec,
)

class PersonaJourneyStatus(StrEnum):
    """Execution status for one simulated user journey."""

    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    TIMED_OUT = "timed_out"
    ERROR = "error"
    
    
class PersonaJourneyResult(BaseModel):
    """ Execution status for one simulated user journey."""
    
    model_config = ConfigDict(
        extra = "forbid",
        frozen = True,
    )
    
    persona: PersonaSpec
    status: PersonaJourneyStatus
    
    summary: str = Field(
        min_length = 1,
        max_length = 2_000,
    )
    
    actions: tuple[str,...] = ()
    observations: tuple[str,...]= ()
    friction_points: tuple[str,...] =()
    blocker: tuple[str,...] =()
    satisfied_criteria: tuple[str,...] =()
    unsatisfied_criteria: tuple[str,...] =()
    
    
    final_url: str | None = None