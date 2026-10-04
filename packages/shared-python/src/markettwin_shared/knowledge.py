"""Shared knowledge-domain contracts for MarketTwin."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class SkillDefinition(BaseModel):
    """Validated capability knowledge supplied to MarketTwin agents."""

    model_config = ConfigDict(extra="forbid")

    intent: str = Field(min_length=1, max_length=1000)

    preconditions: tuple[str, ...] = Field(
        default=(), description="Only source-stated prerequisites. Empty when not established."
    )
    inputs: tuple[str, ...] = Field(
        default=(), description="Only source-stated inputs. Empty when not established."
    )
    constraints: tuple[str, ...] = Field(
        default=(), description="Only source-stated rules or limits. Empty when not established."
    )

    expected_outcomes: tuple[str, ...] = Field(
        min_length=1,
        description="Observable results explicitly established by the source for this capability.",
    )

    failure_signals: tuple[str, ...] = Field(
        default=(),
        description="Only failures stated or demonstrated in the source. Otherwise empty.",
    )


class GeneratedSkillDraft(BaseModel):
    """Structured output produced by the V1 Skill Generator."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=255,
    )

    definition: SkillDefinition = Field(
        description="A source-established actionable capability with an observable outcome. "
        "Component labels and architectural arrows alone are context, not a Skill."
    )

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
    content: str = Field(
        min_length=1,
        max_length=4000,
        description="Source-established facts and relationships only. A named component does not "
        "establish its conventional purpose. Merge overlapping summaries of the same concept.",
    )
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
    content: str = Field(
        min_length=1,
        max_length=4000,
        description="Reusable source-supported rules, transitions, or structure beyond a summary. "
        "Merely describing the existence of a diagram or document is not an artifact.",
    )
    steps: tuple[str, ...] = Field(
        default=(), description="Only an explicit source-established sequence; otherwise empty."
    )
    evidence_ordinals: tuple[Annotated[int, Field(gt=0, strict=True)], ...] = Field(
        min_length=1,
    )
    grounding_confidence: Literal["low", "medium", "high"]
    warnings: tuple[str, ...] = ()


class KnowledgeBuildResult(BaseModel):
    """One grounded semantic result from one source or consolidated source batches."""

    model_config = ConfigDict(extra="forbid")

    application_knowledge: tuple[ApplicationKnowledgeDraft, ...] = Field(
        description="The smallest useful set of distinct source-grounded context items. Merge "
        "overview/component summaries about the same concept. Empty if none is established."
    )
    artifacts: tuple[ProcedureArtifactDraft, ...] = Field(
        description="Only distinct reusable structure established by the source. Empty is normal. "
        "Do not create an artifact merely because the source is a diagram or a document."
    )
    skills: tuple[GeneratedSkillDraft, ...] = Field(
        description="Every source-established capability with actions, rules, "
        "and observable outcomes, including formal requirements. "
        "Empty only when no capability is established. "
        "Labels, components, and arrows alone do not establish a Skill."
    )
