"""LLM model configuration for the MarketTwin execution orchestrator."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from google.adk.models.lite_llm import LiteLlm

DEFAULT_MODEL_PROVIDER: Final[str] = "openai"
DEFAULT_OPENAI_MODEL_NAME: Final[str] = "openai/gpt-4o-mini"
DEFAULT_OPENAI_NUM_RETRIES: Final[int] = 2
DEFAULT_OLLAMA_MODEL_NAME: Final[str] = "ollama_chat/qwen3:1.7b"
DEFAULT_OLLAMA_API_BASE: Final[str] = "http://localhost:11434"
DEFAULT_OLLAMA_NUM_CTX: Final[int] = 8_192
DEFAULT_MAX_TOKENS: Final[int] = 512


@dataclass(frozen=True, slots=True)
class ModelRuntimeConfig:
    """Safe, serializable model configuration used by one runtime."""

    provider: str
    model_name: str
    max_tokens: int
    num_retries: int | None = None
    api_base: str | None = None
    num_ctx: int | None = None
    reasoning_effort: str | None = None

    def snapshot(self) -> dict[str, object]:
        """Return safe model settings without credentials."""

        values: dict[str, object] = {
            "max_tokens": self.max_tokens,
        }

        if self.num_retries is not None:
            values["num_retries"] = self.num_retries
        if self.api_base is not None:
            values["api_base"] = self.api_base
        if self.num_ctx is not None:
            values["num_ctx"] = self.num_ctx
        if self.reasoning_effort is not None:
            values["reasoning_effort"] = self.reasoning_effort

        return values


def resolve_model_runtime_config(
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> ModelRuntimeConfig:
    """Resolve the current MarketTwin model configuration without secrets."""

    provider = os.getenv(
        "MODEL_PROVIDER",
        DEFAULT_MODEL_PROVIDER,
    ).strip().casefold() or DEFAULT_MODEL_PROVIDER

    if provider == "openai":
        model_name = (
            os.getenv("MODEL_NAME")
            or DEFAULT_OPENAI_MODEL_NAME
        ).strip()

        if not model_name.startswith("openai/"):
            model_name = f"openai/{model_name}"

        return ModelRuntimeConfig(
            provider="openai",
            model_name=model_name,
            max_tokens=max_tokens,
            num_retries=DEFAULT_OPENAI_NUM_RETRIES,
        )

    if provider == "ollama":
        model_name = os.getenv(
            "OLLAMA_MODEL_NAME",
            os.getenv(
                "MODEL_NAME",
                DEFAULT_OLLAMA_MODEL_NAME,
            ),
        )
        api_base = os.getenv(
            "OLLAMA_API_BASE",
            DEFAULT_OLLAMA_API_BASE,
        )
        num_ctx = int(
            os.getenv(
                "MARKETTWIN_OLLAMA_NUM_CTX",
                DEFAULT_OLLAMA_NUM_CTX,
            )
        )

        return ModelRuntimeConfig(
            provider="ollama",
            model_name=model_name,
            max_tokens=max_tokens,
            api_base=api_base,
            num_ctx=num_ctx,
            reasoning_effort="none",
        )

    raise ValueError(
        f'Unsupported MODEL_PROVIDER: "{provider}".'
    )


def create_model(
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> LiteLlm:
    """Create the configured LLM used by MarketTwin agents."""

    config = resolve_model_runtime_config(
        max_tokens=max_tokens,
    )

    if config.provider == "openai":
        api_key = (
            os.getenv("MODEL_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        retries = (
            config.num_retries
            if config.num_retries is not None
            else DEFAULT_OPENAI_NUM_RETRIES
        )

        if api_key:
            return LiteLlm(
                model=config.model_name,
                api_key=api_key,
                max_tokens=config.max_tokens,
                num_retries=retries,
            )

        return LiteLlm(
            model=config.model_name,
            max_tokens=config.max_tokens,
            num_retries=retries,
        )

    if config.provider == "ollama":
        return LiteLlm(
            model=config.model_name,
            api_base=config.api_base,
            max_tokens=config.max_tokens,
            num_ctx=config.num_ctx,
            reasoning_effort=config.reasoning_effort,
        )

    raise ValueError(
        f'Unsupported MODEL_PROVIDER: "{config.provider}".'
    )
