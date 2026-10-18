# MarketTwin product audit — 2026-10-16

## Verdict: REFOCUS

MarketTwin has a functioning local execution, human-control, and evidence pipeline.
It is more than a thin model wrapper. However, autonomous defect discovery and an
advantage over ordinary Playwright are **not demonstrated**. Prioritize reliable
planning and caller-approved test oracles before expanding infrastructure or
claiming enterprise readiness.

## What actually worked

### Latest readiness correction — October 16, 23:20 local

User-reported case `selected_feature_agent_format_navigation` in run
`485b5eae-cca8-486f-9582-d9c0428cc5e3` failed because the exact region named
`Page format` was absent before clicking link `Agent`. Diagnostic: `absent_scope`.
It was not evidence of an authentication failure: target `requires_auth=false`,
no authentication verification policy. The other three cases recorded satisfied
assertions. A failed browser action is not itself a confirmed product defect.

The local `.env` also had no HITL internal keys, origins, or viewer URL, so no
canonical viewer was running. Appended only missing documented loopback settings
and a generated local internal key (never printed); existing values were preserved.
Restarted API/execution worker with no active runs; viewer binds `127.0.0.1:8020`.
API health and Kafka health return 200; Kafka reports connected/outbox enabled.
Unsigned worker lease request returns 401. Database migration is `f82e4160cb9d (head)`.

Implemented bounded generic assistance for missing/ambiguous scope or target in
read-only click preflight. One recovery attempt per case, existing same-context
viewer/ownership/generation/expiry boundaries. Human prepares the original control,
without performing the pending action. Release verifies that exact control and
configured identity when applicable, then reruns approval policy before dispatch.
No fallback selector, invented authentication success, changed oracle or automatic
replay of an already dispatched action. Generic recovery captures no reusable auth
snapshot. Policy/prohibited actions and arbitrary runtime errors remain fail-closed;
this is not an unrestricted model confidence/complexity classifier.

Journey UI now identifies planner-selected cases versus deterministic execution,
opens the first loaded failed step, explains recorded diagnostics, displays typed
expected/observed assertion results, and links evidence/human history. The API
exposes only allowlisted diagnostic reasons and validates assertion ownership.
Generic assistance completion says continuation verified, not authentication
verified. Actual database reads confirmed historical `absent_scope` and three
readable structured assertions. Direct visual inspection of that authenticated
user journey was blocked by the available browser's local sign-in state.

Final checks: 59 focused HITL/API tests passed, then the opt-in isolated PostgreSQL
lease test passed separately (resolving the one skipped test). Four real Chromium
recovery-gate checks and six frontend tests passed. Strict source Pyright passed;
Ruff passed with the existing E501 baseline excluded; frontend typecheck/build
passed (existing >500 KB chunk warning). The direct UI/API/DB/viewer recovery test
proved zero clicks before Release, one after successful verification, zero after
failed verification, consumed/abandoned checkpoints, and no generic auth reuse.
It also reran existing auth/MFA/reconnect/cancellation/expiry tests successfully.

Latest **full persisted synthetic** protected pipeline passed in
`.local/ui-integration-result-456f1f5453c44a7e936ce3ce12853e18.json`, run
`64f8f663-6e8c-4de1-b893-16fa20f1cb4f`: three passed, three blocked, two skipped;
results 409 pending -> 200 report; React report rendered; axe zero violations;
no horizontal overflow at 1440/768/390. Cleanup passed; isolated group drained old
retained commands, shared offsets unchanged. This pipeline uses a frozen fixture
plan; generic-recovery integration was tested separately, not as a Kafka case.

Operator: for login takeover, select a target explicitly requiring authentication
and provide the approved read-only identity marker in New Test. Do not enter real
passwords in planning fields. Refresh the UI for the presentation changes. The
API and execution worker are already restarted; do not launch duplicates.
External Kafka exhibited intermittent SSL failures before recovering; future
network stability and post-fix live AI quality are not guaranteed or measured here.

Interaction direction: use a selectable action timeline with before/after evidence,
as illustrated by [Playwright tracing](https://playwright.dev/docs/api/class-tracing),
and explicit interruption/resume state with side-effect checks, consistent with
[LangGraph interrupts guidance](https://langchain-ai.github.io/langgraph/concepts/breakpoints/).
This research does not require adopting another orchestration framework. Further
ideas, not implemented: one run-wide planner/action/handoff/evaluation timeline;
safe human correction of an invalid frozen plan through a new reviewed revision;
and an always-visible explanation of why assistance was requested or unavailable.

The protected synthetic workflow exercised real React, Control API, disposable
PostgreSQL/outbox, loopback Kafka, execution worker/Playwright, evaluation worker,
persisted report, results API, and React report rendering. It used a deterministic
fixture plan, **not model-generated planning**.

Latest evidence: `.local/ui-integration-result-2f92558f57a449c5aced8f57e4931359.json`,
run `deb06690-8344-48e2-8583-3ced6090527e`.

- Login/MFA, viewer disconnect/reconnect, Release, and verified resume passed.
- Five subsequent isolated contexts installed authenticated state and verified
  their authenticated role; all six execution contexts closed.
- One approved sensitive action executed once, with one completed receipt and one
  fixture effect. Three rejected actions did not execute. Duplicate decisions
  returned HTTP 409.
- Evaluation produced three passed cases, three blocked cases, two budget skips,
  zero inconclusive cases, and zero findings. Passed assertions had artifact IDs.
- Results returned expected HTTP 409 while evaluation was pending, then HTTP 200
  with the persisted report. Pending is not an execution failure.
- The report rendered in React. Its axe scan found zero violations; no horizontal
  overflow was detected at widths 1440, 768, and 390. This is not full accessibility
  certification or a complete visual review at every viewport.
- Disposable resources were cleaned; shared Kafka offsets were not reset.

The separate `.local/ui_hitl_integration.py --run` also passed actual UI/API/browser
checks for Release after disconnect **without reconnect**, cancellation preventing
resume/auth reuse, natural three-second request expiry, and five-second lease
expiry with stale-input fencing and successful reclaim. This test does not use
Kafka and must not be presented as a second complete Kafka pipeline test.

## AI quality: controlled results

Twelve authorized provider calls used the configured `openai/gpt-6-luna`, no
retries: no/minimal/richer accurate knowledge × good/seeded-bug local application ×
two repeats. Observation JSON, goal, budgets, scope, and input defaults stayed
consistent; hidden variant labels and benchmark cases were not supplied.

| Knowledge | Accepted plans | Executed browser cases | Seeded defects evidenced |
|---|---:|---:|---:|
| None | 0/4 | 0 | 0 |
| Minimal accurate | 2/4 | 2 | 0 |
| Richer structured | 0/4 | 0 | 0 |

Of 71 candidates, 60 failed schema validation; nine of the remaining eleven failed
policy validation. Common errors involved labeled form targets, action argument
shapes, incomplete semantic targets, and invented grounded expectations. Counts
overlap within candidates. Both accepted cases checked navigation and did not
check the incorrect destination heading. Other seeded checks never executed.

The production planner, validators, browser actions, and assertions ran, but
persistence used validation-only sinks. These are **not persisted E2E results**.
Evidence and reproducible harness:

- `.local/product-audit-live-evidence/results.json`
- `.local/product-audit-live-summary.json`
- `.local/product_audit_live.py`

Usage was 49,495 tokens (30,276 prompt; 19,219 completion; 24,808 input tokens
reported cached). Actual billing is unknown. There were no provider authentication
or HTTP failures. These twelve calls precede the prompt/schema correction below;
post-correction live quality has not been measured. This small, fixed-order sample
does not establish statistical precision, recall, or knowledge-treatment causality.

### Playwright comparison

A hand-authored baseline executed eight checks against each variant, twice: all
32 executions matched fixture truth. Each good observation had eight passing
checks; each bad observation had six contradictions and two passing controls.
The six contradictions cover four seeded root groups: validation bypass,
dependent role, asynchronous result, and incorrect destination heading.

Evidence: `.local/product-audit-baseline-{good,bad}/results.json` and corresponding
`-repeat` directories. This demonstrates that the fixture is testable with ordinary
automation, **not autonomous discovery by the baseline**. No AI uplift is proven.

## Root causes and corrections

| Finding | Evidence / correction | Verification |
|---|---|---|
| Persona startup rejected its own tools | Real factory exposes 15 tools; approved registry listed 10. Registered the five existing controlled functions. | Real tool-construction regression; 39 focused agent configuration/API tests passed; source Ruff/Pyright passed. New live persona execution still needed. |
| Planner instruction/schema mismatch | Models repeatedly used invalid target/argument shapes; provider schema advertised fixture-only action identity. Added explicit contract rules and removed that identity only from provider output schema. Persisted contract and safety checks remain intact. | 39 planner tests passed, including real ADK Runner boundary tests; Ruff/Pyright passed. No additional live provider calls. |
| URL comparison could hide a mismatch | Assertion code compared URLs after stripping query/fragment. It now leaves redacted URL assertions unverified and compares plain URLs exactly. | Twelve real Chromium/assertion tests passed; source/test Ruff and Pyright passed. Canary values remain absent from persisted results. Query/hash URL oracles remain unsupported until a secret-safe verification contract exists. The live observations do not prove two false positives. |
| Earlier fixture evaluator mismatch | Frozen `registration_submit` execution identity was compared to generic `click`. Existing correction validates the exact frozen identity. | Twelve focused evaluator tests and strengthened persisted E2E verdict checks passed. |
| Historical failure lacks diagnostics | Run `ac7fc095-a35e-4073-8d08-f539fc6422a5` saved only pre-plan `ValueError`, no cases/journeys. Current reviewed diagnostics were not loaded in its worker. | Approved LangSmith inspection confirmed a completed model invocation, but trace details failed to load. Exact historical raising check remains unknown. Do not blame credentials or Kafka without evidence. |

### Knowledge and oracle gap

Approved application knowledge reaches the frozen run, but Feature Cases converts
each entry into one truncated prose requirement without caller-owned assertion
definitions. Grounded expectations require an exact approved oracle, target, and
value. Ordinary knowledge selection therefore cannot supply that contract.

Controlled plumbing checks confirmed that none/minimal/rich prose does not create
approved oracles; an explicit caller-owned oracle positive control succeeds.
Extra prose ingestion alone will not solve this. Do not let the model approve its
own expected truth. A small structured oracle authoring/approval workflow is a
product gap, not an acceptable reason to weaken provenance validation.

The feature path also has only four generic safe input values. Rich domain prose
cannot automatically create authorized boundary inputs. This constrains useful
exploration independently of model knowledge.

## Architecture and actual UI observations

Actual running UI inspection covered applications, knowledge/review lists,
ingestion forms, agent settings, test search, a completed report, evidence empty
states, idle human assistance, profile/security settings, and new-run mode/depth
selection. No external run or new model-backed ingestion was submitted.

The dark interface is coherent and readable. However, a completed persona report
with all three journeys failing before browser execution still has a green
completed lifecycle label. Its diagnostic explanation is candid, but the status
can suggest success. Security/settings explicitly show missing production identity
and account-management capabilities. This is a local pilot, not enterprise-ready
production administration.

Outbox durability, exclusive leases, receipts, and evidence ownership serve real
security needs. A single execution consumer remains occupied while awaiting human
assistance; throughput is therefore limited by human response time. Do not add a
new service just for this pilot. Disposable tests use isolated groups and safely
ignore missing historical commands; ordinary startup must not reset shared offsets.

## Market assessment

Existing products already offer requirements-to-tests, AI authoring, evidence,
replay, and human intervention. Examples are
[mabl evidence](https://www.mabl.com/deliver-evidence),
[QA Wolf automation](https://www.qawolf.com/automation-ai),
[Momentic assertions](https://momentic.ai/docs/core-concepts/writing-assertions), and
[BrowserStack agentic testing](https://www.browserstack.com/docs/low-code-automation/test-recording/browserstack-ai/agentic-testing).
These are vendor descriptions, not independently measured competitor performance;
no accounts were purchased or comparative product trials run.

A plausible wedge is authenticated verification for QA/platform teams with SSO,
MFA, and sensitive writes requiring explicit human authorization and auditable
receipts. Willingness to pay and differentiation remain hypotheses. Broad claims
of autonomous bug discovery are currently unsupported by this audit.

## Prioritized next steps and limits

1. Restart the execution worker to load corrected configuration/planning and safe
   diagnostics; restart API/evaluation workers if their changed code is loaded in
   old processes. Do not replay or rewrite historical failed runs automatically.
2. Expose caller-approved structured oracles and domain-safe test inputs through a
   narrow workflow; retain exact ownership and provenance checks.
3. After separate authorization for additional provider usage, repeat blinded
   planning experiments on fresh fixtures. Require reliable accepted plans,
   artifact-backed defects, benign controls, and useful repeatability before
   expanding infrastructure or marketing discovery claims.
4. Distinguish lifecycle completion from test success in summary status. Complete
   production identity/security operations before enterprise deployment.

Not verified: every application workflow, new ingestion/model extraction, real
external applications, production identity, broad security audit, all screen
readers, browser matrix, load/concurrency, and post-fix provider quality. Synthetic
HITL passing does not prove every external SSO/CAPTCHA implementation works.
No deployment, push, real target credentials, or additional paid infrastructure
was used. Local evidence artifacts are ignored workspace files, not committed
release artifacts.

## Changed files and local commands

This audit changed the shared `agent_configuration.py`, its execution service
`test_agent_configuration.py`, execution `workflow/test_case_planner.py` and
`test_feature_case_planner.py`, and execution `browser/assertions.py` and
`test_case_assertions.py`. The ignored `.local/ui_local_integration.py` gained
evaluated-verdict/receipt/accessibility assertions. The new ignored experiment
harness is `.local/product_audit_live.py`. This report and continuity/verification
records were updated. Other existing dirty files were preserved; they are not all
new changes from this audit.

Representative executed verification commands, from the repository root:

The final combined configuration/API/planner/evaluator regression run passed
**90 tests** with five dependency deprecation warnings. The separate URL assertion
run passed **12 tests**. These totals do not include browser baseline or E2E cases.

```powershell
.venv\Scripts\python.exe .local/ui_local_integration.py --protected-fixture
.venv\Scripts\python.exe .local/ui_hitl_integration.py --run
.venv\Scripts\python.exe -m pytest services/execution-orchestrator/tests/test_case_assertions.py -q
.venv\Scripts\python.exe services/execution-orchestrator/scripts/run_deep_fixture_benchmark.py --local-development --variant good --output-dir .local/product-audit-baseline-good
```

The baseline also ran `bad` and repeated both into fresh output directories.
Restricted child-process execution initially blocked Playwright; supported
execution escalation resolved that infrastructure issue. Do not classify those
setup failures as application assertion failures.

To load fixes, stop each old service with Ctrl+C and restart in separate terminals
using the existing `.env` (never paste it into logs):

```powershell
uv run --no-sync --env-file .env uvicorn markettwin_control_api.main:app --host 127.0.0.1 --port 8000
uv run --no-sync --env-file .env python -m markettwin_execution_orchestrator.worker
uv run --no-sync --env-file .env python -m markettwin_evaluation_worker.worker
```

Keep the frontend's configured API address consistent with the API port. These
commands use the workspace's configured infrastructure; no offsets need resetting.
Starting services does not authorize new paid model runs. No new database migration
was introduced by these audit fixes.

An independent reviewer challenged harness verdict coverage, the URL comparison,
and the interpretation of redacted live observations. The harness was strengthened,
the URL defect corrected, and unsupported false-positive claims excluded. Review
did not establish production readiness or close the explicitly listed gaps.
