""" structured final report returned by one MarketTwin Persona Agent."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

JourneyReportedOutcome = Literal[
    "passed",
    "failed",
    "partial",
    "inconclusive",
]

class CriterionEvidence(BaseModel):
    """Evidence reference for one mission success criterion."""
    
    model_config = ConfigDict(
        extra = "forbid",
        frozen = True,
    )
    
    criterion: str = Field(
        min_length = 1,
        max_length = 1_000,
    )
    
    status: Literal[
        "satisfied",
        "unsatisfied",
        "unverified",
    ]
    
    evidence_step_ids: tuple[int, ...] = ()

class PersonaAgentReport(BaseModel):
    """Model-produced observations for one completed Persona Journey."""
    
    model_config = ConfigDict(
        extra = "forbid",
        frozen = True,
    )
    criterion_evidence: tuple[CriterionEvidence, ...] = ()
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