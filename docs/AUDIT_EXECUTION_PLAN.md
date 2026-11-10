# MarketTwin audit execution plan — revision 2

Status: planning checkpoint requested by the owner on 2026-11-10. Implementation is paused. Existing test processes may still finish; collect their outputs before starting any replacements. Do not restart the audit or discard current edits.

## Execution priorities and decision rules

This revision corrects weaknesses in the first plan and the preceding audit:
overlapping heavy runners, disabling tracing during tracing tests, changing report
behavior before the full architecture was clear, and not maintaining the file
checklist as review proceeded. The operating rules below govern the detailed steps.

| Order | Concrete next action | Required exit evidence |
|---|---|---|
| 0 | Collect pending database/browser results; identify audit-owned processes; separate pre-existing edits from audit edits | One accurate command ledger; no unknown or duplicate audit runners |
| 1 | Trace dispatch in `run_executor.py` into harness/persona/slop, then Room, case execution and Board persistence | Requirement-to-source map showing implemented, partial, missing and decision-blocked behavior for each kind |
| 2 | Verify safety, durability, evidence and completion before presentation work | Reproductions and passing regressions for confirmed root causes; explicit unresolved risks |
| 3 | Complete the authorized Board report replacement against the owner's full contract | Persisted synthetic Board -> evaluator -> API -> UI; correct coverage/verdict and owned evidence |
| 4 | Complete remaining file and workflow coverage in dependency order | No silently omitted application source or feature; clear tested versus read-only evidence |
| 5 | Run final checks once source is stable, then deliver | Consolidated outcomes tied to the final working tree, not a mixture of earlier revisions |

Audit priorities do not reorder the retained MKT implementation plan. If a product
decision blocks one task, isolate that dependency and continue independent checks.

### Architecture questions to answer before more edits

- **One engine:** do `harness_run.py`, `persona_run.py` and `slop_run.py` share the
  Board/lifecycle, or merely the dispatcher? Three functioning executors do not by
  themselves satisfy the required common engine.
- **Boss/Lead:** identify actual call-sites for exploration, ranking and recovery.
  A helper in `models/ask.py` is not implemented supervision until the live caller
  invokes it and code validates its proposal. Watch streaming is not a Lead Agent.
- **Worker/Room:** trace context/session identity across items, login, restart,
  defect proof and persona exceptions. Distinguish a browser process from a context.
- **Ask door:** inventory all model-call sites. Reconcile deterministic defaults
  with the requirement “Model API today.” Do not assume Decisions works because a
  client exists, or treat mocked answers as calibration.
- **Report:** review `harness_report.py`, `board_evaluator.py`, evaluation dispatch,
  results API and `HarnessReport.tsx` as one contract. Do not bypass evidence checks
  simply to make the unfinished draft's test pass.

Narrow wiring/behavior repairs are within the audit. Building a new supervisor,
merging executors, enabling write mode, choosing abandoned-park policy, or changing
verdict thresholds requires a concrete proposal before implementation.

### Decisive verification cases

Map existing tests to these cases first. Add only missing reproductions; do not
create a parallel test framework or assume mocked repositories prove transactions.

| ID | Contract | Cases that distinguish correct behavior from a superficial pass |
|---|---|---|
| C1 | Honest Close | Empty discovery, checkpoint page, missing Board, pending/running/parked items, failed checkpoint: no false completed result |
| C2 | Durable work | Crash before action, after external effect but before save, and after committed result; duplicate delivery; restart. No lost items or blind replay of uncertain effects |
| C3 | Result accounting | Duplicate publish/retry and Close sweep: exactly one logical terminal result per item, proven in saved data, not just a flag |
| C4 | Single control key | Worker/human race, stale generation, disconnect, expiry, resume and cleanup; retained login must be verified |
| C5 | Observed outcomes | Visible-but-no-effect button, menu opening, changed calculation, delayed result and timeout: visibility cannot establish success |
| C6 | Fresh proof | Fail/fail, fail/pass, fail/timeout, different failure, missing/foreign evidence: only supported repeat failure becomes broken |
| C7 | Enforced budget | 0/1/299/300/301 items, mid-run discovery, all-blocked work and exhausted model budget; counters and omitted-item reasons reconcile |
| C8 | Safe default | Delete/submit/pay-like controls inventoried with reasons, never silently executed; ambiguity remains blocked |
| C9 | Park/resume | 15-minute default, 30-minute cap, two-minute warning, extension boundary, restart and behind-login inventory; displayed deadline is not expiry enforcement |
| C10 | Typed model gateway | Invalid output, refusal, timeout, backend outage, calibration off/on, budget exhaustion and deterministic fallback; no paid calls |

### Report replacement acceptance

The owner authorized completing the replacement, not removing its required verdict.
Native Explore & Test and supported historical harness runs must route correctly;
persona/slop and historical reports remain readable. Verify:

- Checked X of Y found, explicit owner exclusions, every miss named with its saved
  reason. A missing reason is exposed as a data gap, never invented.
- Board-derived verdict under the agreed rules; no legacy findings or persona
  impressions silently influence it. Existing threshold semantics need review.
- Missing, malformed, duplicate, contradictory or foreign records cannot manufacture
  success or a confirmed defect. Status strings alone are not sufficient proof.
- Failed generation rolls back; retries do not duplicate results; quarantine is
  recoverable; evidence links resolve to the correct run/journey.
- A real persisted synthetic Board reaches the API and browser. Label provider
  mocks and API interception separately from database/browser integration.

### Efficiency and evidence controls

Run one heavy test runner at a time; overlap only lightweight review/bookkeeping.
Do not edit a subsystem while its tests run. Record relevant file hashes with each
result and invalidate affected evidence after changes. Every command needs its
nonsecret overrides, exit code, log and outcome; silence is not completion.

Do not combine isolated reruns into a claim that a full suite passed. Diagnose
timeouts before retrying; no global timeout increase or assertion weakening to get
green. Preserve stale-test changes with their requirement-based justification.
Prior passing tests/builds are reusable only for unchanged behavior.

Classify the 39 lint and 191 typing diagnostics by root cause; do not suppress them
wholesale. The CI switch to `npm install` removes the missing-lockfile failure but
does not establish reproducible dependencies: lockfile policy remains a separate
decision. Avoid unrelated style work and restructuring while correctness gates are
open. Progress updates should report questions resolved, not just commands launched.

Coverage records must include path, content hash, full/partial review scope,
requirements/callers examined, finding IDs, applicable checks and behavior status.
Searches prioritize review; they never count as semantic coverage. Generated,
vendored and binary files may have explicit exclusions; first-party source cannot
be excluded merely because it is large.

## Scope and acceptance

Audit the current working tree, including pre-existing untracked files. Git HEAD is only a reference for preserving changes. Preserve T00–T13 ordering. The owner's Boss / stateless Worker / Browser Room / durable Board specification is the intended architecture; distinguish intended behavior, implemented behavior, and freshly verified behavior. Completing the two unfinished report modules and their test is authorized, but their initial outcome-only design must preserve the owner's required Board coverage and verdict.

Done means every in-scope file has an explicit review disposition, every discovered feature has a verification row, accessible applicable checks have final outcomes, confirmed repairs have regression evidence, and outstanding access/design blockers are named. Tests, automated scans, and source reading are separate evidence types. No production changes, paid calls, commits, pushes, or external messages.

## 1. Consolidate existing evidence before more work

- Collect outcomes from audit-owned sessions and `.local/audit-20261108/` logs; identify interrupted or timing-contaminated runs.
- Record an updated Git status and the audit's own diff separately from the initial patch. Preserve all existing work.
- Update `audit-20261108-coverage.json`, which currently defaults to unreviewed; record full versus partial reads honestly.
- Reuse valid evidence: web typing/build, 35 URL identity/harness checks, nine run-label/status checks, 23 tracing rechecks, and fresh isolated migration upgrade. Later edits require only affected rechecks before the final gates.

Exit: one command ledger, file checklist, feature matrix, and authoritative requirement map; no duplicate test processes.

## 2. Audit the vertical execution contract first

Trace one run through API creation -> dispatch -> Boss -> Board -> Room -> Worker -> checkpoint -> Close -> report -> frontend. Inspect actual callers and failure paths, not just module names.

| Invariant | Required verification |
|---|---|
| Boss alone finishes a run | Empty discovery, nonterminal items, missing result records and failed persistence cannot produce false completion |
| Board preserves work | Crash/restart retains completed items; no silent removals; exactly one result per finished item; each miss has a reason |
| Stateless Worker | Executes one item; returns outcome evidence; worker failure cannot erase committed work |
| Room and control key | One run browser; worker/human exclusion; retained login; clean proof/persona exceptions; teardown on errors |
| Lead supervision | Inventory exploration, prioritisation and recovery call-points actually wired; no browser or completion authority |
| Typed ask door | All model questions use the gateway; calibration controls Decisions; deterministic fallback; bounded calls and cancellation |
| Safety/budget/proof | Read-only default; explicit write boundaries; 300-item bound; observed outcome rather than visibility; fresh-context repeat failure |
| Park/resume | Deadlines, warning, extension, restart, retained session and post-login discovery; distinguish unresolved expiry decisions |
| Report | Board-only coverage, named omissions and verdict; persona quotes and three separate slop families; evidence ownership |

For each discrepancy: reproduce first where practical, make the smallest correction, then rerun its regression. Changes requiring a new architectural or product decision are proposals, not silent rewrites.

Exit: the main workflow has an evidence-backed contract map; high-impact failures are fixed or explicitly blocked.

## 3. Review the remaining repository systematically

Review by responsibility: authentication/authorization; applications/targets; knowledge ingestion; evidence/storage; worker retries/concurrency; shared schemas; frontend navigation/forms/state; database/migrations; dependencies/configuration/scripts/CI; documentation.

Read every changed line and affected callers. For unchanged files, use a file-by-file checklist and automated scans to prioritize review, never to mark semantic review complete. Rank findings by impact; distinguish reproduced defects from concerns. Avoid formatting churn and broad restructuring. Resolve static diagnostics by cause and affected contract, not blanket suppression.

Exit: every application source file has completed semantic review; other files have reviewed or justified excluded status. Partial/unreviewed entries remain visible while work is in progress and prevent an exhaustive-review claim. All findings have references and practical impact.

## 4. Verify real workflows in isolation

- Use the disposable PostgreSQL container `markettwin-audit-20261109`, port 55439, with synthetic data; collect pending persistence checks before repeating them.
- Test migrations, authorization boundaries, rollback, duplicate actions, recovery, and actual database writes/reads.
- Exercise real Chromium UI at desktop/mobile widths: happy/invalid/loading/error/empty states, keyboard/focus, accessibility, console/network errors.
- Keep intercepted API browser tests clearly labeled. Add real API/database integration where safely available; do not confuse either with paid agent/provider acceptance.
- Test execution against local fixtures with deterministic outcomes; use provider mocks for failure/timeout/budget mechanics. Paid calibration and external identity/provider acceptance stay blocked unless separately authorized.

Exit: every feature row has expected behavior, checks, evidence, and pass/fail/blocked status.

## 5. Run final gates once the tree is stable

Run focused checks during repairs. After the last edit, run the relevant full Python and frontend suites, production typing, lint, web typecheck/build, lock/config checks and browser matrix once. Investigate failures; repeat only affected gates unless a fix crosses subsystem boundaries.

Use one heavy test runner at a time on this Windows workspace. Overlap only lightweight independent reads/checks. Keep tracing enabled in tracing tests; the prior global SDK-disable setting invalidated eight failures. Preserve original failures and retries in the ledger. Do not increase test timeouts to conceal bugs.

Exit: final results correspond to the same recorded working tree, with environmental failures distinguished from product failures.

## 6. Deliver and clean up audit resources

Finish `AUDIT_20261108.md`, the coverage checklist and feature matrix. Document fixes, exact commands, results, remaining risks and separately proposed structural work. Update CURRENT_STATE and SESSION_HANDOFF. Stop only the disposable audit container/processes created for this audit after their evidence is captured; preserve logs and all existing services/data.

Do not claim full completion while file review or accessible workflow checks remain unfinished. Do not estimate completion from passing-test percentages alone.

Audit completion and application readiness are separate conclusions. A completed
audit may conclude that the product is not ready; it may not hide unfinished review
behind passing test counts or treat historical measurements as current acceptance.
