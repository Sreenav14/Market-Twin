"""Structured test mission contracts for MarketTwin."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MissionPriority = Literal["low", "medium", "high"]


class TestMissionSpec(BaseModel):
    """One bounded task that MarketTwin will execute."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    mission_id: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    name: str = Field(
        min_length=1,
        max_length=100,
    )

    objective: str = Field(
        min_length=1,
        max_length=500,
    )

    success_criteria: tuple[str, ...] = Field(
        min_length=1,
        max_length=8,
    )

    priority: MissionPriority = "medium"

    @field_validator("success_criteria")
    @classmethod
    def distinct_observable_criteria(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = [" ".join(criterion.split()).casefold() for criterion in value]
        if any(not criterion for criterion in normalized) or len(set(normalized)) != len(value):
            raise ValueError("Success criteria must be nonblank and distinct.")
        return value
