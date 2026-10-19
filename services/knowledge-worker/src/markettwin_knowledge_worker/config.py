"""Character limits and model-call settings for V1 knowledge ingestion."""

import os
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator


class KnowledgeWorkerSettings(BaseModel):
    app_env: Literal["local", "development", "test", "production"] = "local"
    knowledge_internal_secret: SecretStr | None = None
    preview_max_concurrency: int = Field(default=2, ge=1, le=16)
    preview_timeout_seconds: float = Field(default=600, gt=0, le=1800)

    @model_validator(mode="after")
    def validate_internal_secret(self) -> "KnowledgeWorkerSettings":
        secret = self.knowledge_internal_secret
        if secret is not None and len(secret.get_secret_value().strip()) < 32:
            raise ValueError("KNOWLEDGE_INTERNAL_SECRET must contain at least 32 characters.")
        if secret is None and self.app_env not in {"local", "test"}:
            raise ValueError("KNOWLEDGE_INTERNAL_SECRET is required outside local/test.")
        return self

    @classmethod
    def from_env(cls) -> "KnowledgeWorkerSettings":
        return cls.model_validate({
            "app_env": os.getenv("APP_ENV", "local"),
            "knowledge_internal_secret": os.getenv("KNOWLEDGE_INTERNAL_SECRET"),
            "preview_max_concurrency": os.getenv("KNOWLEDGE_PREVIEW_MAX_CONCURRENCY", "2"),
            "preview_timeout_seconds": os.getenv("KNOWLEDGE_PREVIEW_TIMEOUT_SECONDS", "600"),
        })


class KnowledgeConfigurationError(ValueError):
    """An ingestion setting is invalid."""

    code = "configuration_error"


@dataclass(frozen=True, slots=True)
class KnowledgeConfig:
    source_chunk_max_chars: int = 24000
    skill_batch_max_chars: int = 64000
    model_timeout_seconds: float = 180
    model_num_retries: int = 0
    model_max_output_tokens: int = 16384

    def __post_init__(self) -> None:
        if self.model_max_output_tokens < 1:
            raise KnowledgeConfigurationError("Model output limit must be positive.")
        if not 0 < self.source_chunk_max_chars < self.skill_batch_max_chars:
            raise KnowledgeConfigurationError(
                "Source chunk limit must be positive and smaller than Skill batch limit."
            )
        if self.model_timeout_seconds <= 0 or self.model_num_retries < 0:
            raise KnowledgeConfigurationError(
                "Model timeout must be positive and retries nonnegative."
            )

    @classmethod
    def from_env(cls) -> "KnowledgeConfig":
        try:
            return cls(
                source_chunk_max_chars=int(os.getenv("KNOWLEDGE_SOURCE_CHUNK_MAX_CHARS", "24000")),
                skill_batch_max_chars=int(os.getenv("KNOWLEDGE_SKILL_BATCH_MAX_CHARS", "64000")),
                model_timeout_seconds=float(os.getenv("KNOWLEDGE_MODEL_TIMEOUT_SECONDS", "180")),
                model_num_retries=int(os.getenv("KNOWLEDGE_MODEL_NUM_RETRIES", "0")),
                model_max_output_tokens=int(
                    os.getenv("KNOWLEDGE_MODEL_MAX_OUTPUT_TOKENS", "16384")
                ),
            )
        except ValueError as exc:
            raise KnowledgeConfigurationError(str(exc)) from exc
