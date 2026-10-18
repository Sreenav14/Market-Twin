# MarketTwin live execution and human takeover: implementation plan

Updated: 2026-10-17. Status: **planning; further implementation paused by the user**.

This document is the working plan for showing the actual executing browser and
recorded activity, then allowing human interaction when HITL is required. It builds
on the current architecture and preserves all existing uncommitted work. Proposed
interfaces below are requirements, not claims that endpoints already exist.

## 1. Required user experience

The user starts a test without supplying credentials or configuring login markers.
MarketTwin opens the authorized application and executes normally. The user can
open **Live execution**, see the actual active browser page, identify the executing
agent/case, and follow the recorded actions and outcomes.

When an actual login, MFA, SSO, CAPTCHA or supported recovery obstacle is reached:

1. The agent pauses before continuing the blocked operation.
2. The live page clearly says which execution needs assistance and why.
3. An authorized operator chooses **Take browser control**.
4. The existing exclusive control lease is acquired and the same live page becomes
   interactive. The viewer connects automatically following that explicit action.
5. The operator interacts within the already approved origins.
6. **Done—resume agent** revokes human input, verifies safe continuation and resumes
   the same context. Done does not automatically prove an identity or role.
7. **Skip this case/journey** records not tested and advances independent work.

Observation must not acquire a human-control lease, pause execution, enable input,
extend permissions, or count as human assistance. The intended similarity to
watching Codex use a browser is a real page view plus visible actions, not an
animation, generated screenshot, external iframe, or full operating-system desktop.

## 2. Evidence and current state

### 2.1 MT-000050 / Sup_14

Actual Microsoft Edge interaction at `http://localhost:5173/`, saved evidence and
local PostgreSQL were inspected. Run ID:
`65d770e5-ae0e-4283-b516-5caa046726f8`.

- The run completed. It created **zero human requests and zero control leases**.
- The record named Human authentication prerequisite was normal discovery, not a
  human handoff. Its browser closed before feature execution.
- Two real cases ran. One passed; the other failed two inferred visibility checks.
  Neither navigated to a login page; both only navigated to the public product page.
- Docs and Console are visible in the saved screenshot. A locator mismatch is
  plausible; the exact historical accessible names were not retained, so the
  precise cause is not established. This does not prove a product defect.
- The previous flow counted discovery as a third case and placed it last.
- The previous terminal Human Assistance empty state said Waiting for the test.

### 2.2 Corrections already implemented before the planning stop

These are existing working-tree changes to preserve, not work to rebuild:

| Correction | Current code and evidence |
| --- | --- |
| Neutral discovery | No-policy discovery uses Browser discovery / Observe approved starting page and `browser_discovery_v1`; explicit identity policies retain their worker verification semantics. |
| Correct discovery presentation | API exposes runtime name; discovery is separated from case counts and placed before planning. Plan completion uses the actual saved plan event. Existing rows are not rewritten. |
| Terminal assistance | Completed/failed/cancelled runs without requests explain that no human assistance was requested. The corrected MT50 message was verified in Edge. |
| Request context | Assistance responses/UI identify the requesting executor, journey and recorded requesting step when present; closed browsers do not offer an enabled control button. |
| Viewer readiness | After Take control, connection starts automatically. Input is gated until a decoded live frame is drawn. Startup timeout/decode failures are explicit. A WebSocket opening is no longer sufficient to claim readiness. |
| Exact link-name inventory | Native Playwright accessible names replace an inner-text approximation for observed links. Synthetic CSS-generated arrows and aria-hidden children are covered. Frozen expectations and exact matching remain unchanged. |

Focused checks reported before the stop: 26 frontend tests; 23 API tests for the
flow/results group; 5 discovery tests; 44 planner/observation checks; 6 PostgreSQL/
Chromium lease and Skip checks. Some groups overlap; these are not an additive
unique-test total. Frontend typecheck/build and focused production lint/type checks
passed. The existing build chunk warning remains. Repository-wide Python typing
is not clean and must not be represented as passing.

Actual provider-free local pipeline runs after the viewer corrections:

- Persona `a548d974-23f1-4f3f-8e70-4117e84033e8`: public page preceded runtime
  login, automatic live viewer and request context verified, synthetic login/MFA,
  Done, isolated session reuse, three passed journeys and persisted/rendered report.
  Artifact: `.local/ui-integration-result-a3cac89903e74ef9a50c5c72368db3cf.json`.
- Feature Cases `28e0d372-dbc4-4c5e-a86a-4bbe30ba63f8`: completed login request,
  run and report. Existing protected fixture driver also exercises reconnect,
  resume and sensitive approvals. Artifact:
  `.local/ui-integration-result-6df7bf5965234b568850bfdc630cf007.json`.
- These use actual local services/Chromium with scripted or frozen fixture inputs.
  They do not prove live-model planning quality, external SSO, or universal login
  detection. Owned disposable resources were cleaned up; shared offsets unchanged.

### 2.3 Missing capability

**Continuous agent observation is not implemented.** `RunActivityPage.tsx` is a
placeholder. The current viewer only serves an active human-control lease. No
lease-free observation authority, read-only frame API or unified activity endpoint
exists. Both agents stopped before making any changes for that new capability;
there are no partial live-observation implementation files to integrate.

## 3. Audited architecture and exact integration points

This is an architecture and execution-path audit, not a claim that every unrelated
file has been reviewed line by line. Knowledge ingestion, evaluation and reporting
were considered as dependencies; they do not need redesign for live viewing.

| Area / existing file | What exists | Required change and reason |
| --- | --- | --- |
| `apps/web/src/app/router.tsx` | `/runs/:runId/activity` route | Preserve route; use it for Live execution rather than introduce a second competing run page. |
| `apps/web/src/pages/runs/RunActivityPage.tsx` | FutureStagePage placeholder | Replace with real active-browser view, activity and explicit lifecycle states. |
| `apps/web/src/layouts/RunLayout.tsx` | Run polling, awaiting-human banner; Activity under More | Expose Live execution prominently and link to it after Start. Keep standalone Human Assistance compatible. |
| `apps/web/src/pages/runs/HumanActionPage.tsx` | Authorized claim/renew/Done/Skip/approval UI | Reuse for the interrupt inside Live execution. Avoid two independently mounted controllers for one lease. |
| `apps/web/src/pages/runs/HumanBrowserViewer.tsx` | Volatile interactive canvas and sequenced WebSocket input | Retain for human control. Do not enable these input handlers for observation. |
| `apps/web/src/lib/api.ts` | Cookie-authenticated API client and result contracts | Add typed observation metadata, bounded activity and binary-frame calls. Keep images/tickets out of global query caches. |
| `services/control-api/.../api/human_actions.py` | Existing operator permissions, lease endpoints, safe worker configuration validation | Reuse authorization policy and endpoint conventions; do not create a lease just to watch. Avoid a new module importing an unrelated route's private helper long term. |
| `services/control-api/.../services/hitl_worker_client.py` | HMAC-signed internal JSON request client | Add a bounded binary-image request using the same signing, timeout and safe-error rules. |
| `services/control-api/.../main.py` | Explicit router registration; outbox/reaper lifecycle | Register the new read API. No new background infrastructure service is required. |
| `services/control-api/.../persistence/repositories/test_run_results_repository.py` | Journey/step queries and `_safe_action_summary()` | Reuse fixed safe summaries for activity. Never return arbitrary stored historical text or raw observations as a live log. |
| `services/execution-orchestrator/.../browser/owner.py` | `frame(OwnerLease)` checks active human ownership and captures volatile JPEG under lock | Add a separate read-only observation operation. Do not weaken `_require()` or fabricate a lease. Share only safe low-level capture code where useful. |
| `.../browser/owner_registry.py` | Exact session/execution/journey handle lookup in this worker process | Resolve observation to the same existing context; reject wrong/stale handles. |
| `.../browser/viewer_authority.py` | Live user/session, workspace, target, lease and generation checks | Add separate observation permission checks that do not depend on a human request or grant input rights. |
| `.../browser/owner_service.py` | Existing private HTTP service; signed bodies, timestamps, replay-protected nonces | Add a strict internal observation request/response; no raw CDP, arbitrary URL or JavaScript endpoint. |
| `.../browser/viewer_gateway.py` | Human WebSocket JPEG/input transport | Preserve its lease rules, exclusive input, origin checks, disconnect and revoke semantics. |
| `.../browser/controller.py`, `session.py`, `contracts.py` | Owned page/context, session lock, control modes/generation and encounter callback | Observation must honor these states and never modify them. Check before and after capture. |
| `.../persistence/step_recorder.py`, `execution_repository.py` | Steps committed before/after actions | Reuse for live activity; add only missing safe lifecycle events, not duplicate action storage. |
| `.../workflow/{deep_run,case_execution,journey_executor,auth_bootstrap}.py` | Both execution modes, discovery and shared HITL | Audit every browser creation/closure path for observable identity and transition consistency. Do not add unconditional login. |
| `.../worker.py` | One execution consumer, process-local browser registry | Preserve scheduling; worker loss means unavailable context, not permission to replay actions. |
| `packages/database-python/.../models/{execution,testing}.py` | BrowserSession, AgentExecution, ExecutionStep, HumanActionRequest, leases, suspensions, run events | Existing records should suffice. Add a migration only if a proven missing durable lifecycle fact requires it. |
| `apps/web/vite.config.ts` | `/api` proxy plus existing WebSocket viewer proxy | Reuse for local HTTP observation and unchanged control WebSocket. Verify deployed proxy separately. |

## 4. Design decision: observation and control stay separate

### Recommended first implementation

Use **bounded JPEG polling through the authenticated Control API and existing
signed worker HTTP service** for read-only observation. Keep the existing WebSocket
for interactive HITL. This is a proposed implementation choice, not an implemented
endpoint.

Why this is the smallest reliable change:

- It reuses the existing worker listener, browser registry, CDP capture and API
  authentication. No VNC, WebRTC, additional broker, browser service or public CDP.
- Each frame is independently authorized and bound to the exact selected browser.
- An observation request cannot contain clicks, text, keys, scripts or navigation.
- An initial nominal one-frame-per-second refresh is enough to establish truthful
  observation. Label it refreshed live viewing; do not promise video frame rates.
- Frame and metadata requests are bounded; no overlapping frame fetches. Hidden
  tabs stop fetching. Rendering failure cannot pause or fail an otherwise healthy run.

Tradeoff: polling adds HTTP/authentication work and is not smooth video. If a
measured product requirement later needs higher frame rates, consider a distinct
read-only WebSocket ticket mode using the same authorization contract. That is a
separate decision; do not prematurely build two observation transports.

The current human viewer waits 0.5 seconds between JPEG frames before capture and
transport costs. It is also a page viewer, not a full browser-chrome/OS desktop.

## 5. Proposed API contracts

### 5.1 Metadata and bounded activity

`GET /api/v1/test-runs/{run_id}/live-browser`

Return only authorized metadata:

- Run status and actual phase, with a server observation timestamp.
- Selected browser ID, execution ID, journey ID, control generation and mode,
  or `browser: null` with an explicit reason.
- Human-readable executor/case title, optional recorded step reference, and whether
  a real human request or sensitive approval is pending.
- At most 50 safe activity records initially; cursor pagination for older records.
- Recorded lifecycle event types, step type/status/timestamps and fixed redacted
  summaries. Mark the source: planner, discovery, persona, deterministic case,
  human-assistance decision, evaluation or report.

Do not expose passwords, entered values, raw DOM, cookies, session state, full
redirect URLs, arbitrary provider bodies or internal model reasoning. Persisted
browser actions and lifecycle events are not proof that every agent internal
operation is observable. Unknown/unrecorded phases must say so.

### 5.2 Exact-session image

`GET /api/v1/test-runs/{run_id}/live-browser/frame?browser_session_id=...&generation=...`

- The API chooses/validates the browser through the run/execution/journey chain.
- The supplied browser ID and generation prevent an old case label from displaying
  a new case's image. The API must never silently substitute a different browser.
- Return bounded `image/jpeg`, at most a proposed 2 MiB, with `Cache-Control:
  no-store`, `Pragma: no-cache` and a cookie-aware cache boundary.
- Use generic authenticated errors: 401 session ended; 403/404 unauthorized or
  hidden resource according to existing policy; 409 stale/unavailable/suppressed
  browser; 503 unavailable worker. The UI refetches metadata rather than guessing.
- Reject unexpected query/body fields; never accept target URLs or protocol methods.

### 5.3 Private worker observation

`POST /internal/hitl/observe` on the existing private worker service.

Strict signed JSON: actor ID, browser session ID, execution ID, journey ID and
expected control generation. Apply existing body-size, timestamp, nonce, HMAC,
timeout and safe-error conventions. Recheck durable authority and the live owner.
Return only volatile bounded JPEG bytes with no-store headers.

No caller chooses a worker URL. No arbitrary downstream image URL is proxied. No
authentication material is placed in image URLs, browser history or log messages.

## 6. Observation authorization and privacy requirements

For the first release, viewing uses the existing **owner/admin** operator boundary;
ordinary workspace run visibility is not sufficient authorization for live pixels.

The API and worker must independently verify:

1. Active user/session at the public API; active user and current workspace/operator
   entitlement at the signed worker boundary.
2. Active workspace and target, current nonrevoked/unexpired target authorization.
3. Run, journey, execution and browser ownership match exactly.
4. Browser is open, live in this worker, and at the expected generation.
5. Current page is within the frozen approved application origins. Login does not
   add a subdomain or approve a destination. Existing special IdP rules are not a
   general observation bypass.
6. Observation is allowed only in explicitly permitted agent/pending modes. An
   active human lease, verification, terminal failure or generation change suppresses
   observation before and after capture. The authorized controller uses its separate
   existing viewer during human entry.

Read-only capture must not change capture flags, control mode, generation, deadlines,
leases, authentication grants or the frozen plan. Use a bounded lock wait so viewing
cannot indefinitely block a browser action. Revalidate immediately before sending
bytes; never return a frame captured across an ownership transition.

Frames stay in memory only. No S3/MinIO objects, database blobs, Kafka messages,
React Query image caching, local/session storage, service-worker cache, downloadable
session replay or persistent last-frame history. Revoke image object URLs and clear
the canvas on session changes, permission loss, human takeover, verification,
terminal state, logout, unmount and decoding errors.

Human-entered text and keystrokes must remain outside the activity timeline. Show
only safe decision facts such as assistance requested, control claimed, released,
verified, skipped, expired or cancelled. A visible authenticated page can itself
contain sensitive data; therefore access remains operator restricted. Do not claim
generic masking can identify every possible application secret.

## 7. UI and lifecycle behavior

Use the existing Activity route, displayed prominently as **Live execution**.
Retain Human Assistance as a compatible route to the same request/control machinery.
After Start, direct the user to Live execution or provide an immediately visible
Watch live execution action. Do not bury it under More.

Layout: large real browser viewport, current executor/case/status above it, and a
bounded chronological activity panel beside it on desktop and below it on small
screens. Show last-frame time, viewport dimensions and clearly read-only status.
Preserve natural aspect ratio and accurate pointer mapping during actual takeover.

| State | Required UI / behavior |
| --- | --- |
| Draft / queued | Explain no browser has opened yet; show actual queue/run status. |
| Discovery | Show discovery as a separate stage, never a product case or verified login. |
| Planning with no open browser | Show planning/waiting-for-browser; do not show a stale page as live. |
| Agent executing | Live read-only page, exact executor/case and current recorded action. No input forwarding. |
| Assistance pending | Prominent paused reason and requesting journey; Take control and Skip are visible. Any pending preview is noninteractive and must be suppressed before another operator enters data. |
| Human controlling | Only the exclusive authorized controller sees the interactive viewer; ordinary observation stops. Reuse existing claim/renew/reconnect/Done/Skip. |
| Another operator controls | Explain ownership; no second control and no exposure of the operator's secret-entry frames. |
| Verifying after Done | Human input disabled; ordinary observation remains suppressed until the worker establishes safe continuation. |
| Resumed | Reacquire current metadata/generation and follow the current actual browser. |
| Between isolated cases | Clear the old frame immediately; label the next execution only after its exact browser is selected. |
| Disconnect / slow frame | Show stale/unavailable, bounded retry and last successful time. Do not fail the test solely because the viewer is disconnected. |
| Skip | Not tested—human assistance skipped; continue independent work, never mark passed. |
| Completed / cancelled / failed | Stop polling frames, clear volatile pixels; preserve durable safe activity and links to recorded evidence/report. |

Do not mount a second HumanActionPage with separate lease state while an existing
control component remains mounted. Share or reuse that control state at one stable
place. Route changes and refresh must retain backend lease semantics: disconnect
does not mean Done, and stale local state does not authorize input.

## 8. Activity data and truthful status

Reuse ExecutionStep's committed start/completion records. Use safe event projection
from RunEvent, AgentExecution, HumanActionRequest, approval and Report states rather
than copying arbitrary JSON payloads into the UI.

Add only lifecycle events necessary to fill proven gaps: discovery start/end,
planning start/end/failure, requesting assistance, ownership decisions and resumed
execution. First inspect existing records so the same action is not recorded twice.

Every event needs stable identity, timestamp, source, run/execution/journey linkage
when applicable, safe summary and status. Stable cursors/order prevent duplicate
rows after refetch/reconnect. Plan timing is not inferred from the mere presence of
a discovery journey. "Completed" execution and failed product assertions stay
separate. Evaluation pending is not represented as a failed run.

## 9. Implementation sequence and ownership

| Phase | Work | Verify before continuing |
| --- | --- | --- |
| L0: reconcile checkpoint | Preserve dirty tree; review the files in section3 and completed corrections; inspect actual local configuration and active runs. Finalize response/state contracts. | Exact current capabilities/missing pieces documented; no duplicate feature work. |
| L1: secure observation core | New lease-free authority check; same-context read-only frame adapter; signed worker endpoint; bounded capture/response. | Real Chromium frame works in allowed agent mode; wrong actor/handle/origin/generation/human mode all rejected; viewing changes no control state. |
| L2: public read model | Authorized metadata/activity and exact-session binary API; worker-client binary method; router registration; safe summaries and explicit errors. | Tenant/operator tests, stale-session races, no-store and payload bounds pass. |
| L3: visible live page | Replace Activity placeholder, add prominent navigation, read-only rendering and safe polling cleanup; show agent/case/activity. | Public synthetic agent activity visibly updates; no input path; case transitions clear stale images; responsive/accessibility checks pass. |
| L4: inline HITL transitions | Integrate existing takeover/approval component into the live page; observation suppression, explicit claim, readiness, Done/Skip/reconnect and verified resume. | Same browser/context survives handoff; one controller; failed verification stays blocked; rejected/duplicate actions do not execute. |
| L5: gaps and failures | Audit delayed login/MFA/SSO detection, cancellation, expiry, worker loss, missing owner and permission revocation; fill only proven event gaps. | Both execution modes fail closed and report honest outcomes; no automatic replay. |
| L6: complete local acceptance | Actual UI/API/PostgreSQL/outbox/Kafka/worker/browser/evaluation/report with public, protected, good and seeded-bug synthetic fixtures. | All acceptance rows below have exact outcomes and evidence; regressions fixed and rerun. |
| L7: startup/release handoff | Document current migration head, required restarts, local vs external broker choice and supported single-worker topology; record remaining production checks. | No old worker/API silently serving new UI; local manual guide reproducible; deployment remains separately authorized. |

Parallel work may begin after L0 contracts are fixed: one owner for worker
observation/authority, one for API/read model, one for UI/tests, with root integration
and independent security review. Shared files have one owner at a time. Backend
observation and API tests can run independently; integrated UI tests require both.

## 10. Acceptance matrix

Every row needs an actual result; a mock response does not satisfy an integration row.

| Scenario | Acceptance criterion |
| --- | --- |
| Ordinary public run, both modes | No unconditional login request; actual agent browser and safe activity visible. |
| First-page and later login | Assistance appears only after the actual challenge; correct execution pauses. |
| Read-only watching | Clicking/typing in observation cannot affect the page; observer cannot call the input protocol. |
| Same-context takeover | Context/session identity and synthetic login state remain the same through control and Done. |
| Login + MFA | Operator visibly interacts through the viewer; worker cannot continue while human owns the page. |
| Challenge still present | Done cannot falsely claim authenticated continuation. |
| Reconnect | Fresh ticket; unchanged exact ownership until a durable transition; no generation bypass. |
| Disconnect then Done | Revocation reaches worker; wait resumes; no stale input or generation mismatch. |
| Skip before/during control | Only current blocked work is not tested; independent cases continue. |
| Expiry/cancellation | Viewer/input shut down; clear UI; no resumed protected action. |
| Two operators | Only one controls; observation does not reveal the other operator's credential entry. |
| Revoked user/target/role | Next metadata/frame/input denied and pixels cleared. |
| Wrong tenant/run/browser/generation | No metadata or frame leakage; no silent browser substitution. |
| Worker interruption | Browser unavailable honestly; no fake live view or automatic mutation replay. |
| Case turnover | No old label/new frame or new label/old frame pairing. |
| Sensitive actions | Review required action; approve executes at most once; reject/duplicate execute zero times. |
| Secret canaries | No password/OTP/token in activity, URLs, logs, traces, images saved by the feature, caches or artifacts. |
| Seeded-good/seeded-bug | Expected pass/failure classifications and evidence persist; no visual improvement changes test truth. |
| Evaluation/report | Persisted results appear in UI; pending evaluation distinguished from an actual error. |
| Responsive/keyboard | Desktop/tablet/mobile layouts remain usable; correct coordinates; escape from browser keyboard control; clear status announcements. |

Focused unit/security tests precede the integration matrix. Keep one bounded
reproduction per defect and rerun affected cases. Avoid provider-backed experiments,
external site replays or broad benchmarks unless separately authorized.

## 11. Operations, rollout and known limits

- Existing PostgreSQL migration head is `6b0e2ac784d1`; no new observation table or
  migration is currently justified. Confirm head when implementing.
- The normal localhost configuration currently points to an external Kafka broker.
  Restarting those configured services would use its credentials. Permission for
  that restart was asked but not granted before the user stopped implementation.
  Do not infer consent. Use isolated loopback services for development checks.
- Restart API and execution worker after code changes. Frontend HMR does not reload
  Python modules or the worker's environment. Do not launch duplicate consumers or
  reset shared Kafka offsets to make a local test pass.
- Pending HITL occupies the single execution consumer. Later runs can queue while
  API/viewer remain responsive. Observation must not introduce another execution
  consumer to conceal this limitation.
- Browser ownership is process local. Multi-worker routing, durable browser
  resurrection, hosted production release and arbitrary desktop dialogs are not
  delivered by this plan. If deployment requires multiple execution workers, design
  that owner-routing contract separately before claiming support.
- Production needs authenticated HTTPS and same-origin WSS routing for existing
  control, trusted internal worker transport, proxy timeouts/body limits and reviewed
  cookies/origins. Development Vite proxy success does not certify production ingress.
- Never push, deploy, purchase services, use real test credentials or expand external
  origin permissions as a side effect of implementation or verification.

## 12. Definition of done and stop rule

The live-execution feature is complete only when an authorized user can actually
watch an executing synthetic run, identify its agent/case/action, see it pause on
a real protected step, interact through the same owned browser, choose Done or
Skip, and reach an honestly classified persisted report in both execution modes.
Security denials, case turnover and failure states must pass the relevant tests.

Deliver exact changed files, commands, migration/restart requirements, evidence
identifiers, test outcomes and remaining manual/production limitations. Distinguish
coding completeness from verification coverage. Do not equate the existing passing
takeover tests with continuous observation being implemented.

**Current stop:** code work remains paused. This document and checkpoint updates
are the only work authorized by the latest instruction; resume implementation only
when the user asks to proceed.

## References

- [Current HITL guide](README.md)
- [Verification and MT50 evidence](../ui/VERIFICATION.md)
- [Browser architecture](../BROWSER_ARCHITECTURE.md)
- [UI implementation specification](../../MARKETTWIN_UI_REDESIGN_RESEARCH_CODEX_MASTER_SPEC_2026-10-15.md), especially sections6.8–6.9.
- [Playwright CDPSession](https://playwright.dev/docs/api/class-cdpsession)
- [Playwright authentication](https://playwright.dev/docs/auth)
- [Chrome DevTools Page protocol](https://chromedevtools.github.io/devtools-protocol/tot/Page/)
- [OWASP WebSocket security](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html)
