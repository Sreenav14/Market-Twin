"""Tests for provider-neutral observability contracts."""

from types import SimpleNamespace

from markettwin_shared.observability import (
    AgentRuntimeSnapshotSpec,
    ModelTokenUsage,
    model_token_usage_from_adk,
    model_token_usage_from_litellm,
)


def test_adk_usage_normalizes_complete_metadata() -> None:
    metadata = SimpleNamespace(
        prompt_token_count=1200,
        cached_content_token_count=800,
        candidates_token_count=240,
        thoughts_token_count=30,
        tool_use_prompt_token_count=150,
        total_token_count=1620,
    )

    usage = model_token_usage_from_adk(metadata)

    assert usage is not None
    assert usage == ModelTokenUsage(
        input_tokens=1200,
        cached_input_tokens=800,
        output_tokens=240,
        reasoning_tokens=30,
        tool_input_tokens=150,
        total_tokens=1620,
    )
    assert usage.status == "reported"


def test_usage_preserves_unknown_and_explicit_zero() -> None:
    metadata = SimpleNamespace(
        prompt_token_count=0,
        total_token_count=0,
    )

    usage = model_token_usage_from_adk(metadata)

    assert usage is not None
    assert usage.input_tokens == 0
    assert usage.output_tokens is None
    assert usage.total_tokens == 0
    assert usage.status == "partial"


def test_litellm_usage_reads_nested_cached_and_reasoning_tokens() -> None:
    response = {
        "usage": {
            "prompt_tokens": 900,
            "completion_tokens": 100,
            "total_tokens": 1000,
            "prompt_tokens_details": {
                "cached_tokens": 600,
            },
            "completion_tokens_details": {
                "reasoning_tokens": 20,
            },
        }
    }

    assert model_token_usage_from_litellm(response) == ModelTokenUsage(
        input_tokens=900,
        cached_input_tokens=600,
        output_tokens=100,
        reasoning_tokens=20,
        total_tokens=1000,
    )


def test_missing_usage_is_not_fabricated() -> None:
    assert model_token_usage_from_adk(None) is None
    assert model_token_usage_from_litellm(object()) is None


def test_snapshot_hash_is_stable_and_semantic() -> None:
    first = AgentRuntimeSnapshotSpec(
        test_run_id="11111111-1111-1111-1111-111111111111",
        agent_role="meta",
        runtime_agent_name="markettwin_meta_agent",
        runtime_kind="google_adk",
        agent_version="1",
        snapshot_schema_version=1,
        model_provider="openai",
        model_name="openai/gpt-4o-mini",
        model_configuration={"max_tokens": 1024},
        base_instruction="Plan the study.",
        effective_instruction="Plan the study.",
        runtime_prompt="Create a plan.",
    )
    same = AgentRuntimeSnapshotSpec(
        test_run_id="22222222-2222-2222-2222-222222222222",
        agent_role="meta",
        runtime_agent_name="markettwin_meta_agent",
        runtime_kind="google_adk",
        agent_version="1",
        snapshot_schema_version=1,
        model_provider="openai",
        model_name="openai/gpt-4o-mini",
        model_configuration={"max_tokens": 1024},
        base_instruction="Plan the study.",
        effective_instruction="Plan the study.",
        runtime_prompt="Create a plan.",
    )
    changed = AgentRuntimeSnapshotSpec(
        test_run_id=first.test_run_id,
        agent_role="meta",
        runtime_agent_name="markettwin_meta_agent",
        runtime_kind="google_adk",
        agent_version="1",
        snapshot_schema_version=1,
        model_provider="openai",
        model_name="openai/gpt-4o-mini",
        model_configuration={"max_tokens": 1024},
        base_instruction="Plan the study.",
        effective_instruction="Plan the study carefully.",
        runtime_prompt="Create a plan.",
    )

    # Run IDs are relational scope and intentionally excluded from the
    # semantic configuration hash.
    assert first.snapshot_sha256 == same.snapshot_sha256
    assert first.snapshot_sha256 != changed.snapshot_sha256
