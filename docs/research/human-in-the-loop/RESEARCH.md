# Human assistance in MarketTwin: research, architecture, and executable checks

Research date: 20 September 2026. Scope: the local `refactor/python-browser-controller` checkout, research papers, and primary implementation documentation. This is a targeted review, not a claim to have read every paper or every website. Methods, results, and limitations were examined for the four core papers below; other papers were screened as indicated. Prototype results are separated from proposed production behavior.

## Recommendation

Build human assistance as a durable, verified transfer of control around the existing Python browser controller. Combine selective escalation inspired by KnowNo with the same-session human/agent interaction explored in CowPilot. Use collaboration benchmarks to evaluate whether assistance improves the result without hiding agent failures. Add ordinary concurrency, authorization, and recovery engineering: these papers do not supply a complete production protocol.

The useful contribution for MarketTwin is this integration. It is not yet a new research algorithm with demonstrated novelty, universal access, or an optimality guarantee. Quality must be an acceptance constraint and a measured outcome. Human involvement can introduce errors as well as resolve them.

There are three different interactions:

| Interaction | Example | Required mechanism |
|---|---|---|
| Clarification | Which approved test account or billing period should this mission use? | A structured answer bound to the unresolved question |
| Action approval | May this exact sandbox action execute? | A decision bound to the actual action, parameters, environment, and current policy |
| Private browser takeover | The account owner completes login, MFA, or another interactive challenge | Exclusive, temporary control of the same browser session, with private input and verified return |

An `ask_human` tool alone implements none of the full browser lifecycle. A generic confirmation dialog cannot safely replace all three interactions.

## Research that changes the design

| Primary source and reading depth | Useful finding | Application and limits |
|---|---|---|
| [CowPilot: A Framework for Autonomous and Human-Agent Collaborative Web Navigation](https://arxiv.org/html/2501.16609v1), 2025. Core sections examined. | Explores humans pausing, overriding, and resuming web agents within a shared task. Its limited study reports high collaborative completion. | Borrow same-session takeover and explicit action attribution. Do not transfer its performance figures to MarketTwin. Its timed automatic action execution is not approval for a sensitive action. Its processing of human interaction records cannot be copied for private credential entry. |
| [Robots That Ask For Help / KnowNo](https://arxiv.org/html/2307.01928), CoRL 2023. Core method, assumptions, and evaluation examined. | Uses calibrated sets of candidate plans to decide whether ambiguity needs human help. | Borrow calibrated abstention after collecting representative data. The statistical coverage assumptions and episode construction matter; guarantees do not automatically transfer to changing websites, incomplete DOM observations, failed browser actions, or mistaken humans. |
| [Collaborative Gym](https://arxiv.org/html/2412.15701v1), 2024. Framework and evaluation sections examined. | Models asynchronous collaboration and evaluates interaction processes as well as final task outcomes. | Measure interruptions, communication, and human effort alongside completion. Its task environments and studies do not establish browser authentication or payment safety. |
| [HiL-Bench: Do Agents Know When to Ask for Help?](https://arxiv.org/html/2604.09408v1), 2026 preprint. Task design and asking metric examined. | Tests whether agents recognize missing, ambiguous, or conflicting information; evaluates useful questions and blocker coverage. | Measure both unnecessary questions and missed blockers. A model having a help tool is insufficient. This is not a browser takeover or credential-isolation evaluation. |
| [Consistent Estimators for Learning to Defer to an Expert](https://arxiv.org/abs/2006.01862), 2020. Abstract screened. | Studies jointly learning predictions and deferral to an expert. | A later escalation policy should learn relative agent/human performance and cost, not assume every human answer is correct. Not implemented here. |
| [Principles of Mixed-Initiative User Interfaces](https://www.microsoft.com/en-us/research/publication/principles-mixed-initiative-user-interfaces/), CHI 1999. Publisher summary and paper consulted. | Frames collaboration between automation and direct human control. | Treat attention and interruption as costs. Preserve understandable control and recovery. |
| [HAS-Bench](https://arxiv.org/abs/2607.04329), 2026 preprint. Abstract screened. | Evaluates human-agent systems with configurable participation. | Make human roles and authority explicit experimental variables. Its results are not a validation of this proposed implementation. |
| [DiscoBench](https://arxiv.org/abs/2606.27669), 2026 preprint. Abstract screened. | Studies clarification in ambiguous deep-search tasks. | Distinguish information that further observation can uncover from information only the user can supply. Transfer to browser testing remains a hypothesis. |

The strongest combination is CowPilot for interaction, KnowNo for the later escalation policy, and Co-Gym/HiL-Bench for evaluation. No reviewed source eliminates the need for application-specific postconditions, a browser input gateway, or durable state transitions.

## What the current code actually supports

Paths below are relative to the repository root. These are code observations, not paper claims.

| Area | Current evidence | Consequence |
|---|---|---|
| Controller ownership | `services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/controller.py`: `_ensure_agent_control` precedes acquisition of `session.lock`, including `get_state` around lines 342–343; handoff acquires that lock around line 753. | A queued operation can pass the check before human takeover and execute afterward. The included demo reproduces this with the actual controller and a fake session. |
| Browser lifetime | `workflow/journey_executor.py`: `InMemoryRunner` around line 155, one timeout around line 180, unconditional browser cleanup in `finally` around lines 247–253. | Returning or timing out while awaiting a human can close the browser. Pause must become a durable outcome with its own lifecycle. |
| Browser persistence | Controller sessions live in an in-process dictionary; a fresh browser context is created per journey. | A database reference does not preserve a live page, JavaScript state, or an authenticated browser after process loss. |
| Human capture | `browser/human_control.py` stops tracing and disables capture during takeover. Existing console/error collection needs broader suppression or sanitization. | Screenshot suppression alone is not credential isolation. The earlier website-access probe demonstrated the console capture gap with synthetic data. |
| Database states | `packages/database-python/src/markettwin_database/models/execution.py`: execution states omit waiting for human; browser states allow starting/open/closed/failed; human request statuses are pending/leased/completed/cancelled/expired. | In-memory `human_control` cannot simply be persisted as an allowed browser state. Explicit migration and state mapping are required. |
| Lease storage | `HumanControlLease` stores ownership, hashed token, expiry and release, but has no browser control epoch or unique active lease per browser. | The table alone does not prevent competing controllers or stale input. |
| User interface | `apps/web/src/pages/runs/HumanActionPage.tsx` is a future-stage placeholder. Controller defaults to headless Chromium. | A working private browser viewer and authenticated handoff flow still need implementation. |

The ownership race is a concrete finding. It is not a demonstration of a deployed exploit. The reproduction uses controlled scheduling and a fake observation method; no private user data was involved. Production code has not been changed in this research task.

## Proposed algorithm

Use a rule-based policy first. Introduce learned or conformal escalation only after collecting representative, labeled decisions.

1. **Classify the blocker.** An action outside policy stops. Missing browser evidence triggers bounded evidence expansion. A user-only fact triggers clarification. A private credential step triggers takeover. An authorized action needing approval gets a narrowly scoped approval request. Repeated failure becomes assistance or an unresolved result, never a guessed success.
2. **Stop admitting agent operations.** Record pause intent before waiting for the current operation to finish. Perform the final state/ownership check inside the same lock used for control changes. An operation already sent to the website may have taken effect; reconcile its outcome instead of assuming cancellation undoes it.
3. **Persist the request and checkpoint.** Bind it to tenant, run, journey, browser identity/generation, policy version, blocker, expected postcondition, and the exact pending invocation. Suspend model execution. Human wait time uses a separate deadline from active agent time.
4. **Grant one authenticated human a short lease.** Every browser input is checked at the server against owner, scope, expiry, and control epoch. Competing or old leases fail. Starting a private stream waits until capture is disabled and agent operations have drained.
5. **Treat “Done” as a verification request.** Revoke human input first. An internal verifier checks the expected state and whether ordinary evidence capture can safely resume. For login, prefer a trusted account/tenant signal and required page state; a changed URL alone is insufficient.
6. **Resume with a new control epoch and a small result.** Provide only approved facts such as `authentication_verified`, allowed account role, changed page state, evidence references, and attribution. Do not replay typed passwords, OTPs, or every mouse event into the model.

Proposed production states:

```text
AGENT -> PAUSING -> WAITING_FOR_HUMAN -> HUMAN_CONTROL -> VERIFYING -> AGENT
                           ^                |               |
                           +--- expiry -----+--- failed ----+

Any nonterminal state -> CANCELLED or CONTEXT_LOST
```

The prototype represents PAUSING with a pause-intent flag and handles a subset of these states. It does not implement cancellation, durable checkpoints, or the viewer.

An epoch is a monotonically increasing control generation. Every queued agent command and human input carries the generation it was authorized under. Changing ownership invalidates earlier generations. A database lease without enforcement at the actual browser input boundary cannot stop a stale connection.

The optimization target is total cost: model work, human attention, waiting time, and browser infrastructure, subject to quality and authorization constraints. This is a design objective, not a solved global optimization problem. In particular, saving model tokens by asking the user to perform the entire task would defeat the product goal.

For later calibration, collect candidate actions, observed blockers, actual outcomes, and human corrections. Split calibration/evaluation by website or task family to expose generalization failures. A non-singleton calibrated candidate set can trigger assistance; even a singleton remains subject to policy and execution verification. Do not use the model saying “95% confident” as a calibrated probability. The browser setting needs its own assumptions and validation before adopting KnowNo-style statistical claims.

## Access and browser delivery

For a hosted first version, retain Python/Playwright as the browser authority and run a headed browser in an isolated desktop from the beginning of a potentially assisted journey. Present that desktop through an authenticated viewer. [noVNC](https://novnc.com/info.html) is a browser VNC client; it requires a compatible server/transport and does not itself create a browser session or application authorization policy.

| Delivery option | Fit | Main work and limitations |
|---|---|---|
| Isolated headed browser with noVNC | Recommended hosted starting point | Desktop/display, VNC transport, authenticated gateway, session isolation, stream teardown and input gating. Protect the full desktop, not only the web page. |
| Browser-only screencast with forwarded input | Possible narrower custom viewer | More engineering for rendering, input, scaling, popups, tabs, reconnects and browser/native dialogs. Prototype compatibility before choosing it. |
| Local browser integration/extension | Useful for accounts requiring a user's local environment | Different deployment and trust model; user installation, permissions, browser-state isolation, and controller coordination. |

The [noVNC API](https://novnc.com/noVNC/docs/API.html) exposes `viewOnly`; treat this as a client behavior, not an authorization boundary. The gateway must reject unauthorized input regardless of client settings. Avoid exposing raw VNC or browser debugging endpoints directly. Authenticate stream establishment, validate origin/session scope, use encrypted transport, and revoke both the input channel and private display access when the lease ends.

Keep the browser host alive independently of a single ADK invocation. This can remain Python; a second competing browser controller is unnecessary. A restarted orchestration worker can reconnect to a surviving host after validating its generation. If the browser itself is lost, mark that fact. Recreating storage/cookies does not recreate every in-flight application state; a replacement is a new attempt with explicit continuity limits.

Human assistance expands practical access but does not imply “all websites.” Approved network dependencies still need to work: identity-provider redirects, APIs, payment frames, popups, and resource origins. Device-bound authentication and some anti-automation challenges may remain unavailable in a remote browser. Use approved test accounts and site-supported test modes when possible; report access failures honestly.

For payments, distinguish reading public prices, viewing an authorized account's billing page, and executing a sandbox checkout. They have different postconditions. A login takeover is not blanket authorization to buy something. Approval must bind to the actual structured action and current amount/environment when relevant; a page's instructions or an LLM summary cannot grant permission. Do not enable unrestricted agent payments merely because a human helped with authentication.

## Persistence and framework integration

Extend the existing models before adding UI-only controls:

- Execution pause reason, active-time accounting, request deadline and terminal outcome.
- Request kind, phase, blocker ID, expected postconditions, allowed responder role, approval scope, policy version, browser identity and generation.
- Control epoch and owner on the browser host, linked to the persisted lease.
- Invocation/session/tool-call identifiers and last completed operation, plus an idempotency key for answering, claiming, completing and resuming.
- Minimal audit events with actor, transition, timestamps, safe reason, and evidence references.

Acquire claims using a short database transaction that locks the appropriate browser/request row, validates eligibility, retires an expired lease, and inserts the new lease. A partial unique constraint for unreleased leases can enforce one such row per browser. Expiration must be handled explicitly; do not attempt a time-dependent uniqueness predicate. PostgreSQL documents transaction-scoped [row locks](https://www.postgresql.org/docs/current/explicit-locking.html). Never hold a database transaction open while the human works.

Use an outbox or equivalent durable event mechanism for notifications/resume scheduling. Repeated completion calls should return the same outcome, not create multiple resumptions. Cross-process fencing at the host must agree with persisted ownership. A worker crash after a browser action but before recording its result creates an uncertain outcome: observe/reconcile before replaying side effects.

ADK already exposes [tool confirmations](https://adk.dev/tools-custom/confirmation/), including structured payloads. Its current documentation labels the feature experimental and explicitly lists `DatabaseSessionService` and `VertexAiSessionService` as unsupported. Therefore, adding `require_confirmation=True` is not a demonstrated durable implementation for MarketTwin. Validate the installed-version integration in a focused spike; retain an application-owned request state machine and authorization boundary.

ADK's [resume documentation](https://adk.dev/runtime/resume/) uses invocation identity and saved events, warns that tools may execute more than once, and requires extra work for custom agents. Preserve the matching invocation/tool-call identifiers and make replay-sensitive tools idempotent or reconcile their results. This machinery does not preserve a live browser by itself.

[LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) demonstrate checkpointed pause/resume, but interrupted nodes restart from their beginning and preceding side effects must be designed for replay. Borrow the lifecycle principle; a framework migration is not required solely to add a human viewer.

## Private input and evidence quality

The human necessarily sees the private live browser stream. That is separate from storing screenshots or sending pixels/text to a model. During private takeover, suppress stored screenshots, video, traces, DOM snapshots, tool observations, console/error payloads, request bodies, analytics, and raw input events that can expose secrets. Ensure buffering and automatic telemetry cannot flush private content afterward.

Resume only after verification and a capture-safety check. Clearing a password input is not a universal guarantee: secrets can appear in URLs, banners, logs, or page text. Production needs explicit sanitization, minimal verification reads, and synthetic-canary tests across every capture sink. Do not request credentials through the normal agent chat.

Distinguish help that establishes a prerequisite from help that changes the tested behavior. If the mission is to evaluate login usability, a human completing login means that segment was assisted; it cannot count as autonomous success. If login is a precondition for evaluating the billing page, record verified setup separately and evaluate the downstream task normally. Human navigation that reveals a hidden menu or resolves confusing copy is intervention evidence, not proof the original persona found it independently.

Every criterion should retain its evidence and status: verified pass, verified failure, unresolved, or assisted where appropriate. Reaching a page after intervention must not erase the original blocker or upgrade unrelated criteria. Privacy-induced evidence gaps should be visible in the report.

## Validation completed here

The following files are an executable research specification, not production integration:

- `handoff_protocol.py`: in-memory ownership, pause, lease, verification and escalation rules.
- `test_handoff_protocol.py`: 19 passing tests covering queued/in-flight operations, concurrent claims, wrong owner/context, expiry, stale generations, failed verification, capture suppression, context loss, and escalation categories.
- `handoff_demo.py`: reproduces the current controller race and exercises a scripted takeover on a local synthetic page.
- `handoff-demo-results.json`: recorded output from the run.

Observed results:

| Check | Result |
|---|---|
| Actual controller with controlled fake session | Queued observation executed in `human_control`; race reproduced |
| Proposed protocol, local Chromium fixture | Same page object and browser-context cookie retained |
| Human “Done” | Entered `verifying`; did not immediately resume the agent |
| Fixture identity and capture-readiness checks | Passed, followed by verified resume |
| Old agent generation after resume | Rejected |
| Synthetic secret in prototype audit | Absent |
| Paid model/API calls | Zero |

All network requests in the browser demo are intercepted; only the synthetic fixture is fulfilled. “Human” input is scripted. This does not validate real SSO, MFA, CAPTCHA, a viewer, WebSocket authorization, database concurrency, process recovery, production redaction, or end-to-end ADK resume. The in-memory object trusts its server-side callers for identities, time and verification; it must not be exposed as an API security layer.

Reproduce from the repository root:

```powershell
.venv/Scripts/python.exe -m pytest docs/research/human-in-the-loop -q -o addopts= --import-mode=prepend -p no:cacheprovider
.venv/Scripts/python.exe docs/research/human-in-the-loop/handoff_demo.py
```

## Production acceptance experiments

Use deterministic fixtures before external accounts: login success/failure, wrong tenant, expired OTP, popup auth, approved cross-origin redirect, expired session, and a sandbox payment iframe. Add malformed/stale/duplicate messages, two users claiming simultaneously, two workers resuming, refresh/disconnect, browser-host loss, and cancellation during an in-flight operation. Every private capture channel needs synthetic-secret assertions. The race reproduction should become a production regression test when the controller is fixed.

Compare four conditions on the same task families: current autonomous baseline, optimized context without assistance, rule-based assistance, and later calibrated assistance. Include both seeded defects and clean pages. Randomize conditions/order in real-user studies and separate development from evaluation sites. Report intervals and per-family results; a better average can hide regressions on payments or accessibility.

Measure task/criterion success, defect recall, false passes, evidence completeness, useful-question precision, blocker recall, human interventions and active minutes, waiting time, model tokens/cost, browser retention cost, and recovery success. Report assisted completion separately from autonomous completion. Do not count repeated “Are you done?” polling as useful model work.

Quality release gates should include no known unauthorized control path, no detected synthetic-secret capture, no duplicate replay of sensitive actions, and no regression in the agreed critical-criterion suite. Finite tests cannot establish zero possible errors. Broader statistical non-inferiority requires a predefined margin, sample size and held-out evaluation; none is claimed by these 19 tests.

## Implementation order

1. Fix controller checks under the lock and introduce pause intent/control generations. Close all private-capture gaps. Add regression tests to production tests.
2. Add database migrations, application-owned handoff service and authenticated claim/answer/complete/cancel endpoints. Validate concurrency and idempotency against PostgreSQL.
3. Separate live browser retention from invocation cleanup. Add the private viewer and enforce leases at its server-side input boundary.
4. Integrate pause/resume with the installed ADK version, preserve invocation identity, and test crashes/replays. Add verified resumption and accurate evidence attribution to the run UI.
5. Evaluate the rule-based policy with real users and representative sites. Only then investigate calibrated or learned escalation if unnecessary interruptions remain a material cost.

This sequence addresses a demonstrated controller flaw first, delivers useful assistance without speculative training, and leaves a measured path toward smarter escalation. The research prototype is complete; production rollout, external-site validation and calibrated uncertainty modeling remain separate implementation work.
