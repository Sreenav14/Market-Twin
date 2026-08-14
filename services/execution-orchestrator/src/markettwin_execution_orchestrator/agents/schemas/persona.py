"""Structured persona contracts for MarketTwin user simulation."""

from pydantic import BaseModel, ConfigDict, Field


class PersonaSpec(BaseModel):
    """One simulated MarketTwin user perspective."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    persona_id: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    name: str = Field(
        min_length=1,
        max_length=80,
    )

    perspective: str = Field(
        min_length=1,
        max_length=500,
    )

    behavior_traits: tuple[str, ...] = Field(
        min_length=1,
        max_length=6,
    )

    priorities: tuple[str, ...] = Field(
        min_length=1,
        max_length=6,
    )