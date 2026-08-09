"""Factory for MarketTwin persona journey runtimes."""

from dataclasses import dataclass

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from markettwin_execution_orchestrator.agents.registry.agent_registry import (
    AgentRegistry,
    AgentRole,
    create_default_agent_registry,
)
from markettwin_execution_orchestrator.agents.schemas.journey import (
    PersonaJourneySpec,
)
from markettwin_execution_orchestrator.mcp.playwright import (
    create_playwright_toolset,
)


@dataclass(frozen=True, slots=True)
class PersonaJourneyRuntime:
    """Resources owned by one MarketTwin persona journey."""

    journey: PersonaJourneySpec
    agent: LlmAgent
    playwright_toolset: McpToolset


class MetaAgentFactory:
    """Build executable runtime agents from structured journey specs."""

    def __init__(
        self,
        registry: AgentRegistry | None = None,
    ) -> None:
        self._registry = (
            registry
            if registry is not None
            else create_default_agent_registry()
        )

    def create_persona_runtime(
        self,
        journey: PersonaJourneySpec,
    ) -> PersonaJourneyRuntime:
        """Create one journey with its own isolated browser/MCP session."""

        playwright_toolset = create_playwright_toolset()

        builder = self._registry.get(
            AgentRole.PERSONA_BROWSER,
        )

        agent = builder(
            journey=journey,
            playwright_toolset=playwright_toolset,
        )

        return PersonaJourneyRuntime(
            journey=journey,
            agent=agent,
            playwright_toolset=playwright_toolset,
        )