# Agent workflow and evaluation implementation

Implemented and verified October 4, 2026.

## Outcome and design decisions

The execution worker now runs a real ADK sequence: planning, a bounded journey loop, then supervisor collection. Each planned journey has its own concrete sequential node and executes once. Its Persona Agent uses a real MCP connection to the existing controlled Playwright session. Saved outputs reach evaluation only after collection has validated and recorded the complete result set.

The UI separates Results, Evaluation, Findings, Report and editable testing-agent prompts. A compact flow map sits beside these pages. It reflects saved plan and execution records instead of displaying a decorative static diagram. The theme is light, with shared neutral surfaces, consistent controls and explicit status text.

The implementation keeps decisions that need model reasoning in the Meta, Persona and evaluation agents. Ordering, state validation, persistence and collection are deterministic. This avoids adding an LLM supervisor merely to concatenate outputs, reduces latency and gives collection an exact completeness invariant.

## Actual execution and communication

```text
Start test → Control API → outbox → Kafka → persistent execution worker
  SequentialAgent: markettwin_run
    PlanAgent: existing Meta Agent and validated saved plan
    LoopAgent: JourneyLoop
      PlannedJourneyDispatcher
        JourneySequence_N: execute Persona → record result
    SupervisorAgent: validate and persist collection
  completed TestRun → evaluation worker → saved report
```

The Meta Agent produces a validated plan. Python constructs the ADK nodes from that plan; the model does not generate executable orchestration code. The dispatcher selects the next concrete journey sequence. A result is committed before advancing the loop index. The final result explicitly exits the loop, preventing duplicate browser actions.

ADK session state carries the plan, current journey index, pending result, accumulated results and final collection through event state deltas. Supervisor collection checks the exact ordered journey keys against the saved plan and rejects missing, duplicate or unexpected results. Its durable `run.collection` event records the keys and runtime completion/failure counts before the TestRun becomes completed.

Persona conversations and browser sessions remain isolated. They do not receive another Persona's private conversation. Shared orchestration state communicates their saved outputs to the supervisor. PostgreSQL remains the durable record; the live in-memory ADK session is not a restart mechanism or a distributed worker lease.

Low/Medium/High means testing coverage: one/two/four missions with the existing three personas, giving three/six/twelve journeys. It does not change model reasoning effort. Dynamic persona counts and explicit non-Cartesian journey assignments remain a separate planner change.

See [ADK workflow and MCP details](ADK_WORKFLOW_SESSION_STATE_AND_COLLECTION.md).

## Controlled Playwright MCP boundary

Each journey connects an MCP client to an in-process MCP server over memory transport. Discovered tool schemas and calls use the actual MCP protocol. The server delegates to the existing browser tools, retaining origin/network restrictions, action locking, step recording and evidence capture. There is no extra browser, local HTTP listener or unrestricted automation path.

The custom ADK tool adapter makes one call per requested browser action. It deliberately avoids automatic replay after transport failures. Policy and database errors retain their distinct semantics. Tool connections are established before the runtime snapshot, so saved tool metadata describes the transport actually used.

Run/journey/snapshot tracing correlation is captured when the MCP background server starts. Cleanup attempts runner closure, MCP closure and browser/evidence cleanup even if an earlier close fails. Regressions exercise both close failures and a real MCP background tracing boundary.

## Collection and evaluation

The existing evaluation worker remains asynchronous and uses database discovery and its advisory lock. The canonical pipeline produces deterministic execution/outcome findings, visual evidence checks, then a bounded semantic assessment and final report. Diagnostic entry points use this same pipeline rather than maintaining a second reporting implementation.

One semantic model call produces individual journey assessments and an overall assessment against the saved testing goal. Inputs include actual Persona/mission context, saved journey outputs and visual verification records. The output contract requires exact journey IDs, complete individual coverage and supporting journey references. Runtime failures must remain inconclusive application verdicts. The UI uses recorded identity, never the order of model output, to label an individual assessment.

The evaluator uses `EVALUATION_MODEL_NAME` when set, otherwise `MODEL_NAME`, with the existing provider configuration. Output defaults to 4096 tokens through `EVALUATION_MODEL_MAX_OUTPUT_TOKENS`; supported response parameters are detected through LiteLLM. Input is bounded at 120,000 characters. A provider failure, timeout, malformed result or output limit leaves semantic assessment explicitly unavailable while preserving deterministic findings and evidence checks. There are no invented scores or automatic browser reruns.

Assessment data is saved in the report payload alongside full visual-check records. Its runtime records the configured model, actual duration and immutable evaluator prompt snapshot. Evaluation exposes visual-verifier/evaluator context separately from editable testing agents. Older reports remain accessible and truthfully state which records were never saved; they are not silently reevaluated.

The flow map shows `awaiting_report` after execution completes until a final report exists. It does not infer that the evaluation worker is idle from the absence of a report. A historical completed run without a collection event shows `not_recorded` for collection.

See [results and evaluation behavior](RESULTS_AND_EVALUATION_CLARITY.md) and [evaluation readiness](EVALUATION_READINESS_AND_RUN_SETTINGS.md).

## Prompt editing, timing and navigation

The sidebar `/agents` page queries actual Meta/Persona snapshots scoped to the authenticated workspace. Date filters include the selected local calendar days; sorting supports recent/oldest. The response is bounded to 100 results and the UI states that limit. Selecting an entry opens its exact run and snapshot.

The YAML editor permits changes only to instruction and runtime input. **Save prompt** persists a separate per-user draft. Unsaved edits cannot create a rerun draft. Reopening the agent loads the saved edit. Original snapshots, results and evidence remain immutable. Model/tool/identity fields cannot be changed through YAML.

**Create rerun draft** creates a new TestRun and uses the normal Start path. Meta edits replan; Persona edits reuse the source plan and apply the override to the selected journey in a new whole run. The configured server model applies to new execution. Prompt changes cannot guarantee a desired outcome.

Persona duration comes from actual AgentExecution timestamps. New Meta calls persist an `agent.runtime` event linked to their snapshot. Missing historical timing is shown as unavailable. Active elapsed time is approximate and explicitly derives from a recorded start time.

The editor switches to a vertical layout based on its available container width, preserving usable YAML space beside the flow map. Desktop 1100px and mobile regressions cover this constrained layout.

See [prompt permissions and reruns](AGENT_PROMPTS_AND_RERUNS.md).

## Database and operational verification

Applied migrations:

- `d6e71a092f41`: per-user AgentPromptDraft persistence.
- `e8a621bd3c70`: allow actual evaluator runtime snapshots while retaining the existing roles.

No active runs were present before service reload. The Control API, execution worker and evaluation worker were reloaded with the configured environment. `/health` returned process health `ok`; OpenAPI registered the flow, journeys, collection, evaluation-agents, workspace agent-directory and prompt-save endpoints. A read-only database check confirmed revision `e8a621bd3c70` and an existing completed run with six journeys, ten flow nodes and a completed report. No verification started a new application test or spent live model tokens.

Kafka remains an external operational limitation: the bootstrap connection and one broker authenticate, but advertised broker node 1 fails TLS with `record layer failure`. The execution consumer joined its group and waits for commands; the outbox producer still cannot initialize through that broker. This can strand newly requested runs in queued. Process health remains independent of Kafka, and TLS verification/idempotency were not weakened to mask the failure. Broker advertised-address/TLS configuration needs correction before claiming the entire Start path is operational.

## Verification and cleanup

| Check | Result |
| --- | --- |
| Full Python regression suite | 392 passed, 12 skipped; skips retain their opt-in database/live-model/media requirements. |
| Final MCP/ADK/evidence checks after cleanup and correlation fixes | 37 passed. |
| Final prompt/API/flow/assessment checks after identity/status fixes | 42 passed. |
| Changed backend strict Pyright and Ruff | Passed; Pyright reported zero errors. |
| Frontend unit tests | 23 passed. |
| Final TypeScript and production build | Passed. Build retains a nonblocking approximately 516 KB JavaScript chunk warning. |
| Results/evaluation/flow browser scenarios | 14 desktop/mobile scenarios have passing executions; focused retries and fixture polling corrections are documented separately. |
| Final exact assessment identity and constrained prompt editor | Two desktop/mobile scenarios each passed with accessibility and reflow checks. |

Browser tests render the real React app with HTTP fixtures. They check visible states, exact source/evidence navigation, denied-access behavior, polling transitions and layout. They do not prove live model quality or external object-storage/Kafka availability. Full details and honest timing/retry notes are retained in the feature documents.

Temporary test screenshots, traces, generated fixtures and the read-only integration helper were removed after review. Durable regression tests and documentation remain. Application evidence capture, stored run artifacts and uploaded sources were not deleted as development cleanup.

## Remaining boundaries

- This is the current single-worker execution model. Horizontal execution requires a lease/attempt owner before redelivery can safely distinguish a dead worker from a live one.
- The pinned ADK 2.5 supports SequentialAgent/LoopAgent but deprecates them toward its newer Workflow API; the explicitly requested classes are used here and a future SDK migration must be deliberate.
- Evaluator model output is validated and grounded in saved records, but its semantic quality has not been validated against a live model in this change.
- Historical reports without a semantic assessment stay unchanged. An unavailable assessment does not trigger repeated model calls after report completion.
- The flow map is read-only and updates from actual runs; it is not a workflow editor.

Primary references inspected: [ADK sequential workflows](https://adk.dev/agents/workflow-agents/sequential-agents/), [ADK loops](https://adk.dev/agents/workflow-agents/loop-agents/), [ADK session state](https://adk.dev/sessions/state/), [LiteLLM structured output support](https://docs.litellm.ai/docs/completion/json_mode), and [WCAG contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
