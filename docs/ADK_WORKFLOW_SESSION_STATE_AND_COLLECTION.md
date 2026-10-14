# ADK workflow, session handoffs and supervisor collection

Implemented October 4, 2026.

## Update October 10, 2026

The outer journey loop and custom dispatcher described below have been replaced
with a SequentialAgent group (`Agent_Journeys_1`). Planning constructs each bounded
JourneySequence in that group, then the real ADK runner awaits Execute -> Record
for each journey in order before SupervisorAgent collects the results. Only
SequentialAgent containers now hold children in this outer workflow. Recording
no longer emits loop-exit escalation. Identity, durable collection, failure and
isolated browser/session boundaries remain intact.

Eight real-runner regressions pass, including no overlapping execution across
an asynchronous yield and rejection of an over-depth plan before browsing.
The historical loop-specific tree and descriptions below are superseded by this
update. Evaluation/reporting still run in their separate lifecycle phase after
collection; they have not become fictitious ADK children.

See ADK_AGENT_STRUCTURE_RESEARCH.md for the SDK facts and compatibility decision.

## Inspected implementation and SDK behavior

The existing execution path already had an ADK Meta Agent and independent ADK Persona Agents. Its outer coordination was a Python `for` loop. Each persona runtime was created through the existing factory, bound to a policy-controlled Playwright session, and saved an immutable runtime snapshot before calling its model. Execution records and `journey.result` events were committed in PostgreSQL after each journey. Those boundaries remain the source of truth.

This change follows the explicitly requested workflow shape using the installed, pinned `google-adk==2.5.0` package. The implementation was checked against that package's `SequentialAgent`, `LoopAgent`, `BaseAgent`, event actions, runner, and session service code, and against Google's official documentation:

- [Sequential workflows](https://adk.dev/agents/workflow-agents/sequential-agents/): deterministic ordered stages sharing one invocation context.
- [Loop workflows](https://adk.dev/agents/workflow-agents/loop-agents/): bounded iteration and an explicit exit signal.
- [Custom workflow agents](https://adk.dev/agents/custom-agents/): implement a stage through `BaseAgent` and its asynchronous event generator.
- [Session state](https://adk.dev/sessions/state/): use event state deltas for runner-managed handoffs.

ADK 2.5 supports these classes but marks `SequentialAgent` and `LoopAgent` deprecated in favor of its newer Workflow API. They are used here because this exact design was explicitly requested. The dependency remains pinned. A future SDK upgrade should migrate the workflow deliberately, rather than silently replacing this behavior. The strict type checker suppresses only deprecated-symbol diagnostics in the new compatibility module; SDK runtime warnings remain visible.

## Actual agent tree

```text
SequentialAgent: markettwin_run
  PlanAgent
  LoopAgent: JourneyLoop
    PlannedJourneyDispatcher: PlannedJourneys
      SequentialAgent: JourneySequence_1
        ExecuteJourneyAgent_1
        RecordJourneyResultAgent_1
      SequentialAgent: JourneySequence_2
        ExecuteJourneyAgent_2
        RecordJourneyResultAgent_2
      ... one concrete sequence for each planned journey
  SupervisorAgent
```

These are actual ADK agents run by an `InMemoryRunner`, not names added around the old Python loop.

The non-LLM stages are small custom `BaseAgent` adapters around the existing domain operations. The Meta Agent still decides personas and missions. Persona Agents still reason and choose controlled browser actions. Workflow ordering, indexing, validation and collection are deterministic; they do not require another model call.

### PlanAgent

The first stage runs the existing Meta planning workflow, or validates an immutable source plan for a persona-prompt rerun. It enforces the selected testing depth, persists the plan and fresh execution identities, and marks the run running. Only then does it emit the planning handoff into the outer ADK session state.

The planning handoff contains a JSON representation of the validated plan and its persisted persona, mission and journey UUID mappings. PostgreSQL remains authoritative. Knowledge snapshots, target scope, model configuration and prompt overrides retain their existing behavior.

After the plan is committed, this stage constructs the actual nested `SequentialAgent` instances for every assignment. Their descriptions contain the specific persona, mission and journey key. These are real plan-derived nodes in the ADK tree; the dispatcher selects the next existing node using the session index rather than reusing one generic journey sequence. No node is constructed for an assignment outside the validated plan.

### JourneyLoop and JourneySequence

The loop processes each planned persona/mission journey **once**. Low, medium and high retain the existing maximum coverage of 3, 6 and 12 journeys respectively; the planner may use fewer missions when fewer distinct useful tasks exist. The loop ceiling cannot exceed the selected depth.

`ExecuteJourneyAgent` reads the current plan and index from session state. It calls the existing controlled journey runtime for that exact assignment and commits its execution status and result event. The result must identify the assigned journey. A repeated/skipped index or mismatched result fails explicitly.

`RecordJourneyResultAgent` then reads the committed result handoff, appends it to the result collection and advances the index. On the last planned journey it emits `EventActions.escalate=True`, which stops the loop. The supervisor is outside the loop and runs afterward.

There is no retry loop over browser actions. A failed, timed-out or policy-blocked journey is collected with that status and the next distinct journey proceeds. An infrastructure exception, such as a failed durable commit, propagates and stops the run before collection. The workflow does not replay a journey to try to manufacture a pass.

### SupervisorAgent

The explicit supervisor reads the collected session results, validates that their keys exactly match the full ordered plan with no duplicates or omissions, and builds the existing `MultiPersonaExecutionResult` contract.

It then persists a `run.collection` event containing:

- `journey_count`
- `completed_count`
- `failed_count`
- ordered `journey_keys`

The supervisor completion event is committed **before** the TestRun is marked completed. The normal evaluation worker subsequently performs deterministic checks, visual verification, findings and report generation. The supervisor collects and validates the outputs; it does not invent findings or replace the evaluation worker.

No synthetic model prompt or model name is recorded for deterministic stages. Existing immutable runtime snapshots still describe the LLM runtimes actually constructed. The workflow agent tree is visible in ADK execution traces; durable supervisor completion is represented by the collection event.

## Session state and isolation

The root session has a unique ID per execution invocation. Its handoff keys are:

| Key | Purpose |
| --- | --- |
| `markettwin_plan` | Validated plan and durable UUID mappings |
| `journey_index` | Next planned assignment |
| `pending_journey_result` | Result committed by the current execution stage |
| `journey_results` | Completed journey results accumulated in order |
| `run_collection` | Supervisor-validated final result |

Stages emit `EventActions.state_delta`; the actual ADK runner applies those deltas before the next stage reads them. In-place list mutation is avoided. Results are JSON-safe and validated back into the existing Pydantic contracts.

Only outer workflow coordination shares this state. Each Persona Agent still receives a fresh inner ADK conversation and a separate browser session/context for its assigned persona and mission. It does not receive another persona's browsing history, observations, friction or cookies. Browser resource handles and database sessions are held by controlled application code, never placed in serialized session state.

The shared Playwright controller is opened lazily at the first journey and closed through `AsyncExitStack`. Invalid or over-budget planning does not open a browser. Existing per-journey timeouts, evidence recording, browser cleanup, target/network policy and prompt snapshot persistence remain in the original journey executor.

## Controlled Playwright through MCP

Each Persona runtime now uses a real MCP connection to its own journey-bound browser tools. The direct dependency is `mcp>=1.26,<2`, locked to **1.30.0**. The v1 range is deliberate: the installed ADK 2.5 MCP integration imports that SDK's `ClientSession` APIs. The implementation was inspected against the installed SDK and its [official v1 memory transport](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/src/mcp/shared/memory.py), [server APIs](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/src/mcp/server/lowlevel/server.py), and [ADK MCP documentation](https://adk.dev/tools/mcp-tools/).

The lifecycle is:

```text
Persona ADK BaseTool adapter
  MCP ClientSession initialize / list_tools / call_tool
  in-process bidirectional MCP protocol streams
  MCP server with a whitelist of this journey's functions
  existing controlled Playwright controller, browser handle and step recorder
```

The connection uses actual MCP protocol messages and schema discovery. Its memory transport adds no network listener, port, browser subprocess or second browser. It deliberately exposes the existing MarketTwin tools instead of launching an unrestricted third-party Playwright MCP server. Their closed-over session/execution/journey IDs, origin/network restrictions, protected-action rules, shared action lock and evidence recorder remain intact. Tool input schemas reject extra arguments, so an agent cannot inject another browser identity. No browser handles or credentials enter outer ADK session state.

The small ADK `BaseTool` adapter calls `ClientSession.call_tool()` **once**. The installed stock ADK MCP tool wraps calls with an automatic exception retry; that is unsuitable for browser actions when an action may have happened but its response was lost. The adapter has no automatic retry or direct-function fallback. Structured MCP observations retain the original payload and evidence step IDs. Policy rejections remain `BrowserPolicyError` and therefore preserve the existing policy-blocked journey outcome. Durable evidence transaction failures remain `SQLAlchemyError`, which preserves the existing rollback and run-failure behavior.

MCP initialization/discovery has a 10-second bound. The existing journey execution timeout still bounds agent execution. The journey executor attempts to close its inner ADK runner, MCP client/server, and controlled browser in that order, then saves session artifacts. Nested cleanup guards ensure an earlier close failure cannot prevent browser closure and evidence recording. Cancellation terminates outstanding server tasks without replay. Actual persona snapshots record `metadata.browser_tool_transport = "mcp_memory"`; historical snapshots remain unchanged.

The connection is created inside the journey's observability correlation scope. MCP background tasks therefore inherit the actual run, journey, execution and snapshot IDs when they are started, preserving correlation on server-side browser/evidence spans. No credentials enter MCP tool metadata.

## Durability and delivery

Session state coordinates one live invocation. It is not a replacement for PostgreSQL, and this change does not claim durable ADK session resumption or horizontal worker ownership safety.

The persistent worker still processes a command and finishes the run before committing its Kafka offset. Existing recovery rules for interrupted planning/running executions remain unchanged. Deterministic workflow stages do not introduce an alternate command path or offset-commit policy.

The public `execute_markettwin_run` signature and `MultiPersonaExecutionResult` return contract are unchanged. The diagnostic `execute_multi_persona_plan` helper also uses the same ADK workflow rather than maintaining a second Python-loop execution semantics.

## Code changes

- `workflow/adk_workflow.py`: actual agent tree, typed session handoff, exit guard and supervisor validation; real runner lifecycle.
- `workflow/run_executor.py`: planning/persistence callbacks, lazy browser lifecycle, existing run state transitions and final collection ordering.
- `workflow/multi_persona_executor.py`: extracts the existing one-journey execution/persistence block unchanged, reuses the ADK pipeline for direct execution and persists supervisor collection metadata.
- `tests/test_adk_workflow.py`: exercises the real ADK runner without a model or browser.
- `browser/mcp_tools.py`: real MCP discovery, controlled function dispatch, single-call ADK adapter and client/server lifecycle.
- `workflow/journey_executor.py`: connects the Persona Agent to the MCP tools and records the actual transport in its immutable runtime snapshot.
- `tests/test_controlled_browser_mcp.py`: real MCP sessions with fake controlled browsers; no network service or application actions.

## Verification

Seven dedicated real-runner cases passed:

1. Three journeys execute exactly once, then the supervisor.
2. Six journeys execute exactly once, then the supervisor.
3. Twelve journeys execute exactly once, then the supervisor.
4. Failed, timed-out and policy-blocked outputs are retained without replay.
5. A durable execution exception stops before supervisor collection or another execution.
6. A result for the wrong journey is rejected before collection.
7. Duplicate planned assignments are rejected before execution.

The three/six journey cases deliberately use a 12-iteration loop ceiling to verify that the explicit last-result escalation stops the loop without a duplicate final execution. Planning mappings survive the actual JSON session-state round trip.

The runner cases also assert that planning builds the exact number of concrete nested sequences, in assignment order, with unique stage names and the correct parent ownership.

Nine actual MCP protocol cases verify tool discovery and recorded evidence, preserved policy blocking, concurrent-action serialization, no replay after a lost response, closed-session rejection, rejection of injected browser identities/arbitrary tools, cancellation of an outstanding server action, preserved durable evidence transaction errors, and actual OpenTelemetry correlation on server-side background actions. The completed-journey evidence regression additionally checks that the runtime's tools are MCP adapters and its snapshot records the transport. Separate runner-close and MCP-close regressions prove controlled browser closure and evidence recording still happen when either earlier cleanup fails.

After the plan-derived tree and MCP additions, the protocol, actual ADK workflow and evidence/persistence regression suites passed together: **37 tests**. Targeted strict Pyright passed for `mcp_tools.py`, `adk_workflow.py` and `journey_executor.py` with zero errors; Ruff passed for the new/changed protocol and workflow files and their tests.

The focused workflow, coverage, persistent-worker and one-shot diagnostic checks passed together: **21 tests**. Targeted strict Pyright passed for the three changed workflow modules with zero errors, and Ruff checks passed after formatting.

These checks do not invoke external models, spend model tokens, or perform browser actions against a real application. A newly started run still requires the configured broker/outbox/execution/evaluation workers to be available.
