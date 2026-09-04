"""Persona journey execution contracts."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from markettwin_execution_orchestrator.agents.schemas.mission import (
    TestMissionSpec,
)
from markettwin_execution_orchestrator.agents.schemas.persona import (
    PersonaSpec,
)


class PersonaJourneySpec(BaseModel):
    """One persona executing one bounded mission."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    journey_key: str = Field(
        min_length=3,
        max_length=140,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    persona: PersonaSpec
    mission: TestMissionSpec

    @model_validator(mode="after")
    def validate_journey_key(self) -> Self:
        """Require the deterministic persona/mission journey key."""

        expected_key = (
            f"{self.persona.persona_id}"
            f"__{self.mission.mission_id}"
        )

        if self.journey_key != expected_key:
            raise ValueError(
                "journey_key must equal "
                "'{persona_id}__{mission_id}'."
            )

        return self