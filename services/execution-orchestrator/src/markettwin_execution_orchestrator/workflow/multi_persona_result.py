"""Result contract for a MarketTwin multi-persona test run."""

from pydantic import BaseModel, ConfigDict

from markettwin_execution_orchestrator.agents.schemas.plan import (
    MetaAgentPlan,
)
from markettwin_execution_orchestrator.workflow.persona_result import (
    JourneyExecutionStatus,
    PersonaJourneyResult,
)


class MultiPersonaExecutionResult(BaseModel):
    """Result collected from all simulated users journeys."""
    
    model_config = ConfigDict(
        extra = "forbid",
        frozen = True,
    )
    
    plan: MetaAgentPlan
    journeys: tuple[PersonaJourneyResult,...]
    
    @property
    def completed_count(self) -> int:
        """Number of Journeys that completed infrastructure execution."""

        return sum(
            journey.status == JourneyExecutionStatus.COMPLETED
            for journey in self.journeys
        )


    @property
    def failed_count(self) -> int:
        """Number of Journeys that did not complete normally."""

        return len(self.journeys) - self.completed_count

    
    
