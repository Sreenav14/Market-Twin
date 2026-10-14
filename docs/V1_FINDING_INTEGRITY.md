# MKT.md study and first implementation milestone

## What the document asks us to build

MarketTwin is an evidence-first application-testing tool. Its useful output is a
small number of inspectable findings, with the goal, journey, exact browser step,
observed state, and uncertainty visible. Synthetic personas supply perspectives;
their agreement does not measure human preference or independently verify defects.

The existing source approval → frozen run configuration → planning → bounded
browser execution → persisted evidence → evaluation → report architecture is worth
preserving. A complete stored run exists locally; rebuilding the architecture would
not solve the reproduced evidence-attribution problem.

The document defines ten ordered tasks. TASK 00 establishes facts, TASK 01 repairs
finding integrity, TASK 02 validates persona reports, TASK 03 captures failures,
TASK 04 proves the pipeline on controlled fixtures, TASKS 05–08 expose the evidence
and simplify the UI, and TASK 09 establishes the release gate. The explicit V1
acceptance checklist, rather than a completion percentage, remains the finish line.

## Audit findings compared with the working tree

| Finding | Current inspection | Action/status |
|---|---|---|
| F1: unrelated latest screenshot | Confirmed in `find_preferred_evidence` | Removed recency fallback; only exact cited steps can be linked |
| F2: self-reports promoted to defects | Confirmed; repeated criteria also raised severity | Reports and repeated claims remain unverified; repetition is informational |
| F3: criterion evidence not fully validated | Schema allows optional criterion/step references without mission/execution reconciliation | TASK 02; this milestone checks evidence ownership but does not claim full report validation |
| F4: failure screenshot gap | Tool exception handling remains a separate failure-recording path | TASK 03; evidence absence stays visible |
| F5: journey UI missing | Audit is partly stale: journey summaries/API already exist; `JourneyDetailPage` remains a placeholder | Reuse those summaries; later add ordered steps and evidence inspection |
| F6: mocked E2E is not live proof | Still applies | Keep UI regressions; controlled benchmark remains TASK 04 |
| F7: planning diagnostic regenerates a plan | Diagnostic is outside this milestone | TASK 07; do not use it for the read-only baseline |
| F8: report overstates verification | Confirmed; assessment also failed to persist | Corrected wording, separate counts, assessment persisted before return |

The code has advanced beyond several statements in the audit. Existing application,
knowledge review, persona-directory, run collection, and evaluation work must be
assessed before implementing duplicate functionality. The current UI uses a light
theme; the document's dark-theme instruction does not justify a theme rewrite.

## User's decision about repeated claims

Retain repeated cross-persona claims as unverified observations under **Needs
Verification**. Preserve the claim and criterion text and links to the relevant
journeys, which identify personas and missions. Link only actual cited execution
steps and any screenshots captured at those steps. Missing or inconclusive evidence
must leave the observation unverified.

Repetition does not increase severity, contribute to confirmed issue totals, or
constitute independent proof. Relevant visual verification creates its own exact
evidence-linked issue; the original agent observation remains distinguishable.

## Minimal implementation and contract

No database migration or new service is needed. Existing `Finding.category`,
`FindingJourney`, `FindingEvidence`, `ExecutionStep`, and `Artifact` are reused.
One shared category classifier supplies the API/report distinction:

| Existing category | `finding_kind` | `verification_status` | UI group |
|---|---|---|---|
| `visual_criterion` with valid screenshot/step/journey linkage | `observed_product_issue` | `verified_visual` | Confirmed issues |
| `policy`, `execution_reliability` | `test_execution_issue` | `not_applicable` | Test execution issues |
| Journey outcomes, repeated claims, unknown/legacy categories, missing visual evidence | `not_verified` | `unverified` | Needs Verification |

Severity is independent of verification. Repeated claims use `info`, including API
display of older repeated-claim rows that previously stored a higher severity.
Frontend fallback for responses without classification fields is conservative:
absence of a verification contract does not establish a confirmed issue.

Finding creation verifies that journeys belong to the run, artifacts and steps
exist, and evidence belongs to the linked journeys. Visual references are pinned
to the verifier's exact execution, step, and artifact IDs. No latest screenshot,
trace, or final step is substituted when a claim has no valid citations.

Unverified observations and execution diagnostics may be stored without evidence;
confirmed visual findings may not. Read paths check actual screenshot linkage before
classifying visual findings. Reports expose confirmed issue, unverified observation,
and execution diagnostic counts separately. UI confirmed totals and severity totals
exclude unverified observations and execution diagnostics.

The report now labels journey counts as **agent-reported outcomes**, avoids the
blanket phrase “evidence-backed,” and states that no confirmed findings does not
establish a defect-free application. Assessment is assigned before report persistence.

## Verification and review

Regression coverage includes unrelated screenshots, missing steps and artifacts,
cross-execution and cross-run references, mismatched steps, wrong execution attempts,
exact visual evidence preservation, missing-evidence diagnostics, repeated-criterion
citations, repetition without corroboration, classification, report counts, and
assessment persistence. Existing worker retry tests remain in the passing suite.

From the repository root:

```powershell
$env:LITELLM_LOCAL_MODEL_COST_MAP='True'
.venv\Scripts\python.exe -m pytest services/execution-orchestrator/tests services/evaluation-worker/tests services/control-api/tests/test_test_run_results.py services/control-api/tests/test_agent_directory_and_journey_results.py -q --tb=short -p no:cacheprovider --basetemp .local/pytest-v1-final
npm.cmd --workspace @markettwin/web run typecheck
npm.cmd --workspace @markettwin/web run test -- --maxWorkers=1 --testTimeout=15000
npm.cmd --workspace @markettwin/web run build
$env:MARKETTWIN_WEB_URL='http://127.0.0.1:5180'
npm.cmd --workspace @markettwin/web run test:e2e -- --grep 'repeated persona claims|completed test: triage' --workers=1
```

The frontend preview runs at `http://127.0.0.1:5180/`. Review images are saved at:

- `artifacts/v1/needs-verification-chromium.png`
- `artifacts/v1/needs-verification-mobile-chromium.png`

These are rendered screenshots of the actual frontend with test fixture data,
not real product-defect findings. Browser tests also check accessibility and overflow.

## Remaining limitations and focused next steps

1. Implement TASK 02: deterministically reconcile mission criteria, agent status,
   and actual execution steps before persisting the report. Evidence linkage checks
   do not prove the semantic truth of every agent sentence.
2. Implement TASK 03 without masking original browser failures or weakening policy.
3. Run TASK 04 against a controlled authorized fixture with known good, broken,
   ambiguous, and blocked cases. Start with raw counts; a tiny benchmark cannot
   substantiate the proposed percentage gates.
4. Reuse existing journey APIs and components for exact-step inspection after the
   benchmark, rather than creating separate persona, mission, and evidence dashboards.

Production infrastructure, human-assisted authentication, vector databases, persona
portraits, sentiment scores, and new orchestration frameworks remain deferred as
MKT.md specifies. This milestone makes no release-readiness or live detection-quality claim.
