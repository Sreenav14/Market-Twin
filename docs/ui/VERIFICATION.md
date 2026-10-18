# UI redesign verification

Updated: 2026-10-17

## MT-000050 Sup_14: live UI and HITL investigation — 2026-10-17

This is investigation evidence, not a claim that the newly identified presentation
issues have been corrected. Existing feature code and frozen MT50 records were
not modified. User requested research before further changes.

### What actually happened

Run `65d770e5-ae0e-4283-b516-5caa046726f8` (MT-000050) was created at
2026-10-18 01:08:44 UTC, started 01:08:49 and completed 01:09:37. It froze
`runtime_human_assistance=true`, no auth verification policy, and only the exact
`https://supermemory.ai` origin, subdomains false. The target is public.

- **Zero HumanActionRequest rows and zero HumanControlLease rows. No actual HITL
  handoff occurred.** Three browser contexts closed in agent mode, generation0.
- `human_auth_bootstrap_v1` ran 01:08:49–01:08:58, completed with no outcome,
  zero recorded steps/artifacts, and no human request. `authenticated_discovery`
  unconditionally creates the record titled **Human authentication prerequisite /
  Verify identity before protected discovery**, including for no-policy public
  runtime discovery. It binds the encounter handler, navigates, observes and exits
  normally when no challenge appears. The label implies authentication that never
  happened. Its completion is discovery completion, not human or role verification.
- The two real feature cases both only navigate to `/product/` then inspect
  assertions. Neither clicks Docs/Console or reaches a login destination.
  Overview:4 satisfied assertions. Navigation: Docs and Console visibility false,
  Agent visibility true. These are inferred expectations; no product findings were
  persisted. No permission should be expanded and no login fabricated to pass them.

### Actual Microsoft Edge interaction at localhost:5173

Opened the authorized existing workspace session; navigated MT50 Human Assistance,
Journeys, expanded Feature execution/Feature cases, selected the failed navigation
case and opened its recorded screenshot through View evidence. Did not start an
external run, submit credentials, or modify run permissions.

Observed:

1. Human Assistance says **Waiting for the test** / **This page updates as the run
   progresses**, despite the terminal completed status and no request history.
2. Journeys displays the bootstrap as **Journey10000**, **Deterministic browser
   executor**, completed/outcome not recorded. The flow counts **3 cases** while
   feature coverage lists **2 planned**. It puts discovery after the two cases
   because it follows ordinal10000, misrepresenting chronological execution.
3. Saved screenshot at assertion step1892 visibly contains Docs and Console, each
   with an external-link arrow. Frozen role locators require exact accessible names
   `Docs` / `Console`. Thus the failed observations are not proof that the visible
   links are absent. An accessible-name mismatch (possibly arrow suffix) is a
   hypothesis; the exact saved DOM/ARIA naming was not retained in the inspected
   artifacts, so do not claim that precise cause proven or silently rewrite the
   frozen expectations. No external application replay was performed.

### Current viewer architecture and limits

Real challenge -> durable request/run awaiting_human -> Human Assistance -> owner/
admin claims exclusive lease -> signed API-to-worker grant + one-use viewer ticket
-> Connect to protected browser -> same-origin WebSocket proxy -> worker-owned
Playwright page. `ControllerBrowserOwner.frame` uses CDP Page.captureScreenshot;
gateway waits0.5s between frames (roughly2fps before capture/transport cost), sends
volatile JPEG bytes to the React canvas, and forwards sequenced mouse/key/text
input to that same page. Done fences/revokes the generation, verifies continuation
and signals the worker. PostgreSQL/Kafka do not carry viewer input or credentials.

This is an interactive page viewer during a human lease, not an always-on agent
execution monitor or an OS/browser-chrome remote desktop. Completed contexts cannot
be reopened from screenshots. A different-origin console still needs a newly
approved scope; human login cannot authorize it.

Code-review gaps: pending cards lack a human-readable requesting journey/step and
safe destination context; claim and connect are separate steps; viewer reports
Connected on WebSocket open before ticket authorization or a first image; no
first-frame readiness timeout; terminal empty-state text is misleading. Existing
run-level awaiting-human banner is present, but it cannot appear when there is no
durable request. Local configured ports5173/8000/8020 were listening; frontend and
API health returned200. Secret presence was checked as booleans only. Running
process environment equality and a canonical live claim were not established.

### Focused checks and correction order

`pytest` browser owner + viewer gateway + auth bootstrap: **20 passed** (includes
real Chromium/TLS WebSocket same-context login, fencing, reconnect and expiry).
HumanBrowserViewer/HumanActionPage Vitest: **10 passed** using
`--maxWorkers=1 --pool=threads`; first default fork run executed no tests because
workers timed out starting. Component mocks do not prove the canonical live UI
handoff. No new full UI-to-worker login run was performed in this investigation.

Fix narrowly in this order:

1. Represent runtime public discovery as discovery, excluded from feature-case
   counts and ordered before planning; do not imply a human verified identity.
   Preserve explicit-policy semantics and historical frozen run data.
2. Make terminal/no-request Human Assistance say no human assistance was requested;
   distinguish no request, pending request, unavailable owner and closed browser.
3. Add requesting case/journey/step/reason and approved destination context to the
   handoff panel; connect after explicit Take control and show authenticating /
   waiting for frame / ready / failed states, retaining strict authorization,
   reconnect, Done and Skip behavior. Do not expose raw CDP or embed an external
   application iframe as an authentication workaround.
4. Reproduce exact-name versus rendered-link mismatch on a synthetic fixture and
   improve pre-freeze locator grounding/diagnostics; unsupported or misgrounded
   assertions must not masquerade as product defects. Never mutate MT50 expectations.
5. Execute a fresh local public -> protected synthetic run through the actual
   canonical frontend, verify visible live frame and input, Done, independent Skip,
   reconnect and final report. Explicitly separate that evidence from external SSO.

Primary references reviewed: [Playwright CDPSession](https://playwright.dev/docs/api/class-cdpsession),
[Chrome DevTools Page protocol](https://chromedevtools.github.io/devtools-protocol/tot/Page/),
[Playwright authentication](https://playwright.dev/docs/auth),
[OWASP WebSocket security](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html).
Existing page transport is sufficient for the requested takeover; findings do not
justify replacing the architecture or introducing another infrastructure service.

## Runtime-only HITL — 2026-10-17

### Implemented behavior

New Test has no authentication-marker, account or role setup. The API freezes
runtime assistance on new runs; existing frozen requests retain their semantics.
Persona, discovery and Feature Cases bind encounter-driven assistance before
navigation. Actual password, MFA, CAPTCHA and bounded login/SSO challenge signals
can pause execution. A public marketing Login link/newsletter form alone cannot.
Human control remains restricted to authorized origins and exclusive generation
leases. Done resumes only after revocation and a safe continuation check. Without
an approved identity policy, the UI says human assistance completed, not role
verified. Runtime session reuse is in memory, bound to run/target/origin, with no
upgrade into a verified-role grant. Failed/skipped/cancelled handoffs revoke
provisional snapshots. Raw browser traces are disabled for runtime-enabled contexts.

Skip is a separate authorized API transition, not cancellation. It works pending
or leased, abandons the checkpoint, fences/releases viewer control, records not
tested and continues independent work. Duplicate Skip uses the original stored
terminal generation. Reports exclude skipped work from executed/pass/fail counts
and do not create product findings for it. A later independent login challenge
can request assistance again; Skip does not suppress an entire origin.

Key files: NewRunPage/HumanActionPage/api and skipped journey/case presentation;
control API test_run/human_actions and HumanActionRepository; execution controller,
auth_session_broker, mcp_tools, case_execution/journey_executor/auth_bootstrap,
run_request/run_executor/multi_persona_executor/deep_run; shared result contracts,
evaluation workers and result repositories. Migration
`database/migrations/versions/6b0e2ac784d1_add_skipped_human_assistance.py` follows
`31d4ef097a2b` and adds skipped states plus the terminal-generation fence.

### Actual pipeline evidence

These runs used real local React, API, migrated disposable PostgreSQL, outbox,
Kafka, execution worker, Chromium, evaluation worker, persisted reports and rendered
report UI. Persona used a scripted local ADK driver; Feature Cases used frozen
fixture plans. Provider keys were removed. These are integration tests, not AI
planning-quality experiments or external-application certification.

| Scenario | Run / evidence under `.local/` | Observed outcome |
| --- | --- | --- |
| No-policy Feature Cases login/MFA, reconnect, Done, session reuse and sensitive approvals | `bc3cd50e-bded-46eb-80e0-293a2b97d158`; `ui-integration-result-1685de8580b9462db0f32170c94796a7.json` | Completed report; 3 passed, 3 rejected/blocked, 2 budget-skipped; one consumed approval, three rejected, duplicate decisions409 |
| Feature Cases Skip, next independent case requests its own login, then resume | `5e5d5328-db6a-4b86-a971-a917d4731c55`; `ui-integration-result-ba53e998429047c6b6a45baafb0d7fbf.json` | Completed report; 2 passed, 3 blocked, 1 human-skipped, 2 budget-skipped; executed5/not_run3; zero findings |
| Persona public-first, late runtime login, same-context completion and isolated reuse | `07bb9ff2-aac5-455c-8a80-9afcb5a66bc0`; `ui-integration-result-6c972aa7fcbe47e18484b146e9b19a21.json` | 3 passed, completed persisted/rendered report; no upfront human request |
| Persona seeded-bad heading | `70988a3f-eefd-4a20-b9ee-2c29c3ee2315`; same artifact | 3 failed as expected, completed persisted/rendered report |
| Persona Skip from pending, then two independent public journeys | `ec311b6b-cfc2-4b3c-bd7d-41f98f876758`; `ui-integration-result-f4f593d9c4f0460e81d8535a8c19adee.json` | PASS after fix: one skipped/null outcome, two passed; run and report completed; all three contexts closed |

The persona good/bad artifact also contains an earlier failed Skip attempt; it is
not an all-green matrix artifact. The final artifact is a Skip-only rerun despite
the harness's generic matrix success message. No secret entry/live viewer frames
were saved. Unique test consumer groups drained old local commands against isolated
databases; no shared offsets/messages were reset/deleted. Owned disposable databases,
browser artifacts and labelled MinIO containers were removed.

### Proven defect and correction

Skip rolled back the shared AsyncSession. A subsequent synchronized bulk state
update left its cached TestRun expired; `RunStateRepository.mark_completed` read
`run.status` at line67 and raised `MissingGreenlet` after all journeys finished.
This was an application bug, independent of Kafka. `_get_run` now explicitly uses
`populate_existing=True`, preserving state-transition validation. Worker completion
logging uses the immutable accepted run ID. Real PostgreSQL regression
`test_run_state_after_handoff.py` fails with the old get method and passes with the
fix. The complete Skip UI-to-report rerun above then passed.

One diagnostic retry stopped before run creation because a local Kafka CLI command
timed out; broker read-only health checks succeeded and the retry proceeded.
Another diagnostic used incorrectly encoded test selectors; corrected the ignored
harness's UTF-8 selectors before the final rerun. Neither is counted as a passing
application check. The expected typed Skip exception can appear in ADK tool stack
logs; the final persisted run/report states, not a simplistic log grep, determine
the test outcome.

### Checks executed

- Focused runtime challenge, real MCP Skip, snapshot revocation/isolation,
  auth bootstrap, durable lifecycle, API Skip and deterministic/deep evaluator
  batch: **52 passed**.
- Worker finalization/logging and deep-run coverage batch: **24 passed**.
- Real migrated PostgreSQL handoff rollback/finalization regression: **1 passed**;
  old-method baseline: **1 failed as expected** at the exact MissingGreenlet site.
- Earlier focused API batch: **33 passed**; real PostgreSQL/Chromium Skip/lease
  regression: **1 passed**, including pending/leased, unauthorized, expired410,
  duplicate generation, released lease and abandoned suspension checks.
- Focused changed production Ruff and Pyright: **pass / 0 errors**. Full-project
  Pyright: **1209 errors**, including existing unrelated source/test typing issues;
  repository-wide type checking is not clean and is not represented as passing.
- Frontend `typecheck` and production `build`: **pass**; existing >500kB chunk
  warning remains. Focused runtime form/viewer/result Vitest: **22 passed across
  5 files** (`NewRunPage`, `HumanActionPage`, `api.preview`, `journeyPresentation`,
  `FeatureCases`). Final regression-file Ruff and `git diff --check` also pass.

Reproduction commands (repo root; installed dependencies and local services needed):

```powershell
uv run --no-sync pytest -q services/execution-orchestrator/tests/test_runtime_human_assistance.py services/execution-orchestrator/tests/test_auth_session_broker.py services/execution-orchestrator/tests/test_auth_bootstrap.py services/execution-orchestrator/tests/test_human_action_lifecycle_repository.py services/evaluation-worker/tests/test_deep_evaluator.py services/evaluation-worker/tests/test_deterministic_evaluator.py services/control-api/tests/test_human_action_skip.py
uv run --no-sync pytest -q services/execution-orchestrator/tests/test_worker.py services/execution-orchestrator/tests/test_deep_run.py
uv run --no-sync --env-file .env python .local/verify_handoff_expiration.py
$env:MARKETTWIN_TEST_PERSONA_VARIANTS = 'skip'
uv run --no-sync --env-file .env python -u .local/persona_auth_matrix.py
Remove-Item Env:MARKETTWIN_TEST_PERSONA_VARIANTS
npm --workspace @markettwin/web run typecheck
npm --workspace @markettwin/web run build
```

The `.local` drivers are existing ignored local verification tooling, not a
production service or a committed portable test runner.

### Start manual testing / remaining verification

Canonical loopback PostgreSQL was upgraded from `31d4ef097a2b` to `6b0e2ac784d1`
after a read-only query confirmed zero planning/queued/running/awaiting-human runs.
`alembic current` confirms head. Stop the old API/execution/evaluation processes
and restart each once using the [HITL operations commands](../hitl/README.md).
For another checkout/database, apply the additive migration first:

```powershell
uv run --no-sync --env-file .env alembic -c database/alembic.ini upgrade head
uv run --no-sync --env-file .env alembic -c database/alembic.ini current
```

Expected head: `6b0e2ac784d1`. Use the existing loopback infrastructure/settings;
explicitly choose local Kafka before starting workers if `.env` points remotely.
Do not run duplicate consumers. A pending human request still occupies the single
execution consumer; the API/viewer remain responsive and later runs can queue.

1. Create a new authorized test without login fields; Start on a public page.
   Confirm execution begins without an unconditional human request.
2. Follow a protected route. Confirm the actual challenge pauses the requesting
   case/journey and opens Human assistance with the correct run context.
3. Take control/connect; complete login/MFA in the live viewer within approved
   origins. Done should resume the same context only after the challenge is gone.
   Leaving the login challenge present must not produce a successful continuation.
4. On a separate run, Skip pending assistance; confirm not tested and independent
   work continues into a completed report. Repeat Skip while controlling, disconnect
   and reconnect, timeout/expire, cancel and interrupt a worker.
5. Verify unauthorized viewer/scope actions remain denied and rejected/duplicate
   sensitive actions never execute. Review persisted report classifications.

Pending comprehensive manual coverage: external IdPs/popups/CAPTCHA widgets and
unseen challenge layouts; no-policy cancellation/expiry/worker-loss through the
entire UI-to-report chain; exhaustive human navigation/side-effect replay cases;
adversarial secret canaries; live-provider planning quality and production release
verification. A generic difficult assertion is not automatically proof of login.
No arbitrary complexity detector or universal website-support claim is made.

## MT-000048/49 corrections — 2026-10-17

### Additional rendered-browser review

Real Chromium review artifact:
`.local/ui-integration-result-5e9f8ec536144816a9f980f0375ff87a.json`;
18 screenshots in the same-named directory without `.json`. Six states at
1440/768/390: scope request, required-auth New Test, optional-auth New Test,
awaiting-human (before connecting the viewer), good report and seeded-bad report.
All18 axe WCAG2A/AA/2.1AA samples reported0 violations and no horizontal overflow.
Screenshots were inspected across desktop/tablet/mobile; protected viewer frames
and secret entry were never saved. Interactive CUA had no available browser;
verification used real local Chromium via Playwright, not mocked DOM rendering.

Visual inspection found and fixed two issues in `NewRunPage.tsx`: the depth label
preceded the wrong selector, and the authentication checkbox used a row style that
separated its caption from its control. Added actual DOM-order and checkbox-caption
geometry assertions at all three widths; corrected screenshots and full workflow
rerun passed. Frontend TypeScript and production build passed again (existing
large-chunk warning remains).

New required-good run `e7e7c045-63e3-4c5f-9420-dd624e7d1d65`:3 passed;
optional-bad `6696ec88-2ab7-4e7b-82a2-e0c3dc7c2d35`:3 failed as expected.
Both completed UI login/MFA, verified Release, isolated auth reuse, evaluation and
rendered reports. Persona observations remain explicitly unverified product issues.
Provider credentials were removed: the generative overall assessment shows its
honest unavailable fallback; deterministic report persistence/rendering is what
this run verifies. Disposable resource cleanup passed.

### Implemented

1. Exact additional-origin review creates an immutable, separately authorized target
   revision. Owner/admin request and approval; pending revisions cannot execute.
   The rendered UI workflow passed, and a real migrated PostgreSQL regression proves
   original target and persisted frozen run snapshots remain unchanged, member403,
   outsider404, duplicate approval409, and explicit revocation.
2. Shared configured required/optional authentication in persona and Feature Cases.
   Same-context secure handoff; exact identity verification; bounded waiting; isolated
   authenticated session reuse. Independent review's concurrency gap was fixed and
   reproduced by a real Chromium concurrent-click test. Existing unconfigured IdP
   navigation error contract retained; no autonomous IdP access is permitted.
3. Unique semantic planning guidance, rendered DOM whitespace normalization, explicit
   privacy-safe `url_path_v1`, typed unsupported reads, exact frozen-oracle/provenance
   evaluation. URL mismatch canaries prove private unexpected paths are not persisted.
4. Real DOM documentation-link context distinguishes benign navigation from restricted
   effects. Forms, disguised buttons, unknown origins, restricted action paths, query
   actions and encoded traversal remain blocked. Filter reset requires approval.
5. Typed historical policy diagnostics explain the blocked exact origin and link to
   scope review; they do not treat login as destination authorization.

### Real integrated outcomes

All infrastructure was disposable and loopback: real React, cookie-authenticated
FastAPI, migrated PostgreSQL/outbox, Kafka, execution worker, Chromium viewer/tools,
evaluation worker, persisted reports and rendered report UI. Unique execution groups
drained retained missing-run commands without changing shared offsets. No provider
calls, external target tests or real test-account credentials were used.

| Scenario | Exact outcome | Evidence under `.local/` |
| --- | --- | --- |
| Feature Cases, protected good | Run `d660c216-a477-48af-9588-8861f67207bf`: completed; 3 satisfied, 3 rejected/blocked, 2 case-budget skips; 0 findings. Login/MFA, disconnect/reconnect, verified Release, reuse, one approved effect/receipt, 3 rejected actions, four duplicate decisions409. | `ui-integration-result-d5cb2f33a4a84e17977b383360f5dbef.json` |
| Feature Cases, protected seeded bug | Run `9dedb52d-a6df-4c63-b35c-ec7443834d11`: completed; 1 satisfied, 2 failed assertions, 3 rejected/blocked, 2 case-budget skips; 2 persisted findings. Async result and dependent-role defects both detected with artifacts. | `ui-integration-result-c9750a362fc44a6596962ab34930377f.json` |
| Persona required-auth good | Run `255b2793-e97d-4b75-aa9e-dcfaf6999e78`: 3 passed; one completed login request/released lease/consumed suspension; identity-verified reuse across 3 isolated persona contexts; report rendered. | `ui-integration-result-f4c0eb7d7f8c43cca9615956b8753d49.json` |
| Persona optional-auth seeded bug | Run `e946d1ed-660e-4b24-89e6-7f564a2d5cbd`: 3 failed on wrong fixture heading; one verified login/reuse; persisted evaluation/report rendered. | Same persona matrix artifact |
| Cancellation, request/lease expiry | Separate real UI/API/DB/viewer harness passed cancellation/no reuse, natural3s timeout, 5s lease expiry/stale-input fencing/reclaim, reconnect and Release without reconnect; generic recovery verifier failure dispatched nothing. | `.local/ui_hitl_integration.py --run` console outcome |

Both deep reports returned409 with the exact expected evaluation-pending sentence
before evaluation, then200 after persisted evaluation. Reports rendered; axe found0
violations on these report pages; no horizontal overflow at1440/768/390. This is
not an application-wide accessibility certification.

Persona uses a **scripted local ADK model** driving production browser tools and
evidence validation; deep uses the existing explicit engineering fixture plan.
These tests prove integration and controlled detection, not live model planning
quality or universal defect discovery. No frozen historical MT48/49 expectations
or permissions were rewritten, and no Supermemory run was replayed.

### Focused checks and defects found during verification

- Initial focused API/classifier/assertion/auth/evaluator batch:118 passed.
- Planner/bootstrap/lifecycle/handoff batch after shared deadline helper correction:
  53 passed. Final API/scope/diagnostic/DOM-policy/concurrent-auth batch:52 passed.
  Counts overlap; do not add them as a unique-test total.
- Real fresh PostgreSQL migration+scope/frozen-run regression:1 passed.
- Protected fixture good/bad and session reuse:3 passed; DOM policy context:5 passed.
- Frontend typecheck and production build passed; scope/diagnostic Vitest:6 passed.
  Build retains the existing large-chunk warning. Focused source Pyright:0 errors;
  Ruff passed the final root-owned focused files. No lint rules disabled.
- Harness corrected stale authorization wording and explicit execution-mode selection.
  Persona cleanup now checks zero approvals/receipts plus exactly one completed login,
  rather than incorrectly applying registration-approval requirements.
- Seeded-bug fixture initially dropped `variant=bad` through login, masking the first
  async defect. Fixed the bounded fixture redirect, added good/bad ground-truth
  checks, reran and detected both defects. One DOM test fixture lacked an HTML MIME
  type; corrected transport rather than relaxing its security expectation.
- Browser control/scoped suite initially had35 passing and1 failure: new unconfigured
  IdP navigation raised a different exception class. Restored its existing fail-closed
  error contract; affected scoped-browser/shared-authentication retest:15 passed.

### Start manual testing

Migration `31d4ef097a2b` is applied to the canonical local database (no active runs
at migration time). Existing canonical services were not restarted or reconfigured;
stop their old instances before starting one of each with updated code:

```powershell
uv run --no-sync --env-file .env python -m alembic -c database/alembic.ini upgrade head
uv run --no-sync --env-file .env uvicorn markettwin_control_api.main:app --host 127.0.0.1 --port 8000
uv run --no-sync --env-file .env python -m markettwin_execution_orchestrator.worker
uv run --no-sync --env-file .env python -m markettwin_evaluation_worker.worker
npm run dev --workspace apps/web
```

Run the services in separate terminals. Keep existing configured database, Kafka,
object storage and internal viewer settings; do not reset offsets or create duplicate
workers. For local synthetic retests in this workspace (harnesses are ignored local
utilities), use `.local/ui_local_integration.py --protected-fixture`,
`.local/persona_auth_matrix.py`, `.local/ui_hitl_integration.py --run`; prefix each
with `uv run --no-sync --env-file .env python`. Set process-local
`MARKETTWIN_TEST_SEEDED_BUG=1` only for the bad deep fixture, then remove it.

Manual sequence: open target Network policy → request complete exact origins →
review pending revision → explicitly authorize → create a NEW run selecting that
revision → configure required/optional verified identity → Start → Human Assistance
→ Take browser control → Connect → synthetic login/MFA → Release → check verified
resume → inspect ordered journeys, evidence and report. Repeat in both modes.
Reject a sensitive action and confirm no effect; approve another once; disconnect
and Release; cancel/expire another handoff. Never broaden old run permissions.

### Limits

External SSO providers, live CAPTCHA services, real provider-generated plans, hosted
TLS/proxy deployment, canonical cloud Kafka stability and full H12/adversarial release
verification remain unverified. Challenge detection is bounded, not arbitrary visual
reasoning. Roles require explicit markers, not inferred successful login. The single
execution consumer remains occupied during human waiting; worker loss cannot restore
a live browser. Do not interpret synthetic results as universal product readiness.

---

Final readiness rerun: protected persisted E2E artifact
`.local/ui-integration-result-456f1f5453c44a7e936ce3ce12853e18.json` passed with
3passed/3blocked/2budgetskip, results409->200, report rendered, axe0 and no overflow
at1440/768/390. Generic recovery UI/API/DB/viewer separately passed exact-target
verification and one dispatch after Release, no dispatch on failed verification,
no generic auth snapshot. Journey pages now select recorded failures and show
executor/typed expected-observed values; API allowlists historical diagnostics.
Recovery instructions are visible and generic completion does not claim login.
Six focused frontend tests, typecheck and production build passed. Historical
user journey visual review was blocked by browser sign-in; not a release audit.

Latest integrated audit: [Product audit](../PRODUCT_AUDIT_2026-10-16.md).
Protected synthetic persisted E2E passed (three passed, three blocked, two skipped),
including rendered report, zero report axe violations and no horizontal overflow
at 1440/768/390 widths. Separate real HITL integration passed cancellation,
disconnect-before-release, request expiry and lease expiry/reclaim. These results
do not establish model-generated plan quality: the twelve-call comparison accepted
only two weak navigation cases and evidenced no seeded bugs. See report for exact
artifacts, checks, corrections, privacy limits and unverified production workflows.

This record separates mocked browser coverage from local service integration.
Visual Playwright fixtures use synthetic users, workspaces, runs, approvals, and
artifacts. They do not visit external applications or invoke model/provider
planning. HITL credential-bearing browser phases remain excluded from screenshot
and trace capture.

## Quick synthetic E2E and harness correction (2026-10-16)

Command: `.venv\Scripts\python.exe .local\ui_local_integration.py --execute-fixture`
with local subprocess/Docker permissions. Real React, API, freshly migrated
disposable PostgreSQL, outbox, loopback Kafka, execution worker, Playwright,
evaluation worker, persisted reports and results endpoints were exercised.
The explicit local fixture plan replaces model planning; no provider was invoked.

The strengthened harness found a real report defect: the approved fixture Save
records `registration_submit`, but evaluator evidence matching expected `click`.
The action completed with assertions, yet its evaluated verdict became unverified.
The evaluator now requires the exact identity frozen in each step (`action_id` or
`action`). Three new regressions reject incorrect identities; all 12 evaluator
tests passed, as did source Ruff and Pyright. One subsequent harness assertion
incorrectly counted evidence buttons as case buttons; restricting it to the named
case list corrected the harness without changing expected case counts.

The harness now checks case verdicts/evidence, selectable depth and submitted
Medium, the actual selected/skipped budget, rendered case rows, and receipt counts
for approved and rejected runs. Evidence validation errors propagate after owned
resource cleanup; an invocation without workers fails fast.

| Final check | Actual outcome |
| --- | --- |
| Approved run `cc1874cb-6d01-4a49-bdfa-9372637daaf3` | 6 executed, 6 passed, 0 failed assertions, 0 blocked/inconclusive; 2 case-budget skips |
| Approval execution | 5 consumed approvals; 5 completed receipts; duplicate decisions HTTP 409 |
| Rejected run `57f31eab-142b-407e-ad31-11d9d67a0b27` | 4 blocked, 2 passed, 2 budget-skipped; 4 rejections; zero receipts |
| Evaluation readiness | Exact expected HTTP 409 before evaluator startup; HTTP 200 after evaluation for both runs |
| React integration | Cookie login, application/target authorization, draft/start, report and all 8 case rows rendered |
| Depth control | Low/High/Medium selectable with matching help; Medium submitted and enforced as 6 selected cases |
| Production build | Passed, 584.52 kB JS / 89.96 kB CSS; existing chunk-size warning |
| Focused UI tests | 4 passed with `--pool=threads --maxWorkers=1`; default forks worker timed out before tests |
| Cleanup | Owned database, MinIO container, subprocesses and browser artifacts removed; shared consumer offsets untouched |

Safe final record:
`.local/ui-integration-result-2d41da33ee0b4c91899a18ce6911ed14.json`.
Earlier lifecycle-only pass did not prove case verdicts; the failed strengthened
record `.local/ui-integration-result-ebc4a87afbbb4f95b93b184da92c3117.json`
documents the false unverified case before the evaluator correction.
Previous EPERM/native-module build failures are superseded by the successful
permitted local build. Live model-generated plans, protected login/MFA/viewer
scenarios, and the exact historical `c6cb14af` exception remain outside this quick
smoke's verification. Restart canonical API and both workers to load source fixes.

## Feature planner ADK boundary verification (2026-10-16)

68 focused backend tests passed: feature planner, worker failure handling, shared
safe diagnostics, and feature API. Five scenarios run the actual ADK Runner and
production feature planner pipeline with synthetic model responses and stubbed
database I/O: mixed valid/malformed candidates, all malformed candidates, valid
JSON with a thought part, thought-only output, and invalid JSON. The mixed output
reaches our parser with `output_schema` retained; it saves seven valid cases.
Thought parts previously broke final JSON parsing and are now excluded. Invalid
JSON and missing answers produce fixed reviewed reasons; canary response content
does not appear in logs, persisted plans, or public failure payloads.

These checks do not prove live model output, browser case execution, or frontend
integration. The historical `c6cb14af` exception's exact cause remains unknown.
Restart execution worker and Control API before a fresh run. Frontend build/Vitest
were not rerun; their previous Windows spawn/native-module blockers remain open.

## Authorized feature-planner reproduction: HTTP401 (2026-10-15)

User explicitly approved one model-backed reproduction using saved page evidence.
Ran actual ADK feature planner with frozen Sup_2 scope/budget and saved public
ARIA observation (reconstructed ancillary page metadata, not a byte-identical
original tool response). No browser was started; production target not contacted;
DB read-only; runtime/plan persistence replaced with in-memory validation sinks.
Retries disabled and one model-call limit,100s outer bound; telemetry disabled.

Reproduction FAILED with LiteLLM AuthenticationError, providerHTTP401 for configured
openai/gpt-6-luna. Safe evidence .local/feature-planner-reproduction.json retains
only exception class/status and stack locations, no key/prompt/provider body.
Effective credential is MODEL_API_KEY, present and matching root.env;
OPENAI_API_KEY absent. No key value printed, replaced, or tested again.
This proves current planner authentication failure; original33/34 exceptions
were not saved so historical identity of cause remains an inference. No plan
was generated and no target defect established. Model availability/output/case
execution remain unverified until provider authentication succeeds.

Genuine blocker: user must configure a valid authorized model-provider key
privately in MODEL_API_KEY (never send it in chat) and restart execution worker
(and evaluation worker if sharing config). Keep API/worker loopback Kafka
settings aligned. Use a new run; previous failed runs were not rewritten.
Do not make another paid/provider call under the single-reproduction approval.
Earlier diagnostic correction tests24backend/4UI/typecheck/build remain passing;
no new application code change was needed for this credential rejection.

## Feature planning failure reporting correction (2026-10-15)

Sup_3/MT-000034 (78537702-b077-406d-8645-eea72f668402) also failed before
persisting any journey or event. User has no worker logs. Underlying historical
planner exception is not recoverable from these DB rows. Initial Sup_2 discovery
artifact records targetHTTP200. Deterministic case execution still needs model-
generated planning for nonfixture runs; earlier local fixture passes did not
exercise provider-generated candidate output.

Implemented only the proven diagnostic defect: worker now commits safe run.failed
category plus exception class after rollback and on interrupted delivery. Raw
exception messages/provider responses/validation inputs are never persisted.
Shared reviewed messages classify common model authentication/permission/model-
not-found/rate/connection/request, validation, timeout, browser and interruption
failures. API returns only allowlisted diagnostic text. FeatureCases displays a
terminal planning error instead of waiting forever for an unsaved plan and stops
polling that failed result. Historical failures truthfully say error not retained.
No migration or failed-run rewrite. API and execution worker need restart to load
new code. Real readonly case_view checks for33/34 returned the expected safe
historical fallback. No production rerun or provider/model call performed.

Checks: focused worker/API/shared24passed (4existing ADK warnings); frontend
FeatureCases4passed; TypeScript/build passed (584.48kBJS/89.96kBCSS); scoped
Pyright0, Ruff passed ignoring baselineE501. Final worker/shared14passed after
adding durable exception type (overlaps24). Underlying real planner functionality
is NOT declared fixed. Captured reproduction needs user approval if it invokes
the configured paid model; no real credential/provider use authorized here.

## Dark theme implemented (2026-10-15)

User requested dark mode after the redesign. Default theme now uses dark
charcoal canvas/surfaces, mint primary/focus colors, readable neutral text and
dark semantic status backgrounds. Public pages now use shared semantic tokens
instead of hardcoded light surfaces, including demo, skip link and logo/button
foregrounds. Existing fonts/layout/behavior retained. Source changes are only
apps/web/src/styles/tokens.css and apps/web/src/styles/public.css.
Production build passed (JS584.33kB, CSS89.96kB; existing bundle-size advisory).
Fresh anonymous browser renders reviewed: home1440px, login1440px and390px;
actual computed color-scheme dark. Eight palette text/background ratios ranged
5.25:1-16.14:1 (status pairs7.59:1 or greater). Screenshots under ignored
.local/dark-mode contain anonymous pages only. No test suite rerun or real login.
Authenticated report/viewer/portal screenshots and full dark accessibility
acceptance remain unverified. Prior statements that dark mode was deferred are
historical and superseded by this requested implementation.

## End-to-end integration correction (2026-10-15)

The UI implementation is preserved. This follow-up changes only integration
behavior, regression checks and synthetic fixtures; it does not redesign the UI.

### Real public-fixture pipeline

The real React -> Control API -> PostgreSQL/outbox -> local Kafka -> execution
worker -> evaluation worker -> persisted report -> results API -> React path
passed using generated disposable databases, synthetic users and an isolated
UUID Kafka consumer group. No API responses or executor/evaluator were mocked.
The evaluator was deliberately stopped until execution completed to establish
the readiness contract without a timing race.

- Approved run: `23dfdfe4-85d5-46ab-ba16-e8761032c84a`, lifecycle `completed`.
  Six approvals were consumed and six receipts persisted as `completed`.
  Every duplicate decision returned HTTP 409. Decisions in this run used
  authenticated browser API calls; they do not prove the React approval buttons.
- Before evaluation, `/api/v1/test-runs/{id}/results` returned **HTTP 409**, detail
  **"Test run execution completed, but evaluation results are not available yet."**
  This is expected pending behavior, not a failed execution or missing API route.
- After starting the evaluator, results returned **HTTP 200**, persisted report
  `c4ee2703-21bd-4cf3-858b-7462daab9fe9` had status `completed`, and the actual
  redesigned report page rendered "What this test found" and "Executive summary".
- Rejected run: `c3fd65e6-df3e-4d0b-8a83-98c23a328e85`, lifecycle `completed`.
  Five requests were rejected, duplicate decisions returned 409, and **no
  approval receipt** existed. Its results returned 200 and its report completed.
- Safe metadata is retained in
  `.local/ui-integration-result-02e34672c6cb4c0fa8d685bd73e07b9b.json`.
  The test database, owned services/logs and exact UUID-owned temporary MinIO
  container were removed. The existing MinIO service/unknown password was not
  used; the cached image ran on loopback with generated synthetic credentials.

An earlier run (`e6f985c7-9cb0-4e29-a2bf-e678510a9012`) completed execution and
six approvals, but remained at results 409 with no report for 60 seconds. Its
function-level stack reached observability initialization; no exact source line,
exception, or initialized setting was retained. Explicitly disabling MarketTwin
observability in the isolated retry allowed evaluation to complete. Source
review and focused tests found no proven evaluator/observability code defect.
This is a test-configuration/isolation finding; no fallback hides evaluator
failures and the historical unspecified non-2xx cannot be retroactively identified.

### Kafka correction and focused checks

`accept_run_requested` previously raised a generic ValueError for a deleted run,
causing ordinary worker startup to retry that message forever. It now raises a
specific `MissingRunRequestError` only after a successful database lookup returns
no row. `process_command` logs safe event/run IDs and returns so the normal
consumer acknowledges that one delivery without executing it. Database/transport
exceptions and workspace mismatches are not classified as missing runs.

The new UUID test group read from earliest and drained retained disposable
commands from offset 0 to 4 before new runs, then executed current requests.
**No shared consumer offset was reset and no Kafka message/topic was deleted.**
This assumes API/outbox and the ordinary execution worker use the same canonical
database. Never join the shared group with a disposable database. The unsafe
ignored `--worker-startup-check` mode now exits before launching a consumer.

| Follow-up check | Actual result / scope |
| --- | --- |
| New stale-run regressions + existing worker tests | 10 passed; missing acknowledged/next valid executes, DB failure retries, workspace mismatch uncommitted |
| Results-readiness + finding response tests | 10 passed; exact pending/ownership/ready contract |
| Desktop/mobile pending/ready/permission UI and accessibility checks | 8 passed; includes automatic 409 -> ready without a manual refresh |
| PostgreSQL approval/repository lifecycle test | Final rerun: 1 passed, 35.39s; rejected action has no receipt/dispatch callback, concurrent exact consumers allow one callback; reclaimed request appears once with its active lease |
| Composed protected registration fixture browser tests | 2 passed; capture/restore into a fresh real controller context and synthetic login, expired OTP, valid MFA, exact identity, actual effect count, identity on guide navigation |
| Shared/evaluator observability focused checks | 5 shared + 2 evaluator passed, 1 evaluator case deselected; no exporter/provider calls |
| Scoped worker production typing / lint | Pyright 0 errors/warnings; scoped Ruff passed |

The final combined focused backend regression command passed **85 tests**, with
four existing ADK deprecation warnings, in 109.31s. This includes browser owner,
gateway, owner service, auth bootstrap/broker, action policy, worker/stale command,
reaper/client, claim serialization, results readiness and protected fixture tests.
Frontend typecheck and production build passed again (584.33 kB JS, 89.67 kB CSS).
These results overlap the focused rows above; do not sum them as distinct tests.

### Real protected viewer boundary

The live test exposed a second actual integration defect: `ClaimResponse` returned
valid ticket/URL data but omitted `viewer_available`, which React checks before
rendering Connect. The successful claim now includes `viewer_available: true`
after the existing worker-grant and viewer-URL validation. Failure paths still
reject the claim; lease/token/generation checks were not relaxed. A serialization
regression also checks that the lease token and ticket remain absent from repr.

`.local/ui_hitl_integration.py --run` now passes the real authenticated React
login/cookie `/me`, PostgreSQL request/claim, signed API-to-owner lease, restricted
WebSocket, synthetic login/MFA, unexpected socket disconnect, fresh-ticket
reconnect, dashboard, React Release and `authenticated_discovery` completion.
Database checks assert request `completed`, suspension `consumed`, lease released
and browser session closed. A broker snapshot installed into a fresh isolated
context reverified role `user`; a second take for the same case was rejected.
No screenshots, traces, videos or browser evidence files were produced.

This boundary invokes the real auth-bootstrap orchestration directly with an
explicit local-development request, not Kafka or model planning. Its expanded
real local run also passed:

- Pending cancellation through React/API blocks resume, persists `cancelled`,
  closes the browser session and creates no reusable snapshot.
- After successful MFA, disconnecting the viewer and clicking Release **without
  reconnecting** still completes verification and consumes the suspension.
- A natural short request deadline (3 seconds in the test, no DB clock edits)
  blocks resume, persists `expired`, closes the session and creates no snapshot.
- A real API lease with its supported 5-second duration accepts initial viewer
  input, rejects stale input after expiry, returns the request to pending through
  the reaper, and allows a fresh claim/ticket to accept input. Cancelling that
  renewed handoff also fails closed.

Those live cases exposed two more surgical defects, now corrected:

1. `close_session` attempted event-log persistence after a pending cancellation
   changed control to verifying; the privacy sink correctly rejected it and
   interrupted durable cleanup. Shutdown now writes event logs only under agent
   control. It does not enable capture during a handoff.
2. `abandon` classified natural timeout as cancellation if the worker beat the
   periodic reaper. It now persists `expired` for an elapsed deadline, retaining
   cancellation for future or absent deadlines and preserving terminal states.

Four focused regressions passed (safe close plus past/future/absent deadline),
and strict typing on both changed source modules passed. These checks also pass
in the expanded 85-test regression suite above.

### Combined protected Kafka pipeline: PASS

Final clean run `98009f92-ee63-4a20-bcc7-b2580c155159` passed the actual React ->
API -> PostgreSQL/outbox -> Kafka -> execution -> evaluation -> persisted report
-> results API -> React workflow against the loopback protected fixture.
Synthetic fixture planning supplies deterministic cases; no provider planning,
external application, or real account credentials were used. Executor, signed
handoff, browser context, API, database, outbox, Kafka and evaluator were real.

- One login request completed after same-context login/MFA, viewer disconnect,
  fresh-ticket reconnect and React Release. Its auth suspension was consumed
  and lease released. Seven later isolated cases took/installed scoped snapshots
  and reverified the role; there was no second login handoff.
- Eight cases ran: `async_address`, `valid`, `dependent_role`, `navigation` were
  `completed` with recorded verdict `satisfied`. `empty`, `name_boundary`,
  `recovery`, `invalid_email` were intentionally rejected and `policy_blocked`
  with recorded verdict `unverified`. These are not eight passed assertions.
  Before evaluation the API correctly exposed top-level `awaiting_verification`.
- Actual React **Approve once** authorized only `valid`; actual React **Reject**
  denied the other four actions. Exactly one consumed approval, one completed
  dispatch receipt and **one successful registration effect** persisted. All
  five duplicate decision attempts returned HTTP 409. Rejected actions produced
  no dispatch receipt; their four action suspensions were abandoned.
- All eight browser sessions closed. Results returned the expected pending 409,
  then 200 after evaluation. Report `9f4fcf74-5f4c-4cb3-9b1e-2d2069dd24ac`
  persisted as `completed` and rendered in the redesigned React report page.
- Real report widths 1440, 768 and 390 had no horizontal overflow. Axe reported
  **zero violations** for the scanned report; this does not replace manual
  screen-reader review or certify every application route.
- Safe metadata: `.local/ui-integration-result-f99b0ece11294e5ea9ba9c1d8657f646.json`.
  Owned disposable DB, services, UUID-labelled loopback MinIO and browser
  artifacts were cleaned. No shared Kafka offsets/messages were reset/deleted.

Earlier harness assertions failed honestly: the target initially pointed at the
login page rather than protected `/registration.html?variant=good`; approving an
empty-form validation click correctly produced zero registrations; and pre-
evaluation `verdict` is pending while `recorded_verdict` contains worker evidence.
The final runner corrects those test assumptions without weakening app checks.

### Reclaimed-lease listing: reproduced and corrected

A real PostgreSQL regression created a released historical lease and an active
reclaimed lease for the same request. The list endpoint returned two objects
with the same request ID (`2 != 1`). Its outer join now selects only leases with
`released_at IS NULL`; the request remains visible without a lease. Existing
partial uniqueness prevents concurrent active leases. The final PG test passed,
including the active lease ID assertion. No authorization or generation checks
were removed. Final API contracts: **11 passed**; API strict Pyright: **0 errors**.
Scoped Ruff passed with E501 and the existing ASYNC110 polling-test finding
excluded; `git diff --check` passed. No migration was introduced.

Follow-up source changes (in addition to the preserved UI inventory below):

- `services/control-api/src/markettwin_control_api/api/human_actions.py`.
- `services/execution-orchestrator/src/markettwin_execution_orchestrator/worker.py`
  and `workflow/run_request_handler.py`, `browser/controller.py`,
  `persistence/human_action_lifecycle_repository.py`.
- `services/control-api/tests/test_human_action_repository.py`,
  `test_human_action_response.py`, `test_results_readiness.py`.
- `services/execution-orchestrator/tests/test_stale_run_commands.py`,
  `test_protected_registration_fixture.py`,
  `test_browser_scoped_inspection.py`, `test_human_action_abandon_expiry.py`,
  `fixtures/protected_registration_app/server.py`.
- `apps/web/e2e/ui-workflow.spec.ts` (pending-to-ready regression).

The isolated local harnesses and safe metadata stay under ignored `.local/`.

## Commands executed for the integration correction

All commands ran locally from the repository root unless a service directory is
specified. Disposable runners require the already available loopback dependencies
and cached MinIO image; they do not start a shared Kafka consumer group. These
ignored `.local` orchestration scripts are workspace evidence, not shipped CLIs.

```powershell
.venv/Scripts/python.exe .local/ui_local_integration.py --execute-fixture
.venv/Scripts/python.exe .local/ui_local_integration.py --protected-fixture
.venv/Scripts/python.exe .local/ui_hitl_integration.py --run

# Expanded focused backend suite: 85 passed.
uv run --no-sync pytest services/execution-orchestrator/tests/test_browser_owner.py services/execution-orchestrator/tests/test_viewer_gateway.py services/execution-orchestrator/tests/test_owner_service.py services/execution-orchestrator/tests/test_auth_bootstrap.py services/execution-orchestrator/tests/test_auth_session_broker.py services/execution-orchestrator/tests/test_sensitive_action_policy.py services/execution-orchestrator/tests/test_worker.py services/execution-orchestrator/tests/test_stale_run_commands.py services/execution-orchestrator/tests/test_protected_registration_fixture.py services/execution-orchestrator/tests/test_browser_scoped_inspection.py services/execution-orchestrator/tests/test_human_action_abandon_expiry.py services/control-api/tests/test_hitl_worker_client.py services/control-api/tests/test_human_action_reaper.py services/control-api/tests/test_human_action_response.py services/control-api/tests/test_results_readiness.py services/control-api/tests/test_test_run_results.py -q

# Final API contract rerun: 11 passed (overlaps expanded suite).
uv run --no-sync pytest services/control-api/tests/test_human_action_response.py services/control-api/tests/test_results_readiness.py services/control-api/tests/test_test_run_results.py -q
npm --workspace @markettwin/web run test:e2e -- ui-workflow.spec.ts --grep '409 is|pending evaluation automatically|waiting evaluation can recover|forbidden results' --workers=1
npm --workspace @markettwin/web run typecheck
npm --workspace @markettwin/web run build
```

The real PostgreSQL regression ran from `services/control-api` with
`MARKETTWIN_TEST_DATABASE=1`, the root local env file, provider/AWS values cleared,
and Kafka pinned to unavailable loopback `127.0.0.1:1` (no messaging needed):
`uv run --no-sync --env-file ../../.env python -m pytest tests/test_human_action_repository.py -q --tb=short -p no:cacheprovider`.
Its UUID schema translation/cleanup isolates test rows from application schemas.
Never copy real credentials into command arguments or shared test output.

## Prior UI redesign verification results

| Check | Result | Scope |
| --- | --- | --- |
| Final Chromium desktop + mobile Playwright suite (`npm run test:e2e -- --workers=2`) | **107 passed, 7 skipped, 0 failed of 114** | Mocked UI; clean unified acceptance snapshot at two workers. Seven viewport-specific workbench scenarios are intentionally skipped in the mobile project. |
| Earlier six-worker Chromium desktop + mobile run | 104 passed, 3 failed, 7 skipped of 114 | Historical run under CPU load: one Axe timeout and two missing-link assertions; all three passed in focused rerun and the final complete two-worker run. |
| Focused rerun (`npm run test:e2e -- --grep "authenticated artifact metadata\|pending human request\|non-owner role"`) | 4 desktop cases passed; 2 mobile cases intentionally skipped | No assertion failure reproduced in isolation. |
| Shell baseline Playwright spec | 5 viewport cases passed | Synthetic workspace, axe WCAG 2.1 AA, horizontal overflow, 1440×900, 768×1024, 390×844, 320×700, and 640 CSS px (200% reflow equivalent). |
| AppShell Vitest | 3 passed | Drawer Escape/focus return, route navigation/close, workspace-switch cache isolation. |
| Frontend HITL viewer/page Vitest | 6 passed | Viewer and human-action page, including input-coordinate scaling after resize. |
| Final frontend Vitest / typecheck / build | 42 passed; typecheck passed; build passed (584.33 kB JS, 89.67 kB CSS) | Two-worker unit run; focused post-disclosure FeatureCases recheck also passed 3/3. |
| HITL backend focused suite | 47 passed | Worker, authorization, broker, viewer, approval, reaper, and related focused tests; see [HITL guide](../hitl/README.md). |
| HITL opt-in PostgreSQL tests | 2 passed | Disposable database migration and repository/API-to-signed-worker/Playwright integration. Application authentication was stubbed. |
| Synthetic UI → local API → disposable PostgreSQL smoke | Passed | React login/session cookie, `/me`, application create, loopback target create, UI authorization, draft create, and logout. Disposable data was cleaned up. No execution or provider calls. |
| Prior isolated synthetic execution (superseded by integration correction above) | Execution completed; report unverified in that attempt | Real UI/API/outbox/Kafka/worker path; UUID-scoped test group consumed and committed its command. Immediate results request returned non-2xx without retained status; evaluator/report readiness was not established. |

The shell baseline found a quick-navigation `kbd` contrast ratio of 4.48:1 at
10px. The label was changed to the darker text token and 12px. A subsequent
Chromium check passed contrast, overflow, modal Escape, focus return, and drawer
route navigation with focus moved to `#main-content`. Stable screenshots are
under `.local/ui-redesign/screenshots/`; they are synthetic UI artifacts.

The earlier full-suite failures did not reproduce in the focused rerun. After
final screenshot review, auth coverage became a collapsed-by-default summary
with full detail preserved, and the mobile 100-case list was bounded. The final
unified two-worker suite then passed 107 tests with 7 intentional skips and no
failures. The populated workbench matrix separately completed 8/8 Chromium
checks, followed by the final unified suite against the updated implementation.

## Spec matrix disposition

Evidence is tied to source baseline `339a4b3` plus the preserved working tree.
`PASS` means the listed layer's check passed, not that a broader full-stack
scenario passed. `PARTIAL` means some assertions/layers passed while the full
acceptance remains open. `NOT_EXECUTED` means no execution evidence is available;
historical local pipeline attempts below failed or were incomplete; the new
protected pipeline above passed. Mock API browser tests
are not real API, PostgreSQL, Kafka, or authenticated-target proof.

### E01–E17: UI routes and roles

| ID | Route, precondition, action | Expected → observed evidence | Layer / result |
| --- | --- | --- | --- |
| E01 | Anonymous `/`, `/how-it-works`; visit and follow public navigation. | Public content and useful navigation → public-route UI fixtures and live-render review passed. | Mock UI + local rendered browser / **PASS** |
| E02 | `/login`; unauthenticated local disposable account, login then logout. | Session redirect persists; logout clears session → React cookie/session login and logout smoke passed against disposable API/DB. No provider auth tested. | Real local UI/API/PostgreSQL / **PARTIAL** |
| E03 | Unauthorized workspace/deep link or artifact; attempt direct route/resource. | No cross-workspace/artifact disclosure → frontend guards and cache isolation tests passed; cross-user artifact denial against real API not run. | Mock UI + Vitest / **PARTIAL** |
| E04 | Workspace shell at 320, 390, 768, 1024, 1280, 1440px; operate rail/drawer. | Keyboard navigation, focus return, stable route and no overflow → shell axe/overflow tests, live 1280×800 and 1024×768 review passed. | Mock UI + live local rendered browser / **PASS** |
| E05 | Switch authorized workspace while on scoped pages. | Queries/routes change without retained prior workspace data → workspace-switch cache isolation Vitest passed. | Vitest / **PASS** |
| E06 | `/applications`, `/applications/new`, `/applications/:id`; create/edit, empty/error, long name. | Permission-safe CRUD and duplicate prevention → list/create UI and disposable local application create passed; edit API is explicitly absent/placeholder; full permission/error matrix not run. | Mock UI + real local create/API/PG / **PARTIAL** |
| E07 | `/applications/:id/targets/new`, `/targets/:id/authorization`; create loopback target and authorize. | Exact origin/policy visible and authorization enforced → local loopback target create and authorization smoke passed; destructive origins/network-policy edit matrix not run. | Real local UI/API/PG + mock UI / **PARTIAL** |
| E08 | `/ingestion`, `/knowledge/review`, `/knowledge/review/:id`; inspect state and source. | Pending/approved/rejected state and provenance retained → mocked knowledge workflow E2E passed; no live external source/provider ingestion in this verification. | Mock UI / **PASS** |
| E09 | `/runs`; search/status/mobile row action. | Query and truthful status retained → mocked run-list/status responsive checks passed; backed-up search persistence was not independently verified. | Mock UI / **PARTIAL** |
| E10 | `/applications/:id/runs/new`; select target/options and submit draft. | Original payload/defaults unchanged, one submit → viewport/Axe matrix and exact legacy payload assertion passed; real UI/API smoke created a draft. | Mock UI + real local API/PG smoke / **PASS** |
| E11 | Draft run detail; start once with allowed role and Kafka unavailable/available. | No duplicate start; queue failure truthful → mocked controls covered; final isolated real start was consumed/committed and reached completed. Earlier nonisolated attempt timed out; Kafka-unavailable recovery not exercised live. | Mock UI + real local API/Kafka/worker / **PARTIAL** |
| E12 | `/runs/:id/evaluation`, `/runs/:id/report`; evaluation pending. | Pending never presented as pass/final → pending copy and automatic 409-to-ready UI tests passed; real protected run returned 409 then 200 and rendered its persisted report. | Mock UI + real complete local pipeline / **PASS** |
| E13 | `/runs/:id/overview`, `/journeys`, `/journeys/:journeyId`, `/evidence`, `/findings`, `/report`; inspect direct links. | Existing details, evidence and routes remain usable → case inspector, selected step, exact More route, artifacts and layouts passed mocked Chromium/Axe matrix; real persisted report also rendered responsively. | Mock UI + real report / **PASS** |
| E14 | `/runs/:id/findings`; follow evidence provenance. | Inference not labeled confirmed; evidence link grounded → related view/source tests passed, but no new live issue/evaluator evidence was produced. | Mock UI / **PARTIAL** |
| E15 | `/runs/:id/evidence`; request authorized exact artifact, then try cross-user. | Authenticated exact artifact loads; cross-user denied and failure visible → mocked access-endpoint metadata and intercepted image passed; real cross-user retrieval denial not run. | Mock UI / **PARTIAL** |
| E16 | `/settings/profile`, `/settings/workspace`, `/settings/members`, `/settings/security`; inspect role guards/confirmation. | Role-appropriate settings and accessible destructive confirmation → routes/placeholders covered by UI suite; comprehensive role mutation matrix not run (member/security APIs absent). | Mock UI / **PARTIAL** |
| E17 | `/error`, unknown route and injected timeout/404/empty responses. | Recovery shown without false success → mocked recoverable-state/error route suite passed; not every backend error combination was exercised. | Mock UI / **PASS** |

### H-E01–H-E22: synthetic HITL acceptance

| ID | Route/precondition/action | Expected → observed evidence | Layer / result |
| --- | --- | --- | --- |
| H-E01 | Authorized protected target; request login and pause run. | Real combined run reached awaiting_human, fenced the agent, completed one login and continued to report. | Real React/API/PG/owner/Kafka/evaluation / **PASS** |
| H-E02 | Authorized owner claims the request. | Real cookie-authenticated React claim granted the scoped viewer; reclaimed PG request returns one row with its current lease. | Real UI/API/PG/owner / **PASS** |
| H-E03 | Second operator/tab claims same browser lease. | Conflict, no second input source → exclusive lease/DB contention tests pass; real simultaneous viewer-tab trial not run. | API/PG tests / **PARTIAL** |
| H-E04 | Owner connects viewer after claim. | Real restricted WebSocket controlled the same Playwright context used for login and verified resume. | Real UI/API/owner/browser / **PASS** |
| H-E05 | Synthetic login and OTP through viewer. | Login/MFA passed; no credential-phase screenshots/traces/video. Full integrated DB/APM/Kafka canary sweep remains unexecuted. | Real browser + focused privacy tests / **PARTIAL** |
| H-E06 | Release before login succeeds. | No identity verification or silent resume → verifier/workflow fail-closed tests pass; full paused-run pipeline not run. | Worker/workflow tests / **PARTIAL** |
| H-E07 | Correct synthetic login; release. | Exact user role verified before same-context resume; full protected run and report completed. | Real complete local pipeline / **PASS** |
| H-E08 | Disconnect before Release. | Live successful MFA followed by disconnected Release without reconnect verified identity and consumed the suspension. | Real UI/API/PG/owner/browser / **PASS** |
| H-E09 | Reconnect with fresh ticket; deny reused ticket. | Live unexpected disconnect/fresh-ticket reconnect passed; original-ticket single-use denial covered by gateway regressions. | Real reconnect + gateway regressions / **PASS** |
| H-E10 | Release while viewer connected. | Live React Release revoked input; worker verified authentication and resumed. | Real UI/API/owner/browser / **PASS** |
| H-E11 | Temporary release notification failure. | Retry same lease safely without duplicate control → signed handoff/idempotency tests pass; injected live service failure not run. | API/worker unit tests / **PARTIAL** |
| H-E12 | Expire lease and send stale input. | Real 5-second lease denied stale input; reaper returned pending; fresh claim/ticket accepted input. Natural request expiry persisted expired. | Real API/PG/owner/browser / **PASS** |
| H-E13 | Cancel pending request. | Live React cancellation blocked resume, persisted cancelled, closed browser, produced no reusable snapshot. | Real UI/API/PG/worker / **PASS** |
| H-E14 | Approve opted-in synthetic Save. | React approved valid case; one consumed request, one completed receipt, exactly one target registration and persisted report. | Real complete local pipeline / **PASS** |
| H-E15 | Reject synthetic Save. | Four React rejections stayed policy_blocked/unverified with no receipt; target effect count remained exactly one for the separate approved action. | Real complete local pipeline / **PASS** |
| H-E16 | Tamper page, action fingerprint, or generation. | Old approval cannot authorize changed action → fingerprint/owner/generation validation tests pass; browser-driven tamper workflow not run. | API/worker tests / **PARTIAL** |
| H-E17 | Duplicate decisions/release or replay receipt. | Five live duplicate decisions returned409; PG concurrent consumers dispatched once; focused duplicate revoke/replay tests pass. Full Kafka command replay not injected. | Real decisions/PG + worker tests / **PARTIAL** |
| H-E18 | Interrupt worker/browser during protected action. | Lost browser fails closed, uncertain side effect protected → interruption/uncertainty unit paths pass; real process kill and recovery test not run. | Worker unit tests / **PARTIAL** |
| H-E19 | Reuse auth across isolated cases. | One completed login, eight closed contexts; seven later cases took/installed snapshots and reverified user without another login. Stale-state fallback covered by focused tests. | Real complete local pipeline + broker tests / **PASS** |
| H-E20 | Wrong-role actor or unapproved IdP origin. | Denied before navigation/control → role, actor, exact-origin authorization tests pass; live unapproved-IdP browser trial not run. | API/worker tests / **PARTIAL** |
| H-E21 | Search DB, logs, artifacts, trace, Kafka, UI/report for canaries. | No secrets persisted or exposed → focused browser success/failure/timeout trace and privacy tests pass; integrated DB/APM/Kafka canary sweep not run. | Browser/worker unit tests / **PARTIAL** |
| H-E22 | Viewer resize, pointer mapping, keyboard. | Actual connected login/MFA input passed; resize coordinate scaling and keyboard exit covered by Vitest. Full connected resize/manual keyboard audit not run. | Real browser + frontend Vitest / **PARTIAL** |

### Historical attempts before the integration correction

The following records describe earlier attempts only. Current full protected
pipeline evidence and the stale-command fix are above; these older unknown
responses cannot be assigned a status retroactively.

Earlier integration attempt: the provider-free synthetic worker fixture using real
local Kafka **FAILED its bounded 10-minute completion check**. The API's outbox
published `run.requested` to `markettwin.execution.commands`, but the disposable
run remained `queued`; `execution.agent_executions`, `execution.run_events` and
`execution.action_approval_requests` had no rows. No approval, evaluator or report
was reached. This does not establish the underlying cause or an application-code
defect. The runner printed its run ID only on success, so no run ID was retained.
The UUID database and its owned runtime/browser artifact directory were removed;
the application's database and Kafka offsets/topics were not reset. No retry is
pending. Unit/API/PostgreSQL successes do not prove this pipeline passed.
Two bounded worker-only diagnostics created no run or new message. The first
confirmed process liveness only. The second reached `run_worker` ->
`process_command` -> `accept_run_requested` and repeatedly raised `ValueError`;
this rules out an import/startup hang. The exact exception branch/message was
not retained. Old broker commands referencing a prior disposable database are
a plausible harness isolation problem, not a proven cause. No Kafka topic or
offset was changed. Diagnostic databases and private logs were removed.
The default local execution consumer group has not committed these earlier
synthetic commands. Because their disposable databases were deleted, ordinary
manual startup against this broker can encounter stale requests. Do not assume
this broker is a clean manual-test baseline. The final harness uses a fresh
UUID-scoped consumer group initialized at the topic end, without resetting the
default group.

**Final isolated attempt:** run `fcf0f1b1-6fdd-4124-8122-1ca628ea50aa`
reached exact API lifecycle status `completed`. Test group
`markettwin-execution-worker-test-27e5a237c1fc49008ad85a74fb92e15c`
was initialized at offset 2 before publication, then committed offset 3 with
log-end 3 and lag 0 on partition 0. Only the test launcher's consumer-name
constant was changed; production envelope, relay, request handler and executor
were used. The evaluator polls this isolated PostgreSQL DB directly; it has no
Kafka consumer group. The next `/api/v1/test-runs/{id}/results` call returned
non-2xx; the response status was not retained, so evaluator/report completion
and report UI remain **unverified**. A readiness race is possible, not proven.
Approval count was not printed/retained, so this run does not independently
prove that a sensitive-action approval was requested or exercised. Completion
was read through authenticated `GET /api/v1/test-runs/{id}`; no report UI route
was rendered. The ignored future harness now records safe result metadata and
bounded results-readiness polling, but that revision has not been executed.
The disposable DB, owned processes and browser artifacts were cleaned up. No
further run is pending. The default group was not reset; final broker metadata
reported it absent, so its normal `earliest` startup would replay retained
commands from the deleted disposable databases. No production backend source
was changed to bypass request validation.
No protected external application, real credential, or authenticated live browser
was used here. The frontend-only suite expressly checks that a mock lease grant
does not open the protected WebSocket before Connect.

### P01–P12: responsive, accessibility, resilience and performance

| ID | Route/precondition/action | Expected → observed evidence | Layer / result |
| --- | --- | --- | --- |
| P01 | Shell, run, case, viewer and NewRun at 320/390/768/1024/1280/1440px. | No horizontal page overflow → viewport matrix, 100-case bounded list, shell baseline and live 1280×800/1024×768 checks pass. | Mock UI + local rendered browser / **PASS** |
| P02 | 100-case list, long title/name/origin/ID. | Readable wrapped/truncated content with access to full selection → 100-case keyboard/select test passes at 320/1440; specific long-origin/long-ID matrix not complete. | Mock UI / **PARTIAL** |
| P03 | Direct deep link, refresh, Back/Forward, non-admin route. | Authorized history/navigation only → exact case “More” route and role-hidden HITL controls checked; complete history/direct-refresh permission matrix not run. | Mock UI / **PARTIAL** |
| P04 | Skip link, drawer, disclosure and case selection by keyboard. | Visible/returned focus, operable controls → shell drawer Vitest, keyboard case selection and authenticated-coverage disclosure keyboard tests pass; full tab-order/focus-obscuration review not run. | Vitest + mock Chromium / **PARTIAL** |
| P05 | Screen reader and live status announcements. | Names, status and reading order usable → axe and accessible-name checks only; manual screen-reader/assistive-tech test not executed. | Not executed / **NOT_EXECUTED** |
| P06 | Rendered light/dark UI surfaces. | Contrast and non-color status cues in both themes → light-mode axe WCAG 2.2 AA checks pass; dark mode is deferred and untested. | Mock rendered UI / **PARTIAL** |
| P07 | `prefers-reduced-motion: reduce`; navigate/open disclosure. | Motion reduced without focus loss → reduced-motion UI tests pass. | Mock UI / **PASS** |
| P08 | HITL query polling while request/viewer remains open. | No duplicate or runaway refetch → ordinary query behavior covered; sustained polling/load behavior not measured. | Not established / **NOT_EXECUTED** |
| P09 | Production build and route bundles. | Report bundle delta and avoid gratuitous dependencies → build passes (584.33 kB JS, 89.67 kB CSS); no baseline delta/chunk audit. | Build / **PARTIAL** |
| P10 | Throttled LCP/INP/CLS measurement. | Report measured lab values → no throttled Web Vitals run. | Not executed / **NOT_EXECUTED** |
| P11 | Dark-mode portal, tooltip, select, chart and browser overlay. | All surfaces themed → dark mode deferred; no portal/overlay test. | Not executed / **NOT_EXECUTED** |
| P12 | Repeat submit/approve/release or navigate during action. | No duplicate effect or run restart → focused UI action/duplicate guards and API/receipt idempotency tests pass; full real Kafka replay not run. | Mock UI + API/worker tests / **PARTIAL** |

Additional evidence: live rendered mock overview at 1280×800 and 1024×768
passed axe WCAG 2.2 AA and overflow checks. Review captures include
`.local/ui-redesign/screenshots/workspace-1280.png` and
`workspace-1024.png` where present. Current focused case screenshots are
`cases-1440.png`, `cases-768.png`, `cases-390.png`, `cases-320.png`,
`new-run-1440.png`, `new-run-320.png`, and blank synthetic HITL captures in
`.local/ui-redesign/screenshots/`. These contain mocked noncredential data only.
The 640 CSS-pixel reflow check is not equivalent to browser/OS zoom. Broad
benchmarking and manual screen-reader testing were not executed.

## Local services and data safety

At the initial audit on 2026-10-15, Vite was available on loopback port 5173.
PostgreSQL accepted connections and MinIO was running. Kafka was started from an
already-cached repository Compose image and became healthy. The existing local
application database reported Alembic revision `d7f3c2a9b108`; head was
`f82e4160cb9d` (three migrations ahead). That database was not upgraded. The
successful API smoke used an isolated disposable database at current head and
cleaned up its data; it did not upgrade or overwrite the existing database.

The local Control API/worker service readiness audit initially found no service
on the configured API 8000 or worker 8020 ports; port 8080 was an unrelated
`httpd` returning 404 for the health paths. This audit therefore does not certify
a persistent full application stack. No real browser login credentials or
external application targets were used. One earlier CRUD/Kafka health probe did
contact the repository-configured Aiven Kafka endpoint (apparently with existing
environment credentials); it did not publish a message or start a run, and the
user was informed. Subsequent isolated checks pinned Kafka to local services and
cleared SASL configuration. The follow-up complete synthetic application execution through Kafka,
browser owner, evaluator and report passed as recorded above; no persistent
manual-testing stack is left running by those disposable tests.

## Local commands and changed-file inventory

From the repository root, run the local web app with
`npm run dev --workspace @markettwin/web`. Run the complete mocked browser suite
with `npm run test:e2e --workspace @markettwin/web -- --workers=2`; run shell
component tests with `npm run test --workspace @markettwin/web -- src/layouts/AppShell.test.tsx`.
For backend services, migrations, and the synthetic manual HITL flow, follow the
[HITL guide's local setup and manual end-to-end sections](../hitl/README.md#local-setup).
The redesign source baseline is commit `339a4b3`.

Files changed in the current redesign workspace snapshot (the research master
spec supplied as input is listed separately below):

- `apps/web/e2e/`: `knowledge-workflow.spec.ts`, `run-flow.spec.ts`,
  `ui-workflow.spec.ts`, `ui-shell-baseline.spec.ts`,
  `ui-workbench-design.spec.ts`.
- `apps/web/src/components/markettwin/`: `FeatureCases.test.tsx`,
  `FeatureCases.tsx`, `ResultsBoundary.tsx`, `RunFlowPanel.tsx`.
- `apps/web/src/components/ui/StatusBadge.tsx`; `apps/web/src/layouts/`:
  `AppShell.tsx`, `AppShell.test.tsx`, `RunLayout.tsx`.
- `apps/web/src/lib/`: `targetAuthorization.ts`,
  `targetAuthorization.test.ts`.
- `apps/web/src/pages/applications/ApplicationOverviewPage.tsx`,
  `apps/web/src/pages/overview/OverviewPage.tsx`,
  `apps/web/src/pages/public/PublicPages.tsx`,
  `apps/web/src/pages/runs/`: `HumanActionPage.tsx`,
  `HumanActionPage.test.tsx`, `HumanBrowserViewer.tsx`,
  `HumanBrowserViewer.test.tsx`, `NewRunPage.tsx`, `RunEvidencePage.tsx`,
  `RunFindingsPage.tsx`, `RunOverviewPage.tsx`, `RunReportPage.tsx`,
  `RunsPage.tsx`; `apps/web/src/pages/targets/`:
  `TargetAuthorizationPage.tsx`, `TargetOverviewPage.tsx`.
- `apps/web/src/styles/`: `base.css`, `flow.css`, `journeys.css`,
  `product-theme.css`, `run-records.css`, `tokens.css`, `workspace.css`.
- `docs/CURRENT_STATE.md`, `docs/SESSION_HANDOFF.md`, `docs/hitl/README.md`,
  `docs/ui/ROUTE_INVENTORY.md`, `docs/ui/VERIFICATION.md`.

`MARKETTWIN_UI_REDESIGN_RESEARCH_CODEX_MASTER_SPEC_2026-10-15.md` is preserved
as the supplied input specification. Generated/ignored artifacts are under
`.local/ui-redesign/` (screenshots) and `apps/web/test-results/` (Playwright
diagnostics); they are not source changes. `docs/hitl/README.md` remains the
authoritative source for HITL implementation phases and test/service commands.

## Start manual testing

1. Review [local setup](../hitl/README.md#local-setup), explicitly pin loopback
   Kafka/PostgreSQL/storage and disable content telemetry for local checks. Do
   not inherit cloud broker or provider credentials from an unrelated shell.
2. Upgrade your selected local application database with the documented Alembic
   command. Its last observed revision is `d7f3c2a9b108`; required head is
   `f82e4160cb9d`. This session did not migrate that existing database. No new
   migration is required by this integration correction.
3. Start the existing dependencies, API, **one** execution worker, evaluation
   worker and Vite in the guide. The API/outbox/worker must share the same DB;
   do not reset Kafka offsets or delete topics. Pending human waits occupy the
   execution consumer; later runs can legitimately stay queued.
4. Start the combined synthetic fixture on an unused port, for example:

   ```powershell
   .venv/Scripts/python.exe services/execution-orchestrator/tests/fixtures/protected_registration_app/server.py --port 5193
   ```

5. Authorize exact origin `http://127.0.0.1:5193` with loopback policy and
   requires-auth. Use target **`/registration.html?variant=good`**, not the login
   URL. Configure `#identity`, exact marker `Signed in as user`, role `user`, a
   nonsecret account reference, and explicitly opted-in synthetic effect policy.
   Follow the [manual guide](../hitl/README.md#manual-end-to-end-guide) for the
   declared effect rules and consent; authorization alone does not permit writes.
6. Start the run, open Human assistance, Claim and Connect. Enter only fixture
   `fixture-user` / `synthetic-password`, then OTP `246810`. Release after login;
   verify resumed cases and reused identity. Repeat separately with disconnect /
   Reconnect / Release, disconnected Release, Cancel, and lease expiry.
7. Review the exact pending action/step. Approve the valid synthetic submission;
   reject other mutation probes. `/__fixture_effects` reports successful
   registrations; duplicate decisions must not increase it. Wait for evaluation:
   the results 409 pending response is expected until the completed report is
   available. Open report/findings/evidence and inspect blocked vs verified truth.

## Remaining manual / release verification

- Real process kill/browser crash and uncertain-effect recovery; simultaneous
  viewer-tab contention; live injected revoke-delivery failure; full Kafka replay.
  Focused unit/PG tests cover related paths but do not replace these live trials.
- End-to-end synthetic canary sweep across DB/logs/artifacts/Kafka/APM; focused
  privacy tests passed, and credential-phase capture was disabled in live runs.
- Authorized real SSO/IdP/CAPTCHA and production HTTPS/WSS proxy integration.
  No external application or real-account testing was performed in these runs.
- Manual screen-reader, full keyboard/connected-resize and cross-browser review;
  broad performance/field measurements; H12 adversarial/release certification.
  Dark mode is now implemented; full authenticated dark render/accessibility
  review remains open. **Hosted production remains NO-GO.**
