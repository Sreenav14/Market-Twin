"""Structured test mission contracts for MarketTwin."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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