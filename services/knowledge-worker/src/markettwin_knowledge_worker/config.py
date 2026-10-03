"""Character limits and model-call settings for V1 knowledge ingestion."""

import os
from dataclasses import dataclass


class KnowledgeConfigurationError(ValueError):
    """An ingestion setting is invalid."""

    code = "configuration_error"


@dataclass(frozen=True, slots=True)
class KnowledgeConfig:
    source_chunk_max_chars: int = 24000
    skill_batch_max_chars: int = 64000
    model_timeout_seconds: float = 180
    model_num_retries: int = 0

    def __post_init__(self) -> None:
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
            )
        except ValueError as exc:
            raise KnowledgeConfigurationError(str(exc)) from exc
