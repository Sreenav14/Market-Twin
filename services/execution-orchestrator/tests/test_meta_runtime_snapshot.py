from google.adk.agents import LlmAgent
from markettwin_execution_orchestrator.agents.meta_agent import (
    META_AGENT_MAX_TOKENS,
    build_meta_runtime_snapshot_payload,
)
from pytest import MonkeyPatch


def test_build_meta_runtime_snapshot_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MODEL_PROVIDER",
        "openai",
    )
    monkeypatch.setenv(
        "MODEL_NAME",
        "gpt-4o-mini",
    )
    monkeypatch.setenv(
        "MODEL_API_KEY",
        "must-not-appear",
    )

    agent = LlmAgent(
        name="markettwin_meta_agent",
        model="openai/gpt-4o-mini",
        instruction="Create a bounded MarketTwin plan.",
    )

    runtime_prompt = (
        "Create the MarketTwin testing plan."
    )

    payload = build_meta_runtime_snapshot_payload(
        agent=agent,
        runtime_prompt=runtime_prompt,
    )

    assert payload.agent_role == "meta"
    assert payload.runtime_kind == "google_adk"

    assert (
        payload.runtime_agent_name
        == "markettwin_meta_agent"
    )

    assert payload.model_provider == "openai"

    assert (
        payload.model_name
        == "openai/gpt-4o-mini"
    )

    assert payload.model_configuration == {
        "max_tokens": META_AGENT_MAX_TOKENS,
        "num_retries": 2,
    }

    assert payload.effective_instruction == (
        "Create a bounded MarketTwin plan."
    )

    assert payload.runtime_prompt == runtime_prompt

    assert payload.persona_snapshot is None
    assert payload.mission_snapshot is None

    assert payload.tools == ()

    assert payload.metadata == {
        "output_schema": "MetaAgentPlan",
    }

    assert "must-not-appear" not in (
        payload.canonical_json()
    )