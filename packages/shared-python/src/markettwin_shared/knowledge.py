"""Shared knowledge-domain contracts for MarketTwin."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SkillDefinition(BaseModel):
    """Validated capability knowledge supplied to MarketTwin agents."""

    model_config = ConfigDict(extra="forbid")

    intent: str = Field(min_length=1, max_length=1000)

    preconditions: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    expected_outcomes: tuple[str, ...] = Field(
        min_length=1,
    )

    failure_signals: tuple[str, ...] = ()


class GeneratedSkillDraft(BaseModel):
    """Structured output produced by the V1 Skill Generator."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=255,
    )

    definition: SkillDefinition

    evidence_unit_ids: tuple[UUID, ...] = Field(
        min_length=1,
    )

    grounding_confidence: Literal[
        "low",
        "medium",
        "high",
    ]

    warnings: tuple[str, ...] = ()