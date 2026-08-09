""" Structured persona contracts for MArketTwin multi-perspective testing"""

from pydantic import BaseModel, ConfigDict, Field


class PersonaSpec(BaseModel):
    """ Specification for one simulated MarketTwin user perspective""" 
    
    model_config = ConfigDict(
        extra = "forbid",
        frozen = True,
    )
    
    persona_id: str = Field(
        min_length = 3,
        max_length = 64,
        pattern = r"[a-z][a-z0-9]*$"
    )
    
    name: str = Field(
        min_length = 1,
        max_length = 80,
    )
    
    perspective: str = Field(
        min_length = 1,
        max_length = 500,
    )
        
    behavior_traits: tuple[str,...] = Field(
        min_length = 1,
        max_length = 6,
    )
    
    priorities: tuple[str,...] = Field(
        min_length = 1,
        max_length = 6,
    )
    
    
class MetaAgentPlan(BaseModel):
    """ Structured testing plan produced by the MarketTwin Meta Agent"""
    
    model_config = ConfigDict(
        extra = "forbid",
        frozen = True,
    )
    
    mission_summary: str = Field(
        min_length=1,
        max_length=500,
    )
    
    personas: tuple[PersonaSpec, ...] = Field(
        min_length = 2,
        max_length = 5,
    )