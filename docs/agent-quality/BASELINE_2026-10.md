# MarketTwin deep-testing baseline — 2026-10-14

## Scope and result

This is T00 of the **2026-10-14 MKT.md deep-testing plan**, not the older
TASK 00–09 plan described in October 10 continuity records. The user authorized
parallel engineering agents; the product's sequential browser execution remains
unchanged. This baseline agent changed only this report and the adjacent sanitized
failure matrix. No planning was regenerated, historical findings rewritten,
external target executed, dependency installed, service started or deployment made.

The local code already contains substantial evidence-integrity and inspection
improvements missing from MKT.md's remote-source inventory. It still uses the
three-persona × mission plan rather than explicit feature cases with deterministic
assertion oracles. The historical controlled benchmark demonstrates specific
planning and evaluation failures, and later corrections, but **does not establish
current precision, recall, coverage, cost or repeatability**.

T00's unavailable-environment allowance applies: an attempted read-only query of
known local fixture runs failed with `ConnectionRefusedError`. Historical records
and their exact screenshots could not be re-inspected today. T01 may proceed with
a controlled fixture; model-quality and release gates remain open.

## Reproducible checkout and runtime

| Observation | Verified result on 2026-10-14 |
|---|---|
| Local branch | `feat/batch-1-aws-observability` |
| Local HEAD | `801c2b43aab2a02189217e9e6d5c02773226b0fa` |
| Cached tracking reference (`git rev-parse '@{u}'`) | Same commit |
| Live remote HEAD | Not fetched or verified during this baseline; a cached tracking reference is not a live remote check |
| Workspace | Substantial modified, deleted and untracked files existed before this work; all preserved |
| Python | 3.12.12 |
| Node | v24.18.0 |
| Installed Python Playwright | 1.61.0 |
| Installed Google ADK | 2.5.0 |
| Frontend build's Vite version | 8.2.2 (root agent's completed command) |
| Default shell | Failed startup: helper setup refresh error |
| Reviewed escalated read/test commands | Executed successfully |

Commands used to verify checkout and installed package versions:

```powershell
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git rev-parse '@{u}'
git status --short
.venv\Scripts\python.exe --version
node --version
.venv\Scripts\python.exe -c "from importlib.metadata import version; print('playwright=' + version('playwright')); print('google-adk=' + version('google-adk'))"
```

The baseline is the dirty working tree, not a pristine checkout of the named
commit. Parallel fixture/contract work can add files during this session; this
report's source conclusions concern the existing production paths inspected.
No clean/reset/revert action was used. Full status output was inspected, not
reproduced here to avoid confusing unrelated work with this task's changes.

## Current code versus the MKT.md inventory

Paths below are relative to the repository root. `EO` means
`services/execution-orchestrator/src/markettwin_execution_orchestrator/` and `EW`
means `services/evaluation-worker/src/markettwin_evaluation_worker/`.

| MKT.md audit statement | Verified local behavior | Implication |
|---|---|---|
| Meta output budget 1,024 | `EO/agents/meta_agent.py`: `META_AGENT_MAX_TOKENS = 4096` | Do not implement the already-made token increase or attribute shallow testing to the old value |
| Persona uses factory's 512-token default | `EO/agents/persona_agents.py`: explicit `PERSONA_AGENT_MAX_TOKENS = 2_048`; factory fallback remains 512 | 512 is not the default persona factory call's effective output budget |
| Exactly 3 personas and 1–4 missions | Still required by `EO/agents/schemas/plan.py`; low/medium/high testing-depth limits further bound missions | Systematic explicit case classes are still absent from this legacy schema |
| Broad mission contract only | `EO/agents/schemas/mission.py` still has ID/name/objective/criteria/priority, with new nonblank/distinct criterion checks | Validation prevents duplicate criteria; it does not encode preconditions, input partitions or executable oracles |
| Every persona × mission runs sequentially | `EO/workflow/journey_planner.py` retains Cartesian expansion; `adk_workflow.py` builds a real SequentialAgent journey group | Engineer parallelism does not authorize parallelizing the shared product execution session |
| Worker 90s versus request 180s | `EO/workflow/run_request.py` default 90; `run_executor.py`, `multi_persona_executor.py` and `journey_executor.py` request defaults 180 | Retain this distinction; historical effective budget needs a saved configuration, not inference from a class default |
| No independent report consistency checks | `EO/workflow/journey_executor.py` invokes `validate_execution_report`; `workflow/report_validation.py` validates assigned criteria and owned completed actions/artifacts | Report consistency is implemented; semantic truth of a criterion remains a separate boundary |
| Latest screenshot fallback for findings | `EW/persistence/evaluation_repository.py` exposes `find_reported_evidence`; deterministic evaluator uses exact reported references | The audit's latest-screenshot description is superseded locally; relevance still needs verification |
| Failed actions have no evidence capture | `EO/browser/tools.py` calls `record_failure_evidence` after recording failure, with bounded state capture | Existing failed-step capture must be reused rather than duplicated |
| Product findings conflate agent claims | `packages/shared-python/.../finding_classification.py` separates visual product issues, unverified observations and execution diagnostics; report generator uses these groups | Classification is improved, but its visual label alone is not benchmark ground truth |
| Visual verifier only has image judgment | `EW/visual_verifier.py` checks strict `preconditions_met`; visual evaluation requires focused evidence for failed-state promotion | These safeguards reduce specific false confirmations; they do not constitute deterministic UI assertions |
| No live ordered journey API or usable journey UI | Current result API, `RunJourneysPage.tsx` and `JourneyDetailPage.tsx` exist; continuity records document authorized list/detail and exact step artifacts | T11/T12 should inspect and extend current contracts, not recreate placeholders |
| No controlled benchmark | `services/execution-orchestrator/scripts/run_v1_benchmark.py` and existing `tests/fixtures/v1_benchmark/index.html` exist | Reuse proven safety setup; existing historical benchmark is narrower than the new deep-feature manifest |

Current planning also includes an application-specific end-to-end blueprint,
knowledge grounding, isolation instructions and mandatory coverage-gap guidance
in `EO/workflow/planning.py`. These are prompt/structural improvements, not
measured proof of comprehensive feature coverage.

Still present and not established as causal: `/no_think` in Meta/persona prompts;
80 visible elements in `browser/observations.py`; model-visible ARIA capped at
2,000 characters in `browser/contracts.py`; no existing `assert_state` browser
tool; no keyboard/check/uncheck/scoped tool among the ten browser functions
inspected. A truncation or timeout cause requires an actual trace and provider
metadata. Do not change models, remove prompt tokens or raise timeouts merely
because these limits exist.

Approved knowledge is passed into planning by `run_request.py` and included in
the planning prompt. This inspection did not establish a full provenance-tagged
case context reaching each persona. Product targets remain governed by existing
authorization and browser policy; the historical harness explicitly restricts
database/storage to loopback and uses the local-development policy for its fixture.

## Historical measurement, separated from today's checks

Sources are [V1_BASELINE.md](../V1_BASELINE.md),
[V1_BENCHMARK_RESULTS.md](../V1_BENCHMARK_RESULTS.md),
[CURRENT_STATE.md](../CURRENT_STATE.md) and
[SESSION_HANDOFF.md](../SESSION_HANDOFF.md). These are retained earlier
measurements, **not independently repeated or verified against the DB today**.

| Historical run | Recorded result | Interpretation |
|---|---|---|
| `ef725d32-45ac-4456-bf75-e1ed00c6d8f8` (initial broken) | 12 executions, 68 steps, 185/185 physical artifacts; 10 inconclusive, 1 partial, 1 failed; 15 unverified observations, 1 stored visual issue | Manual review rejected exact screenshot step 768 as sufficient proof; report completion and object existence did not establish a valid detection |
| `ef9bab44-953b-4c96-b621-7f1bfc82c8bf` (initial ambiguous) | 3 passed journeys, 35/35 artifacts, no findings | Planner tested recognizing uncertainty rather than final delivery; earliest demonstrated boundary was planning/oracle selection |
| `11fecf58-7e65-4c83-9c37-a5a016bf4f1f` (initial policy) | 3 passed journeys, 40/40 artifacts; restricted navigation blocked by network | Earliest implementation failure was missing click policy propagation; product statuses were misleading despite enforced network isolation |
| `7e2e0079-8e6f-41fa-bd95-4b1ff35ebeb2` (policy repeat) | 3 policy_blocked, null product outcomes, 3 execution diagnostics, 18/18 artifacts | Specific historical corrected behavior; not a new current safety measurement |
| `a4aeadb9-dcb7-4706-860b-0316be0cf1b9` (ambiguous repeat) | 3 inconclusive journeys but 3 false visual confirmations; 41/41 artifacts | Evaluation promoted a conditional requirement without its prerequisite |
| `bc1f4a68-5f97-49c2-981f-a4d3654f9764` (corrected ambiguous) | 3 inconclusive, zero confirmed defects, 3 unverified observations; 46/46 artifacts | Specific prerequisite guard repeat passed its intended historical check |
| `13158b2b-4910-4db3-8b47-bcc387c749ee` (working repeat) | 6 passed, 66/66 objects; initial HeadObject403, evaluation-only recovery yielded zero findings | Storage/evaluation reliability incident, not a product defect; cause was not established |
| `3d0be5e4-2d8c-40cf-80aa-a033011845b9` (target-context broken) | 12 executions, 84 steps, 220/220 artifacts; 4 stored visual findings, 14 observations | Manual review rejected Billing evidence steps 1065/1095; prompt improvements alone did not prevent false confirmation |
| `b9c94c59-d47b-4988-9037-abf5d6c443dd` (latest working checkpoint) | Completed, 6 journeys, 22 steps, 71/71 physical artifacts, zero findings | Positive control recorded in CURRENT_STATE; predates latest agent-setting/link changes |
| `25f6f762-c5b7-4910-8be7-a3aaeb41e212` (latest broken checkpoint) | Completed report `b75a07fe-9123-4047-a8f1-10b3f723ef47`; 12 journeys, 77 steps, 213/213 artifacts; 7 stored observed-product issues, 14 unverified observations | Seven stored issues are explicitly not yet manually validated detections; no valid precision/recall calculation follows |

Repeated persona confirmations are not distinct seeded defects. Some later runs
used a changed fixture with standalone destination views and recorded fixture
hashes; do not pool all historical runs into a same-fixture A/B measurement.

### Two specific failure reconstructions and missing timeline evidence

1. **Wrong-destination evidence, initial broken run.** Existing benchmark sources
   record a real seeded Billing-to-Profile navigation mismatch. The stored visual
   issue cites step 768, whose reviewed image showed the top viewport rather than
   the destination region. The failure established by review is insufficient
   observed state plus erroneous evaluation promotion, not failure of the seeded
   defect to exist. The complete sequence of earlier navigation/click/capture IDs,
   execution/journey IDs, model name, per-journey elapsed time and tokens could not
   be reread today. A later isolated verifier replay returned unverified; it was
   not a new full-pipeline run and did not rewrite the old finding.
2. **Conditional delivery, ambiguous repeat.** Sources record a pending state with
   no final delivery evidence, three inconclusive journeys and three visual
   confirmations of a conditional requirement. This supports `evaluator_error`
   with an unestablished prerequisite, not an application defect. Exact action
   timelines/artifact IDs/model/elapsed/usage were unavailable today. The later
   corrected repeat is separate history, with zero confirmations.

These are sanitized reconstructions from retained reviewed documentation, not
invented step-by-step DB traces. The adjacent JSON deliberately uses null for
unknown timelines, execution IDs, model, duration and usage. Its rows label
historical provenance and distinguish corrected repeats from initial failures.

## Checks actually executed this session

The baseline agent ran:

```powershell
$env:LITELLM_LOCAL_MODEL_COST_MAP='True'
.venv\Scripts\python.exe -m pytest services/execution-orchestrator/tests/test_persona_report_validation.py services/execution-orchestrator/tests/test_browser_tools.py services/execution-orchestrator/tests/test_meta_blueprint.py services/execution-orchestrator/tests/test_adk_workflow.py services/evaluation-worker/tests/test_finding_integrity.py services/evaluation-worker/tests/test_visual_verifier.py services/evaluation-worker/tests/test_evaluation_repository.py -q --tb=short -p no:cacheprovider --basetemp .local/pytest-agent-quality-baseline
```

Result: **75 passed, 50 warnings in 23.54 seconds; exit 0**. Warnings concern
deprecated ADK BaseAgentConfig/SequentialAgent. These protect consistency,
ownership, collection sequencing and specific verifier boundaries. They do not
run the configured planning model, establish image-model quality or complete an
autonomous feature benchmark.

The root agent executed and reported both completed checks:

```powershell
npm.cmd --workspace @markettwin/web run typecheck
npm.cmd --workspace @markettwin/web run build
npm.cmd --workspace @markettwin/web run test -- --maxWorkers=1 --testTimeout=15000
```

All exited 0. Unit tests passed 27 tests across 8 files in 105.84 seconds with
the explicit serial/15-second-timeout command above; this does not establish
the default concurrent test configuration's result. Build processed 2,049
modules and produced a 544.84 kB JS bundle;
the existing >500 kB chunk warning remains. No frontend source was edited for
these commands. No frontend e2e suite was run by this baseline agent.

Sanitized retrospective inspection used installed `asyncpg` and dotenv, required
a loopback database host, opened an explicit read-only transaction and selected
only IDs/statuses/model names/elapsed intervals/action types/artifact metadata for
the two named historical failure runs. It did not print credentials, prompts,
URLs, screenshots, raw errors or user text. Connection failed before records were
read: **`ConnectionRefusedError`**. The probe did not start services or mutate DB.
No physical artifact or image-content verification was performed today.

## Root-cause assessment and next work

**Verified current design limitation:** legacy plans lack explicit feature cases,
input partitions and deterministic assertions; Cartesian persona execution and
bounded semantic observation remain. This supports building a measurable pilot,
not asserting that a particular cap/model caused a particular failure.

**Historically demonstrated earliest boundaries:** wrong expected test objective
(planning), missing policy-status propagation (browser/runtime), and false visual
confirmation from insufficient region/prerequisite evidence (evaluation). Several
were corrected locally; the latest remaining detection count is unvalidated.

**Unmeasured hypotheses:** model budget truncation, time exhaustion, provider
reasoning suppression, persona diversity, unnecessary repeated trajectories,
and missing knowledge at the actual failing action. No finish reason, usage/cost,
saved effective model configuration or timed current trajectory was retrieved.

Next: T01's reviewed deterministic feature fixture and versioned static oracles,
with model-independent browser ground-truth checks and explicit loopback policy.
Reuse existing persistence and benchmark safety boundaries. An explicit case
contract can be developed alongside the fixture when its requirements are clear,
but runtime integration and claimed improvement require T01 evidence first.
Revisit persisted benchmark timelines after the local DB is available; review
exact images against static truth before counting any confirmed detection.
