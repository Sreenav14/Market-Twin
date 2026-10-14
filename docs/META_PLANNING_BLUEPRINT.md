# Meta-generated end-to-end testing blueprint

Updated 2026-10-10 following the user's clarification that Meta must create useful
application-specific agents, rather than merely displaying a fixed phase diagram.

## What is fixed and what Meta creates

The execution contract is Meta -> sequential journeys -> Collector -> evidence
evaluation -> Report. This contract controls ordering and evidence integrity.
Meta generates the personas and missions from the goal, authorized target, and
selected approved knowledge. Runtime construction expands that actual plan into
one isolated journey agent for each persona/mission pair. Names and tools are
assigned by controlled application code; Meta does not generate arbitrary Python,
unregistered tools, or unrestricted agent types.

Thus the container blueprint is fixed, but the journey content is generated.
There is no hard-coded list of account/pricing/signup agents. The phase labels in
the UI describe the execution contract, not evidence of model-designed coverage.

## Planning changes

Previously the Meta instruction emphasized concise generic goals and included
examples such as product understanding, pricing and beginning signup. Its output
budget was 1,024 tokens. The updated template removes that anchoring and raises
the bounded output budget to 4,096 tokens, consistently across creation, runtime
configuration and snapshots. This is a ceiling, not a minimum output requirement.

The planning input now includes an explicit planning_blueprint. Meta must:

- Map desired functions and documented behavior into prioritized, coherent flows.
- Give personas concrete differences in discovery, recovery, familiarity and
  expectations relevant to this application, not merely different names.
- Describe the ordered end-to-end path in each existing mission objective, with
  relevant setup, interactions, safe validation/recovery and final state.
- Use distinct observable product criteria, grounded in the goal/knowledge.
- State assumptions, missing access and uncovered scope in mission_summary.
- Keep each journey independent of other agents' cookies or side effects.

The existing objective/criteria/persona models are reused; no database migration
or second planning system was introduced. Mandatory blueprint guidance also
accompanies edited runtime prompts. Persona instructions now explicitly require
completing the assigned flow, rather than ending after an intermediate page opens.

New validation rejects duplicate persona/mission IDs, blank or repeated criteria,
and duplicate newly generated mission objectives. Objective uniqueness is checked
for fresh Meta output rather than retroactively invalidating historical plan replay.
These checks establish structural quality, not semantic completeness or truth.

## One run and coverage limits

One run executes every planned mission with every generated persona, sequentially,
then collects and evaluates the outputs. Current depth limits remain exactly three
personas with up to one/two/four missions (low/medium/high), yielding up to 3/6/12
journeys. Related functions should fit within a complete flow rather than becoming
a separate shallow agent for every screen.

For example, if account recovery is requested and supported by approved knowledge,
a mission could cover entry -> account settings -> invalid address feedback ->
correction -> authorized confirmation, with criteria for the relevant state changes.
That is an illustration, not a built-in mission or a promise that account access
exists. Real credentials, forbidden side effects and unavailable dependencies
remain blockers. More requested features than the bounded plan can cover must be
identified as coverage gaps; the app cannot honestly promise exhaustive testing.

## Verification and remaining work

Six regressions first failed against the prior implementation, then passed.
The broader focused suite passed 38 tests, covering planning inputs, depth limits,
journey expansion, persona prompts, persistence, configuration and real sequential
runner behavior. Ruff and strict Pyright checks were also run.

No representative live model/browser benchmark was performed for this template
change. Before claiming improved generated-plan quality, inspect the actual Meta
output for a representative approved application, then check each desired function
against planned criteria and executed browser steps. Existing benchmark results
predate these templates and do not validate them. Lack of approved knowledge can
still limit specificity because Meta has no browser access while planning.

## References

- [Google ADK LlmAgent guidance](https://adk.dev/agents/llm-agents/): instructions,
  model generation configuration and structured output are distinct controls;
  model-driven behavior still requires evaluation.
- ADK_AGENT_STRUCTURE_RESEARCH.md: SDK agent types and installed 2.5.0 compatibility.
- V1_PRODUCT_CONTRACT.md and V1_FINDING_INTEGRITY.md: evidence and scope requirements.
- agents/meta_agent.py and workflow/planning.py: Meta template, blueprint, budget.
- agents/persona_agents.py: execution instructions for the generated missions.
- agents/schemas/plan.py and mission.py: assignment and criterion validation.
- workflow/journey_planner.py and adk_workflow.py: generated cross-product and order.
- tests/test_meta_blueprint.py: new regression checks.

Paths above are relative to
services/execution-orchestrator/src/markettwin_execution_orchestrator unless
prefixed with tests or referring to a document in this directory.
