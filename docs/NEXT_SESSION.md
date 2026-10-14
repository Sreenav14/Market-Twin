# MarketTwin next-session handoff

Read CURRENT_STATE.md first. User requests remain cumulative; latest build-first
instruction supersedes detection-first. Preserve evidence integrity and avoid
repeated analysis/benchmarks. Work sequentially and give concise progress updates.

## Immediate continuation

Newest fix: MT-000024 completed; its Agent Prompts view failed because generated
YAML aliases were rejected by the strict editor validator. PromptYamlDumper now
expands shared objects; both display and internal validation use it.24 prompt
regressions and Ruff/Pyright pass; real Sup_1 endpoint invocation returned9 agents.
API now PID33564/session29762, health OK. Removed95 disposable test outputs and
one-off probes at user's request; retain tests, references and runtime evidence.

Previous queue diagnosis: MT-000024's command was published and Kafka connected.
The missing execution worker was restored (session64769).
Evaluation worker started in session25432. Check their latest logs/status before
starting duplicate consumers. Do not redispatch or directly replay browser work.
The previous SSL diagnosis was incomplete; distinguish broker health, publication,
consumer availability, active execution, and report completion.

Latest issue resolved: knowledge worker restored on8010, two failed link entries
regenerated and awaiting review. New submissions use recursive rendered browser
research (30 pages/120 seconds), not the old five-page HTML reader. Read
LINK_BROWSER_RESEARCH.md. Worker PID34236/session44162.
Do not auto-approve generated skills or claim exhaustive site inspection.

Newest clarification: Meta must design useful end-to-end coverage, not just fit
generic agents into a fixed UI. Template/input/budget/validation improvements are
implemented; read META_PLANNING_BLUEPRINT.md. Next meaningful validation is a
representative actual Meta plan and browser run, mapping requested functions to
criteria and executed evidence. Current scope still caps three personas and
1/2/4 missions by depth. Do not call prompt regressions proof of live agent quality.

Latest steering: the prompt/flow change is implemented and verified. Read
CURRENT_STATE.md and ADK_AGENT_STRUCTURE_RESEARCH.md. The settings form is removed;
YAML is the editable source. Meta precedes a sequential journey group, then
Collector and Evaluation/Report. Outer LoopAgent/dispatcher are removed; flow
scrolling and mobile Save interception are fixed. No SDK upgrade was made.

Validation: 44 focused backend tests; updated workflow suite 8 passed. Four
focused desktop/mobile E2Es passed. TypeScript, runtime Pyright/Ruff and build pass.
Do not recollect old sessions 53124/56454 or repeat those checks without new changes.
The existing rerun schema still maps sequential temperature/tools defaults to an
implicit reporter. Explicit reporter-child schema migration is not implemented.

Remaining release work: audit benchmark confirmations against exact browser
criteria/evidence; check representative real sequential rerun and linked-source
skill output; verify Kafka outbox connectivity. These are existing release gates,
not evidence that the focused prompt/flow checks failed. Preserve uncertainty and
all historical reports. The current broad goal tool may still show paused; the
user explicitly resumed this prompt/flow task. Do not mark the entire build goal
complete based solely on this patch.

## Key implementation paths

- Shared strict settings: packages/shared-python/src/markettwin_shared/agent_configuration.py
- Actual ADK tree: services/execution-orchestrator/src/markettwin_execution_orchestrator/agents/configuration.py
- Runtime application/snapshot/report author guard: workflow/planning.py,
  workflow/journey_executor.py, workflow/multi_persona_executor.py in that service.
- Draft YAML/fork API: services/control-api/src/markettwin_control_api/api/agent_prompts.py.
  Uses existing AgentPromptDraft; no new agent config store. Metadata tree contains
  configuration for future reruns. Old YAML without new fields remains compatible.
- UI: AgentPromptsPage.tsx, AgentTree.tsx, ProjectAgentBrowser.tsx,
  lib/agentPrompts.ts, styles/agent-prompts.css and product-theme.css.
- Link research: services/control-api/src/markettwin_control_api/knowledge/link_research.py;
  API POST /api/v1/workspaces/{workspace_id}/ingestion/link delegates to existing
  ingest_source. IngestionPage.tsx offers file/link. Existing worker grounds skill
  drafts against extracted evidence; source bundle retains every researched URL.
- Evidence credentials: control-api config.py, evidence/artifact_url_signer.py,
  api/artifacts.py, api/ingestion.py and knowledge/storage.py. The one-off signed
  screenshot probe was removed after verification; regression tests remain.
- Test names: NewRunPage, lib/format.ts testTitle/testReference, test_run API,
  TestRun.test_number identity model, migration f2a931c64780 (already applied locally).

## Reference map and reasons

- MKT.md: original product/build roadmap. Current behavior is bounded V1, not every
  aspirational architecture feature. User asks minimal models/accurate evidence.
- docs/V1_PRODUCT_CONTRACT.md: current behavior, agent/link contract, release limits.
- docs/V1_FINDING_INTEGRITY.md and V1_PERSONA_REPORT_VALIDATION.md: confirmation,
  ownership, retained observations and deterministic criterion/report boundaries.
- docs/V1_FAILED_ACTION_EVIDENCE.md: safe read-only recovery without erasing failure.
- docs/V1_BENCHMARK_RESULTS.md and V1_BASELINE.md: historical benchmark evidence and
  ground truth; results cannot be promoted based on persona agreement.
- docs/BROWSER_ARCHITECTURE.md, ADK_WORKFLOW_SESSION_STATE_AND_COLLECTION.md:
  Python controlled browser boundary, real ADK ordering and state/collection.
- docs/AGENT_PROMPTS_AND_RERUNS.md: immutable history, personal drafts, explicit Start.
  New project grouping/strict config/all-role flow supersedes old flat-directory notes.
- docs/INGESTION_WORKFLOW_UI_AND_REVIEW.md, KNOWLEDGE_GROUNDING_FIX.md and
  SOURCE_ASSET_BOUNDARY.md: source-backed skill drafts, review and approved knowledge.
- docs/SESSION_HANDOFF.md: full earlier history and user decisions. Do not reset
  the dirty worktree; many edits predate this session. No commits/deployments made.
- Accessibility/motion primary references used for public UI:
  https://web.dev/articles/animations-guide
  https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html
  https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html
  https://www.w3.org/WAI/tutorials/forms/

## Goal and limitations

Earlier homepage/How/login goal is marked complete after verified UI/build work.
Current explicit goal tracks agent flows/settings, links/skills, evidence repair
and documentation; mark complete only after remaining checks are collected. This
is feature completion, not production-readiness. Detection accuracy, local Kafka
connectivity and representative real-input validation remain release gates.
