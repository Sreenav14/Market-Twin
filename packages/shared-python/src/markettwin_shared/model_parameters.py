"""Provider parameters shared by direct calls and the agent model adapter."""

import os
from typing import TypedDict


class CompletionParameters(TypedDict, total=False):
    max_completion_tokens: int
    max_tokens: int
    reasoning_effort: str
    allowed_openai_params: list[str]
    temperature: float


def completion_parameters(
    model: str, max_tokens: int, *, temperature: float | None = None,
) -> CompletionParameters:
    """Use the modern OpenAI token limit and explicitly configured reasoning effort."""
    parameters: CompletionParameters = {}
    if model.startswith("openai/"):
        parameters["max_completion_tokens"] = max_tokens
        effort = (os.getenv("MODEL_REASONING_EFFORT") or "").strip()
        if effort:
            parameters["reasoning_effort"] = effort
            # Forward documented parameters even when LiteLLM's model registry is older.
            parameters["allowed_openai_params"] = ["reasoning_effort"]
        if temperature is not None and (not effort or effort == "none"):
            parameters["temperature"] = temperature
    else:
        parameters["max_tokens"] = max_tokens
        if temperature is not None:
            parameters["temperature"] = temperature
    return parameters
