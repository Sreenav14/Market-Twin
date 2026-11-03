# Fix specification execution plan

Latest (2026-11-02): corrected single-contract six-run campaign passed every gate;
Phase 7 default/banner implemented and focused checks passed. Live UI wiring is
integrated; 199/199 frontend tests, typecheck/build, production Pyright and Ruff
pass. Final post-Phase7 full Python suite passed: 1,245 passed, 23 skipped, zero
failures. Phases 0–7 and requested live UI wiring are complete locally. Older
checkpoints below are historical diagnostic attempts. No commits or deployment.

Updated 2026-11-02 (case-timeout fix required). All work is local and uncommitted.

The user explicitly authorized parallel agent work and asked for the fastest
parallel completion. A repaired acceptance attempt has been stopped after broken
repeat 3 stalled beyond its 240-second per-case budget. Its first two broken runs
passed their per-run recall/completion gates; the third required one manual recovery
and is recorded failed. A timeout-path regression and fix are now in progress. Keep
the default switch closed until a fresh six-run batch passes every gate.

## Decisions and constraints

- Preserve existing workspace changes, legacy execution modes, evidence ownership,
  origin restrictions, approval rules and persona/case limits. No commits or pushes.
- Discovery evidence references the existing integer ExecutionStep IDs.
- Discover and approve checks on the good fixture, then execute the frozen checks
  on the broken fixture. Do not derive expected behavior from broken observations.
- Exact locator ambiguity stops an action; fallback applies only to zero matches.
- The configured cloud Kafka broker currently fails DNS. Benchmark runs may use
  the existing loopback broker through process-only settings; preserve `.env`.
- Do not change the new-run default until all six benchmark runs pass the gates.

## Work allocation

| Owner | Scope | Deliverables | Acceptance |
| --- | --- | --- | --- |
| Primary | Discovery, contract-to-case execution, shared contracts, benchmark and integration | Complete bounded discovery; exact translation; timed checks; three variants; fresh-browser replay; real API/Kafka/worker fixture loop | Focused production Ruff/Pyright; execution integration tests; live maps and raw outcome tables |
| approval_results_ui | `apps/web` | Discovery selection and exploration flow; approval page and route; plain-language check editing; report sections, evidence and coverage; status reasons | Meaningful component tests, typecheck, build, accessibility checks; confirmed and unverified items stay distinct |
| run_reliability | Worker/database/control API reliability files | Heartbeat migration/model; 10s heartbeats; health/preflight; start rejection; stall reasons; interrupted-run explanation | Focused tests for missing/stale workers, broker/dispatch failure, legal starts and status reasons; migration reviewed before application |
| evaluation_integrity | Contract evaluation, experience, verdict and report validation | Exact approved grounding; owned original/replay evidence; honest coverage; deduplicated findings; cited experience scores and screenshot input | Fail/fail confirms; fail/pass and unavailable replay stay unverified; forged report rejected; missing experience fails softly |

Agents own separate files. Shared schema or payload changes must be coordinated
through the primary agent. No agent applies database migrations or restarts shared
services while the live fixture run is active.

## Ordered integration and validation

1. **Reconcile Phases 0–3.** Read source and existing tests; repair gaps affecting
   the current execution path. Keep the approved contract immutable and versioned.
   Verify API authorization and prior browser behavior remain intact.
2. **Complete Phase 4.** Integrate execution checkpoints, confirmation scheduling,
   evaluator proof checking and experience reporting. Exercise timeout salvage and
   non-reproducing failures. Run focused tests before broader service checks.
3. **Live fixture preflight.** Run one good-discovery/broken-execution loop and one
   good loop using the real configured model and production workers. Persist every
   result, including infrastructure failures. Repair the implementation when the
   gates fail; do not change fixture defects or thresholds.
4. **Integrate reliability.** Review the heartbeat migration and its dependency,
   validate schema in a disposable database, then integrate preflight and status
   reasons with both start paths. Verify a stopped worker creates no queued zombie.
5. **Integrate the UI.** Check real backend payloads and all approval/start/error
   paths. Verify zero-journey and zero-approved-test states. Inspect coverage and
   evidence links on desktop and mobile; run existing accessibility checks.
6. **Six-run acceptance.** Three broken and three good runs. Require at least 3/4
   seeded defects confirmed in each broken run, navigation detected in at least
   2/3, zero false confirmations across good runs, at least 80% terminal journeys,
   at most 20% inconclusive, and no manual queue/worker intervention. Every confirmed
   defect must show exact screenshot evidence and its confirmation attempt.
7. **Default and final regression.** Only after acceptance, select discovery mode
   by default for new runs while retaining explicit legacy/deep selection. Run
   appropriate Python and frontend checks, compare pre-existing failures, inspect
   the combined diff, and update current status with actual evidence.

## Current evidence and open work

- Focused discovery/Phase 3 batch: 33 passed.
- Browser/case/deep-evaluation regression batch: 64 passed.
- API/generation/workflow batch: 41 passed.
- Focused replay/conversion/experience/verdict batch: 17 passed.
- Contract scheduling tests: 2 passed; report API rejection checks: 12 passed.
- These batches overlap and are not a single full-suite total.
- The cloud-broker preflight failed while queued; retained record:
  `.local/contract-benchmark-cloud-failure.json`. Its outbox event was retained.
- Latest user checkpoint: loopback Kafka preflight, repeats=1 and
  `--approve-fixture-actions`, is recorded in
  `.local/contract-benchmark-preflight-20261101-retry.json` and its scorer output
  `.local/contract-benchmark-preflight-20261101-retry.score.json`. Broken
  `a703e669` confirmed 3/4 seeded defects, including navigation; Good `7ccedb4a`
  confirmed zero false defects. Both have 21/24 completed journeys (87.5%),
  provenance, report-integrity pass, and zero manual interventions. The disabled
  Continue control remains unverified (`replay_unavailable` / `policy_blocked`).
  This is one repeat per fixture, not the six-run gate. The JSON artifacts and
  CURRENT_STATE checkpoint are user-provided latest evidence; do not overwrite.
- The prior paragraph claiming 3/3 reliability and UI remain unfinished is
  superseded for implementation status: Phase 5 source and Phase 6 UI are present
  in the tree. Agent review is checking their integration against the new payload.
  Phase 4's implementation exists, but its acceptance remains open until the
  benchmark gates pass. Phase 7 must remain untouched until then.
- Immediate sequence: (a) finish three targeted independent reviews (UI/API,
  scorer, reliability); (b) fix any concrete issues and run targeted checks;
  (c) verify benchmark harness freshness, readiness, cleanup, model/cost bounds,
  and scorer behavior before spending six live runs; (d) collect two more broken
  and two more good runs, retaining every raw result; (e) evaluate all §8 gates,
  append raw tables to the benchmark record, and only then decide whether the
  default can change; (f) run final relevant regressions and update CURRENT_STATE
  and SESSION_HANDOFF. No commits or pushes.

## Latest checkpoint — 2026-11-02

- Additional targeted verification: 64 case/replay/deep-evaluator tests passed;
  47 scorer/generation/execution/replay tests passed; 74 Phase 0–3 focused tests
  passed; 21 Phase 5 readiness/start tests passed; the Phase 5 queued-run
  `status_reason` transition test passed; 27 case-assertion file tests passed.
  The UI approval page has 5 passing tests and typecheck passed. Ruff passed on
  the modified Python files.
- Three fixes landed after the five-run pre-fix diagnostic: empty or unreplayable
  journeys no longer consume the case cap; visible/enabled preconditions are
  generated only for compatible click targets; and an owner-approved failed
  precondition has an executor-ordering regression. The scorer now requires six
  unique reported, integrity-valid runs and complete good reports before passing
  the zero-false-confirmation gate.
- `.local/contract-benchmark-acceptance-20261101.json` was intentionally stopped
  after five reports because its recall/completion gates had already failed. Keep
  it as pre-fix diagnostic evidence; it is not final acceptance.
- The first repaired-batch preflight rejected a stale pre-fix run. It had no active
  steps and an accepted-delivery receipt; worker `process_command` finalized it as
  interrupted without replaying browser actions. The restarted batch then completed
  broken repeats 1 and 2: 4/4 defects (navigation included), 24/24 and 23/24 terminal,
  zero manual interventions for those reports, integrity true. Broken repeat 3 had
  a running `Billing settings navigation` execution with no step/event for >30 min,
  despite `max_seconds=240`, no pending approvals/pauses, and fresh worker heartbeats.
  The harness was stopped; worker recovery marked the run failed. Its checkpoint is
  `.local/contract-benchmark-acceptance-20261102-repaired.json` and row 3 records one
  manual recovery. This batch is incomplete and cannot pass acceptance. Do not reuse
  its two successes in the fresh six-run gate.
- Web validation: typecheck passed, build passed (existing 834.59 kB JS chunk warning),
  and serialized Vitest passed 186/186 across 38 files. Default parallel Vitest had
  four timeout failures; the serialized retry passed.
- Full Python suite: 1,213 passed, 23 skipped, 2 failed in 10m43s. The new executor
  test passed when the entire test file was rerun (27 passed); the unrelated
  visual-verifier span test passed alone and after the knowledge-worker
  observability file (7 combined passed). Consider the full-suite result
  order-sensitive and unresolved until a clean full-suite rerun confirms it.
- Next: determine why the 240-second case timeout did not finalize a stalled
  execution; add a deterministic timeout regression, fix and verify the lifecycle;
  run the clean six-run batch under a new artifact path; record six raw per-journey,
  per-assertion and replay tables in `docs/V1_BENCHMARK_RESULTS.md`; rerun the full
  Python suite and relevant web checks; then switch the default only if every §8.2
  gate passes. Update CURRENT_STATE and SESSION_HANDOFF with actual results. No
  commits or pushes.

## Token-aware execution plan

Keep the active context focused on the acceptance path. Parallel agents own the
UI/backend payload reconciliation, scorer completion, and reliability audit.
The primary owns benchmark orchestration and final integration. Do not repeat
earlier broad test suites. Use targeted commands for changed files first; run the
full acceptance suite only once the harness and safety gates are validated. Keep
updates concise and write durable checkpoints before each live benchmark batch.
If remaining context becomes insufficient, update CURRENT_STATE and
SESSION_HANDOFF with exact next commands, run IDs, test output and open blockers.

Completion means implemented behavior plus measured acceptance. Unit tests alone
do not establish autonomous discovery quality or product-defect recall.
