import pytest
from google.adk.agents import LlmAgent
from markettwin_execution_orchestrator.agents.registry.agent_registry import (
    AgentRegistry,
    AgentRole,
)


def test_registry_registers_and_returns_builder() -> None:
    registry = AgentRegistry()

    def builder() -> LlmAgent:
        raise NotImplementedError

    registry.register(
        AgentRole.META,
        builder,
    )

    assert registry.get(AgentRole.META) is builder


def test_registry_rejects_duplicate_role() -> None:
    registry = AgentRegistry()

    def builder() -> LlmAgent:
        raise NotImplementedError

    registry.register(
        AgentRole.META,
        builder,
    )

    with pytest.raises(
        ValueError,
        match="already registered",
    ):
        registry.register(
            AgentRole.META,
            builder,
        )


def test_registry_rejects_unknown_role() -> None:
    registry = AgentRegistry()

    with pytest.raises(
        KeyError,
        match="No agent builder registered",
    ):
        registry.get(AgentRole.ANALYZER)
