"""Tests for Agent Inspector usage and YAML presentation."""

from datetime import UTC, datetime
from uuid import uuid4

from markettwin_control_api.api.agents import _render_yaml
from markettwin_control_api.persistence.repositories.agent_observability_repository import (
    ModelInvocationRecord,
    summarize_usage,
)


def test_usage_summary_preserves_unknown_attempt_count() -> None:
    now = datetime.now(UTC)
    invocations = (
        ModelInvocationRecord(
            invocation_id=uuid4(),
            status="completed",
            usage_status="reported",
            invocation_sequence=1,
            attempt_number=1,
            model_provider="openai",
            model_name="openai/gpt-4o-mini",
            model_version=None,
            input_tokens=100,
            cached_input_tokens=50,
            output_tokens=20,
            reasoning_tokens=None,
            tool_input_tokens=None,
            provider_total_tokens=120,
            latency_ms=250,
            started_at=now,
            completed_at=now,
            error_code=None,
        ),
        ModelInvocationRecord(
            invocation_id=uuid4(),
            status="rate_limited",
            usage_status="unavailable",
            invocation_sequence=2,
            attempt_number=1,
            model_provider="openai",
            model_name="openai/gpt-4o-mini",
            model_version=None,
            input_tokens=None,
            cached_input_tokens=None,
            output_tokens=None,
            reasoning_tokens=None,
            tool_input_tokens=None,
            provider_total_tokens=None,
            latency_ms=80,
            started_at=now,
            completed_at=now,
            error_code="RateLimitError",
        ),
    )

    summary = summarize_usage(invocations)

    assert summary.attempts == 2
    assert summary.completed == 1
    assert summary.rate_limited == 1
    assert summary.unknown_usage_attempts == 1
    assert summary.input_tokens == 100
    assert summary.provider_total_tokens == 120
    assert summary.latency_ms == 330


def test_yaml_renderer_handles_multiline_prompt() -> None:
    rendered = _render_yaml(
        {
            "agent": {
                "role": "persona",
            },
            "tools": [
                "browser_get_state",
                "browser_click",
            ],
            "instructions": {
                "effective": "Line one\nLine two",
            },
        }
    )

    assert 'role: "persona"' in rendered
    assert '- "browser_click"' in rendered
    assert "effective: |" in rendered
    assert "  Line one" in rendered
    assert "  Line two" in rendered
