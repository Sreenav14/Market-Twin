"""Shared knowledge-domain contracts for MarketTwin."""

from typing import Annotated, Literal

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

    evidence_ordinals: tuple[Annotated[int, Field(gt=0, strict=True)], ...] = Field(
        min_length=1,
    )

    grounding_confidence: Literal[
        "low",
        "medium",
        "high",
    ]

    warnings: tuple[str, ...] = ()


class ApplicationKnowledgeDraft(BaseModel):
    """Grounded product context that is useful but not necessarily testable as a Skill."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=4000)
    evidence_ordinals: tuple[Annotated[int, Field(gt=0, strict=True)], ...] = Field(
        min_length=1,
    )
    grounding_confidence: Literal["low", "medium", "high"]
    warnings: tuple[str, ...] = ()


class ProcedureArtifactDraft(BaseModel):
    """Grounded procedure or structured operational artifact proposed for review."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    kind: Literal["procedure", "artifact"]
    content: str = Field(min_length=1, max_length=4000)
    steps: tuple[str, ...] = ()
    evidence_ordinals: tuple[Annotated[int, Field(gt=0, strict=True)], ...] = Field(
        min_length=1,
    )
    grounding_confidence: Literal["low", "medium", "high"]
    warnings: tuple[str, ...] = ()


class KnowledgeBuildResult(BaseModel):
    """One grounded semantic result from one source or consolidated source batches."""

    model_config = ConfigDict(extra="forbid")

    application_knowledge: tuple[ApplicationKnowledgeDraft, ...]
    artifacts: tuple[ProcedureArtifactDraft, ...]
    skills: tuple[GeneratedSkillDraft, ...]
