"""LLM model configuration for the MarketTwin execution orchestrator."""

import os
from typing import Final

from google.adk.models.lite_llm import LiteLlm

DEFAULT_MODEL_PROVIDER: Final[str] = "openai"
DEFAULT_OPENAI_MODEL_NAME: Final[str] = "openai/gpt-4o-mini"
DEFAULT_OLLAMA_MODEL_NAME: Final[str] = "ollama_chat/qwen3:1.7b"
DEFAULT_OLLAMA_API_BASE: Final[str] = "http://localhost:11434"
DEFAULT_OLLAMA_NUM_CTX: Final[int] = 8_192
DEFAULT_MAX_TOKENS: Final[int] = 256


def create_model(
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> LiteLlm:
    """Create the configured LLM used by MarketTwin agents."""

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

        api_key = (
            os.getenv("MODEL_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )

        if api_key:
            return LiteLlm(
                model=model_name,
                api_key=api_key,
                max_tokens=max_tokens,
            )

        return LiteLlm(
            model=model_name,
            max_tokens=max_tokens,
        )

    if provider == "ollama":
        model_name = os.getenv(
            "OLLAMA_MODEL_NAME",
            os.getenv("MODEL_NAME", DEFAULT_OLLAMA_MODEL_NAME),
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

        return LiteLlm(
            model=model_name,
            api_base=api_base,
            max_tokens=max_tokens,
            num_ctx=num_ctx,
            reasoning_effort="none",
        )

    raise ValueError(
        f'Unsupported MODEL_PROVIDER: "{provider}".'
    )
