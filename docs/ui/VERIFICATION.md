# UI redesign verification

Updated: 2026-10-15

This record separates mocked browser coverage from local service integration.
Visual Playwright fixtures use synthetic users, workspaces, runs, approvals, and
artifacts. They do not visit external applications or invoke model/provider
planning. HITL credential-bearing browser phases remain excluded from screenshot
and trace capture.

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
  Dark mode remains deferred. **Hosted production remains NO-GO.**
