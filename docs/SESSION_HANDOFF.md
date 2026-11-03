# MarketTwin implementation handoff

Current follow-up: user asked ALL old UI surfaces be unified with concept format and
architecture. /root/unify_test_pages owns runs/components/markettwin, now largely
finished (94 focused pass); /root/unify_app_settings management (24 pass + browserQA
green); /root/unify_public_auth auth/public/system (26 pass, publicbrowserlastlabel
contrast retest). Root owns shared statusLabel/StatusBadge, concept-workspaceCSS,
styles imports, unusedOverviewPage compatibility re-export, final integration.
Frontend full serialized suite session70427 is active. All typechecks currentlypass.
Browser management25 widths + testdetail6 layouts +11 WCAG audits +keyboard passed;
root visually inspected create360/apps1440 and corrected control order, square styles,
workspace font tokens. UrlIntakeForm label ink-2 fixes rose-background AA contrast.
No backend/API/auth semantics changes or benchmark rerun. Before final: full suite,
build/typecheck, public accessibility result, final docs and source whitespacecheck.

## Final checkpoint — 2026-11-02 21:32 local (supersedes older checkpoints)

Completed locally: Phases 0–7 plus requested live UI integration. All ten acceptance
gates passed using counted Runs1,4,5,6,7,8 under source contract
`04e84d9b-1a27-4f1e-b8ae-fca678a1d3cd`, v1, hash
`3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373`.
Source discovery ran once; five later replays performed zero discovery. Raw
outcome/assertion/replay tables, excluded Runs2/3 and startup failures are in
V1_BENCHMARK_RESULTS. Final score artifact is retry2.score.json under .local.

Final full Python:1245 passed,23 skipped,0 failed,10m17s; log
`.local/fix-spec-python-final-phase7-20261102.log`. Full web:199 passed across39
files; typecheck/build/Ruff/production-focused Pyright pass. New requests default
discovery, explicit old modes/historical fallback preserved, exact legacy banner
guarded. No viewer-policy relaxation; previously failing test passed in final suite.
UI uses real protected dashboard/watch/results, explicit /examples demos, retained
URL through setup; detail/auth layouts are preserved. Cleanup timeouts left three
working persona outcomes inconclusive; thresholds passed honestly. No matched old
engine baseline, so no comparative superiority claim. No commits or deployment.

21:24 local: Phase7 source stable. Four new-request defaults discovery; explicit
legacy/deep retained, persisted missing-mode fallback remains legacy. Exact legacy
banner guards tested. Focused Python65/web23 pass, production Pyright/Ruff and final
web typecheck/build pass. Full web session6540 still running; final full Python
log `.local/fix-spec-python-final-phase7-20261102.log` at39%, no failures yet.
No viewer production/test relaxation; isolated prior failure passed15.54s. Root
needs final suite results, final docs/plan sync, final table of all run gates and
honest no-matched-old-engine-baseline verdict, plus local/no-commit confirmation.

21:18 local continuation: root independently ran scorer on complete retry2 campaign,
status PASSED and every gate true. Run 8 user report sent: working,0/4,nav no,false0,
91.7% terminal,8.3% inconclusive,7m18s. Root authorized new_ui_wiring Phase7 defaults,
legacy banner/tests now; historical missing snapshot mode must remain legacy.
Full postfix Python log:1236passed23skipped1failed viewer_gateway TLS realcontext
test line539 expected control_mode human, got none after detach. scorer_finish
resumed to diagnose/fix without weakening human-control policy. reliability_audit
resumed to complete raw tables/all-gates table/excluded diagnostics/comparison limit.
No matched old-engine baseline, so no beats-old-engines claim. No commits.

13:04 update: Run 7 working #2 reported 0 confirmations, 24/24 terminal, no
inconclusive/interventions, integrity/provenance pass, 344.48 seconds; exact-format
report sent to user. Run 8 working #3 `bb032b1b-092e-4bc7-b1d2-cf32bcdaaf3a`
executes, same retry2 campaign artifact. Five accepted rows complete (1,4,5,6,7).
Full suite past 40%, no failures yet. Once final aggregate gates pass, gated
new_ui_wiring agent owns Phase7 defaults/banner/tests; root must independently
score final artifact and update product contract/current-state/final results table.

12:59 local: Run 6 working #1 reported 0 confirmed defects, 23/24 terminal, 1/24
inconclusive (cleanup TimeoutError despite satisfied assertions), 0 interventions,
integrity/provenance pass; 328.50 seconds. User received exact-format report.
Run 7 working #2 `2ca8d0d2-4eae-4949-846e-7627ee6c783e` is executing. Accepted
completed rows 1,4,5,6. Final Python suite runs in agent scorer_finish session 86092,
PID68048 BelowNormal, logs `.local/fix-spec-python-final-postfix-20261102.log` and
`.stderr.log`. Phase7 agent new_ui_wiring awaits all-six gate confirmation before
changing API/worker/web defaults/banner and testing. Keep historical fallback legacy.

12:56 update: Run 5 reported 4/4, navigation yes, 24/24 terminal, 0 inconclusive,
0 unexpected confirmed/manual intervention, integrity/provenance pass; 11m23s.
Run 6 working #1 `acde605d-19ba-4947-92d9-5d2ef9ae91de` is executing. Full suite
agent resumed to finish completed-step counting checks and run final validation.
Correction: Run 4 actually had 24/24 terminal and 0 inconclusive. Earlier 21/24
and 3/24 were source Run 1 metrics mistakenly attributed by the agent; artifacts
never changed. User and V1 results corrected. Accepted completed rows: 1,4,5.

12:46 local update: Run 4 `721d6ec8-1b7d-40d6-a2d4-c3959ef9915b` reported 4/4
including navigation, 21/24 terminal, 3/24 inconclusive, zero unexpected confirmed
findings/manual intervention, integrity/provenance pass; 9m50s elapsed and zero
discovery. Run 5 `6c0a7ac9-8ae8-47d7-902b-d147ac681e8e` executes broken #3,
then working #1–3. Corrected final full suite starts alongside working runs.
UI agent finished live wiring: 38 focused tests/typecheck/build pass, follow-up
approved-replay draft routing 5/5 and typecheck pass. Existing detail/auth layouts
remain; no complete all-pages visual acceptance claim. API generic-start now
rejects source-replay drafts (3 tests pass), so only contract/start can execute them.

Parallel UI task: user explicitly asked separate agent to wire new UI, find old
pages and fix concrete nonoptimal flows. /root/new_ui_wiring owns frontend routes,
live concept dashboard, auth/URL intake and presentation (avoids root's api.ts/
NewRunPage/RunReport default work). 21 focused tests passed; five new integration
checks/typecheck pending. Sample intercepts at authenticated paths removed; demos
are /examples/*; live /runs/:id/watch,/results use evidence-aware implementations,
old activity/report URLs remain aliases. URL retained through login/create/target
authorization. Preserve these user-requested changes through final Phase 7.

LIVE (2026-11-02 12:32 local): operational Run 4
`721d6ec8-1b7d-40d6-a2d4-c3959ef9915b` is executing, broken replay #2, with source
contract/hash unchanged, no discovery, preflight HTTP200 ready=true. Campaign:
`.local/contract-benchmark-single-contract-20261102-retry2.json` and matching log.
reliability_audit monitors; source Run 1 counts broken #1, next is broken #3 then
working #1–3. Prior draft `43054f88...` never executed (503 before readiness wait);
initial preflight-only serialization failure is preserved. Client mode request
serialization now explicitly sends all selected modes; focused API tests passed
11/11. Defaults remain legacy until gates pass. No commits.


## Latest protocol correction ? 2026-11-02 12:09 local

The user clarified that discovery runs once on the good fixture, one contract is approved/frozen, then that exact contract is reused for three broken and three good fixture executions. Run 1 is accepted as baseline broken replay 1: run `ed1eba45-267d-44af-956d-463209266c77`; 4/4 defects incl. navigation; 21/24 terminal, 3/24 inconclusive; zero false confirmations/manual intervention; provenance/integrity pass. Its source contract is archived immutably at `.local/contract-benchmark-source-contract-20261102.json`: ID `04e84d9b-1a27-4f1e-b8ae-fca678a1d3cd`, v1, content hash `3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373`. Discovery map covers all six declared features; primary main-page journey completed.

Run 2 (`44674ee0-9e8f-4af3-bbf9-cdffeb35120e`) is discovery-reliability data only and excluded from replay counts because it independently rediscovered. Its per-run diagnostics were 4/4 defects including navigation, 20/24 terminal, 4/24 inconclusive, zero false confirmations/manual intervention, integrity pass. Run 3 (`5e39c03e-8a6d-4d9a-aa9b-012f7e82e74e`) was interrupted during independent discovery before a report and finalized failed through supported delivery recovery; one operational cancellation/recovery; excluded.

Run 1 took 15m19.7s from creation to report: 2m32.4s discovery, 12m01.8s execution/replay, 18.1s report generation. Its required action durations total about 599s of the 722s execution window, with 12 replay links. Removing discovery saves the measured 2m32s; the remaining runtime is required execution/replay. Stored artifacts do not separately time uploads. The old per-run discovery harness has stopped. Next run two broken and three good replays using the archived contract hash, with no new discovery; keep thresholds and fixture unchanged. Phase 7 stays closed. No commits.

Protocol correction (2026-11-02, supersedes older live-batch status below): the
user explicitly requires one frozen contract. Run 1 `ed1eba45-267d-44af-956d-463209266c77`
counts as broken replay #1; run 2 is discovery-reliability evidence/protocol deviation
only; run 3 is interrupted and excluded. Original batch session 64370 is stopped.
Remaining: exactly two broken and three working replays of Run 1's immutable
checks/id/version/hash, no new discovery. scorer_finish owns authorized API source
reuse; ui_reconcile owns replay harness/scorer; reliability_audit owns source archive,
results and future monitoring. Rebind only destination run identity, retaining
source provenance and approval; enforce target/user/source integrity. Any opaque
human-takeover block stops/reports the action, with no workaround or silent skip.
Report each run in the user's exact format; record every failure/deviation in
V1_BENCHMARK_RESULTS. Default switch remains gated; no commits.

12:25 local: API source reuse 39 tests/Pyright/Ruff pass; harness/scorer 14 tests
and Ruff pass; opaque-stop production/schema path 5 tests/Pyright/Ruff pass. First
single-contract preflight failed before run creation because actual source rules
serialize optional scope_name/scope_role as null; expected shape omitted them.
ui_reconcile is normalizing exact policy comparison; reliability_audit owns retry
launch/monitoring, preserving the nonempty failed-preflight log. No discovery or
execution occurred. Source archive `.local/contract-benchmark-source-contract-20261102.json`
has hash `3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373`.
New operational labels 4–8; accepted six rows are 1,4,5,6,7,8. The corrected full
suite is held until corrected broken replay #3 finishes, then overlaps working runs.

Latest verification update (2026-11-02 11:54 local): no final acceptance yet.
Elevated retry session 64370 writes
`.local/contract-benchmark-acceptance-20261102-final-retry1.json` and `.log`.
Broken repeat 1 (`ed1eba45-267d-44af-956d-463209266c77`) passes its measurable
per-run gates: 4/4 defects including navigation, 21/24 terminal, 3/24 inconclusive,
zero intervention, provenance/integrity pass. Broken repeat 2 reported 4/4 including
navigation, 20/24 terminal, 4/24 inconclusive, zero intervention, provenance/integrity
pass. Repeat 3 (`5e39c03e-8a6d-4d9a-aa9b-012f7e82e74e`) is executing (12:03 local).
Full Python run: 1,219 passed, 23 skipped, one failure. The failure's assertion
incorrectly required global snapshot completeness despite an intentionally oversized
fixture; corrected while preserving scoped fields checks. Exact test and 14 related
tests pass; 3 production typing errors fixed, focused Pyright and Ruff pass.
scorer_finish will run the corrected full suite at reduced priority once broken
repeat 3 reports, alongside good runs to avoid extending the final wait.
Fresh-source setup at `.local/fix-spec-fresh-setup-20261102` passed: npm installed
192 packages; locked uv sync resolved 148/audited 146; Chromium installed with approved
cache access; 1,243 tests collected in 27.93s after installation. Corresponding logs
are `.local/fix-spec-fresh-{npm,uv,chromium,collection}-20261102.log`. This is an
isolated export of uncommitted source, not a committed clone. Keep Phase 7 closed;
no commits. Preserve initial permission-denied attempt as diagnostic evidence.

Supplemental Phase 3 evidence: `services/evaluation-worker/tests/test_contract_approval_boundary.py`
passed its persisted approved/frozen fail/fail scenario and API report-proof check;
the same synthetic evidence in draft state created no finding/report. Focused test:
1 passed; Ruff clean. This does not replace full-suite or benchmark gates. The
compact `docs/V1_PRODUCT_CONTRACT.md` describes implementation as of this checkpoint,
with the legacy default intact and final acceptance pending.

Updated: 2026-11-02. Branch: `feat/batch-1-aws-observability`.

Targeted follow-up: scoped inspection regression 1/1 and related contract generation/API
tests 14/14 passed. The global truncation assertion was removed because the page's
separate long form intentionally overflows the page-wide observation cap; scoped field
checks remain. Pyright on the three corrected production files reports 0 errors, and
Ruff passes on the changed production/test files. Wait for the live benchmark before
the single post-fix full-suite run.

## Latest fix-spec checkpoint — 2026-11-02 (supersedes next section)

The repaired benchmark attempt is stopped; do not resume session 96209. Artifact:
`.local/contract-benchmark-acceptance-20261102-repaired.json`. Broken repeats 1 and
2 reported 4/4 defects including navigation, with 24/24 and 23/24 terminal
journeys, zero manual intervention in those reports, and integrity passed. Broken
repeat 3 stalled on `Billing settings navigation` for >30 minutes despite a
240-second case budget, with no step/event, pending approval, pause request, or
human action. It was cancelled and finalized failed through the worker's existing
duplicate-delivery recovery path; the artifact records one manual recovery. This
diagnostic attempt is not a six-run acceptance and its first two reports cannot be
reused for the next gate.

Web validation passed: typecheck, build (existing 834.59 kB chunk warning), and
serialized Vitest 186/186. Focused Python tests passed across changed paths; the
full suite had 1,213 passed, 23 skipped, 2 failures, both passing in focused
follow-up checks. Re-run the full suite after resolving the case-timeout path.

Next: inspect `case_execution.py`/`contract_run.py` around the open session and
missing first step; add a deterministic timeout regression, fix and verify, then
start a new clean six-run acceptance under a new artifact filename. Preserve
fixture and thresholds; keep Phase 7 defaults closed unless all §8.2 gates pass.
No commits or pushes.

Follow-up status: blocked-navigation timeout coverage now passes (28 tests in
the case-assertion file, Ruff clean). The pause callback's extension before its
active-pause query is being corrected, with a blocked-probe regression. That
accounting defect is confirmed; the full >30-minute stall cause is still open.
Benchmark task diagnostics and suite-isolation investigation are running in
parallel. Phase 4 acceptance is incomplete; do not report Phases 0–6 as done.

Pause correction targeted checks: seven deadline/authentication-handoff tests
passed, Ruff clean. Empty probes no longer extend case deadlines, actual pauses
have a bounded allowance, and expired timers preserve timeout reporting. Original
login/approval wait semantics are preserved. Visual-span test instrumentation
isolation was corrected; visual/precondition tests passed together (2/2). A full
suite rerun is starting in `.local/fix-spec-python-final-20261102.log`. Fresh
acceptance is pending final harness diagnostic checks; planned new artifact is
`.local/contract-benchmark-acceptance-20261102-final.json`.

Latest: fresh six-run benchmark started in session 51434; log is
`.local/contract-benchmark-acceptance-20261102-final.log`. reliability_audit owns
monitoring and scoring. Full Python rerun has shown five failures by 28%, with
final details pending; scorer_finish owns investigation. Initial cost-map fetch
used LiteLLM's local fallback; verify required model calls separately. Phase 7
remains closed. Harness diagnostics/scorer tests passed 9/9; metadata snapshots
now capture bounded worker await chains and selected pending task frames.

## Active fix specification acceptance — 2026-11-02

Continue `MARKETTWIN_FIX_SPEC_FOR_CODEX.md` from the live repaired acceptance,
not from a clean baseline. Work is local; do not commit or push. The user approved
the exact declared fixture actions once. An initial preflight found an interrupted
pre-fix run; with no active steps and an accepted-delivery receipt, the worker's
supported recovery path marked it failed without replaying browser actions. The
current run is loopback-only and checkpointing to
`.local/contract-benchmark-acceptance-20261102-repaired.json` (command session
96209). The previous pre-fix diagnostic is retained at
`.local/contract-benchmark-acceptance-20261101.json` and was stopped after five
reported runs because recall/completion already failed.

The repaired batch has two reported broken runs: repeat 1 is 4/4 seeded defects,
navigation included, 24/24 terminal; repeat 2 is 4/4, navigation included,
23/24 terminal with one inconclusive. Both have 0 manual interventions and pass
provenance/report integrity. Four reports remain; run 3 broken is in discovery.

Current focused evidence: case/replay evaluator 64 passed; scorer/generation/
execution/replay 47 passed; Phase 0–3 74 passed; Phase 5 readiness/start 21 passed;
case assertion file 27 passed; scorer 7 passed; UI approval page 5 passed and
typecheck passed; modified Python Ruff checks passed. Full Python suite produced
1,213 passed, 23 skipped, 2 failures in 10m43s. Both failing cases passed
follow-up isolated checks (the executor test file had 27 passes; the visual span
test passed alone and in a 7-test combined run). Treat the full-suite ordering
issue as unresolved pending a clean rerun.

Implemented follow-up fixes cover assertion-empty case-cap handling, exact
visibility/enabled preconditions for compatible click targets, executor stop
ordering with persisted evidence, scorer validation of complete/integrity-valid
reports, and a queued-run `status_reason` transition test. Default switch remains
closed until every §8.2 gate passes. After the live run: score all six terminal
reports, append raw per-journey/per-assertion/replay tables to
`docs/V1_BENCHMARK_RESULTS.md`, run web suite/build, then update CURRENT_STATE and
this handoff with results. If a gate fails, iterate without changing the fixture
or thresholds.

## Concept UI Implementation Checkpoint (2026-11-02)

Implemented the Arize-Inspired Concept design per `markettwin-concept-implementation-spec.md`:
- CSS Token Architecture: `apps/web/src/styles/concept-tokens.css` with exact values from §2A.1, typography scale §2B, spacing §2C, accessibility focus rings, and reduced-motion rules.
- Canonical Demo Fixture: `apps/web/src/lib/concept-dataset.ts` with verbatim §4B dataset, helper formatters for coverage headline ("11 of the 14 attempts we could check worked.") and aria labels.
- Reusable Components: `apps/web/src/components/concept/` containing all 14 required primitives: StatusPill, VerdictBlock, CoverageBar, VerdictStrip, ProofChip, ProofTrail, ProgressLine, ContextTabs, UrlIntakeForm, StepList, TakeoverPanel, NeedsYouRow, TesterCard, TriptychSignature, MegaMenu, ConceptHeader, ConceptFooter (with required bottom bar credit line).
- Four Core Views:
  - Landing Page (`apps/web/src/pages/concept/LandingPage.tsx`): 11 sections with URL intake validation, hero tablist, triptych, stat band, example card, how it works, what you get, feelings, final CTA, and footer.
  - Dashboard Page (`apps/web/src/pages/concept/DashboardPage.tsx`): 3 real states (live-moment with blocked Priya, all-clear with calm text, brand-new empty state).
  - Watch Live Page (`apps/web/src/pages/concept/WatchLivePage.tsx`): snapshot header, 3 equal-weight tester cards, StepList collapse, TakeoverPanel states A/B.
  - Test Results Page (`apps/web/src/pages/concept/TestResultsPage.tsx`): H1 verdict block, compact triptych, coverage bar, tasks×testers matrix with verbatim reasons, comparison strip, P1/P2 cards, feelings pull-quotes, what we did not check list.
- Verification: TypeScript typecheck passes clean (`0 errors`), and automated Vitest test suite (`apps/web/src/test/concept-acceptance.test.tsx`) achieves 16/16 test passes with 0 banned copy strings or unauthorized hex codes.
Read [current status](CURRENT_STATE.md) first; [README](SESSION_HANDOFF.md) is the entry point.
This is the single detailed project guide: requirements, decisions, operations and
continuation. Older plans/reviews have been consolidated rather than retained as
competing files. Historical source inventories and proposed metrics are not current
runtime or production-readiness claims.

## Working agreement

Preserve all existing uncommitted frontend/backend/browser changes. Prioritize the
user's code-first implementation work; use proportionate checks rather than repeated
broad audits. Do not rewrite working APIs, authentication, permissions, browser controls
or evidence ownership to match a broken prototype. No paid model calls, deployment,
canonical restart, migration, commit or push were part of the latest source changes.
The newest runtime acceptance remains incomplete after Windows temp-folder errors.

## Current architecture and contracts

React/TypeScript calls the workspace-authorized FastAPI Control API. Starting a test
persists its frozen configuration/approved knowledge and transactional outbox event.
The relay publishes to Kafka; the execution worker durably accepts commands. ADK
planning creates bounded personas/missions or feature cases. Legacy persona journeys
and deterministic deep-feature cases remain separate, compatible execution modes.
Journey-bound Python tools own exact Playwright contexts. They do not expose raw
Playwright/CDP. Steps and S3/MinIO artifacts preserve exact run/journey/execution
provenance. Deterministic collection precedes independent evaluation/report publication.
Execution completed and report completed are different states.

Knowledge belongs to the workspace and can be explicitly attached to applications.
Original source, generated drafts and human approval are separate. Version pins retain
the source actually used by a run. Evidence ordinals are positive and must belong to
the current source/batch; consolidation cannot invent citations. Document adapters
extract deterministically; one KnowledgeBuilder handles supported native media and
returns grounded knowledge/procedure/Skill drafts. Missing media, malformed outputs,
unknown citations and provider errors must fail honestly, never return fake success.
Do not invent application-specific knowledge from filenames or product names.

Caller-owned FeatureScope and PlanBudget remain immutable. Cases must be executable,
scoped, bounded and meaningful: positive/negative/boundary/recovery coverage where
supported. Legacy plans and historical result schemas remain readable. Deterministic
assertions establish only observable facts. A tool completing, schema-valid prose,
repeated persona agreement or a partial viewport does not prove a product defect.
Conditional prerequisites and exact relevant evidence must be established first.
Runtime failures, blocked authentication and unknown observations remain distinct.

Artifact grants, paginated journeys and report links must belong to the exact workspace,
run and execution. Multi-journey findings open their provenance rather than guessing
an owner for flat step IDs. Target links cannot silently substitute another target.
Unsupported application/target/profile/workspace/member/security edits stay explicit
read-only/unavailable states until real management APIs exist.

## Sequential implementation and acceptance framework

The T00-T13 sequence below replaces the old TASK00-09 sequence. This is the retained
requirements/gate framework, not a claim that all work is incomplete or verified.
Current source status and remaining acceptance are in CURRENT_STATE.md. Reuse the
implemented fixture, schemas, scheduler, assertions, API and UI before creating new
infrastructure. Model-quality comparisons and generalization still need actual evidence.

| Task | Deliverable | Acceptance |
| --- | --- | --- |
| T00 baseline | Current-code discrepancies, sanitized failure matrix, actual checks and limitations | Recorded tests; historical evidence distinguished from fresh measurement |
| T01 fixture | Same-feature good/bad variants, independent manifest, direct browser oracle runner | Real non-AI Chromium checks; explicit local scope; blocked/unknown probes |
| T02 planning | Versioned `FeatureScope`/`TestCaseSpec`, deterministic validation/budget trimming, immutable plan, one-persona case bridge | Meaningful positive/negative/boundary/recovery cases, invalid plans rejected, legacy unchanged |
| T03 observation | Bounded form/region state and scoped semantic locators | Duplicate controls, ambiguity, stale state, redaction, bounded outputs |
| T04 safe actions | Only fixture-required check/uncheck, focus/keyboard, viewport preset | Policy → operation → recorded artifact → real fixture scenario |
| T05 assertions | Typed expected/observed records and deterministic verdicts tied to exact execution/step | Absent alert fails, delayed state passes, unavailable state unverified, foreign evidence rejected |
| T06 case execution | Sequential isolated cases, budgets/recovery, terminal events, truthful coverage | 6–8 cases finish within bounds; skips/blocks/errors accounted for; legacy unchanged |
| T07 report integrity | Extend existing validation to assertions and impossible claims | Invalid claims stay diagnostic; original action failure retained |
| T08 findings | Assertion-grounded failures with source and exact supporting evidence | No irrelevant/foreign proof, tool errors distinct, reconciled case totals |
| T09 experiments | Controlled one-variable budget/context/model comparison | Actual per-case counts, elapsed time, usage/cost when available; three core repeats |
| T10 generalization | Authorized form, list/filter and navigation workflows | Independently reviewed repeatable checks beyond fixture |
| T11 API | Add case/coverage/assertion semantics to existing authorized result surface | Cross-user/run rejection, pagination, safe output, historical compatibility |
| T12 UI | Case coverage, provenance and expected/observed alongside exact evidence | Live backend/storage/UI path, responsive/accessibility; human comprehension trial |
| T13 release | Accurate support/limits/docs and compatibility verification | Safety/evidence release checklist, actual benchmark and no unsupported claims |

## Service operation and configuration

Use Node 22+/npm 10+ and Python 3.12. Preserve existing `.env`; `.env.example` owns
configuration names/defaults. Source entry points:

- Control API: `services/control-api/src/markettwin_control_api/main.py` (`app`).
- Knowledge Worker: `services/knowledge-worker/src/markettwin_knowledge_worker/main.py` (`app`).
- Execution: `markettwin_execution_orchestrator.worker`.
- Evaluation: `markettwin_evaluation_worker.worker`.

From the repository root, with the existing dependencies/environment:

```powershell
npm.cmd --workspace @markettwin/web run dev
uv run --env-file .env python services/execution-orchestrator/scripts/run_execution_worker.py
uv run --env-file .env python -m markettwin_evaluation_worker.worker
```

The web app uses its configured API proxy. Match API/Knowledge Worker host/port to
local configuration; do not start competing listeners just to repeat a check.
Kafka dispatch needs `OUTBOX_RELAY_ENABLED=true`. Normal UI requires actual services,
authenticated workspace, target authorization and configured artifact storage; no
production page should inject demo data to hide an unavailable API.

The Compose stack in `infra/compose/docker-compose.yml` is loopback-only development
infrastructure (PostgreSQL, Kafka, MinIO). Pass `.env` explicitly when using Compose.
Changing environment values does not rotate existing-volume credentials. Helm,
Terraform and empty schema/client/policy packages are scaffolding, not validated
production deployment contracts. Production hosting/identity, backups/restore,
rotation, lifecycle, networking and cost acceptance remain open.

Database migrations are under `database/migrations`, configured by
`database/alembic.ini`. Apply required revisions through the normal reviewed migration
workflow with a verified backup. The delivery-retry baseline is `a7d8e9201b34`; newest
agent/HITL optimization uses the existing schema. Keep the verified local backup
`.local/audit/pre-audit-schema-20261019T015217Z.dump` and runtime/configuration data.

Production concurrency defaults: `MARKETTWIN_EXECUTION_CONCURRENCY=2` and
`MARKETTWIN_EVALUATION_CONCURRENCY=2`, each bounded 1-4. Run usage limits default to
`MARKETTWIN_RUN_MAX_MODEL_CALLS=512` and `MARKETTWIN_RUN_MAX_MODEL_TOKENS=2000000`.
First provider reservation freezes per-run limits. These are call/token bounds,
not a guaranteed dollar ceiling or reconstruction of old billing.

## Human takeover and privacy

Read-only observation grants no input and is suppressed while a human controls the
same browser. One actor/lease/generation owns input. Live login, membership, target
authority, execution identity and expiry are rechecked; no connection-lifetime auth
cache. Internal handoffs/releases stay signed, and origins stay explicitly allowlisted.
Never guess IdP/CDN authority or grant unrestricted top-level challenge navigation.

Requested pause becomes paused only at a safe boundary. Resume cannot replay a step;
taking browser control is explicit. Done releases input but does not prove identity:
independently verify approved continuation in the original context. Sensitive actions
require exact action/resource/environment approval. Duplicates, expiry, rejection or
uncertain effects must not dispatch another mutation. Owner loss fails closed.

Pointer drag uses guarded move/down/up/cancel, frame-content coordinates, sequence/rate
checks and cleanup on disconnect/cancellation/expiry. Old decoded frames cannot replace
newer frames. Solved known anchors are distinct from active/unreadable challenges.
A solved challenge is not authenticated identity; provider refusal stays blocked or
unverified. Never replay challenge tokens or weaken egress to turn a run green.

Network diagnostics use only fixed sanitized reasons/destination classes; no URLs,
credentials, raw exceptions or page content. Authorized operator pixels may contain
account data: masking known sensitive evidence controls is not universal redaction
of arbitrary unmarked text/widgets. Broader post-login privacy and device/IME/popup/
screen-reader acceptance remain open. Session replay recording is deferred.

Acceptance should cover read-only view, pause/resume, one control claim, login/MFA
verification, disconnect/reconnect/Done, Skip, exact approval/rejection/duplicates,
expiry/cancellation/stale generations, owner loss and separate execution/evaluation/
report states. Use an authorized synthetic/local or customer-owned staging target.

## Implementation details and verification limits

Updated: 2026-11-02. Branch: `feat/batch-1-aws-observability`.

## Concept UI Implementation Checkpoint (2026-11-02)

Implemented the Arize-Inspired Concept design per `markettwin-concept-implementation-spec.md`:
- CSS Token Architecture: `apps/web/src/styles/concept-tokens.css` with exact values from §2A.1, typography scale §2B, spacing §2C, accessibility focus rings, and reduced-motion rules.
- Canonical Demo Fixture: `apps/web/src/lib/concept-dataset.ts` with verbatim §4B dataset, helper formatters for coverage headline ("11 of the 14 attempts we could check worked.") and aria labels.
- Reusable Components: `apps/web/src/components/concept/` containing all 14 required primitives: StatusPill, VerdictBlock, CoverageBar, VerdictStrip, ProofChip, ProofTrail, ProgressLine, ContextTabs, UrlIntakeForm, StepList, TakeoverPanel, NeedsYouRow, TesterCard, TriptychSignature, MegaMenu, ConceptHeader, ConceptFooter (with required bottom bar credit line).
- Four Core Views:
  - Landing Page (`apps/web/src/pages/concept/LandingPage.tsx`): 11 sections with URL intake validation, hero tablist, triptych, stat band, example card, how it works, what you get, feelings, final CTA, and footer.
  - Dashboard Page (`apps/web/src/pages/concept/DashboardPage.tsx`): 3 real states (live-moment with blocked Priya, all-clear with calm text, brand-new empty state).
  - Watch Live Page (`apps/web/src/pages/concept/WatchLivePage.tsx`): snapshot header, 3 equal-weight tester cards, StepList collapse, TakeoverPanel states A/B.
  - Test Results Page (`apps/web/src/pages/concept/TestResultsPage.tsx`): H1 verdict block, compact triptych, coverage bar, tasks×testers matrix with verbatim reasons, comparison strip, P1/P2 cards, feelings pull-quotes, what we did not check list.
- Verification: TypeScript typecheck passes clean (`0 errors`), and automated Vitest test suite (`apps/web/src/test/concept-acceptance.test.tsx`) achieves 16/16 test passes with 0 banned copy strings or unauthorized hex codes.

The agent/HITL findings have been implemented in source. Runtime acceptance
of the newest changes remains incomplete; verification limits are listed below.

- Legacy planning has a 90-second deadline and an explicit call cap, scaled to the
  actual LLM agents in a configured sequential tree. Persona calls are also capped;
  the provider adapter applies per-attempt deadlines and explicitly budgeted retries.
- Visual requests have provider/criterion deadlines and a bounded batch allowance.
  Timeout, rate-limit and budget outcomes remain unverified. Downloads have bounded
  connection/read/retry settings; cancellation drains the download before temp-file
  deletion, so safe cleanup may extend the batch's wall-clock allowance.
- Completed visual judgments persist independently of final report publication in
  the existing event store. Cache identity includes run/execution, actual image
  hashes, prompt/context and runtime/model hash. Transient failures are not cached.
  A report rollback therefore reuses saved judgments. A crash between provider
  completion and durable save can still require another request. Evidence downloads
  still occur to verify actual bytes before reuse.
- Production execution defaults to two concurrent isolated runs, configurable 1-4.
  Same-run deliveries are serialized; Kafka commits only completed partition prefixes.
  Unacknowledged buffering is bounded and transport recovery drains active tasks.
  A PostgreSQL session advisory lock and bounded heartbeat preserve one live browser
  registry/viewer owner. This resolves the head-of-line wait within that owner;
  distributed browser routing/horizontal worker scaling remain intentionally disabled.
  Evaluation also defaults to two concurrent reports with existing per-run locks.
- Production viewer authorization combines current login and entitlement in one SQL
  query per check, preserving checks before/after capture and before diagnostics.
  Fallback authorities retain their existing interface. No connection-lifetime
  authorization cache was introduced.
- A periodic gateway sweep removes expired disconnected leases, attached IDs and
  tickets, preserving live reconnect/renewal. Slow frame/diagnostic writes are bounded
  so stalled sockets cannot retain connected bookkeeping indefinitely.
- A durable per-run call/token budget spans execution and evaluation. Each provider
  attempt reserves estimated input plus maximum output before dispatch; actual
  reported usage replaces reservations for later calls. Unknown/failed attempts keep
  reservations. Limits are frozen on the first call and survive report retries.
  Exhaustion stops new journeys. Defaults: 512 calls / 2,000,000 tokens, configurable
  in `.env.example`. These are not guaranteed dollar ceilings or exact image-token
  estimates, and do not retroactively account for calls before this implementation.

Implementation uses the existing schema; no migration, provider execution, deployed
service restart, commit or push was performed. Deployment must restart workers to
load the changed code. Full distributed failover and financial billing enforcement
were not added. See the service-operation section for settings and recovery semantics.

Verification: 41 focused worker/model/report/evidence checks passed in the earlier
batch. A later batch passed 13 checks but had six failures and twelve setup errors
caused by Windows temporary-directory access denial; the elevated retry was
interrupted. Later-added cache/lease regression cases therefore do not yet have a
complete passing runtime result. Final lint/type/whitespace results are recorded in
the current checkpoint. No live provider, PostgreSQL/Kafka ownership recovery or
production browser acceptance was exercised in this follow-up.

## Retained safeguards
- Browser tools serialize the complete recorded action, not only Playwright calls.
- Human leases bind actor, browser, execution and control generation; live viewer
  authorization checks workspace membership, user/session and target approval.
- Login verification remains separate from checking that a CAPTCHA was solved.
- Sensitive actions require exact approval and clean up on cancellation; an
  uncertain mutation is not automatically replayed.
- Evaluation has durable discovery, advisory locking, bounded report retries and
  quarantine. Those controls do not themselves prevent duplicate model charges.
- Knowledge preview has explicit concurrency and whole-preview time limits, and
  knowledge construction configures model timeout/retries and input chunk limits.
- The deterministic case path avoids a model call for every browser action.

No unrelated dead code or historical test files were deleted in this review.
The diagnostics method was disconnected functionality and is now wired.

Final Ruff and six production-source Pyright roots pass (zero errors/warnings);
whitespace checks pass. These do not establish live provider or DB/Kafka acceptance.

## Current UI design and interaction requirements

Evidence desk uses deep teal, charcoal, paper/warm neutrals, full-width top navigation
and source-linked reporting. No red/orange branding, glass effects or archived Figma
explorations. Use actual application routes/data and preserve newer working behavior.

## Shared foundations

`apps/web/src/styles/tokens.css` owns semantic values and compatibility aliases. `product-theme.css` composes the shell and page families; `report-intelligence.css` composes report analysis. Update owning rules rather than introducing another theme override sheet. Existing components consume the same `--mt-*`, `--surface`, `--text`, `--primary`, and `--ledger-*` aliases.

| Purpose | Value |
| --- | --- |
| Canvas / paper / inset | #EAE6DD / #FBFAF7 / #F2EEE6 |
| Primary / hover / selected | #245B50 / #1C493F / #E3EFEB |
| Main / supporting text | #242320 / #615E56 |
| Divider / control boundary | #C9C3B7 / #878174 |
| Success / failure / blocked / inconclusive | #276343 / #80345D / #825314 / #485A72 |

Use opaque surfaces, restrained boundaries and 4–12px corners. No glass, backdrop blur, decorative gradients, red/orange branding, or isolated legacy palette. Reserve shadows for overlays. Berry denotes failure; green requires an actual passing result. Unavailable observations stay neutral. Status always has text as well as color.

IBM Plex Sans is body/control text; IBM Plex Sans Condensed semibold is headings; IBM Plex Mono is identifiers. Fonts are self-hosted with licenses and `font-display: swap`. Do not synthesize condensed type. Operational headings are usually 28–34px, sections 20–24px, body 14–16px. Use 4/8/12/16/20/24/32/40px spacing and approximately 44px touch targets.

## Shell and responsive behavior

Use `AppShell` and `.mt-shell` top navigation: Overview, Applications, Tests, Knowledge, Agents, Settings. Tests remain application first. Application-scoped tests select Tests; target detail/security/scope select Applications; ingestion and knowledge detail select Knowledge; all settings tabs select Settings. Only one global destination is current. Use actual router destinations rather than broken prototype links.

Below 1280px full labels move into the accessible Menu drawer. Retain workspace switching, account/sign-out, and command navigation. Radix contains focus, supports Escape, restores the trigger on dismissal, and focuses main after route selection. Header stacking stays below overlays. On phones use 20px gutters, stacked layouts, full-width primary page actions, and 16px editable text. Verify 1440/1024/768/390px plus 320px stress checks. Wide tables/workflows may scroll locally; flexible children and media fit their containing region.

## Task-specific compositions

- Overview prioritizes the latest actionable test and actual inventory. Completed execution opens its report; it never implies a product pass.
- Lists use comparable records. Forms group scope/execution and disclose optional settings. Creation saves a draft; execution starts explicitly.
- Target authorization and network scope preserve exact origins, role checks, basis/confirmation, expiry/revocation, and requested revisions.
- Report destinations retain `reportView=overview|usefulness|inspection` and URL state. Count axes use actual record totals; zero draws no mark. Partial data stays explicit. Preserve feature cases and expected/observed/source classifications.
- Task/step selection uses stable IDs and paginated saved data. Evidence uses the authorized endpoint. Do not invent coverage, timings, coordinates, heatmaps, effort, customer impact, or historical trends.
- Execution retains the full-width protected browser, real activity, identity, generations, leases, sockets, pointer/keyboard/cursor/scrolling, control and approval boundaries.
- Knowledge separates original source, generated draft and approval. Agents retain recorded runtime selection, YAML save/reset/download and explicit rerun drafts.
- Unsupported edits, members/security capabilities, and unavailable evidence use honest recovery states. Do not create decorative Save or approval controls.

## Verification

The route/state inventory and current evidence are recorded in `docs/TEAL_REDESIGN_REVIEW_2026-10-22.md`. Render React routes with isolated API fixtures when provider execution is unnecessary. Check keyboard/focus, contrast, labels, long values, overflow, roles and recovery. Axe supplements visual review; it does not establish WCAG conformance or provider acceptance. Run current typecheck/build and relevant regression tests. Record coverage and limits without reusing historical results.

## Application/data wiring

Target-to-new-test links retain the requested target and cannot silently substitute
an unavailable or unauthorized target. Recent/oldest ordering uses persisted
created_at with a test-number tie-breaker and retains search/status URL state.
Application query identity includes user/workspace/application; failed refresh
keeps loaded rows and offers retry. Deletion returns to the application's Tests;
cancelling target creation returns to its application's targets, including direct entry.

Artifact preview identity includes run/artifact; stale grants and journey IDs cannot
leak into another test. Assessment links select the exact journey. Combined findings
open provenance rather than inventing an owner for flat step IDs. Uncertain Done
delivery stops lease renewal until safely retried. These current contracts were
preserved when the older wiring review was consolidated.

## Route and screenshot coverage

All rows below passed at 1440, 1024, 768 and 390px. The manifest contains per-width results. Screenshots use explicit synthetic fixtures; the execution row intentionally includes live-status recovery.

| View | Actual route | Desktop | Phone |
| --- | --- | --- | --- |
| overview | `/overview` | [1440](../.local/teal-redesign/after/overview-1440.png) | [390](../.local/teal-redesign/after/overview-390.png) |
| applications | `/applications` | [1440](../.local/teal-redesign/after/applications-1440.png) | [390](../.local/teal-redesign/after/applications-390.png) |
| tests | `/runs` | [1440](../.local/teal-redesign/after/tests-1440.png) | [390](../.local/teal-redesign/after/tests-390.png) |
| composer | `/applications/22222222-2222-4222-8222-222222222222/runs/new` | [1440](../.local/teal-redesign/after/composer-1440.png) | [390](../.local/teal-redesign/after/composer-390.png) |
| report | `/runs/11111111-1111-4111-8111-111111111111/report` | [1440](../.local/teal-redesign/after/report-1440.png) | [390](../.local/teal-redesign/after/report-390.png) |
| journey | `/runs/11111111-1111-4111-8111-111111111111/journeys/55555555-5555-4555-8555-555555555555?step=13` | [1440](../.local/teal-redesign/after/journey-1440.png) | [390](../.local/teal-redesign/after/journey-390.png) |
| knowledge | `/knowledge/review` | [1440](../.local/teal-redesign/after/knowledge-1440.png) | [390](../.local/teal-redesign/after/knowledge-390.png) |
| ingestion | `/ingestion` | [1440](../.local/teal-redesign/after/ingestion-1440.png) | [390](../.local/teal-redesign/after/ingestion-390.png) |
| settings | `/settings/profile` | [1440](../.local/teal-redesign/after/settings-1440.png) | [390](../.local/teal-redesign/after/settings-390.png) |
| execution | `/runs/11111111-1111-4111-8111-111111111111/activity` | [1440](../.local/teal-redesign/after/execution-1440.png) | [390](../.local/teal-redesign/after/execution-390.png) |
| application | `/applications/22222222-2222-4222-8222-222222222222` | [1440](../.local/teal-redesign/after/application-1440.png) | [390](../.local/teal-redesign/after/application-390.png) |
| new-application | `/applications/new` | [1440](../.local/teal-redesign/after/new-application-1440.png) | [390](../.local/teal-redesign/after/new-application-390.png) |
| edit-application | `/applications/22222222-2222-4222-8222-222222222222/edit` | [1440](../.local/teal-redesign/after/edit-application-1440.png) | [390](../.local/teal-redesign/after/edit-application-390.png) |
| application-tests | `/applications/22222222-2222-4222-8222-222222222222/runs` | [1440](../.local/teal-redesign/after/application-tests-1440.png) | [390](../.local/teal-redesign/after/application-tests-390.png) |
| targets | `/applications/22222222-2222-4222-8222-222222222222/targets` | [1440](../.local/teal-redesign/after/targets-1440.png) | [390](../.local/teal-redesign/after/targets-390.png) |
| new-target | `/applications/22222222-2222-4222-8222-222222222222/targets/new` | [1440](../.local/teal-redesign/after/new-target-1440.png) | [390](../.local/teal-redesign/after/new-target-390.png) |
| target | `/targets/33333333-3333-4333-8333-333333333333` | [1440](../.local/teal-redesign/after/target-1440.png) | [390](../.local/teal-redesign/after/target-390.png) |
| edit-target | `/targets/33333333-3333-4333-8333-333333333333/edit` | [1440](../.local/teal-redesign/after/edit-target-1440.png) | [390](../.local/teal-redesign/after/edit-target-390.png) |
| authorization | `/targets/33333333-3333-4333-8333-333333333333/authorization` | [1440](../.local/teal-redesign/after/authorization-1440.png) | [390](../.local/teal-redesign/after/authorization-390.png) |
| network | `/targets/33333333-3333-4333-8333-333333333333/network` | [1440](../.local/teal-redesign/after/network-1440.png) | [390](../.local/teal-redesign/after/network-390.png) |
| source-review | `/knowledge/review/source-review` | [1440](../.local/teal-redesign/after/source-review-1440.png) | [390](../.local/teal-redesign/after/source-review-390.png) |
| agents | `/agents` | [1440](../.local/teal-redesign/after/agents-1440.png) | [390](../.local/teal-redesign/after/agents-390.png) |
| workspace-settings | `/settings/workspace` | [1440](../.local/teal-redesign/after/workspace-settings-1440.png) | [390](../.local/teal-redesign/after/workspace-settings-390.png) |
| members | `/settings/members` | [1440](../.local/teal-redesign/after/members-1440.png) | [390](../.local/teal-redesign/after/members-390.png) |
| security | `/settings/security` | [1440](../.local/teal-redesign/after/security-1440.png) | [390](../.local/teal-redesign/after/security-390.png) |
| run-summary | `/runs/11111111-1111-4111-8111-111111111111/overview` | [1440](../.local/teal-redesign/after/run-summary-1440.png) | [390](../.local/teal-redesign/after/run-summary-390.png) |
| run-agents | `/runs/11111111-1111-4111-8111-111111111111/agents` | [1440](../.local/teal-redesign/after/run-agents-1440.png) | [390](../.local/teal-redesign/after/run-agents-390.png) |
| perspectives | `/runs/11111111-1111-4111-8111-111111111111/perspectives` | [1440](../.local/teal-redesign/after/perspectives-1440.png) | [390](../.local/teal-redesign/after/perspectives-390.png) |
| missions | `/runs/11111111-1111-4111-8111-111111111111/missions` | [1440](../.local/teal-redesign/after/missions-1440.png) | [390](../.local/teal-redesign/after/missions-390.png) |
| evaluation | `/runs/11111111-1111-4111-8111-111111111111/evaluation` | [1440](../.local/teal-redesign/after/evaluation-1440.png) | [390](../.local/teal-redesign/after/evaluation-390.png) |
| journeys | `/runs/11111111-1111-4111-8111-111111111111/journeys` | [1440](../.local/teal-redesign/after/journeys-1440.png) | [390](../.local/teal-redesign/after/journeys-390.png) |
| findings | `/runs/11111111-1111-4111-8111-111111111111/findings` | [1440](../.local/teal-redesign/after/findings-1440.png) | [390](../.local/teal-redesign/after/findings-390.png) |
| evidence | `/runs/11111111-1111-4111-8111-111111111111/evidence` | [1440](../.local/teal-redesign/after/evidence-1440.png) | [390](../.local/teal-redesign/after/evidence-390.png) |
| human-action | `/runs/11111111-1111-4111-8111-111111111111/human-action` | [1440](../.local/teal-redesign/after/human-action-1440.png) | [390](../.local/teal-redesign/after/human-action-390.png) |
| forbidden | `/403` | [1440](../.local/teal-redesign/after/forbidden-1440.png) | [390](../.local/teal-redesign/after/forbidden-390.png) |
| error | `/error` | [1440](../.local/teal-redesign/after/error-1440.png) | [390](../.local/teal-redesign/after/error-390.png) |
| not-found | `/missing-location` | [1440](../.local/teal-redesign/after/not-found-1440.png) | [390](../.local/teal-redesign/after/not-found-390.png) |

Public `/`, `/how-it-works`, `/login`, `/auth/callback` were captured and checked at all four widths. Populated finding detail, artifact grants/denial, draft/start, agent YAML editing/reruns and knowledge approval/selection are additionally exercised by workflow checks. They are not all separate rows in the visual matrix.

## 18. Figma references and current-state provenance

Figma file: https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9

Current page ID: `13:140`, renamed “01 / Current product — unified system.”

Archive section on that page: `69:1354`, containing 34 previous frames. The separate rejected-direction page and research/system page remain historical/reference material.

The 52 current frame IDs below are traceability references. They are not a requirement to query Figma before implementation. A frame may represent a responsive variant, component state, unavailable capability, or a shared route family rather than a new product route.

| Key | Current frame | Figma ID/link | Implementation interpretation |
|---|---|---|---|
| report | Report overview | [60:856](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=60-856) | Run report overview; counts, limitations, priority finding |
| journey | Journey canvas | [58:131](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=58-131) | Usefulness/journey detail; actual ordered steps and selected assertion |
| inspection | UI/UX inspection | [60:968](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=60-968) | Finding distributions, filters, classification, recommendation and source |
| mobileEvidence | Mobile evidence | [58:279](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=58-279) | 390 px selected-step and expected/observed reference |
| artifactDialog | Artifact context dialog | [60:1167](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=60-1167) | Desktop preview-access state; production uses actual authorized viewer |
| mobileArtifactDialog | Mobile artifact dialog | [61:211](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=61-211) | 350 px dialog within a 390 px viewport |
| workspace | Workspace overview | [69:211](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=69-211) | Latest actionable test, applications, optional knowledge |
| applications | Applications | [69:315](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=69-315) | Application inventory and add/open actions |
| application | Application overview | [69:410](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=69-410) | Targets, tests and approved context |
| authorization | Target authorization | [69:495](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=69-495) | Actual status, basis, confirmation and revoke behavior |
| tests | Tests | [69:567](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=69-567) | Preserve application-first entry where implemented |
| createTest | Create test | [69:652](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=69-652) | Goal/target/mode/depth, optional knowledge and draft creation |
| execution | Recorded execution | [69:762](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=69-762) | Real selected task, recorded steps and session availability |
| knowledge | Knowledge library | [69:856](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=69-856) | Source inventory, review state and add-source flow |
| ingestion | Add knowledge | [69:940](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=69-940) | File/link input, purpose, processing and draft generation |
| knowledgeReview | Source review | [69:1027](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=69-1027) | Original source and generated draft; real approval capability |
| settings | Profile settings | [69:1105](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=69-1105) | Read-only/editable account capability from current API |
| home | Public home | [69:1176](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=69-1176) | Product explanation and labeled illustrative evidence |
| signin | Sign in | [69:1247](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=69-1247) | Actual supported authentication and recovery |
| humanAction | Human assistance | [69:1272](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=69-1272) | Protected browser, paused case and authorized controls |
| newApplication | Create application | [71:247](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-247) | Name/description validation and target setup continuation |
| newTarget | Add target | [71:277](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-277) | Environment, URL and authentication requirement |
| editApplication | Edit application unavailable | [71:315](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-315) | Do not invent unsupported update API |
| editTarget | Edit target unavailable | [71:334](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-334) | Retain update/reauthorization capability boundary |
| members | Members unavailable | [71:353](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-353) | Do not fake membership management |
| security | Security unavailable | [71:372](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-372) | Do not fake session/identity APIs |
| callback | Auth callback | [71:391](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-391) | Actual pending verification, redirect and recovery |
| forbidden | Forbidden | [71:410](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-410) | Access recovery without leaking restricted data |
| error | Unexpected error | [71:429](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-429) | Relevant retry with saved context retained |
| notFound | Not found | [71:448](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-448) | Missing location/record recovery |
| coverage | Coverage unavailable | [71:467](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-467) | State within reporting; no inferred inspected-page percentage |
| comparison | Comparison unavailable | [71:486](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-486) | State within reporting; no invented history |
| partial | Partial report | [71:505](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-505) | Saved findings remain visible; retry missing task data |
| empty | Empty filtered results | [71:524](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-524) | Explain/reset filters; not an issue-free verdict |
| targets | Target list | [71:543](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-543) | Application target environments and add/open actions |
| target | Target overview | [71:566](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-566) | Identity, authorization context and scope navigation |
| network | Execution scopes | [71:592](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-592) | Approved policy and requested revisions; exact origins |
| applicationKnowledge | Application knowledge context | [71:630](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-630) | Preserve inspected redirect to ingestion if still current |
| applicationRuns | Application tests | [71:650](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-650) | Associated test inventory with correct run links |
| workspaceSettings | Workspace details | [71:670](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-670) | Actual name, access, state and ID; read-only where required |
| agents | Agents/prompts | [71:689](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-689) | Recorded runtime selection, YAML save/reset/download/rerun rules |
| draft | Draft review | [71:715](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-715) | Review configuration; explicit start only |
| perspectives | Simulated testers | [71:739](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-739) | Recorded generated perspectives or feature-mode not-applicable state |
| missions | Testing goals | [71:762](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-762) | Recorded mission objective/criteria and mode distinctions |
| evaluation | Evaluation records | [71:785](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-785) | Qualitative saved results and limitations |
| activity | Recorded activity | [71:808](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-808) | Actual actions and timestamps, filtering and selected event |
| how | How it works | [71:844](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-844) | Public workflow, execution modes and evidence categories |
| mobileWorkspace | Mobile workspace | [71:877](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-877) | Single-column actionable test and application summary |
| mobileCreate | Mobile create test | [71:897](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-897) | Readable stacked fields and optional disclosure |
| mobileKnowledge | Mobile knowledge | [71:932](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-932) | Source inventory/empty state and real add-source action |
| mobileInspection | Mobile inspection | [71:947](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-947) | Finding, classification, recommendation and own source |
| mobileMenu | Mobile navigation | [71:966](https://www.figma.com/design/bLnyexlqaV81bgGDNwl9v9?node-id=71-966) | Accessible drawer/dialog with all global destinations |



## Benchmark methodology and proposed gates


### 11.1 Controlled fixture matrix

Make the **first smoke benchmark small** (6–8 core cases) to avoid unnecessary model spending. Expand to 20–30 independently labeled cases across **at least three feature types** only after the smoke test can run repeatedly. Include a mix of positive, negative, boundary, recovery, asynchronous, duplicate-locator, navigation, policy-blocked and deliberately ambiguous cases.

| Fixture family | Known-good cases | Seeded defects | Expected non-bug outcomes |
|---|---|---|---|
| Form validation | required field, valid formatting, error-clearing | absent validation, incorrect allowed-length behavior, failed recovery | account-creating submit blocked |
| Search/filter/list | expected results, no-result state, sort state | wrong filter application, reset failure, incorrect row selection | inaccessible/empty view correctly unverified |
| Multi-step navigation | page transition, state preservation, Back, delayed loading | wrong redirect, lost selection, missing confirmation | authorized-origin boundary blocked |
| Responsive/keyboard | focus navigation and viewport usability on fixture | hidden action, clipped control, keyboard-inaccessible control | visual ambiguity remains unverified if no pixels were inspected |

**Never choose fixture truth by letting the same LLM propose both bug and expected answer.** The fixture implementation and oracle manifest must be independently authored and independently tested.

### 11.2 Comparison protocol

1. Freeze fixture version, test data and oracle manifest.
2. Use the same goal, authorization, source requirements, and allowed budget for baseline and improved implementation; where modes fundamentally differ, disclose the unequal scope.
3. Run A then B, with independent reset/repetition; randomization/order effects should be considered if applicable.
4. Label each detected issue **manually or by deterministic fixture truth**, before viewing agent explanations when possible.
5. Score **actual executed checks and defects**, not length of output, number of personas, number of screenshots or raw LLM confidence.
6. Record failed tool calls, elapsed time, token usage, retry count and in-scope policy blocks.
7. Repeat selected cases across at least 3 independent runs for stability, adding more repetitions if variance is high and budget permits.
8. Keep every regression case that exposed a real defect or false positive.
9. Run the full suite on model and prompt changes only after targeted smoke tests pass.
10. Publish both numerator/denominator and examples of errors; don't present tiny-sample percentages as precise general accuracy.

### 11.3 Exact metric definitions

**Scenario execution rate** = cases with completed real browser execution / executable planned cases. Exclude policy-blocked/non-executable cases from denominator but **show their raw count**.

**Oracle coverage** = actually executed cases with a valid deterministic or verified visual assertion / actually executed cases. This is **known-case coverage**, not website coverage.

**Seeded defect recall** = distinct known seeded defects correctly reported as verified / distinct in-scope, safely observable seeded defects. A defect may affect multiple cases; count by root issue not journey duplication.

**Verified finding precision** = true confirmed product defects / all findings labeled `verified product defect`, using independent ground truth review. A missing requirement does not become true just because the report says so.

**False positive count** = findings labeled verified but not supported by fixture/application ground truth; record count by cause (`wrong_oracle`, `agent_error`, `tool_error`, `network_error`, `screenshot_mismatch`).

**Evidence provenance correctness** = verified product findings whose exact supporting steps and artifacts match the same execution **and actually prove the asserted observation** / all verified product findings.

**Unverified calibration** = ambiguous, unsupported, blocked or tool-uncertain cases appropriately labeled instead of forced pass/fail / all labeled ambiguous, unsupported, blocked or tool-uncertain cases in fixture truth.

**Case reproducibility** = selected test cases yielding equivalent verdicts under same seeded state and environment / repeated case trials; report individual cases and legitimate nondeterminism.

**Useful findings per model dollar and per minute** = distinct true verified defects / measured model cost or end-to-end time. Report `N/A` rather than fabricated cost if prices/usage are unknown.

**Customer comprehension** = in an observed pilot, participant correctly identifies (a) result class, (b) exact evidence, (c) next action. This is separate from automated backend validity.

### 11.4 Proposed initial gates (not measurements)

| Gate | Initial proposed threshold | Why / qualifications |
|---|---|---|
| P0 evidence and safety | **Zero** confirmed findings with fabricated/foreign/irrelevant evidence; **zero** unauthorized browser actions | Hard invariant on all examined test runs |
| P0 controlled fixture | **All** intentional policy blocks reported as blocked, not defects | Must be exact in fixture |
| P0 assertion semantics | **All** deterministic fixture cases produce the correct `satisfied/not_satisfied/unverified` class when run directly | Tests oracle implementation separately from LLM |
| Pilot verified-finding precision | Target **≥95%**, and **zero** severe false product-bug claims | Only interpret percentage after enough independently labeled findings |
| Pilot seeded-defect recall | Target **≥80%** for safely observable seeded defects | Sensitivity goal, not guarantee of comprehensive testing |
| Pilot known-case coverage | Target **≥85%** actually executed/verified among authorized, executable, in-budget planned cases | Show omitted/blocked cases |
| Pilot run termination | **100%** terminate as completed, partial-with-reason or explicit failure by configured bound | No indefinite silent activity |
| Stability | **No unexplained verdict drift** in core golden fixtures over 3 repeats | Report flaky cases honestly; 3 runs are weak statistical evidence |
| Usability pilot | User can inspect one confirmed issue and exact step evidence in **~60s** | Trial target, not guaranteed experience |

Do **not** lower evidence/safety gates to improve recall. If recall is poor but precision is high, improve planning/tools. If recall is high but precision is poor, fix oracles and verification first.

### 11.5 Results file example

```json
{
  "benchmark_version": "deep-fixture-v1",
  "commit": "CURRENT_COMMIT_SHA",
  "mode": "deep_feature",
  "model_configuration": "REDACTED_SAFE_CONFIGURATION",
  "fixture_version": "v1",
  "planned_cases": 8,
  "attempted_cases": 7,
  "verified_defects": 0,
  "false_positive_count": 0,
  "seeded_defects_detected": 0,
  "seeded_defects_in_scope": 3,
  "missing_results": ["NOT_YET_RUN"],
  "evaluation_status": "not_run"
}
```

These are **schema examples**, not a claim that tests have run. Store benchmark output only after real execution and don't ship sample values as results.

---


## Release acceptance gates


### Testing depth

- [ ] One feature becomes multiple **meaningfully different** explicit test cases.
- [ ] Positive, negative, boundary and recovery cases are produced **when relevant**.
- [ ] Every case has requirement/source provenance or is labeled exploratory.
- [ ] Cases have deterministic/independently checked outcomes, not only narrative summaries.
- [ ] Browser can observe relevant form states and disambiguate repeated controls.
- [ ] Safe missing actions are implemented only where proven needed.
- [ ] Bounded recovery and adaptive exploration do not loop indefinitely.
- [ ] Non-executable cases clearly show `blocked`, `not_run` or `inconclusive`.

### Truthfulness and evidence

- [ ] Confirmed defects are validated against actual expected/observed state.
- [ ] Step and artifact belong to correct run/journey/execution.
- [ ] Artifact **supports the exact claim** and isn't merely the latest screenshot.
- [ ] Failed browser actions preserve accurate status and evidence if available.
- [ ] Agent tool errors and model hallucinations are not customer-facing product bugs.
- [ ] Cross-persona repetition alone never confirms or escalates a defect.
- [ ] Report counts separate product bugs from coverage gaps, policy blocks and runtime issues.
- [ ] Browser, source knowledge and artifacts never permit prompt-injection-based privilege expansion.

### Empirical benchmarks

- [ ] Ground-truth fixture reviewed independently.
- [ ] Legacy baseline results recorded with actual execution IDs, where possible.
- [ ] Improved results recorded on same fixture.
- [ ] Individual case outcomes, precision, recall, evidence accuracy, cost and time reported with denominators.
- [ ] Golden core case verdicts stable across repeated controlled runs or unstable cases explicitly documented.
- [ ] Real authorized feature tests performed after fixture success.

### Compatibility and privacy

- [ ] `public_only` network policy unchanged and tested.
- [ ] No autonomous passwords, OTP, CAPTCHA, payments, destructive actions or unauthorized origin access.
- [ ] No secrets in model context, customer-facing error, screenshot reference or result API where avoidable.
- [ ] Older TestRuns, findings and reports remain readable with honest legacy provenance.
- [ ] No unexplained DB migrations or queue/service additions.
- [ ] Existing targeted Python tests, frontend typecheck/build, and API authorization tests pass.

### Experience (after agent correctness)

- [ ] Real live case/step/evidence API exists.
- [ ] A test report shows what was tested and what remained untested.
- [ ] A confirmed defect navigates directly to the supporting step and artifact.
- [ ] Normal error/loading/permission states are handled honestly.
- [ ] A real participant can explain an issue and its evidence without reading raw LLM logs.

**NO-GO:** Any verified defect with invented/wrong evidence, unsafe browser action, systematic misclassification of tool failure as product bug, no controlled benchmark, or falsely reported coverage blocks the release regardless of how attractive the UI is.

---


## Delivery and evaluation recovery


Apply migration `a7d8e9201b34` before deploying this worker and the Control API.
It adds retry metadata without deleting, publishing, or completing existing work.

Outbox failures back off from 5 seconds with exponential growth, capped at one
hour; the eighth failure quarantines the retained event. Evaluation failures
back off from 30 seconds, capped at one hour; the fifth failure quarantines the
completed run's evaluation. Only a completed version-1 report marks evaluation
complete. Successful provenance snapshot persistence alone does not.

A publish timeout can mean Kafka accepted the message but its acknowledgement
was lost. Retrying can deliver a duplicate. Consumer deduplication remains
required. Do not mark an event published manually to clear a backlog.

Inspect backlog and quarantine in a trusted database administration session:

```sql
SELECT count(*) AS unpublished, min(created_at) AS oldest_unpublished,
       count(*) FILTER (WHERE quarantined_at IS NOT NULL) AS quarantined
FROM integration.outbox_events WHERE published_at IS NULL;
SELECT id, attempts, next_attempt_at, quarantined_at, last_error
FROM integration.outbox_events WHERE published_at IS NULL ORDER BY id;
SELECT id, evaluation_attempts, evaluation_next_attempt_at,
       evaluation_quarantined_at, evaluation_last_error
FROM testing.test_runs WHERE evaluation_attempts > 0;
```

Diagnostics contain exception class names, rather than transport/model exception
payloads that may include secrets. Diagnose the underlying provider, evidence, or
configuration failure first. After correcting it, recover one selected row by
ID in a transaction; review the affected row and commit only the intended reset:

```sql
BEGIN;
SELECT id, attempts, last_error FROM integration.outbox_events
WHERE id = :event_id AND published_at IS NULL FOR UPDATE;
UPDATE integration.outbox_events
SET attempts = 0, next_attempt_at = NULL, quarantined_at = NULL, last_error = NULL
WHERE id = :event_id AND published_at IS NULL AND quarantined_at IS NOT NULL;
COMMIT;
```

For evaluation recovery, pause the evaluation worker first (including diagnostic
scripts), then reset one retained run and restart the worker:

```sql
BEGIN;
SELECT id, evaluation_attempts, evaluation_last_error FROM testing.test_runs
WHERE id = :test_run_id FOR UPDATE;
UPDATE testing.test_runs
SET evaluation_attempts = 0, evaluation_next_attempt_at = NULL,
    evaluation_quarantined_at = NULL, evaluation_last_error = NULL
WHERE id = :test_run_id AND evaluation_quarantined_at IS NOT NULL;
COMMIT;
```

Bind `:event_id` / `:test_run_id` using the database client's parameter support.
Neither reset replays browser execution. Provenance snapshots are reused by
semantic hash; incomplete reports are completed in place, and findings/report
changes roll back together if final generation fails.

## Separate SAM planning context

SAM remains a separate, unimplemented working design, not a MarketTwin service.
Retained requirements: one owner-facing primary assistant; web, phone and SMS in the
full vision; a real isolated computer with live view/takeover; sourced memory;
explicit approvals; no unsolicited outreach or ambient capture. Authorized helpers
are bounded and optional; persistent employees are a later lifecycle capability.
The budget ceiling is under $20/month, with a provisional $19 envelope and later
Mac mini purchase after measurement. Proposed starting limits were one active root
task and up to three explicitly authorized helpers, not measured optima.

Keep SAM code, databases and services separate. Prove a local core before expanding
channels; phone/SMS remain requirements but affordability/integration is unresolved.
Selected models/search, host capacity, workflow implementation, speech, jurisdiction
and full-V1 feasibility are unvalidated. GEPA/repair ideas require bounded evaluated
experiments, not open-ended self-modification. No purchases/deployment are authorized
by retaining this plan. Existing `docs/sam-audit/experiment-results.json` records only
isolated crash/replay and concurrent-budget mechanisms, not SAM runtime quality.

## Documentation and workspace cleanup

Only README.md, docs/CURRENT_STATE.md and this guide remain as project documentation.
AGENTS.md remains repository instructions; font licenses, source/configuration,
regression tests, screenshots/manifests, benchmark JSON and runtime/backup data remain.
No duplicate archive document was created. Older dated narratives and full source
inventories were removed after consolidating active decisions/requirements here.
The current source and retained machine-readable evidence govern actual behavior.
The final consolidation removed 60 standalone documentation files. Inventory checks
confirm three project docs plus unchanged AGENTS.md instructions, 89 valid local
links/anchors, 52 Figma frame links and all 14 T00-T13 task rows. Font licenses and
non-document evidence were not removed; no application tests were needed.
