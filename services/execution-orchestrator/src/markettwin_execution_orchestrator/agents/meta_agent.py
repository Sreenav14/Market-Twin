""" MarketTwin Meta Agent for multi-perspective test planning"""

from google.adk.agents import LlmAgent
from markettwin_shared.runtime_snapshot import AgentRuntimeSnapshotPayload

from markettwin_execution_orchestrator.agents.schemas.plan import (
    MetaAgentPlan,
)
from markettwin_execution_orchestrator.models.model_factory import (
    create_model,
    resolve_model_runtime_configuration,
)

META_AGENT_MAX_TOKENS = 1024

def build_meta_runtime_snapshot_payload(
    *,
    agent: LlmAgent,
    runtime_prompt: str,
) -> AgentRuntimeSnapshotPayload:
    """Build the safe semantic snapshot for the Meta Agent."""

    if not isinstance(agent.instruction, str):
        raise TypeError(
            "Meta Agent must use a static string instruction "
            "for runtime snapshotting."
        )

    model_configuration = (
        resolve_model_runtime_configuration(
            max_tokens=META_AGENT_MAX_TOKENS,
        )
    )

    return AgentRuntimeSnapshotPayload(
        agent_role="meta",
        runtime_kind="google_adk",
        runtime_agent_name=agent.name,
        agent_version=1,
        snapshot_schema_version=1,
        model_provider=model_configuration.provider,
        model_name=model_configuration.model_name,
        model_configuration=(
            model_configuration.snapshot_parameters()
        ),
        effective_instruction=agent.instruction,
        runtime_prompt=runtime_prompt,
        success_criteria=(),
        tools=(),
        policy_references=(),
        metadata={
            "output_schema": MetaAgentPlan.__name__,
        },
    )
    
def create_meta_agent() -> LlmAgent:
    """ Create the MarketTwin Meta Agent."""
    
    return LlmAgent(
        name = "markettwin_meta_agent",
        model = create_model(
            max_tokens = META_AGENT_MAX_TOKENS,
        ),
        description = (
            "Create diverse realistic user perspectives for "
            "testing an authorized application."
        ),
        instruction="""
/no_think

You are the MarketTwin Meta Agent.

Your responsibility is to design a concise multi-perspective testing
plan for the authorized application and user-supplied testing goal.

You DO NOT interact with the browser.

You must produce two separate concepts:

PERSONAS
Describe WHO is using the application.

MISSIONS
Describe WHAT those users should attempt to accomplish.

For every test run:

1. Generate exactly 3 materially different realistic user personas.

2. Personas must differ meaningfully in behavior, expectations,
   familiarity, priorities, patience, trust sensitivity, urgency,
   domain knowledge, or other relevant dimensions.

3. Personas must not contain test-specific objectives or success
   criteria. Those belong to missions.

4. Generate between 1 and 4 bounded test missions.

5. Each mission must represent one clear user goal that can be
   independently executed and evaluated.

6. Avoid one giant mission that attempts to test the entire product.

7. Each mission must contain observable success criteria.

8. Missions should be useful across all generated personas unless
   the supplied testing goal clearly requires otherwise.

9. Do not create duplicate personas or duplicate missions.

10. Do not invent permissions or authorization.

11. Keep the plan small enough for efficient execution.

MarketTwin will deterministically combine every persona with every
mission after you produce the plan.

Example conceptually:

Personas:
- first-time user
- experienced user
- trust-sensitive user

Missions:
- understand the product
- find pricing
- begin signup

Do not copy these examples unless they actually fit the application.
""".strip(),
        output_schema=MetaAgentPlan,
    )