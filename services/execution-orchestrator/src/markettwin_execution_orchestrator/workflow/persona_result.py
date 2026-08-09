"""Execution results for one MarketTwin persona journey."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from markettwin_execution_orchestrator.agents.schemas.journey import (
    PersonaJourneySpec,
)


class JourneyExecutionStatus(StrEnum):
    """Infrastructure lifecycle for a persona journey."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    POLICY_BLOCKED = "policy_blocked"


class JourneyOutcome(StrEnum):
    """Observed product outcome for the simulated user."""

    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    INCONCLUSIVE = "inconclusive"


class PersonaJourneyResult(BaseModel):
    """Structured result for one persona/mission execution."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    journey: PersonaJourneySpec

    status: JourneyExecutionStatus
    outcome: JourneyOutcome | None = None

    summary: str | None = Field(
        default=None,
        max_length=2_000,
    )

    actions: tuple[str, ...] = ()
    observations: tuple[str, ...] = ()
    friction_points: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    satisfied_criteria: tuple[str, ...] = ()
    unsatisfied_criteria: tuple[str, ...] = ()

    final_url: str | None = None