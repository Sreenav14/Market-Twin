"""Configuration must change the real tree while retaining controlled tools."""

import json

import pytest
from google.adk.agents import LlmAgent, SequentialAgent
from markettwin_shared.agent_configuration import default_configuration, validate_configuration
from markettwin_execution_orchestrator.agents import configuration


@pytest.mark.parametrize(
    "change",
    [
        {"name": "bad name"},
        {"temperature": 0.3},
        {"temperature": float("nan")},
        {"temperature": True},
        {"agent_type": "ParallelAgent"},
        {"tools": ["shell_exec"]},
        {"tools": ["browser_click", "browser_click"]},
        {"unknown": 1},
        {"sub_agents": [{**default_configuration("Agent_2"), "instruction": "Observe"}]},
    ],
)
def test_invalid_configuration_rejected(change):
    with pytest.raises(ValueError):
        validate_configuration({**default_configuration("Agent_1"), **change}, browser_allowed=True)


def test_planning_agent_cannot_gain_browser_access():
    with pytest.raises(ValueError):
        validate_configuration(
            default_configuration("Agent_1", ("browser_click",)), browser_allowed=False
        )


@pytest.mark.parametrize("name", ["Agent_1", "Agent_1_reporter"])
def test_sequential_names_cannot_collide(name):
    value = {
        **default_configuration("Agent_1"),
        "agent_type": "SequentialAgent",
        "sub_agents": [{**default_configuration(name), "instruction": "Observe"}],
    }
    with pytest.raises(ValueError, match="unique"):
        validate_configuration(value, browser_allowed=True)


def test_actual_sequential_children_order_tools_and_temperature(monkeypatch):
    calls = []
    monkeypatch.setattr(
        configuration, "create_model", lambda **kwargs: calls.append(kwargs) or "openai/example"
    )

    def browser_click():
        """Click a controlled target."""
        return "observed"

    def browser_get_state():
        """Observe the controlled browser."""
        return "state"

    primary = LlmAgent(
        name="original",
        model="openai/example",
        instruction="Never invent evidence.",
        tools=[browser_click, browser_get_state],
    )
    settings = {
        **default_configuration("Agent_4", ("browser_get_state",)),
        "agent_type": "SequentialAgent",
        "temperature": 0.02,
        "sub_agents": [
            {
                **default_configuration("Agent_4_sub_1", ("browser_click",)),
                "instruction": "Inspect navigation.",
            }
        ],
    }
    root, tree, reporter = configuration.configure_agent(
        primary,
        {"agent_configuration": json.dumps(settings)},
        name="Agent_4",
        max_tokens=2048,
        browser_allowed=True,
    )
    assert isinstance(root, SequentialAgent)
    assert [agent.name for agent in root.sub_agents] == ["Agent_4_sub_1", "Agent_4_reporter"]
    assert root.sub_agents[-1] is primary
    assert root.sub_agents[0].tools == [browser_click]
    assert primary.tools == [browser_get_state]
    assert "Never invent evidence" in root.sub_agents[0].instruction
    assert [child["name"] for child in tree["sub_agents"]] == [
        agent.name for agent in root.sub_agents
    ]
    assert calls == [
        {"max_tokens": 2048, "temperature": 0.05},
        {"max_tokens": 2048, "temperature": 0.02},
    ]
    assert reporter["model_configuration"]["requested_temperature"] == 0.02


def test_reasoning_temperature_recorded_as_requested_not_applied(monkeypatch):
    from markettwin_execution_orchestrator.models.model_factory import (
        resolve_model_runtime_configuration,
    )

    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("MODEL_NAME", "openai/gpt-5")
    monkeypatch.setenv("MODEL_REASONING_EFFORT", "low")
    parameters = resolve_model_runtime_configuration(temperature=0.05).snapshot_parameters()
    assert parameters["requested_temperature"] == 0.05
    assert parameters["temperature"] is None
