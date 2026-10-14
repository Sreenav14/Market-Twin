# MarketTwin V1 baseline — October 10, 2026

## Repository tested

- Requirements: `MKT.md`; repository behavior: `AGENTS.md`.
- Branch: `feat/batch-1-aws-observability`.
- HEAD: `801c2b43aab2a02189217e9e6d5c02773226b0fa` (matches the audited commit).
- The working tree had substantial tracked and untracked changes before this work.
  This baseline covers the working tree, not a pristine checkout of HEAD.
- Existing changes were preserved. No dependency installation, migration, deployment,
  external target execution, or fresh model-driven run was needed for this milestone.

## Before implementation

| Check | Result |
|---|---|
| Execution-orchestrator tests, evaluation-worker tests, result API test | 185 passed |
| Frontend TypeScript check | Passed |
| Frontend unit tests with original defaults | 20 passed, 3 failed |
| Frontend unit tests serially, 15-second timeout | 23 passed |
| Frontend production build | Passed; existing warning about a bundle over 500 kB |
| New evidence-integrity regressions before fixing code | 7 failed as expected |

The initial frontend failures were two 5-second timeouts and an upload-call-count
failure following a timeout. All passed when run serially with a longer timeout.
The repository test configuration was not changed to conceal these results.

Commands used, from the repository root:

```powershell
$env:LITELLM_LOCAL_MODEL_COST_MAP='True'
.venv\Scripts\python.exe -m pytest services/execution-orchestrator/tests services/evaluation-worker/tests services/control-api/tests/test_test_run_results.py -q -p no:cacheprovider --basetemp .local/pytest-v1-baseline
npm.cmd --workspace @markettwin/web run typecheck
npm.cmd --workspace @markettwin/web run test
npm.cmd --workspace @markettwin/web run test -- --maxWorkers=1 --testTimeout=15000
npm.cmd --workspace @markettwin/web run build
```

Installed dependencies were used directly. The local cost-map setting avoids an
unnecessary provider cost-map download; these tests are not fresh paid model runs.

## Latest completed local run

Read-only PostgreSQL inspection found run
`7976ed75-9e7a-4d94-932f-dc79595b8982`.

| Record | Count/status |
|---|---:|
| Personas | 3 |
| Missions | 2 |
| Planned journeys | 6 (3 × 2) |
| Journey result events | 6 |
| Browser steps | 101 |
| Artifacts | 223 |
| Screenshots | 100 |
| Other artifacts | 105 |
| Traces | 6 |
| Console logs | 6 |
| Network logs | 6 |
| Findings | 1 |
| Report | Completed |
| Physical artifact checks against local object storage | 223 present, no size mismatches |

The audit only emitted counts, statuses, and identifiers. It did not print target
content, screenshots, credentials, or raw report narratives. Object checks used
metadata requests, not image downloads. Database access used a read-only transaction.

This establishes that the persisted pipeline has produced a complete run and real
artifacts. It does not measure defect-detection quality or prove the report's claims.

## Earliest verified correctness failure

No earlier execution failure was established by the baseline checks. The first
reproduced trust failure was in evaluation:

1. Agent-reported failures were linked to the execution's latest screenshot, regardless
   of which step the claim concerned.
2. Finding persistence accepted evidence from an unrelated execution or missing step.
3. Missing evidence caused diagnostics to be rejected rather than retained honestly.
4. The executive summary called all findings evidence-backed.
5. Report assessment assignment occurred after the function returned, so the
   assessment was not persisted.

These were reproduced by failing tests before their fixes.

## After the first implementation milestone

- 216 targeted Python tests passed: execution, evaluation, result API, and existing
  agent-directory/journey-results tests.
- 24 frontend unit tests passed using serial execution and the stated timeout.
- Frontend typecheck and production build passed.
- Four browser checks passed across desktop Chromium and mobile Chromium, covering
  finding grouping, counts, missing evidence, report totals, existing triage navigation,
  accessibility checks, and horizontal overflow.
- Changed-file lint passed. Strict type checks passed for the changed evaluation,
  classification, and result API/repository modules (zero errors).
- A final targeted rerun after the small type and legacy-severity fixes passed
  all 80 evaluation/result API tests.

## Limits and next boundary

- Browser UI regressions use intercepted API fixtures; they are not a live pipeline benchmark.
- Artifact existence was verified, but image content was not manually matched to each claim.
- Existing historical reports were not rewritten or reevaluated.
- No controlled benchmark precision/recall or provider reliability measurements exist yet.
- Criterion membership, completeness, and agreement with persisted action outcomes
  still need the deterministic Persona Agent validation in TASK 02.
- Failed-action capture and the full journey-step inspection workflow remain subsequent tasks.

TASK 00 is complete. TASK 01 addresses the reproduced evaluation boundary; the next
implementation task is TASK 02, followed by failed-action evidence capture and the
controlled end-to-end benchmark in the document's dependency order.
