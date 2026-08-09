"""Result contract for a MarketTwin multi-persona test run."""

from pydantic import BaseModel, ConfigDict

from markettwin_execution_orchestrator.agents.schemas.persona import (
    MetaAgentPlan,
)
from markettwin_execution_orchestrator.workflow.persona_result import (
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