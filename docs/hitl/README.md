# MarketTwin HITL: implementation, operations and testing guide

Updated: 2026-10-17. This is the single current HITL documentation entry point.
It consolidates the implementation handoff, phase evidence, transport review,
baseline reconciliation, finish checklist and original master implementation plan.

**Current work is paused for planning.** The requested continuous live agent
browser/activity view is not implemented. See the detailed
[live execution implementation plan](LIVE_EXECUTION_IMPLEMENTATION_PLAN.md) for
current code status, exact required files, reasons, security, dependencies and
acceptance tests. Existing human takeover is a separate capability. The plan also
records the MT50 corrections implemented and tested before the pause.

**Release status: local pilot code implemented; hosted production NO-GO.**
Focused checks and the complete synthetic local HITL-to-report pipeline passed.
Comprehensive adversarial, external-identity and release verification remain open. Implementation status must not be read as acceptance certification.

## Runtime-only HITL implementation (2026-10-17)

New tests start without login, identity-marker, role or account-reference fields.
The API freezes `runtime_human_assistance: true` for these runs. Agents begin
normal browser execution; an actual detected authentication challenge requests
assistance. A public page containing a Login link does not itself trigger takeover.
If the first destination is a login page, assistance may appear after that first
navigation. Existing runs retain their frozen configuration and explicit identity
verification policies.

The operator opens **Human assistance**, chooses **Take browser control**, connects
to the same live browser, and completes login/MFA or other needed interaction within
approved origins. **Done—resume agent** revokes viewer authority and checks safe
continuation before browser tools resume. Without an explicit verification policy,
completion proves neither a particular identity nor a role. A scoped in-memory
session may be reused in isolated contexts within the same run and target; failed,
skipped or cancelled handoffs revoke provisional copies. Authenticated state is
not written as a reusable file. Runtime-enabled contexts disable raw traces before
an unexpected login is encountered.

**Skip this case/journey** is available before claiming control and while controlling.
It durably marks the request skipped, fences/releases control, abandons its
checkpoint, and records **Not tested—human assistance skipped**. It does not pass
the assertion, produce a product defect, or cancel independent work. Another
independent journey may request assistance if it encounters its own login blocker.
Duplicate Skip preserves the original terminal generation and cannot revoke a
newer session. Stop run remains separate.

Migration `6b0e2ac784d1` adds the skipped state and terminal-generation fence on top
of `31d4ef097a2b`. It has been exercised on disposable PostgreSQL databases and
applied to the normal loopback database after verifying zero active runs. Restart
the API and workers before using the feature. On another checkout, apply the
migration before restarting. Do not
start duplicate execution consumers or reset shared offsets. Existing service
processes do not reload this code automatically.

Local evidence and exact remaining checks are maintained in
[UI verification](../ui/VERIFICATION.md#runtime-only-hitl--2026-10-17).
Coverage is synthetic: it does not certify arbitrary external SSO/CAPTCHA widgets,
all possible login-page layouts, or live-model planning quality. Generic difficulty
is not automatically treated as proof of authentication or permission to expand
scope. Out-of-origin navigation still needs a separately approved execution scope.

## Historical runtime-only HITL research (before implementation)

The following records the original gap analysis and proposed acceptance matrix.
The implementation status above and verification record supersede this historical
description; unchecked research scenarios remain verification work, not proof of
universal support.

### Confirmed user experience

Start a test without supplying login credentials, identity markers, role/account
references or enabling HITL. Agents execute normally. Only an encountered blocker
creates human assistance. The operator may control the same live browser freely
within the frozen approved origins. **Skip this case/journey** records **Not tested:
human assistance skipped** and continues independent work; it never bypasses login
or marks a skipped test passed. Stop run is a separate action. If the first page
itself requires login, a request can legitimately appear on first navigation;
there must be no unconditional pre-execution login request.

Both operator choices were explicitly confirmed in conversation: free takeover
within approved origins; skip only the blocked case/journey.

### Why the previous behavior differed

- `NewRunPage.tsx` forces verification and required mode for `requires_auth` targets;
  its form requires identity-marker, role and account-reference fields.
- Control API `api/test_run.py` rejects protected runs without that policy. Simply
  changing required to optional still needs an upfront policy.
- `journey_executor.py` and `case_execution.py` bind the authentication callback
  only when an `AuthVerificationPolicy` exists. `auth_bootstrap.py` can request
  authentication before feature discovery. The low-level challenge detector is
  already runtime-oriented, but no-policy runs do not get the callback.
- `HumanActionPage.tsx` exposes cancellation, not skip. The database request status
  constraint has no skipped state; deep-result contracts have no assistance-skipped
  result. Renaming Cancel would lose the distinct outcome and reporting semantics.
- `auth_session_broker.py` accepts only a verified principal matched to explicit
  role/account/origin. It cannot safely treat arbitrary human completion as a
  verified role. Unconfigured sessions also enable raw Playwright traces; privacy
  needs to cover unexpected login redirects before any secret entry, not only
  sessions declared authenticated at creation.

### Recommended implementation using current architecture

1. Make runtime assistance the new-run default, remove required login/HITL fields
   from the ordinary form, and allow creation without an authentication policy.
   Target authorization and frozen origins remain mandatory. Preserve old frozen
   policies and explicit role-verification contracts for existing runs.
2. Bind a common assistance handler to every persona, discovery and feature-case
   browser session before first navigation. Combine bounded password/MFA/CAPTCHA
   detection, evidenced login redirects/auth challenges, and a structured agent
   request-help tool. A marketing Login link, generic403, wrong assertion or product
   bug is not by itself proof of an authentication challenge. Bound repeated requests
   per obstacle so a skipped challenge cannot produce an immediate prompt loop.
3. Reuse durable requests, suspensions, ownership and exclusive viewer leases.
   Pause browser tools and the execution budget, persist the exact execution cursor,
   display the requesting agent/case/step/reason, and offer **Take control**, **Skip
   this case/journey**, and separate **Stop run**. While controlling, use **Done,
   resume agent** and retain Skip. Do not record live frames, entered credentials
   or token-bearing redirects. Reuse existing channels; no new service/framework.
4. Resume only after viewer authority is revoked and the current generation is
   reconciled. Reobserve the actual page, require an approved application origin,
   check that the relevant obstacle/continuation permits progress, and recheck action
   policy. A human may have navigated or already performed an action: never blindly
   replay a pending submit/click or alter frozen expectations to fit the new state.
   Where continuation/effect cannot be established, report human-assisted/unverified
   or offer Skip rather than inventing success.
5. Distinguish an operator-established browser session from independently verified
   identity/role. Ordinary login needs no marker input. It can produce a short-lived,
   in-memory runtime session grant bound to run/target/exact origin/operator/session
   epoch for allowed case reuse, with identity/role explicitly unknown. Existing
   approved role oracles can upgrade verification; role-dependent tests without
   proof remain unverified/not tested. Such a grant never expands action or origin
   authorization. Logout, expiry, changed identity or challenge revokes stale copies.
6. Add explicit skip request/result semantics through migration, API, worker,
   shared contracts, evaluation and UI. Skip must atomically resolve the request,
   abandon its suspension, revoke any lease/tickets, close or quarantine that case's
   context and advance only to independent work. Duplicate Skip/Done must be
   idempotent; a worker notification failure cannot permit stale viewer input.
   Preserve distinct cancelled, expired, skipped, failed and assisted outcomes.

### Research basis and acceptance gates

[LangGraph dynamic interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
support conditional durable pauses; its side-effect guidance highlights replay
hazards. These are patterns to apply to existing MarketTwin machinery, not a reason
to migrate frameworks. [Browser Use custom tools](https://docs.browser-use.com/open-source/customize/tools/basics)
demonstrate an agent requesting human input during execution; that example alone
does not supply authenticated viewer ownership or safe browser continuation.
[Playwright authentication](https://playwright.dev/docs/auth) documents context
isolation and sensitive authenticated state. [OWASP authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
distinguishes identity from permission; human login cannot grant arbitrary scope.

Original acceptance matrix (see verification record for executed scenarios): no-configuration public run
never prompts; late login in both modes; first-page login only after navigation;
same-context takeover/Done; human navigation and completed-side-effect no replay;
Skip before/during claim with next independent case continuing; duplicate decisions;
challenge still present;401/403 versus genuine bug distinction; identity-unknown
reuse versus verified-role isolation; popup/SSO scope enforcement; disconnect/expiry/
cancellation/worker loss; secrets canary across traces/logs/artifacts; skipped and
assisted outcomes accurately rendered in the final report. Existing configured-flow
tests do not establish that this new no-setup flow works.

## Latest corrections: MT-000048 and MT-000049

Implemented and exercised locally on 2026-10-17. Detailed outcomes and executable
commands are in [UI verification](../ui/VERIFICATION.md#mt-00004849-corrections--2026-10-17).

### Additional destination approval

Open the target's **Network policy / Execution scopes** page. Request a new target
name, the complete list of exact origins (including the base origin), and a reason.
This creates a separate **pending** target. An owner/admin then reviews every origin
on its Authorization page and explicitly authorizes that new scope. Select the new
target when creating a new run. Existing runs cannot be expanded or retroactively
resumed into an unapproved origin. Login never grants destination authorization.
Wildcards, credentials, paths, queries, fragments and automatic subdomain trust are
rejected. Migration `31d4ef097a2b` links revisions without changing existing scopes.

### Authentication in either execution mode

New Test supports **verified human authentication assistance** for Persona journeys
and Feature Cases. Protected targets require authentication. A public target may
explicitly select optional authentication: public browsing continues until a bounded
visible credential/MFA/CAPTCHA challenge or approved human-only IdP is encountered.
Configure the approved application origin, unique identity marker selector, exact
marker text, role identifier and nonsecret account reference. SSO origins must
already be in the approved execution scope and are human-only.

The worker creates a durable request; the operator claims exclusive browser control,
connects the live viewer, enters synthetic/test credentials directly in that browser,
and chooses **Release control for verification**. The worker verifies the exact
approved identity before resuming the same context. Login alone does not establish
a role. Reuse is in memory, bound to run/target/origin/account/role, copied into isolated
contexts, and reverified. A failed identity check blocks resume and revokes reuse.
Unexpected unknown origins stay blocked. An arbitrary difficult page is not proof
that authentication is required. Narrow missing/ambiguous-control assistance remains
bounded and separately verified. Worker loss does not restore a live browser.

### Verification changes and remaining limits

New plans prefer unique semantic controls. Rendered text assertions normalize DOM
whitespace without editing frozen targets/expectations; genuine duplicates remain
ambiguous. The explicit `url_path_v1` oracle ignores query/fragment by contract and
persists no arbitrary mismatched path. Unsupported private full-URL/value reads are
unverified, not product defects. Benign documentation links need real link metadata,
no form, a safe documentation path and an already authorized destination; labels
alone cannot waive restrictions. Filter reset still requires one-time approval.

Real synthetic UI-to-report tests passed in both modes on good/seeded-bad fixtures.
Required and optional persona authentication, reconnect/Release, approvals/rejection,
duplicate decisions, expiry and cancellation were exercised. This is local pilot
evidence, not external IdP/CAPTCHA compatibility, model-quality or release certification.
The single execution consumer still waits while its run awaits a human; no new
infrastructure was introduced. Restart old local services before manual testing.

## Investigation evidence preceding these corrections

### Findings from persisted evidence

| Run | Mode | Recorded outcomes | Human requests |
|---|---|---|---|
| MT-000048 / `3c1f46d0-1dc2-413d-8f54-0000110bcb8c` | Legacy persona journeys | Six journeys: four policy-blocked, one passed, one inconclusive | None |
| MT-000049 / `2f9205d2-a5d4-4261-8ce4-0c0ba787bbbf` | Feature Cases | Five cases: two satisfied, two unverified, one not satisfied; **zero policy-blocked** | None |

Both runs froze only `https://supermemory.ai` with `include_subdomains=false`.
Both targets had `requires_auth=false`, no authentication verification policy,
and sensitive-action approvals disabled. Completed run status means collection
finished; it does not mean every journey passed.

MT-000048's four blocked steps all have the exact reason:
`Target origin "https://console.supermemory.ai" is not allowed.` They occurred in
journeys 1/2/4/6 at steps 36/6/19/17 respectively: two clicks and two navigations.
This proves a destination authorization mismatch. It does not prove that a login
screen was reached: the destination was blocked first. There were no durable
human requests. Legacy `browser/tools.py` records and rethrows browser policy
exceptions; `workflow/journey_executor.py` does not bridge these into the modern
verified authentication handoff. This is a real workflow coverage limitation.

MT-000049's distinct issues:

- Overview heading: text `What a memory is` matches both a Contents link and a
  heading; the assertion returned `ambiguous_target`. Title assertion passed.
- Agent-format navigation: expected `/product.md`; the recorded frame remained
  `/product/` and acquired a query string. The URL verifier returned unverified
  `inspection_failed` because its privacy contract cannot compare redacted URLs.
  A recorded `/product.md` fetch returned 200 and a separate request returned 503.
  These facts do not establish the cause of the final routing behavior; no raw
  query values were disclosed and no external replay was performed.
- Contents and Pricing cases passed their recorded assertions.
- Mobile heading: screenshot and accessibility snapshot show the expected heading.
  Trace DOM text is `Memory that infers, updates and forgets.The engine, in one page.`
  because a `<br>` separates the first sentence and a span. The generated plain
  text locator includes a space after the period and reports absent. This is a
  reproducible selector/oracle mismatch, not a confirmed mobile product defect.
  The expectation is inferred and must remain distinct from an approved finding.

Offline Chromium reproduction using synthetic inline HTML confirmed mobile text
matches 0 versus heading-role matches 1; overview text matches 2 versus heading-role
matches 1. Pure URL-policy probes confirmed the frozen root-only authorization
rejects console while an explicitly supplied exact console origin accepts it.
The latter is a diagnostic probe, **not a change to any actual target authorization**.

### Why login does not automatically open HITL here

Current behavior is configuration-driven, not a universal login detector:

| Configuration or boundary | Current behavior | Required correction |
|---|---|---|
| Public target + legacy persona | Agent tools run inside frozen scope; policy exceptions can end a journey | Explicit scope-review outcome and visible executor capability limits |
| Protected Feature Cases + approved identity policy | Verified bootstrap/login/MFA takeover and controlled resume | Existing supported route; use a protected application target |
| Public Feature Cases + missing/ambiguous click control | One bounded generic recovery attempt | Existing supported recovery; never count it as verified login |
| Unexpected login on a public target | No general authentication escalation/identity policy exists | Optional-auth contract, safe challenge detection and approved identity verification |
| Unapproved console or IdP origin | Network/action remains blocked | Explicit exact-origin authorization before browser access |
| Legacy persona + authenticated execution | Normal API rejects configured authenticated execution outside Feature Cases | Integrate shared handoff lifecycle or clearly disable this combination |

The viewer's local configuration is now present and API/worker keys match; the
missing configuration from earlier sessions is not the reason these two runs
created no requests. A working viewer does not imply all executors trigger it.

There is also an operator setup gap: `CreateTargetRequest` and the normal target
form create only the base origin. The inspected target routes provide creation
and reads but no additional-origin management endpoint. The run form accepts SSO
origins only if already authorized on the target. Therefore multi-origin/SSO setup
is not a complete ordinary-user workflow, despite backend support and fixture tests.

### Recommended implementation, in order

1. **Explain the block precisely.** Persist typed policy codes and sanitized denied
   origins; show frozen allowed scope, affected step, and next action. Use separate
   labels for scope approval needed, login needed, sensitive action approval,
   locator ambiguity, unsupported verification, and hard denial.
2. **Complete exact-origin setup/review.** Let an authorized operator explicitly
   review console and authentication-only IdP origins, with audit/versioning and
   renewed authorization where scope expands. Keep existing run snapshots immutable;
   create a new run for an expanded scope until a versioned scope amendment exists.
   Do not silently add wildcards or infer authorization from a shared parent domain.
3. **Unify handoff triggers across supported executors.** When a configured identity
   becomes unavailable or a safe authentication challenge is detected on an already
   authorized origin, quiesce capture, persist the request/checkpoint, and pause in
   the same context. Human performs login/MFA, releases, and the worker verifies
   the approved identity on the approved app origin before resuming. Unknown origins
   require scope review, not a login bypass. Keep generic recovery and auth reuse
   separate. Do not invent a role marker from untrusted page text.
4. **Make authentication modes explicit.** Public-only, authentication-required,
   and optional-auth need clear capabilities. Until optional-auth/persona wiring is
   implemented, show that limitation before Start. A separate console target with
   Feature Cases, `requires_auth=true`, a reviewed identity marker and explicitly
   authorized IdP origins is the smallest supported protected-testing route.
5. **Fix generated selectors and safe route assertions.** Prefer observed heading
   role/name for headings and scoped role/name for links. Do not change a frozen
   expectation after it fails or fall back to fuzzy matching. Add a versioned,
   explicit path/public-route oracle for non-secret navigation checks; preserve the
   full-URL privacy boundary instead of comparing stripped URLs as equal.
6. **Review intent classification separately.** Pure local probes show
   `View payment documentation`, `Invite API reference`, and `Remove filters` all
   hard-block under the current substring classifier. This is evidence of coarse
   intent classification, **not the cause of MT-000048's four blocks**. Evaluate
   role, link destination, form submission semantics and exact intended operation
   before classifying benign reading as a financial/destructive write. Retain hard
   denial for real prohibited actions and unsafe network destinations.

Research supports retaining explicit scope, secret-safe auth state, and safe resume:
[OWASP SSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
recommends allowlist-based validation and preventing redirect bypasses;
[Playwright authentication](https://playwright.dev/docs/auth) documents isolated
contexts, conditional state reuse, and the sensitivity of authentication state;
[LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
warns that resumed execution can repeat side effects. These principles fit the
existing MarketTwin architecture and do not require adopting another framework.

Acceptance checks for those changes: no dispatch to unapproved origins; approve
only exact domains under current authorization; IdP pages remain human-only;
same-context login/MFA/SSO and verified identity after Release; cancellation/expiry
cannot resume; duplicate Release cannot duplicate actions; persona/deep modes
advertise their real capabilities; ambiguous/inferred assertions cannot become
verified product findings. Test all with local synthetic accounts and origins.

This investigation changed documentation only. It did not alter target permissions,
weaken policies, rewrite either run, use credentials, call a model, or rerun the
external application. An independent reviewer agreed with the scope/authentication
separation and challenged unsupported conclusions about the Agent URL requests.

## Contents

1. [Coding completeness](#coding-completeness)
2. [Architecture and ownership](#architecture-and-ownership)
3. [State transitions and failure handling](#state-transitions-and-failure-handling)
4. [API and viewer contracts](#api-and-viewer-contracts)
5. [Database and migrations](#database-and-migrations)
6. [Local setup](#local-setup)
7. [Declared synthetic effects](#declared-effect-example)
8. [Manual end-to-end guide](#manual-end-to-end-guide)
9. [Verification and phase status](#phase-status-and-verification)
10. [Troubleshooting](#troubleshooting)
11. [Source and regression-test map](#source-and-regression-test-map)
12. [Known limits](#known-limits-and-verification-still-required)
13. [Original master plan](#appendix-a-original-master-plan)
14. [Historical test evidence](#appendix-b-historical-verification-evidence)
15. [Viewer transport decision](#appendix-c-historical-viewer-transport-review)
16. [Original baseline](#appendix-d-historical-baseline-reconciliation)

The current sections govern operational status. Appendices preserve original
requirements and historical evidence; their older checkpoint statements do not
supersede the current implementation/verification status.

## Coding completeness

The initial-pilot HITL feature code is implemented in the existing architecture.
H00-H12 acceptance/release verification is a separate, incomplete status.

- Same-context browser takeover, exclusive expiring leases, authenticated REST
  decisions, signed worker handoff, generation fencing and restricted viewer.
- Verified login/role bootstrap before generated protected feature discovery;
  authentication-only SSO origins are authorized in advance and unavailable to
  agent requests. Password/OTP/CAPTCHA challenges prevent premature verification.
- Durable login/action suspensions and single-use approval receipts; cancellation,
  rejection, expiry and worker/browser interruption fail closed without replay.
- General Save/Create/Update/Publish/Submit approval dispatch. Eligibility requires
  exact user-declared action rules, an authorized nonproduction environment,
  synthetic data/reset confirmation, and a separate owner/admin decision.
  Destructive/payment/permission/messaging effects and opaque confirmations remain
  blocked. The existing local registration fixture retains its narrow exception.
- Approval hashes bind action/arguments, current page/form state, resource reference,
  requester, browser session/generation, target authorization, policy and expiry.
  The UI links the decision to the exact step and preceding safe evidence.
- Short-lived in-memory target/run/account/role-scoped authentication reuse in fresh
  contexts, per-case verification and fresh-HITL fallback for expired/stale state.
- Authenticated sessions disable raw Playwright traces and browser error payloads;
  screenshots mask inputs, editable fields, code/pre and marked sensitive content.
  Authenticated model observations omit raw ARIA page dumps and URL query/fragment.
- React run configuration, live browser control, approval/rejection, wait/resume
  states, and authenticated role/feature coverage with separate human contribution.
  Human waits are excluded from both case and run action budgets.

## Essential checks

### Current complete local integration (2026-10-15)

The real protected React/API/PostgreSQL/outbox/Kafka/execution/evaluation/report
pipeline passed, including login/MFA, fresh-ticket reconnect/Release, scoped
cross-case auth reuse, React approval/rejection, single actual target effect and
persisted report rendering. Results returned expected evaluation-pending409 then
200. Separate live boundary checks passed disconnected Release without reconnect,
cancellation, request expiry and lease expiry/reclaim with stale-input rejection.
Final focused backend85passed; real PG lifecycle/approval/reclaimed-lease test1
passed; final API contract11passed; pending/ready desktop/mobile UI8passed;
typecheck/build and scoped checks passed. Counts overlap.

Integration fixes cover stale deleted-run Kafka deliveries, successful claim
viewer availability, one current lease per listed request, privacy-safe close
and truthful expiry. No migration or new infrastructure was added. Exact run and
report IDs, test scope, files, limitations and startup instructions are in
[UI integration verification](../ui/VERIFICATION.md#end-to-end-integration-correction-2026-10-15).
The earlier correction and historical appendices below are retained as evidence.


### Integration correction against 0682c375

The focused correction fixes the disconnect/Release generation race. Closing a
viewer detaches transport while retaining the durable lease, human ownership and
current generation. Only an authorized database transition advances the fence.
Release validates the committed database generation, revokes live control and
signals the waiting worker even without a WebSocket. Authentication verification
still runs before agent control resumes. Exact duplicate notifications are
idempotent; stale, uncommitted and differently bound generations fail closed.
Late duplicates after completed verification do not revoke the resumed agent.

Reconnect obtains a fresh one-use ticket through authenticated POST
`/api/v1/human-actions/{request_id}/viewer` for the same unexpired actor, token,
request and generation. Transport sequences reset without changing the lease.
Expiry denies reconnect and Release; the existing reaper/reclaim path grants a
new generation. Release delivery failures return HTTP 503; an exact authorized
retry redelivers the committed revoke without advancing the fence twice. The UI
retains retry controls even if an in-flight heartbeat fails. HITL validation
errors omit raw invalid input, including submitted lease tokens.

Checks executed for this correction (overlapping suites; do not sum totals):

- Owner/viewer/workflow/lifecycle/worker/privacy focused suite: **35 passed**.
- Final worker, disconnect and strict owner-generation checks: **9 passed**.
- Local PostgreSQL/API-to-signed-worker/Playwright integration: **1 passed**,
  covering disconnected Release, active-viewer Release, fresh-ticket reconnect,
  expired lease/reclaim, delivery retry, duplicates and verified authentication/
  resume. Application-user authentication is stubbed with a synthetic actor;
  database authorization and the signed bridge are real.
- Disposable PostgreSQL migration test: **1 passed**. Actual full-chain upgrade,
  Alembic metadata check, final-migration downgrade/reupgrade and second check
  passed. Final combined database invocation: **2 passed**. Disposable test DB
  and schemas were removed; the application database was not migrated.
- API bridge/reaper and token-reflection canary checks: **8 passed**.
- Viewer UI reconnect tests: **2 passed**. Final frontend typecheck/build passed.
  Existing bundle-size warning remains.
- Strict Pyright: **0 errors** in affected backend production paths. Scoped Ruff
  passed with the existing E501 baseline excluded. `git diff --check` passed.

No migration or infrastructure service was added by that earlier correction.
Full synthetic UI/Kafka/evaluation/report integration subsequently passed above;
H12 release verification remains unexecuted.

### Exact files changed in this correction

- `apps/web/src/lib/api.ts`
- `apps/web/src/pages/runs/HumanActionPage.tsx`
- `apps/web/src/pages/runs/HumanBrowserViewer.test.tsx`
- `apps/web/src/pages/runs/HumanBrowserViewer.tsx`
- `docs/CURRENT_STATE.md`
- `docs/SESSION_HANDOFF.md`
- `docs/hitl/README.md`
- `services/control-api/src/markettwin_control_api/api/human_actions.py`
- `services/control-api/src/markettwin_control_api/persistence/repositories/human_action_repository.py`
- `services/control-api/tests/test_hitl_migrations.py`
- `services/control-api/tests/test_hitl_worker_client.py`
- `services/control-api/tests/test_human_action_repository.py`
- `services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/controller.py`
- `services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/owner.py`
- `services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/owner_registry.py`
- `services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/owner_service.py`
- `services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/viewer_authority.py`
- `services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/viewer_gateway.py`
- `services/execution-orchestrator/src/markettwin_execution_orchestrator/worker.py`
- `services/execution-orchestrator/tests/test_browser_owner.py`
- `services/execution-orchestrator/tests/test_viewer_gateway.py`
- `services/execution-orchestrator/tests/test_worker.py`

Earlier implementation evidence follows:

Focused workflow/API: 85 passed; browser/security: 45 passed; final rule/API/summary: 27 passed (overlap); PostgreSQL: 1 passed; fixture: 3 passed. Typing/build and offline migration rendering passed. The phase-status and verification sections below contain the consolidated evidence. No comprehensive
pipeline run, external app testing, benchmark, paid model call, push or deployment
was performed. Migrations were rendered offline; the application's existing DB
was not upgraded. Disposable PostgreSQL test schemas were created and removed.

## Architecture and ownership

| Component | Responsibility | Boundary |
| --- | --- | --- |
| React frontend | Run configuration, pending requests, protected canvas viewer, approval/rejection, role/feature coverage | Browser credentials belong only in the transient viewer; never in run notes |
| FastAPI Control API | Authenticate MarketTwin user, check workspace/target authorization, claim/renew/release/cancel, approval decisions | Does not own Chromium or expose a debugging endpoint |
| PostgreSQL | Durable requests, exclusive leases, fencing generations, suspension cursors and one-use receipts | Stores secret-free coordination metadata, not browser storage state |
| Kafka and outbox relay | Deliver durable run commands to the existing execution worker | Duplicate commands cannot authorize replay of a side effect |
| Execution worker | Own Playwright contexts, perform deterministic case steps, pause/resume and clean up interruptions | Single-worker pilot; live contexts are process-local |
| Restricted owner/gateway | Transient viewport frames and bounded human input for one live handle | Private internal CDP; no raw CDP/VNC endpoint to the browser client |
| In-memory auth broker | Reuse short-lived verified cookies/storage within matching run/target/role/account/origin scope | Not persisted to DB, Kafka, reports or ordinary artifacts |
| Evaluation worker | Verify recorded assertions/evidence and produce the existing report | Successful login is not evidence that a feature passed |

Generated protected discovery runs only after approved identity verification.
Frozen user-authored/fixture plans retain their existing validation path. Each case
uses its own context, verifies the expected role, and can request fresh human login
when transferable state is unavailable. A manual authentication prerequisite is
recorded separately from feature-case execution.

The transport decision is restricted CDP behind the signed worker bridge and
lease-bound WebSocket gateway. It reuses the existing Playwright-owned context;
it does not add a remote desktop stack. The full original comparison is preserved
in Appendix C. Performance/cost measurement and integrated acceptance were not run.

## State transitions and failure handling

| Event | Durable/browser behavior | Expected user outcome |
| --- | --- | --- |
| Authentication missing or step-up challenge visible | Create request and await human; stop agent input and capture before human entry | Awaiting human |
| Authorized claim | Acquire exclusive lease with actor, expiry and generation; attach exact live handle | Controlling browser |
| Lease renewal | Revalidate authority and extend only within allowed request lifetime | Viewer stays available while authorized |
| Release | Revoke human input, verify approved application identity/role, then consume the continuation | Verification followed by resuming, or blocked |
| Cancel/reject/expiry | End the request or approval and abandon its continuation | Blocked/cancelled; no assumed success |
| Eligible synthetic action | Persist exact approval request and pause before dispatch | Review exact step and preceding safe evidence |
| Approval consumed | Commit a single receipt before dispatch; recheck page/form fingerprint | One exact dispatch |
| Effect outcome unknown | Persist uncertain outcome; do not blindly retry | Operator investigation/new run required |
| Worker/browser lost | Cancel active handoffs, fence browser generation, abandon checkpoints; mark claimed effects uncertain | Failed/blocked instead of reconstructing a lost context |

Human waiting has a separate bounded allowance and is excluded from active case
and run action budgets. Live-browser loss is not crash-proof continuation. A
PostgreSQL browser UUID cannot recreate a Playwright context after process loss.

## Security controls

- MarketTwin user authentication and workspace/target authorization are checked
  separately from the tested application's login and role.
- One active control lease per browser; actor/generation/expiry and monotonically
  increasing input sequences prevent stale operator input from retaining control.
- Viewer tickets are one-use, expire within 30 seconds or the lease deadline, and
  are sent in the initial WebSocket message rather than a URL query string.
  Handshake time is bounded to five seconds and its payload to 512 bytes. The
  owner bounds input rate to 30 events per second. Authority is rechecked during
  streaming and input; ticket possession does not grant permanent access.
- The viewer uses approved origins, WSS outside the explicitly allowed loopback
  development path, and a private signed API-to-worker bridge. Raw CDP remains
  internal. HTTP mutation endpoints require the frontend request/CSRF checks.
- Credentials/OTPs are entered only by the human through the transient viewer.
  During handoff, agent tools, ordinary observations, screenshots, trace capture
  and browser error recording are fenced.
- After takeover, authenticated sessions do not resume raw Playwright traces or
  raw browser error payloads. Screenshots mask inputs, editable areas, code/pre
  and data-sensitive/data-secret regions. Authenticated observations omit raw
  ARIA dumps and remove URL query/fragment. These controls do not classify every
  possible app-specific secret rendered in arbitrary page content.
- SSO/IdP origins must be explicitly authorized on the target and declared as
  authentication-only. They are available to human authentication and blocked
  from normal agent navigation/inspection. The verified application origin is
  distinct from those authentication-only origins.
- Approval requires a declared synthetic effect and reset confirmation plus an
  independent owner/admin decision. The action hash and resource hash bind
  semantic target, scope, current page/form state, requester, browser generation,
  resource reference, target authorization, policy version and expiry.

## API and viewer contracts

These are application routes, not instructions to bypass authentication.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | /api/v1/test-runs/{run_id}/human-actions | List authorized run handoffs and states |
| POST | /api/v1/human-actions/{request_id}/claim | Claim exclusive browser control |
| POST | /api/v1/human-actions/{request_id}/renew | Renew the current authorized lease |
| POST | /api/v1/human-actions/{request_id}/viewer | Obtain a fresh reconnect ticket for the authorized lease |
| POST | /api/v1/human-actions/{request_id}/release | Revoke human input and request verification/resume |
| POST | /api/v1/human-actions/{request_id}/cancel | Cancel a handoff |
| GET | /api/v1/test-runs/{run_id}/action-approvals | List pending/approved exact-action requests and review links |
| POST | /api/v1/action-approvals/{approval_id}/decision | Approve once or reject |
| GET | /api/v1/test-runs/{run_id}/hitl-summary | Secret-free human contribution and authenticated coverage |
| WebSocket | /api/v1/hitl-viewer | Same-origin transient browser viewer |

Lease operations bind lease ID, secret lease token and generation to the current
authorized user/request. A release or Done interaction is never authentication
proof by itself. Worker verification must still pass the frozen policy.

The redesigned run navigation exposes Human Assistance and Evidence directly.
Owner/admin operators can claim and decide; other workspace roles see an explicit
operator-required message. In the live viewer, Tab/Shift+Tab navigate the tested
page; **Shift+Escape** returns focus to MarketTwin's keyboard-exit control, then
Tab can reach Release. Leaving keyboard control or closing the viewer does not
Release the lease. Lease grants remain local to the owning page and are excluded
from React Query mutation data/variables. UI redesign evidence and remaining
integrated checks are recorded in [UI verification](../ui/VERIFICATION.md).

## Database and migrations

| Durable record | Contents and purpose |
| --- | --- |
| testing.test_runs | Run lifecycle including awaiting_human, explicit approval opt-in and frozen configuration |
| execution.browser_sessions | Execution ownership, open/closed/failed state, control mode and fencing generation |
| execution.human_action_requests | Bounded login/handoff request, execution/browser linkage and terminal state |
| execution.human_control_leases | Actor, token hash, generation, expiry/release and exclusive browser control |
| execution.execution_suspensions | Secret-free continuation phase/cursor, deadlines, remaining active time and consumption count |
| execution.action_approval_requests | Exact action/resource fingerprints, authorized decision, expiry and browser generation |
| execution.action_approval_receipts | Single claimed/completed/uncertain dispatch receipt |

New HITL migration sequence:

1. c7a411f2b903: control fencing and durable suspension foundation.
2. d7f3c2a9b108: nonnegative browser/checkpoint generation constraints.
3. e8d4b7c1a620: action-bound approvals and non-replayable receipts.
4. a1b2c3d4e5f6: separately persisted synthetic fixture approval authority.
5. f82e4160cb9d: general run approval authority, awaiting_human status, cancellation,
   browser/session generation binding and approval-linked suspensions.

The final Alembic head is f82e4160cb9d. Offline SQL rendering and disposable PostgreSQL upgrade/check/downgrade/reupgrade checks passed. The existing
application DB was not upgraded by the coding session. Apply the migration before
running the new API/worker code; use normal backup/change procedures for any DB
whose contents you need to preserve. Disposable PostgreSQL test schemas were used
for transaction checks and removed afterward.

## Local setup

Use existing local dependencies and synthetic accounts. Do not replace .env.
The expected services are PostgreSQL, Kafka and MinIO, then API, execution worker,
evaluation worker and Vite. Existing local model/browser/storage configuration is
still needed for generated planning and evaluation.

1. Merge the HITL entries from .env.example into your local configuration. Keep
   APP_ENV=local. Set HITL_INTERNAL_SECRET and MARKETTWIN_HITL_INTERNAL_SECRET to
   the same newly generated local secret (at least 32 random bytes); do not use
   an account password or provider key. Keep the worker bound to 127.0.0.1:8020.
2. For the default frontend use MARKETTWIN_HITL_VIEWER_ORIGINS=http://localhost:5173,
   MARKETTWIN_HITL_VIEWER_URL=ws://localhost:5173/api/v1/hitl-viewer and
   VITE_HITL_VIEWER_PROXY_TARGET=http://127.0.0.1:8020. Origins and ports must match.
3. Use local-only Kafka settings for fixture/manual tests: KAFKA_BOOTSTRAP_SERVERS=localhost:9092,
   KAFKA_SECURITY_PROTOCOL=PLAINTEXT, and no cloud SASL credentials. Verify the
   effective broker host/protocol before starting API or workers; do not inherit
   a cloud broker from an existing .env. Keep that file private and merge settings
   deliberately rather than replacing it.
4. Set OUTBOX_RELAY_ENABLED=true for queued local execution. For isolated local
   verification set MARKETTWIN_OBSERVABILITY_ENABLED=false and
   MARKETTWIN_OBSERVABILITY_CAPTURE_CONTENT=false; configure telemetry separately
   before enabling it. Hosted use needs a reviewed HTTPS/WSS reverse proxy.
5. From the repository root, after local services are available:

```powershell
# Start existing local infrastructure only when needed.
docker compose --env-file .env -f infra/compose/docker-compose.yml up -d postgres kafka minio
# Apply the additive chain through 6b0e2ac784d1.
uv run --no-sync --env-file .env alembic -c database/alembic.ini upgrade head
uv run --no-sync --env-file .env alembic -c database/alembic.ini current
# In EACH API/worker terminal, explicitly override any remote .env broker:
$env:KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
$env:KAFKA_SECURITY_PROTOCOL = "PLAINTEXT"
# Separate terminals (repeat the two overrides above in each):
uv run --no-sync --env-file .env uvicorn markettwin_control_api.main:app --host 127.0.0.1 --port 8000
uv run --no-sync --env-file .env python -m markettwin_execution_orchestrator.worker
uv run --no-sync --env-file .env python -m markettwin_evaluation_worker.worker
npm --workspace @markettwin/web run dev
# Optional loopback synthetic protected fixture:
.venv/Scripts/python.exe -m http.server 5193 --bind 127.0.0.1 --directory services/execution-orchestrator/tests/fixtures/hitl_app
```

Use your configured API port if it differs from 8000. Vite reads CONTROL_API_PORT.
For these commands set CONTROL_API_PORT=8000 and WEB_ORIGIN=http://localhost:5173
in the existing local configuration. Do not run two execution consumers.

**Kafka scheduling limitation:** `run_worker` awaits the current `process_command`
before committing and receiving the next execution command. Pending human
assistance occupies the single execution consumer until resume, timeout,
cancellation or failure; later runs can remain queued. The API and viewer listener
can still respond. An event-driven worker regression confirms this behavior.
Extra execution consumers are not a supported workaround: multi-worker live
browser ownership/recovery is not implemented.

Retained commands referencing a genuinely missing run are now acknowledged
individually without browser execution; database lookup failures still retry.
No offset reset or topic deletion is needed for these stale disposable commands.
The normal execution group must use the same canonical database as the API and
outbox. Never start that group against a disposable or unrelated empty database.

## Declared effect example

For a Save button inside the fixture's Profile form, enter this JSON in the run's
synthetic effect rules field (use the exact observed accessible scope name):

```json
[{"category":"save","role":"button","name":"Save","scope_role":"form","scope_name":"Profile","resource_reference":"synthetic-profile-v1","test_data_reset_confirmed":true}]
```

A rule without a scope matches only an unscoped click. This is a declaration of
an approved synthetic effect, not a guarantee that arbitrary application code is
safe. Review the target and use dedicated test data with a reset contract.

## Manual end-to-end guide

1. Create/authorize a local target at
   http://127.0.0.1:5193/index.html?view=dashboard with requires_auth enabled and
   loopback network policy. Use the exact http://127.0.0.1:5193 allowed origin.
2. Create a deep feature run. Configure verification origin to that origin,
   selector #identity, exact marker Signed in as user, role user and a nonsecret
   account reference such as fixture-user. For admin testing use a separate run
   and admin-specific policy. Do not combine role state.
3. Start a run that checks the protected dashboard. Open Human assistance; confirm
   awaiting_human. Claim the viewer, connect, click Sign in, then enter only
   fixture-user / synthetic-password. Continue and enter synthetic OTP 246810.
4. Release control on the dashboard. Verify that the role check completes, human
   input stops, and protected discovery/case execution continues. A wrong account,
   unfinished challenge, or Cancel must leave the case blocked, never passed.
   Repeat Release in separate runs with the viewer still connected and after a
   brief network disconnect. Disconnect alone must not resume the agent. For a
   valid lease use Reconnect, check input, then Release; the original ticket is
   consumed and cannot reconnect. If Release reports delivery failure, restore
   worker connectivity and retry Release using the retained lease. For expiry,
   stop heartbeats, wait for expiry/reaping, then claim anew; stale controls must
   fail. Keep this test separate from the normal Release run.
5. Run several independent read-only protected cases. Check fresh contexts, correct
   role verification, authentication reuse counts and no repeated login when state
   transfers. Expire/logout to verify fresh-HITL fallback. Browser restart must
   fail closed; it does not reconstruct a lost context.
6. Test a declared synthetic Save effect with explicit safe data/reset prerequisites.
   Use the exact role/name/scope rule, inspect the pending step/evidence, approve
   once, and verify the effect. Repeat separately with Reject, expiry, changed
   form values and worker interruption. No old approval may authorize a new effect.
7. Test lease conflicts in a second tab, disconnect/reconnect, wrong role, stale
   generation, request cancellation and expiry. Check that human and agent input
   never overlap and no mutation is blindly retried.
8. For SSO testing, use an explicitly authorized local IdP/test app and configure
   its exact origin as authentication-only. It must work during human control and
   be denied to agent navigation/inspection after release. No external IdP was tested.
9. Let the evaluation worker finish. Reconcile planned/executed/asserted/blocked/
   not-run counts and human contribution. Authentication alone must not pass a case.
   Scan actual artifacts/logs/events/DB/Kafka/viewer telemetry for synthetic canaries.

## Known limits and verification still required

- Complete synthetic local UI -> API -> Kafka -> worker -> viewer -> resume ->
  evaluator/report passed. H12 hostile-path/release certification, production
  proxy/identity testing and the remaining live trials in UI verification are
  still required. HOSTED PRODUCTION NO-GO.
- Single execution worker; pending human assistance occupies its execution consumer
  and queues later runs. Human waits are bounded. A lost live browser fails
  closed rather than restoring passkeys or replaying actions. No horizontal-worker
  recovery or unrestricted parallel execution is claimed.
- In-memory auth state does not survive worker restart. Cookie/storage transfer
  depends on the app; nontransferable authentication falls back to human login.
- Hardware WebAuthn/OS prompts, real CAPTCHA providers and external SSO compatibility
  are unverified. The viewer intentionally exposes restricted browser input only.
- Browser-context separation does not isolate shared backend data. Resetting or
  assigning separate synthetic datasets/accounts is an explicit operator prerequisite.
- App secrets rendered outside masked/marked regions require target-specific review
  before using real data. This work used synthetic accounts only. No raw auth trace
  is retained; arbitrary page text cannot be certified secret-free by generic code.
- Feature inventory/coverage is bounded to the frozen approved scope and verified
  role. It is not proof of full application coverage or autonomous planning quality.
- Existing Vite chunk-size warning remains. Existing unrelated edits/deletions and
  historical compatibility code were preserved; no broad cleanup/reset was done.

## Phase status and verification

| Phase | Feature code | Verification |
| --- | --- | --- |
| H00 | Existing work reconciled and preserved | Shell recovery and git status confirmed |
| H01 | Synthetic protected login/MFA/role/profile fixture and independent truth | Final real-Chromium fixture 3 passed; exhaustive attack fixture matrix unexecuted |
| H02 | Additive leases, generations, suspensions, approvals/receipts and run opt-in | Disposable PostgreSQL binding/replay/cancel/interruption test passed; offline SQL rendered; one head f82e4160cb9d; application upgrade not applied |
| H03 | Human-phase fencing plus authenticated trace/error suppression, masks and bounded observations | Browser/privacy/viewer suite 45 passed; integrated all-sink canary scan remains |
| H04 | Same-context owner and restricted viewer transport | Focused owner/viewer security tests passed; full control-plane stream E2E remains |
| H05 | Authenticated REST control, React viewer, approval UI and exact-step review links | API tests, backend/frontend typing and build passed; full browser claim trial remains |
| H06 | Verified pre-discovery bootstrap, per-case checks, human-only SSO origins and challenge detection | Bootstrap ordering/failure tests, verifier and SSO isolation tests passed; external auth technology compatibility untested |
| H07 | Durable bounded pause/resume, timer accounting, fencing and no-replay worker cleanup | Focused workflow tests and real DB cancellation/interruption tests pass; full Kafka crash matrix remains; one worker only |
| H08 | Protected execution is wired to existing case/evaluator/report architecture | Integrated browser-to-report acceptance not executed; not an accepted/completed phase |
| H09 | In-memory scoped auth-state broker, fresh contexts and stale-state HITL fallback | Focused broker/verifier tests pass; complete multi-case pipeline remains |
| H10 | General exact declared synthetic-effect rules, reset prerequisites, decision/receipt/expiry/generation/page-state binding and dispatch | Final rule/API/summary 27 passed; real DB replay/stale-generation/cancellation test passed; full UI-to-effect E2E remains |
| H11 | Safe role/feature inventory/coverage and manual contribution UI | Focused coverage/authorization tests pass; fixture-to-final-report count reconciliation remains |
| H12 | Operational limitations/manual guide recorded | Comprehensive adversarial matrix, human security review, performance/release gates NOT EXECUTED; hosted production NO-GO |

Final check commands/results:
- Focused workflow/approval/worker/API suite: 85 passed, before last explicit-rule addition.
- Focused real-browser privacy/SSO/owner/viewer/broker/verifier/evidence suite: 45 passed.
- Final explicit-rule/API/coverage suite: 27 passed (overlaps the earlier suite).
- Final MARKETTWIN_TEST_DATABASE=1 local disposable-schema approval/lease test: 1 passed.
- Final synthetic fixture: 3 passed.
- Strict Pyright on full affected backend production paths: 0 errors; final rule/API paths rechecked: 0 errors.
- Frontend TypeScript and final production build passed. Earlier focused viewer/coverage UI: 3 passed. Existing Vite >500 kB warning remains.
- Ruff passes with the existing E501 baseline excluded; new import/unused/type findings corrected.
- Offline Alembic full-chain rendering passed; head f82e4160cb9d. One initial render found an overlong FK identifier; shortened before passing rerun.
- git diff --check passed. Tests use synthetic data and local resources only.

One transient reviewer usage-limit failure blocked an edit/check batch; it made no
changes. After the reset time, supported escalated execution worked again. Default
helper setup failures are infrastructure failures, not MarketTwin test failures.
No reviewer bypass, tree reset/cleanup, credential import, paid call, push or deploy.


## Troubleshooting

| Symptom | Check and safe action |
| --- | --- |
| Run stays queued | Confirm Kafka health, enabled outbox relay and the single execution consumer. Broker connectivity alone does not prove worker availability |
| Awaiting human but no viewer | Check matching API/worker internal secrets, worker listener, exact frontend Origin, viewer URL and Vite WebSocket proxy |
| Viewer disconnected | Use Reconnect while the lease is valid; it obtains a fresh ticket. Expiry requires reaping and a new claim. Disconnect does not release control |
| Viewer connection rejected | Check ticket/lease expiry, actor, generation and Origin; do not reuse consumed tickets |
| Release reports delivery failure | Restore worker connectivity and retry Release with the retained lease; exact retry redelivers the committed fence |
| Release does not resume | Confirm the expected application origin, unique visible marker and correct identity/role; finish any visible challenge and release on a reviewed safe page |
| SSO request blocked | Authorize the exact local IdP origin on the target and declare it authentication-only; do not broaden general agent authority |
| Sensitive action blocked | Check explicit run opt-in, nonproduction target, exact role/name/scope rule and reset confirmation. Empty rules intentionally authorize no effect |
| Approval becomes unusable | Form/page state, target authorization, browser generation, decision role or expiry may have changed. Reinspect; never force reuse of the old receipt |
| Later cases ask for login again | State may have expired, changed role or failed transfer. Fresh HITL is the supported fallback |
| Worker interrupted | Inspect failed/blocked run and uncertain receipts; do not replay the mutation. Start a separately authorized run after resolving test-data state |
| Report absent after execution | Confirm the evaluation worker is running and inspect its safe diagnostics; execution and evaluation are separate services |
| Shell fails even for Get-Date | Treat helper/setup failure as infrastructure failure. Use supported execution recovery; never reset/delete application source to fix a tool failure |

## Source and regression-test map

| Area | Main paths relative to repository root |
| --- | --- |
| Shared contracts | packages/shared-python/src/markettwin_shared/{auth_verification,action_approval,deep_testing,feature_plan}.py |
| Database schema | packages/database-python/src/markettwin_database/models/{execution,testing}.py and database/migrations/versions/ |
| Control plane | services/control-api/src/markettwin_control_api/api/{human_actions,hitl_summary,test_run}.py |
| API persistence/worker bridge | services/control-api/src/markettwin_control_api/persistence/repositories/{human_action_repository,action_approval_repository,test_run_repository}.py and services/{hitl_worker_client,human_action_reaper}.py |
| Browser security/viewer | services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/{controller,session,human_control,evidence,observations,owner,owner_registry,owner_service,viewer_authority,viewer_gateway,sensitive_action_policy}.py |
| Authentication reuse | Same browser package: auth_verifier.py and auth_session_broker.py |
| Durable continuation/approval | Execution persistence package: human_action_lifecycle_repository.py, suspension_repository.py, sensitive_action_approval.py, step_recorder.py and plan_repository.py |
| Worker/workflows | Execution worker.py and workflow/{auth_bootstrap,case_execution,deep_run,run_request,run_executor}.py |
| Frontend | apps/web/src/pages/runs/{HumanActionPage,HumanBrowserViewer,NewRunPage}.tsx, components/markettwin/FeatureCases.tsx, lib/api.ts and vite.config.ts |
| Local configuration | .env.example; actual local .env remains private |
| Backend regressions | services/execution-orchestrator/tests/ and services/control-api/tests/: focused auth, policy, ownership, viewer, workflow, cancellation, replay and coverage tests |
| Frontend regressions | HumanBrowserViewer.test.tsx and components/markettwin/FeatureCases.test.tsx |
| Synthetic fixture | services/execution-orchestrator/tests/fixtures/hitl_app/{index.html,ground_truth.json} |

Regression tests, independent fixtures and migrations are maintained source, not
temporary test outputs. They remain in the repository. The old fixture approval
compatibility module also remains because existing tests still exercise it.
Generated .local HITL debug/owner-trial artifacts are not required at runtime.

## Documentation maintenance

Update this file when HITL behavior, setup, evidence or release status changes.
Do not add another dated checkpoint or duplicate HITL handoff. The repository-wide
CURRENT_STATE.md and SESSION_HANDOFF.md remain continuity records and link here.
Unrelated project documentation remains unchanged.

## Appendix A: original master plan

Historical/design material follows. Current operational status is recorded above.

<details>
<summary>Expand the complete preserved reference</summary>

# MARKETTWIN — HITL, Authenticated Testing and Full-Application Readiness
## Implementation master plan and execution contract for GPT-6 coding agent

**Status:** Detailed engineering handoff; not an assertion that changes have been implemented.  
**Prepared:** 2026-10-14.  
**Repository:** `Sreenav14/Market-Twin`.  
**Audited branch:** `feat/batch-1-aws-observability`.  
**Verified remote HEAD at preparation:** `8075327a8a0681edaa0ac6d9273362c7eb65e264`.  
**Primary source of previous design:** `MARKETTWIN_HITL_V2_INDEPENDENT_ARCHITECTURE_AUDIT.md`; also read `MKT.md`, `AGENTS.md`, `docs/CURRENT_STATE.md` and `docs/agent-quality/IMPLEMENTATION_ROADMAP_2026-10.md` in the actual checkout.  
**Implementation language:** Python 3.12, TypeScript/React, PostgreSQL, FastAPI, Python Playwright, Google ADK, current Kafka/outbox infrastructure.  
**Intent:** Make MarketTwin capable of **safe human-assisted authentication**, **authenticated feature discovery**, **reliable case execution across protected screens**, **human approval for specifically authorized actions**, and **evidence-grounded reports**. Preserve existing work. No blanket rewrite.  
**Important:** This file is an executable *engineering specification* and acceptance contract. It does **not** prove local runtime quality or authorize a live target test, use of real secrets, purchases, cloud deployment, or pushing code.

---

# 0. FIRST INSTRUCTION TO THE IMPLEMENTING GPT-6 AGENT

You are the lead engineer implementing this specification in an **existing, actively developed repository**. Your job is not to copy the proposed examples mechanically. Inspect the real current code and choose the **smallest safe solution that satisfies each acceptance criterion**. The proposed file paths and contracts are implementation targets, not permission to overwrite existing compatible features.

1. Read `AGENTS.md`, `MKT.md`, `docs/CURRENT_STATE.md`, `docs/SESSION_HANDOFF.md`, and the current deep-testing roadmap. Check `git status --short`, actual branch, HEAD, recent history, existing migrations, fixture runners and tests **before editing**. Preserve all local uncommitted changes. Do not assume the HEAD SHA above is still current.
2. Produce a brief **reconciliation report** listing what is already implemented, what is partially implemented, what is absent, and any incompatibility between the plan and actual code. Label each claim `CODE VERIFIED`, `DOCUMENTED ONLY`, `EXPERIMENTAL`, or `UNVERIFIED`.
3. Work in **small dependency-ordered phases**, adding tests first or alongside implementation, validating each phase before the next. Parallel coding subagents, if available, may analyze independent files but **must not simultaneously edit shared execution-state contracts**. One integrator owns cross-module decisions.
4. Prefer existing Postgres, Kafka/outbox, FastAPI, ADK, Playwright, and auth/authorization helpers. **Do not add Redis, Temporal, Celery, LangGraph, hosted browser infrastructure, a new agent framework, or a generic event-sourcing platform** without a demonstrated gap and explicit approval.
5. Treat authorization, credential privacy, browser ownership, replay prevention and correctness as release blockers. Never loosen a safety rule simply to make a benchmark pass. No real passwords, session cookies, OTPs, recovery codes, PII, or authentication state in LLM input/output, Git, snapshots, Kafka events, browser traces, ordinary S3 artifacts, API errors or logs.
6. Tests must use controlled **synthetic** identities, synthetic OTP/MFA simulation, and an expressly authorized local fixture. Never attempt CAPTCHA bypass or unapproved third-party authentication, payment, destructive or production actions.
7. **No `git push`, AWS deployment, cloud spending, live external website tests, credential import, destructive migration or irreversible side effect** without explicit authorization. Do not invent benchmark measurements, GitHub CI status or release approval.
8. If exact same-browser HITL with credentials cannot be secured in the available runtime, **stop safely** and report the blocker. Do not substitute a fake second browser or call a user-entered "Done" button authentication proof.
9. Implement the full agreed capability incrementally, but **stop at architecture-changing or security-sensitive decision gates** (browser viewer technology, user identity provisioning, new infra spend, destructive migration). For normal code/test tasks, continue through the phase sequence after passing its gates; summarize results after each phase in `docs/CURRENT_STATE.md`.
10. Distinguish demo, pilot and production claims. A fixture green check does not establish security against a hostile browser page or readiness for unknown applications.

## Non-negotiable product outcome

A user authorizes a staging application and a specific test identity. MarketTwin reaches a protected page, detects authentication, stops agent input/capture safely, grants exactly one authorized human a short-lived takeover of **the SAME Playwright BrowserContext**, lets the human complete simulated or approved interactive authentication, revokes human input, verifies actual application identity/role through approved read-only checks, then conducts **real feature tests** while preserving exact evidence and without reusing risky actions. The user can see pending assistance, act, cancel and understand blocked outcomes. Subsequent isolated test cases can reuse **authorized short-lived authentication state** where supported without repeated manual logins. The result report never equates an AI claim with an independently verified product defect.

## Explicitly outside the initial pilot

Real credential collection; unrestricted remote desktops; bypassing MFA or CAPTCHA; third-party websites without authorization; arbitrary production transactions; full account administration; generic desktop computer control; browser restart restoring a live passkey session; unrestricted parallel browser testing; indefinite paused sessions; guaranteed crash-proof same-browser continuation; replacing existing evidence and testing engines; a visual redesign unrelated to HITL. These can only be considered under separately reviewed requirements.

---

# 1. VERIFIED REPOSITORY BASELINE (DO NOT REBUILD THESE)

All observations below are from the remote `8075327a` tree, not a fresh local runtime test. Recheck the actual checkout.

| Current file/location | Verified state and implication |
|---|---|
| `services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/controller.py` | `create_session()` starts a Chromium browser and fresh BrowserContext per journey; it sets service workers blocked and downloads disabled, and installs HTTP/WebSocket routing. `begin_human_control()` / `end_human_control()` already exist and accept browser-session/execution/journey identity. |
| `.../browser/session.py` | `JourneyBrowserSession` has session/execution/journey ownership, page, context, capture flag, action counter, `asyncio.Lock`, in-memory state. |
| `.../browser/human_control.py` | Stops tracing and disables capture during takeover; re-enables afterward. **Not sufficient by itself** because console, request-failure, page-error listeners remain active and viewer transport is absent. |
| `.../browser/evidence.py` | Playwright traces capture screenshots, DOM snapshots and sources; error files include accumulated browser logs. Must treat as possibly sensitive. |
| `.../browser/action_policy.py`, `policy.py`, `network.py` | Low-risk action checks, allowlisted origin and IP checks exist. They are not a complete policy for IdP origins or production side effects; DNS validation does not guarantee pinned network egress. |
| `packages/database-python/src/markettwin_database/models/execution.py` | `HumanActionRequest` and `HumanControlLease` tables already exist. `HumanActionRequest.browser_session_id` is **NOT NULL**; `HumanControlLease` has lease-token hash but lacks sufficient active-owner fencing. BrowserSession DB status check has `starting/open/closed/failed` while memory also supports `human_control`. |
| `packages/database-python/src/markettwin_database/models/testing.py` | TestRun state constraint permits `draft/planning/queued/running/completed/failed/cancelled`, not `awaiting_human`. |
| `.../persistence/run_state_repository.py` | Supports planning, running, completed, failed, and claim queued; no durable suspension/resume. |
| `.../workflow/journey_executor.py` | ADK `InMemoryRunner` inside bounded execution, with browser closed in `finally`. Plain return while waiting will not preserve session. |
| `.../workflow/case_execution.py` | Executes preplanned deterministic case actions; creates case-local session, bounded timeout, closes in `finally`. Needs an explicit suspension boundary and recorded action cursor. |
| `.../workflow/deep_run.py` | Creates a **temporary browser for discovery and closes it**, then creates **new sessions for cases**. An initial human login cannot automatically flow to them. |
| `.../workflow/run_request.py` | Persisted run uses 90-second default per journey. Human wait must be a separate deadline, not use this budget. |
| `.../worker.py` | Kafka message executes a full run before the consumer commits; duplicates of planning/running deliveries can mark a run failed. No durable resume command/owner. |
| `services/control-api/src/markettwin_control_api/api/` | No HITL API router in audited tree. Existing workspace/target/authorization security helpers should be reused. |
| `apps/web/src/pages/runs/HumanActionPage.tsx` | Placeholder; router already points to `runs/:runId/human-action`. |
| `database/migrations/versions/` | Actual Alembic migration location. **Not** `packages/database-python/alembic/versions`. Inspect current migration heads before making any migration. |
| `services/execution-orchestrator/pyproject.toml` | Pinned `google-adk==2.5.0`, `playwright==1.61.0`. Match installed API/version in code; do not paste unverified examples from newer docs. |
| `apps/web` | React + TypeScript; Playwright E2E, Vitest, existing auth and run UI. Do not rewrite. |

### Current code's key contradictions to repair

* One human-authenticated discovery context is **discarded** before case execution.
* `human_control` exists in memory but not in the `execution.browser_sessions` DB status constraint.
* `HumanActionRequest` requires browser ownership; a pre-run approval cannot use `browser_session_id = null` without an explicit migration or a **separate** contract.
* `Trace.capture_enabled=False` does not prevent application console text, failed request URLs, error events or viewer transport from handling secrets.
* An ordinary browser session may be closed in a `finally` block during a human pause.
* A single Kafka worker cannot remain blocked for unbounded human input without compromising delivery and recovery semantics.
* A per-case browser without storage-state bootstrap is not authenticated by a different context's login.
* Button-text filtering alone is not a sufficient server-side side-effect approval policy.
* A live account logged into staging is not necessarily an approved account for testing role-separated or state-changing cases.

### Code-reading order for the implementing agent

Start with `AGENTS.md`, `docs/CURRENT_STATE.md`, this spec, the V2 audit, then: `browser/{controller,session,human_control,evidence,contracts,errors,policy,network,action_policy}.py`; `workflow/{run_executor,run_request,deep_run,case_execution,journey_executor,test_case_planner}.py`; `persistence/{run_state_repository,execution_repository,run_event_repository}.py`; `worker.py`; ORM models; `control-api/api/{test_run,target_authorizations,auth,dependencies,permissions}.py`; current router, `HumanActionPage`, `FeatureCases`, `RunActivityPage`; test fixtures; Alembic; Docker Compose and infra. Limit reads to touched areas; use targeted searches thereafter.

---

# 2. ARCHITECTURAL DECISION RECORDS (ACCEPT / TEST / DEFER)

## ADR-H01 — One deterministic HITL coordinator, not an authentication LLM

**Accept.** Human assistance and approvals must be decided by deterministic policy and access control. The LLM may emit a typed **request for assistance**; it must never grant a lease, select an approver, read credentials, define its own origins or override a ban. Reuse your existing ADK for planning/execution, not for security authorization.

## ADR-H02 — Authentication before protected feature discovery

**Accept; blocking.** In a protected application, inspect the public landing/login state without asserting feature coverage, then perform authorized authentication bootstrap, then discover protected features and create cases. If authentication fails or cannot be verified, mark protected coverage `blocked_auth`, not `passed`, and do not claim full application discovery.

## ADR-H03 — Same browser for interactive takeover

**Accept; blocking.** A human must control the same `BrowserContext` and page(s) the engine intends to resume. A second tab in the human's ordinary browser is **not** equivalent. Browser owner must persist through the human wait for the pilot. Cross-process browser reattachment is not guaranteed just because its ID exists in Postgres.

## ADR-H04 — Human waiting is a durable state, not a 90-second tool timeout

**Accept; blocking.** Separate `active_execution_deadline` and `assistance_deadline`. Suspend at safe execution boundaries, record a checkpoint, return control to scheduler/worker, and resume from a validated checkpoint without replaying side effects. During a first local *viewer spike only*, an in-process wait is acceptable with explicit limits and documented crash loss; **do not ship it as complete durability**.

## ADR-H05 — Pilot browser-owner abstraction; avoid premature microservices

**Accept interface first, deployment later.** Create a small `BrowserOwner`/`BrowserSessionOwner` boundary that exclusively owns Playwright BrowserContext and viewer input. In an initial synthetic fixture pilot the existing process can implement the interface. For an actually durable asynchronous wait, a **separately supervised, addressable browser owner process** is necessary to prevent a Kafka execution task from blocking while human input is pending. That does NOT require Redis or a new orchestration product. Use existing Postgres + Kafka/outbox to track control plane; add small internal owner RPC only after local proof.

Do not claim browser-process-crash survival. If browser owner dies, invalidate active lease/auth context, mark `browser_lost` and require a new safe session/authentication; never replay uncertain actions.

## ADR-H06 — Browser viewer transport: measured spike, not premature permanent choice

**PILOT DECISION GATE.** Compare isolated **headful Chromium + noVNC/websockify** with a restricted **CDP screencast/input gateway** under the same threat/latency/functionality tests. Prefer the simplest that demonstrably enforces exact-session control, viewer authorization, no persisted credential frames, keyboard/input correctness and network isolation. noVNC streams a whole desktop and is less restricted by default; CDP may have smaller UI authority but needs protocol engineering and a robust input fence. The repository does not validate either today.

Initial local proof may choose noVNC to reduce development time if it runs in one disposable container/display and raw VNC/CDP is bound to loopback/private network. **Do not declare the production winner before tests.** Never expose raw VNC, CDP, Chrome debugging or a generic shell publicly.

## ADR-H07 — REST control plane + tightly controlled WSS viewer

**Accept.** Preserve existing FastAPI REST endpoints and API Gateway REST direction for commands, claims, approvals and status. An interactive remote browser requires a streaming/duplex transport; use a separately authenticated **WSS viewer channel** (or measured equivalent). This does **not** replace REST with WebSockets for core business operations. On AWS, select a suitable authenticated gateway based on real binary/latency requirements; don't assume REST API Gateway can directly proxy an interactive VNC stream.

## ADR-H08 — Conditional HITL, synthetic accounts, no general privileged credentials

**Accept.** Preferred: dedicated staging/test account (least privilege). HITL for login, MFA, CAPTCHA and similarly necessary manual prerequisites. Consent for a particular synthetic side effect can be separately requested. Human completing SSO does not imply authorization for all actions.

## ADR-H09 — Auth reuse is conditional and security sensitive

**Accept with verification.** Reuse short-lived, appropriately scoped Playwright `storage_state` across isolated case contexts *only* for a dedicated test identity when the application supports it. State can contain impersonation-capable cookies, local storage, IndexedDB and, depending on capture options/version, sensitive credentials. NEVER persist to report/RunEvent/S3 evidence or model context. Prefer in-memory sealed handles during one run; use encrypted ephemeral storage only when process boundaries demand it. Session-storage-only apps and device-bound SSO can require same-context fallback or repeated HITL.

## ADR-H10 — Approvals bind to exact authorized action; no blanket override

**Accept.** A human approval is narrow, expiring, single-use, bound to environment + identity + resource + action + normalized arguments + risk + worker generation. An approval never overrides hard-deny categories, unapproved origin or production safety constraints.

## ADR-H11 — Accurate reporting and evidence preservation

**Accept.** Human-controlled credential entry is **not** captured as ordinary agent evidence. Record only safe audit metadata: who took control, purpose, time, outcome, auth/role verifier ID and later assertions. Pre- and post-HITL trace segments remain separate; no secret-bearing middle trace. Human approval is not evidence that the tested feature worked.

## ADR-H12 — Incremental enterprise design rather than V1 re-platforming

**Accept.** Build around existing tables and interfaces; additive migrations only where needed, no duplicate auth management stack. Keep one worker at first. Do not conflate current functional pilot with availability, high-availability, multi-tenant production hardening or guaranteed full application test coverage.

---

# 3. THREAT MODEL AND SECURITY CONTRACT

## Protected assets

1. Customer/test account passwords, OTP/MFA codes, WebAuthn/private credentials, recovery codes and API secrets.
2. Browser authentication state (cookies, local storage, IndexedDB, session storage), CSRF tokens, implicit access tokens.
3. Human viewer control authority, live pixels, keystrokes and clipboard.
4. Customer app data visible after login, including potentially personal information.
5. Run/tenant ownership, target allowlist, test authorization, human approvals and audit events.
6. Evidence/artifacts, agent prompts, telemetry, Kafka messages, DB JSONB and S3 object storage.
7. Worker/browser processes and local/network environment.

## Trust boundaries

A. Customer application content **is untrusted**, including text instructions in HTML and console messages; never treat it as MarketTwin operational authority.  
B. LLM output is untrusted proposal, not an authorization token.  
C. Authenticated MarketTwin UI session is insufficient alone for browser control; the actor needs per-run/per-session eligibility and an active lease.  
D. Browser owner process is a privileged sandbox boundary; remote viewer has limited input, never direct shell/OS or raw CDP.  
E. Authenticated browser state is a secret that must be protected independently from test evidence.  
F. Cross-tenant access is forbidden even with guessed UUIDs or expired links.  
G. Network policy must apply to **all** browser traffic, including redirects, iframes, popups, sockets and human-phase SSO.

## Required risk controls

| Threat | Required technical control | Mandatory test |
|---|---|---|
| Second human tries to claim | Transactional active lease + generation + actor authorization | Concurrent claims: exactly one winner |
| Agent calls tools while human types | Quiesce and fence tools before enabling human input | Agent tool rejected during lease |
| Delayed human input after resume | Fence generation checked by viewer owner for each event | Revoked/expired lease event rejected |
| Credential leak to trace | Stop tracing before display/input, preserve separate segments | Synthetic marker absent from all generated artifacts |
| Credential leak to console logs | Gate/clear buffers and redact all event sinks during sensitive phase | Forced console/network error cannot leak marker |
| Credential leak via viewer | Frames are transient and not recorded/forwarded to LLM; WSS authenticated | No stored frame/key event artifacts |
| CSWSH against WSS | Origin allowlist, CSRF where applicable, revalidate session + per-message lease | Cross-origin connection rejected |
| Cross-tenant takeover | Resource ownership checked on every REST/WS call | Foreign workspace/run ID -> 404/403 |
| Session token replay | CSPRNG token, hash at rest, expiry, single active lease, no query token | Old token rejected after release |
| Prompt injection in app | No DOM instructions used for privilege/approval/origin decisions | Malicious page cannot request unsafe privilege |
| Redirect to internal/private host | Target/IdP policy + network egress controls | Internal redirect/WebSocket blocked |
| DNS rebinding | Egress-level restriction/pinning strategy verified, not only preflight DNS | Host resolves public then private -> blocked |
| Unknown side effect after timeout | Record uncertain outcome, read-only reconciliation; no auto retry | Submit counted at most once |
| Browser crash during HITL | Revoke lease, owner lost, mark blocked/reauth; no auto resume | Kill browser owner, no stale input accepted |
| MFA/SSO on unapproved IdP | Preapproved auth-only origin; don't auto-extend allowlist | Unknown IdP destination denied |
| Unauthorized approval | Explicit role/delegate + action fingerprint/expiry/version | Replay/different action rejected |
| Cross-role auth reuse | Per-role, per-target, per-run scoped sealed state | Admin state inaccessible to user cases |
| Long-running resource leak | Timeouts, connection limits, browser owner reaper | Lease expiry closes viewer and cleans up |

## Mandatory data-handling posture

* Don't capture or retain key strokes, login form values, MFA code pixels, clipboard contents, unredacted URLs with credentials, HTTP request bodies/headers, auth tokens, raw cookies or hidden credential fields.
* Disabling Playwright tracing alone does not meet the requirement: UI viewer frame capture, console logs, request-failure URLs, page errors, access logs, APM spans, model observations and exceptions must be covered.
* Keep sensitive phase **transient**. The viewer necessarily handles pixels to display the login form; those pixels are allowed to travel only through the authenticated volatile channel to the intended human, not to storage or LLM.
* After human release, inspect only an allowlisted, read-only, application-specific auth/role proof. Avoid sending authenticated pages with sensitive customer PII to the AI before policy checks/redaction.
* If a source page logs secrets itself, MarketTwin must not mirror those logs into lasting artifacts. Prefer suppressing entire event categories during takeover rather than trying to sanitize arbitrary strings perfectly.
* Encrypt/authenticate ephemeral auth state at rest if any is persisted; use a short TTL, strict object/account metadata, binding to run and role, revocation and delete-on-completion. Only the browser owner/auth broker may decode it.
* Audit metadata **without secrets**: run, target, request, actor, reason, attempt number, lease generation, decision, verifier, timestamps. Retention policy should be documented and tested.
* Configure safe defaults for browser UI channels: no file upload/download, no arbitrary URL entry in viewer if not needed, no unapproved clipboard sync, no password autofill from host, no Chrome settings/devtools/shell, one isolated OS user/container per browser owner for multi-tenant hosted use.

---

# 4. TARGET V1 COMPONENTS AND OWNERSHIP

```text
USER (authenticated MarketTwin, authorized for selected workspace/target)
    |
    | HTTPS REST: configure / request status / claim / release / approve / cancel
    v
CONTROL API (existing FastAPI + auth + workspace/target policies)
    |                    |
    | transaction        | WSS grant (session-bound + short TTL)
    v                    v
POSTGRES               VIEWER GATEWAY (one leased actor, frame/input policy)
    |                    |
    | RunEvent, leases   | private capability, fenced by generation
    |                    v
    |               BROWSER OWNER (same Playwright BrowserContext)
    |                    ^
    v                    |
KAFKA / OUTBOX ----------+
    |
    v
EXECUTION ORCHESTRATOR (existing planner/case executor/ADK)
    |               |
    | request HITL  | after resume: no secret-bearing content
    +-------------->HITL COORDINATOR (deterministic policy)
                         |
                         v
                  AUTH VERIFIER (read-only, approved)
                         |
                         v
                  AUTH CONTEXT BROKER (optional short-lived state)
                         |
                         v
                  ISOLATED FEATURE-CASE CONTEXTS
                         |
                         v
                EVALUATION + REPORT (existing, evidence-grounded)
```

### Responsibility boundaries (minimal modules)

**HITL coordinator**: validates request and reason, database state machine, actor eligibility, claim/release/expiry, audit events, idempotency, no browser rendering. Build in existing Control API/service packages, not as an LLM agent.

**Browser owner**: sole process/object allowed to call Playwright input methods, knows session/control generation, guards every input, stops/resumes evidence capture, monitors browser liveness; exposes only narrowly scoped internal methods. First pilot uses existing Controller behind an adapter; durable V1 requires a supervised owner that lives through worker suspension.

**Viewer gateway**: streams sanitized transient image frames and forwards validated human input to browser owner; cannot change target policy or access other sessions. External WSS protected by MarketTwin login, claim and session-bound short grant. No raw transport port public. Viewer transport is a decision gate.

**Auth verifier**: checks allowed app origin + approved application-defined, read-only login/role proof (e.g., known heading, account menu, read-only identity endpoint permitted by target config). Does not infer authentication from a human's 'Done' signal. Exposes safe boolean/evidence metadata, not tokens.

**Auth context broker**: optional per-run and per-role secret reference. Captures `storage_state` only on explicit policy, encrypts/isolates it, tests reuse on a fresh context, binds lifetime to run; can fall back to same-context execution. Browser owner is the only consumer.

**Approval policy**: evaluates action risk and environment, creates a normalized fingerprint of one approved action and enforces one-time consumption. Browser clicks still pass normal origin/policy checks. Do not try to infer a risky server-side mutation from arbitrary button text alone.

**Run scheduler**: existing DB/Kafka worker gains pause/checkpoint and resume command logic. No indefinite active Kafka consumer call. Never retry uncertain side effects merely because a message was redelivered.

---

# 5. SEPARATE THE THREE HITL WORKFLOWS

## 5A. Browser takeover for login, SSO, MFA, CAPTCHA

Trigger: target policy `requires_auth`, explicit authenticated case precondition, or clearly recognized login redirect/challenge. Agent may request assistance; policy decides whether to initiate. User must be an authorized owner/admin or explicitly designated operator for the target; **ordinary workspace write permission is not enough for privileged takeover**.

Sequence: create/persist a real browser session -> quiesce agent -> stop tracing and all persistence sources -> persist request and suspension cursor -> issue short-lived claim -> human connects via viewer to **same context** -> human types secrets -> human signals completion -> revoke viewer input **before** verification -> read-only auth/role check -> resume agent and tracing only after proof/sanitization -> store limited audit metadata.

If denied, expired, abandoned, unknown IdP, invalid role or browser lost: terminal blocked/inconclusive branch. Never automatically retry login with saved user secrets.

## 5B. Human approval of one action (no browser takeover required)

Trigger: policy classifies an action as approval-eligible and the target/environment permits it. Prefer synthetic staging data. A request contains human-readable **specific** operation, effect, resource and expiry but no sensitive payload.

Sequence: construct normalized action intent and idempotency key -> check target risk policy -> persist request -> human explicitly approve/deny -> validate current version/fingerprint/authorization -> consume approval once within transaction -> executor performs exactly that permitted action once -> record result. If effect is ambiguous, stop/reconcile rather than automatically repeating.

Never treat “Approve” as an override for destructive production, payment, personal messaging, privilege escalation, data exfiltration, or unknown actions. When uncertain, block or transfer limited control to a trained operator in an authorized sandbox.

## 5C. Pre-run test account and approved test data setup

User selects environment, test account role, disposable dataset, allowed origins (including separately reviewed IdP domains), authentication verification contract, consent and permitted action classes. Credentials are provisioned through an appropriate secret/identity path, not stored in test briefs or passed to the model. Initial pilot can use manual synthetic login; later use test-account authentication bootstrap where target policies allow it.

Keep pre-run setup distinct from `HumanActionRequest`, which currently **requires** a `browser_session_id` and `execution_id`. Introduce a small account/setup profile contract or reference, not a nullable fake browser session.

---

# 6. STATE MACHINES AND SAFETY INVARIANTS

## 6A. Browser input ownership

```text
CREATED
  -> AGENT_CONTROL
  -> QUIESCING             (deny new agent calls; drain one in-flight call)
  -> HUMAN_PENDING         (tracing/log sinks disabled; no human lease yet)
  -> HUMAN_CONTROL         (exactly one live lease, browser owner accepts human input)
  -> REVOKING              (deny viewer immediately, drain/reject queued events)
  -> AUTH_VERIFYING        (safe, read-only; no model tools, no viewer input)
      -> AGENT_CONTROL     (if verified expected account/role)
      -> HUMAN_PENDING     (if retry explicitly allowed and within deadline)
      -> BLOCKED/CLOSED    (denied/expired/failed/lost)
```

Guarded invariants:

* `agent_input_enabled XOR human_input_enabled` (both may be false, never both true).
* All input carries `browser_session_id`, `execution_id`, `owner_generation`, actor and lease; browser owner validates generation/expiry/authorization **per event**.
* Human takeover requires **actual browser session** persistence first; `request_type` is controlled by policy.
* `stop_trace()` and disabling **all** sink capture must finish **before** issuing viewer input token.
* Human release revokes input **before** post-login inspection or returning agent ownership.
* No restart of trace in the middle of an unverified login page.
* Browser loss/fencing mismatch is terminal `browser_lost`/`interrupted`, never fake “passed”.

## 6B. TestRun and execution states

```text
draft -> queued -> planning -> running -> completed
                    |           |
                    +-----------+----> awaiting_human
                                       |  |
                                verified  expired/denied/cancelled
                                       |  |
                                    running blocked/inconclusive or cancelled

running/awaiting_human + owner_lost -> interrupted/reauth_required, NOT silent replay
```

Proposed states must match **all** of: SQL check constraints, ORM literals, `RunStateRepository`, worker claim/retry, run APIs, frontend status typing, polling, activity, cancellation, evaluation readiness and metrics. Designate `awaiting_human` as **nonterminal**. Decide whether `interrupted` is a terminal run status or diagnostic + `failed` based on current product contract; do not add a state without checking existing consumers.

**Prefer a persisted `RunSuspension`/`ExecutionCheckpoint` record** for the exact paused case/step, and only add `awaiting_human` to statuses where needed. Existing `AgentExecution`/`BrowserSession` checks must be aligned or an explicit separate owner/suspension status introduced. Do not write memory-only state while Postgres claims the browser is `open` and agent-driven.

## 6C. Human request/lease

```text
REQUEST: pending -> leased -> completed
         |          |           
         +----------+-----> cancelled / denied / expired / browser_lost

LEASE: created -> active -> released / expired / revoked
```

No permission escalation on claim; a request can have at most one **active** lease. Re-acquisition advances a monotonic `generation`; all previously issued grants are rejected. Absolute expiry is separate from renewable short heartbeat/lease. Limit attempts and total human-wait time.

## 6D. Action approval

```text
proposed -> waiting -> approved -> consumed -> executed
                     \-> denied/expired/cancelled
approved + changed action/version -> INVALIDATED, never executed
```

Action approval is logically different from browser input control. Use a separate table/contract or an explicit discriminator with check constraints that do not break existing `HumanActionRequest` non-null keys. Do not repurpose the “login” status semantics for approvals.

---
# 7. DATA MODELS, MIGRATIONS, TRANSACTIONS AND CONSISTENCY

## 7.1 Scope of additive DB work

Implementing agent: first examine **actual migration head** under `database/migrations/versions/`, related model imports, SQL constraints, cascade paths, existing type-checks and tests. Never assume an empty database. Use Alembic `upgrade` and a tested rollback/downgrade where appropriate. Do not silently replace or delete existing HumanAction tables.

**Recommended minimal target schema, logical fields (not an instruction to create every table blindly):**

### Existing `execution.browser_sessions`: extend coherently

* Current identity `id`, `execution_id`, browser type/state, timestamps; preserve foreign keys.
* Persist `control_state` or extend `state` to include `agent_control`, `quiescing`, `human_pending`, `human_control`, `verifying` as justified by existing contracts. **Do not confuse browser liveness with control mode**. Cleanest option if migration is small: retain `state` for *liveness* (`starting/open/closed/failed`) and add separate `control_mode` ENUM/check: `agent/human_pending/human/verifying/none`. Existing tests/clients must see a consistent projection.
* Add `control_generation BIGINT NOT NULL DEFAULT 0`, increment atomically at every ownership change.
* Add `owner_id`/`owner_heartbeat_at` only if cross-process browser owner is introduced in this phase; no fake owner ID for an in-process spike.
* Maintain `one browser session per execution` invariant unless explicit authored cases require alternatives. Do not break existing uniqueness accidentally.

### Existing `execution.human_action_requests`: preserve ownership

Current `execution_id` and `browser_session_id` are required and the request types are `login/password/mfa/captcha/other`; statuses `pending/leased/completed/cancelled/expired`. Preserve them for **browser-bound human takeover**. Do **not** put a pre-run request with null browser ID into this table without an intentional compatibility migration.

Add only truly required fields:

* Safe reason code + request-kind or keep `request_type` for browser takeover.
* `request_expires_at` (if existing `expires_at` sufficient, reuse).
* `requested_role` (opaque approved test-role identifier; no role secret).
* `created_by_actor_id`/`delegate_id` if actor policy demands it; appropriate constraints.
* `resume_checkpoint_id`, expected `browser_generation`, `auth_verifier_id`, last decision metadata or separate linked table; favor JSONB **only for nonsensitive versioned metadata** if a small column set is unwarranted.
* `denied`/`browser_lost` reason can be a typed terminal reason associated with existing `cancelled`/`expired` rather than multiplying status values. Choose one consistent versioned event contract and document translation.

### Existing `execution.human_control_leases`: enforce exclusivity

Current fields include `request_id`, `browser_session_id`, `user_id`, `lease_token_hash`, `acquired_at`, `expires_at`, `released_at`.

Add `generation` (must match the browser's current generation) and optional `revoke_reason`; unique or partial unique index to ensure **at most one unreleased lease per browser**. Suggested Postgres index:

```sql
-- Illustration. Match the actual schema/constraint migration and backfill.
CREATE UNIQUE INDEX uq_active_human_lease_per_browser
ON execution.human_control_leases (browser_session_id)
WHERE released_at IS NULL;
```

**Important:** Expired rows still have `released_at IS NULL` until a transaction/reaper marks them released. On claim, lock browser + pending request, release any expired previous lease, increment generation, insert new lease in **one transaction**. A predicate like `expires_at > now()` must not be used as the sole dynamic partial-unique condition; it is not a reliable exclusion invariant.

### Separate action approval (new logical contract)

Do not overload `HumanActionRequest` with a nullable browser ID for pre-run approvals. If supported only for in-browser queued actions, a separately keyed `human_action_approvals` table is clearer, with:

```
approval_id UUID
run_id UUID; journey_id UUID?; execution_id UUID?; browser_session_id UUID?
actor_id UUID; requested_by_step_id BIGINT?
action_fingerprint TEXT; action_category TEXT; resource_id TEXT?
policy_version TEXT; environment TEXT; requested_role TEXT?
status proposed|pending|approved|denied|expired|consumed|cancelled
request_created_at; expires_at; decided_at; consumed_at
idempotency_key TEXT; decision_generation BIGINT
safe_display JSONB (allowlisted fields ONLY)
```

If you can satisfy the same invariant by adding an explicit discriminator and constraints to the existing tables **without** undermining their foreign keys or security, justify that alternative in an ADR. Do not create a table simply because one is shown here.

### Durable execution suspension and resume cursor

Use a small `ExecutionSuspension`/`RunCheckpoint` record or versioned, immutable RunEvent + authoritative run state if simpler, containing:

```
checkpoint_id
run_id / case_id / journey_id / execution_id / browser_session_id
checkpoint_version; controller_generation; owner_id
phase (auth_preflight | case_action | assertion | etc.)
planned_step_index; last_durable_step_id; last_completed_action_receipt_id
pending_human_request_id; auth_context_ref?  # opaque ID only
active_deadline_remaining_ms; suspended_at; human_deadline
resume_count; status waiting|ready|consumed|abandoned
last_update_version (CAS)
```

No raw action arguments with secrets; no full Playwright Page or Python coroutine serialization. A checkpoint is **the intended continuation point**, not a promise of replay-safe mutation. Side-effectful actions require their own durable receipts/reconciliation policy.

## 7.2 Transactions and concurrency

* Every claim/release/expire/cancel/approve uses a Postgres transaction with row locks or a conditional versioned update. A precondition must be checked inside the transaction; do not check eligibility once in the frontend and trust that result minutes later.
* Browser ownership/generation is authoritative at the **browser owner**. DB stores the policy state and generation; queued stale commands with lower generations are rejected by the live owner.
* The same person must not hold two concurrent input leases on one browser. Two different persons racing must produce exactly one winner. Old viewer connections die when generation changes.
* Request creation is idempotent by `(execution_id, suspend_cursor, reason_code, policy_version)` or an equivalent unique key; duplicate Kafka deliveries may not produce multiple pending prompts.
* Approvals are consumed atomically (approved → consumed with fingerprint/version/idempotency match) before dispatching the action, and the action executor must store an attempt/receipt and reject duplicate dispatch. If the effect is uncertain, reconcile rather than retry.
* Store event timestamps using UTC; use server-side absolute lease/request expiry and heartbeat with skew tolerance. Expiry does not automatically mean success or a product defect.
* Never hold an open SQL transaction across human wait, WebSocket activity, LLM calls, browser navigation or file upload.
* Ensure target authorization remains valid on claim **and** resume. If target authorization is revoked mid-session, force cancellation/revocation.
* DB status/parent-child foreign keys need version-compatible reads for old runs; preserve existing legacy reports and deep-test execution.

## 7.3 Data migration acceptance criteria

1. Upgrade from a real existing populated test DB works; no dropped data or foreign keys.
2. Existing pre-HITL runs can still load APIs and reports; old status mappings remain readable.
3. SQL enforces one active lease per browser; race test with two DB sessions passes.
4. `BrowserSession` open/closed state and control mode cannot contradict a live active lease without detection/reconciliation.
5. A stale generation cannot approve, release another actor's lease, or send browser input.
6. Migration tests prove documented downgrade behavior, or explicitly mark downgrade not supported and require backup/restore strategy before production.
7. `ruff`, `pyright`, pytest and app typecheck include updated schemas.

---

# 8. REST API AND REAL-TIME VIEWER PROTOCOL

The following route names are **proposed** and may be adjusted to fit existing API naming. Preserve existing workspace-run authorization checks. Return opaque IDs, sanitized metadata and no secrets.

## 8.1 REST endpoints

| Method / route | Actor | Purpose | Security and semantics |
|---|---|---|---|
| `GET /api/v1/test-runs/{run_id}/human-actions` | Authorized workspace reader, with sensitive fields restricted | List safe summaries, pending reason, status and TTL | Never disclose lease secrets or auth-state tokens; include only eligible operator names as policy permits |
| `GET /api/v1/test-runs/{run_id}/human-actions/{request_id}` | Owner/admin or assigned delegate | Read one assistance request | Check request/run/workspace ownership and expiration |
| `POST /api/v1/test-runs/{run_id}/human-actions/{request_id}/claim` | Eligible human operator | Atomically claim same browser for short TTL | CSRF, member eligibility, target authorization, active lease, current owner generation; `409` on conflict |
| `POST .../{request_id}/viewer-ticket` | Current lease holder | Issue short session-bound WSS viewer capability | One-time, short TTL, stored hashed, bound to actor + browser + generation; return only over HTTPS and not in URL query |
| `POST .../{request_id}/complete` | Current lease holder | Signal finished credential step | **Not proof of auth**; revoke viewer input and start server-side verifier |
| `POST .../{request_id}/cancel` | Operator/owner/admin as policy defines | End pending request safely | Revoke lease, terminate viewer, record reason, block/skip protected scope |
| `POST .../{request_id}/renew` | Current lease holder | Extend heartbeat if within absolute expiry | Never extend absolute maximum indiscriminately; rotate or validate version |
| `GET /api/v1/test-runs/{run_id}/auth-status` | Authorized viewer | Show verified/needs-human/blocked status for UI | Do not expose session state or customer identity beyond needed role |
| `POST /api/v1/test-runs/{run_id}/resume` | Scheduler/internal only, NOT arbitrary UI clients | Enqueue safe resume after verifier success | Internal identity, CAS checkpoint, idempotent; no free-form resume cursor |
| `GET /api/v1/test-runs/{run_id}/approvals` | Authorized role | List pending action decisions | Sanitized exact operation description |
| `POST .../approvals/{approval_id}/decision` | Specifically authorized approver | Approve/deny once | Exact action fingerprint, policy version, resource version, expiry, CSRF, no blanket grant |

Prefer `404` for foreign resources to avoid leaking existence; `401` for no authenticated MarketTwin session; `403` for visible but unauthorized action; `409` for owner/version conflict; `410` for expired/consumed; `422` for malformed inputs. Avoid returning sensitive internal browser state or URLs with tokens in error details. Apply appropriate request limits and audit events.

### Example safe claim response (illustrative)

```json
{
  "schema_version": 1,
  "request_id": "<opaque-id>",
  "run_id": "<opaque-id>",
  "status": "leased",
  "reason": "interactive_login_required",
  "browser_control": "human",
  "lease_expires_at": "<UTC timestamp>",
  "absolute_deadline": "<UTC timestamp>",
  "viewer_ticket_required": true,
  "instructions": "Sign in to the approved staging application. Do not paste credentials into MarketTwin chat."
}
```

No cookie, password, token or `storage_state` contents in JSON. Deliver any short-lived capability through the authenticated restricted endpoint; never log its raw bytes.

## 8.2 WSS viewer handshake, authorization and events

**WSS is for live viewer frames/input only**, not the general run-control API. Authenticated MarketTwin session + same-origin check + short viewer ticket tied to claimed actor/browser/generation are required. Send ticket in a constrained initial control frame or an appropriately restricted subprotocol after secure handshake; do not put it into query strings, browser history or logs. Consider browser limitations on custom WebSocket headers.

Example constrained application-level **control event** (not VNC raw bytes):

```json
{
  "schema_version": 1,
  "event": "input.pointer_click",
  "browser_session_id": "<opaque-id>",
  "generation": 7,
  "sequence": 45,
  "payload": {"x": 424, "y": 211, "button": "left"}
}
```

The gateway MUST validate: authenticated actor, same-origin handshake, live lease, current generation, browser ownership, monotonically increasing input sequence/idempotency, coordinate bounds, allowed input type, rate and size limits. A connection once authenticated must **not** be trusted forever. Input queued before revocation must be drained or rejected. Multiple sockets viewing may be allowed by policy only if **one** can input; simpler pilot: exactly one operator connection.

Supported initial input types: pointer click/move, bounded scroll, key press/release and text composition for human phase. For credentials, typed keystrokes go only to browser owner, **not to ordinary structured app logs or Kafka**. Avoid making a generic `type_text` API that exposes raw strings to the control API; if streaming input must carry characters, process transiently within viewer owner, never persist/log. Enforce browser navigation policy on resulting redirects and popup events.

Frames are volatile, access controlled, low-latency images; disable every recording option. If using noVNC, raw VNC access must be private to the isolated container/session and bridged through an authenticated gateway; no general-purpose browser desktop should be exposed outside the container.

### Recommended default security settings (tune by tests)

* Absolute human request deadline: 10 minutes for **synthetic pilot**; configurable per environment with upper bound.
* Viewer session grant: at most 60 seconds to initiate (shorter is fine).
* Lease heartbeat: every ~15–30 seconds; grace window bounded and tested.
* Max active input connection: 1 per browser.
* Max viewer input message: enforce small JSON bounds; non-image control frames far below 64 KB.
* WebSocket `Origin`: explicit allowlist only. `SameSite`, Secure and HttpOnly settings appropriate to deployment; CSRF for mutating REST calls.
* Host/browser idle timeout: tested, configurable, not hardcoded globally for nonpilot work.
* All limits are **starting design assumptions**, not empirical optima or published universal rules.

## 8.3 Frontend UX

Replace the placeholder `apps/web/src/pages/runs/HumanActionPage.tsx` with a focused read-only status and takeover/approval surface:

* Context header: application/target name, environment (prominent staging/production distinction), test name/run ID, reason, current run status, time remaining.
* Safe instructions: "You are controlling the isolated MarketTwin test browser. Enter credentials only into the application shown inside the secure viewer." Never display a MarketTwin password/OTP text field.
* Claim button visible **only for eligible actors**, but server repeats all eligibility checks; conflict explains another operator has control.
* Viewer component only after an active claim; shows connect/reconnect state without preserving frames/typed text to local storage. Disable screenshot/copy/record affordances in MarketTwin; cannot guarantee the user's OS cannot screenshot, so do not claim impossibility.
* "I'm done" signals a verification request; show `Verifying sign-in…`, then `Verified as approved test role`, `Still signed out`, `Incorrect role`, `Verification unavailable`, or `Expired`.
* Distinct "Cancel / stop test" path; never conflate network disconnect and test pass.
* Explicit human action approval card shows intended operation, test environment, resource, risk, time to expire and action-specific approve/deny; never a vague “approve all future actions.”
* Run overview/activity/journey pages show awaiting-human status, pause reason, and protected coverage blocked if unresolved. Logs do not reveal typed content.
* Keyboard accessible, screen-reader labels, visible timeouts, protected mobile state, clear errors, user-safe retry where allowed. No surprise auto-login attempts.

Add frontend TypeScript types to `apps/web/src/lib/api.ts` (or established API contracts) and focused unit/E2E tests. Do not bypass existing `RunLayout` permissions.

---

# 9. BROWSER OWNER, VIEWER AND PRIVACY ENGINEERING

## 9.1 BrowserController changes

**Refactor minimally**: introduce a controller-facing `BrowserOwner` protocol that calls existing `BrowserController` methods; do not recode locator, network policy, screenshots or session locking. Add:

* `quiesce_for_human(session_id, expected_execution_id, expected_generation, reason)` — block scheduling new agent operations, wait for known in-flight action to complete/abort safely, stop trace, suppress all event/capture sinks, clear sensitive buffers and set input authority to none.
* `begin_human_control(...)` — require valid lease/generation, verify trace OFF/sinks OFF, enable only owner-gated human input.
* `revoke_human_control(...)` — stop accepting viewer input immediately, advance/fence generation, clear in-flight input queue, enter verifying state.
* `read_auth_verifier(...)` — read-only approved check with target-origin constraints; no model prompt, no arbitrary JS from untrusted page or human.
* `resume_agent_control(...)` — only after auth proof + sanitized state; restore capture policy for safe protected pages, segment traces, leave human phase unrecorded.
* `mark_browser_lost(...)` — revoke viewer, invalidate auth context, mark blocked, run cleanup; no auto replay.

All direct action entry points (`navigate`, `click`, `fill`, `select`, `set_checked`, `scroll`, `go_back`, `wait`, `get_state`, screenshots, read_assertion`, and new owner input methods) must enforce the **same** current authority through the controller. Read-only model observation is forbidden during human input, even if it does not mutate state.

Potential race: `stop_trace()` may be asynchronous and a concurrent screenshot action may already be running. Hold one session input/capture lock across quiesce and state switch; never grant viewer before all collectors are stopped. Use generation at both DB and owner; don't equate an asyncio lock with cross-process fencing.

## 9.2 Fix all capture sinks, not only screenshots

Review each sink explicitly:

1. Playwright trace (screenshots/snapshots/sources), video, HAR, screenshot and accessibility text.
2. `BrowserEventBuffer`: console errors, page errors and failed requests (URLs/paths/query/body could be sensitive), cumulative buffers.
3. `browser/controller.py::_on_console`, `_on_request_failed`, popup `pageerror`, `dialog` handler, download listener.
4. `ExecutionStepRecorder`, session artifact writer, persisted observation summaries, action records.
5. ADK event history, prompts, tool arguments, model response previews, LiteLLM tracing, OpenTelemetry/OpenInference spans.
6. FastAPI access/exception logs, WebSocket server logs, reverse proxy/CDN/API Gateway logs, client error tracking/analytics, browser viewer gateway.
7. Kafka payloads/outbox events and retry/dead-letter pathways.
8. Developer console/devtools, browser storage/caches, crash dumps, temporary files, traces on failure.

**Implementation:** while control state is `human_pending/human/verifying`, no ordinary sink should receive page text, URLs with query strings, credential field values, frame bytes, input payloads, or auth storage. Allow only safe event code (`human_control.started`, `human_control.ended`, `auth_verification.result`), actor ID, stable opaque target ID and timestamps. Application errors during sensitive phase are **not** recorded as normal diagnostics. Purge preexisting event buffers at the boundary if they contain potentially sensitive login interactions. Resume capture only on an approved safe page and only after verification. Consider capturing no DOM on protected screens containing PII unless required and safe.

Privacy validation is **adversarial**: fixture emits synthetic `CANARY_PASSWORD_...` into page console, request failure URLs, DOM error messages and exception strings during login; scan all artifact files, DB dump of new records, Kafka captured envelopes, instrumentation mock sinks, frontend state/storage and viewer logs. Zero matches is required. Also test denial/timeout/error paths because cleanup paths commonly leak more than happy paths.

Note: using a *remote browser viewer* cannot mean nobody on the server has technical access to a human's credentials. OS/browser process memory and the target site necessarily handle them. State precisely that MarketTwin prevents **agent/model/log/evidence exposure**, provides host isolation and access limits; avoid impossible “credentials never touch MarketTwin infrastructure” claims.

## 9.3 Viewer spike: compare two alternatives under one fixture

**Option 1: headful Chromium + private VNC/noVNC**

* Strength: standard human-browser operation, keyboard/SSO coverage, potentially quickest prototype.
* Costs/risks: desktop-wide control; extra virtual display and VNC process; keyboard/clipboard/file picker surfaces; high video traffic; Docker/Linux requirement (user's Windows host needs Docker Desktop/WSL2 or equivalent); potential recording/proxy logs.
* Hardening: per-session isolated display/container/user, rootless or constrained container, disable clipboard and host file access, no public raw VNC/CDP port, private authenticated WSS bridge, egress restrictions, modest CPU/RAM budgets, teardown on timeout.

**Option 2: restricted CDP screencast/input bridge**

* Strength: possible browser-viewport-only UI; finer control over allowed input.
* Costs/risks: larger custom protocol surface, browser-version coupling, text composition/IME, keyboard shortcuts, popups, frame resize, cursor hit testing and input acknowledgement, potential app/session race.
* Hardening: browser owner only holds CDP; gateway exposes **no raw CDP methods** to user; server accepts only a small validated input protocol and streams frames transiently.

**Measurable selection rubric:** same-context login + MFA simulation; 0 secret artifact matches; no commands after lease revocation; input fidelity with form/keyboard/scroll; correct popup/SSO handling; browser memory/CPU; bandwidth/latency on local and remote client; recovery from disconnect; Windows development setup; maintainability and hosting cost. Capture written evidence. If neither passes security gates, stop; don't select a winner by preference.

## 9.4 Browser isolation, OS and network

* Pilot: bind viewer/browser internals to localhost or isolated Docker network, use synthetic fixture; protect browser owner behind authenticated API.
* Hosted: tenant/session isolation with per-owner OS/browser process, container egress deny-by-default apart from target and narrow IdP/resources, no privileged container, no host mounts or Docker socket, minimal env vars, memory/file limits, strict timeouts, cleanup.
* Browser route handlers must validate HTTP, HTTPS, WebSocket, redirects and subresources. Origin allowlist alone is not sufficient to prevent DNS rebinding or network pivot; use egress proxy/firewall where possible and **validate the actual destination**. If unavailable in V1 local-only, document as a production blocker rather than claiming SSRF-proof deployment.
* Disable downloads, file uploads and OS dialogs by default. Explicitly test passkeys/WebAuthn compatibility; some hardware-backed auth cannot be completed in a remote browser. Classify unsupported rather than faking pass.

---

# 10. AUTHENTICATION BOOTSTRAP AND ROLE-SAFE MULTI-CASE TESTING

## 10.1 New logical workflow

```text
Validate target, explicit owner consent and allowed origins
    ↓
Check `requires_auth` / approved account profile
    ↓
Create isolated browser context, navigate public entry
    ↓
If login required: HITL request -> verified same-context human login
    ↓
Verify approved application origin + actual test account/role
    ↓
Authenticated feature discovery (NOT before login)
    ↓
Freeze test plan, requirement provenance and coverage scope
    ↓
For each case:
    - fresh isolated context with authorized short-lived auth state IF supported;
    - otherwise safe same-context fallback or new HITL;
    - confirm auth and role preconditions;
    - execute and assert with existing evidence contracts;
    - never use a login failure as a product defect without a separate explicit oracle.
    ↓
Run evaluator, report protected coverage and any auth-related blocks
```

Do not conflate `requires_auth` with “permission to access all pages.” The target's `allowed_origins` and application role policy remain binding. When not authenticated, record which protected features were **not inspected**.

## 10.2 Auth verifier contract

Provide a **user-approved**, versioned configuration for known staging identity/role. At minimum:

```
AuthVerifierSpec v1:
  target_id; origin; verifier_id; version
  success_checks: [approved read-only URL / visible semantic locator / safe identity endpoint]
  expected_test_account_id? (opaque stable ID, no email if avoidable)
  expected_role (user/admin/etc.)
  logout/expired indicator (optional)
  safe_on_failure: true
  prerequisites: the same browser owner and authorized origin
```

A human pressing “Done” is **not** a verifier. A redirect to the home page is not enough if the page is public. Login must be proven through application-specific signals and role where possible. Never claim admin-role verification if the app only exposes a generic authenticated marker; classify role as `unknown` and don't execute admin test cases.

Disallow free-form model-authored JavaScript or unknown URLs as verifier definitions. Use existing safe semantic locator/URL checks or explicitly approved read-only target API. No arbitrary data extraction. The verifier must not navigate to customer personal documents merely to establish role.

## 10.3 `storage_state` broker (conditional)

**Source practice:** Playwright supports `BrowserContext.storage_state()` and creating new contexts using that state. The file/JSON may impersonate the test account; use an ephemeral encrypted state reference, not a normal artifact. `storage_state` does not automatically capture every app's sessionStorage/browser/device binding. IndexedDB capture is optional and should be turned on **only if necessary**. Playwright 1.61 includes WebAuthn credential-related capture options; never capture/export real passkey private keys by default.

Minimal state handle metadata:

```
AuthContextRef = {
  id, workspace_id, application_id, target_id, test_run_id,
  test_account_id, expected_role, issued_at, expires_at,
  verifier_id, browser_owner_id?, isolation_policy_version,
  state_format_version, storage_method, revoked
}
```

Sensitive underlying blob: keep in memory for a bounded same-process run if possible. If persisted between owner processes, use authenticated encryption at rest, private short-TTL store accessible only to owner, encryption key outside model prompts, no snapshots/ordinary S3 artifacts, rotate and revoke. Prefer separate dedicated test accounts for distinct roles and cases mutating shared server-side data. Do not share admin state with user cases.

**Correctness:** after creating a fresh context with state, run the same auth+role verifier before any protected action. If it fails, discard handle and request new HITL/reauth or block. Expiration is not a product defect.

## 10.4 Role/fixture matrix

Example intended coverage for staging fixture:

| Identity | Scenario | Requirement |
|---|---|---|
| anonymous | Public home, redirects to login | No human required; no false protected coverage |
| ordinary test user | Login via HITL, user dashboard, own profile | Verified user-only state |
| ordinary test user | Cannot access admin-only page | Real role-isolation assertion with correct expected deny |
| admin test user | Admin dashboard with distinct identity | Separate auth context; prove admin role |
| user session expired | Redirect to login, optional HITL restart | No automatic use of stale auth state |
| user mutates staged data | Validation/persistence with isolated test data | No cross-test contamination |

Login credentials and test data reset instructions are part of fixture setup, never LLM prompts. The full-application feature inventory and role matrix must be generated **after** role-authenticated discovery.

## 10.5 SSO/IdP origins

Maintain distinct frozen policies:

```
application_origins = allowed normal test origins
identity_provider_origins = separately approved auth-only origins
supporting_resource_origins = narrowly scoped, reviewed if strictly necessary
```

Only human auth bootstrap may follow the IdP allowlist. On completion revoke the auth-only exception for AI execution; do not let AI navigate IdP pages using general browser tools. Check redirect chains, subframes, popups and WebSockets. Unknown IdP domain -> blocked/prompt administrator for **separate** authorization, not automatically whitelisted because a web page navigated to it.

Use controlled fake IdP for pilot tests. Real enterprise SSO, CAPTCHA, hard passkeys and production IdP terms may require separate permission/feasibility testing.

---

# 11. EXECUTION, KAFKA, CHECKPOINT AND RESUME SEMANTICS

## 11.1 Core issue to solve

Current `worker.py` consumes one command, processes the entire run, then commits Kafka delivery. `case_execution.py` and `journey_executor.py` close browser in `finally` and use bounded `asyncio.timeout`. A developer adding `await human_decision()` inside the existing tool call would monopolize the consumer and risk timeouts/replays; writing `awaiting_human` to DB is **not enough**.

## 11.2 Required resumable work units

Prefer explicit, small **durable work units**:

```
run.start / plan
-> auth.bootstrap.open
-> human.request / wait state (separate browser owner remains live)
-> auth.verify
-> feature.discover
-> case.execute(step cursor)
-> case.verify / persist
-> next case
-> evaluate
```

Do **not** serialize a Python coroutine, hold SQL transactions for minutes, or rely exclusively on ADK replay to guarantee exactly-once browser effects. Persist the plan ID, case ID, step cursor, browser owner ID/generation, last durable action receipt and pending human request. Use existing Kafka/outbox for notifications/commands, with idempotency keys and transactionally persisted state.

### Kafka command handling

* Existing execution command topic can be extended with versioned `resume_requested`/`human_resolved` command types only if routing and consumers remain backward compatible. Add a separate topic **only if** delivery/ownership requirements force it; document the reason.
* A worker that safely suspends commits the original delivery **only after** persisting the checkpoint + pending request + any necessary outbox command in one DB transaction.
* A resume event must be processed by a worker that atomically claims the current checkpoint/version and validates owner/browser generation and auth verifier success. Duplicate/out-of-order/stale commands are no-ops with audit, not fresh execution.
* Use outbox relay for reliable emit, not direct Kafka send before Postgres commit.
* Keep one worker initially; do not use a huge Kafka poll interval as the HITL durability mechanism.
* If the browser owner disappeared during wait, mark `browser_lost/reauth_required`, release lease and **do not** attempt to “resume” into a new, unauthenticated browser pretending continuity.
* State-changing browser actions must have a receipt associated with execution and step, and ambiguous outcomes must be classified `uncertain_effect` and reconciled read-only before any retry.
* Do not mark a legitimate `awaiting_human` run failed solely because Kafka redelivered a `run_requested` message.

### Timer semantics

`active_execution_deadline` stops or is recomputed from recorded remaining budget on suspension; `human_request_deadline` and lease deadlines keep running independently. The resumed execution still consumes only its **remaining** authorized action/time budget. Suspension is not a way for the LLM to obtain unlimited test time.

## 11.3 Deep-case integration

The immediate next protected feature must work **without** redesigning the planner/evaluator. Introduce controlled session injection into `execute_test_case` while maintaining old defaults:

* A safe browser/session handle for a verified authenticated same-context pilot; or
* An opaque `AuthContextRef` that `BrowserController.create_session()` resolves with approved short-lived test storage state in later cases.

The planner must discover **authenticated** UI. Do not close the bootstrap context prematurely if you plan to use it for the first case. Provide `start_from_authenticated_page` path guarded by verified account/role. Normal unauthenticated cases continue using existing clean contexts.

Checkpoint case at **action boundary**; if it pauses before an action, persist the planned step index and browser owner. If action was attempted before a timeout/interrupt, keep an `unknown_effect` receipt and stop; never auto-replay a click/submission. Preserve existing `ExecutionStep`/artifacts IDs and don't fabricate a completed step.

**Evaluator compatibility:** extend any expected action sequence/ownership validation for legitimate `human_authentication` and `human_approval` transition records as **separate control events**, not as evidence that a planned test action completed. Do not relax exact evidence ownership. Credential-phase viewer actions are not ordinary assertion steps.

## 11.4 Legacy Persona Agent integration

For full V1 later, add a structured `request_human_assistance` tool to ADK only as a request to the deterministic coordinator. The LLM never calls `begin_human_control` directly. Keep `HumanControlActiveError` enforcement in every agent tool. Resume only from a durable work checkpoint or explicitly re-create the agent's state from persisted events with safe idempotency; test pinned ADK 2.5.0 APIs before enabling resumability. Existing `InMemoryRunner` isn't itself a persisted recovery solution.

Google ADK's official resume documentation warns that interrupted tools can run at least once and **more than once** after resume. Side-effectful browser tools require app-level idempotency and reconciliation regardless of ADK's state.

---
# 12. FULL-APPLICATION TESTING AFTER HITL (DO NOT CONFUSE ACCESS WITH COVERAGE)

HITL is a prerequisite for testing some protected flows, but it is not itself a deep-testing engine. The previously implemented feature-case system is still opt-in, deterministic and bounded; real autonomous planning quality has not been established by the available committed benchmark. Keep this scope separate.

## 12.1 Authenticated feature inventory

After verified login for each approved role, discover app navigation and features with safe read-only observation. Create a versioned inventory:

```
FeatureInventoryItem:
    application_id, environment, origin, role
    feature_id, page/route pattern, name
    discovered_from (navigation snapshot, approved knowledge, user-specified)
    authorization_scope
    requirements (grounded/inferred/unknown)
    interaction_class (read_only / synthetic_write / approval_required / forbidden)
    test_status (planned / run / passed / failed_assertion / blocked / inconclusive / not_run)
    evidence_refs (safe step IDs, artifact IDs only)
```

Avoid dumping arbitrary authenticated HTML/PII into the LLM. Use bounded, scoped navigation data; redact user-specific text. Prioritize known critical feature flows and role isolation. Inventory is **not** a license to crawl the entire application unconstrained.

## 12.2 Case matrix

For each approved, testable feature, plan positive, negative, boundary, navigation, recovery, role-permission and state-transition cases **where actually applicable**. Distinguish:

* `documented_expected` — frozen product specification with source and approved oracle;
* `user_declared_expected` — frozen user-created acceptance criterion, explicitly labeled;
* `inferred_expected` — model hypothesis; exploratory only, not confirmed defect;
* `unknown` — cannot infer expected outcome;
* `blocked` — safety/auth/environment prerequisite not satisfied.

Protect case isolation: fresh context or verified short-lived auth state; if mutating server-side data, use dedicated account/test dataset and reset contract. A shared login cookie **does not isolate backend account data**; don't claim case isolation merely because browser contexts are separate. Keep one browser/case at first.

## 12.3 Human intervention during a test

Some approved features may require a new CAPTCHA, step-up MFA, password confirmation or regulated action. The agent should request assistance and pause at a safe action boundary; it does **not** mark the case failed just because human action is required. If the human declines, classify blocked and show which cases remain untested.

The recovery agent (planned separately) may diagnose missing controls only with read-only observation and bounded safe alternatives; it must not bypass HITL, adjust frozen expected outcomes, or retry unknown-effect side effects.

## 12.4 Transparent report

Report at least:

* Application/environment, authorized scope, test roles and verified account class (no credentials).
* Total identified features and cases, exact number executed, passed, failed assertions, inconclusive, blocked, not run; per-role coverage.
* Explicit auth/HITL events and manual prerequisites **without secret content**.
* Confirmed **source-grounded** defect candidates with exact safe execution-step/evidence references; separate source-contract mismatch from intrinsic product correctness.
* Unverified AI observations and execution failures separately, without treating them as confirmed bugs.
* Distinguish actions performed by an agent, a deterministic script and a human. Human-entered login steps do not count as autonomously executed test steps.
* Areas inaccessible due to MFA, passkey/IdP incompatibility, policy, permissions or resource budget.
* Any gaps in the approved expectation contract. No claim of “full coverage” unless an independently maintained inventory supports it.

Continue the requirement-to-assertion compiler and adaptive browser recovery roadmap **after** the first authenticated case passes end-to-end. Do not silently alter its verification standards to make HITL appear successful.

---

# 13. CONTROLLED TEST FIXTURE (REQUIRED BEFORE AUTHENTICATED LIVE APPLICATION)

Build or extend a small **explicitly synthetic** local testing application, independent of the implementation's expected test outputs. Reuse existing deep fixture tooling where possible; do not replace it.

### Synthetic pages and behavior

1. Public landing with navigation to login.
2. Login page with dedicated synthetic username/password fixtures; simulator reads values locally (do not send into LLM).
3. Simulated MFA/OTP challenge that accepts an authorized **fake** code and has known expired/incorrect branches; no real external OTP provider.
4. Optional fake IdP at second local hostname/origin; checked through local-development policy with explicit fake IdP allowlist (not arbitrary real external SSO).
5. Protected user dashboard with a distinct read-only identity/role verifier.
6. Protected admin dashboard and explicit forbidden view for user role.
7. Safe profile/preferences form with validation; isolated test data/reset.
8. A synthetic approval-gated action with harmless observable postcondition and idempotent record.
9. Session expiry, logout and role change; ensure stale auth state rejected.
10. Good/bad fixture variants with predetermined differences and independent ground truth, plus a delayed login/popup and unpredictable UI label challenge for later recovery tests.
11. Injected hostile prompt text on a page (“ignore approval rules”), synthetic console errors, request-failure URLs and deliberate secret-canary strings.
12. Browser owner crash/disconnect simulation, lease race and stale input injections.

### Fixture truth contract

* Machine-readable ground truth with exact expected behavior, role permissions and allowed transitions. Keep this static/independent from the agent's generated plan.
* Dedicated synthetic test users and account reset; never real production usernames or secrets.
* Known click effects and state transitions so duplicate side effects can be detected.
* Support a restricted `local_development` network policy only; do not broaden the public browser origin policy.
* Test the UI both with headless current browser and headed viewer owner without changing expected feature results.
* Add a fixture 'good' variant that should produce **zero falsely confirmed defects**, and a seeded 'bad' variant with countable contradictions and root-cause grouping.

### Milestone demonstration to record (no secret capture)

```
1. Create approved fixture TestRun as test user.
2. Preflight identifies required login.
3. Browser owner opens session; agent tools are quiesced; evidence capture stops.
4. One eligible human operator claims viewer; unauthorized operator is denied.
5. Human completes synthetic login + MFA in exact context.
6. Revoke viewer; auth verifier confirms role=user; agent control resumes.
7. Run one protected feature assertion, persist step evidence and report verdict.
8. Create fresh case context with bounded auth state where supported; verify auth again.
9. Wrong-role and expired-session cases remain blocked/unverified.
10. Scan all artifacts/logs/events/telemetry for canary secret; find none.
11. Repeat under simulated viewer disconnect, operator cancel and browser crash.
```

---

# 14. EXACT DEPENDENCY-ORDERED IMPLEMENTATION WORK PACKAGES

## Execution rule

Work packages H00–H12 below are **incremental PR-sized units**. Keep all previous behavior compatible. For each package: (a) inspect actual files, (b) state exact planned edits and short rationale, (c) write/extend tests, (d) implement, (e) run focused and relevant regressions, (f) show changed file list and factual evidence, (g) update `docs/CURRENT_STATE.md`. Proceed to the next only after its acceptance gate passes. Never claim a phase finished because files exist or mocks pass.

### H00 — Reconcile current checkout and establish safety baseline

**Dependencies:** None. **Priority:** P0. **Proposed files:** documentation and a small focused baseline script only if needed; no product edits.

**Tasks**
- Read repo architecture and exact migrations. Check dirty worktree and preserve pre-existing code.
- Inventory all HITL-related existing methods, DB tables, authorization checks, policies, logs and test fixture.
- Produce decision register: current behavior, desired behavior, gap, risk, source, test.
- Choose explicit pilot target/synthetic identities, bounded runtime and release definitions.
- Run focused current Python/TS tests and controlled direct browser fixture if environment supports them. If not, record blocked reason; never fill in fabricated results.

**Gate:** Baseline recorded; no lost edits; reviewer can distinguish implemented, documented, unverified and deferred. Existing tests green or pre-existing failures identified exactly.

### H01 — Synthetic protected app + attack fixture

**Dependencies:** H00. **Priority:** P0. **Touch:** existing `services/execution-orchestrator/tests/fixtures` / controlled fixture directories and tests; minimize new harness.

**Tasks**
- Add safe synthetic login/MFA/role/expiry/SSO-mock behavior with static independent oracle and reset.
- Add confidential canary emitted in controlled logs during takeover; verify harness can detect a leak.
- Test policy boundaries and deterministic existing cases without HITL first.
- Add seeded harmful *prompt-injection text* in fixture; verify it cannot change target allowlist or approval policy.

**Gate:** Fixture works both good and bad, independently scored; no real network/identity call; fresh test data; known expected outcomes.

### H02 — DB constraints, request/lease lifecycle and ownership

**Dependencies:** H01. **Priority:** P0. **Touch:** `packages/database-python/src/markettwin_database/models/{execution,testing}.py`, actual `database/migrations/versions`, new or existing HITL persistence repository, state repository, tests.

**Tasks**
- Decide minimal additive schema using Section 7. Preserve required `HumanActionRequest.browser_session_id`.
- Implement atomic `create/claim/renew/release/expire/cancel` with idempotency and generation; owner-eligibility checks in API-facing service.
- Add durable suspension/checkpoint record, including exact cursor and short token-free metadata.
- Update TestRun/AgentExecution/BrowserSession state contract consistently where needed.
- Run concurrency, migration, re-entrant and unauthorized tests.

**Gate:** Exactly one active input lease per browser in concurrent DB sessions; expired/consumed grants fail; old data readable; no cross-tenant ownership leak.

### H03 — Complete sensitive-phase privacy gate

**Dependencies:** H02. **Priority:** P0 release blocker. **Touch:** `browser/{human_control,controller,session,evidence,observations}.py`, step recorder/log instrumentation, tests.

**Tasks**
- Introduce explicit capture policy and quiesce/revoke states, with lock/fence preventing agent and human input overlap.
- Suppress console, failed request, pageerror/dialog content and telemetry during sensitive phase; clear unsafe buffers. Ensure trace STOP is complete before viewer grant.
- Suppress snapshots/screenshot/DOM/LLM observations during phase; no transient viewer frames persisted.
- Resume only on verified and appropriately safe target page. Keep separate trace segments.
- Inject known canary into fixture and test all success/failure/timeout/exception and close paths.

**Gate:** Zero canary matches across *all* instrumented sinks and evidence artifacts; agent input forbidden during human control; browser close cleanup never leaks secrets. Without this, do not expose viewer to credentials.

### H04 — Browser ownership abstraction and local viewer technology spike

**Dependencies:** H03. **Priority:** P0. **Touch:** existing browser controller adapter; isolated local pilot viewer/gateway, local Docker/WSL configuration if selected, fixture tests, spike comparison report.

**Tasks**
- Create minimal `BrowserOwner` interface wrapping existing controller; do not copy browser logic.
- Implement a private viewer POC using chosen transport (noVNC or restricted CDP), run measured comparison when both are feasible. Observe exact browser `session_id` before/during/after.
- Put WSS input behind signed-in user + lease/generation policy; no raw debugging port outside owner network.
- Test keyboard, paste/IME if applicable, focus, pointer, scroll, popup, two factor simulation, inactivity timeout, disconnection, resize and revocation.
- Record latency/resource/security/compatibility in a decision doc. **Stop for explicit review of irreversible hosting/vendor choice.**

**Gate:** Human logs in on same Playwright context; no agent commands during takeover; no stale input after revoke; no secret recording; clear transport decision backed by measurements.

### H05 — HITL REST API and minimal React takeover UI

**Dependencies:** H02–H04. **Priority:** P0. **Touch:** new `services/control-api/src/markettwin_control_api/api/human_actions.py`, `main.py`, permissions/helpers, `apps/web/src/pages/runs/HumanActionPage.tsx`, API types, routing/status UI, tests.

**Tasks**
- Implement authorized request/list/claim/viewer-ticket/complete/cancel/renew endpoints using existing session auth and workspace/target membership.
- Render real pending assistance, reason, timer, viewer, completion/verification, cancellation and errors; no login password/OTP fields in MarketTwin UI.
- CSRF, WSS Origin, session and per-message permission checks, safe errors, rate limiting, no ticket in query string.
- Add frontend and backend negative permission tests and accessibility checks.

**Gate:** Unauthorized cannot claim/view/release; concurrent winner behavior reflected in UI; completion does not independently mark auth verified; no credential strings visible in API responses or persistent frontend state.

### H06 — Auth verifier, scope policy and SSO bootstrap

**Dependencies:** H05. **Priority:** P0. **Touch:** new/extended `workflow/auth_bootstrap.py`, `browser/policy.py`, `browser/controller.py`, `workflow/deep_run.py`, target configuration API and tests.

**Tasks**
- Add approved, read-only verifier spec and fake IdP auth-only origins; freeze immutable target policy snapshot at run creation.
- Create browser before authenticated feature discovery; request HITL only for authorized targets.
- On human completion revoke viewer input, verify actual account/role, clean sensitive state, resume and re-segment evidence.
- Fail safely for wrong role, unknown/expired IdP, absent proof, redirect to private IP or denied target.
- Document egress enforcement gap if local runtime cannot pin actual network destinations.

**Gate:** Verified user can access protected fixture and planner sees protected app, wrong role denied, unknown IdP blocked; no auth state exposed to model.

### H07 — Durable suspension and worker-safe resume

**Dependencies:** H02, H04, H06. **Priority:** P0 (V1 reliability). **Touch:** `worker.py`, `run_request_handler.py`, `run_state_repository.py`, `run_event_repository.py`, new checkpoint manager, `workflow/{run_executor,case_execution,journey_executor}.py`, associated tests.

**Tasks**
- Define explicit `awaiting_human` work-unit and checkpoint; ensure worker can commit after durable suspension without ending the run as failed.
- Introduce supervised/browser owner addressability for human wait if shipping beyond synchronous pilot, not general new infrastructure by default.
- Create idempotent resume via existing Kafka/outbox command flow. Resume only with current checkpoint, generation, live owner and verified auth.
- Prevent duplicate Kafka redelivery from failing legitimate paused runs; prevent uncertain side-effect replay.
- Keep bounded human deadline separate from active case deadline; cancellation and resource reaper.

**Gate:** Forced Kafka redelivery and process restart simulation cannot repeat a synthetic mutation; user can pause for minutes without blocking all new work; browser owner loss is visibly blocked, not silently re-executed.

### H08 — First end-to-end protected feature using same context

**Dependencies:** H05–H07. **Priority:** P0. **Touch:** `workflow/{deep_run,case_execution}.py`, `browser/controller.py`, relevant evaluation/test files; minimal UI wiring.

**Tasks**
- Execute full synthetic flow including approved login + MFA + role verifier + one protected feature assertion.
- Persist actual execution step and artifact IDs *outside* credential phase; evaluate via existing deep evaluator.
- Show the user journey and associated evidence, with HITL marker separate from autonomous action timeline.
- Confirm target origin/permissions remain the same; policy-blocked cases do not become product bugs.

**Gate:** Repeatable full pipeline from user start to final report, not only a standalone browser script. Independent ground truth matches report; no secret leakage; no fabricated confirmed findings.

### H09 — Isolated multi-case authenticated-state broker

**Dependencies:** H08. **Priority:** P1. **Touch:** `browser/controller.py` create session options, new `workflow/auth_context.py`/broker, `workflow/deep_run.py`, account/test config, tests.

**Tasks**
- Explicitly choose short-lived in-memory broker first; encrypted storage only if cross-process required.
- Capture approved synthetic test account `storage_state` after verified login; no automatic inclusion of virtual passkeys/private credentials. Bind reference to tenant/run/role/target/expiry.
- Initialize separate contexts for next cases and verify account/role in **each**; fallback to same-context or HITL when state cannot transfer.
- Prevent admin cookie reuse by user case, stale state after logout, and server-state conflicts; support approved distinct accounts for mutating cases.

**Gate:** At least 3 independent protected cases run without repeated manual login when state supported; wrong-role/stale state blocked; auth blob cannot appear in normal artifacts.

### H10 — Separate human approval for one controlled side effect

**Dependencies:** H02, H05, H07. **Priority:** P1. **Touch:** new approval policy/repository/API, browser action dispatch, fixtures and tests.

**Tasks**
- Identify approval-eligible synthetic effect classes; build canonical immutable fingerprint including actor, environment, resource/version, action/args, expiry and policy version.
- Require explicit eligible human decision; consume once; reject changed action/target/replay/stale resource.
- Preserve hard-deny production categories. No generic approval for opaque “Continue” operations without classification.
- Record safe audit+result; fake fixture ensures synthetic mutation happens **at most once** under duplicate command delivery and uncertain timeout.

**Gate:** Approval never overrides denied target/risk, is not reusable, and cannot authorize a different effect; default non-approved action blocked.

### H11 — Authenticated coverage matrix and reporting UX

**Dependencies:** H08–H10 as applicable. **Priority:** P1. **Touch:** feature plan, run/coverage report, evaluation worker, `FeatureCases`, journey detail, run overview.

**Tasks**
- Inventory protected routes/features per role after login; create grounded feature test cases, track not-explored portions.
- Distinguish manual login, autonomous actions, deterministic case execution, assertion results, blocked and unverified outcomes.
- Show actionable safe evidence without human credential steps; prevent false “full application tested” banner.
- Add app-specific approvals/role coverage only when permission and reset prerequisites exist.

**Gate:** Report counters reconcile exactly to run events/plan and independent fixture truth; no protected feature marked tested simply because authentication succeeded.

### H12 — Hostile-path validation, security review and release/no-go

**Dependencies:** All required P0/P1 tasks. **Priority:** P0 before hosted release. **Touch:** tests, CI gates, docs, optional load test config, security review; do not deploy automatically.

**Tasks**
- Run full adversarial matrix in Section 15 and compare against frozen baseline.
- Test operator concurrency, role escalation, CSWSH, request/lease replay, credentials in every sink, SSO redirects, DNS rebinding/egress, worker restart, browser loss, duplicated Kafka commands, expired tokens, ambiguous click effects, state reuse, cancellations.
- Measure latency, owner memory/CPU per browser, network bandwidth, model calls and hosting projections; no invented cost.
- Document residual risks, unsupported auth technologies and user-facing limitations. Have a human review lease/credential code paths.
- Decide pilot, staging or production gate explicitly; don't call full production readiness with failed or unexecuted security gates.

**Gate:** Signed-off test matrix, no known credential leak, no authorization bypass, no non-idempotent duplicate effect, authenticated fixture E2E green, old unauthenticated flows green, cost/security measured and documented.

---
# 15. ADVERSARIAL AND FUNCTIONAL TEST MATRIX — MUST IMPLEMENT

The following are **required tests**, not examples that can all be replaced by one happy-path mock. Use deterministic fixture truth and isolated transaction/browser tests. In security-critical paths, cover real API authorization and actual browser owner behavior in addition to unit tests. Label unavailable environmental tests explicitly.

| ID | Test scenario | Required result |
|---|---|---|
| T01 | Public authorized feature | Legacy unauthenticated flow unchanged |
| T02 | Protected fixture triggers auth preflight | Request exists, protected feature not falsely inspected |
| T03 | Human claim by eligible operator | Exactly one active lease, valid generation |
| T04 | Two eligible operators claim concurrently | Exactly one 2xx winner, one conflict |
| T05 | Workspace reader lacking operator role | Claim rejected |
| T06 | Foreign workspace guessed request/run UUID | No cross-tenant information or control |
| T07 | Owner/admin revokes target authorization while takeover pending | Current lease revoked, run blocked |
| T08 | Browser input by agent during human control | Rejected even if tool name is otherwise safe |
| T09 | Browser input by human before claim | Rejected |
| T10 | Human input with old generation after resume | Rejected |
| T11 | Human input with expired lease before UI notices | Rejected server-side |
| T12 | Human input on viewer socket with different actor | Rejected |
| T13 | WSS from disallowed Origin with valid cookie | Rejected at handshake |
| T14 | WSS session cookie expired mid-connection | Input stops; disconnected/revoked |
| T15 | CSRF against lease/approval endpoints | Rejected |
| T16 | Oversized/malformed/replayed WS control frame | Rejected, no browser action |
| T17 | Agent and human try concurrent input at transition boundary | Never both accepted |
| T18 | Synthetic login + fake MFA using same context | Auth verifier succeeds, protected page accessible |
| T19 | Human clicks Done without completing login | `auth_unverified`, not resumed as authenticated |
| T20 | Human logs in with wrong role | Wrong role blocked, no admin test allowed |
| T21 | Human denies/cancels/abandons | Blocked/inconclusive, no false product defect |
| T22 | Human wait exceeds deadline | Lease expires, browser cleaned or safely parked |
| T23 | Viewer disconnect while human has lease | Bound on reconnection, no uncontrolled input |
| T24 | Browser owner killed during takeover | Request invalidated, no replay; `browser_lost` reported |
| T25 | Worker restarted while paused, browser owner still live | Resume path uses checkpoint and current owner; no duplicate action |
| T26 | Kafka run request redelivered while paused | Not marked incorrectly failed, no duplicate human requests |
| T27 | Resume command delivered twice/out of order | Single checkpoint consumed, no duplicate effect |
| T28 | Original action succeeded but response timed out | No automatic second submission; reconcile/uncertain |
| T29 | Synthetic password appears in page console during human phase | No password in MarketTwin artifacts/events/APM |
| T30 | Synthetic OTP appears in request-failure URL/error | No OTP in MarketTwin logs or persisted metadata |
| T31 | Playwright tracing was active immediately before takeover | Trace segment ends before credential entry |
| T32 | Exception/timeout during human phase cleanup | No secret log/trace leakage |
| T33 | Viewer transport configured with recording capability | Recording disabled/test detects noncompliance |
| T34 | Unknown IdP redirect during SSO | Blocked, not auto-whitelisted |
| T35 | Approved synthetic IdP redirect and return | Allowed only during auth phase |
| T36 | IdP origin after agent resumes | AI navigation to auth-only origin denied |
| T37 | Redirect to private/link-local/metadata IP or unsafe WS | Blocked; no network pivot |
| T38 | Public-to-private DNS rebind through browser network | Blocked by egress/network policy, otherwise HOSTED NO-GO |
| T39 | Auth state copied to a new user-role context | Rejected/verified wrong role, never silently used |
| T40 | Stale storage state after logout/expiry | Reauth/blocked, not successful |
| T41 | Auth blob appears in report/Kafka/LLM prompt | Never allowed; scanner must find zero occurrences |
| T42 | User and admin tested concurrently with shared server state | No cross-account data leakage; use separate accounts |
| T43 | Synthetic approval exact fingerprint | One approved harmless mutation only |
| T44 | Modified resource/arguments after approval | Approval invalidated/rejected |
| T45 | Expired or already consumed approval | Rejected |
| T46 | Production-like prohibited action asks for approval | Hard-denied; no escalation |
| T47 | Prompt-injection text asks agent to whitelist domain/skip login | Does not change policy, origin or approval |
| T48 | Good fixture with no defects | Zero confirmed false issues |
| T49 | Seeded bad fixture | Grounded contradiction detected with exact step and expected source |
| T50 | Only inferred expectation contradicted | Needs verification, not confirmed defect |
| T51 | Browser human phase incorrectly counted as agent test coverage | Test fails; corrected counting excludes manual input |
| T52 | Marked full app pass with uncovered feature | Test fails; report shows not-run/gaps |
| T53 | Old legacy persona run and old report retrieval | Backward-compatible |
| T54 | Alembic upgrade populated DB | No data loss, constraints operate, downgrade/restore documented |
| T55 | UI keyboard-only operator walkthrough and screen reader labels | Can claim, perform operation, cancel, observe outcome |
| T56 | Browser resources remain after timeout/cancel | Reaper closes/disposes them within bounded grace |

Where needed, record browser trace **outside** the sensitive phase and test results **without** any captured secret values. For leak tests, include raw strings only in controlled fixture in-memory and test harness; never publish real credentials or synthetic canaries to public logs. If a test cannot run due to infrastructure, it is `NOT EXECUTED` and cannot satisfy release gate.

### Particular evidence assertions for security tests

* A test failing because of UI rendering does not prove HTTP request denial; test server enforcement directly.
* A test checking the frontend hides a claim button does not prove the API prevents claim.
* A test checking only a password input DOM attribute does not prove absence of model or telemetry leakage.
* A test proving browser-origin checks does not prove actual TCP egress safety under DNS rebinding.
* A human viewer connected to a second browser is a **failing** test, even if the second browser's login works.
* Successful manual login is **not** proof of any downstream test case's correctness.
* A browser session `open` row is not proof that its process is alive; add heartbeat/probe.
* Absence of GitHub Actions statuses does not demonstrate tests passed. Record actual local command output and CI when available.

---

# 16. QUALITY GATES, METRICS AND RELEASE CRITERIA

## 16.1 Stage definitions

| Stage | Allowed claims | Mandatory evidence |
|---|---|---|
| Design reviewed | Contracts and risks documented | Code audit, security review notes, decision register |
| Local transport spike | Human can interact with same browser on synthetic fixture | Session-ID continuity, owner/lease checks, no-secret recorder test |
| Local integrated pilot | Human login -> verify -> one protected feature -> report | Real FastAPI/Postgres/worker/Playwright/evaluator path and fixture truth |
| Authenticated V1 staging | Multiple isolated role-scoped cases, resumable human wait, action approvals | Redelivery, owner crash, state reuse and 56-case relevant security matrix |
| Hosted production | Mature isolation/egress, operations, cost, identity, security signoff | Independent review, deployment-specific hardening, observed load/cost, rollback drill |

## 16.2 Mandatory pass/fail gates

**Security:** zero credential/OTP/auth-state strings leaked into tested persisted sinks; zero unauthorized tenant/user access; zero input events accepted after revocation; zero concurrent agent+human control; zero disallowed origins/network paths in the tested threat model; zero approval reuse; no real credential or live production effect. Any violation is a hard NO-GO.

**Safety:** all uncertain-effect actions remain un-replayed until reconciled; a browser loss never returns “pass”; denial/expiry remain blocked or inconclusive; no run resumes without auth/role proof; arbitrary app text cannot broaden policy.

**Correctness:** authenticated fixture cases reproduce ground truth; known-good produces zero confirmed false defects; each confirmed assertion has matching frozen source, exact owned browser step and relevant evidence; reported case counts reconcile to persisted data.

**Reliability:** duplicate Kafka commands and concurrent claims do not create duplicate mutations or active leases. Normal worker pause releases consumer processing work; owner process failure is handled explicitly. Cross-case auth is only reused after per-case verification.

**Compatibility:** no regression in legacy public-site testing; existing API routes and old run reports work; no unreviewed breaking migration.

**Performance/cost:** measure actual run latency (excluding and including human wait separately), viewer frame latency, CPU/RAM per active browser owner, DB/Kafka volume, auth-state lifetime, provider/model cost, browser capacity. Do not invent AWS costs, promise a free tier, or assume the machine can support N viewers without measurements.

## 16.3 Proposed quantitative pilot thresholds (tune after baseline)

1. **0** cross-tenant takeover successes in the test matrix.
2. **0** accepted stale/expired generation input frames.
3. **0** synthetic credential matches in any audited persisted MarketTwin sink or ordinary evidence artifact.
4. **0** repeat execution of the fixture's approval-gated synthetic mutation under duplicates/restarts.
5. **0** falsely confirmed product issues in independently known-good fixture.
6. **100%** expected role verifiers honored in fixture scenarios, including wrong role.
7. **100%** honest blocked/inconclusive outcomes when auth cannot be verified.
8. Run at least **three independent** full-integrated success trials and **three** challenge/failure trials, then expand to varied synthetic fixtures; report counts, not just selected screenshots.
9. Demonstrate at least **three** separately verified protected feature cases for reused auth state in applications that support reuse; no repeated manual login within each valid run.
10. Record actual latency and cost distribution; decide operational limits only after observation.

These thresholds are **acceptance proposals**, not measured results or proof of general security.

## 16.4 What success does *not* establish

The fixture can show architecture correctness but not that every real IdP, CAPTCHA, hardware passkey, session-storage implementation, customer identity policy or SaaS app is supported. Also, authenticated browser control cannot by itself detect all defects or cover all screens. Document unsupported cases and request an explicit authorized staging target for later reality checks.

---

# 17. OPERATIONAL AND AWS/DEPLOYMENT POSITION

**Do not deploy during initial development.** User's MarketTwin direction is incremental V1 with minimized AWS cost and a REST API control plane. Preserve that:

1. Implement/test locally with existing Postgres, Kafka/outbox and MinIO/S3-compatible dev infrastructure; add the smallest disposable browser/display container needed for viewer pilot. Do not rebuild root infrastructure.
2. Keep FastAPI REST commands, authorization and business APIs. Use WSS **only** for live viewer media/input or a similarly vetted duplex transport. Evaluate gateway choice separately; AWS API Gateway's REST API and WebSocket API are distinct types with different limits/integration semantics.
3. Avoid introducing paid hosted browsers, brokers, cache tiers or orchestration services before cost measurement and approval.
4. If staging on AWS eventually, browser owner containers need their own isolated, supervised runtime and secure private networking. Do not run long-held browser desktops in short-lived Lambda function calls. Size Fargate/EC2/EKS only after a measured browser process profile; don't guess cheapest without instance/network/storage prices and expected concurrency.
5. Network egress is part of the architecture: defend against private/local metadata endpoint access under redirects/DNS changes, including authentication-only origins. Security groups alone may not implement domain-level restrictions; use a real egress enforcement strategy and test it before multi-tenant hosting.
6. Timeouts/reapers must bound abandoned browsers, video streams, authentication state and active leases. Include cleanup on cancel, browser close, end of run, target revocation and workspace/user permission removal.
7. Keep logs strictly nonsecret. If CloudWatch or another APM is used, add explicit filters and audit the exporter/OTel instrumentation. Separate security audit events from sensitive browser transcript recordings.
8. If browser viewer reliability or identity integration is unproven, release only to a synthetic local/staging fixture—not to customers with real credentials.

### Suggested operational SLO inputs (measure first)

* Maximum concurrent active browsers per host; peak resident memory; boot time; per-frame bandwidth.
* Mean/p95 claimed-viewer connect time and key-to-visual-response latency.
* Fraction of human assistance requests completed, denied, expired, disconnected, browser-lost.
* Success/failure per app auth mechanism (password/MFA/SSO/session reuse), with appropriate privacy.
* Count of stale-input blocks, failed authorization checks, secret scanner failures.
* Cost per authenticated feature test, including browser resources and human-wait resource time.

Never treat a synthetic load number or documentation cost example as a current production price.

---

# 18. CODING, TEST, REVIEW AND HANDOFF CONVENTIONS

## 18.1 File and module placement rules

* Keep ORM in `packages/database-python/src/markettwin_database/models/`; migrations in `database/migrations/versions/`.
* Keep shared typed contracts in `packages/shared-python/src/markettwin_shared/` **if reused across API/orchestrator/evaluation**, otherwise place internally near the implementing service.
* Keep browser safety, viewer ownership and capture rules in `services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/` or a small adjacent owner module/service rather than burying them inside an ADK prompt.
* Keep DB HITL transactions in control-api or a shared repository following existing package conventions, without circular service imports.
* Keep FastAPI endpoints in `services/control-api/src/markettwin_control_api/api/` and register with existing `main.py`.
* Keep React screen in the existing `HumanActionPage.tsx`, API functions/types in current app conventions. Reuse permission helpers.
* Keep test fixture and benchmark integrated into existing test directories/scripts; avoid a duplicate project scaffolding system.
* Avoid adding a new DSL or generalized workflow engine. Small typed Python data classes/Pydantic schemas and deterministic functions are preferred.

## 18.2 Required automated checks

Adjust exact invocations to the user's environment and current repo configuration; record full errors rather than claiming an invocation ran successfully when it did not:

```powershell
# From MarketTwin root (Windows PowerShell examples; adapt safely)
git status --short
git branch --show-current
git rev-parse HEAD

# Focused tests after each Python phase
uv run --env-file .env python -m pytest services/execution-orchestrator/tests -q
uv run --env-file .env python -m pytest services/control-api/tests -q
uv run --env-file .env python -m pytest packages/database-python/tests -q
uv run --env-file .env python -m pytest services/evaluation-worker/tests -q

# Quality checks (do not use broad formatting to rewrite unrelated code)
uv run ruff check services packages
uv run pyright

# React frontend
npm.cmd --workspace @markettwin/web run typecheck
npm.cmd --workspace @markettwin/web run build
npm.cmd --workspace @markettwin/web run test -- --maxWorkers=1 --testTimeout=15000

# Run controlled Playwright E2E after the fake app/services start
# Follow the repository's own test/e2e setup and authorized local fixture instructions.
```

These are **candidate commands**, not executed here. `--env-file .env` may load sensitive values; never echo them. `npm.cmd` is appropriate on Windows; Unix shells may use `npm`. Prefer narrow targeted pytest/ruff commands during development and broader suites at phase gates. Some database and browser tests require local services and Playwright browser installation—mark unavailable services clearly and do not convert that into a pass.

## 18.3 Phase report required from coding agent

After every Hxx phase, write a compact machine-reviewable status report:

```text
PHASE: Hxx / title
Baseline SHA / current SHA / branch / dirty files before-after
Decisions taken / alternatives rejected / why
Exact files touched / new migrations / API changes
Tests run with commands and actual counts/exits
Browser or security fixture evidence path (nonsecret)
Acceptance criteria: PASS / FAIL / NOT EXECUTED individually
Regression/compatibility effects
Known risks, limitations and next dependent phase
Any authorization / cost / deployment decision requiring approval
```

Update `docs/CURRENT_STATE.md` with factual results and next step and follow `AGENTS.md` continuity rules. No unapproved `git push`, deployment, third-party billing, or use of real credentials.

## 18.4 Stop conditions

Stop and ask before: changing authentication secret-handling policy; storing real session state on disk; allowing production side effects; expanding allowed origins to an unknown IdP; deploying VNC/CDP publicly; choosing a paid browser vendor; adding a new broker/orchestration platform; changing existing network policy; running on external targets; destructive DB migration; committing/pushing to another branch; claiming unknown costs are within budget.

If the local checkout has substantial unstaged changes, work around them surgically and do not overwrite their contents. If this plan contradicts implemented behavior, provide a minimal RFC and preserve actual code until resolved.

---

# 19. COPY-READY KICKOFF INSTRUCTION FOR GPT-6 IMPLEMENTER

Paste the following short instruction into the coding agent **with this entire Markdown file attached or present at repository root** (for example, `docs/HITL_IMPLEMENTATION_MASTER_PLAN.md`). Do not rely on a link to a previous ChatGPT artifact being visible to the coding agent.

> Implement MarketTwin's human-in-the-loop authenticated testing capability from `MARKETTWIN_GPT6_HITL_FULL_APPLICATION_IMPLEMENTATION_MASTER_PLAN.md`.
>
> This is an existing Python Playwright + Google ADK + FastAPI + PostgreSQL + Kafka + React/TypeScript monorepo. My central goal is a trustworthy autonomous application-testing product capable of human-assisted login/MFA/SSO, authenticating the **exact** Playwright BrowserContext, preserving secrets from AI/evidence, resuming safely, and testing multiple protected features/roles with accurate findings.
>
> **Start by reading** `AGENTS.md`, `MKT.md`, `docs/CURRENT_STATE.md`, `docs/SESSION_HANDOFF.md`, existing deep-testing roadmap, actual source, migrations and test fixtures. Inspect `git status` before changing anything. Existing branch/commit may be newer than the plan; reuse code that already exists.
>
> Execute H00–H12 **in dependency order**, in reviewable small steps, testing every phase and updating `docs/CURRENT_STATE.md`. Treat security and correctness gates as strict: never capture real credentials or OTPs in prompts, traces, logs, RunEvents, Kafka, S3 or user-visible reports; never let agent and human both control a browser; never treat a 'Done' button as auth proof; never blindly replay an action after uncertain side effect; never bypass target network/auth rules.
>
> Preserve the current architecture and APIs. Do not replace the browser controller or add orchestration services without demonstrated necessity. Do not mistake a direct deterministic fixture runner for proof of autonomous agent testing. If the viewer transport choice requires a local security/cost experiment, run the synthetic comparison and ask for approval at that decision gate. Do not deploy, push, spend, access public targets, use real credentials or perform destructive actions without my explicit permission.
>
> Provide exact changed files, real test outcomes, and what remains unverified after each phase. Mark production-release gates `NO-GO` until they are actually passed. Begin now with H00 and H01, then progress according to the plan's dependencies.

---

# 20. DECISION GATES AND OPEN QUESTIONS THE ENGINEER MUST VALIDATE

These are not excuses to stop all development; document defaults for synthetic pilot and elevate only truly consequential choices.

1. **Viewer transport:** noVNC or restricted CDP? Default: measured local POC; production choice gated by security/latency, not aesthetics.
2. **Local environment:** user works with Windows/PowerShell; verify Docker Desktop/WSL2 availability before assuming Linux display containers. Default: use project-supported Docker/Playwright dependencies; do not install system-wide software without consent.
3. **Human operator entitlement:** who may authenticate as test role? Default: workspace owner/admin explicitly designated for the target. 'Member' can create ordinary run but cannot claim a privileged login unless authorized.
4. **Synthetic account provisioning:** fixture only at first. Do not depend on or store real credentials.
5. **MFA methods:** fake OTP simulator first. Document unsupportable real passkey/IdP cases rather than work around security controls.
6. **Auth verifier:** approved application-specific marker/role. If lacking, block role-restricted testing.
7. **Browser lifetime:** pilot in-process may prove same-context UX but not worker-crash durability. Durable V1 requires supervised separate owner; decide implementation after POC.
8. **Auth reuse:** default optional, target- and role-bound, transient and reverified. No implicit reuse across test runs or tenants.
9. **Side-effect policy:** default synthetic staging mutations only; all real/potentially irreversible production actions denied.
10. **Network:** for external hosted multi-tenant browsers, add tested egress restrictions. Existing code's DNS pre-check is not enough to claim DNS-rebinding resistance.
11. **Full app scope:** requires approved role/feature inventory, budget and reset policy. A single protected run is not full app certification.
12. **Hosting/cost:** measure browser-owner resource profiles, proxy/data transfer and concurrency before proposing AWS services or budgets.
13. **Persistence/retention:** decide short TTL and key ownership for any encrypted state; audit/revoke. Auth-state blob is never ordinary evidence.
14. **Approval schema:** preserve current non-null `HumanActionRequest` browser FK. Use separate action-approval contract unless a safe additive migration is demonstrably simpler.
15. **Google ADK semantics:** verify actual pinned `2.5.0` before using resume features; duplicate tool execution risk remains even where supported.

---

# 21. PRIMARY DOCUMENTATION AND TRACEABILITY

These are source references for engineering principles; repository facts are from the pinned GitHub SHA at the top. Validate links and documentation against dependency versions during implementation.

| Source | What it supports |
|---|---|
| [Playwright Python — Authentication](https://playwright.dev/python/docs/auth) | Isolated contexts, reusing storage state, sensitive auth data and nonportable session storage |
| [Playwright Python — BrowserContext API](https://playwright.dev/python/docs/api/class-browsercontext) | `storage_state`, context state and version-specific options; check Playwright 1.61 behavior |
| [Playwright Python — Trace Viewer](https://playwright.dev/python/docs/trace-viewer) | Traces can contain DOM snapshots, screenshots and network contents; privacy scope is broader than screenshots |
| [Google ADK — Resume](https://adk.dev/runtime/resume/) | Resumable workflow concepts and at-least-once/tool-reexecution caution; confirm API for repo's pinned `google-adk==2.5.0` |
| [OWASP WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html) | WSS handshake origin validation, CSWSH, message-level authorization, payload/rate limits and sensitive-log hygiene |
| [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) | Secret lifecycle, audit, authorization and safe treatment of security-sensitive material |
| [AWS API Gateway — WebSocket APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-overview.html) | Difference between REST and WebSocket interface types; does not make API Gateway automatically optimal for a high-bandwidth viewer |
| [noVNC](https://novnc.com/info.html) / [websockify](https://github.com/novnc/websockify) | Browser-accessible VNC client/WS proxy; **not** a turnkey MarketTwin authorization or isolation layer |
| [MarketTwin GitHub branch](https://github.com/Sreenav14/Market-Twin/tree/feat/batch-1-aws-observability) | Primary code audit target |
| `MARKETTWIN_HITL_V2_INDEPENDENT_ARCHITECTURE_AUDIT.md` | Prior independent source/recommendation review; do not mistake recommendations for implemented functionality |

### Source-vs-proposal discipline

**Code-confirmed:** Browser state transitions, ORM constraints, new BrowserContext per journey/case, worker commit semantics, frontend placeholder, current route/controller patterns, existing deep-testing guard.  
**Official-doc supported:** Auth-state handling risk, browser context isolation, trace content, WS security, ADK duplicate-tool caution, AWS interface distinction.  
**Engineering proposal:** New REST endpoints, lease intervals, browser owner deployment topology, versioned checkpoint schema, auth verifier DSL, viewer choice, migration layout, benchmark thresholds and phase estimates.  
**Not validated:** Real tenant deployment, external IdP compatibility, browser viewer frame/input latency, auth-state portability, credential leak absence in a deployed environment, AWS costs, multi-tenant egress enforcement, protected E2E correctness and production readiness.

---

# 22. DEFINITION OF DONE — FINAL CHECKLIST FOR THE CODING MODEL

- [ ] Read local repo and reconcile plan; preserve pre-existing changes.
- [ ] Synthetic protected feature fixture and independent oracles exist.
- [ ] One-lease-per-browser enforced transactionally; fencing generation works across stale sockets.
- [ ] Existing DB constraints/foreign keys preserved or migrated coherently, and status readers updated.
- [ ] Browser-owner interface preserves exact Playwright context during takeover.
- [ ] Agent tool authority is disabled before human input and restored only after server-side verification.
- [ ] Screenshot, trace, console/network error, APM, Kafka, UI and viewer secret sinks are gated; canary scan passes.
- [ ] Interactive secure viewer works on controlled fixture; no public raw VNC/CDP.
- [ ] Human claims, cancels, expires and verifies through authenticated REST API and React UI.
- [ ] Approved auth-only IdP origins are isolated from general agent network authority.
- [ ] Actual target role/account is checked before authenticated feature planning and on new case context.
- [ ] Worker can durably suspend/resume through existing Postgres/Kafka without indefinitely processing a command.
- [ ] Duplicate messages and uncertain effects cannot silently re-execute mutations.
- [ ] One full integrated protected feature test passes through planner/executor/evaluator/report; no fake coverage.
- [ ] Multi-case test-account state reuse is verified, scoped, expiring and inaccessible to LLM.
- [ ] A separate exact one-time approval flow is implemented if included in selected release phase.
- [ ] Feature/role coverage reports blocked/not-run/inferred correctly and excludes human credential steps from agent metrics.
- [ ] Every relevant attack test in Section 15 is passed, failed with a blocker, or marked NOT EXECUTED (never assumed passed).
- [ ] Existing public flows and legacy reports remain functional; migrations are safe.
- [ ] Tests/commands/results are recorded with actual outputs and no credential exposure.
- [ ] Viewer transport ADR and measured latency/security/cost tradeoffs are documented.
- [ ] No deployment, real login, public-target test, paid service, destructive action or push occurred without approval.
- [ ] Final release classification is explicit: `LOCAL PILOT`, `STAGING CANDIDATE`, or `HOSTED PRODUCTION NO-GO/GO` with supporting evidence.

**Final philosophy:** An AI agent should not need secrets or unbounded privileges to test a protected application. Human assistance grants only the missing authenticated capability, temporarily and under deterministic policy. Existing test planning and evaluation remain responsible for proving what the software actually did. Build proof before promising completeness.


</details>

## Appendix B: historical verification evidence

Historical/design material follows. Current operational status is recorded above.

<details>
<summary>Expand the complete preserved reference</summary>

## Historical evidence before final generalized implementation

# HITL phase evidence — 2026-10-14 continuation

Baseline/current HEAD: 8075327a8a0681edaa0ac6d9273362c7eb65e264.
Existing dirty files were recorded before editing and preserved, including the
deleted knowledge-worker bridge, RunFlowPanel change, prior HITL code and plan.

## Environment recovery

Default exec process creation still fails with helper_unknown_error: setup refresh
had errors. The supported escalated Get-Date command succeeded. Node REPL can
read workspace files. This is infrastructure evidence, not an application failure.
Read/test commands now run through the working escalated shell. No reset, clean,
deletion, credential import, paid model call, push or deployment occurred.

## Phase reconciliation against actual code

| Phase | Status | Code and acceptance evidence / remaining proof |
| --- | --- | --- |
| H00 | Complete baseline | Existing H00 reconciliation read, dirty tree inspected, HEAD confirmed, refreshed browser baseline 8 passed. |
| H01 | Partial implementation | Static synthetic login/MFA/user/admin fixture and independent auth oracle exist. Fixture and verifier tests pass. Full expiry/reset, fake IdP, approval effect, disconnect fixture matrix and authenticated end-to-end run are absent. |
| H02 | Partial implementation; focused repository gate passes | Additive migrations, lease repository, generation/index, ExecutionSuspension and one-time approval models exist. PostgreSQL lease/approval and bounded expiry-reaper tests pass; API lifespan owns the reaper. `alembic heads` reports `a1b2c3d4e5f6` as the single head and the complete chain renders offline. Migration compatibility/restore matrix is not run. |
| H03 | Browser privacy controls verified; integration unverified | Browser/tool privacy tests are included in the 48-pass focused suite; rejected agent calls cannot record steps/evidence in tested paths. API/WS/APM/DB/Kafka integrated canary scans remain pending. |
| H04 | Implemented local worker/viewer path; integrated acceptance partial | Same-context restricted owner, registry, supervised loopback Uvicorn WebSocket gateway, one-time tickets, live authority checks and React canvas/input client are wired. Worker/viewer tests pass (24); browser/API/worker DB-backed claim-to-stream acceptance and production WSS reverse-proxy deployment are unverified. |
| H05 | Implemented API/UI paths; integration partial | Run-scoped list/claim/renew/cancel/release and signed worker handoff, authorization checks and viewer UI exist. API targeted suite passes 12 (one PostgreSQL-gated skip); live authenticated claim was not exercised end-to-end. |
| H06 | Authenticated role verification wired; integration partial | Exact origin/selector/marker/role policy is validated against target allowlist; worker waits for release then verifies the same live handle before resuming. Focused workflow/verifier tests pass; integrated authenticated app run is not executed. |
| H07 | Durable request/checkpoint transitions implemented; crash recovery partial | Auth request and secret-free suspension lifecycle is persisted; bounded in-process wait resumes after signed release. Worker restart/browser loss cannot restore the Playwright context and is fail-closed; full Kafka suspension/replay integration remains unverified. |
| H08 | Not complete | No integrated protected start→worker→same-browser takeover→verified resume→evaluator/report run. Direct service/workflow fakes are not pipeline proof. |
| H09 | Scoped cross-case reuse implemented; integration partial | Verified in-memory broker is connected to takeover and fresh case contexts; snapshots are target/role/account/origin scoped, one-use and reverified. Focused tests pass; full multi-case authenticated run not executed. |
| H10 | Partial implementation; focused acceptance passes | Approval schema, fingerprint-bound decisions, single-use receipts, API listing/decision and UI exist. A local/test-only, explicitly opted-in synthetic fixture supports one fixed `registration_submit` action; worker refreshes the decision, revalidates target/auth/owner, consumes the receipt once, dispatches, and records completed/uncertain. Fixture approval, API, and disposable PostgreSQL cross-session/replay tests pass. General sensitive-action approval and full integrated browser-to-report acceptance remain unverified. |
| H11 | Partial reuse only | Existing feature coverage/report/UI can be reused, but authenticated role matrix, protected coverage accounting and manual-HITL metrics are absent. |
| H12 | Not executed | Full 56-case adversarial matrix, three integrated successes/failures, deployment isolation/egress/resource measurements and human security review remain pending. HOSTED PRODUCTION NO-GO. |

## Current edits and decisions

H03 additions: controller.require_agent_control rejects calls before recorder
summaries; observations and direct event-log helper deny sensitive-phase access;
real-browser cleanup tests scan success/failure/timeouts and separate trace ZIPs.
Existing mock controller gains only the corresponding guard method.

H04 additions: browser/owner.py is a private adapter with actor/lease/generation/
expiry/sequence/rate checks, bounded input, transient CDP viewport frames, safe
errors and immediate revocation. No raw CDP endpoint or arbitrary method exposed.
browser/viewer_gateway.py has explicit Origin/WSS/session/one-time-ticket checks
and per-frame/input authority revalidation; it is intentionally unregistered
until real control-plane integration. Only local synthetic tests are authorized.

Normal local implementation is authorized by the current user request. An
irreversible hosting/vendor choice, dependency install, deployment, public target,
real credential or spend still requires separate permission.

## Commands and results

- From services/execution-orchestrator: ../../.venv/Scripts/python.exe -m pytest tests/test_browser_scoped_inspection.py tests/test_hitl_fixture.py -q --tb=short -p no:cacheprovider — 8 passed, 27.08s.
- Extended privacy/tool/fixture suite — 29 passed, 31.93s.
- Owner/scoped/tool suite — 28 passed, 32.65s.
- MARKETTWIN_TEST_DATABASE=1 uv run --no-sync --env-file .env python -m pytest services/control-api/tests/test_human_action_repository.py -q --tb=short -p no:cacheprovider — 1 passed, 2.87s; disposable local schemas.
- Ruff on changed owner/privacy modules and tests, with documented existing E501 baseline ignored — passed.
- Strict Pyright on owner/controller/tools/evidence/observations — 0 errors.
- Initial owner collection failed due to a test-module import; fixed before passing rerun. Initial lint/typing errors corrected; no runtime acceptance inferred from those failed checks.

Auth-session broker hardening: target host/domain cookie filtering was added and
the focused broker test passed. The focused browser privacy/owner/WSS/auth/reuse/
fixture suite passed 48 tests in 52.65s. Strict Pyright on touched HITL API,
repositories, verifier, broker, owner, gateway and suspension modules reported
0 errors. Ruff passed on those modules/tests. Frontend typecheck and production
build passed; Vite retains the existing >500 kB chunk warning.

Current focused checks: worker/auth/viewer/workflow 26 passed; fixture approval,
auth handoff and deep-run 17 passed; approval worker suite 45 passed; Control API
create suite 11 passed and targeted API suite 12 passed, 1 skipped because the
PostgreSQL opt-in was unset; isolated PostgreSQL approval/repository tests passed.
Auth handoff tests then
passed 2, including the new timeout regression proving a 40 ms action budget
survives an 80 ms simulated human wait. The case deadline is extended only by
actual bounded wait time (maximum 10 minutes); post-login action time remains
bounded by its original remaining budget. Frontend typecheck/build and viewer
component 1 passed; strict Pyright reported zero errors for changed worker/API
paths. Ruff has one known pre-existing E501 at `workflow/deep_run.py:394`; newly
introduced lint findings were corrected. `alembic heads` reports
`a1b2c3d4e5f6` as the single head. Offline `alembic upgrade head --sql`
rendered the full chain successfully to stdout with synthetic connection values;
no database was contacted or changed. A full frontend test-suite attempt
was interrupted without a result; do not count it. Build retains the existing
Vite >500 kB chunk warning.

Next: run user-owned end-to-end authenticated browser-to-report verification
after applying the migration and starting local services; retain the fixture-truth guard. Local setup
uses matching API/worker internal secrets, loopback worker bind on port 8020,
`http://localhost:5173` as the allowed origin, and same-origin Vite WebSocket
proxying. Run the
database-backed worker attach test and authorized synthetic authenticated E2E
through report. Until those pass, H08 and H12 and end-to-end acceptance stay incomplete. Preserve
all prior edits; do not mark phases complete without their acceptance tests.


</details>

## Appendix C: historical viewer transport review

Historical/design material follows. Current operational status is recorded above.

<details>
<summary>Expand the complete preserved reference</summary>

# H04 viewer transport review — 2026-10-14

## Scope and evidence

This review compares the two H04 candidates named in the HITL implementation plan: a headful browser exposed through noVNC and a restricted Chrome DevTools Protocol (CDP) channel. It uses the repository inventory recorded in `HITL_H00_RECONCILIATION_2026-10-14.md` and the H03 implementation. This is a threat-model review, not a measured benchmark. The application now uses a restricted CDP owner behind an authenticated same-origin WSS gateway; no latency/resource benchmark or full authenticated end-to-end result is claimed.

## Comparison

| Criterion | Headful browser + noVNC | Restricted CDP |
|---|---|---|
| Browser ownership | Can present the same browser process/context if that process is launched headful on the isolated display. Must prove exact Playwright `BrowserContext` ownership and lease-bound routing. | Can attach to the browser process, but CDP is a powerful control/debugging protocol. A broker must constrain targets and methods; a raw debugging endpoint would expose more than the active tab/session. |
| Credential and page-data exposure | Human sees rendered pixels and can type. The server-side display path must not record or persist frames; disable clipboard/file transfer and unrelated desktop surfaces. | Protocol clients may read DOM, cookies, storage, network, and page state depending on enabled methods. Method allowlisting, target scoping, and no raw endpoint/token disclosure are mandatory. |
| Least privilege | Input and pixel streaming can be bounded to the isolated browser display. Desktop isolation and websocket authentication remain critical. | Potentially narrower at the transport layer only if method/target policy is complete and tested; mistakes can expose browser-wide data or permit arbitrary execution. |
| Integration cost | Requires headful display server, noVNC/websockify or equivalent, TLS/WSS termination, and display lifecycle management. Presence of these dependencies in the current local environment has not been verified. | Avoids desktop stack, but requires a secure CDP proxy/broker, strict protocol filtering, session binding, and compatibility testing with Playwright's owned browser. No such proxy is present in the H03 changes. |
| Performance and acceptance evidence | Pixel encoding and streaming may add CPU/bandwidth. No measurements available. | Usually avoids full desktop video encoding; protocol event/input behavior and added proxy overhead are unmeasured. |

## Implemented local choice

For this product's human-in-the-loop goal, prefer **headful browser + noVNC** only if H04 proves that the viewer controls the exact browser instance and authorized context, uses a lease-bound authenticated WSS path, disables clipboard/file transfer and recording, and cannot see another desktop or session. This keeps the human interaction surface closer to ordinary visible browser input and avoids exposing CDP's broad inspection/execution surface to the viewer. It introduces display and streaming infrastructure, so it must be shown to reuse existing local resources or receive explicit approval before adding dependencies or infrastructure.

The implementation chose the restricted-CDP path. It keeps the CDP endpoint private and allows only bounded input/viewport operations through the owner adapter; WSS tickets are one-use and lease-bound, and authority is rechecked for frames and input. A direct CDP websocket is not exposed. This choice still needs the integrated database-backed browser claim and synthetic fixture acceptance path before it can be called fully verified.

## Gate status

**H04 implementation is partial; integrated acceptance is not passed.** Focused evidence now includes worker listener startup/shutdown, exact live-handle registration, signed internal request freshness/body/replay checks, WSS gateway one-time ticket and cancel-before-connect tests, plus React viewer component test. The API/worker DB-backed claim-to-stream path, authenticated fixture walkthrough, credential canary scan across integrated sinks, and performance/resource measurements remain unverified. Local worker binds to loopback:8020; production requires a private owner listener behind a trusted same-origin WSS reverse proxy. No deployment or new paid transport was added.


</details>

## Appendix D: historical baseline reconciliation

Historical/design material follows. Current operational status is recorded above.

<details>
<summary>Expand the complete preserved reference</summary>

# HITL implementation reconciliation (H00)

Date: 2026-10-14  
Branch: `feat/batch-1-aws-observability`  
Baseline/current commit: `8075327a8a0681edaa0ac6d9273362c7eb65e264`  
Pre-existing worktree changes: deletion of `MARKETTWIN_KNOWLEDGE_WORKER_UI_BRIDGE.md`, untracked master plan, and the deep-mode `RunFlowPanel.tsx`/continuity edits from the preceding MKT task. Preserved.

## Reconciliation

| Area | Status | Verified behavior and gap | Risk / next proof |
|---|---|---|---|
| Browser context | CODE VERIFIED | `BrowserController.create_session` creates a fresh Chromium context and stores a process-local session keyed by UUID. `begin_human_control`/`end_human_control` toggle this same session. | No viewer or cross-process owner exists; a UUID in Postgres cannot reattach after worker loss. |
| Input fencing | CODE VERIFIED | `_ensure_agent_control` denies controller actions only when session state equals `human_control`; controller methods share a session lock. | No lease actor/generation is supplied to each input, and no central claim/revoke API exists. |
| HITL persistence | CODE VERIFIED | `execution.human_action_requests` requires execution and browser session; `human_control_leases` stores user/token hash/expiry/release. | No claim lifecycle repository/API was found; no DB uniqueness constraint limits unreleased leases per browser; no lease generation. |
| Run pause/resume | CODE VERIFIED | Run states and SQL constraints have no `awaiting_human`; case/journey executors close the browser in `finally`; worker handles a complete run per command. | Durable same-context suspension requires an owner surviving Kafka worker suspension and a cross-process coordination decision. |
| Capture privacy | CODE VERIFIED | Beginning human control stops trace and sets `capture_enabled=False`; screenshot helpers honor that flag. | Browser callbacks continue appending console/page/request errors, old buffers are not cleared, and event logs serialize cumulative buffers. No canary scan exists. Credentials cannot safely be entered through a viewer today. |
| Auth / roles | CODE VERIFIED | No approved auth verifier contract, synthetic IdP, protected fixture, or authenticated discovery gate found. | Protected coverage must remain blocked until an application-defined verifier proves identity and role. |
| API/UI/viewer | CODE VERIFIED | `HumanActionPage` is a placeholder. No human-actions routes or authenticated viewer gateway found. | Transport, viewer authorization, cross-origin policy, and secret-frame handling remain architecture/security gates. |
| Deep feature testing | CODE VERIFIED | Versioned `deep_feature_v1` plan, deterministic case executor, exact assertions/evidence, evaluator and case UI already exist. | Reuse these; do not conflate authentication with feature coverage or claim LLM persona execution. |
| Local fixture | CODE VERIFIED | Deep registration fixture and independent eight-case manifest exist; no protected authentication behavior exists yet. | H01 adds a synthetic local-only auth fixture; public-site testing is not part of this phase. |

## Decisions and scope

Use the existing local Chromium/Playwright fixture and `local_development` policy;
no new service, dependency, cloud resource, real identity, or external target.
Synthetic credentials exist only inside the fixture and its tests. Human browser
control is not enabled by this reconciliation. Defer WSS/viewer selection, browser
owner process topology, auth-state persistence, and any change to production
secret-handling policy until a concrete security design review. Local phases may
continue where they do not expose credentials or weaken existing network policy.

## Baseline validation

Command: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests/test_browser_scoped_inspection.py tests/test_deep_testing_fixture.py -q` from `services/execution-orchestrator`  
Result: **12 passed in 47.10s**. This is current baseline behavior, not HITL security validation.

## Phase status

H00: baseline and gap register recorded; PASS.  
H01: synthetic protected fixture and independent browser oracle in progress.  
H02–H12: NOT STARTED; advance only after dependency gate and safe local proof.



</details>

