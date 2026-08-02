"""LLM model configuration for the MarketTwin execution orchestrator."""

import os
from typing import Final

from google.adk.models.lite_llm import LiteLlm

DEFAULT_OLLAMA_MODEL_NAME: Final[str] = "ollama_chat/qwen3:1.7b"
DEFAULT_OLLAMA_API_BASE: Final[str] = "http://localhost:11434"
DEFAULT_OLLAMA_NUM_CTX: Final[int] = 8_192
DEFAULT_MAX_TOKENS: Final[int] = 256


def create_model() -> LiteLlm:
    """Create the local Ollama-backed LLM used by MarketTwin agents."""

    model_name = os.getenv("OLLAMA_MODEL_NAME", DEFAULT_OLLAMA_MODEL_NAME)
    api_base = os.getenv("OLLAMA_API_BASE", DEFAULT_OLLAMA_API_BASE)
    num_ctx = int(os.getenv("MARKETTWIN_OLLAMA_NUM_CTX", DEFAULT_OLLAMA_NUM_CTX))

    return LiteLlm(
        model=model_name,
        api_base=api_base,
        max_tokens=DEFAULT_MAX_TOKENS,
        num_ctx=num_ctx,
        reasoning_effort="none",
    )
