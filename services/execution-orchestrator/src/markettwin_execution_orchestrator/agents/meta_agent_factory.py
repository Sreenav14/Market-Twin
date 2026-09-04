"""Factory for MarketTwin Persona Journey runtimes."""

from dataclasses import dataclass

from google.adk.agents import LlmAgent

from markettwin_execution_orchestrator.agents.registry.agent_registry import (
    AgentRegistry,
    AgentRole,
    create_default_agent_registry,
)
from markettwin_execution_orchestrator.agents.schemas.journey import PersonaJourneySpec
from markettwin_execution_orchestrator.browser import (
    BrowserController,
    BrowserSessionHandle,
    create_browser_tools,
)


@dataclass(frozen=True, slots=True)
class PersonaJourneyRuntime:
    """Agent resources bound to one already-created Journey browser session."""

    journey: PersonaJourneySpec
    agent: LlmAgent
    browser_session: BrowserSessionHandle


class MetaAgentFactory:
    """Build executable Persona Agents without creating a second browser path."""

    def __init__(
        self,
        registry: AgentRegistry | None = None,
    ) -> None:
        self._registry = (
            registry if registry is not None else create_default_agent_registry()
        )

    def create_persona_runtime(
        self,
        *,
        journey: PersonaJourneySpec,
        browser_controller: BrowserController,
        browser_session: BrowserSessionHandle,
    ) -> PersonaJourneyRuntime:
        """Bind one Persona Agent to one Python Playwright Journey session."""

        browser_tools = create_browser_tools(
            controller=browser_controller,
            handle=browser_session,
        )
        builder = self._registry.get(AgentRole.PERSONA_BROWSER)
        agent = builder(
            journey=journey,
            browser_tools=browser_tools,
        )

        return PersonaJourneyRuntime(
            journey=journey,
            agent=agent,
            browser_session=browser_session,
        )
