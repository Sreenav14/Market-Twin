""" Factory for MarketTwin persona-agent runtimes."""

from dataclasses import dataclass

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from markettwin_execution_orchestrator.agents.persona_agents import (
    create_persona_agent,
)
from markettwin_execution_orchestrator.agents.registry.agent_registry import (
    AgentRegistry,
    create_default_agent_registry,
)
from markettwin_execution_orchestrator.agents.schemas.persona import PersonaSpec
from markettwin_execution_orchestrator.mcp.playwright import (
    create_playwright_toolset,
)


@dataclass(frozen=True, slots=True)
class PersonaAgentRuntime:
    """ Resources owned by one simulated MarketTwin persona."""
    
    persona: PersonaSpec
    agent: LlmAgent
    playwright_toolset: McpToolset
    
    
class MetaAgentFactory:
    """ Build executable agents from Meta Agent Persona specifications."""
    
    def __init__(
        self,
        registry: AgentRegistry | None = None,
    ) -> None:
        self._registry = (
            registry
            if registry is not None
            else create_default_agent_registry()
        )
        self._registry = registry
    
    def create_persona_runtime(
        self,
        persona: PersonaSpec,
    ) -> PersonaAgentRuntime:
        """ Create one persona with its own isloated browser/MCP session."""
        
        playwright_toolset = create_playwright_toolset()
        
        agent = create_persona_agent(
            persona = persona,
            playwright_toolset = playwright_toolset,
        )
        
        return PersonaAgentRuntime(
            persona = persona,
            agent = agent,
            playwright_toolset = playwright_toolset,
        )
        
    