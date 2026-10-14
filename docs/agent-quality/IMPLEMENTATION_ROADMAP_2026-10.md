# Deep feature testing: analysis and parallel implementation roadmap

Prepared 2026-10-14 against the existing dirty working tree. Source plan: [MKT.md](../../MKT.md).
This document separates implementation readiness from measured agent quality.

## Assessment

The plan identifies the right central problem: a successful browser action and a
schema-valid persona report do not prove that a feature satisfies a requirement.
Detailed testing needs independently specified cases, recorded observable checks,
and honest accounting for work that could not run. More personas, larger output
budgets, and interface polish cannot substitute for those checks.

The plan is substantially stronger than a prompt-only change because it includes
ground truth, case isolation, bounded execution, source provenance, exact evidence,
and compatibility with the existing runtime. Its event-first pilot and one
persisted journey per independent case avoid unnecessary database migrations.
Preserve Python Playwright, ADK, approved knowledge, Kafka/outbox, authorization,
and the current artifact pipeline.

However, the remote audit describes committed HEAD rather than all current local
work. HEAD is `801c2b43aab2a02189217e9e6d5c02773226b0fa` on
`feat/batch-1-aws-observability`; substantial pre-existing changes must be retained.
A matching HEAD does not mean the working tree matches the audited implementation.

## Verified discrepancies and their implications

| Plan's inspected behavior | Current local behavior | Implementation consequence |
| --- | --- | --- |
| Planner output limit 1,024; persona uses 512 | `META_AGENT_MAX_TOKENS=4096`; `PERSONA_AGENT_MAX_TOKENS=2048` | Establish current baseline; do not repeat proposed token increases blindly. |
| Report schema without execution consistency checks | `workflow/report_validation.py` and focused regressions exist | Extend validation for case assertions; preserve existing safeguards. |
| Failed actions generally lack evidence | `browser/tools.py` already captures best-effort read-only failure state | Test and reuse; no duplicate capture path. |
| Generic latest evidence chosen for reported criteria | `find_reported_evidence` selects exact execution/step references | Ownership/linkage is stronger, but semantic relevance still needs verification. |
| Repeated persona claims can inflate confidence | Existing finding classification preserves unverified observations | Keep this distinction when adding assertion-grounded cases. |
| Journey/evidence pages are placeholders | Authorized journey detail API and step-selected evidence UI exist | Extend the current contract with case provenance and assertions; avoid rebuilding. |
| No controlled fixture or actual pipeline measurements | V1 fixture, harness and historical results exist | Preserve old benchmark truth; add missing controlled same-feature variants. |
| Three personas and up to four missions | `MetaAgentPlan` still enforces these limits and repository persists Cartesian expansion | Add a separate opt-in deep contract and persistence bridge, not a legacy schema rewrite. |
| Browser observation/locator limitations | Global exact semantic locators and 2,000-character model ARIA cap remain | Scoped observation and field state remain justified fixture-driven work. |

The existing `testing_depth.py` chooses one, two, or four missions; it is a
legacy breadth setting, not a feature test-case planner. Source search found no
current `TestCaseSpec`, deep-feature plan/event pipeline, or per-case assertion
results in the execution runtime. These are the major remaining product gaps.

Historical benchmarks demonstrate actual browser execution and stored artifacts,
but also insufficient screenshot context, conditional-precondition mistakes, and
inconclusive/missed seeded defects. Their counts must not be republished as
validated precision or recall. See [baseline](BASELINE_2026-10.md) and
[historical benchmark results](../V1_BENCHMARK_RESULTS.md).

## Complete work breakdown

Statuses below describe the starting point for this implementation session.
Existing partial functionality does not satisfy a new deep-mode acceptance gate.

| Task | Remaining deliverable | Reuse / starting state | Required verification | Work owner |
| --- | --- | --- | --- | --- |
| T00 baseline | Current-code discrepancies, sanitized failure matrix, actual checks and limitations | Existing baseline/history are useful but older | Recorded tests; historical evidence distinguished from fresh measurement | Baseline agent |
| T01 fixture | Same-feature good/bad variants, independent manifest, direct browser oracle runner | Existing V1 mixed fixture and live harness | Real non-AI Chromium checks; explicit local scope; blocked/unknown probes | Fixture agent + harness agent |
| T02 planning | Versioned `FeatureScope`/`TestCaseSpec`, deterministic validation/budget trimming, immutable plan, one-persona case bridge | Legacy Pydantic models and `PlanRepository` | Meaningful positive/negative/boundary/recovery cases, invalid plans rejected, legacy unchanged | Planning workstream after T01 |
| T03 observation | Bounded form/region state and scoped semantic locators | Existing controller, observation and tool recorder | Duplicate controls, ambiguity, stale state, redaction, bounded outputs | Browser workstream after case targets fixed |
| T04 safe actions | Only fixture-required check/uncheck, focus/keyboard, viewport preset | Existing action/network policy | Policy → operation → recorded artifact → real fixture scenario | Browser workstream, same owner as T03 |
| T05 assertions | Typed expected/observed records and deterministic verdicts tied to exact execution/step | Existing step and artifact persistence | Absent alert fails, delayed state passes, unavailable state unverified, foreign evidence rejected | Assertions workstream after T02–T04 |
| T06 case execution | Sequential isolated cases, budgets/recovery, terminal events, truthful coverage | Existing ADK workflow, journey runner, persistence | 6–8 cases finish within bounds; skips/blocks/errors accounted for; legacy unchanged | Runtime workstream after T05 |
| T07 report integrity | Extend existing validation to assertions and impossible claims | Much legacy validation/capture already exists | Invalid claims stay diagnostic; original action failure retained | Runtime/evidence workstream |
| T08 findings | Assertion-grounded failures with source and exact supporting evidence | Existing classification, focused visual evidence and prerequisite checks | No irrelevant/foreign proof, tool errors distinct, reconciled case totals | Evidence workstream after T05/T07 |
| T09 experiments | Controlled one-variable budget/context/model comparison | Existing snapshots and increased budgets | Actual per-case counts, elapsed time, usage/cost when available; three core repeats | Benchmark workstream after T05/T06 |
| T10 generalization | Authorized form, list/filter and navigation workflows | Existing authorization and approved knowledge | Independently reviewed repeatable checks beyond fixture | Benchmark workstream after T01–T09 |
| T11 API | Add case/coverage/assertion semantics to existing authorized result surface | Current paginated journeys and artifact access | Cross-user/run rejection, pagination, safe output, historical compatibility | API workstream after T06/T08 |
| T12 UI | Case coverage, provenance and expected/observed alongside exact evidence | Current journey/findings/report UI | Live backend/storage/UI path, responsive/accessibility; human comprehension trial | UI workstream after T11 and quality gate |
| T13 release | Accurate support/limits/docs and compatibility verification | Existing operational/docs/checks | Safety/evidence release checklist, actual benchmark and no unsupported claims | Integration owner after required gates |

## Parallel execution strategy

The user explicitly requested multiple implementation agents. The first wave
assigns independent file sets to three agents while the integration owner performs
cross-cutting analysis, frontend baseline checks and continuity updates:

1. Baseline agent owns the new baseline document and sanitized failure matrix.
2. Fixture agent owns the new fixture, ground-truth manifest and fixture tests.
3. Harness agent owns runner/scoring code and its focused tests.
4. Integration owner owns this roadmap, review, combined verification and session records.

The fixture and harness agents agree the manifest interface directly. Historical
V1 fixture behavior remains reproducible. A direct fixture run establishes oracle
truth and is labeled `direct_fixture`; it cannot be represented as an autonomous
MarketTwin quality score. Legacy journey narratives cannot soundly be matched to
new case IDs, so autonomous scoring needs the T02/T05/T06 binding first.

Later waves can reuse the same agents under these boundaries:

- After fixture acceptance: planning contract/bridge and browser inspection may
  be prepared independently against the agreed fixture interface. Integration
  requires the validated case contract; scoped locator and action edits share one owner.
- After planning/browser acceptance: assertion work precedes runtime integration;
  evidence diagnostics can be reviewed in parallel. Do not let multiple agents
  edit `controller.py`, `tools.py`, or `journey_executor.py` simultaneously.
- After recorded cases exist: evaluator and API changes can proceed in separate
  services against the agreed versioned event contract. Benchmark scoring can be
  developed alongside them, with a single owner for each test/schema surface.
- After API/quality acceptance: UI work and compatibility documentation can run
  in parallel. Measured model experiments and live benchmarks remain serialized
  when they share fixture ports, queues, accounts or state.

Parallel software development does not authorize parallel persona executions or
changes to the runtime's database-session concurrency. Each case keeps one stable
browser context during its steps and starts with independent fixture state.

## Decisions needed in implementation, not additional infrastructure

- Freeze schema version, case/requirement IDs and actual event payloads before
  API/evaluator consumers are written. Existing JSONB events are transport, not a
  substitute for validation and ownership checks.
- Define verdict precedence explicitly: policy block and infrastructure failure
  cannot become product failures; missing oracle/observation is unverified;
  unstarted budget-trimmed candidates are not-run, with no fabricated execution.
- Bound plan candidates, case actions, retries, assertion waits, and total run
  time outside model instructions. Model output cannot increase authorization.
- Document where fixture-only safe submissions differ from customer targets.
  Runner-owned CSS selectors are test instrumentation, not new agent tools.
- Preserve requirements as data. Approved knowledge and page content cannot
  inject authority, raw code, arbitrary selectors or unsafe test values.
- Prefer conservative equivalence keys for plan deduplication; do not discard
  distinct preconditions using an LLM judgment alone.
- Keep source certainty separate from assertion satisfaction. An inferred
  expectation may be observed to fail without becoming a confirmed business bug.
- Keep costs unknown when token usage/pricing is absent. Counts and denominators
  matter more than small-sample percentages or favorable narrative summaries.

## Completion standard

The first product milestone remains a real bounded 6–8-case feature run with
independent assertions, reproducible seeded defects, exact evidence and truthful
limits. Fixture tests, mocked UI tests, a completed report, and physical artifact
existence individually cannot establish that milestone. No deployment, external
target testing, schema migration, or new LLM worker is necessary for this first wave.

Fresh frontend typecheck and production build passed on 2026-10-14. The build
retains its existing >500 kB JavaScript chunk warning (544.84 kB). Agent-owned
test results and remaining gates are recorded in the baseline and session checkpoint.
