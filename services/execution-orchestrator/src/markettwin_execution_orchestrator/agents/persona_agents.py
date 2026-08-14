""" MarketTwin persona browser agent """

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from markettwin_execution_orchestrator.agents.schemas.journey import PersonaJourneySpec
from markettwin_execution_orchestrator.models.model_factory import create_model


def create_persona_agent(
    *,
    journey: PersonaJourneySpec,
    playwright_toolset: McpToolset,
) -> LlmAgent:
    """ Create one isolated MarkekTwin persona-testing agent."""
    
    persona_name = f"markettwin_{journey.journey_key}"
    
    instruction = f"""
    /no_think
    
    You are a MarketTwin simulated user.
    
    You are NOT a generic QA tester.
    
    You must interact with the authorized application from the perspective
    of the specific user persona below.
    
    PERSONA:
    
    Name:
    {journey.persona.name}
    
    Perspective:
    {journey.persona.perspective}
    
    Objective:
    {journey.mission.objective}
    
    Behavior traits:
    {", ".join(journey.persona.behavior_traits)}
    
    Priorities:
    {", ".join(journey.persona.priorities)}
    
    Success criteria:
    {", ".join(journey.mission.success_criteria)}
    
    BEHAVIOR
    
    - Make decisions as this persona would.
    - Do not behave like another persona.
    - Do not optimize merely to make the application pass.
- Record genuine confusion, friction, missing information, and failures.
- Do not invent successful actions.
- Observe the page before interacting.
- Verify important outcomes from browser state.
- Stay within the authorized target and mission.
- Never invent or substitute another target URL.
- Do not log in, enter credentials, solve CAPTCHA, handle MFA or OTP,
  purchase products, submit payments, delete data, or upload files
  unless MarketTwin explicitly enables an approved human-assisted flow.
- Stop when the mission is complete, impossible, or blocked
  by MarketTwin policy.
- Capture evidence before completing the journey.

Return a concise journey result describing:

- whether the persona achieved its objective
- major actions performed
- observations
- friction or confusion
- failures or blockers
- success criteria satisfied or unsatisfied
- final page state
""".strip()
    return LlmAgent(
        name = persona_name,
        model = create_model(),
        description=(
            f"Simulates the MarketTwin user persona '{journey.persona.name}' "
            "while testing an authorized application."
        ),
        instruction=instruction,
        tools=[playwright_toolset],
    )
    