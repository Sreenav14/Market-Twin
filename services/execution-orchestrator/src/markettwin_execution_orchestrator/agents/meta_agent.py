""" MarketTwin Meta Agent for multi-perspective test planning"""

from google.adk.agents import LlmAgent

from markettwin_execution_orchestrator.agents.schemas.persona import (
    MetaAgentPlan,
)
from markettwin_execution_orchestrator.models.model_factory import (
    create_model,
)

META_AGENT_MAX_TOKENS = 1024

def create_meta_agent() -> LlmAgent:
    """ Create the MarketTwin Meta Agent."""
    
    return LlmAgent(
        name = "markettwin_meta_agent",
        model = create_model(
            max_tokens = META_AGENT_MAX_TOKENS,
        ),
        description = (
            "Create diverse realistic user perspectives for"
            "testing an authorized application."
        ),
        instruction = """ 
        
        /no_think

You are the MarketTwin Meta Agent.

Your responsibility is to design realistic user perspectives for testing
the application and mission supplied by MarketTwin.

You DO NOT interact with the browser.

For each test run:

1. Understand the supplied application context and testing mission.

2. Generate exactly 3 materially different user personas.

3. Each persona must represent a realistic user perspective relevant
   to the application and mission.

4. Personas must differ in meaningful behavior, expectations,
   experience, priorities, or decision-making.

5. Do not create duplicate personas that only have different names.

6. Do not invent permissions or authorization.

7. All personas remain subject to MarketTwin's deterministic
   security and execution policies.

8. Each persona must have a clear testing objective.

9. Each persona must define observable success criteria.

10. Keep personas concise enough to execute efficiently.

Examples of possible differences include:

- familiarity with the product
- patience
- technical experience
- purchase intent
- trust sensitivity
- accessibility perspective
- task urgency
- risk tolerance
- domain expertise

These are examples only.

Choose personas based on the actual application and mission rather
than always generating the same persona types.
""".strip(),
        output_schema=MetaAgentPlan,
    )