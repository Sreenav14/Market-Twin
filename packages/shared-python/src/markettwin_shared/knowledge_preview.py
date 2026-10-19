"""Typed HTTP contract for a temporary knowledge preview."""

from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, field_validator

from markettwin_shared.knowledge import (
    ApplicationKnowledgeDraft,
    GeneratedSkillDraft,
    ProcedureArtifactDraft,
)


class KnowledgePreviewSourceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    source_item_count: int
    processed_item_count: int
    original_url: str | None = None

    @field_validator("original_url")
    @classmethod
    def validate_original_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlsplit(value)
            if (len(value) > 2048 or parsed.scheme not in {"http", "https"}
                    or not parsed.hostname or parsed.username or parsed.password):
                raise ValueError("Original source must be an HTTP(S) URL without credentials.")
        return value


class KnowledgePreviewEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordinal: int
    evidence_type: str
    content_text: str | None = None
    content_json: dict[str, object] | None = None
    source_locator: dict[str, object]
    extractor_name: str
    extractor_version: str


class KnowledgePreviewIssueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    source_locator: dict[str, object]
    requires_fallback: bool


class KnowledgePreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: KnowledgePreviewSourceResponse
    application_knowledge: tuple[ApplicationKnowledgeDraft, ...]
    artifacts: tuple[ProcedureArtifactDraft, ...]
    skills: tuple[GeneratedSkillDraft, ...]
    evidence: tuple[KnowledgePreviewEvidenceResponse, ...]
    extraction_issues: tuple[KnowledgePreviewIssueResponse, ...]
