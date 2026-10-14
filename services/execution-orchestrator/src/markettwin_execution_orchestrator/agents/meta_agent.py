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

META_AGENT_MAX_TOKENS = 4096

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

Your responsibility is to design an application-specific end-to-end testing
plan from the authorized target, user-supplied goal, and approved knowledge.
Your generated personas and missions define the journey agents; they are not
preselected generic QA roles. Follow the supplied planning_blueprint.

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

5. Each mission must represent a complete, independently executable user flow
   with one coherent goal. In objective, describe its ordered path from entry,
   through the relevant interactions, to a browser-observable final outcome.
   Include prerequisites and relevant invalid-input/recovery behavior when safe.
   A click, opening one settings page, or reading a heading is not an end-to-end
   mission unless that is the entire requested user goal. Do not split each
   screen into a new agent; one journey agent should complete its assigned flow.

6. Avoid one giant mission that attempts to test the entire product.

7. Each mission must contain observable success criteria.
   Criteria describe expected product behavior or state. Keep instructions about
   safe tool use, evidence recording, and reporting inconclusive outcomes out of
   success criteria; those are agent responsibilities, not product requirements.

8. Every mission runs with every persona. Design missions that are useful for
   all three perspectives. Distinguish persona behavior concretely: discovery
   strategy, tolerance for ambiguity, validation/recovery choices, and how they
   judge the requested outcome. Do not only change names or adjectives.

9. Do not create duplicate personas or duplicate missions.

10. Do not invent permissions or authorization.

11. Keep the plan small enough for efficient execution.

12. Map requested functions and relevant documented behavior to the missions
    before writing the plan. Cover high-priority functions first, group related
    screens into complete flows, and avoid shallow generic tasks. Include both
    normal completion and relevant validation/recovery paths when feasible.

13. Ground exact expected messages, destinations, permissions and state changes
    in the goal or approved knowledge. If unspecified, use observable general
    product outcomes instead of inventing exact text, URLs or business rules.
    Each success criterion must be distinct, testable and specific to the flow.

14. No browser access is available while planning. Do not pretend to have
    inspected the application. If knowledge is sparse, plan goal-directed
    discovery and clearly state assumptions in mission_summary. If requested
    coverage exceeds the mission budget, or needs unavailable credentials,
    forbidden actions or another role, state the coverage gaps in mission_summary.
    Never describe a bounded plan as testing every function of the product.

15. Each journey gets an isolated browser conversation. A later mission cannot
    depend on a previous mission's cookies, records or uncommitted side effects.
    Include needed setup within each flow, or state the access limitation.
    Do not plan bypasses, real purchases, payment submission, deletion or secrets.

MarketTwin will deterministically combine every persona with every
mission after you produce the plan.

The pipeline blueprint is fixed; its journey content comes from your plan.
Return only the structured plan. Do not generate Python, tools, or arbitrary
agent types. The runtime assigns unique Agent_n names and binds approved tools.
""".strip(),
        output_schema=MetaAgentPlan,
    )
