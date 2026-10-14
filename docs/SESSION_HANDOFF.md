# MarketTwin session handoff

For the authoritative current checkpoint, read [CURRENT_STATE.md](CURRENT_STATE.md)
first. The checkpoint entries below preserve audit history and may be superseded.

Updated 2026-10-10. Read this before continuing. This document is a continuity
record, not a production-readiness claim. Update it before ending a session or
approaching its token/context limit; the user explicitly requested this.

## Latest checkpoint (read first)

### Deep-feature local gaps closed; release gates remain open (2026-10-14)

The user asked to complete the remaining MKT T00–T13 work. T00/T01 were already
done. T02–T08 code and the minimum case API/UI already existed ahead of the prior
checkpoint. This session added deterministic assertion regressions, repeated
read-only checks, budget skip reasons, persona-report contradiction diagnostics,
recorded-but-unconfirmed case results, bounded case/step paging, and pending-result
UI copy. Focused tests: 35 passed. Feature-case UI tests: 2 passed.

T09 and T10 were not executed: they need paid model comparisons and authorized
applications beyond the local fixture. No human one-minute comprehension trial
was run. Release remains NO-GO. `deep_feature_v1` stays opt-in, and fixture truth
is still not loaded from an ordinary configuration snapshot.

### New deep-feature plan: parallel T00/T01 implementation (2026-10-14)

User requested analysis/implementation of root MKT.md, then explicitly authorized
multiple agents for optimal parallel work. Baseline, fixture and harness agents
worked on disjoint paths; root reviewed/integrated, wrote the full T00–T13 roadmap,
ran frontend checks and repeated direct benchmark commands. No runtime persona
parallelism was introduced. The new plan's T00–T13 numbering is distinct from the
old TASK00–09 sequence recorded below.

Deliverables: docs/agent-quality/BASELINE_2026-10.md and sanitized failure matrix,
IMPLEMENTATION_ROADMAP_2026-10.md and FIXTURE_BENCHMARK.md; separate
services/execution-orchestrator/tests/fixtures/deep_testing_app/index.html;
tests/benchmarks/markettwin_deep/manifest.json; run_deep_fixture_benchmark.py;
test_deep_testing_fixture.py and test_deep_fixture_benchmark_scoring.py.
run_v1_benchmark.py changed only to require explicit --local-development at CLI.
All historical v1 fixture files and substantial pre-existing workspace edits kept.

Current-code audit supersedes stale MKT inventory: 4096 planner/2048 persona output
budgets; report-validation/failed-step evidence capture and journey/evidence API/UI
already implemented. Explicit TestCaseSpec, independent assertions, deep case
execution/coverage still missing. Do not duplicate earlier integrity fixes.

Measured checks this session: 75 focused backend checks; 27 frontend unit tests;
frontend typecheck/build; 15 combined new fixture/scoring tests; Ruff and strict
Pyright four affected Python files 0 errors. Build retains 544.84 kB chunk warning.
Direct fixture good/bad 8/8 executions, 8/8 oracle agreement each, bad 6 contradictions
plus 2 successful controls. Root repeated both direct commands successfully. Reports
and exact screenshots in .local/deep-fixture-good and .local/deep-fixture-bad;
all 3 diagnostic probes report not_executed, with separate fixture policy checks.
These are non-AI fixture truth, not autonomous detection measurements.

Historical sanitized DB read failed ConnectionRefusedError before records read;
do not invent current action timelines/model usage/precision/recall. Live remote
HEAD was not fetched; cached upstream/local HEAD 801c2b43... match. No model calls,
public-site runs, service starts, installs, migrations, commits or deployment.
Whole-workspace whitespace check reports pre-existing plan.py trailing whitespace;
left unchanged under surgical-edit policy. Existing service/PID notes are stale.

Next work package is T02 per MKT, using frozen T01 manifest as fixture evidence.
Plan/spec/bridge must keep legacy 3-persona Cartesian behavior and old reports.
Parallel development may continue under roadmap file ownership, but integrate
dependent assertion/runtime/evaluator/API/UI stages only after their gates pass.
No release or agent-quality milestone has been declared complete.

### Revised SAM architecture package delivered (2026-10-12)

User requested new architecture docs. Created the four-file docs/sam-v2 package:
README index, architecture, runtime contracts and phased build/validation plan.
It preserves the under-$20 ceiling and later Mac mini direction while making
spend admission, helper limits, permission boundaries, retry reconciliation and
GEPA promotion explicit. Proposed spending allocations and quality thresholds
still need measurement; original phone/SMS requirements remain cost-gated rather
than deleted. Prior audit and experiment evidence are linked. No application
implementation, purchases or deployment were performed.

### SAM budget supersedes audit's original recommendation (2026-10-12)

User: "under $20 later I will buy mac mini". Updated comprehensive audit to
record a total recurring V1 ceiling under $20, provisional $19 allocation
($12 models, $2 paid tools, $4 incremental power/backup, $1 contingency), and
existing hardware now / Mac mini later. Allocation is not measured feasibility.
No automatic budget increase; hardware is separate capital cost. Preserve
reasoning, verification and requested helpers; bound volume and optimizer runs.
Phone/SMS deferral remains proposed staging, not permission to remove required
channels. Later Mac configuration and compatibility must be measured. Earlier
$100 recommendations below are superseded. No purchases or product code changes.

### Comprehensive SAM architecture audit completed (2026-10-12)

User supplied a comprehensive 11-phase audit request in attachment
b3cdf77e-e449-4480-b770-3fbe5049d117/Pasted text.txt and then asked for constraints
recommendations. Delivered docs/sam-audit/SAM_ARCHITECTURE_AUDIT_2026-10-12.md:
14 required deliverable sections, 20 provisional ADRs, risk/technology matrices,
cost scenarios, growth analysis, 12 pending integration experiments and skeptical
second-pass corrections. Review scope is SAM, not a new MarketTwin code audit.
Original SAM plan and earlier GEPA review remain unchanged. Primary-source web
research covered runtime, model pricing, voice, retrieval, isolation, advisories
and GEPA issues. Some direct Perplexity/FCC pages failed; limitations disclosed.
Isolated experiments.py and experiment-results.json preserve successful local
crash/replay and concurrent budget results. First OS-temp attempt failed on
sandbox permissions before testing; successful run used audit-local temp files.
No paid provider experiment or SAM integration test was run. User repeatedly
requested progress; avoid further promises without producing reviewable output.
Final recommendation: existing hardware, bounded three-workload pilot, $100 cap;
32 GB/1 TB target conditional on measurements; $215 illustrative medium monthly
scenario is not a quote. No product code/services/deployment changed. Do not
begin SAM implementation unless subsequently requested.

### Separate SAM document review (2026-10-11)

The user requested a detailed feasibility/optimality assessment of the attached
SAM_MASTER_PLAN_V1.md, emphasizing a capable primary agent, requested helpers,
iteration, and recursive learning. Delivered SAM_PLAN_REVIEW_2026-10-11.md with
design gaps, concrete acceptance tests, proposed benchmark gates, and sources.
No executable SAM was supplied or tested; all runtime test cases are pending.
No SAM implementation, paid benchmark, agent creation, or vendor selection was
performed. User clarified GEPA (Genetic-Pareto), plus GA/RL; the review now
includes a bounded GEPA experiment, separate runtime/improvement loops, and 36
proposed adversarial tests. This assessment does not replace the MarketTwin plan.

### Newest checkpoint: UI, agent structure, links and evidence access

CURRENT_STATE.md and NEXT_SESSION.md now supersede the older checkpoint below.
User asks project/test agent flows, low temperature, names, sequential subagents,
approved tools, linked research generating reviewable skills, and a long-name
layout repair (provided image.png). Implemented using existing snapshots/drafts,
controlled browser tools and knowledge pipeline. Configured .env S3 credentials
fix the screenshot 403 InvalidAccessKeyId; probe now HTTP200 image/png.
Project/test flow and subagent interaction browser checks pass desktop/mobile.
Final feature/evidence tests92 pass. Broad backend405 pass/4 skip/one outdated name
assertion, now fixed and focused2 pass. Long-name browser check53124 and final
Pyright/probe56454 are in flight. API40924/session8472, Vite97555. Latest broken
benchmark25f6f762-c5b7-4910-8be7-a3aaeb41e212 has12journeys,77steps,213/213objects,
7 stored observed product issues and14unverified; seven confirmations still need
manual review. Benchmark predates newest agent settings. No production claim,
new fixture benchmark, dependency install, commit or deployment.


**Newest current checkpoint:** region run `ae957cff-0b52-4987-89ab-d43b42b8bd34`
finished report `c1c27372-d307-44e8-821b-84d899db07d6`, 75 steps/212 physical
artifacts, 4 visual confirmations (2 disabled/2 missing inline validation) and16
unverified observations. Images1115/1162 manually reviewed; correct named button
clicks precede focused capture. Navigation/Profile region image1119 reviewed but
VLM keeps all navigation unverified because destination is inline on source page.
Fixture now renders standalone Help guide/Profile views, changed ONLY after run
finished. Two real Chromium tests failed before/pass after. Complete238 tests,
Ruff/strictPyright pass. Future runs have fixture SHA256 config, old ones don't.
Working repeat `b9c94c59-d47b-4988-9037-abf5d6c443dd` is active shell71677,
`.local/v1-benchmark-working-destination.log`; verify then broken repeat on new
fixture. `.local/v1_benchmark_review.py` now returns safe fixture_sha256 too.
User detection-first choice remains: no API/UI implementation before this stage.

**Latest user steering:** user explicitly chose "Continue detection work before UI."
Keep TASK04 active; do not advance to TASK05/06 or call the benchmark passed.
New full region-capture repeat `ae957cff-0b52-4987-89ab-d43b42b8bd34` is running in
shell21738, `.local/v1-benchmark-broken-region.log`. Small persona prompt change
captures existing result containers/controls after the triggering action (never
missing expected text); after navigation capture actual observed destination
heading via focused tool (not original link/page-top heading). Harness brief
specifies inline validation beside field and preview status in its result section.
Prompt construction test passed and Ruff passes. Last complete backend suite236.
Replay unsatisfied step1023 manually viewed: actual disabled control present.
New full repeat is unreviewed; do not fabricate its outcome. If context gets short,
continue from CURRENT_STATE then this handoff; all exact reference docs below.
Harness now records fixture SHA256 in the existing configuration snapshot for
future runs; computed in asyncio.to_thread, Ruff/strict Pyright pass. Active run
started before checksum addition. No fixture content changed during this run.
Possible next improvement if navigation remains poorly observed: make fixture
navigation render a realistic separate destination view instead of showing a
destination inside a long page. Not implemented; inspect current results first,
preserve historical failures and repeat working navigation if fixture changes.

**Authoritative newest checkpoint:** target-context repeat `3d0be5e4-2d8c-40cf-80aa-a033011845b9`
finished report `30624052-db57-46e9-be47-b84330ed5328`, 84 steps, 220/220 artifacts.
Two disabled-control and two billing visual issues stored, fourteen observations.
Manual billing images 1065/1095 lack destination region; reject those confirmations.
New conservative guard in visual_evaluation downgrades unsatisfied without a
focused crop to unverified, preserving original model explanation/refs. Crop is
necessary, not independently sufficient. Failing regression reproduced boundary;
236 complete backend tests, Ruff and strict Pyright pass. Saved-evidence read-only
replay `.local/v1-visual-boundary-replay.json` finished: 13 checks, 1 unsatisfied
disabled control at1023, 12unverified including both rejected billing cases. No
historical report mutated; replay is not a new full run. No benchmark is running.
New ignored `.local/v1_recheck_visual_boundary.py <benchmark-run-id>` guards
local DB/storage, read-only transaction, uses actual repository/storage/batch verifier.
User received full done/remaining status and optional direction question: preserve
strict verification and proceed to TASK05/06 while tracking detection release gate,
or continue detection refinement before UI. No answer at checkpoint writing.
Do not claim benchmark passed or production ready. Follow user steering if received.

**Newest checkpoint:** focused repeat `87922cc8-56ce-45c0-8353-9d9436162906`
finished, report `7ac1b7d5-e784-4756-bef5-22c5bd81ff2f`, 234/234 artifacts,
three confirmed disabled-button findings and fourteen unverified observations.
Detection gate still fails. Generic click summaries prevent establishing which
control triggered the captured state. Minimal next fix stores bounded exact
semantic click locator fields in the existing action_summary (each <=160 chars;
otherwise generic). No filled values, no new model/migration, no historical rewrite.
Repository forwards this only for cited owned click steps with the recognized
summary prefix; visual context retains status and excludes future steps. Prompt
treats target labels as untrusted data and keeps pixels as product truth.
232 complete execution/evaluation tests pass; Ruff/strict Pyright pass.
New full repeat `3d0be5e4-2d8c-40cf-80aa-a033011845b9`, shell 6380,
`.local/v1-benchmark-broken-target.log`, is running. Review this before TASK 05.

**2026-10-10 continued work:** tool access restored. Broken repeat
`60e65ca1-c914-4950-bfcb-85a5e433d480` finished; exact report/counts are in
CURRENT_STATE and V1_BENCHMARK_RESULTS. Low detection keeps TASK 04 open.
Saved action context is now passed to vision using only owned cited step IDs,
types and statuses; no page content or secrets. Future steps are excluded,
failed statuses preserved. Diagnostic saved-image rechecks remain inconsistent,
not a passed quality gate. Explicit focused capture now scrolls the rendered
requested element into view before taking viewport/crop, following
https://playwright.dev/python/docs/api/class-locator#locator-scroll-into-view-if-needed.
A real Chromium test failed before the fix and passes afterward, including hidden
element rejection. No default network policy changed. New full broken repeat
`87922cc8-56ce-45c0-8353-9d9436162906` is shell 7672,
`.local/v1-benchmark-broken-focused.log`; new complete backend suite is shell 6096.
Latest complete execution/evaluation verification: 230 tests, Ruff passes, strict
Pyright 0 errors (suite 6096 completed).
TASK 05 existing list endpoint audited, no implementation started; TASK 06 UI
still pending sequential benchmark verification. Preserve historical checkpoints below.

**Tool-limit checkpoint:** working repeat is shell session **75176**, log
`.local/v1-benchmark-working-repeat.log`. Further escalated read commands were
rejected because the automatic approval review account hit its usage limit, not
because of an unsafe action. The rejected action was reading this handoff and the
working-repeat phase markers; it did not execute. The reviewer reported retry at
6:24 AM. Do not bypass approval review or infer new benchmark outcomes without
reading them once tool access is restored. Existing approved processes may finish.
Next: review working repeat, then run/review broken repeat; finish TASK 04 before
implementing TASK 05 and requested TASK 06 UI. Latest verified suite is 229 passed.
Polling the already-approved working process returned finished with shell exit 1
and no output (output was redirected). Earlier completed pipeline runs also had
shell exit 1 with redirected provider stderr, so this is not proof of pipeline
failure or success. Its actual phase markers, run ID, report, outcomes and physical
artifacts are still unreviewed. No benchmark process is intentionally left active.

**Final superseding checkpoint:** prerequisite-guard ambiguous repeat
`bc1f4a68-5f97-49c2-981f-a4d3654f9764` completed with report
`90ce69b5-aece-4c96-bb8e-f7b499cd7e0e`: all three inconclusive, zero confirmed
defects, three unverified observations, 46/46 physical artifacts. Conditional
visual checks stayed unverified. This specific repeat passed its intended gate.
Full execution/evaluation suite passed **229 tests**, strict Pyright 0 errors.
One test-only long line was fixed afterward; Ruff now passes. No source edits
after those checks. Working-case repeat has just started; read
`.local/v1-benchmark-working-repeat.log` for ID/phase. After it completes, review
and repeat broken cases. TASK 04 still incomplete; no UI implementation yet.

**Superseding checkpoint:** session 97677 is now running the second corrected
ambiguous benchmark, log `.local/v1-benchmark-ambiguous-prerequisite-repeat.log`,
run `bc1f4a68-5f97-49c2-981f-a4d3654f9764`. Session 38957's ambiguous repeat
`a4aeadb9-dcb7-4706-860b-0316be0cf1b9` completed with all 3 inconclusive but
**3 false visual confirmations** and 3 unverified observations, 41/41 objects.
The visual model treated a conditional requirement as failed although its stated
prerequisite (final delivery evidence) was absent. This is a real benchmark
failure; do not count it as a detection or claim the ambiguous gate passed.

Minimal new boundary: visual model JSON now includes `preconditions_met`
(true/false/null). An unsatisfied result is deterministically downgraded to
unverified unless that field is strictly True. Prompt explains conditional
prerequisites. Existing result model reused, no migration/new model call. Three
regressions failed before the fix (False, None, string "true"); a True case retains
unsatisfied. All 11 focused visual tests passed afterward. Needs real repeat result.

Another regression found that original-only repeated claims lost valid diagnostic
step links after normalization. `_reported_step_ids` now reads both corrected and
original criterion evidence, filtering by exact claim criterion; the existing
repository remains authoritative for ownership and artifact validity. No
unrelated screenshot fallback or confirmation is introduced. New original-only
exact-step test failed before the fix. Full backend/lint/Pyright checks are now
running in **session 51550**; poll and record final results.

The initial policy run completed: `11fecf58-7e65-4c83-9c37-a5a016bf4f1f`, report
`7211e5ed-05a9-4518-bcf2-b5b52d22e8e7`, 40/40 physical artifacts, no findings.
It blocked network access but recorded all three journeys completed/passed because
click didn't propagate a policy error. Real Chromium regression
`tests/test_browser_navigation_policy.py` failed before a minimal fix, then passed:
`controller.click` now checks an HTTP(S) href against the existing target policy
before clicking and propagates BrowserPolicyError. Network guards remain intact;
the test verifies the original URL is preserved. Browser regression/tools: 16 pass.

Policy repeat finished successfully: `7e2e0079-8e6f-41fa-bd95-4b1ff35ebeb2`, report
`78ce3c3e-0b5a-4a26-8b32-963c0b290f10`. All three are policy_blocked, outcome null,
three execution diagnostics, zero confirmed product issues, and 18/18 physical
objects. Direct model recheck of step 768 now returns unverified; log
`.local/v1-partial-viewport-repeat.log` (session 31573, finished). This is one
specific repeat, not general accuracy proof.

At the previous checkpoint the active process was session 38957, corrected ambiguous pipeline, log
`.local/v1-benchmark-ambiguous-repeat.log`. It supersedes session 64613 as active
work. The superseding checkpoint above lists current work. Do not start
another harness while it owns port 5191. Repeat working and broken afterward.
Newest source files passed Ruff/strict Pyright; the full execution/evaluation
suite now passes **224 tests**, including the real-browser regression. Session
86120 returned those passing checks. No further edits occurred after that check
except documents. Working/broken repeats still needed to measure prompt fixes.

## Objective and user decisions

Study `MKT.md` and build its V1 plan sequentially. Fix evidence integrity before
the later UI phase. Keep implementation minimal and reuse existing models.
Accuracy and evidence integrity are the user's highest priorities. Make optimal
routine choices autonomously; surface material suggestions during progress.

Repeated synthetic-persona claims must remain linked observations under **Needs
Verification**, never independent corroboration, confirmed bug totals, or high
severity based on repetition. Preserve persona, journey, criterion, and actual
execution references. Only relevant browser evidence can support confirmation.
Missing/inconclusive evidence stays unverified. Add meaningful regression tests.

The UI phase must include a premium app-specific public homepage, smooth relevant
animation, a comprehensive understandable How it works page, and a Log in button
that reaches the login page. The user explicitly said to include this in the
sequential plan, not skip the original technical steps to build the UI first.
Give frequent concise updates. Do not invent an overall completion estimate.

The app sent an explicit pause instruction earlier; the user subsequently said
"continue why paused?" and authorized continuation. Work resumed. `get_goal`
still returned a paused premium-UI goal; its API cannot resume goals. Do not
mark that goal complete while the requested UI is unbuilt. Do not create another
unfinished goal merely to bypass its status.

## Workspace and guardrails

- Root: `C:\Users\sreen\OneDrive\Desktop\MarketTwin`; PowerShell.
- Branch: `feat/batch-1-aws-observability`; audited HEAD:
  `801c2b43aab2a02189217e9e6d5c02773226b0fa`.
- Many tracked and untracked edits, including deleted images/documents, existed
  before this work. Never reset, clean, revert, or broadly reformat them.
- Root `AGENTS.md` supplies Karpathy rules: minimal surgical changes, visible
  assumptions, failing regression first, verify success criteria.
- Do not deploy, push, install dependencies, expose `.env`, or test an unrelated
  external target. Benchmark uses the already configured model provider and
  isolated loopback fixture. Default `public_only` policy remains intact.
- Do not spawn additional agents unless explicitly authorized by user or skill.
  `/root/ux_research` completed the earlier Sites-skill research; no work to await.
- Default shell execution repeatedly fails with helper setup errors. Escalated
  read/test commands worked with explicit justifications. One automatic approval
  review timed out; a single retry succeeded. No unresolved approval rejection.

## Reference map and why each matters

| Reference | Purpose |
|---|---|
| `../MKT.md` | Primary 00–09 execution plan, quality gates, dependencies, release checklist |
| `../AGENTS.md` | Workspace coding and verification rules |
| `V1_BASELINE.md` | TASK 00 baseline measurements and pre-existing limitations |
| `V1_FINDING_INTEGRITY.md` | TASK 01 audit, evidence/classification changes, regression validation |
| `V1_PERSONA_REPORT_VALIDATION.md` | TASK 02 deterministic consistency boundary |
| `V1_FAILED_ACTION_EVIDENCE.md` | TASK 03 exact failed-step capture and rollback behavior |
| `V1_BENCHMARK_RESULTS.md` | TASK 04 actual measurements, failures, pending repeat work |
| `RESULTS_AND_EVALUATION_CLARITY.md` | Existing results/evaluation foundation; read before UI/API duplication |
| `ADK_WORKFLOW_SESSION_STATE_AND_COLLECTION.md` | Existing execution/supervisor collection design |
| `PERSONA_STRUCTURED_REPORT_FIX.md` | Existing final-response schema/tool behavior |
| `AGENT_PROMPTS_AND_RERUNS.md` | Existing prompt snapshots and reruns |

Read the actual code before relying on older docs; the workspace has pre-existing
changes beyond its HEAD. In particular the journey list API already exists.

For UI, the Sites skill was read and applied to the existing local repo:
`C:/Users/sreen/.codex/plugins/cache/openai-curated-remote/sites/1.0.0/skills/sites/SKILL.md`,
plus its `references/design/presentation-led.md` and `references/preview/local.md`.
No hosted site was created. Research primary references:

- https://web.dev/articles/animations-guide — use transform/opacity, profile mobile.
- https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html — avoid long
  uncontrolled autoplay; short animation or explicit Play control.
- https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html — keyboard focus.
- https://www.w3.org/WAI/tutorials/forms/ — clear labels/errors, minimal login.

## Completed implementation

### TASKS 00–01

Baseline audit and finding integrity implemented and verified. Shared classifier
in `packages/shared-python/src/markettwin_shared/finding_classification.py`:
visual criterion plus valid linked screenshot → observed product issue;
policy/runtime → test execution issue; remaining → not verified.

Evaluation repository removed unrelated latest-screenshot fallback. Findings use
exact cited steps and artifacts, checking execution/journey ownership and
artifact-to-step linkage. Cross-persona drafts retain criterion identity, remain
informational, and explicitly disclaim independent proof. API/report join actual
screenshots to owned execution steps and affected journeys. Frontend separates
Confirmed issues, Needs Verification, and Test execution issues. Confirmed bug
counts exclude unverified observations. Journey links remain inspectable.

Initial baseline: 185 backend tests; frontend serial suite 23 passed. The default
frontend suite had timeout-related failures; no config was changed. After initial
integrity work: 216 backend tests, 24 frontend tests, typecheck/build, and four
desktop/mobile browser checks passed. Build retains a pre-existing bundle-size
warning. Screenshot artifacts under `artifacts/v1/needs-verification-*.png` use
explicit UI fixtures; they are not live product evidence.

### TASK 02

`workflow/report_validation.py` checks assigned criteria exactly once, no invented
criteria, positive strict integer IDs, execution ownership, completed actions,
recorded screenshot/accessibility artifacts, and consistent lists/outcome.
Unsupported reports become inconclusive; policy blocks retain execution status.
This is execution consistency, not independent semantic truth.

Original `reported_outcome`, `reported_criterion_evidence`, and
`reported_unsatisfied_criteria` plus `report_validation_issues` are saved in
`PersonaJourneyResult` and `journey.result` event/collection payloads. Deterministic
evaluation preserves repeated original claims after downgrade, but links only
valid corrected IDs. RunJourneysPage exposes Report checks. No migration added.

### TASK 03

`browser/tools.py` commits the original BrowserActionError failure, then makes a
five-second read-only `get_state` capture of the same session under existing
controller guards. Evidence attaches to that failed step; no action retry or
status rewrite. Response reports captured/unavailable. `record_failure_evidence`
rolls back evidence writes on failure or cancellation; prior failure stays saved.
Policy/session errors retain existing propagation. Recovery can pass using a later
completed step without rewriting the earlier failed step.

Verification: 222 execution/evaluation tests passed; changed production modules
passed lint/strict Pyright; frontend typecheck passed. A subsequent additional
recovery regression passed with all 57 focused tests. Two persona instruction and
snapshot tests passed after benchmark-driven prompt changes. Rerun relevant full
checks after the newest verifier changes; do not assume those are yet verified.

## TASK 04 active: actual results and why fixes are needed

Fixture: `services/execution-orchestrator/tests/fixtures/v1_benchmark/index.html`.
Harness: `services/execution-orchestrator/scripts/run_v1_benchmark.py`.
Runs actual Meta Agent → three-persona browser journeys → persistence/storage →
evaluation → report. Refuses remote DB/storage. Creates separate authorized local
target and run in seeded workspace; binds fixture 127.0.0.1:5191, restricted link
5192. Does not weaken production network policy.

| Case | Run ID | Result |
|---|---|---|
| Working | `9299d697-d52d-4cd9-abf5-57c47a9f4184` | Report completed; 5 passed, 1 inconclusive; 66/66 physical artifacts; no confirmed issue |
| Broken | `ef725d32-45ac-4456-bf75-e1ed00c6d8f8` | Report completed; 10 inconclusive, 1 partial, 1 failed; 185/185 objects; 15 unverified observations, 1 stored visual issue |
| Ambiguous, initial | `ef9bab44-953b-4c96-b621-7f1bfc82c8bf` | Report completed; all 3 passed, no findings; 35/35 objects; wrong goal interpretation, repeat needed |
| Policy | Read `.local/v1-benchmark-policy.log` | Started, outcome not yet reviewed at handoff creation |

The stored visual issue is NOT manually validated: its exact screenshot step 768
shows the top viewport rather than the relevant destination region. The seeded
defect is real, but this screenshot does not prove it. Record an evidence-quality
failure, not a successful detection. Do not conceal the historical result.
Manually viewed working steps 687 (Help guide) and 691 (save confirmation) support
those expected states. Local copies are `.local/benchmark-step-*.png`.

Benchmark exposed persona criterion paraphrasing and planner success criteria
containing reporting instructions. Small fixes made:
1. Persona criterion list is JSON strings repeated at final response; don't
   substitute mission objective. Planner criteria describe product states.
2. Suspected wrong/missing UI states require relevant region capture + exact IDs.
3. Visual verifier explicitly says missing text in partial viewport or missing
   action/transition context is unverified (newest change, needs verification).
4. Ambiguous harness goal now requires final delivery confirmation, keeping
   pending state inconclusive rather than making recognition of uncertainty pass.

These are hypotheses to repeat-test, not measured accuracy improvements.
TASK 04 is incomplete and quality gates have not passed. The policy run started
after the newest instruction changes. Repeat working/broken/ambiguous afterward.

## Running processes and useful commands

At handoff creation, shell session 71284 runs the policy benchmark, logging to
`.local/v1-benchmark-policy.log`; poll with write_stdin. Previous run sessions:
3803 working (finished, shell returned 1 despite completed phase/report; stderr
warnings via PowerShell may affect exit), 12168 broken, 37589 ambiguous. Poll to
confirm process exits. Never start another fixture harness while 5191 is occupied.

Vite was started on `http://127.0.0.1:5180`, session 27691; verify still running.
Existing Control API listener is 8080. No new backend server was started.

Ignored `.local/` review helpers exist. They guard loopback services and never print
credentials. Only use benchmark review helpers for benchmark runs:

```powershell
.venv\Scripts\python.exe .local/v1_baseline_audit.py <run-id>
.venv\Scripts\python.exe .local/v1_benchmark_review.py <run-id>
.venv\Scripts\python.exe .local/v1_benchmark_screenshot.py <run-id> <step-id>
.venv\Scripts\python.exe services/execution-orchestrator/scripts/run_v1_benchmark.py policy
$env:LITELLM_LOCAL_MODEL_COST_MAP='True'
.venv\Scripts\python.exe -m pytest services/execution-orchestrator/tests services/evaluation-worker/tests -q --tb=short -p no:cacheprovider
```

Avoid raw `.env` or verbose provider-error dumps; filter phase JSON and error types.
Docs do not contain credentials. Harness itself passed Ruff and strict Pyright
before newest brief-only edits. No dependencies installed or commits/pushes made.

## Remaining sequence and acceptance criteria

1. Finish TASK 04: inspect policy run; verify ownership/physical artifacts and no
   confirmed policy defects; repeat working/broken/ambiguous after small fixes;
   manually review exact confirmed images and report honest raw counts. If failure
   persists, fix the demonstrated boundary minimally and retest. Never claim
   production ready just because reports terminate or unit tests pass.
2. TASK 05: reuse existing authorized journey list endpoint; enrich missing counts,
   persona perspective/mission objective/summary/evidence availability; add scoped
   detail endpoint with exact ordered steps/artifacts and linked findings. Audit
   existing evidence/detail paths first. Ownership regression tests are essential.
3. TASK 06: evidence-first journey UI, then requested public premium home + How it
   works + login path. UI work is not implemented yet. Existing AppRoot currently
   resolves auth for every route; public routes should be outside that gate so the
   homepage/help don't depend on auth API. Existing login is email-only local
   approved identity; do not imply production Cognito is ready.
4. TASK 07: creation/knowledge clarity; TASK 08: status/report clarity; TASK 09:
   release gate from MKT, with actual tests and documented unresolved risks.

UI direction researched: product-native goal → persona journey → browser evidence
→ confirmed/Needs Verification demonstration; no fake metrics, testimonials,
generic particles, or unrelated animation. Use existing components/fonts/tokens;
smooth accessible transform/opacity motion, reduced-motion, mobile overflow,
visible focus and clear forms. A dark navy/mint public presentation was considered
but not finalized. Inspect actual rendered desktop/mobile pages and axe checks.
