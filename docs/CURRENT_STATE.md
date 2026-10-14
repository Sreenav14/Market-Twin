# Current MarketTwin checkpoint

## Latest checkpoint: new MKT deep-testing plan (2026-10-14)

The user requested detailed analysis of the new root MKT.md and implementation,
then explicitly requested multiple engineering agents working in parallel.
Three agents delivered independent T00/T01 work; runtime journey execution remains
sequential. See docs/agent-quality/IMPLEMENTATION_ROADMAP_2026-10.md for all T00–T13
assignments, dependencies, current-code discrepancies and acceptance gates.
This new task numbering supersedes the older TASK00–09 sequence below for this work.

T00 baseline is recorded in docs/agent-quality/BASELINE_2026-10.md and its sanitized
failure matrix. Branch/HEAD still match the MKT audit, but the dirty workspace has
newer planner/persona budgets (4096/2048), report validation, failed-action capture,
exact evidence linkage and journey API/UI. These existing changes were preserved.
Read-only historical DB inspection failed ConnectionRefusedError; live remote HEAD
was not fetched. Historical detection counts remain unvalidated, not fresh metrics.

T01 implemented a separate deep_testing_app fixture, independent versioned manifest,
and run_deep_fixture_benchmark.py. Eight core cases cover valid/invalid/boundary,
dependent controls, recovery, async state and navigation. Good/bad variants share
the feature; bad produces six case contradictions (not six independent root bugs).
The existing historical v1 fixture remains intact. The historical live benchmark
CLI now requires --local-development. New direct runner starts ephemeral loopback
only, isolates cases, restricts network/service workers, and writes actual values,
hashes, screenshots and JSON/Markdown. See docs/agent-quality/FIXTURE_BENCHMARK.md.

Verification: 75 focused existing backend tests passed; 15 final combined new
fixture/scoring tests passed (9 real Chromium +6 scoring/CLI). Ruff and strict
Pyright across four affected Python files pass with zero errors. Fresh frontend
typecheck/build and 27 unit tests pass; existing 544.84 kB bundle warning remains.
Direct good/bad runner executions each complete 8/8 cases with 8/8 ground-truth
agreement. Generated evidence is .local/deep-fixture-good and deep-fixture-bad.
Three diagnostic probes explicitly remain not_executed in runner output; fixture
tests separately verify policy/probe states. No fresh autonomous pipeline/model
run, dependency install, migration, commit, push, deployment or public target test.
Whole-workspace git diff --check still flags pre-existing trailing whitespace in
agents/schemas/plan.py; this session did not change that file.

T02–T08 and the minimum T11/T12 surfaces are now implemented in the working tree.
Versioned feature plans, scoped inspection, safe check/focus/viewport actions,
deterministic assertions, sequential case execution, assertion-aware report
diagnostics, assertion-grounded findings, case/step read APIs, and the feature-case
result panel exist. A recorded result stays unconfirmed until evaluation. This
session added budget skip accounting, repeated read-only assertion checks, report
contradiction diagnostics, case pagination/steps, and pending-result UI copy.

Verification on 2026-10-14 after those additions: 72 focused planner, assertion,
report, evaluator, and case-API tests passed on recheck, including real Chromium
assertion checks. Feature-case UI tests previously passed 2. The report boundary
now reads assertion JSON stored on assertion steps; a contradictory persona pass
becomes inconclusive. Ruff is clean on the new production modules. Strict Pyright
reports no errors in the changed production modules.
Pre-existing long lines in control-api case tests and deep_run.py were left
unchanged. No model experiment, authorized external application, migration,
commit, push, or deployment was run.

Ordinary deep runs now freeze the validated feature scope into the run snapshot
before execution. The evaluator still confirms a finding only when that same scope
contains the matching requirement assertion. Inferred expectations stay
unconfirmed. Case action rows use the persisted step status, and failed-assertion
counts count individual checks. Deep mode remains opt-in, and the executor remains
deterministic until an accuracy benchmark justifies bounded recovery.

Still open: T09 has no measured model/budget winner because no paid model matrix
was run. T10 has no reviewed form, list/filter, and navigation proof on authorized
applications. T12 has no live backend-to-browser participant trial. T13 release
checklist remains NO-GO. The deterministic case executor is not a claim that an
LLM persona performed observe–act–assert. Fixture truth still cannot be enabled
merely by a configuration snapshot. Do not rebuild already implemented evidence
pages or infer that previous local services are running from stale PIDs below.

Updated 2026-10-10. This is the authoritative current state. Historical decisions
and superseded checkpoints remain in SESSION_HANDOFF.md and V1_BENCHMARK_RESULTS.md.
The user's latest direction is build everything requested, then test/benchmark;
do not return to the earlier detection-before-UI instruction.

## Implemented

### Revised SAM architecture documents (2026-10-12)

Created docs/sam-v2/README.md, ARCHITECTURE_V2.md, RUNTIME_CONTRACTS.md and
BUILD_AND_VALIDATION_PLAN.md in response to the user's request for new architecture
docs. They carry forward the under-$20 operating constraint, proposed $19 envelope,
existing hardware first and later Mac mini migration. They define bounded helper
delegation, verification/repair, durable execution and separately evaluated GEPA.
Phone/SMS remain full-V1 requirements with cost-gated staging. These are design
documents, not an implemented or integration-tested SAM system.

### SAM budget and later hardware decision (2026-10-12)

User explicitly requires V1 operating costs under $20/month and plans to buy a
Mac mini later. This supersedes the earlier $100 recommendation below. Updated
the comprehensive SAM audit with a provisional $19 total envelope, existing
hardware first, no automatic spend increase and measured Mac migration/sizing.
Web-first staging and later phone/SMS are recommendations, not an approved
deletion of full-V1 channel requirements. No purchase or implementation started.

### Separate comprehensive SAM audit (2026-10-12)

Completed docs/sam-audit/SAM_ARCHITECTURE_AUDIT_2026-10-12.md in the user's
requested 14-section order, with 20 provisional ADRs, requirement traceability,
primary-source research, cost assumptions and 12 pending integration experiments.
User requested recommendations for unspecified constraints: existing hardware,
32 GB/1 TB planning target, three bounded workloads and $100/month pilot cap.
Two isolated stdlib/SQLite mechanisms were executed with negative/control variants:
lost-receipt replay duplicates without receiver deduplication; ten forced budget
races overspend without atomic admission and stay within budget with it. Source
and raw results are in docs/sam-audit. These are not SAM/PostgreSQL runtime proof.
Verdict: conditional go for bounded prototype; no production-readiness claim.
No application code, infrastructure, account settings or services were changed.
The existing MarketTwin plan remains unchanged.

### Separate SAM plan assessment (2026-10-11)

Reviewed the user's attached SAM_MASTER_PLAN_V1.md as a separate design request.
See SAM_PLAN_REVIEW_2026-10-11.md for feasibility findings, bounded delegation,
evidence-driven repair, GEPA/GA/RL assessment, and 36 proposed adversarial tests.
This was a document review with primary-source research, not a SAM runtime test
or implementation. No MarketTwin application code or running services changed;
the existing MarketTwin execution sequence remains unchanged.

### Agent prompt 500 fix and temporary output cleanup (2026-10-10)

MT-000024 completed, but its prompt endpoint rejected aliases generated by its
own YAML serializer because recorded structure and rerun configuration shared
an object. PromptYamlDumper now expands shared values without aliases, including
the internal validation serialization. Strict rejection of user-supplied aliases
remains. All24 prompt regressions pass; Ruff/Pyright pass. A read-only invocation
of the endpoint with Sup_1's real records returned9 agents successfully. API
restarted PID33564/session29762; health is OK.

At the user's request, removed95 generated testing files: one-off .local probes,
benchmark diagnostic exports/logs/screenshots, pytest temporary directories,
Playwright result output, artifacts/v1 UI screenshots, and web/debug.log. Kept
regression tests, benchmark harness/fixtures, reference docs, artifacts/runs,
database/object-storage records, dependencies and Kafka data. Future agents must
not rely on deleted .local diagnostic scripts.

### Queued test dispatch diagnosis (2026-10-10)

Live checks for MT-000024 (Sup_1, run31619f3d-64f4-4519-a3c9-c3cd7f642a30)
showed Kafka health connected and run.requested already published with zero
failure attempts. Earlier SSL logs were not the current blocking condition.
No execution worker was running. The execution worker was restored using the
existing .env (session64769) and connected successfully to its Kafka consumer
group. MT-000020 started running first; MT-000024 remains queued behind it in
normal sequential execution. Evaluation worker was also started (session25432).
Do not replay the command, bypass the queue, or label MT-000024 running before
its persisted status changes. Kafka connectivity alone does not prove worker
availability or completed end-to-end reporting.

### Link ingestion outage and browser research (2026-10-10)

The knowledge worker was offline on8010. It is restored; a real synthetic preview
generated knowledge/skill. Both identified failed local link entries were retried
and now need review, with4/6 proposed skills and no processing errors. Nothing was
approved. Link research now renders JavaScript, expands read-only navigation and
discovers same-origin pages recursively, bounded to30 pages/120 seconds. It saves
URLs, observed text/actions and coverage gaps through existing draft ingestion.
14 link regressions pass, including real Chromium JS/disclosure/deep-link checks;
Ruff/Pyright, frontend typing/build pass. See LINK_BROWSER_RESEARCH.md for details.
Final focused link/client/processor/ingestion suite:44 passed. Ingestion form
unit tests:8 passed. No unrelated benchmark was rerun.
Current API PID21100/session59212; worker PID34236/session44162. Kafka SSL remains
a separate unresolved gate. Successful retries used saved source bundles; they
do not prove upgraded browser coverage of the user's original sites.

### Meta-generated coverage clarification (2026-10-10)

Meta's prompt and input blueprint now prioritize application-specific end-to-end
flows with distinct persona behavior, recovery/final-state checks and coverage
gaps. Output budget is 4,096 instead of 1,024. Existing models are reused; runtime
agents remain created from Meta's actual persona/mission plan. New structural
validation and mandatory guidance for edited prompts were added. Focused suite:
38 passed; actual model/browser quality validation remains pending. Read
META_PLANNING_BLUEPRINT.md before claiming comprehensive or improved live coverage.

### Latest prompt/flow correction (2026-10-10)

The user resumed prompt/flow implementation after the ADK research. Agent Settings
now shows Meta -> Sequential Agent (recorded journey subagents) -> Collector ->
Evaluation and Report. Prompt settings are YAML-only; the separate form is removed.
Flow panels scroll internally on desktop/mobile and long historical names wrap.
The real outer ADK runtime uses a SequentialAgent journey group, with no LoopAgent
or custom dispatcher. Only sequential containers hold children in that workflow.
Eight runner regressions pass, including no overlapping executions and rejecting
over-depth plans before browsing. Existing per-journey evidence ownership, durable
collection, failures/timeouts, and reporter-author checks remain intact.

Validation: 44 focused backend checks passed before the added depth test; the
updated workflow suite then passed all 8 checks. TypeScript, runtime Pyright and
Ruff pass. All four focused desktop/mobile prompt + run-flow browser checks pass,
including YAML save/reset/rerun, accessibility and internal scroll styling. The
previous mobile Save interception is resolved. Production build passes; its
existing large-chunk warning remains (544.75 kB JS).

The compatible rerun YAML schema is retained: sequential configuration fields
provide defaults for the implicit reporter, with separate settings on extra LLM
children. A migration to explicit reporter-child-only fields remains a separate
schema change; do not claim native ADK YAML or a completed Workflow SDK migration.
See ADK_AGENT_STRUCTURE_RESEARCH.md for primary sources and current decisions.

- Evidence integrity: repeated persona claims remain Needs Verification, retain
  persona/journey/criterion/step references, never raise severity or confirmed
  totals merely through repetition. Browser evidence is required for confirmation.
- Authorized journey list/detail API: latest attempt, ordered paginated steps,
  bounded artifact metadata, safe summaries, linked classified findings. Exact
  selected-step evidence only; no unrelated screenshot fallback.
- Premium public homepage, comprehensive How page, accessible finite motion and
  reduced-motion support, working login routing and shared warm/forest theme.
  Workspace navigation and pending-evaluation messages have been simplified.
- Optional short test name and PostgreSQL identity number displayed as MT-000042.
  Full goal remains in test configuration. Identity migration f2a931c64780 is applied
  to the local DB; existing rows backfilled. Concurrent insert/backfill check passed.
- Agent Settings: project/application -> tests -> ordered per-test agent flow.
  All recorded roles are visible, including read-only evaluator/visual verifier.
  Planner/persona reruns support custom names, LlmAgent/SequentialAgent, low
  temperature (default 0.05, bounded 0?0.2), approved tools, and up to three extra
  LLM children before the structured reporter. Real ADK trees and full child
  settings are snapshotted; only primary reporter final events are parsed.
  Historical snapshots remain immutable. Requested/effective temperature are
  distinguished when a reasoning model controls sampling itself.
- Public link knowledge ingestion: bounded HTML/text research (up to five pages),
  source URL/content preservation, draft knowledge/skill generation through the
  existing pipeline, explicit review/approval. Public IP validation, pinned
  connections, redirect checks, TLS identity, byte/time/page limits. No arbitrary
  tools or automatic skill approval.
- Evidence access repair: API was signing local MinIO links with ambient AWS
  credentials instead of configured .env credentials (403 InvalidAccessKeyId).
  Configured signer/storage credentials now produce HTTP 200 image/png; local
  screenshot probe returned 39,059 bytes. Same fix covers knowledge source access.
- User screenshot showed long historical names covering the settings form.
  Agent grid items now allow shrinking and names wrap inside cards/headings/tree.
  Desktop/mobile long-name browser regression is being finalized.

## Validation and benchmark

- Journey API: 22 passed. Naming/create/knowledge API: 15 passed. Local PostgreSQL
  identity concurrency/backfill: 1 passed. Frontend units: 26 passed before adding
  one link test; targeted ingestion suite now 8 passed. Production build passed
  (existing ~547 KB JS chunk warning remains). Frontend typecheck passed.
- Public/results browser suite: 22 passed. Main/knowledge fixes: 11/12 then remaining
  mobile knowledge passed. Updated project/test agent and knowledge flows: 4 passed.
  Sequential subagent desktop/mobile and axe checks: 2 passed. Final long-name
  regression is in flight; see NEXT_SESSION.md for process/session status.
- Backend final suite: 405 passed, 4 skipped, one outdated expected visual-agent
  name. Expected name was updated to Agent_VisualVerifier_1; focused snapshot suite
  passed 2 tests. Earlier final focused feature/evidence suite: 92 passed.
- Changed production Python Ruff passed; strict Pyright passed agent configuration,
  planning/journey runtime, link research and API. Remaining credential/evaluator
  typecheck output is being collected. No dependency installs, commits or deployment.
- Working benchmark b9c94c59-d47b-4988-9037-abf5d6c443dd: completed, six journeys,
  zero findings, 22 steps, 71/71 physical artifacts.
- Latest broken benchmark 25f6f762-c5b7-4910-8be7-a3aaeb41e212: completed report
  b75a07fe-9123-4047-a8f1-10b3f723ef47; 12 journeys, 77 steps, 213/213 physical
  artifacts. Product classifier yields 7 stored observed-product issues and 14
  unverified observations. These seven are not yet manually validated detections.
  This benchmark predates the latest agent-setting/link changes. No fixture run
  is active. Do not run shared port-5191 fixture benchmarks concurrently.

## Remaining release gates

Detection recall and repeatability remain below the release contract. Manually
review latest confirmations against exact images/actions and ground truth before
claiming validated detections. Do not loosen evidence rules to raise benchmark totals.
The local API outbox previously logged Kafka SSL record-layer failures; verify the
broker connection before declaring Start-to-report pipeline ready. Login is local
identity access, not fully provisioned production authentication. Review long-name
UI screenshot, finish final checks/docs, and test real sequential rerun and link
skill output on a representative public documentation source before deployment.

## Running local preview

Vite localhost:5173, session 97555. API localhost:8001, PID 40924/session 8472.
Default sandbox shell startup fails with helper setup refresh errors; reviewed
escalated shell calls work. Never expose .env credentials or signed URLs in outputs.
