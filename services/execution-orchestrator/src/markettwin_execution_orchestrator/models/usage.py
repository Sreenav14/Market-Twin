"""Provider-neutral model usage contracts for MarketTwin."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelTokenUsage:
    """Token usage reported for one model invocation."""

    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    tool_input_tokens: int | None = None
    total_tokens: int | None = None


def model_token_usage_from_adk(
    usage_metadata: object | None,
) -> ModelTokenUsage | None:
    """Convert ADK usage metadata into MarketTwin's provider-neutral contract."""

    if usage_metadata is None:
        return None

    return ModelTokenUsage(
        input_tokens=_optional_int(
            getattr(usage_metadata, "prompt_token_count", None)
        ),
        cached_input_tokens=_optional_int(
            getattr(usage_metadata, "cached_content_token_count", None)
        ),
        output_tokens=_optional_int(
            getattr(usage_metadata, "candidates_token_count", None)
        ),
        reasoning_tokens=_optional_int(
            getattr(usage_metadata, "thoughts_token_count", None)
        ),
        tool_input_tokens=_optional_int(
            getattr(usage_metadata, "tool_use_prompt_token_count", None)
        ),
        total_tokens=_optional_int(
            getattr(usage_metadata, "total_token_count", None)
        ),
    )


def _optional_int(value: object) -> int | None:
    """Return a non-negative integer usage value when the provider supplied one."""

    if type(value) is not int or value < 0:
        return None

    return value