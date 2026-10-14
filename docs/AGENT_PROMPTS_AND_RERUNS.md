# Current prompt and flow update ? 2026-10-10

Agent Settings selects a project/test and shows Meta -> Sequential Agent with
recorded journey subagents -> Collector -> Evaluation and Report. YAML alone
configures prompt text and rerun settings; historical identity/context fields
remain immutable. There are no separate settings controls. The flow scrolls
inside its panel, and sequential children run in declared order. Collector is a
deterministic stage without an invented model prompt. Evaluation remains a
separate worker phase before the report. Historical notes below are superseded
where they describe a flat directory or separate configuration form.

Desktop/mobile save/reset/rerun and flow regressions pass. See CURRENT_STATE.md
and ADK_AGENT_STRUCTURE_RESEARCH.md for verification and schema compatibility.

# Agent prompts and rerun drafts

Implemented October 4, 2026.

## Saved edits and run timing follow-up

The prompt editor now has an explicit **Save prompt** action. Saved edits are separate per-user prompt drafts, not mutations of historical runtime snapshots. The page loads saved YAML when reopening an agent, updates its query cache after saving, shows unsaved/saved status, and disables rerun creation while current edits are unsaved. Reset restores the original prompt in the editor; saving that reset deliberately updates the separate draft.

Created-agent rows show their saved creation timestamp and actual recorded execution duration. Persona timing comes from AgentExecution; new Meta calls record an agent.runtime event tied to their immutable snapshot. Running executions with a real start timestamp show approximate elapsed seconds; historical snapshots without timing records display “Duration not recorded” rather than inventing a value. Local calendar date filters and newest/oldest sorting make recent agents easier to find. A selected editor stays open when its row is excluded by a date filter, preserving edits.

The sidebar **Agents** landing page lists actual created agents across the workspace, rather than only tests. Its date/order filters run against the authenticated workspace API, using the selected local midnight as the inclusive start and the midnight following the end date as an exclusive end. This includes the whole selected calendar day across timezone/DST boundaries. The page states its 100-result limit. Selecting a row opens the correct test and exact snapshot through `/runs/{id}/agents?snapshot={snapshot_id}`. Optional per-run filters are available as well.

Saved-draft persistence, authenticated Save API and its migration are implemented separately from the immutable snapshot reader. The updated desktop/mobile workflow tests cover Save validation, rerun gating and navigation back to saved YAML.

The latest real completed run was also checked read-only: all ten Meta/Persona
prompt snapshots round-trip through YAML and the edit validator. Its additional
visual verifier snapshot remains separate from the Meta/Persona directory.
Visual verifiers and the new testing-goal evaluator are inspected in Evaluation,
where their actual model, creation time and available instruction are read-only.

## Problem and inspected boundaries

MarketTwin already saves immutable `AgentRuntimeSnapshot` rows for planning, persona execution, and visual verification. They contain the actual instruction and runtime input supplied to the agent, the configured model, controlled browser tool names, persona/mission context, timestamps, and a semantic configuration hash. The Control API already authenticates reads of those snapshots against the parent TestRun. The UI did not expose this information or provide a way to try a prompt change.

The implementation uses those existing runtime records. Separate AgentPromptDraft rows store per-user edits; they do not replace historical snapshots or create another agent registry. Migration d6e71a092f41 creates this draft table.

## Navigation and review

- The workspace sidebar has an **Agents** page at `/agents`, listing created agents across accessible workspace tests, with date filters and recent/oldest ordering.
- Selecting a test opens `/runs/{id}/agents`, also available in the test's tabs.
- The page lists snapshots of agents that were actually created. Queued/draft tests truthfully show that no agents exist yet. Planner snapshots appear at planning time; persona snapshots appear as individual journeys start. Active execution refreshes the list every five seconds.
- Selecting an agent displays its saved prompt and context as YAML. Multiline text uses YAML literal blocks, which are readable and editable without escaping newlines.
- The YAML can be downloaded. The editor offers reset and a clearly named **Create rerun draft** action. Errors keep the editor and user edits visible.
- Visual verifier and evaluator snapshots appear under Evaluation, outside the testing-agent prompt directory. They are read-only; this rerun endpoint supports Meta and Persona agents.

The page uses the app's shared theme tokens, panel/button typography and status badges. Desktop places the agent list beside the editor; narrow screens stack them. A normal labeled textarea avoids adding a heavyweight code-editor dependency.

## Rerun behavior

`POST /api/v1/test-runs/{id}/agent-reruns` accepts one source snapshot ID and the edited YAML. It creates a **new draft TestRun** and navigates to its overview. It does not start browser execution automatically. The normal **Start test** action, outbox, Kafka command and persistent execution worker remain the execution path.

The new configuration records `rerun_of_test_run_id`, `source_agent_snapshot_id` and the selected `agent_prompt_overrides`. It copies the source test's frozen target, study brief, approved knowledge and testing depth. Original TestRuns, snapshots, results and source/evidence history are untouched.

There are two intentional cases:

1. **Planner prompt edit:** run the planner again with the edited instruction and input, then execute its newly validated plan. The selected coverage limit is still enforced.
2. **Persona prompt edit:** reconstruct the source test's persisted personas and missions as a frozen `replay_plan`, create new execution identities, and apply the edited instruction/input to the selected persona/mission journey. The source personas, objectives, success criteria and priorities remain intact. This avoids re-planning a different set of journeys and accidentally attaching an override to the wrong generated agent.

A persona rerun executes a new whole test using the source plan. Only the selected journey receives the edited prompt; the other journeys use the normal agent template. The implementation edits one saved agent at a time. It does not provide batch prompt editing, live mutation of an executing agent, or a separate single-journey evaluation pipeline.

The recorded model in exported YAML describes the original agent. New execution uses the currently configured server model, as normal execution does; the page states this explicitly. YAML is not a model configuration override.

## Validation and permissions

- Reads require membership access to the source TestRun.
- Creating a draft requires an existing workspace write role and a currently accessible, actively authorized target. Starting the draft rechecks target authorization using the existing Start endpoint.
- The selected snapshot must belong to the specified source run. A snapshot from another run returns 404.
- Only `instruction` and `runtime_prompt` may change. Model, model configuration, tool names, persona, mission and snapshot identity must match the saved snapshot. Browser sessions and browser/network policies remain constructed by the existing controlled runtime.
- YAML uses PyYAML's safe loader, rejects arbitrary Python tags, duplicate/non-string mapping keys and aliases, and bounds both the request size and editable prompt lengths.
- Persona replay requires a complete reusable persisted plan compatible with the current three-persona, one-to-four-mission contract. Missing plan data returns a specific 409 rather than queuing a broken execution.
- The execution request carries the overrides to the existing planner/persona runtime. The effective edited instruction and runtime input are applied **before** writing the new runtime snapshot, so later review shows the prompts actually used.

Prompt edits cannot guarantee a desired model result. Structured output contracts and server-side tool policy still apply. This feature does not rewrite malformed results in historical runs.

## Changed implementation

- `services/control-api/.../api/agent_prompts.py`: authorized YAML inspection, safe validation, immutable draft forks and frozen source plan reconstruction.
- `services/control-api/.../main.py`: register the two endpoints.
- `services/control-api/pyproject.toml` and `uv.lock`: declare the existing PyYAML dependency directly for the Control API.
- `services/execution-orchestrator/.../workflow/planning.py`: apply planner prompt overrides before snapshot persistence.
- `services/execution-orchestrator/.../workflow/journey_executor.py`: apply journey overrides to the factory-created controlled persona runtime before its snapshot is saved.
- `services/execution-orchestrator/.../workflow/multi_persona_executor.py`: select the override by the frozen journey key.
- `services/execution-orchestrator/.../workflow/run_request.py` and `run_executor.py`: load overrides/replay plan from the frozen TestRun configuration and use the existing execution pipeline. These files also contain the separately implemented testing-depth change.
- `apps/web/src/lib/agentPrompts.ts`: typed API operations, reusing the existing authenticated request helper.
- `apps/web/src/pages/runs/AgentPromptsPage.tsx` and `styles/agent-prompts.css`: list, YAML editor, download/reset and draft creation.
- Route, AppShell, RunLayout and command menu hooks expose the feature within the existing app navigation.

## Verification

- **15 Python tests passed**, covering multiline YAML round trips, immutable fields, malformed YAML, duplicate keys, unsafe tags, aliases, both planner/persona draft forks, preservation of knowledge/depth/history, schema-valid replay plans, cross-agent 404, and read-only role 403.
- **2 Playwright tests passed**, one desktop and one mobile. They navigate from the sidebar, inspect saved YAML, show a validation error without losing the editor, reset edits, submit modified YAML, and arrive at the new draft's Start action. Both include a WCAG 2 A/AA and WCAG 2.1 AA accessibility audit with zero violations and a check for horizontal document overflow.
- Ruff passed for the new backend endpoint and tests.
- Targeted strict Pyright passed for the new backend endpoint with zero errors. Three narrowly scoped callback annotations cover PyYAML's incomplete third-party types; application values and edited payloads remain typed and validated.

The end-to-end tests use controlled API fixtures. They do not execute browser actions against a real application or spend model tokens to validate draft creation. Production execution of a rerun still depends on the normal outbox/Kafka/worker availability.

Temporary Playwright output created for these checks is removed after verification; durable regression tests remain in the repository.
