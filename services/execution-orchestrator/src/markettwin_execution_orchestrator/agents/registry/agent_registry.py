""" Registry of agent types supported by MarketTwin"""

from collections.abc import Callable
from enum import StrEnum

from google.adk.agents import LlmAgent


class AgentRole(StrEnum):
    """ Stable MarketTwin agent roles."""
    
    META = "meta"
    PERSONA_BROWSER = "persona_browser"
    ANALYZER = "analyzer"
    REPORTER = "reporter"
    
AgentBuilder = Callable[..., LlmAgent]
    
class AgentRegistry:
    """ Register agent builders by role."""
    
    def __init__(self) -> None:
        self._builders: dict[AgentRole, AgentBuilder] = {}
        
    def register(
        self,
        role: AgentRole,
        builder: AgentBuilder,
    ) -> None:
        """ Register one builder for an agent role."""
        
        if role in self._builders:
            raise ValueError(f"Agent role already registered: {role}")\
                
        self._builders[role] = builder
        
    def get(
        self,
        role: AgentRole,
    ) -> AgentBuilder:
        """ Return the registered builder for an agent role."""
        try: 
            return self._builders[role]
        except KeyError as exc:
            raise KeyError(
                f"No agent builder registered for role: {role}"
            ) from exc
            
        
    def contains(
        self,
        role: AgentRole,
    ) -> bool:
        """ Return whether a role has a registered builder."""
        
        return role in self._builders
    

def create_default_agent_registry() -> AgentRegistry:
    """ Create the default agent registry."""
    from markettwin_execution_orchestrator.agents.meta_agent import (
        create_meta_agent,
    )
    from markettwin_execution_orchestrator.agents.persona_agents import (
        create_persona_agent,
    )
    
    registry = AgentRegistry()
    
    registry.register(
        AgentRole.META,
        create_meta_agent,
    )
    
    registry.register(
        AgentRole.PERSONA_BROWSER,
        create_persona_agent,
    )
    
    return registry