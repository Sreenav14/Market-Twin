""" MarketTwin persona browser agent """

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from markettwin_execution_orchestrator.agents.schemas.persona import PersonaSpec
from markettwin_execution_orchestrator.models.model_factory import create_model


def create_persona_agent(
    *,
    persona: PersonaSpec,
    playwright_toolset: McpToolset,
) -> LlmAgent:
    """ Create one isolated MarkekTwin persona-testing agent."""
    
    persona_name = f"markettwin_persona_{persona.persona_id}"
    
    instruction = f"""
    /no_think
    
    You are a MarketTwin simulated user.
    
    You are NOT a generic QA tester.
    
    You must interact with the authorized application from the perspective
    of the specific user persona below.
    
    PERSONA:
    
    Name:
    {persona.name}
    
    Perspective:
    {persona.perspective}
    
    Objective:
    {persona.objective}
    
    Behavior tarits:
    {", ".join(persona.behavior_traits)}
    
    Priorities:
    {", ".join(persona.priorities)}
    
    Success criteria:
    {", ".join(persona.success_criteria)}
    
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
- Stop when the persona objective is complete, impossible, or blocked
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
            f"Simulates the MarketTwin user persona '{persona.name}' "
            "while testing an authorized application."
        ),
        instruction=instruction,
        tools=[playwright_toolset],
    )
    