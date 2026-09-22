"""Tests for MarketTwin model-usage normalization."""

from types import SimpleNamespace

from markettwin_execution_orchestrator.models.usage import (
    ModelTokenUsage,
    model_token_usage_from_adk,
)


def test_model_token_usage_from_adk() -> None:
    metadata = SimpleNamespace(
        prompt_token_count=1_200,
        cached_content_token_count=800,
        candidates_token_count=240,
        thoughts_token_count=30,
        tool_use_prompt_token_count=150,
        total_token_count=1_620,
    )

    assert model_token_usage_from_adk(metadata) == ModelTokenUsage(
        input_tokens=1_200,
        cached_input_tokens=800,
        output_tokens=240,
        reasoning_tokens=30,
        tool_input_tokens=150,
        total_tokens=1_620,
    )


def test_model_token_usage_preserves_missing_values() -> None:
    metadata = SimpleNamespace(
        prompt_token_count=500,
        total_token_count=550,
    )

    assert model_token_usage_from_adk(metadata) == ModelTokenUsage(
        input_tokens=500,
        total_tokens=550,
    )


def test_model_token_usage_returns_none_without_metadata() -> None:
    assert model_token_usage_from_adk(None) is None