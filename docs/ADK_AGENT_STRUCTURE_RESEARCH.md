# Google ADK agents: research and MarketTwin decisions

Researched 2026-10-10 using Google's official documentation and the locally
installed `google-adk==2.5.0` implementation. This document separates SDK facts,
current MarketTwin behavior, and proposed changes. It does not claim the pending
runtime or UI reconfiguration has been implemented.

## Main finding

Subagents are not exclusive to SequentialAgent. ADK's BaseAgent defines the
`sub_agents` relationship; LLM coordinators, sequential/parallel/loop controllers,
and custom agents can use that relationship. A child has one parent. The parent
type determines how children are invoked; nesting alone does not guarantee that
every child runs, or that they run in order.
[Google's hierarchy and custom-agent documentation](https://adk.dev/agents/custom-agents/).

MarketTwin's requested rule is narrower: only SequentialAgent containers should
hold children, LlmAgent workers should be leaves, and execution should follow the
listed order. This is a product constraint we can enforce, rather than an ADK
limitation. UI labels must preserve that distinction.

## Agent and workflow comparison

| Type or mechanism | Who controls execution? | Child behavior | MarketTwin decision |
| --- | --- | --- | --- |
| LlmAgent / Agent | Model reasoning and tool selection | Can delegate when configured as a coordinator | Use as a leaf for planning, browser work, and model judgments |
| SequentialAgent | SDK list order | Awaits each child before starting the next | Fits the requested ordered pipeline |
| ParallelAgent | SDK concurrency | Concurrent branches, interleaved events | Exclude from this sequential product configuration |
| LoopAgent | SDK iterations and exit events | Repeats child sequence | Avoid for one-pass journey execution |
| Custom BaseAgent subclass | Application code | Whatever the implementation explicitly invokes | Keep small deterministic leaf stages for persistence and collection |
| Workflow | Graph edges and application routing | Composes agents, functions, tools, and nested workflows | Modern migration option; evaluate deliberately |
| ManagedAgent | Google-hosted agent execution | Remote managed reasoning and tools | Unsuitable as a drop-in replacement for our owned browser controller |
| RemoteA2aAgent | Remote agent through A2A | Protocol-mediated remote task execution | No present requirement; retain local evidence ownership |
| RoutedAgent | Explicit routing function | Selects an agent for an invocation | Current documented feature is TypeScript experimental, not our Python runtime |

The table includes both concrete agent classes and orchestration mechanisms.
They are not all interchangeable Python classes. The sections below identify
their scope and sources.

## LlmAgent, also called Agent

LlmAgent provides model-driven reasoning, instructions, tools, and optional
structured input/output. `Agent` is its common alias, not a separate kind of
intelligence. Temperature belongs to model generation configuration; it controls
sampling rather than workflow scheduling. A low value cannot prove correctness
or guarantee identical browser actions.
[Official LlmAgent guide](https://adk.dev/agents/llm-agents/).

Installed-source observations: `llm_agent.py` inherits BaseAgent, accepts
`generate_content_config`, `output_schema`, `output_key`, and `sub_agents`, and
supports `chat`, `task`, and `single_turn` modes. The output-key implementation
writes the result into an event state delta. These fields are not properties of
SequentialAgent's own model: that controller has no model call to configure.

For MarketTwin, the planner determines a bounded plan. Persona workers use
registered tools bound to the assigned browser session. Helpers may provide
context, but their prose cannot become the final structured result or independent
evidence. The designated reporter's author identity and schema remain essential
validation boundaries. Requested temperature 0.05 and effective provider settings
must remain separately recorded when a model adapter omits unsupported sampling
parameters.

## SequentialAgent

SequentialAgent runs its children in their declared order and passes a shared
InvocationContext. A worker can store output under an `output_key`; a later worker
can consume that state. The controller does not ask a model which stage comes
next. Nested sequential groups can organize a larger ordered pipeline.
[Official sequential workflow guide](https://adk.dev/agents/workflow-agents/sequential-agents/).

Installed-source observations: `_run_async_impl` iterates `sub_agents` and consumes
each child's asynchronous event stream before advancing. Pause/resume handling
can stop an invocation before the remaining children. Therefore “sequential”
means ordered execution when the invocation progresses, not unconditional
completion despite failures, cancellation, or a paused invocation.

MarketTwin should use this shape for planned journeys that run once. Deterministic
recording must follow the assigned journey before collection begins. Browser
contexts still need explicit isolation: a sequential wrapper's shared state does
not create separate browser sessions or make persona observations independent.

## ParallelAgent

ParallelAgent starts children concurrently. Results may arrive in a different
order, so it fits independent tasks followed by an explicit collection stage.
It does not fit a requirement that each browser agent finish before the next
starts. Concurrent work also requires explicit handling of shared resources and
result handoffs.
[Official parallel workflow guide](https://adk.dev/agents/workflow-agents/parallel-agents/).

Important implementation nuance: the installed Python code creates branch
InvocationContexts with `model_copy()` and separate branch paths, then merges
event streams using concurrent tasks. Branch history separation is not proof
that every underlying mutable object or browser resource is deeply isolated.
We should not rely on the documentation's broad isolation wording to infer
separate databases, sessions, or tool instances. MarketTwin already establishes
those boundaries in application code; keep them explicit.

## LoopAgent

LoopAgent repeats its child sequence until a stopping condition or iteration
limit is reached. It is useful for bounded critic/revision cycles. The official
pattern uses an escalation event to exit.
[Official loop workflow guide](https://adk.dev/agents/workflow-agents/loop-agents/).

Installed-source observations: `max_iterations` defaults to None. The run loop
checks `event.actions.escalate` and invocation pause signals. Its iteration test
uses a falsy-value check; callers must not treat zero as a reliable disabled-loop
setting. A positive explicit bound is needed for any retained loop.

MarketTwin's current LoopAgent selects a different already-planned journey each
iteration rather than retrying a journey. That works, but a direct sequential
group expresses the one-pass requirement more clearly and removes the dispatcher
and last-iteration escalation bookkeeping. No automatic browser replay should
be introduced by this simplification.

## Custom agents and BaseAgent

BaseAgent is the common foundation, not a ready-made reasoning agent. Subclasses
implement application-controlled execution and emit ADK events. A custom agent
can implement conditional control flow or orchestrate children; those behaviors
must be coded explicitly.
[Official custom-agent guide](https://adk.dev/agents/custom-agents/).

MarketTwin's WorkflowStage is a small BaseAgent adapter around an existing
operation. Planning handoff, recording, and collecting durable results do not
require another LLM. Keep these stages deterministic and identify them accurately
in the flow. A UI should not invent prompts, temperatures, or model names for
them. Under the requested product rule, these adapters remain leaves.

## Modern Workflow graphs and dynamic workflows

ADK 2 adds Workflow graphs that combine agents and deterministic code through
explicit edges. Graphs can express branching, nested workflows, and data passing.
Dynamic workflows support application-controlled loops and conditional execution
when a fixed graph is insufficient.
[Official graph guide](https://adk.dev/graphs/),
[dynamic workflow guide](https://adk.dev/graphs/dynamic/).

Local 2.5.0 exports `Workflow` from `google.adk`. SequentialAgent, ParallelAgent,
and LoopAgent are decorated as deprecated in favor of Workflow, with removal
planned for a future version. Their local warning also states that Workflow
cannot yet be used as an LlmAgent subagent. Deprecation is real, but it is not a
reason to combine an SDK migration with the immediate UI correction.

Recommendation: preserve the pinned version for the minimal ordered-container
change, document its compatibility scope, then assess a separate Workflow
migration with equivalent ordering, failure, persistence, cancellation, and
evidence-isolation tests. Do not silently upgrade the SDK or represent Workflow
as the same runtime type as SequentialAgent.

## Collaborative coordinators and modes

Collaboration is an architecture using coordinating agents and specialized
children, not a new agent class. The documented modes are chat, task, and
single-turn; they affect user interaction and returning control to the parent.
The current collaboration page notes a Python graph task-mode limitation.
[Official collaborative workflow guide](https://adk.dev/workflows/collaboration/).

A coordinating LlmAgent chooses delegation dynamically. That does not guarantee
every worker executes in a prescribed order. MarketTwin's requested flow should
therefore use deterministic orchestration, with model reasoning inside each
worker. Agent count, shared prompts, and agreement do not increase evidentiary
independence.

## ManagedAgent

ManagedAgent connects to Google's server-hosted managed agents. The documentation
marks Python support from 2.4.0 as Preview; managed reasoning and tools execute
remotely rather than through the same local function-tool lifecycle.
[Official managed-agent guide](https://adk.dev/agents/managed-agents/).

Installed 2.5.0 lazily exports ManagedAgent. Its implementation rejects
client-executed function tools and supports server-side tools and remote MCP
specifications. This makes it unsuitable as a simple replacement for our current
journey-bound in-process MCP browser tools. Adoption would require a separate
execution/evidence contract, not just changing an agent type in YAML.

## RemoteA2aAgent

RemoteA2aAgent adapts a remote agent into ADK using the Agent2Agent protocol and
an agent card. This is different from MCP: A2A integrates an agent service;
MCP exposes tools. Google's Python consuming-agent guide marks A2A experimental.
[Official A2A consuming guide](https://adk.dev/a2a/quickstart-consuming/).

Installed-source observations: the adapter subclasses BaseAgent, resolves an
agent card, converts messages/events, manages remote task/session state, and
provides timeout and client-lifecycle configuration. A remote output would still
need validated ownership, provenance, and schema checks before it could support
a MarketTwin finding. No remote-agent feature is necessary for the current goal.

## RoutedAgent and model routing

RoutedAgent uses a routing function to select an agent, with documented fallback
behavior before output begins. It differs from fixed list execution and from
LLM-chosen delegation. The current documentation labels this feature TypeScript
experimental; do not expose it as an available Python agent type here.
[Official agent-routing guide](https://adk.dev/agents/routing/).

Model routing selects a model and is a different concern from agent structure.
Neither is needed to satisfy sequential execution in MarketTwin.

## YAML and state boundaries

Google documents an experimental Agent Config YAML loader. Its current guide
lists restrictions, including Gemini model support. That is distinct from
MarketTwin's strict prompt-draft YAML and controlled runtime builder.
[Official Agent Config guide](https://adk.dev/agents/config/).

MarketTwin should keep its existing validated YAML format: no arbitrary Python
imports, unregistered tool names, or editable historical ownership fields. In the
next schema correction, SequentialAgent should contain only orchestration
identity and ordered children; model settings belong to LlmAgent children. Existing
drafts need an explicit compatibility path because the current schema puts
temperature/tools on the sequential configuration and applies them to an implicit
reporter. Do not show a supposedly native ADK YAML example that the current API
cannot actually accept.

Session state is a handoff mechanism, not a substitute for durable product
records. Event state deltas and output keys help later stages consume prior work.
[Official session-state guide](https://adk.dev/sessions/state/).
MarketTwin must continue using PostgreSQL commits and owned artifact records as
the source of truth; never place browser handles or credentials into serialized
state.

## Proposed minimal reconfiguration, not yet applied

Implementation update (2026-10-10): the user resumed the prompt/flow work. The
separate settings form is removed; settings are edited in YAML. The flow groups
all recorded persona runtimes under Sequential Agent after Meta, then Collector
and Evaluation/Report. Flow panels scroll independently. The outer journey
LoopAgent/dispatcher is replaced by a real SequentialAgent group. Model settings
remain applied to actual LLM workers, but the existing compatible rerun YAML
schema still includes reporter defaults on its sequential configuration; a full
schema migration to explicit reporter-child settings is not part of this patch.
The numbered list below records the researched design, not a claim that this
remaining schema migration was performed.

1. Remove the separate agent settings form. Edit the approved rerun configuration
   only inside YAML, with actionable validation messages.
2. Make SequentialAgent the only supported container; make each LlmAgent a leaf
   with its own custom name, low temperature, instruction, and registered tools.
3. Replace the outer JourneyLoop and PlannedJourneyDispatcher with a sequential
   group containing the validated, bounded journey sequences in execution order.
4. Preserve each journey's isolated browser/session, exact assigned identity,
   result commit, timeout/status handling, and final collection completeness checks.
5. Keep evaluation/reporting in their actual lifecycle phases. The current
   evaluator runs in another worker; do not draw it as a child of an ADK root
   unless the runtime truly changes to match that representation.
6. Render actual per-test agent types and ordered children. Bound the flow panel
   and scroll it independently; wrap legacy names and keep save actions reachable.

Proposed workflow shape:

```text
SequentialAgent: run
  BaseAgent leaf: plan and persist
  SequentialAgent: planned journeys
    SequentialAgent: journey 1
      BaseAgent leaf: execute isolated journey runtime
      BaseAgent leaf: record committed result
    SequentialAgent: journey 2
      BaseAgent leaf: execute isolated journey runtime
      BaseAgent leaf: record committed result
  BaseAgent leaf: validate and collect

Separate lifecycle phase: evidence evaluation -> report
```

The inner runtime may itself be a SequentialAgent of LlmAgent helpers and a final
LlmAgent reporter. It is invoked by the execution stage; it must not be presented
as a direct subagent relationship unless the recorded runtime tree supports that.

## Verification required after implementation

- Real ADK execution order, no overlapping journey execution, and exactly one
  execution/commit per planned assignment.
- Failed/timed-out/policy-blocked outcomes remain collected; infrastructure errors
  stop before falsely successful collection.
- Duplicate plans, wrong journey keys, depth overflow, and incomplete collections
  remain rejected.
- Only sequential containers have children; every LLM leaf has distinct identity
  and correct model/tool snapshot, with unchanged evidence ownership.
- Strict YAML rejects unknown fields/tools, aliases/duplicates, invalid temperatures,
  name collisions, and children on leaves; supported legacy drafts migrate safely.
- Helper prose cannot override the reporter schema or confirm a product defect.
- Desktop/mobile browser checks prove long names fit, flow scrolls independently,
  and YAML save/reset/rerun controls remain reachable without forced clicks.

## Local reference map and status

Inspected installed source under `.venv/Lib/site-packages/google/adk/`:
`agents/__init__.py`, `base_agent.py`, `llm_agent.py`, `sequential_agent.py`,
`parallel_agent.py`, `loop_agent.py`, `_managed_agent.py`, `remote_a2a_agent.py`,
and package `__init__.py`. Package METADATA confirms version 2.5.0.

MarketTwin implementation references:

- `packages/shared-python/src/markettwin_shared/agent_configuration.py`: current
  strict rerun schema, LLM leaf restriction, names, tools, bounds.
- `services/execution-orchestrator/src/markettwin_execution_orchestrator/agents/configuration.py`:
  runtime tree and implicit final reporter construction.
- `services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/adk_workflow.py`:
  current SequentialAgent + LoopAgent + custom dispatcher structure.
- `docs/ADK_WORKFLOW_SESSION_STATE_AND_COLLECTION.md`: current durable handoffs.
- `docs/V1_FINDING_INTEGRITY.md`: confirmation and evidence requirements.
- `docs/CURRENT_STATE.md` and `docs/NEXT_SESSION.md`: feature and release checkpoint.

Research was completed without runtime changes. The subsequent authorized
prompt/flow implementation is documented in the update above. Dependencies
remain pinned; there was no SDK upgrade or native Agent Config loader adoption.
