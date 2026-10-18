# MarketTwin — Complete Repository Assessment, Live Execution, Agents UX and Secure HITL | One-Stack Master Specification

## Revision 3 — repository-wide inventory and integration audit added to the previous LangSmith-only master spec

**Revised:** 2026-10-17 (US Central) / 2026-10-18 UTC  
**Target repository:** `Sreenav14/Market-Twin`  
**Audited remote branch:** `feat/batch-1-aws-observability` at `38431448ded7357c6d7b6010baa0d4c4ad773146`  
**Audience:** MarketTwin owner, frontend/backend engineers, independent reviewer, Codex implementation agent  
**Status:** **Repository-wide tree inventoried; selected critical paths source-reviewed; no full-source line-by-line certification or locally executed integration checks. Updated research and implementation specification only.**  
**Scope:** Live browser observation, comprehensible execution/Agents UX, contextual HITL authentication and intervention, safe pause, trustworthy findings/evidence, regression/security acceptance.  
**Out of scope now:** adding third-party observability platforms, replacing browser infrastructure, adopting another agent/orchestration framework, configurable 80-persona execution, unrestricted production SSO/CAPTCHA, and redesigning unrelated pages.

> **Critical source-of-truth rule:** This document reflects the pushed branch inspected above, not necessarily the local checkout. Before any implementation, inspect `git status`, `git rev-parse HEAD`, active processes, current Alembic head, configuration, migration state, and the latest `docs/hitl/README.md`, `docs/hitl/LIVE_EXECUTION_IMPLEMENTATION_PLAN.md`, `docs/SESSION_HANDOFF.md`, and `docs/ui/VERIFICATION.md`. Never overwrite uncommitted work or assume an older plan's “missing” items are still missing. Existing synthetic pass reports are agent-authored evidence, not tests independently rerun during this research.

## READ THIS FIRST — audit scope, honesty and evidence

This is the **single replacement document** for the earlier Live Execution / Agents UX / HITL master specs. It retains their useful implementation design and adds a comprehensive cross-service assessment, previously overlooked wiring checks, honest implementation-status corrections and a required local exhaustive-code validation procedure. **Use this file, not the earlier drafts, for further planning.**

**Repository examined:** `Sreenav14/Market-Twin`, remote branch `feat/batch-1-aws-observability`, commit `38431448ded7357c6d7b6010baa0d4c4ad773146` (the latest HEAD visible to this review). The tree contains **672 tracked blobs totaling approximately 4.60 MB**, of which **573 have source/config-format extensions** (`py`, `ts`, `tsx`, `css`, `html`, `sql`, `json`, `toml`, `yml`) and **175 are test-related paths**; these categories overlap. It includes **418 Python**, **84 TSX**, **32 TypeScript**, **67 Markdown** files and **20 migration-version files**. The 672 also include manifests, docs, placeholder files and locks.

**What was really checked:** The complete remote tree structure and per-subsystem file counts were retrieved; core frontend, API, HITL, browser, workflow, evaluator, telemetry, test, environment and infrastructure files were fetched and inspected for actual interfaces, control flows and status claims. Historical handoff notes and the former master spec were compared to relevant current source. **Not all 672 files have been read line-by-line.** A literal, defensible all-code certification requires cloning the full repository—including unpushed local changes—then performing a tracked-file-by-file review, static/tool tests, security review and integrated execution. The final sections specify exactly how to do that. No source changes, tests, local secrets inspection or runtime/browser interaction were performed in this review.

**Evidence vocabulary used throughout:**
- **C (confirmed at pinned source):** precise code/API/UI contract observed in a retrieved file; it is not proof of live deployment.
- **D (documentation claim only):** historical synthetic test/report assertion, not independently rerun here.
- **R (risk to investigate):** plausible bug or inconsistency requiring a local reproduction/security test; not a confirmed exploit.
- **P (proposed):** deliberate product/architecture recommendation, not implemented.
- **U (unverified):** data or runtime capability unavailable to this review, including private `.env` values and live LangSmith delivery.

**Critical correction to prior wording:** The existing `docs/hitl/LIVE_EXECUTION_IMPLEMENTATION_PLAN.md` and `docs/SESSION_HANDOFF.md` contain older statements that worker observation methods/tests are absent. On the pinned pushed branch, the worker has `ControllerBrowserOwner.observe`, signed internal `/observe`, observer authorization and `tests/test_live_browser_observation.py`. **Do not rebuild those pieces; independently test and finish their integration.** The public Control API observation route and React Live Execution screen remain absent.

**All-code audit is a gate, not a claim:** Section 19 is a mandatory executable worklist for the local checkout. No developer or agent may use this document as evidence of 100% source coverage or production readiness without attaching the completed coverage manifest and command outputs.

---

## Single-stack decision — read first

**MarketTwin's implementation stack remains:** React + TypeScript + Vite, FastAPI/Python, Google ADK, Python Playwright/Chromium, PostgreSQL/Alembic, Kafka/outbox, MinIO/S3-compatible artifact storage, existing MarketTwin authentication and HITL browser owner, **OpenTelemetry + OpenInference instrumentation**, and **LangSmith as the selected agent-tracing destination**. This document proposes no other observability SaaS, browser service, sandbox, agent framework, UI framework, or data store.

**Verification status matters:** repository code *proves an OTLP/HTTP exporter and Google ADK instrumentation exist*, but **does not prove that the developer's `.env` points at LangSmith, that authentication headers are correct, or that a trace reaches the LangSmith workspace**. The target integration must be tested. The client-facing execution timeline remains backed by MarketTwin's own authoritative database—not by scraping or relying on LangSmith dashboard access.

**Why no parallel tracing stack:** One diagnostic destination means one set of correlation conventions, redaction rules, user guidance, ownership and operational checks. Existing telemetry should be correlated with product actions rather than replaced. Technical trace views belong behind an Advanced diagnostics panel.

---

# 0. Executive decision: what to build and why

**Recommendation: Proceed with a focused, evidence-first Live Execution workbench, including an understandable tester/journey hierarchy and contextual HITL.** Preserve the existing React/TypeScript, FastAPI, Python Playwright, PostgreSQL, Kafka/outbox, and worker-owned browser architecture.

The user's desired experience is:

1. Create an authorized test with a specific goal.
2. See **who/what** is testing (a clearly labeled simulated tester, goal, and execution mode).
3. Watch the **actual browser** while it is operating; see recorded actions and their statuses.
4. Understand what the system is doing, **why**, and whether the user needs to act.
5. When a supported authentication/MFA/SSO/CAPTCHA blocker is **actually encountered**, see a prominent **Human assistance required** state; take control of the same browser; enter credentials into the actual target website via the protected viewer; release control.
6. If needed, **request** a cooperative pause at a safe boundary, then optionally take over; never imply instant interruption of a submitted action.
7. Resume only after the browser owner and policy layer confirm safe continuation; maintain evidence integrity and never silently replay a side effect.
8. Inspect verified outcomes, genuine product defects, test-specification defects, unverified assertions, permission blocks and human involvement separately.

**Design thesis:** MarketTwin's identity is **evidence-backed, supervised software testing by simulated journeys**, not a chat-first AI dashboard, an animated agent theater, or fabricated virtual customer research.

**Priority order:**

- **P0: Make execution truthful and visible.** An interactive-looking UI is not useful if it displays stale frames, invented reasoning, or a browser different from the selected journey.
- **P0: Make assistance obvious and safe.** Human authentication should occur in the same isolated browser context, with exclusive human ownership, protected transport, privacy controls and verified continuation.
- **P1: Make Agents intelligible.** Prioritize tester, goal, journey, verified behavior and evidence; expose model settings/YAML only for advanced operators.
- **P1: Add cooperative manual pause.** This is a genuine backend control-plane change, not a CSS/button change.
- **P1: Prove the end-to-end journey.** Build and test local synthetic fixtures in both execution modes, including seeded defects, credentials and negative/race cases.
- **Later:** Higher-frame-rate streaming, dynamic populations, simultaneous agent pools, sandbox providers, comparative versions and synthetic persona opinions.

## Honest product appraisal

The repository contains meaningful code for browser ownership, signed internal services, human leases, executor workflows, step persistence, evaluation, Kafka and API/UI integration. This is **more substantial than a static AI-themed front end**. However, the repository's `docs/PRODUCT_AUDIT_2026-10-16.md` says **REFOCUS**: stronger defect discovery and advantage over conventional Playwright are **not yet proven**. A live workbench improves controllability and trust; it does not itself prove that model-generated assertions are correct or that synthetic opinions represent people.

---

# 1. Detailed UI and observability research — only sources relevant to MarketTwin's stack

This update intentionally **removes competing platform comparisons, screenshots, dependencies, and recommendations**. It derives interaction principles from MarketTwin's existing application, its chosen runtime and tracing tools, established usability/accessibility principles, and security documentation. These are documented capabilities and design guidance; I did not open the private running product during this review.

## 1.1 Sources and what we can correctly conclude

| Existing stack / applicable standard | Source examined | Supported implementation insight | Boundary that must remain clear |
|---|---|---|---|
| **MarketTwin React UI** | Audited routes/components at pinned commit; prior repository UI spec | Preserve existing tokens and pages; replace the Activity placeholder with one coherent browser/step/assistance experience | Static React routes do not mean backing APIs already exist |
| **Python Playwright** | [Trace Viewer](https://playwright.dev/python/docs/trace-viewer), [Tracing API](https://playwright.dev/python/docs/api/class-tracing) | Recorded actions, selected-step details, timestamps and before/after evidence are useful patterns | Raw traces/DOM/network data are not safe to expose indiscriminately, especially at login |
| **Python Playwright authentication** | [Official authentication guide](https://playwright.dev/python/docs/auth) | Browser context can carry authenticated cookies/state; such state is sensitive and requires scoped reuse/disposal | Manual sign-in does not prove role, account identity or broad permission |
| **Google ADK + OpenInference** | MarketTwin `observability.py` using `GoogleADKInstrumentor` and `TraceConfig` | Agent/model-tool spans can be automatically instrumented while contents are hidden by default | Span presence never means an application assertion passed |
| **OpenTelemetry / OTLP HTTP** | [OTLP exporter specification](https://opentelemetry.io/docs/specs/otel/protocol/exporter/), [Python exporter configuration](https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html) | Existing Python exporter can send spans to the configured traces endpoint; preserve service names, correlation IDs, minimal metadata | Kafka messages and DB rows are authoritative business state; telemetry is diagnostic, often sampled or delayed |
| **LangSmith** | [Trace with OpenTelemetry](https://docs.langchain.com/langsmith/trace-with-opentelemetry), [Observability concepts](https://docs.langchain.com/langsmith/observability-concepts) | LangSmith can ingest non-LangChain OpenTelemetry traces, including mapped OpenInference attributes | Actual MarketTwin → LangSmith delivery must be verified in the configured project; dashboard access is separate |
| **WCAG 2.2** | [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/), [Status-message guidance](https://www.w3.org/WAI/WCAG21/Techniques/aria/ARIA22) | Visible status, keyboard-operable takeover, non-color-only information, focus management and announced state changes | Automated accessibility scans alone do not certify usability |
| **Security boundaries** | [OWASP Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) and [Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) | Credential values, token-bearing URLs and session data must be excluded from log/trace/evidence surfaces | MarketTwin's remote browser still processes keystrokes and authenticated session state; do not promise zero handling |

## 1.2 Interface interaction patterns backed by the above

**Pattern A — status before detail.** The first screen should answer: current phase, active tester/goal, what happened last, what happens next, and whether action is required. Show exact source-recorded states rather than an invented progress percentage.

**Pattern B — task, browser, timeline as one workbench.** Place the selected journey and goal beside the *actual* browser view and chronological recorded operations. Clicking a step brings up evidence and what the result supports. A readable hierarchy beats a raw stream of JSON spans or animated prose.

**Pattern C — read-only observation versus privileged interaction.** A passive frame capture is not a human-control lease. Render it with a component incapable of sending browser input. Human input is exposed only after an explicitly authorized claim on the exact owned browser context.

**Pattern D — action and result are different.** Browser action completed, expected outcome satisfied, evaluation complete and website defect confirmed are separate facts. They must not collapse into one green success icon.

**Pattern E — show problems with appropriate agency.** “Human assistance required” must explain the requesting test and obstacle. “Destination approval required” is separate from “Login needed.” “Browser unavailable” cannot offer a fake reconnect to a dead process-local session.

**Pattern F — every state has a privacy model.** Screenshot frames seen by an authorized operator, browser screenshots stored as evidence, private keystrokes during manual login, and sanitized telemetry are four distinct data categories with different retention and access policies.

**Pattern G — novice-first, technical second.** Default Agents screen displays simulated tester → task → current work → evidence-supported result. Put runtime YAML, model settings, OpenTelemetry span IDs and LangSmith trace diagnostics in an explicitly labeled Advanced panel.

## 1.3 Alternatives within our existing tools (no new services)

| Decision dimension | Existing-stack options | V1 choice | Reconsider only if |
|---|---|---|---|
| Live browser visuals | Existing `owner.observe()` JPEG snapshots or an additional custom stream on the same worker | **Bounded, on-demand JPEG polling** through authenticated Control API | Measured frame-rate/performance needs justify transport complexity |
| Interactive browser | Existing lease-bound `HumanBrowserViewer` WebSocket | **Reuse as the exclusive human-input transport** | Proven platform deficiency prevents required accessibility/control |
| User-visible activity | Current PostgreSQL `ExecutionStep` / `RunEvent` / handoff records, or diagnostic traces | **Use redacted, typed DB projection** | Proven missing lifecycle facts require narrow schema additions |
| Detailed technical tracing | Existing OpenTelemetry + OpenInference exporter | **LangSmith only** once exporter destination is validated | User explicitly changes the stack decision |
| Agent execution | Existing Google ADK and both executor types | **Keep both, label them accurately** | Independent benchmarks show a justified redesign need |
| Evidence storage | Existing artifact and MinIO/S3-compatible path | **Persist approved safe evidence only** | Retention policy and user demand justify another model |

## 1.4 Specific product hypotheses to validate with users

1. Can a first-time developer identify the selected browser and current journey within 10 seconds? *(Target, not a proven metric.)*
2. Can the same developer explain why human assistance is necessary without reading documentation?
3. Can an operator complete a synthetic login and hand the same browser back with no assistance from a developer?
4. Can they differentiate a real website defect from a selector/test-design failure?
5. Can a QA engineer reach relevant LangSmith trace diagnostics from a failed journey **without** having to decode a prompt YAML tree?
6. Does watching add value without materially slowing browser execution? Compare watched and unwatched synthetic trials.
7. Can users take meaningful action on findings, rather than merely read reports?

These must be measured through browser-based usability sessions and controlled experiments, not answered from the appearance of the UI.

---

# 2. Pinned repository evidence and exact existing/missing capability

## 2.1 Code verified at the remote HEAD

| Existing surface/file | Source-level evidence | Delivery consequence |
|---|---|---|
| `apps/web/src/pages/runs/RunActivityPage.tsx` | Only a `FutureStagePage` with “live Run event timeline ... when ... API is connected” | **No usable live UI yet**; preserve route, replace placeholder |
| `apps/web/src/layouts/RunLayout.tsx` | Run tabs include Summary/Journeys/Findings/Evidence/Report/Human Assistance; Activity is under More | Put **Live Execution** in primary run navigation and immediate post-start path |
| `apps/web/src/components/markettwin/RunFlowPanel.tsx` | Expandable nodes, statuses, raw technical kinds; personas called “Sequential Agent/subagents” | Replace or simplify **presentation**, keep flow data for technical inspector |
| `apps/web/src/components/markettwin/ProjectAgentBrowser.tsx` | Global `/agents` points to “Agent settings”, project/run selection | Split task-oriented “Testers & Journeys” from advanced agent settings, without losing route |
| `apps/web/src/pages/runs/AgentPromptsPage.tsx` and `AgentTree.tsx` | YAML, runtime snapshot, temperature, model and subagent tree dominate | Move advanced configuration behind explicit “Advanced agent settings” |
| `apps/web/src/pages/runs/RunJourneysPage.tsx` | User/mission, execution status vs outcome, steps/evidence, technical metadata already exist | Build understandable journeys list/detail and link to live view + outcomes |
| `apps/web/src/pages/runs/RunOverviewPage.tsx` | Lifecycle rail, findings and recorded metrics | Add an explicit **current action / next action** section for active runs; preserve findings for completed runs |
| `apps/web/src/pages/runs/RunPerspectivesPage.tsx`, `RunMissionsPage.tsx` | `FutureStagePage` placeholders | Either connect actual persisted persona/mission data or remove from primary nav until connected |
| `apps/web/src/pages/runs/HumanActionPage.tsx` | Human requests, claim/renew/reconnect/Done/Skip, and one-time approvals, with role checks | Reuse HITL domain logic; avoid mounting **two** lease-owning controllers |
| `apps/web/src/pages/runs/HumanBrowserViewer.tsx` | React canvas; volatile WebSocket JPEG/input; auto-connect after grant; touch/click mapping; keyboard escape; input forwarded as text | Same live page can become interactive **only** under exclusive human lease |
| `services/execution-orchestrator/.../browser/owner.py` | `observe(handle, generation)` captures bounded JPEG under lock, checks agent/pending mode and exact generation; `frame(lease)` serves human controller | **Low-level read-only capture already exists**; reuse it |
| `.../browser/owner_service.py` | Signed internal `POST /observe` handler and lease endpoints exist | **Worker-internal observation endpoint exists**; do not rebuild |
| `.../browser/viewer_authority.py` | `observer_permitted` checks active member/owner/admin, target authorization, exact browser generation and mode | Reuse/strengthen durable authorization; add post-capture authority verification |
| `services/control-api/.../api/live_browser.py` | **Absent at audited HEAD** | Add authorized run-scoped read model and volatile frame proxy |
| `services/control-api/.../main.py` | No `live_browser` router registered | Register only after matching API implementation |
| `services/control-api/.../persistence/repositories/test_run_results_repository.py` | Steps have existing safe action/observation summaries, IDs and timestamps | Project a read-only bounded activity feed from existing durable records |
| `.../workflow/journey_executor.py` | Persona ADK loop and existing runtime auth callbacks | Hook live lifecycle/manual pause into persona boundary, not only deterministic cases |
| `.../workflow/case_execution.py` | Step start/finish, deterministic case execution, persisted approval and assistance | Hook safe pause before tool/step dispatch; report uncertain side effects accurately |
| `.../workflow/multi_persona_executor.py` | Journeys run sequentially | Don't promise simultaneous N-browser monitoring; active-selector must be truthful |
| `.../agents/schemas/plan.py` | Exactly **three personas**, one to four missions | Preserve V1 planner schema; do not add user-configurable population counts now |
| `.../workflow/persona_result.py`, `.../agents/schemas/persona_report.py` | Per-journey outcome, summary, friction, blockers, criterion evidence | UX can show evidence-linked simulated observations; **not real user testimonials** |
| `.../browser/human_control.py` | Stops trace/evidence before handoff, guards agent tools; resumes on verified safe continuation | Maintain capture fence before **any** credential entry |
| `.../browser/auth_session_broker.py` | In-memory scoped cookies/storage snapshots can be reused across isolated cases | Login secrets are not given to LLM, but session data is processed in MarketTwin memory; disclose accurately |
| `.../browser/viewer_gateway.py` | One-time viewer ticket, cookie/Origin validation, lease authority, frame/input flows | Strict control path exists; don't expose it to observers |

**Important reconciliation:** `docs/hitl/LIVE_EXECUTION_IMPLEMENTATION_PLAN.md` describes low-level observation as missing in some rows but code **already has** `owner.observe`, the signed worker `/observe` route, authority validation and Chromium-focused observation tests. The **public Control API + React live UX** are still absent at the audited HEAD. Any new implementing agent MUST use current source over stale plan tables.

## 2.2 System constraints that change design

- Browser ownership is **process-local**; a worker crash does not reconstitute the same live browser.
- Human waits occupy the **single execution Kafka consumer** in the current topology; later runs may queue even while the UI and viewer stay responsive. Expose this queue truthfully; do not conceal it with fake parallelism.
- Each persona journey and deterministic case can use an isolated browser context; browser identity can change between cases. The UI **must clear a previous frame** before showing another selected browser.
- Run status, execution status, assertion outcome, finding classification and report/evaluation readiness are **different dimensions**.
- The worker's local capture screenshot is restricted to `agent` and `human_pending` modes, not active human entry; the protected interactive viewer uses a separate lease-bound channel.
- Runtime HITL has locally demonstrated certain synthetic login/MFA, skip, reconnect and report paths, but broad external SSO/CAPTCHA and production security remain unverified.
- The previous repository product audit concluded the local end-to-end pipeline is implemented but **model-generated autonomous defect quality** is not yet established against independent ground truth.

## 2.3 Existing design language to retain

Use the original UI master spec, existing React components and tokens as the baseline. Keep **Instrument Sans Variable** for UI/body and **IBM Plex Mono** for IDs/code. Continue “Quiet Precision”: restrained neutral surfaces, accessible contrast, subtle borders, clear informational typography, Lucide icons, action-oriented labels, no flashy gradient/glow/artificial AI animation. Do not create a second incompatible visual system.

---

# 3. Mental model, information architecture, terminology

## 3.1 Primary user mental model

> **Application** → authorized **Target** → **Test** (what to examine) → **Simulated Testers and Goals** → executed **Journeys/Cases** → **Steps & Evidence** → **Verified Results**.

There are **two execution modes**, not one universal class of autonomous agent:

- **Persona Journeys:** planner-generated personas × missions; LLM-supported bounded browser-tool work, one journey at a time in the current worker.
- **Feature Cases:** planned cases executed via bounded deterministic action steps; do **not** label each deterministic executor as an autonomous-thinking persona.

On the same run, the UI must label actual executor type in ordinary language and make advanced runtime metadata available on demand.

## 3.2 Terminology map

| Technical term | User-facing label | One-line meaning | Advanced detail |
|---|---|---|---|
| Meta Agent | **Test Planner** | Chooses goals/cases for this test | Model, prompt/config, snapshot |
| Persona | **Simulated Tester** | Hypothetical approach to testing; not a human participant | Traits, priorities, generated source |
| Mission | **Testing Goal** | What the tester is trying to achieve | Frozen objective and criteria |
| Persona × Mission | **Journey** | One tester attempting one goal | Execution/journey IDs, attempt |
| `deep_feature_v1` | **Feature Case** | A bounded planned browser test | Deterministic executor identity |
| BrowserController | **Test Browser** | Browser where actions actually occur | Session ID, generation, owner |
| HumanActionRequest | **Human assistance required** | An authorized operator must complete a protected step | Request ID, reason, expiry |
| HumanControlLease | **You are controlling the browser** | Exclusive temporary input authority | Lease/generation, role, timeout |
| Sensitive-action approval | **Review protected action** | Authorize one exact pending side effect | One-time receipt/fingerprint |
| Evaluator | **Results verification** | Classifies what evidence supports | Evaluator kind, criteria |
| Run flow | **Test progress** | Planner → execution → evaluation → report | Raw workflow graph |
| Agent snapshot/YAML | **Advanced agent configuration** | Saved technical behavior and rerun settings | Full YAML/model metadata |

**Avoid:** “user” ambiguously meaning real MarketTwin operator vs simulated tester; “agent thought”; “human verified login” without configured identity check; “passed” when only infrastructure completed; “customers liked it” from LLM opinions.

## 3.3 Navigation contract

**Workspace left nav (top level):** Overview, Applications, Tests, Agents (or “Testers & Agents” if needed for discoverability), Knowledge, Settings. Global pending-action indicator only if real pending requests; do not invent unread counts.

**Within a Test:**

- **Overview** — what this test is for, actual phase, next action, key results.
- **Live Execution** — the primary active screen; browser + execution list + timeline + contextual assistance.
- **Journeys / Cases** — completed or active tester goals and outcomes, linked to live execution.
- **Findings** — independently qualified issues requiring action.
- **Evidence** — preserved safe evidence and selected-step inspection.
- **Report** — completed evaluation and limitations.
- **More / Advanced** — Evaluation diagnostics, agent configuration, raw flow, persisted plan, technical snapshots.

**Human Assistance:** keep legacy route `/runs/:runId/human-action` for bookmarks/tests; it should link/focus the same canonical intervention in Live Execution rather than instantiate a competing live controller. A stable shared lease owner/controller must guarantee one authoritative client view. **Do not redirect active leases or unmount them casually.**

**Activity route:** keep `/runs/:runId/activity`; show it as **Live Execution**. Existing `/runs/:runId/agents`, `/agents`, `/runs/:runId/perspectives`, `/runs/:runId/missions` remain addressable; connect to real persisted data or label clearly as not available and remove from main nav until complete.

## 3.4 Action-oriented dashboard and status hierarchy

A header should answer in one scan: **Target**, **Goal**, **Phase**, **Selected journey**, **Needs your action?**

Example, illustrative only: `MT-50  ·  Test sign-up  ·  Executing  ·  New visitor: create account  ·  Human assistance required`.

Render separate dimensions:

| Dimension | Example | Must never imply |
|---|---|---|
| Run processing status | Planning, executing, awaiting human, evaluating, completed | Product passed all tests |
| Journey execution status | Running, completed, skipped, timeout, policy-blocked | Mission criterion satisfied |
| Journey/product outcome | Passed, failed, partial, inconclusive, unverified | Confirmed website bug necessarily |
| Assertion verification | Satisfied, unsatisfied, unverified | Browser infrastructure failure |
| Finding classification | Confirmed product issue, needs verification, test execution/specification problem | Every locator failure is app defect |
| View authority | Read-only, human control, unavailable | A read-only viewer can send input |

Never mark `409 evaluation pending` as a failed test; show report pending distinctly from genuine API error. Never show an unsourced percent-complete bar or predicted time-to-finish as fact.

---

# 4. Screen-by-screen product specification

## 4.1 Test creation and immediate post-start

**Before Start:** keep one prominent goal composer, authorized target/environment, mode selection with plain-language differences, coverage bounds, and review of exact approved origins / sensitive-action policy. User should not need to enter credentials or configure login markers by default for supported runtime HITL. Advanced identity-policy configuration remains opt-in and explicit.

**After Start:** change primary action to **Watch live execution**. Navigate to `/runs/:runId/activity` or provide visible CTA while the work is queued. Show truthful phases: queued, preparing, browser discovery, planning, executing, evaluating, ready. No fictitious progress percent.

**On a blocked origin:** “This destination is not in the approved test scope,” exact origin if safely displayable, actions **Review allowed destinations** / **Stop or skip**, but **never** silently change frozen run authorization. Approval yields a new authorized execution/reviewed revision, not permission mutation under an existing frozen run.

## 4.2 Live Execution workbench (desktop)

**Primary composition:**

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ Test: Sign-up journey   Target: Approved staging       Executing       [Stop test]       │
│ Goal: Check account creation                      [Why this test?] [Report when ready] │
├────────────────┬────────────────────────────────────────────┬────────────────────────────┤
│ TEST WORK      │ ACTUAL TEST BROWSER                        │ RECORDED ACTIVITY          │
│                │                                            │                            │
│ ▸ Discovery    │  [Read only] browser status, viewport      │ 10:31 Opened start page    │
│ ▸ Planner      │ ┌────────────────────────────────────────┐ │ 10:32 Found signup link   │
│ ▸ New visitor  │ │                                        │ │ 10:33 Navigated /signup  │
│   Sign up      │ │ LIVE PICTURE OF SAME BROWSER            │ │ 10:34 Human needed        │
│ ▸ Returning... │ │ NO FABRICATED SCREENSHOTS               │ │                            │
│ ▸ Evaluation   │ └────────────────────────────────────────┘ │ Selected step details      │
│                │ Last refreshed: time; honest errors        │ Why / result / evidence    │
├────────────────┴────────────────────────────────────────────┴────────────────────────────┤
│ Action required: Login is blocking this journey. [Take control] [Skip journey]          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**Important behavior:**

- **Left:** compact tree of lifecycle → actual journeys/cases, one real selected browser at a time. Items indicate running/queued/completed/blocked; avoid empty “agent avatar gallery.”
- **Center:** real image from current owned Playwright page, correct viewport aspect, last-frame timestamp, read-only state; no automatic browser interaction. The last frame is cleared when selected browser ID/generation changes, on permission loss, after human claim, on completion, and on decode error.
- **Right:** chronological stable-ID activity; selectable steps show actual action, status, elapsed time if recorded, safe explanation and evidence. Search/filter only if useful. No unsourced “thinking” bubbles.
- **Bottom/action region:** only the current actionable intervention, if any; do not mix login and “approve payment” into one generic affirmative button.
- Active journey selection should follow current execution by default, but allow selecting recorded journeys. Selecting a finished journey shows **historical evidence**, not falsely labeled live frames.
- Clear distinction between **Live** and **Recorded** controls, with timestamps and source badges as secondary metadata (not decorative status tags).

## 4.3 Tablet/mobile adaptation

- Desktop wide: left selection 210–260 px, fluid central viewport, right inspector 280–360 px **only when space permits**; avoid three squeezed columns at typical laptop widths.
- Tablet/narrow: selected journey chip/drawer above the browser; activity beneath; optional inspector drawer. Browser always gets a meaningful minimum width.
- Mobile: browser aspect-correct with pinch/scroll behavior; explicit read-only state; activity below; clear, full-width human-assistance CTA. No screenshot cropping or hidden Done/Skip. Verify coordinate transformation against CSS scaling, device pixel ratio, browser viewport resizing and touch.
- Never let an always-visible sidebar cover the credential entry region or cause horizontal overflow. Keyboard focus and shortcut escape must work at all widths.

**These widths are design candidates:** exact breakpoints must be validated in Chrome/Edge and screenshots (e.g., 1440, 1280, 1024, 768, 390, 320), not accepted on paper alone.

## 4.4 Timeline and selected-step inspector

A timeline entry is a **typed fact**:

- `Opened approved landing page` — recorded navigation, timestamp, browser context, outcome.
- `Attempted to locate the Sign up link` — action preflight, status `ambiguous` / `not found` / `confirmed`.
- `Authentication obstacle detected` — evidence-backed challenge, *not* a generic login link on marketing page.
- `Human assistance requested` — durable request ID and exact asking journey.
- `Operator claimed control` — durable authority transition, without entered text or browser screenshots.
- `Agent resumed safely` — committed transition + verification status.
- `Started evaluating evidence` / `Report ready` — actual evaluator phase events.

Selecting an action shows: **Goal**, **What was attempted**, **What was observed**, **Status**, **Why this is or isn't a product defect**, **Evidence reference**, **Time**, **source**, **supporting provenance**. A browser screenshot alone does not prove the behavior was a bug.

Group repeated network errors rather than flooding the panel. Support `All`, `Problems`, `Human needed`, `Browser actions`, and optional `Technical` filters; count from real data. Stable cursors prevent duplicate entries after polling/reconnect. No raw page text, full query strings, secrets, HTML or model prompts in the ordinary feed.

## 4.5 Agents / Testers information architecture — explicit overhaul

**The current global `/agents` and per-run `/agents` primarily emphasize YAML, model and runtime snapshots. This is a major product mismatch.** Most application owners need behavioral outputs first; developers retain the advanced inspector.

**Global Agents page:** headline **Simulated Testers & Agent Settings** (or simpler **Testers & Agents**). Tabs or segments:

1. **Testers and journeys:** select application/test, view actual run-scoped testers, their priorities/goal, progress and outcomes. Do not show global generated personas detached from their source run.
2. **Execution diagnostics:** actual planner/case/agent type, recorded steps, model tool events *only if instrumented*. Status/correlation IDs.
3. **Advanced settings:** current prompt YAML/snapshot editor and explicit rerun-draft workflow; maintain existing role checks and no editing frozen results.

**Run Agents page default:**

| Tester or executor | Goal | Mode | Current work / status | Verified outcome | Action |
|---|---|---|---|---|---|
| New visitor (synthetic) | Create an account | Persona journey | Awaiting human | Not yet verified | Watch / Assist |
| Returning user (synthetic) | Retrieve a record | Persona journey | Completed | Passed | Inspect evidence |
| Feature Case 04 | Navigate to a named control | Deterministic | Failed locator preflight | Test specification issue | Inspect step |

Rows above are illustrative, never fake API defaults. If there are no run-scoped personas, show the accurate empty state and link to start/create a test.

**Tester detail:** short purpose (≤2 sentences), priorities and scenario assumptions, goal, success criteria, step chronology, friction observations, outcome, verified evidence, any human assistance. Keep model-generated subjective commentary in a distinct section labeled **Simulated perspective — hypothesis, not feedback from a human**; make it optional and not the headline or a satisfaction metric.

**Technical inspector:** planner model/version when recorded; frozen prompt snapshot; whether step was LLM tool, deterministic case, discovery, human, evaluator; exact durable events and correlating trace IDs. No private chain-of-thought. Actual tool result can be summarized safely, with full developer diagnostics permitted only after authorization/redaction.

**Agent flow visualization:** show only authentic relationships. If three personas × two missions yield six sequential journeys, do not depict six parallel browser agents. Show Test Planner → 6 planned journeys (sequential) → Evaluator → Report, with case selection and timestamps. A separate “How MarketTwin works” explanation can describe the pipeline; it must not impersonate current run state.

**Existing route compatibility:** preserve `/agents` and `/runs/:runId/agents`, YAML editor, rerun behavior, query caches and role permissions. Use UI presentation wrappers/adapters rather than back-end renames. Connect `/perspectives` and `/missions` to truthful stored entities, or hide from primary nav until done.

## 4.6 Run Overview: next action over vanity metrics

For queued/running/awaiting-human tests, show a prominent state panel with **current phase, selected journey, last recorded action, when updated, one correct next action**. Examples:

- `Planning test goals — no browser is currently open. View recorded planning status.`
- `Executing Journey 2 of 6 — Watching is available.`
- `Human assistance required for Journey 2 — Take control to sign in; agent is paused.`
- `Awaiting evaluation — browser work finished; report not yet available.`
- `Worker disconnected — cannot watch/resume this browser; review persisted steps.`

For completed runs, lead with **confirmed issues / needs verification / test execution issues**, not unsupported “quality scores.” Include run scope, limitations, visited journeys, and direct links to evidence and report. “No findings” is never “application is bug-free.”

## 4.7 Findings, Evidence and Report — make action possible

The most useful output is **a reproducible and independently checkable issue**, not a prose verdict.

For each finding show: title; severity only if justified; **classification** (confirmed product issue / needs verification / test specification failure / environment/policy block); goal/expected/observed; source step IDs; screenshots or safe network/console references if available; reproduction steps; reviewer status and caveats.

Use a trace-like before/after inspector **only for evidence that already exists and is safe to display**. Never synthesize screenshots, secretly persist live stream frames or blur things on screen while still storing raw pixels.

For a persona output, distinguish **observed browser behavior** and **model-reported friction/interpretation**. A failed `get_by_text` selector when a heading is visibly present is **test-specification failure**, not a confirmed application defect. No inference of page failure from an unrelated 503 alone. Unverifiable redacted URLs remain “unverified,” not passed.

## 4.8 Intervention queue and notifications

Provide one **Needs your attention** indicator scoped to current workspace/run, backed by real pending assistance or approval rows. Use semantic accessible status announcements and safe event payloads; never display passwords, OTPs, token-bearing URLs, or a captured credential-entry screenshot in browser notifications or email.

Deduplicate by exact request/action ID; retain historical completed/expired/skipped state without crowding current work. Separate three different human decisions:

- **Take browser control** (user is typing into site in a leased browser),
- **Approve once / Reject** (one specific protected side effect),
- **Review requested destination** (authorization/scope workflow, never automatic change to frozen scope).

Notifications are supplemental: the **run page must itself** show the pending action; do not make a toast or email the only path to intervention.

---

# 5. Complete HITL experience: login, sign-up, MFA, SSO and recovery

## 5.1 User-facing flow and exact messages

```
Agent browsing authorized target
  → evidence-backed auth obstacle encountered
  → finish/fence current operation safely
  → create exact-journey HumanActionRequest and suspension
  → display "Human assistance required"
  → owner/admin explicitly clicks "Take control"
  → acquire exclusive lease; agent input and evidence capture OFF
  → same browser/context becomes interactive through protected viewer
  → operator completes login/MFA/allowed signup within approved scope
  → operator clicks "Done — resume agent"
  → revoke input, verify scope/safe continuation and configured identity policy
  → resume from exact safe boundary OR stay blocked/Skip
```

**Notification copy (example, not runtime fact):**

> **Human assistance required — Sign in**  
> The registration journey reached a sign-in page. The agent is paused and cannot enter your credentials.  
> **Website:** approved staging target. **Test:** New visitor — Create account.  
> [Take browser control] [Skip this journey] [Why is this needed?]

**During human control:**

> **You are controlling the test browser.** Enter credentials directly into the website. MarketTwin will not show this interaction in the agent activity timeline. Do not paste credentials into agent notes. [Done — resume agent] [Skip journey]

**After Done:**

> **Checking safe continuation…** Your browser input is disabled. MarketTwin is checking the approved destination and configured authentication requirements before the agent resumes.

**Failed verification:**

> **The agent cannot safely continue yet.** The expected approved page or configured login state was not verified. Choose retry takeover (if lease/request allows) or skip this journey. Nothing is marked passed.

**Do not say:** “Credentials are never shared anywhere” or “End-to-end zero knowledge” for the current remote viewer. The transport/worker receives input and the website necessarily receives authentication information.

## 5.2 Recognition must be conservative

Trigger when observed evidence supports an actual login/MFA/CAPTCHA/SSO or recoverable protected interaction, via bounded detector/callback and optional safe explicit tool request. A marketing Sign in link, unapproved domain, arbitrary `403`, selector failure or model hunch is **not enough** by itself. Distinguish:

- **Authentication obstacle:** eligible for HITL in approved scope.
- **Destination needs review:** requires independent origin approval; no takeover bypass.
- **Sensitive action:** separate one-action approval (signup/account creation may create a real external effect; require explicit authorization where policy calls for it).
- **Test locator ambiguous / unsupported oracle:** classify and support bounded human recovery only where allowed; never silently change frozen plan/assertions.
- **Prohibited action:** remains prohibited even when a person claims browser control unless policy independently allows human operation.

The implementation must support first-page and delayed obstacles in **both** persona and Feature Cases paths. Avoid repeated prompting loops after Skip.

## 5.3 Same-context control safety

- Human claim binds `run`, `execution`, `journey`, `browser_session`, `request`, `lease`, `actor` and `generation`. One current owner, no competing agent input.
- The worker must pause/cancel **future dispatch**, not interrupt an already-uncertain side effect. Browser session remains open during the lease.
- On claim, stop screenshot/trace/evidence capture **before** the first human keystroke; clear safe event buffers and prevent future credential entry logging.
- On viewer reconnect, issue new short-lived ticket under the **same durable lease**; disconnect must not mean Done or elevate generation.
- On Done, revoke user input first; validate target and configured identity; check continuation/replay safety. No role verification is implied by simply reaching a page. No unauthorized replays.
- On Skip, record `not tested / assistance skipped`, continue independent work when possible, and revoke provisional state. On expiry, user revocation, cancellation or worker failure, fail closed.
- Suppress read-only observation of **another person's** credential entry; a non-controller must not get pixels or key events during human control.

## 5.4 Credential/privacy boundary — what can and cannot be promised

**Code fact:** `HumanBrowserViewer.tsx` forwards input via WebSocket `text` events; `owner.py` inserts text into the owned Playwright page. `human_control.py` fences evidence capture; `viewer_gateway.py` authenticates tickets and avoids recording payloads; `auth_session_broker.py` can keep scoped browser cookies/storage **in process memory** for reuse.

**Accurate user statement:** “You enter credentials into the target website through MarketTwin's protected, interactive browser. The AI agent is paused. We design the evidence/logging pipeline not to retain your credential entry; the browser service still processes input and session state, and the target site receives credentials. Use a dedicated test account.”

**Mandatory verification:** canary password/OTP/cookie/query values must not appear in database rows, Kafka/outbox payloads, MinIO artifacts, browser traces, captured screenshots, console/error logs, analytics, frontend caches, exception serialization, model requests, approval summaries or other persisted stores. Test pre-handoff and post-handoff transitions, not just during control. Re-scan after each change.

**Limitations:** target page can itself show private account data *after* login. Avoid raw DOM/page extraction or blanket recordings of authenticated content; masking known input selectors does not protect arbitrary sensitive text. Prefer allowlisted observations and safe screenshots, operator access controls, explicit retention, and isolated fixture accounts. For a hard client-only secrecy requirement, design a different trusted local browser execution boundary; current server-side remote browser cannot guarantee that the server never sees keystrokes or cookies.

**Session reuse:** maintain short-lived run/target/account scope, expiry, one-use-per-case, revocation and no serialized reusable auth-state file. User-facing text should disclose reuse; consider an explicit default-off control for external non-synthetic targets after assessing compatibility and privacy. Do not silently turn off legitimate existing tested reuse without migration/approval.

---

# 6. Read-only live browser transport: recommended technical contract

## 6.1 Decision: on-demand bounded JPEG observation

Use existing worker-side `owner.observe()` and the signed internal `/observe` route as the **low-level** capture path. Build the missing public API and frontend. Keep existing lease-bound WebSocket unchanged for human input.

**V1 proposed default:** request approximately **1 frame per second when a user is actively watching**, with at most one in-flight frame request per viewer; skip polling when hidden. These are **design defaults, not measured performance guarantees**. Never poll continuously in the background by default. A slow/failed frame must not stop a healthy test. If average capture delays exceed tolerance, throttle or return “viewer busy”; do not hold session lock indefinitely.

Frame bytes are volatile and **not** automatically saved to PostgreSQL, S3/MinIO, Kafka, session replay, service worker cache, React Query or browser local/session storage.

## 6.2 Public Control API — proposed, not present at audited HEAD

**Metadata / bounded activity:**

`GET /api/v1/test-runs/{run_id}/live-browser`

Suggested shape (contract proposal; align with existing response conventions):

```json
{
  "run_id": "uuid",
  "run_status": "running",
  "phase": "executing",
  "server_observed_at": "2026-10-17T19:00:00Z",
  "browser": {
    "browser_session_id": "uuid",
    "execution_id": "uuid",
    "journey_id": "uuid",
    "generation": 2,
    "control_state": "agent",
    "viewer_state": "available",
    "viewport": {"width": 1280, "height": 720}
  },
  "selected_work": {"kind": "persona_journey", "title": "New visitor — Create account"},
  "assistance": {"kind": "none", "request_id": null},
  "activity": {"items": [], "next_cursor": null}
}
```

The example is a proposed response shape, **not an example of live data**. No browser field until the session is actually open; no guessed page title/URL/current action. If multiple sessions later run simultaneously, API selects explicitly or requires a browser/session choice. **Do not silently swap sessions**.

**Frame:**

`GET /api/v1/test-runs/{run_id}/live-browser/frame?browser_session_id=<uuid>&generation=<int>`

- Validate logged-in actor and owner/admin permission, current workspace and target authorization, run/execution/journey/browser chain, **exact generation** and safe control mode.
- Recheck authorization just before delivering bytes, including after worker response; worker also validates authority before and after capture. Avoid URL-selected worker hosts or arbitrary proxy destinations.
- Expected responses: 200 `image/jpeg` bounded (e.g. ≤2 MiB candidate); 401 session expired; 403/404 permission/resource hidden under established error policy; 409 selected browser changed/unavailable/suppressed; 503 owner worker unavailable. `Cache-Control: no-store`, `Pragma: no-cache` and content-type validation.
- Bound capture/worker timeout, rate and overall concurrent watchers. If two operators may watch concurrently, establish explicit per-session limits; fail closed on protected-state transitions.
- Do not append auth ticket, actor cookie, secret token or sensitive full URL to frame URL/query string.

**Activity:** one stable cursor, bounded page size (candidate: 50 records); source only from fixed typed allowlisted representations of persisted `ExecutionStep`, `RunEvent`, `HumanActionRequest`, approvals and report/evaluation rows. Avoid pulling `untrusted observation_summary` or raw model output directly into public history.

## 6.3 Worker internal adapter

Existing `POST /internal/hitl/observe` (mounted relative to the owner's internal router) already validates signed request, `actor`, browser/execution/journey IDs and generation and calls `registry.observe`. Tighten:

- Same HMAC/body-size/timestamp/nonce replay rules as lease calls.
- Reject extra JSON keys and any request specifying URL/JavaScript/CDP instruction.
- Re-check **durable operator/target authorization after capture and before worker sends bytes**. Present code verifies durable authorization first, and local ownership after capture; check post-capture durable authority separately to close that gap.
- Check live origin before/after capture, current control generation, no active human/viewer state; bounds on JPEG bytes, timeout and lock wait.
- Generic safe errors; no page exceptions or tokens serialized.

## 6.4 Frontend polling and correctness

Implement browser selector using immutable IDs and generation; clear image on mismatch; use `AbortController`/request lifecycle and revoke object URL after drawing or unmount. A query-cache holding binary live frames is prohibited. Show viewport size, last delivered frame age, “Read-only live view”, and explicit `temporarily unavailable`/`disconnected` states. Don't keep showing a stale frame with a live label.

The currently interactive `HumanBrowserViewer` must remain a **separate input-gated component**, or share only strictly passive frame-rendering primitives. Never reuse `onPointerDown`/`onKeyDown` controls for observation mode with a mere CSS `pointer-events:none` guard.

**No browser open?** Show planning/queue/discovery/evaluation status honestly; no unrelated stock screenshot or previous session pixels.

---

# 7. Cooperative manual pause and takeover: extra scope beyond the earlier plan

**Important:** The existing `LIVE_EXECUTION_IMPLEMENTATION_PLAN.md` focuses on watching and encounter-driven HITL. A general operator-requested pause requires its own durable state transition and action-boundary contract in the current Google ADK / Python execution path. **It is not implemented.** Treat it as a separately gated milestone. Do not add a live Pause button until the worker can acknowledge a safe boundary.

## 7.1 Semantics

- “Request pause” means: **ask the active executor to stop dispatching at the next safe checkpoint**. The UI shows `Pause requested`; only worker acknowledgment shows `Paused`.
- If a browser action is in progress, wait for a confirmed completion or a classified uncertain effect. Never abort a partially dispatched payment, signup or other mutation and blindly replay it.
- When paused, the agent and human cannot both type. If no live browser exists, show `No browser available for takeover` rather than a misleading control button.
- Resume needs the exact session/generation/current page, reviewed continuation and a clear policy for what happens to frozen assertions and planned next actions after human navigation.
- Request should be idempotent and bounded; a repeat click returns the existing request state rather than creating competing leases.
- The pause operation must not modify target permissions, turn a prohibited action into an approved one, or automatically grant control to an arbitrary viewer.

## 7.2 Proposed state model (illustrative; adapt to existing persisted schemas)

```
AGENT_RUNNING
  └─ user requests pause → PAUSE_REQUESTED
      ├─ safe action boundary, acknowledged → PAUSED
      │    ├─ authorized claim → HUMAN_CONTROLLED
      │    │    └─ Done → VERIFYING → AGENT_RUNNING or BLOCKED
      │    ├─ Resume without human → AGENT_RUNNING
      │    └─ Skip → SKIPPED / continue independent work
      ├─ action uncertain → BLOCKED_REVIEW_REQUIRED
      ├─ cancellation → CANCELLED
      └─ worker loss → WORKER_UNAVAILABLE
```

Do not collapse `PAUSE_REQUESTED` and `PAUSED` into one state. Do not reuse `awaiting_human` to imply that a human already controls the browser.

## 7.3 Proposed API (not implemented)

`POST /api/v1/test-runs/{run_id}/journeys/{journey_id}/pause-requests` — durable, actor-authorized, idempotent with request key, validated active execution and exact ownership. Return `202 requested` with request ID and state; only worker changes it to acknowledged. If no active browser, return an explicit inapplicable state.

`GET .../pause-requests/{request_id}` or include in the live metadata read model. `POST .../{request_id}/resume` only for a truly acknowledged pause with no claimed human control; validate current state and generation.

The **existing HITL claim/release/skip API** is still the control authority: once worker recognizes an eligible paused journey, create/reuse a specific human request rather than invent a parallel browser owner. Scope and permission checks remain exact.

## 7.4 Checkpoint integration, failure semantics

- Add a cooperative pause check before dispatching a browser action in `BrowserController._agent_control_action` (one common guard) **and** ensure persona ADK loop and deterministic case scheduler stop advancing when requested. Browser lock and DB transitions must have a safe ordering; avoid deadlocks by not waiting for human while holding browser lock.
- For persona ADK, pausing during an in-flight model request may only acknowledge at the **next tool/model boundary**. Do not claim instantaneous pause or that we paused the LLM itself.
- For deterministic case, `record_action` already persists start/finish; checkpoint after finishing the current action and before the next reserved action. A pending sensitive-action approval is its own exact operation and cannot be bypassed by pause/resume.
- Human modifications may invalidate planned selectors/expectations. Reobserve and verify the exact planned next action or explicitly mark it `unverified/needs review`; never silently edit frozen test criteria to “pass”.
- A worker crash does not resurrect the owned Chromium context. Durable request may remain for audit, but live takeover is unavailable and run status must reflect failure/reconciliation.

## 7.5 Scheduling limitation

A human wait currently occupies the single Kafka execution consumer. A paused run may block later runs. This is a **known V1 operational limitation** that must be transparent in the UI. Make the pause timeout bounded and visible. Moving to a durable suspended-work scheduler and releasing the consumer can be planned later with a proven replay-safe checkpoint contract; do not bolt on extra Kafka workers without owner affinity and resumability.

---

# 8. Architecture, LangSmith tracing and authoritative event projection

## 8.1 Data flow

```
React Live Execution
  ├─ GET metadata/activity from Control API (auth + workspace authorization)
  ├─ GET transient JPEG via Control API → signed worker observe → active browser owner
  ├─ POST pause request → DB durable intent → worker acknowledges at safe boundary
  └─ Existing claim/renew/release/skip/approval endpoints → exact worker owner

PostgreSQL authoritative run/step/lease/event records ─┐
                                                       ├─ typed safe projection → UI
Execution Worker / BrowserController / ADK / cases ───┘

Kafka/outbox carries durable execution commands/events where already architected;
NEVER route live viewer frames or credential keystrokes through Kafka.
```

The authoritative event stream for user-facing history should be database-backed and correlation-safe; **LangSmith traces via existing OpenTelemetry/OpenInference/Google ADK** support diagnostic timing and agent/tool investigation, **not authoritative success**. Use existing `ExecutionStep`, `RunEvent`, human requests/leases and result rows before adding schema. Add migrations only for a genuinely missing durable pause fact or required stable lifecycle cursor.

## 8.2 Typed activity contract

Candidate structure:

```ts
type ActivitySource =
  | 'planner' | 'browser_agent' | 'deterministic_case'
  | 'human_assistance' | 'approval' | 'evaluation' | 'report' | 'system';

type ActivityStatus =
  | 'started' | 'completed' | 'failed' | 'policy_blocked'
  | 'inconclusive' | 'unverified' | 'skipped' | 'requested' | 'acknowledged';

type SafeRunActivity = {
  id: string;             // stable durable identifier or namespaced composite key
  run_id: string;
  journey_id?: string;
  execution_id?: string;
  step_id?: number;
  source: ActivitySource;
  kind: string;           // allowlisted semantic event type
  status: ActivityStatus;
  occurred_at: string;    // actual persisted event time
  title: string;          // fixed safe projection; no raw model prose
  explanation?: string;   // safe fact + known policy rationale, not chain of thought
  evidence_ids?: string[];
};
```

Use deterministic ordering `(occurred_at, source_key/id)` or monotonically stored ID/cursor; cursor must not drop late/committed events or duplicate rows across reconnect. For multi-worker future, globally unique event IDs matter more than wall-clock order.

**Operational states:** queued, discovery, planning, executing, model waiting (only if instrumented), paused requested, paused, human needed, human controlled, verifying, evaluation pending, report ready, cancelled, failed, worker unavailable, session ended. Unrecorded internal activity = **“No further recorded action yet”**, not fabricated narration.

## 8.3 Data quality and provenance rules

- *Known:* `ExecutionStep` says a browser tool ran/completed; screenshot shows recorded page state; approved action receipt says one action was authorized.
- *Inferred:* “This may be an application defect”; “The user might find navigation confusing.” Render with explicit qualifier.
- *Unknown:* Actual human satisfaction, account/role without configured verification, an unobserved network cause, private model thought.
- Keep timestamps, source, execution/journey IDs and linked evidence available; no fake status from UI timers.
- Represent data not yet loaded, genuinely empty, API error, session revoked, worker unavailable and historical record as distinct states.

## 8.4 LangSmith-only tracing architecture — code facts and what is not verified

**Architectural decision:** LangSmith is our selected **technical observability destination**. The existing exporter/instrumentation is the pathway; we do not install a second observability service or switch away from Google ADK.

### Verified at the pinned repository revision

| Fact | File/evidence | Status |
|---|---|---|
| Process-level OpenTelemetry SDK, `OTLPSpanExporter` and `BatchSpanProcessor` | `packages/shared-python/src/markettwin_shared/observability.py` | **Implemented in code** |
| Enabled via `MARKETTWIN_OBSERVABILITY_ENABLED`, endpoint from `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | same file | **Configured by environment; live settings unknown** |
| Default content capture is off via `MARKETTWIN_OBSERVABILITY_CAPTURE_CONTENT` | same file | **Implemented in code** |
| Google ADK instrumented with `GoogleADKInstrumentor` / `TraceConfig` | `services/execution-orchestrator/src/markettwin_execution_orchestrator/observability.py` | **Implemented in code** |
| Run, journey, execution, snapshot and agent-role context available for correlation | `workflow/planning.py`, `workflow/journey_executor.py`, shared observability processor | **Partial correlation implementation; cross-service continuity unverified** |
| LangSmith receives traces from the currently running services | Must inspect private local configuration and LangSmith project | **Not independently verified** |
| LangSmith trace IDs or links appear in the customer-facing UI | No supported full integration found in audited pages | **Not established; proposal below** |

**Important:** We are not importing another tracing SDK to replace our OpenTelemetry exporter. Official LangSmith documentation supports traces from our existing Google ADK/OpenTelemetry architecture. Google ADK stays as the agent runtime. LangSmith must be configured as the OTLP destination and tested.

### Verify the exporter rather than assume it

In the user's **existing private local environment** (do not post keys, print `.env`, or commit changes), confirm these effective settings; the following example values are placeholders, **not a claim they are already configured**:

```dotenv
MARKETTWIN_OBSERVABILITY_ENABLED=true
MARKETTWIN_OBSERVABILITY_CAPTURE_CONTENT=false
OTEL_SERVICE_NAME=markettwin-execution-orchestrator
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://api.smith.langchain.com/otel/v1/traces
OTEL_EXPORTER_OTLP_HEADERS=x-api-key=<private-key>,Langsmith-Project=<private-project>
```

For an alternate authorized LangSmith deployment/region, use its documented endpoint; never hardcode an endpoint from this example into application business logic. The code creates the Python OTLP **HTTP** exporter with an **explicit `TRACES_ENDPOINT`**, so the per-signal URL must include the full `/otel/v1/traces` path. It is *not* the same as `OTEL_EXPORTER_OTLP_ENDPOINT` base URL, which appends `/v1/traces` automatically. In the actual deployed environment, check header format, network egress, service restart, project/workspace selection and installed exporter version. See [LangSmith's OTLP guide](https://docs.langchain.com/langsmith/trace-with-opentelemetry) and [OTLP exporter semantics](https://opentelemetry.io/docs/specs/otel/protocol/exporter/).

- `OTEL_EXPORTER_OTLP_HEADERS` is used by the Python exporter; do not copy actual keys into instructions, user-visible activity, screenshots, traces or issue reports.
- The current code only initializes tracing when observability is enabled; the absence of traces may mean disabled flag, missing endpoint, exporter failure, missing activity, or wrong LangSmith project, not automatically an agent failure.
- Keep `MARKETTWIN_OBSERVABILITY_CAPTURE_CONTENT=false` as the safe default. Turning it on could expose model prompts, tool inputs, page content or hidden credentials; any change requires a dedicated privacy review. `TraceConfig` prevents some captures but does not prove every custom span is redacted.
- Avoid bootstrapping multiple tracer providers or adding another auto-instrumentor for the same ADK calls. Duplicate spans obscure causality and may increase costs.
- LangSmith's OTLP ingestion supports **traces** via this route; application logs, durable run states and product evaluation are separate systems and must not be described as automatically ingested by LangSmith.

### Controlled smoke-test procedure — perform during implementation

1. Check current branch/dirty tree, running services and private environment without disclosing secrets. Confirm chosen **LangSmith project** with the operator.
2. Start a **disposable local synthetic** MarketTwin run through its normal API/worker path, with tracing enabled and content capture off. Avoid live-user accounts and provider-backed costs without approval.
3. Observe a nonsecret `test_run_id`, `journey_id` and `execution_id` in MarketTwin's committed execution records.
4. Inspect the LangSmith project UI to find a trace emitted by Google ADK/OTLP. Confirm timing, model/tool span hierarchy and matching safe correlation attributes (if actually emitted).
5. Verify that no password, OTP, token, raw cookie, full sensitive redirect URL, or secret test canary appears in **LangSmith trace attributes/events**. Also inspect local trace/log/evidence surfaces.
6. If traces are absent, classify: observability disabled / exporter endpoint issue / header/project issue / provider network failure / instrumentation event missing. Record a redacted error summary, not keys.
7. Independently match final PostgreSQL journey status and evidence to the trace: **a span success is never taken as proof that a website test passed**.
8. Document verified trace identifier, controlled fixture run ID, observed hierarchy and failures in `docs/ui/VERIFICATION.md`; do not fabricate a successful trace link.

### Correlation schema (proposal — no raw content)

For related spans and DB activity, expose only existing nonsecret opaque IDs as metadata when safe: `test_run_id`, `journey_id`, `execution_id`, `agent_snapshot_id`, `persona_id`, `mission_id`, `agent_role`, `execution_mode` and service name. Explicitly classify whether each is present at **every hop**; do not assume automatic OTel parent propagation through Kafka. A `trace_id` linkage from the persisted journey may be added only if a verified, safe trace ID exists and the product needs it. The database remains the source of truth even if trace export is delayed, sampled or fails.

### Where LangSmith belongs in MarketTwin UI

- **Live Execution normal view:** zero LangSmith dependency for load, activity or HITL. The user sees DB-backed steps and read-only browser pixels.
- **Agents / Advanced diagnostics:** optional **Open LangSmith trace** affordance only for a verified trace association and an operator with access to that LangSmith project. The browser must not accept arbitrary caller-supplied redirect URLs. Otherwise show “Agent trace not available” with a reason if known.
- **Evaluations:** show MarketTwin's own authoritative assertion/evidence classification; LangSmith span status is a diagnostic signal, not a separate product evaluator.
- **Failures:** a LangSmith tracing outage must not stop a healthy test, expose secrets, or mark a website defect. A trace gap should be visible to a technical operator without disrupting the product UX.

## 8.5 Source-of-truth boundary and failure examples

| Question | Answered by | Not answered solely by |
|---|---|---|
| What step was actually attempted? | `ExecutionStep` and typed `RunEvent` with exact execution IDs | A LangSmith model span alone |
| What page is open right now? | The owned Playwright session at current generation | A historical screenshot or span |
| Did human takeover start/end? | Durable `HumanActionRequest`, lease and worker owner state | A frontend button click |
| Did the website feature work? | Grounded assertions, independent evidence and evaluator result | Model confidence or trace success |
| Why did the AI tool fail? | Recorded step diagnostics, safe worker errors and linked **LangSmith** span where available | A fabricated agent “thought” paragraph |
| Did sensitive information leak? | Secret-canary review across DB, MinIO/evidence, logs, exported LangSmith spans and viewer paths | “TraceConfig is enabled” alone |

## 8.6 LangSmith implementation and acceptance checklist

- [ ] Confirm **one selected LangSmith project** and correct nonsecret endpoint path.
- [ ] Confirm actual Google ADK OpenInference spans are exported, not just an initialized SDK.
- [ ] Validate redaction with synthetic secret canaries; capture-content setting remains false.
- [ ] Verify safe identifiers correlate spans to run/journey/execution without copying credentials or private page text.
- [ ] Distinguish provider timeout, no spans, missing instrumentation and missing user permission.
- [ ] Confirm trace errors never alter durable MarketTwin execution outcomes.
- [ ] Add only an optional Advanced trace link; never require LangSmith project access to view ordinary run status or take over a browser.
- [ ] Establish trace retention/access according to actual selected LangSmith settings, not assumptions.

---

---

# 9. UI design system and interaction fidelity

## 9.1 Visual style (inherit existing master spec)

Preserve shared design tokens/colors/themes where already rolled out. Baseline palette candidates from the older spec: `#f8f9f7` canvas, `#ffffff` surface, `#172422` primary ink, `#0c625d` accent; dark canvas `#0f1516`, dark surface `#161f20`. Values are design candidates; the actual repository token stylesheet wins where deployed. No second massive CSS override layer.

- Instrument Sans for ordinary reading; IBM Plex Mono **only** technical identifiers and compact log times.
- 14–16 px ordinary UI/body; avoid 10–12 px informational paragraphs. Headers establish simple hierarchy, not giant empty hero sections.
- Borders and spacing communicate grouping; avoid 8 nested cards per journey, glowing chips, decorative gradient/status animations, false metrics.
- Time is readable in local locale with full absolute time accessible on hover/focus; relative “3s ago” only if actually refreshed.
- Icon + text, not color alone, for human-needed, blocked, read-only, paused and completed states.
- Progressive disclosure: beginner gets goal/current step/next action; expert may open technical event/evidence/config panel.

## 9.2 Important interactive requirements

- Any important control has an accurately scoped label and disabled reason; no inert buttons.
- Keyboard traversal, skip link and focus recovery; `Shift+Escape` currently exists for leaving browser keyboard control—preserve/document/test it.
- Human-interactive browser gains focus **only when user explicitly claims control**; read-only viewer never forwards key events.
- On human control loss, clear browser pixels/input focus and announce loss; no stale remote-control surface.
- “Take control” only appears/works for the actual available request and authorized operator. Unauthorized viewer sees explanation, not button.
- View-level polling never holds input lease, increases human timeout or prevents test completion.
- Loading > couple seconds: progress/status explanation using source-recorded phase; no fake multi-step spinner completion.
- Error recovery should answer what happened, whether the test continues, whether the user should retry, and what is safe to do next.

## 9.3 Status and microcopy examples

| Real state | Good microcopy | Bad/misleading microcopy |
|---|---|---|
| Planner working | “Planning test journeys. No test browser is open yet.” | “Agents exploring...” when none are |
| Active read-only view | “Watching the registration journey. Browser input is disabled.” | “Live AI thinking” |
| Busy capture | “Browser frame temporarily unavailable; test continues.” | “Execution failed” |
| Pending login | “Human assistance required for this journey.” | “AI fixed authentication” |
| Pause request sent | “Pause requested; waiting for the current action to reach a safe stopping point.” | “Paused” before ack |
| Human lease active | “You are controlling the test browser.” | “Everyone can collaborate” |
| After Done | “Checking whether the agent can safely resume.” | “Login verified” without marker |
| Result pending | “Execution finished; evaluation/report still processing.” | “Failed (409)” |
| Skipped | “Not tested — human assistance skipped.” | “Passed” |
| Locator failure | “Test step could not locate a unique control; application defect unconfirmed.” | “Bug found!” |
| Worker lost | “The live browser was lost. Recorded evidence remains available.” | Reconnect same browser if it no longer exists |

---

# 10. Security, privacy, authorization and failure-mode threat review

| Threat/failure | Required control | Verification |
|---|---|---|
| Observer becomes controller | Two separate authorities/transports; no keyboard/click handlers in observation; no lease from a GET | Try input protocol with observation-only state; 403/409 |
| Wrong tenant/workspace | API + worker independently validate exact run/execution/journey/session ownership and role | Cross-tenant read/frame denial; no bytes leaked |
| Permission revoked during capture | Durable authorization revalidated **after** async screenshot before bytes sent | Race revocation against capture; deny |
| Credential leak during human entry | Stop trace/screenshots/event buffers before human input; prohibit logs and model context from raw frames/keys | Canary scan across persisted artifacts/DB/logs/model payloads/exported telemetry (not the legitimate encrypted request to the target) |
| Raw authenticated data leaked after Done | Safe page/origin revalidation and tight evidence collection; minimize private DOM | Synthetic account profile with canary PII remains protected |
| Replay/double-submit | Consumed action receipts, safe checkpoints, no automatic retry on ambiguous effects | Force timeout around submit; exactly-once-or-inconclusive outcome |
| Scope bypass via SSO/redirect | Approved exact origins; external SSO scope review independently authorized | Redirect to unapproved domain blocked without auto-grant |
| Lease theft/replay | Short one-use viewer tickets, signed internal service, origin/cookie, generation fencing | Ticket reuse/stale generation rejected |
| Case-turnover frame mixup | Exact browser_session_id and generation; wipe old buffer | Switch between isolated cases during poll |
| View/capture performance starvation | Bound observer requests, lock wait, JPEG size and viewer count | Compare execution latency with and without observation |
| Worker death | Fail closed; cannot resurrect process-local browser | Kill disposable worker and verify honest UI |
| Misleading status | Typed persisted events, distinct outcome semantics, no invented progress | API/UI contract tests and manual observation |
| Accidental auth reuse | Explicit scope, expiry, run teardown revocation, no persisted state file | Cross-run/target/case replay denied |
| Human signup unintended effect | Exact action approval/target authorization where necessary, no real credentials or third-party effects in tests | Disposable fixture effect count and duplicate decision test |

**Non-negotiable:** do not weaken network/origin constraints for usability. Do not claim a protected site permits remote login just because the viewer is connected. No prod SSO/CAPTCHA claim without provider-specific verification and permission. Production ingress requires reviewed HTTPS/WSS, proxy routes, auth cookies, tenant scoping, network egress enforcement, role permissions and adversarial tests.

---

# 11. Implementation plan, exact integration points and staged gates

Use **one incremental feature branch / small reviewable commits** (only after user authorizes commits/pushes), no broad rewrite. An implementing agent should first reconcile the current local branch and the existing plan; do not blindly add already-present worker `observe` implementations.

| Stage | Scope | Key source locations | Gate: must prove before next |
|---|---|---|---|
| **L0 — Baseline and design contracts** | Inspect local HEAD/diff/migrations/ports, actual route inventory, typed status/authority model; compare this doc with current source. No code churn yet. | `docs/hitl/*`, `docs/ui/*`, router, control API, worker, DB schema | Baseline matrix: exists/partial/missing/untested; zero work lost |
| **L1 — Public observation and security** | Reuse low-level worker observer, add Control API metadata/activity/frame, signed binary worker client, post-capture authority check, exact browser generation. | `services/control-api/src/markettwin_control_api/api/live_browser.py` **new**; `.../services/hitl_worker_client.py`; `.../persistence/repositories/test_run_results_repository.py`; `.../main.py`; worker `owner_service.py` / `viewer_authority.py` | Real Chromium JPEG through authenticated API; wrong actor/session/role/mode blocked; no capture leak |
| **L2 — Live Execution UI** | Replace Activity placeholder; main nav, run/current work, real frame, typed timeline and step inspector; responsive states; clear stale frame on turnover. | `apps/web/src/pages/runs/RunActivityPage.tsx`, `apps/web/src/layouts/RunLayout.tsx`, `apps/web/src/lib/api.ts`, new small focused components, existing tokens/CSS | User sees a real synthetic executing page and steps, no input in read-only, correct case switching |
| **L3 — Contextual HITL in workbench** | Integrate pending requests, viewer claims, reconnect, Done/Skip and approvals with one lease owner and proper role gates. Avoid parallel duplicate lease controllers. | `HumanActionPage.tsx`, `HumanBrowserViewer.tsx`, shared controller hook/component, existing human-actions APIs | Same browser preserved through synthetic login/MFA; no overlapping inputs; failed release handled |
| **L4 — Agents + test understanding** | Reorganize global/run Agents around tester/goal/journey/outcome; move YAML and model details to Advanced; populate/hide placeholder perspectives/missions truthfully; improve Overview/journey navigation. | `ProjectAgentBrowser.tsx`, `AgentPromptsPage.tsx`, `AgentTree.tsx`, `RunFlowPanel.tsx`, `RunJourneysPage.tsx`, `RunOverviewPage.tsx`, `RunPerspectivesPage.tsx`, `RunMissionsPage.tsx` | Unfamiliar user can identify actual tester/goal/step/outcome without opening YAML; no fake personas |
| **L4a — LangSmith trace validation** | Verify actual OpenTelemetry HTTP export to the existing LangSmith project; inspect redacted span hierarchy and safe correlation; optional diagnostic link behind authorization. No new tracing framework. | Shared `observability.py`, ADK `observability.py`, current local env, `docs/ui/VERIFICATION.md` | One real synthetic trace located and correlated; secret-canary redaction verified; disabled exporter does not break execution |
| **L5 — Cooperative manual pause** | Create durable pause request/acknowledgment, safe action-boundary checks in both modes, adapt existing human lease machinery; timeout/cancellation/worker-loss semantics. | Proposed API + DB migration **only if needed**, `BrowserController`, `journey_executor.py`, `case_execution.py`, run state, human suspension repositories | Pause acknowledged after safe boundary, no replay; exact same live browser claim/resume; in-flight failure honest |
| **L6 — Verification and product usefulness** | Full isolated UI → API → DB/outbox → Kafka → real browser → HITL → evaluator/report; performance/privacy/accessibility/usability. | Existing fixture/e2e suites, `docs/ui/VERIFICATION.md`, `docs/hitl/README.md` | Complete published evidence matrix; negative cases and grounded report classifications pass |

### Dependency and concurrency notes

- L1 must define types before L2 integration; one owner per shared file. L4 UX work can progress independently after status/data contract is agreed.
- L3 should preferably **reuse** a shared controller rather than duplicate `HumanActionPage` stateful hooks in both routes. Lease renewal/cancel/disconnect semantics must survive React navigation/unmount or explicitly be recovered server-side.
- L5 is high risk and should be separately reviewed and perhaps held behind feature flag until L1–L4 are demonstrably stable.
- Do not introduce additional UI streaming infrastructure, Kafka frame topics, or durable frame storage until measured need justifies the change.
- Preserve existing CLI/local setup, migrations and environment. Particularly, verify Kafka broker selection; never reset shared offsets, launch duplicate consumers, commit secrets, or touch third-party accounts without approval.

### File-by-file starting checklist

**Frontend:**

```
apps/web/src/app/router.tsx
apps/web/src/layouts/AppShell.tsx
apps/web/src/layouts/RunLayout.tsx
apps/web/src/pages/runs/RunActivityPage.tsx
apps/web/src/pages/runs/HumanActionPage.tsx
apps/web/src/pages/runs/HumanBrowserViewer.tsx
apps/web/src/pages/runs/AgentPromptsPage.tsx
apps/web/src/pages/runs/RunJourneysPage.tsx
apps/web/src/pages/runs/JourneyDetailPage.tsx
apps/web/src/pages/runs/RunOverviewPage.tsx
apps/web/src/pages/runs/RunEvidencePage.tsx
apps/web/src/pages/runs/RunFindingsPage.tsx
apps/web/src/pages/runs/RunReportPage.tsx
apps/web/src/pages/runs/RunPerspectivesPage.tsx
apps/web/src/pages/runs/RunMissionsPage.tsx
apps/web/src/components/markettwin/ProjectAgentBrowser.tsx
apps/web/src/components/markettwin/AgentTree.tsx
apps/web/src/components/markettwin/RunFlowPanel.tsx
apps/web/src/lib/api.ts
apps/web/src/styles/*  (reuse existing semantic tokens)
```

**Control API & DB:**

```
services/control-api/src/markettwin_control_api/api/live_browser.py (proposed)
services/control-api/src/markettwin_control_api/api/human_actions.py
services/control-api/src/markettwin_control_api/api/test_run_results.py
services/control-api/src/markettwin_control_api/services/hitl_worker_client.py
services/control-api/src/markettwin_control_api/persistence/repositories/test_run_results_repository.py
services/control-api/src/markettwin_control_api/main.py
packages/database-python/src/*  (inspect actual model path)
database/migrations/versions/*  (new pause migration only if justified)
```

**LangSmith diagnostic export (existing stack; no replacement):**

```
packages/shared-python/src/markettwin_shared/observability.py
services/execution-orchestrator/src/markettwin_execution_orchestrator/observability.py
services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/planning.py
services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/journey_executor.py
```

**Execution:**

```
services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/owner.py
services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/owner_service.py
services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/viewer_authority.py
services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/viewer_gateway.py
services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/controller.py
services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/human_control.py
services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/auth_session_broker.py
services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/journey_executor.py
services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/case_execution.py
services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/multi_persona_executor.py
services/execution-orchestrator/src/markettwin_execution_orchestrator/persistence/step_recorder.py
services/execution-orchestrator/src/markettwin_execution_orchestrator/worker.py
```

**Test/docs examples:** `apps/web/e2e/run-flow.spec.ts`, `apps/web/e2e/ui-workbench-design.spec.ts`, `apps/web/src/pages/runs/HumanActionPage.test.tsx`, `HumanBrowserViewer.test.tsx`, `services/execution-orchestrator/tests/test_live_browser_observation.py`, `test_runtime_human_assistance.py`, `test_human_action_abandon_expiry.py`, `services/control-api/tests/test_human_action_response.py`. These are starting points; find newer tests before adding duplicate ones.

---

# 12. End-to-end acceptance matrix (synthetic local; separate production)

Record each as **Passed / Failed / Blocked / Inconclusive / Not run**, with exact command, run ID, expected and actual output, source commit, evidence location and what was independently observed. “Frontend component tests pass” is not equivalent to “the real browser takeover works.” Avoid additive test counts when suites overlap.

## 12.0 LangSmith verification prerequisites (existing diagnostic stack)

| ID | Test | Expected |
|---|---|---|
| LS-01 | Inspect actual effective exporter configuration without printing tokens | Selected LangSmith endpoint/project correct; content capture disabled |
| LS-02 | Execute a disposable synthetic Google ADK persona test with telemetry enabled | A corresponding trace appears in the selected LangSmith project with correct timestamps |
| LS-03 | Compare trace safe IDs and persisted run/journey/step IDs | Correlation supported for all claimed fields; missing propagation explicitly marked |
| LS-04 | Scan trace attributes/events for synthetic password/OTP/token canaries | Zero sensitive canaries in exported trace; investigate any leak before release |
| LS-05 | Disable exporter or simulate failed delivery in isolated test | Testing pipeline completes or reports its own legitimate failure, not a fabricated application defect |
| LS-06 | Open advanced diagnostics as unauthorized/not-in-LangSmith user | No privileged diagnostic data exposed or guessed trace deep-link |

## 12.1 Core user understanding

| ID | Trial | Expected |
|---|---|---|
| UX-01 | New visitor begins a public synthetic test | After Start, can find Live Execution immediately |
| UX-02 | No browser open during planning | Correct planning state; no stale/fake live image |
| UX-03 | Real persona journey | Tester, goal, selected browser, actual step status make sense |
| UX-04 | Real deterministic feature case | Clearly marked Feature Case; not represented as a human persona |
| UX-05 | Switch selected journey between isolated sessions | Old frame cleared, new frame only when exact ID/generation matches |
| UX-06 | Select failed step | Expected, observed, cause classification, safe evidence linked |
| UX-07 | Revisit completed run | Historical records work; no “live” image promised |
| UX-08 | Global Agents and per-run Agents | Beginner finds goal/outcome; expert still finds YAML/config |
| UX-09 | Unknown model progress/no recorded new step | Says “No new recorded action yet”; no invented thought |
| UX-10 | Wrong/expired session | Proper error and permission denial; no protected browser pixels |

## 12.2 Live frame and performance

| ID | Trial | Expected |
|---|---|---|
| OBS-01 | Real Chromium, active agent, correct operator | JPEG reaches UI with actual current page |
| OBS-02 | Observer click/type/key input | No input reaches browser; no control lease created |
| OBS-03 | Two spectators / excessive concurrent frame fetch | Bounded resource use and no input rights |
| OBS-04 | Browser busy / capture times out | Viewer says unavailable; agent continues normally |
| OBS-05 | Browser closes/reopens / generation changes | No old pixels mislabeled as new browser |
| OBS-06 | Watch with browser tab hidden | Polling pauses; resumes with fresh authority |
| OBS-07 | Operator permission or target authorization revoked mid-capture | Worker/API deny bytes, frontend clears frame immediately |
| OBS-08 | Human lease becomes active | Observation suppressed; controller only sees protected viewer |
| OBS-09 | 320/390/768/1024/1440 wide | No overflow, legible browser/activity, correct aspect and focus |
| OBS-10 | With/without watcher | Measure p50/p95 frame latency, worker lock contention and test step latency; no invented performance claim |

## 12.3 HITL and controlled side effects

| ID | Trial | Expected |
|---|---|---|
| HIT-01 | Public page contains Sign in link | No false-positive automatic handoff |
| HIT-02 | First-page actual login challenge | Correct request, selected journey, safe pause |
| HIT-03 | Mid-journey login challenge | Existing context preserved; prior steps remain attributable |
| HIT-04 | Login + MFA via human viewer | Credentials not passed to LLM/evidence; safe continuation only |
| HIT-05 | Human claims, disconnects, reconnects | Fresh ticket; same durable lease/generation; no parallel input |
| HIT-06 | Done before successful login | No false identity verified or unauthorized resume |
| HIT-07 | Auth policy requires role | Resume only if exact configured identity/role verified |
| HIT-08 | Optional/unconfigured auth | No invented identity/role, scoped run continuation only if safe |
| HIT-09 | Skip before and during control | Not tested; independent work can continue |
| HIT-10 | Origin redirects to unapproved SSO/console | Permission block/scope review, no automatic expansion |
| HIT-11 | Sensitive one-time action approved | Exactly one effect; no duplicate dispatch |
| HIT-12 | Rejected/duplicate action | No effects; duplicate decision rejected |
| HIT-13 | Two operators race claim | Exactly one controls, second gets no credential pixels/input |
| HIT-14 | Cancel/expire/revoke | Input fenced; session/lease cleanup; accurate durable status |
| HIT-15 | Worker killed during control | Honest unavailable state, no phantom successful resumed browser |
| HIT-16 | Pre/during/post human phase canaries | No password/OTP/token in persisted/log/model paths |

## 12.4 Manual cooperative pause (only after implemented)

| ID | Trial | Expected |
|---|---|---|
| PAUSE-01 | Request during idle-between-steps | Ack at safe boundary; no further dispatch |
| PAUSE-02 | Request during in-flight navigation | “Pause requested” until classified; no false immediate pause |
| PAUSE-03 | Request during mutating submit | No duplicate submit on resume; uncertain effect stays unverified |
| PAUSE-04 | Claim and resume exact browser | Exclusive input and version fencing; same context preserved |
| PAUSE-05 | Human changes page location | Next original assertion revalidated/blocked; no plan rewrite |
| PAUSE-06 | Duplicate request or stale generation | Idempotent or safely rejected |
| PAUSE-07 | Cancel/timeout/worker loss while requested/paused | Deterministic terminal state, no dangling lease/input |
| PAUSE-08 | Persona LLM is responding | UI states waiting for next safe boundary, not instantly paused |

## 12.5 Value, evaluator and product truth

| ID | Trial | Expected |
|---|---|---|
| VAL-01 | Known-good fixture | No invented product defects |
| VAL-02 | Seeded-defect fixture | Correctly linked observed defect or honest miss |
| VAL-03 | Intentionally ambiguous locator | Classified as test/specification issue, not confirmed website bug |
| VAL-04 | Broken DOM text normalization | No false product defect if heading visually present |
| VAL-05 | Redacted query URL / unsupported oracle | Unverified, never silently passed |
| VAL-06 | Unknown authentication role | Not represented as verified account/role |
| VAL-07 | Execution complete but evaluator pending | UI correctly shows pending until report 200 |
| VAL-08 | Persona simulated opinion | Explicitly identified as model hypothesis, linked to behavior, never “real users liked it” |
| VAL-09 | Deterministic Playwright baseline | Compare defect precision, miss rate, false positives and effort before AI value claims |
| VAL-10 | Post-implementation unfamiliar-user study | Observe actual onboarding/interpretation/task completion and misunderstandings |

## 12.6 Accessibility and privacy review

- WCAG 2.2 AA candidate acceptance: screen-reader status text, meaningful labels, keyboard-only operation, focus visible/recovered, no keyboard traps, contrast, reflow at small widths/zoom, reduced-motion behavior and touch targets; **manual testing required in addition to axe**.
- Ensure browser takeover keyboard escape (`Shift+Escape`) and explicit Leave browser keyboard control; browser `Tab` forwarded only during authorized control; unsupported OS/native picker states accurately described.
- All test runs use disposable local synthetic fixtures and dedicated test identities. Network scopes are explicitly authorized; no third-party login replays or paid model calls without approval.
- Restore canonical API/workers only after checking current process and external Kafka configuration. Never reset shared offsets or launch duplicate consumer workers as a workaround.

---

# 13. Performance, usability and operational goals (proposals, not proven metrics)

Set measurement criteria before implementation, then collect actual values on the machine and fixture used. Suggested starting **engineering targets** for review, subject to measurement:

- Timeline event after durable commit: ideally visible within **≤3 seconds** for current 2–5-second polling or better if optimized; never promise exact immediacy.
- Live image nominal **~1 fps** only while visible/authorized; no overlapping calls; enforce ≤2 MiB response and bounded lock/HTTP timeouts.
- A watcher must not materially reduce p95 browser-action throughput; measure watch-on/watch-off against same fixture and compare.
- On permission revocation or human claim, suppress server delivery on next check and clear visible pixels immediately when the client learns of the transition; do not imply instant asynchronous remote revocation unless transport supports push.
- Core Web Vitals are useful for field UX where data exists; local browser tests should focus on interaction responsiveness, large step histories, long-running work, and heavy artifact lists. No fake 100% performance scores.
- User-comprehension study: without instructions, can a new user explain (a) current goal (b) current phase (c) whether human input is required (d) which claims are verified (e) how to inspect evidence? Collect timing/confusion data rather than inventing a satisfaction KPI.
- Provide explicit fallback statuses on API/worker disconnect; graceful handling matters more than endlessly animating a spinner.

---

# 14. Independent adversarial review and second-pass corrections

A second conceptual review was performed against the pinned source facts, prior UI spec and official reference documentation. **This is not a claim that a separate human or independent model reran the code or performed real-browser acceptance tests.** Findings that are likely to prevent expensive misimplementation:

| First-pass assumption/risk | Double-check outcome | Required correction |
|---|---|---|
| “Observation is not implemented” | **Only public/UI path missing** at audited HEAD; low-level worker `observe`, authority and tests exist | Reuse and verify; no duplicate service |
| “Live viewer means video” | JPEG polling renders refreshed images, not guaranteed 30fps continuous video | Label refreshed live image and last-update time |
| “Watch any agent thinking” | Private model reasoning is not an appropriate/available UI data source | Show recorded stages, tool calls and durable observations only |
| “Human takeover is missing” | Existing claim/reconnect/release/skip and viewer already exist in supported synthetic workflows | Integrate and improve; don't replace |
| “Any login link triggers help” | Marketing login link isn't a blocker; real detected obstacles are needed | Conservative challenge classification and test false positives |
| “One action can stop instantly” | Side effects, model calls and browser operations have noninterruptible/uncertain windows | Cooperative pause requested→acked; no replay |
| “Credentials never touch MarketTwin” | WebSocket keyboard transport and in-memory auth snapshots process sensitive state | Precise privacy promise; defend logs/model/evidence; test canaries |
| “Every case is an autonomous persona” | `deep_feature_v1` uses deterministic steps | Distinguish executor modes clearly |
| “Run completed means app worked” | Infrastructure and tested-site results are separate | Status taxonomy and source-linked evidence |
| “80 testers next” | Current planner exactly 3, sequential mission expansion and single worker | Later scoped scheduler/methodology, not this milestone |
| “Existing plan is current in every detail” | Some old implementation tables contradict current repo source | Reconcile current checkout before code |
| “Internal signed worker calls mean authority can't change” | Asynchronous capture creates a permission-change window | Re-check after capture, before returning bytes |
| “A dashboard alone proves product value” | Repository audit says autonomous bug detection unproven | Seeded-defect + conventional baseline value gate |
| “More knowledge or model calls fixes outcomes” | No supported causal evidence of ingestion volume alone being root cause | Separate controlled experiment; prioritize test-oracle accuracy |

### Revision-specific second-pass corrections

- [x] Removed platform comparisons and tool-specific UX mimicry that could be mistaken for integration decisions.
- [x] Kept **LangSmith** as the sole selected technical trace destination; retained existing OpenTelemetry and OpenInference instrumentation because they are present in code.
- [x] Verified the repository uses explicit `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, which requires the **complete traces URL** (different from the base OTLP endpoint). See official LangSmith/OTel documentation.
- [x] Distinguished **code installed** from **environment configured** from **trace actually arrived**, rather than claiming deployed LangSmith success.
- [x] Reconciled the old plan's “low-level observation missing” statement against current `owner.observe` and signed `/observe` implementation; the public API and UI remain unimplemented at the reviewed commit.
- [x] Kept customer-facing activity database-backed; LangSmith is optional advanced diagnostics, not a dependency for watching or HITL.
- [x] Preserved password/session privacy caveats and conservative claims about simulated testers and application defects.
- [x] Retained existing Google ADK, Python Playwright, FastAPI, React, Kafka, PostgreSQL and MinIO; no new execution or observability product recommended.
- [ ] **Must be checked in the local checkout:** exact active LangSmith project, headers, effective `.env`, plugin/exporter version, real trace delivery, owner routing, API restarts and current migration head.

## 14.1 Explicit remaining uncertainties

- No live browser/code execution was performed as part of this research; current local checkout may be newer or dirty.
- Current exact public routes, database schemas, migration heads and environment must be rechecked locally when implementation begins.
- Full production SSO/CAPTCHA, WSS ingress, reliable multi-worker browser owner routing and durable worker-crash recovery are not proven.
- Low-level screenshot capture and lease checks require a full signed-worker/API/browser/React race test, not just a unit test.
- Appropriate number of concurrent observers and acceptable impact on browser actions require actual performance profiling.
- “Worth paying for” requires real user interviews and measured workflow improvement. Technical integration alone is not market validation.

## 14.2 Double-review checklist for implementing engineers

**Before implementing:** one reviewer traces UI → API → SQL → worker → owner code and writes explicit authority/session/state diagrams. A second reviewer independently attempts to falsify assumptions about capture, control transfer and pause. Resolve disagreements with a reproducer. If no independent reviewer is available, document that limitation.

**After implementing:** review screenshots at desktop/tablet/mobile for navigation, live viewing, HUMAN NEEDED and controller states; do real keyboard/screen-reader checks; inspect evidence/results in running UI; compare screenshot labels to actual browser ID and generation; review all secret-canary surfaces including exported LangSmith spans; rerun both execution modes; confirm no forbidden network access.

**Never claim:** “100% secure,” “all agents fully observable,” “complete production HITL,” “zero data processed by server,” “every simulated persona represents a person,” “high bug-detection precision” without measured evidence.

---

# 15. Definition of done / go-no-go

### Live Execution V1 — minimum usable version (observation + contextual HITL)

- [ ] Run navigation exposes **Live Execution** immediately after Start.
- [ ] Real authorized operator sees actual active Chromium page, selected journey/case and activity facts, correctly correlated.
- [ ] Read-only observer cannot inject input; access checks and stale generation/workspace handling pass.
- [ ] Human assistance appears inside workbench on actual supported obstacle, preserving the correct browser context; login/MFA/reconnect/Done/Skip flows pass in **both** execution modes.
- [ ] Password/OTP canaries absent from persisted evidence and model/logging pathways in tested scenarios; limitations disclosed truthfully.
- [ ] Agents/journeys show tester/goal/recorded steps/outcome as primary information; advanced YAML remains accessible but secondary.
- [ ] Seeded-good/seeded-bug outcomes and report/evaluation semantics remain correct through complete isolated pipeline.
- [ ] Responsive/keyboard/contrast checks pass; one unfamiliar user can follow the test without developer coaching.
- [ ] LangSmith-only tracing pipeline has been verified with redacted synthetic spans, or is plainly documented as unconfigured/blocked without affecting execution.

### Manual-pause V1 — separate completion gate

- [ ] Durable pause request and acknowledgment across both executors.
- [ ] True safe boundary; no duplicate or unverified side-effect replay.
- [ ] Exact browser-session takeover with exclusive lease and verified resume.
- [ ] Cancellation, stale requests, timeout, origin/authority revocation and worker loss fail closed.

### Production release — **not** automatically granted by local acceptance

- [ ] Review HTTPS/WSS/auth cookies, trusted worker routing, DNS and network-layer egress, security tests and operational limits.
- [ ] Verify real provider SSO/MFA/CAPTCHA **with explicit authorization** and reviewed accounts, not broad “works everywhere” claims.
- [ ] Assess scaling beyond single consumer and in-memory browser owner before hosted concurrency.
- [ ] Publish retention, scope, session-reuse and credential-handling disclosures; conduct adversarial review.

---

# 16. Codex / engineering handoff — concise execution directive

> Implement MarketTwin **Live Execution + Agent Understandability + Contextual HITL** using this specification and the current local repo. First reconcile `docs/hitl/LIVE_EXECUTION_IMPLEMENTATION_PLAN.md` with actual working code; read the UI master spec to preserve the design system. Work incrementally: public read-only API/authority → real Live Execution UI/timeline → one canonical HITL controller → understandable Agents/journeys → independently gated cooperative pause → integrated tests. Preserve React/TypeScript, Google ADK, Playwright, FastAPI, PostgreSQL, Kafka/outbox, MinIO, the existing OpenTelemetry/OpenInference exporter **with LangSmith as the only selected trace destination**, and all permission boundaries; do not add any second observability backend, sandbox or browser framework. Use the actual computer for UI inspection and real isolated synthetic end-to-end tests. Distinguish code complete from tests truly verified. Add regression tests and exact evidence for all security/session/race transitions. Be factual, challenge the UX and hidden failure modes, and do not push, deploy, incur provider costs, use personal credentials or reset shared Kafka offsets without authorization. Stop to ask when a real authorization/security decision is required.

---

# 17. Verified research/source index — MarketTwin stack and applicable standards only

**Repository-specific source (pinned branch; source audit, not live runtime certification):**

1. MarketTwin source: `https://github.com/Sreenav14/Market-Twin/tree/38431448ded7357c6d7b6010baa0d4c4ad773146`
2. Existing MarketTwin HITL plan: `docs/hitl/LIVE_EXECUTION_IMPLEMENTATION_PLAN.md`.
3. Existing MarketTwin HITL guide: `docs/hitl/README.md`.
4. Prior product-quality verdict: `docs/PRODUCT_AUDIT_2026-10-16.md` (**REFOCUS**).
5. Existing design conventions: `MARKETTWIN_UI_REDESIGN_RESEARCH_CODEX_MASTER_SPEC_2026-10-15.md` and current React tokens.
6. Current instrumentation code: `packages/shared-python/src/markettwin_shared/observability.py` and `services/execution-orchestrator/src/markettwin_execution_orchestrator/observability.py`.

**Official documentation of technology we use:**

7. LangSmith: OpenTelemetry ingestion for our existing Google ADK instrumentation — https://docs.langchain.com/langsmith/trace-with-opentelemetry
8. LangSmith: observability concepts — https://docs.langchain.com/langsmith/observability-concepts
9. OpenTelemetry: OTLP exporter protocol and exact signal endpoints — https://opentelemetry.io/docs/specs/otel/protocol/exporter/
10. OpenTelemetry Python: OTLP HTTP configuration — https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html
11. Playwright Python: Trace Viewer — https://playwright.dev/python/docs/trace-viewer
12. Playwright Python: tracing — https://playwright.dev/python/docs/api/class-tracing
13. Playwright Python: authenticated browser state — https://playwright.dev/python/docs/auth

**Applicable usability, accessibility and security standards (not extra runtime services):**

14. W3C WCAG 2.2 — https://www.w3.org/TR/WCAG22/
15. W3C status announcements — https://www.w3.org/WAI/WCAG21/Techniques/aria/ARIA22
16. OWASP Logging Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
17. OWASP Session Management Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

**Evidence categories:** repository claims = source-verified at pinned commit; external technology descriptions = cited official documentation; current `.env`, latest local code, LangSmith trace ingestion, browser usability and production security = **not independently verified** in this research. Those require implementation/acceptance checks.

---

**Final boundary:** This artifact is an evidence-grounded, implementation-ready proposal, **not a claim that the specified features already work**. The next step is to inspect the latest local checkout and implement L0–L2, validate, then proceed through the gates. The right success metric is whether an authorized user can tell what happened, intervene safely, and trust the resulting evidence—**not** the number of screens, agents, animated logs or generated opinions.

---

# 18. Cross-service audit: code wiring, UX consistency and risk register

The findings below supersede any old-plan assumption that a proposed endpoint already exists or an implementation is absent. Labels **C/D/R/P/U** have the precise meanings defined near the top. A severity expresses development priority, not exploit confirmation. All file paths refer to the pinned pushed commit, not necessarily the working tree on the developer's computer.

## 18.1 Exact remote repository coverage inventory

| Repo area | Tracked files | Relevant responsibility | Review obligation for the full local pass |
|---|---:|---|---|
| `apps/web` | 134 | React pages, routing, permissions, types, browser controls, unit/E2E tests, styles | Every route, state transition, event listener, accessibility state, typed API contract and test fixture |
| `services/control-api` | 113 | FastAPI, auth, tenant/target policy, run lifecycle, HITL, evidence, knowledge links | Every endpoint and persistence effect, authorization checks and idempotency |
| `services/execution-orchestrator` | 167 | Planning, Google ADK, Playwright, agent tools, policy, evidence, HITL and Kafka worker | Every action path, check-before-dispatch, session ownership and recovery |
| `services/evaluation-worker` | 42 | Verified outcomes, finding classification and report creation | Assert evidence validity; never mistake test failures for application defects |
| `services/knowledge-worker` | 47 | Source collection/normalization/preview | Authentication, source control, context trust, extraction and retry/bounds |
| `packages/shared-python` | 30 | Core contracts, policies, telemetry, Kafka helpers | Validation, serialization, stale compatibility and secret-safe logging |
| `packages/database-python` | 17 | ORM models and repositories | Cross-tenant FKs, lifecycle constraints, cascade and index effects |
| `database` | 24 | Alembic schema/migrations and SQL | Downgrade/upgrade ordering, backwards compatibility, constraints and locks |
| `infra` | 10 | Compose/container infrastructure | No credentials in source, local/prod parity assumptions, data persistence |
| `packages/agent-schemas`, `event-schemas`, `mission-schemas`, `policy-rules`, `openapi-client`, `evaluation-rubrics` | 18 total | Workspace package placeholders/contracts | Avoid claiming these automatically generate active contracts; verify consumers |
| Root, docs, scripts and non-code | 70 total | Environment templates, build, architecture, support instructions | Resolve stale docs, deployment assumptions and dangerous runbook commands |
| **Total** | **672** | **All tracked files** | **Only executable locally against the exact checkout; no '100% reviewed' certification here** |

**Inventory note:** Tests are included within the area counts (175 matching test-related paths). Don't sum test count with source count. The inventory excludes untracked/dirty developer files, `.local` artifacts, virtual environments, `node_modules`, ignored secrets, and future pushes. Review those local changes separately before claiming total coverage.

## 18.2 Evidence-backed findings and corrective action

### CW-01 — Live activity is not wired from the public UI to the browser (P0, C)

**Source:** `apps/web/src/pages/runs/RunActivityPage.tsx` still renders `FutureStagePage`. `services/control-api/src/markettwin_control_api/main.py` registers no `live_browser` router and the live metadata/frame methods are missing in the public client. `RunLayout.tsx` hides Activity under **More**. The worker's internal observation transport exists and is distinct from these gaps.

**Impact:** The user cannot watch what an executing agent actually sees, despite the worker's low-level screenshot support.

**Correction:** Reuse signed internal `POST /internal/hitl/observe`; implement public authorization/metadata/volatile-frame projection, integrate precise browser selector with Activity route and promote Live Execution in navigation. Treat observer as read-only. Never conflate a human-control WebSocket ticket with observation authority.

**Verification:** Real local Playwright run viewed in React; screenshot changes across actions; exact active run/journey/session matches; no input is accepted; browser turnover clears stale pixels; both execution modes tested.

### CW-02 — Agent presentation is an internal configuration browser, not a tester-facing narrative (P0 UX, C)

**Source:** `apps/web/src/pages/runs/AgentPromptsPage.tsx`, `components/markettwin/ProjectAgentBrowser.tsx`, `AgentTree.tsx`. The primary content is snapshot chronology, model settings, YAML editor, and rerun controls. The flow panel uses “Meta Agent” and “Sequential Agent” headings; no one-place tester/goal/step/outcome/evidence explanation exists.

**Impact:** Users cannot easily tell who is acting, which browser belongs to a tester, why the action was attempted, or whether the outcome was established.

**Correction:** Distinguish **Simulated testers**, **Testing goals**, **Executed journeys** and **Advanced agent settings**. Preserve the exact YAML editing/rerun route for authorized advanced users; never mutate frozen execution results when changing future prompts. Feature Cases must not be misrepresented as LLM personas. Back tester cards with actual persisted journeys, not invented avatar demographics.

**Verification:** An unfamiliar tester locates current task, step evidence and outcome without YAML access; technical reviewer can still inspect model/tool snapshot and prepare a versioned rerun; read-only members cannot mutate settings.

### CW-03 — Separate Human Assistance route fragments the user journey (P0 UX, C)

**Source:** `HumanActionPage.tsx` implements claim/renew/reconnect/Done/Skip and approvals but is separate from the active-browser/step view. `RunLayout.tsx` links to it only in a conditional banner/tab; Activity remains a placeholder.

**Impact:** Assistance appears disconnected from the triggering step or current screen.

**Correction:** One canonical Live Execution workbench surfaces the request, exact journey, safe reason and same browser. Reuse the existing lease logic through **one shared lease-state owner**. Preserve old routes and server-side lease behavior; don't mount duplicate independent controllers or accidentally release on route unmount.

**Verification:** Test first-page and delayed synthetic login, lease refresh across UI navigation and reload, two tabs/operators, reconnect, Done/Skip, and no duplicated input client.

### CW-04 — Operator-requested cooperative pause does not exist (P1 architecture, C)

**Source:** `browser/controller.py` has authentication/approval checkpoints and a session lock; `workflow/journey_executor.py` has an ADK event loop; `case_execution.py` persists steps. No general durable user-issued pause command, acknowledged checkpoint, or manual-pause lifecycle was found in reviewed execution/control code.

**Impact:** “Pause now” would be a misleading button and could race a submitted form or in-flight model/tool operation.

**Correction:** After observation/HITL integration, add a typed, durable **pause requested → quiescing → paused → human eligible → verifying → resumed/blocked** state machine. Fence new actions at cooperative boundaries in **both** modes, acknowledge only after in-flight mutation is known safe, and never auto-replay uncertain submits.

**Verification:** Attempt pause before/after simulated click and submit, during model wait, at browser turnover, after worker crash and during an already leased handoff; inspect durable state, side-effect count and UI wording.

### CW-05 — Observation authority needs a final durable pre-send recheck (P0 security review, R)

**Source:** `browser/owner_service.py` `observe(request)` performs `viewer_authority.observer_permitted` before `registry.observe` and responds with bytes. `browser/owner.py` validates local browser mode/generation and origin both before and after screenshot capture. The observed route does **not visibly repeat the DB entitlement check after the capture**; a permission change during that asynchronous interval warrants examination. This is an architectural TOCTOU *risk*, not evidence of successful leakage.

**Correction:** Add a fail-closed, second durable authorization and current-generation check immediately before returning bytes. Audit target origin, permission changes, request cancellation and all denial codes. Bound screenshot capture time, not only lock acquisition. Avoid exposing raw browser/CDP operations.

**Verification:** Concurrency test revoking membership or target approval while `Page.captureScreenshot` is artificially delayed; no post-revocation frame; no cached sensitive pixels after API denial.

### CW-06 — Login privacy statement must be technically accurate (P0 trust/security, C)

**Source:** `HumanBrowserViewer.tsx` sends text/keyboard events over the protected WebSocket; `viewer_gateway.py` validates and forwards them; `owner.py` inserts them into the worker-controlled Chromium page. `browser/human_control.py` stops evidence trace and suspends capture before human entry. `browser/auth_session_broker.py` can hold scoped cookie/storage snapshots in process memory.

**Fact:** Passwords are **not intended to be given to the model or recorded**, but plaintext keystroke transport and browser session secrets are **processed by MarketTwin infrastructure**. The target site/IdP also receives them. Do **not** state “credentials never leave the device” or “no credentials are handled anywhere.”

**Correction:** Disclosure language must say *“Enter login details yourself in the protected browser; they are not requested by the AI agent. MarketTwin forwards your input to the browser, and its session state may be held temporarily for authorized test reuse. We do not intentionally store credential keystrokes or credential-entry frames.”* Confirm actual transport encryption and secret handling per deployment. Restrict use to dedicated test accounts. Full zero-server-plaintext privacy would require a different, user-local browser design.

**Verification:** Inject uniquely identifiable dummy password, OTP, bearer token and cookie canaries, then scan model requests, API/worker logs, Kafka payloads, database records, stored artifacts, traces, request errors, diagnostic exporters and browser cache for violations.

### CW-07 — Authenticated screenshots need a post-handoff privacy policy (P0 data handling, R)

**Source:** `browser/evidence.py` masks common input/text selectors for authenticated-session screenshots, while the page may display secrets in non-input elements (profile text, tables, notifications, custom widgets). Runtime assistance disables raw traces; this is valuable but not comprehensive.

**Correction:** Separate evidence-capture policy before/during/after human control. Do not claim selector-based masking identifies all sensitive information. Adopt least-privilege test accounts, content restrictions, optional page/region redaction and artifact access controls. Agent evidence should not automatically expose full authenticated page contents to operators lacking approval.

**Verification:** Synthetic password/token canaries in text nodes, custom elements, popups and redirected pages; attempt artifact download and evaluation access by users with insufficient roles.

### CW-08 — Session reuse is intentionally real, so isolation/revocation must remain explicit (P1, C/R)

**Source:** `browser/auth_session_broker.py` stores bounded in-memory snapshots and copies scoped cookies/storage into fresh contexts; it is not a credentials vault or persisted login file. `workflow/auth_bootstrap.py` opens a browser for discovery/login and then closes it; subsequent cases can inherit intentionally scoped state.

**Correction:** Define who authorizes reuse, the target/run/scope limits, TTL and disposal. Ensure failed/skipped/cancelled requests revoke the right snapshots and that cross-run/target/role/tenant reuse cannot occur. Mark signup as a **side effect** requiring explicit approval; creating an account is not merely authentication.

**Verification:** Try two accounts, changed roles, mixed target subdomains, runs with different approvals, logout, expiry, worker restart, multiple cases and cancellation. Verify that the UI explains when an existing authorized session is reused.

### CW-09 — Runtime assistance ≠ universal login/SSO detection (P0 reliability, C/D/U)

**Source:** `NewRunPage.tsx` supplies `runtime_human_assistance=true` on normal creation and Control API accepts it for protected targets without an upfront identity policy. `browser/controller.py` binds authentication encounter callbacks; existing documentation reports synthetic successful handoffs. External SSO/CAPTCHA, every login layout and dynamically loaded federated login remain unverified.

**Correction:** Distinguish observed authentication barriers from a mere “Log in” link, generic 403, unapproved origin, broken selector or missing feature. If a redirect leaves frozen approved origins, raise **scope review required** before any browser access; do not auto-grant arbitrary subdomains. Provide an agent-side structured request for help without trusting the LLM's claim alone.

**Verification:** Synthetic first-page/delayed/incorrect-credentials/MFA/SSO-like redirect and scope-denied fixtures, plus a separately authorized external pilot. Actual browser origin enforcement must hold during manual control.

### CW-10 — UI statuses and results have different truth domains (P0, C)

**Source:** `RunOverviewPage.tsx` maps run status to lifecycle; `RunJourneysPage.tsx` presents execution status and outcome; deterministic and persona evaluators operate later. Historical audits explicitly describe tests that completed infrastructure execution but did not validate expected behavior.

**Correction:** Render run lifecycle, browser/worker availability, journey execution, assertion verification, findings and report readiness separately. Model-generated “satisfied” is not a confirmed website defect or usability vote. Never infer universal coverage, progress %, or real customer sentiment from a fixed number of synthetic journeys.

**Verification:** Seed ambiguous text locator, incomplete evidence, blocked origin, successful browser action but failed assertion, evaluation pending and all-journeys-failed runs; prevent misleading green overall success.

### CW-11 — Three personas and sequential execution are hard-coded V1 constraints (P1 design, C)

**Source:** `agents/schemas/plan.py` requires exactly 3 personas. `workflow/testing_depth.py` allows up to 4 missions; `workflow/multi_persona_executor.py` invokes sequential journey execution. This is **not** configurable 10/20/50 simulated users and **not** 80 simultaneously executing agents.

**Correction:** Display real fixed counts and queue accurately. Do not add a population slider as a decorative frontend parameter. Future scaling requires plan-schema versioning, scheduler/backpressure, model/request budgeting, browser isolation, honest repeatability and a valid synthetic research methodology.

**Verification:** Three personas × N missions yields N×3 journeys, in observed order; UI displays one active browser and skips closed sessions; report counts actual executed work.

### CW-12 — LangSmith configuration is intended but trace arrival is unproved (P1 operational, C/U)

**Source:** `.env.example` includes `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://api.smith.langchain.com/otel/v1/traces`, `OTEL_EXPORTER_OTLP_HEADERS=...`, and `MARKETTWIN_OBSERVABILITY_ENABLED=false`. Shared observability initializes a Python OTLP/HTTP span exporter; execution observability instruments Google ADK through OpenInference with content hidden unless explicitly enabled.

**Correction:** Retain **only LangSmith as destination**, existing OpenTelemetry/OpenInference for instrumentation, and MarketTwin database for product-authoritative events. Check real `.env` with redaction, exporter wiring, project header, correct signal URL, credentials, network reachability, service restart and trace receipt. Do not use raw model trace text as a user-facing activity feed.

**Verification:** One synthetic run with a unique ID and model/tool spans; check correlated run/execution/journey IDs in LangSmith. Keep content-capture disabled and verify canaries absent.

### CW-13 — Existing docs disagree with current low-level code (P1 maintenance, C)

**Source:** `docs/SESSION_HANDOFF.md` and `docs/hitl/LIVE_EXECUTION_IMPLEMENTATION_PLAN.md` contain older claims that worker observation and its test file do not exist, but pinned source includes `owner.observe`, `viewer_authority.observer_permitted`, internal `owner_service.observe` and a Chromium test file.

**Correction:** Update handoff/runbooks by exact commit and role; mark old status as historical. Source and repeatable tests outrank stale narrative. Do not delete old audits; annotate them as superseded.

**Verification:** Search docs for “not implemented”, “not exist”, “current”, “paused”, “head” and reconcile each statement against paths, commit and actual test result.

### CW-14 — Live UI lacks a durable, unified activity projection (P0, C)

**Source:** `ExecutionStepRecorder` commits action starts and finishes; `test_run_results_repository.py` already exposes safe summaries for journey steps; `test_run_results.py` exposes `/flow`, journeys and results. There is no unified bounded public activity endpoint combining planner, discovery, persona, Feature Case, human request, approval and evaluation, and no live browser binding in the React API client.

**Correction:** Introduce typed stable event IDs/cursors and source labels; reuse `ExecutionStep`/`RunEvent`/HITL/approval records rather than storing a duplicate stream. A finite API page should carry durable timestamps, source, run/journey/execution context, status and strictly allowlisted safe summaries. Never display private chain-of-thought or unredacted prompts.

**Verification:** Out-of-order commits, reconnect/polling, report generation after execution, stale session selection and duplicate delivery; no duplicate or missing activity rows and no fabricated stage completion.

### CW-15 — Single-worker HII waiting and browser ownership limit scalability (P1 operations, C/D)

**Source:** Browser registry is process-local. Existing handoff documentation notes the current single execution-consumer queue can remain occupied while awaiting a human. Multiple workers without explicit owner routing would not be able to resolve arbitrary browser sessions by ID.

**Correction:** Show queue delay and browser unavailable truthfully. V1 must not promise arbitrary parallelism or crash resurrection. Long term, make owner routing and worker lease expiration explicit before multi-worker rollout. Do not silently launch a second consumer as a debugging workaround.

**Verification:** One waiting-for-human run + another queued run; worker loss; stale owner; system restart; Kafka redelivery; no replay of unsafe actions or false green status.

### CW-16 — Viewer keyboard/input ergonomics and full-browser compatibility require real UX tests (P1, R)

**Source:** `HumanBrowserViewer.tsx` forwards mouse, wheel, limited keys and text via a password-type proxy input and canvas; it requires a decoded first live frame before enabling input. That is a reasonable restricted V1 input surface, not an arbitrary desktop session.

**Correction:** Test keyboard focus, typing of Unicode/IME, paste, backspace, tab order, responsive viewport mapping, mobile soft keyboard, popups, multi-page auth and CAPTCHA widgets. State clearly when a target requires unsupported interaction and allow safe Skip. Avoid broadening input tools without explicit security review.

**Verification:** Synthetic form with non-Latin text, Shift+Tab, resize, mobile viewport, action after reconnect, prevented duplicate sequence, and keyboard escape from browser control.

### CW-17 — Evidence and evaluation must be validated independently of the attractive UI (P0 product value, D/U)

**Source:** `services/evaluation-worker` has deterministic evaluation, deep evaluator and report-generation implementations; current repository audit `docs/PRODUCT_AUDIT_2026-10-16.md` states that autonomous model-generated defect discovery beyond conventional Playwright has **not** been demonstrated. Fixture-driven synthetic E2E success does not prove live-model quality.

**Correction:** Run seeded-good and seeded-bad applications with a stable oracle, compare to a basic Playwright baseline, classify false positives and missed defects, record costs and repetitions, validate evidence ownership and report consistency. UI must separate simulator impressions from independently grounded findings.

**Verification:** For each case, verify exact expected defect, independent reproduced behavior, evidence references, side effects, task outcome, appropriate diagnosis, and stability across repeats; record inconclusive separately.

### CW-18 — Configuration sample has potential operability hazards (P2, R)

**Source:** `.env.example` contains duplicate `KAFKA_BOOTSTRAP_SERVERS` entries and a mixed-case example S3 bucket `marketTwin-local`. Duplicate assignments complicate diagnosis; S3-compatible backends have naming restrictions that must be checked in the actual target. These are **sample hygiene and validation tasks**, not confirmed production bugs. The `.env.example` sets observability disabled by default; enabling requires intentional secret-safe configuration.

**Correction:** Consolidate duplicate env entries and validate bucket naming against the actual object store. Never expose literal real keys; don't treat the example as proof of running configuration. Review both `HITL_INTERNAL_SECRET` and `MARKETTWIN_HITL_INTERNAL_SECRET` with the relevant API/worker parser, and ensure they represent an intentionally shared secret rather than two accidentally independent values.

**Verification:** Parse environment in isolated CI; start local disposable services and run one bounded artifact upload; verify Kafka/OTLP/HITL startup and redact environment logging.

### CW-19 — Foundational code health and security cannot be inferred from historical test summaries (P1 gate, U)

**Source:** `pyproject.toml` defines strict Pyright, Ruff and pytest; `apps/web/package.json` defines typecheck, Vitest, Vite build and Playwright E2E. Some historical handoffs describe repository-wide Pyright failures and *focused* checks passing; which baseline is current has not been rerun here. The common E2E `apps/web/e2e/run-flow.spec.ts` uses API fixtures; it is not a production pipeline integration test.

**Correction:** Execute the **full** local code/test workflow in Section 19, preserve all failures without weakening tests, and distinguish mocked UI tests, real Chromium tests, full Kafka/DB pipelines and external live-model trials. Use explicit baselines for pre-existing warnings.

**Verification:** Attach complete stdout/stderr summary, fail counts, exact environment/revision (excluding secrets) and a per-file review ledger. No test result may be invented from a documentation assertion.

## 18.3 System wiring map and must-check continuity

| Boundary | Existing evidence | Integration question | Acceptance criterion |
|---|---|---|---|
| React → Control API | Typed API client, protected cookie session, run page queries | Does UI use exact routes and no stale client types? | Contract tests and real authenticated UI exercise |
| API → PostgreSQL | Run/human action/result repositories | Are tenant ownership and run identity checked on each read/write? | Cross-workspace/role negative API tests |
| API → Outbox → Kafka | Run dispatch + outbox | Can an accepted run be lost or dispatched twice? | Crash/retry/idempotency tests, no offset resets |
| Kafka → Execution worker | Worker consumer and run status transitions | Does an orphan/replayed message resume unsafe work? | Duplicate-delivery/worker-loss tests |
| Planner → frozen work | Meta plan schemas, snapshots, policy | Are unsupported targets/expectations invented? | Invalid plan and no-ground-truth fixtures denied or inconclusive |
| Persona → browser tools | ADK + bounded controller tools | Are all tools exact-session-bound and policy-filtered? | Wrong execution/journey/session rejected |
| Feature Cases → browser | Deterministic `case_execution` | Are in-flight side effects never replayed? | Submit-once/cancellation/approval tests |
| Browser → private worker viewer | Signed HTTP / lease WebSocket | Can observed frames or input cross a generation boundary? | Revocation/race/stale session tests |
| Private worker → public observation | **Missing public path** | Do worker frames get exposed with independent read-only auth? | New route, binary bounds, no-store, no input capability |
| Activity → safe persisted events | Step and run-event records | Are displayed status/activity truthful and ordered? | Cursor/late commit/duplicate event tests |
| HITL → resume | Durable request/lease/suspension + same context | Does release prove safe page and revoke input? | Same-session browser verified; denied resume fenced |
| Browser → artifact store | Screenshot/ARIA/trace pipeline | Are stored records from correct execution and redacted? | Artifact ownership & canary scan |
| Evaluation → report | Deterministic/deep evaluator | Does report honor assertion evidence and not claim product bug on locator mismatch? | Independent ground-truth fixtures |
| OpenTelemetry/OpenInference → LangSmith | Exporter and endpoint example | Are content off and required correlation visible? | Verify actual trace receipt and no secrets |
| Knowledge ingestion → planning | API/worker/selection | Does only approved context reach prompts, under size limits? | Wrong-tenant/poisoned/empty/rich context tests |

## 18.4 UX hierarchy: recommended exact interactions

**A. Application / test index:** Show last tested target, run status and last independently verified result. No fabricated success %, synthetic customer ratings or polished but ungrounded sentiment.

**B. Test Overview:** The first screen shows exact approved scope, study goal, mode and current phase, one *Watch live execution* primary action while running, and a prominent, actionable real pending-request banner.

**C. Live Execution:** A run-stage rail above an exact selected journey; on desktop left tester/case selection, large live browser in center, right activity details and pending assistance. On narrower screens prioritize browser and one collapsible activity drawer. Always show *last frame time*, selected session ID (in advanced info), control mode, observer authorization and genuine unavailable states.

**D. Agent/Testers:** Default to application-specific simulated tester cards with goal, known actions, friction, outcome and evidence. In Feature Case mode, show cases, not fabricated personas. A second *How the system works* explanation names planner, browser executor, evidence verifier and report generator. YAML/model/trace diagnostics move under *Advanced* with existing permissions and rerun semantics intact.

**E. Human Assistance:** Provide the same contextual claim/lease and protected viewer inside Live Execution, preserving the standalone deep link. Show exact supported reason: login, MFA, sensitive-action approval, scope review, interrupted control, unavailable browser or other verified recovery blocker. Scope change is not a login bypass.

**F. Post-run:** Journey playback from durable safe steps/evidence (not a fabricated video); explicit *Confirmed issue*, *Needs verification*, *Test-specification issue*, *Policy restriction*, *Skipped* and *No finding*. Every claim links to a real step/artifact. Provenance records whether a human intervened. No “X% of users liked this” without genuine human-study data.

## 18.5 Order-of-operations corrections to the earlier roadmap

1. **L0 — full checkout reconciliation and local baseline audit** (Section 19): this now precedes any code edits. It must enumerate all tracked/untracked changes, full file-by-file review ledger, tests, local infrastructure and truth source. Preserve dirty files.
2. **L1 — finish and secure existing observation core:** don't recode `owner.observe` or internal `/observe`. Review its screenshot lifecycle, durable final authorization, timeout, frame bounds, origin checks and actual Chromium tests.
3. **L2 — public observation + event contracts:** implement typed metadata, exact-session image response, safe bounded event projection and independent authorization. No credentials/pages/DOM to logs or client caches.
4. **L3 — usable workbench:** replace Activity placeholder, promote nav, wire selected browser and recorded actions, clear old frames. Accessibility/readability/responsive checks required.
5. **L4 — contextual HITL integration:** one lease state owner; same browser; Done/Skip/reconnect; secure after-login gating; prevent human frames in public observer.
6. **L5 — Agents explainability overhaul:** tester/goal/outcome/evidence first; advanced prompt editor retained; Feature Cases named honestly; existing persistence reused.
7. **L6 — safe manual pause:** only after L1-L5 behavior is accepted; cooperative at action boundary, durable acknowledgement, no mutation replay.
8. **L7 — independent benchmark and adversarial acceptance:** full API/DB/outbox/Kafka/worker/browser/evaluator/report plus LangSmith trace receipt; compare defect discovery against real ground truth.
9. **L8 — operational/go-no-go:** document supported single-owner topology, remaining limits, release security checks, reproducible startup and no unsupported production-readiness claim.

**Stop rule:** Do not mark a milestone complete if it passes only mocked UI tests. Don't introduce new observability platforms or new sandbox runtimes. If the latest local checkout has already implemented a feature, audit/verify it rather than overwrite it.

# 19. Required exhaustive local checkout audit — before claiming 'every line of code'

This section is executable guidance for Codex or an engineer with the user's actual checkout, not a claim that the steps were executed in this session. It is intentionally scoped to *all tracked application code* and is the missing part needed to substantiate the request for exhaustive code review.

## 19.1 Establish exact source and preserve work

From the Windows PowerShell repository root:

```powershell
git status --short
git branch --show-current
git rev-parse HEAD
git diff --stat
git diff --cached --stat
New-Item -ItemType Directory -Force .local\audit | Out-Null
git ls-files | Set-Content .local\audit\tracked-files.txt
```

Capture untracked code separately (`git status --porcelain`) without reading `.env`, real tokens or private user data into any generative model. Use source content from the actual current checkout, not just the remote SHA, when differences exist. Preserve old/dirty files; do not run autoformatters until the baseline is recorded.

**For each tracked code file**, enter an audit-ledger row containing: path, exact SHA/working-tree version, reviewer, subsystem, date, inspected yes/no, relevant public API/caller, trust boundary, primary invariants, tests inspected, issue IDs, verification status, and whether it is generated/placeholder/test-only. For migrations, also record schema predecessor, upgrade, downgrade, deployed-head compatibility and non-destructive safety. Create a separate ledger for ignored but required runtime config without storing secrets.

No auditor should say “every line inspected” until `audited_code_files == enumerated_code_files` and every row has evidence. Static scans are useful indexing, **not** substitutes for semantic review.

## 19.2 Repository-wide static diagnostics (safe to run without live credentials)

```powershell
# Run after uv sync / npm install as appropriate for the local environment.
uv run --no-sync ruff check .
uv run --no-sync pyright
npm --workspace @markettwin/web run typecheck
npm --workspace @markettwin/web run build

# Inventory implementation debt; inspect every hit, don't auto-dismiss.
rg -n 'TODO|FIXME|NotImplementedError|FutureStagePage|pass$|except Exception|except BaseException' apps services packages database infra
rg -n 'dangerouslySetInnerHTML|localStorage|sessionStorage|eval\(|exec\(|subprocess|pickle|shell=True' apps services packages database infra
rg -n 'HITL_INTERNAL_SECRET|MARKETTWIN_HITL_INTERNAL_SECRET|OTEL_EXPORTER_OTLP|MARKETTWIN_OBSERVABILITY|KAFKA_BOOTSTRAP_SERVERS' .env.example apps services packages infra
```

If `rg` is not installed, use `Get-ChildItem -Recurse` + `Select-String` or install ripgrep independently. Be cautious: searches over `.env` or local artifacts could leak secrets; the commands above deliberately search `.env.example` and tracked source only. Even when lint succeeds, examine policy bypasses and missing runtime wiring manually. Historical strict-Pyright failures must be recorded, not concealed.

## 19.3 Test execution tiers and evidence classes

Only after determining test fixtures and preparing isolated dependencies:

```powershell
uv run --no-sync pytest -q
npm --workspace @markettwin/web run test
npm --workspace @markettwin/web run test:e2e
```

Do **not** run against shared Kafka offsets or production credentials. The E2E suite contains mocked/API-routed tests: passing it does not prove a real worker or browser handoff. Create a separate fully integrated disposable environment, using local or explicitly approved Kafka/PostgreSQL/MinIO and synthetic accounts, for the full chain. Report each tier separately: source-static, isolated unit, mocked frontend E2E, real Chromium owner tests, DB contract tests, synthetic full stack, external/production pilot (not authorized by this spec).

**Critical negative/race cases:** revoked operator while frame capture is pending; wrong workspace/target/run/browser/generation; observer attempts input; operator-operator control race; viewer disconnect; pause during submit; worker loss and retry; stale Kafka command; authentication/session reuse crossing scope; credential canaries in traces/logs/artifacts/telemetry; incompatible migration head; duplicated outbox dispatch; manipulated finding evidence; untrusted knowledge prompt injection.

Each new finding must carry reproducible steps, exact file/line and code SHA, expected vs observed, bug vs test limitation, proposed change, before/after regression evidence, and unresolved uncertainty. A test failure is not automatically an application defect.

## 19.4 Per-area minimum review checklist

| Area | Inspect every implementation path for | Mandatory adversarial scenario |
|---|---|---|
| React routes and API client | Auth errors, stale caches, cleanup, permissions, escape/focus, input controls | User changes workspace mid-stream; no stale frame/ticket |
| Frontend Agents/Reports | Mode truth, source provenance, unsupported percentages/opinions | Failed but completed journey never shown as passed |
| Control API | Cookie auth, role, tenant, target authorization and ownership per endpoint | Cross-workspace request/lease/artifact denied |
| Browser controller | Whitelisted tools, origin/DNS/WebSocket/redirect policy, lock state | Unapproved IdP / new domain blocked before access |
| Observation/HITL | Snapshot access, claim, renewal, generation, viewer ticket, disconnect | No observer/input escalation; no human/agent overlap |
| Planner/agent workflow | Exact frozen plan, budget, timer, bad model output, replay limits | Fabricated expectation cannot become confirmed bug |
| Deterministic cases | Step budgets, approval, effect counts, idempotency | Ambiguous submitted mutation never retried |
| Knowledge worker | Source ACL, schema/extraction sizes, injection, error handling | Wrong-tenant and prompt-injection content safely handled |
| Kafka/outbox/worker | Topic/group config, duplicate/stale events, consumer interruption | Redelivery does not execute a sensitive action twice |
| Postgres/migrations | All 20 migrations, constraints, upgrade compatibility | Apply migrations to disposable seeded prior-head DB |
| Artifact storage | ACL, MIME, signed URL scope, cleanup, credential privacy | Private screenshot never downloaded cross workspace |
| Evaluation/reporting | Independent evidence, assertion ownership, classification | Locator ambiguity not called product failure |
| OpenTelemetry→LangSmith | OTLP HTTP env, safe masking, correlation, exporter flush | Synthetic secret canary absent, trace arrives correctly |
| Infra/deployment | Private bridge binding, HTTPS/WSS, egress, resources | Viewer exposed externally or worker egress broad by mistake |

## 19.5 Source-by-source review completion and second reviewer

A complete local audit delivers:

1. **Full tracked-code manifest** with no unreviewed source/migration/config file hidden behind an aggregate count, plus extra modified/untracked code entries.
2. **Findings register** with severity, confidence, impact, file/line, owning service, root cause, minimal fix, regression test and final verification state.
3. **Cross-service wiring graph** for every supported UI action and worker transition. An ORM model existing without a public/API call is *not* a functioning feature.
4. **Complete tests and environment matrix** containing exact test commands, isolated setup, successful/failing counts, skips, warnings and blockers.
5. **Independent challenger pass** that specifically attempts to falsify critical architecture/security/status claims. Review comments must be resolved or recorded as disputed.
6. **Updated versioned specification** with unresolved questions, what must be fixed first, what must not be expanded, implementation/QA owners and release checklist.

Do not treat a code search, model review, or archived test summary as complete. If the user wants a literal “every line of code” certification, the local checkout needs to be available and the audit ledger must be filled; the remote-only review above does not constitute that certification.

# 20. Final double-check and decision log

| Double-check | Result at pinned remote SHA | Remaining evidence needed |
|---|---|---|
| Only chosen observability vendor? | **Yes:** LangSmith destination; OpenTelemetry/OpenInference existing instrumentation | Actual exporter/project trace arrival |
| Competing sandbox/browser/agent frameworks required? | **No:** preserve current Python Playwright, Google ADK, FastAPI and Kafka | Only reconsider after hard product requirements |
| Low-level read-only observation already exists? | **Yes (source):** owner, authority, internal route, Chromium test | Run the Chromium and concurrency tests locally |
| Public Live Execution view wired? | **No (source):** Activity placeholder / missing public API | Implement and integrated test |
| Existing HITL browser input path? | **Yes (source):** lease WebSocket, protected viewer and control transitions | External SSO, CAPTCHA, mobile/IME security pilot |
| User credentials never traverse server? | **No:** remote WebSocket input reaches worker Chromium | Privacy disclosure and secret-canary verification |
| General human-requested pause done? | **No (source):** authentication checkpoints are not generic pause | Durable pause + safe action fence |
| Agents UX user-comprehensible? | **Not demonstrated:** YAML/configuration is primary UI | Usability tasks with unfamiliar operators |
| Exactly three persona count hard-coded? | **Yes (source)** | Planner migration only later |
| Multi-agent parallel execution already present? | **No for current persona execution path** | Scheduler/routing design later |
| Whole repository audited line-by-line? | **No:** tree and critical paths reviewed; complete local audit required | All-code ledger and full test results |
| All code working and product useful? | **Not established** | Independent end-to-end tests + seeded defects/baseline |

**Decision:** Keep the existing stack. **Finish the user-visible observation/HITL capability**, make Agents and outcomes understandable, then introduce genuinely safe operator pause. Prioritize secure authenticated observation and trustworthy classification over additional AI narrative. Run the full local codebase audit before declaring an implementation milestone complete, and demand independent evidence of real defect discovery before expanding the persona population.

