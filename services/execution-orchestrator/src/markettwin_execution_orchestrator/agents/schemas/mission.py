""" Structured test mission contracts for MarketTwin."""

from pydantic import BaseModel, ConfigDict, Field


class TestMissionSpec(BaseModel):
    """ One bounded task that MarketTwin will execute."""
    
    model_config = ConfigDict(
        extra = "forbid",
        frozen = True,
    )
    
    mission_id: str = Field(
        min_length = 3,
        max_length = 64,
        pattern = r"[a-z][a-z0-9]*$"
    )
    
    name: str = Field(
        min_length = 1,
        max_length = 100,
    )
    
    objective:str = Field(
        min_length = 1,
        max_length = 500,
    )
    
    success_criteria: tuple[str,...] = Field(
        min_length = 1,
        max_length = 8,
    )
    
    priority: int = Field(
        ge = 1,
        le = 5,
        default = 3,
    )