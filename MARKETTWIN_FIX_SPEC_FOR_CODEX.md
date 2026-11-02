# MarketTwin — Fix Specification for Implementation

**Audience:** An implementing coding agent ("Codex"). This document is your complete task brief. Read it fully before writing code. Where this document says MUST / MUST NOT, treat it as a hard requirement. Where it names a file path, that path was verified against the repository at the baseline commit below — inspect the file before modifying it anyway.

**Repository:** `Sreenav14/Market-Twin`
**Baseline branch:** `feat/batch-1-aws-observability`
**Baseline commit:** `c455d8d` ("update HITL")
**Working branch to create:** `feat/discovery-contract-v1`, branched from the baseline above. Do NOT work on `main` (it contains only a LICENSE). Do NOT merge or delete the legacy code paths in this task (see §3, Non-goals).

---

## 0. How to work through this document

1. Implement in the phase order given in §7 (Phase 0 → Phase 7). Each phase is independently testable. Do not start a later phase until the earlier phase's tests pass, except Phase 1 quick wins which may be done in parallel with Phase 0.
2. After each phase, run the exact commands listed for that phase and record the results in your PR description.
3. Open ONE draft PR per phase (stacked on the previous phase branch is acceptable), titled `fix-v1 phase N: <name>`. Do not open one giant PR at the end.
4. If a requirement in this spec conflicts with something you find in the code, STOP for that item, note the conflict in the PR description, and implement everything else. Do not silently invent a different design.
5. Open questions that require the product owner's decision are collected in §10. Do NOT invent answers to them. Implement the default stated there if one is given; otherwise leave that item out and flag it.

---

## 1. The product goal (what MarketTwin is supposed to do)

Stated by the product owner, in his own framing:

> Create multiple agents with different perspectives that test and validate an app's functionalities — discover what all is there, test how it works, and report how a user feels using it — like a test run plus a "is this market-worthy?" check. Extra checks: hunt for errors / things that are not functioning, and judge whether the app looks and feels like low-quality "AI slop".

In one sentence: **Agents that are like twin users from the app's target market actually use the app, and the owner gets a trustworthy verdict: what exists, what works, what is broken (proven), how it feels, and whether it is ready for real users.**

Everything in this spec exists to make that one loop work. Anything that does not serve that loop is out of scope (§3).

---

## 2. The critical issue (why the current product does not deliver the goal)

### 2.1 Root cause, in one paragraph

**No component of the system ever creates a fixed, machine-checkable definition of "what should happen" for a journey, at a moment when someone has actually seen the app.** The Meta/planner agent invents missions *without opening the app* (its prompt states it has no browser). The persona agent must then discover + perform + judge a mission in a single loop, and the only judge of its free-text success criteria is itself. The deterministic validator can only check that the agent's story is internally consistent and cites real evidence steps — so almost every outcome is downgraded to `inconclusive`. The alternative engine (`deep_feature_v1`) does use machine-checkable assertions, but a failure only counts as a *verified* finding if the caller supplied the exact assertion (oracle) in advance — and the knowledge-ingestion path builds `Requirement`s from prose with **no assertion definitions**, so normal runs can emit cases that pass/fail but **zero verified findings**.

The system is therefore stuck between trusting LLM narration (false bugs) and trusting nothing (0 confirmed findings). This is a workflow-design defect, not a model-quality problem. Changing models, prompts, or timeouts inside the same workflow will NOT fix it.

### 2.2 Evidence for the root cause (from the repository itself)

| # | Evidence | Source |
|---|----------|--------|
| E1 | Default mode `legacy_persona`: persona LLM self-reports `outcome` and per-criterion `satisfied/unsatisfied` against free-text criteria; `report_validation.py` docstring: "Execution consistency is not independent verification of product behavior." Legacy findings classify as `not_verified`, except the narrow visual-crop path | `services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/report_validation.py`; `services/evaluation-worker/.../report_generator.py`, `deterministic_evaluator.py` |
| E2 | Deep mode verified finding requires `grounded_failure()`: assertion `origin != "inferred"` AND `(oracle, target, expected_value)` exactly equals a caller-supplied `Requirement.assertions` definition. `Requirement.assertions` defaults to `()` and knowledge-derived requirements supply none; the planner prompt instructs "Use origin inferred unless a caller-owned requirement assertion supplies the exact oracle…" | `services/evaluation-worker/src/markettwin_evaluation_worker/deep_evaluator.py:106` (`grounded_failure`), `:28` (`valid_case_evidence`); `packages/shared-python/src/markettwin_shared/feature_plan.py:144` (`Requirement`); `services/execution-orchestrator/.../workflow/deep_run.py` (`knowledge_requirements()`) |
| E3 | Live planning experiment: 12 authorized provider calls → 71 candidates, **60 failed schema validation, 9 of remaining 11 failed policy validation; accepted plans 0/4 (no knowledge), 2/4 (minimal), 0/4 (rich); seeded defects evidenced: 0.** Hand-authored Playwright baseline on the same fixture: **32/32 executions matched fixture truth.** Audit verdict: "REFOCUS … No AI uplift is proven." | `docs/PRODUCT_AUDIT_2026-10-16.md` |
| E4 | Controlled benchmark (4 seeded defects: disabled primary button, missing validation, incorrect navigation, missing confirmation): best repeats confirm only the disabled button (± missing validation); navigation and confirmation defects stay unverified. "This does not pass the detection gate." / "Overall detection is still insufficient." | `docs/V1_BENCHMARK_RESULTS.md` |
| E5 | Real-target run (Klaviyo, 9 journeys): **5 timed out, 3 inconclusive, 1 policy blocked, 0 verified issues**; "model assessment unavailable" | PR #5 description; `MARKETTWIN_COMPLETE_UI_UX_REDESIGN_ALL_PAGES_IMPLEMENTATION_PLAN_2026-10-18.md` §1093/§1269 |
| E6 | Real journeys average ~4–6 recorded browser steps total (e.g. 22 steps / 6 journeys; 77 steps / 12 journeys), i.e. agents mostly navigate and observe, then stop | `docs/agent-quality/BASELINE_2026-10.md`; `docs/CURRENT_STATE.md` |
| E7 | Repo release gates (precision ≥ 95%, seeded-defect recall ≥ 80%, known-case coverage ≥ 85%, zero severe false claims) have never been measured as passed; "Detection recall and false confirmations remain unresolved until measured release criteria pass." | `MKT.md`; `docs/V1_PRODUCT_CONTRACT.md`; `docs/V1_BASELINE.md` |

### 2.3 Amplifier bugs (real, but secondary — fix them in the phases that say so)

| # | Bug | Exact location / value |
|---|-----|------------------------|
| A1 | Journey wall-clock budget is **90 s** for a full LLM + browser loop, overriding the 180 s defaults. On timeout, the persona's final response is parsed only *after* the loop, so a timeout discards ALL partial work and returns the literal summary "Persona Journey exceeded the configured execution time." | `workflow/run_request.py:20` (`max_duration_seconds_per_journey: int = 90`); `workflow/journey_executor.py` (`asyncio.timeout(...)`, `except TimeoutError` branch) |
| A2 | Persona output token cap **2,048** with `/no_think` prefix; a long mission can truncate the final JSON → `ValidationError` → whole journey `failed` ("Persona Agent returned an invalid structured result.") | `agents/persona_agents.py:17` (`PERSONA_AGENT_MAX_TOKENS = 2_048`); `workflow/journey_executor.py` |
| A3 | No LLM-call cap and no retry for Meta/planner/persona calls (only the deep planner sets `RunConfig(max_llm_calls=2)`). One stuck model call consumes the whole journey budget | `workflow/planning.py`; `workflow/journey_executor.py` (bare `InMemoryRunner`, no `run_config`) vs `workflow/test_case_planner.py` |
| A4 | Observation is viewport-only, capped at **80 visible elements**, ARIA snapshot truncated to **2,000 chars** for the model. Controls off-screen are invisible except by scrolling — this manufactures scroll-loops | `browser/observations.py:21` (`MAX_VISIBLE_ELEMENTS = 80`); `browser/contracts.py:8` (`MAX_MODEL_ARIA_SNAPSHOT_CHARS = 2_000`) |
| A5 | Accessible-name mismatch: the observation computes an element's name in injected JS (aria-label → aria-labelledby → label → alt/placeholder/innerText, ≤160 chars), but actions click via Playwright `get_by_role(..., exact=True)`. The name the model copies can differ from the name Playwright matches. Links are re-grounded by regex-parsing `aria_snapshot()` under a shared 2 s deadline and silently dropped on timeout | `browser/observations.py` (`build_observation`, `_ground_link_names`); `browser/actions.py` (`semantic_locator`, `require_unique`) |
| A6 | Locators have **no fallback**: `semantic_locator()` requires exactly one strategy, all `exact=True`; 0 or >1 matches = failure. No fuzzy/positional/second-strategy fallback exists anywhere | `browser/actions.py:35` (`semantic_locator`), `:25` (`require_unique`) |
| A7 | Tool imbalance + no action discipline: `create_browser_tools()` exposes 15 tools, ~9 observe-type (`get_state`, `scroll`, `capture_element`, `take_screenshot`, `get_form_state`, `focus_next`, `set_viewport`, `wait`, `go_back`) vs 6 act-type (`navigate`, `click`, `fill`, `select`, `check`, `uncheck`). There is NO action budget, NO progress/stuck detection, NO "must act" rule. Acting is also the risky path (policy preflight, sensitive-click approvals, forbidden action classes in the prompt) while observing can never fail policy — so a cautious model rationally drifts to scroll/observe | `browser/tools.py:29` (`create_browser_tools`); `agents/persona_agents.py` (instruction) |
| A8 | Mission schema cannot be specific: `objective` ≤ 500 chars, `success_criteria` 1–8 free-text strings; the only validator checks non-blank + distinct after case-folding. No steps, preconditions, test inputs, or expected values exist in the schema. Real test examples: objective "Verify that the page is accessible." / criterion "Page is accessible." / "Information found" | `agents/schemas/mission.py`; `agents/meta_agent.py`; tests `test_persona_agent.py`, `test_adk_workflow.py`, `test_meta_blueprint.py` |
| A9 | Inconclusive flip rule: ANY single validation issue (criterion not reported exactly once, cited step not completed, cited step missing a screenshot/accessibility artifact, agent paraphrasing a criterion) forces the whole journey outcome to `inconclusive`. Inconclusive is the dominant outcome in nearly every recorded live/benchmark run (10/12, 8/12, 8/12, 7/12 journeys) | `workflow/report_validation.py` |
| A10 | One policy-blocked step voids the entire journey outcome. Real example MT-000048: 4/6 journeys blocked because the target's frozen origins allowed `supermemory.ai` but agents needed `console.supermemory.ai` | `workflow/report_validation.py`; `docs/CURRENT_STATE.md`; `docs/ui/VERIFICATION.md` |
| A11 | Assertions are fragile under real-app timing: default assertion read window **1,500 ms** (hard max 5,000 ms); a double-read stability helper (`repeat_read_only_assertion`) exists but is never called in production code | `browser/assertions.py`; `browser/controller.py:682` (`read_assertion`) |
| A12 | Silent infrastructure stalls — a run needs Postgres + outbox relay + Kafka + a SINGLE serial execution worker + LLM provider + S3 + evaluation worker all alive, and at least 4 failure points present to the user as "nothing is happening, no error": (a) `outbox_relay_enabled` defaults to `False`; (b) execution worker down (incident MT-000024: run sat queued, no reason shown); (c) Kafka connect/SSL failures (run stays queued; health can still look connected); (d) evaluation worker down (run completes, report never appears, results API returns 409 "pending" forever). Also: worker crash/restart mid-run → run is marked `failed`/"interrupted" and NEVER resumed (offset commits only after terminal state; redelivery of an accepted event is deliberately not replayed) | `services/control-api/src/markettwin_control_api/config.py:49`; `workflow/run_request_handler.py`; `worker.py` (`process_command`, `abandon_run_handoffs`); `services/evaluation-worker/.../worker.py`; `docs/CURRENT_STATE.md` (MT-000024, MT-000046, MT-000034) |
| A13 | Serial execution + HITL blocking: the execution worker is a single consumer; a human-assistance wait (up to `MAX_HUMAN_LOGIN_WAIT_SECONDS = 600`) blocks ALL other runs. `EXECUTION_MAX_POLL_INTERVAL_MS = 86_400_000` (24 h) exists to tolerate this | `worker.py` (`run_worker`); `workflow/case_execution.py`; `workflow/journey_executor.py` |
| A14 | Fresh-machine setup is broken in 3 places (verified by actually installing this branch): (1) Root README's install instructions say `pnpm` (with a wrong package name `markettwin-web`), but there is no `pnpm-workspace.yaml`/pnpm lockfile — root `package.json` declares **npm** workspaces and the web package is `@markettwin/web`. Following the README literally cannot work. (2) Plain `npm install` crashes in npm's Arborist peer-dependency resolution; there is no lockfile (`.npmrc` sets `package-lock=false`); the working flag `--legacy-peer-deps` is documented nowhere. (3) `uv sync` succeeds but ~91 orchestrator tests then fail because Playwright Chromium binaries are not installed; the step `uv run playwright install chromium` is documented only in `services/execution-orchestrator/README.md` / `docs/BROWSER_ARCHITECTURE.md`, not in the root README or PR validation checklists | `README.md`; `package.json`; `.npmrc`; `services/execution-orchestrator/README.md` |
| A15 | Workflow core is built on ADK's deprecated `SequentialAgent` (deprecation warnings across the test suite). Not to be migrated in this task — noted so the implementing agent does not "fix" it opportunistically | `workflow/adk_workflow.py` |

### 2.4 What is NOT the problem (do not "fix" these)

- The browser controller, step/artifact recording, and evidence model are sound and well tested. Verified on this branch by a fresh install: **execution-orchestrator 465 passed / 3 skipped (DB opt-ins) / 0 failed** (after installing Chromium), **frontend typecheck clean, Vitest 138/138 passed**. The failure is in live-agent workflow design, not in unit-tested plumbing.
- Safety/policy enforcement (origin allowlists, sensitive-input guards, approval for sensitive clicks) is a feature. The fix must work *with* it, not weaken it (§4.9 guardrails).

---

## 3. Non-goals and frozen scope (hard)

The implementing agent MUST NOT, in this task:

1. Add any new product feature: no new ingestion formats, no new knowledge-worker capability, no new HITL capability, no observability/LangSmith work, no AWS/deployment work, no UI redesign beyond §6 (the contract-approval screen and the report restructure described there, nothing else).
2. Delete the `legacy_persona` or `deep_feature_v1` execution modes, their tables, or their history. The new mode is added beside them (§4.1). Deprecation happens only in Phase 7, and only by changing a default — never by deleting code or data.
3. Change the number of personas (still exactly 3 in the persona configuration) or the testing-depth mission/case caps (`workflow/testing_depth.py`), except where §5 explicitly redefines how those caps apply to the new mode.
4. Weaken any browser/network/sensitive-input policy, origin allowlist, or approval rule. Locator fallbacks (§5.4) must never click an ambiguous target by guessing.
5. Migrate off Kafka, Postgres, Kafka-based dispatch, or ADK in this task. (A database-poll dispatch *option* appears in Phase 5 as an additive flag; removing Kafka is a separate, later decision.)
6. Perform broad refactors, renames, or formatting sweeps outside the files a phase explicitly touches.
7. Claim detection quality from unit tests or scripted/fake ADK drivers. Detection quality may only be claimed from the live fixture benchmark in §8.

---

## 4. Target design: new execution mode `discovery_contract_v1`

### 4.1 Principle

Split the single confused loop into three stages with different rules:

```
CURRENT (legacy_persona):
  Plan (blind) ──► Explore + Perform + Judge (one agent, one loop, 90 s)
               ──► Validate the agent's story ──► mostly "inconclusive"

NEW (discovery_contract_v1):
  STAGE 1  DISCOVER   Agent(s) explore the live app. Output = a factual MAP:
                      features found + journeys actually completed, recorded
                      as concrete steps. NO verdict, NO pass/fail, NO findings.
        │
        ▼
  STAGE 2  FREEZE     System generates a TEST CONTRACT from the map:
                      journeys → steps; observed outcomes → plain-language
                      assertions ("checks"). The app OWNER approves / edits /
                      removes checks in one simple UI screen. Approved checks
                      become caller-owned oracles (origin = user_approved).
        │
        ▼
  STAGE 3  RUN        (a) FUNCTION: deterministic re-execution of each frozen
                          journey (reuse deep engine). Code decides pass/fail
                          per check. A check that fails is REPLAYED once in a
                          clean browser; only a repeat failure is a CONFIRMED
                          defect.
                      (b) FEELING: personas re-run / review the same frozen
                          journeys and score EXPERIENCE only (rubric, §5.6).
                          Their scores never create or remove a defect.
        │
        ▼
  REPORT   Works │ Broken (confirmed only) │ How it felt (per persona) │
           Market-worthy verdict │ Coverage (tested X of Y discovered)
```

Register the new mode exactly where the existing modes are registered:
`workflow/run_executor.py` — `execution_mode: Literal["legacy_persona", "deep_feature_v1"]` becomes `Literal["legacy_persona", "deep_feature_v1", "discovery_contract_v1"]`, with a dispatch branch analogous to the existing `deep_feature_v1` branch. The mode is stored in `TestRun.configuration_snapshot` the same way deep mode is detected there by the evaluation worker.

### 4.2 Stage 1 — Discovery

**New module:** `services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/discovery.py`
**New agent factory:** add `create_discovery_agent(...)` in `agents/persona_agents.py` (or a sibling `agents/discovery_agent.py` if the file's structure makes that cleaner — keep the model/runtime construction pattern of `create_persona_agent`).

Behaviour requirements:

1. The discovery agent runs against the authorized target start URL in a fresh `BrowserController` session, using the existing browser tools (`browser/tools.py:create_browser_tools()`), under the existing target/network policy. No new browser authority.
2. Its instruction MUST state, in substance:
   - "Your job is to MAP this application, not to judge it. Do not decide pass/fail. Do not report defects."
   - "Find the main features and complete real user journeys end-to-end where the app allows it (e.g. sign-up form up to the safe pre-submit stage, search, navigation to a detail page, settings review — within existing safety policy)."
   - "Record every journey as the exact sequence of actions you actually performed, with the control you used and what the app showed afterwards."
   - "If you cannot complete a journey, record exactly where and why you stopped (blocked_reason), using the reason vocabulary in §4.2.4."
3. **Act-or-block discipline (fixes A7):** the agent loop MUST be wrapped by a progress tracker (new class `DiscoveryProgressTracker` in `workflow/discovery.py` or `browser/tools.py` wrapper):
   - Count consecutive observe-type tool calls (`browser_get_state`, `browser_scroll`, `browser_capture_element`, `browser_take_screenshot`, `browser_get_form_state`, `browser_focus_next`, `browser_set_viewport`, `browser_wait`) with no intervening act-type call (`browser_navigate`, `browser_click`, `browser_fill`, `browser_select`, `browser_check`, `browser_uncheck`; `browser_go_back` counts as act for this purpose).
   - After **3 consecutive observe calls**, inject a system-style reminder into the next model turn: "You have observed 3 times without acting. Either perform a concrete action toward a journey now, or end this journey attempt with a blocked_reason."
   - After **5 consecutive observe calls**, terminate the current journey attempt and record it with `blocked_reason = "observation_loop"`.
   - Detect scroll-loops specifically: ≥4 `browser_scroll` calls on the same URL with no act call between them counts toward the same termination.
   - The same tracker MUST also detect a repeated identical failed locator (same role+name+strategy failing twice) and terminate that journey attempt with `blocked_reason = "target_not_found"` after the second identical failure (the current prompt already tells the model not to repeat a failing locator unchanged; this makes it mechanical).
4. **Blocked-reason vocabulary** (closed enum, use exactly these): `authentication_required`, `policy_blocked`, `target_not_found`, `ambiguous_target`, `observation_loop`, `time_budget`, `step_budget`, `provider_error`, `unknown`.
5. **Budgets for discovery (fixes A1 for this stage):** per discovery session: `max_steps = 60` tool calls, `max_duration_seconds = 420` wall clock, `max_llm_calls = 60` enforced via ADK `RunConfig(max_llm_calls=...)` (the runner in this stage MUST pass a `RunConfig`, unlike the legacy persona runner). On budget exhaustion, discovery ends *gracefully with whatever map exists* — a partial map is a valid output, never an exception that fails the run.
6. **Output schema** — new file `packages/shared-python/src/markettwin_shared/discovery_contract.py`, following the conventions of `feature_plan.py` (frozen Pydantic contracts). Minimum content:

```python
class DiscoveredStep(FrozenContract):
    ordinal: int
    action: Literal["navigate", "click", "fill", "select", "check", "uncheck", "go_back"]
    target_role: str | None        # e.g. "button", "link", "textbox"
    target_name: str | None        # the accessible name actually used
    input_key: str | None          # key into safe test data, never a raw secret value
    resulting_url_path: str | None # path only, no query/fragment
    resulting_page_title: str | None
    observed_text_markers: tuple[str, ...]  # short visible texts observed after the step
    execution_step_id: UUID        # the recorded ExecutionStep that proves this happened

class DiscoveredJourney(FrozenContract):
    journey_key: str               # stable slug generated deterministically from steps
    title: str                     # plain language, e.g. "Sign up with email"
    feature_key: str               # grouped feature, e.g. "registration"
    completed: bool
    blocked_reason: BlockedReason | None
    steps: tuple[DiscoveredStep, ...]

class DiscoveredFeature(FrozenContract):
    feature_key: str
    title: str
    entry_url_path: str
    journey_keys: tuple[str, ...]

class DiscoveryMap(FrozenContract):
    target_origin: str
    features: tuple[DiscoveredFeature, ...]
    journeys: tuple[DiscoveredJourney, ...]
    coverage_notes: tuple[str, ...]  # e.g. "Checkout requires login; not explored"
```

   Every `DiscoveredStep` MUST reference a real, persisted `ExecutionStep` from the discovery execution (reuse `persistence/step_recorder.py` / `ExecutionStepRecorder` exactly as the legacy tools do). A step that cannot be tied to a recorded execution step MUST be dropped by validation, not trusted.
7. **Persistence:** persist the `DiscoveryMap` as a versioned run artifact: store the JSON in the run's `configuration_snapshot` under key `discovery_map` AND emit a `RunEvent` of type `discovery.completed` with counts (features, journeys completed, journeys blocked by reason). Reuse `persistence/run_event_repository.py`. Do NOT create a new database table for the map in this task unless the snapshot approach demonstrably cannot hold it (if so, flag it in the PR per §0.4 instead of inventing a migration silently).
8. Discovery runs ONCE per test run in this version (shared map for all personas). Per-persona discovery is out of scope.

### 4.3 Stage 2 — Contract generation and owner approval

**New module:** `services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/contract_generation.py`
**Contract schema:** add to `packages/shared-python/src/markettwin_shared/discovery_contract.py`:

```python
class ContractAssertion(FrozenContract):
    assertion_id: str
    oracle: Literal["visible_text", "visible", "enabled", "url_path_v1", "title", "count", "checked"]
    target_role: str | None
    target_name: str | None
    expected_value: str | None
    plain_language: str        # "After clicking Continue, a heading 'Welcome' appears."
    origin: Literal["user_approved"]   # set ONLY by the approval action, see below
    source_step_ordinal: int

class FrozenJourneyContract(FrozenContract):
    journey_key: str
    title: str
    feature_key: str
    steps: tuple[TestCaseStep, ...]        # reuse the deep engine's step type
    assertions: tuple[ContractAssertion, ...]
    safe_test_data_keys: tuple[str, ...]

class TestContract(FrozenContract):
    contract_id: UUID
    test_run_id: UUID
    version: int
    status: Literal["draft", "approved", "frozen", "superseded"]
    journeys: tuple[FrozenJourneyContract, ...]
    approved_by_user_id: UUID | None
    approved_at: datetime | None
```

Generation rules (deterministic first, LLM last):

1. **Steps** are generated ONLY by translating `DiscoveredJourney.steps` 1:1 into the deep engine's existing step representation used by `workflow/case_execution.py:execute_test_case()` (inspect `packages/shared-python/src/markettwin_shared/deep_testing.py` / `feature_plan.py:TestCaseSpec` and reuse those types; do not create a parallel step system). Input values MUST come from the existing safe-test-data mechanism used by deep mode (`workflow/deep_run.py:default_scope()` / fixture safe data) referenced by key, never raw values copied from discovery observations.
2. **Assertions** are generated ONLY from what discovery actually observed after a step:
   - Final step of a completed journey → `url_path_v1` assertion on `resulting_url_path` (if present) and/or `visible_text`/`title` assertion on an observed text marker / page title.
   - A step whose observation shows a validation message, confirmation text, or a newly appearing element → `visible_text` assertion on that marker.
   - A control that discovery successfully used → at most an `enabled`/`visible` assertion at its point of use. Do NOT generate assertions about behaviour discovery did not observe (no negative assertions, no invented expected values).
   - Each generated assertion gets a `plain_language` sentence built from a template: `"After <step description>, <expected observation>."` The owner approves sentences, not JSON.
3. An LLM MAY be used to improve `plain_language` wording and journey/feature titles only. It MUST NOT create, delete, or alter steps, oracles, targets, or expected values. If the LLM call fails, fall back to the template wording — contract generation must still succeed.
4. **Approval is the oracle-creation event.** Draft assertions have NO origin and NO evidential power. The approval action (§6.1 API) sets `origin = "user_approved"`, records `approved_by_user_id` / `approved_at`, and moves the contract `draft → approved → frozen` (frozen at Stage 3 start; a frozen contract is immutable — edits create a new version with status `superseded` on the old one, following the existing immutable-snapshot pattern used for agent runtime snapshots).
5. **Evaluation change (the core fix for E2):** in `services/evaluation-worker/src/markettwin_evaluation_worker/deep_evaluator.py`, extend `grounded_failure()` so that an assertion with `origin == "user_approved"` whose `(oracle, target, expected_value)` matches an assertion in the *frozen TestContract for that run* counts as grounded — i.e. add `user_approved` alongside the existing `fixture_truth → fixture` and `approved_knowledge` sources. The frozen contract plays the role the caller-supplied `FeatureScope`/`Requirement.assertions` plays today. `valid_case_evidence()` MUST also verify the frozen contract's hash/version matches the plan that was executed (the executed plan must record `contract_id` + `version`).
   - Assertions with origin `inferred` (LLM-planned, unapproved) remain ungrounded. Do not relax this.
   - Add unit tests proving: (a) user-approved assertion failing on replay → verified finding; (b) identical assertion without approval → NOT verified; (c) contract edited after freeze (version mismatch) → NOT verified.
6. If the owner approves ZERO journeys/assertions, Stage 3 does not run and the test run ends with status `completed` and an explicit report state "No approved tests — nothing was verified." It MUST NOT silently fall back to legacy persona judging.

### 4.4 Stage 3a — Functional execution (deterministic, with replay confirmation)

1. Convert each `FrozenJourneyContract` into the deep engine's case representation and execute with the EXISTING `workflow/case_execution.py:execute_test_case()` and `browser/assertions.py:evaluate_assertion()` via `BrowserController.read_assertion()`. Do not write a second executor.
2. **Per-case budgets (fixes A1/A11 for this stage):** per case `max_duration_seconds = 240` wall clock; per-action Playwright timeout stays 30 s; assertion read window: call the existing double-read path — wire `browser/assertions.py:repeat_read_only_assertion()` (currently unused) into `read_assertion` for the oracles `visible_text`, `visible`, `enabled`, `url_path_v1`, `title`, with an effective stability window of up to 5 s (two reads ≥500 ms apart must agree). A single 1.5 s read MUST NOT be the sole basis for a `not_satisfied` verdict on those oracles.
3. **Checkpointing (fixes total-loss on timeout):** `execute_test_case` already records steps as it goes; ensure the case result is persisted after EVERY step (verify current behaviour; if the case result object is only persisted at the end, add incremental persistence of assertion results as `test_case.assertion` run events per assertion, which the evaluator can reconstruct from). On timeout, the case ends with status `timed_out` and verdict `unverified`, and the report MUST show "completed N of M steps, stopped at step K" from the persisted records. A timeout MUST NOT discard completed assertion results.
4. **Replay confirmation (new):** when a case finishes with any `not_satisfied` assertion, schedule exactly ONE confirmation replay of that case in a fresh browser session, immediately, before evaluation. Persist both executions, linked by `replay_of_execution_id` (use the existing execution/attempt structures; if a link field does not exist, record the pairing in a `test_case.replay` run event — do not add a migration without flagging per §0.4).
   - In the evaluator (deep evaluator path for this mode): a `not_satisfied` assertion becomes a **verified (`verified_deterministic`) finding ONLY IF** it is grounded (§4.3.5) AND the same assertion was `not_satisfied` in both the original and the replay execution, on the same frozen contract version.
   - If the replay passes, the finding is recorded as an unverified observation with reason `did_not_reproduce` (possible flake / timing), never as a confirmed defect, and never silently dropped.
   - If the replay cannot run (policy, provider, infra), the finding stays unverified with reason `replay_unavailable`.
5. Persona variation in this stage: the SAME frozen journeys are executed for each of the 3 personas, where a "persona" in this mode means an *input-and-behaviour variant only*: different safe test-data values (e.g. name/email variants by key), different viewport (one mobile-width persona), and different patience parameters (assertion stability window already fixed; do NOT vary oracles by persona). The functional verdict is per-journey across personas: a check is `passed` only if it passed for all personas that completed it; persona-specific failures are reported as such (they are real signal, e.g. mobile-only breakage).

### 4.5 Stage 3b — Feeling and market-worthiness (personas judge experience ONLY)

**New module:** `services/evaluation-worker/src/markettwin_evaluation_worker/experience_evaluator.py`, called from `workflow.py:evaluate_and_generate_report()` for runs whose `configuration_snapshot` mode is `discovery_contract_v1`, in addition to the deep evaluator.

1. Input: the persisted execution records for the run (steps, durations, retries, blocked steps, assertion outcomes, screenshots) — NOT a fresh browser session, NOT the persona's free narrative.
2. For each persona that executed, compute DETERMINISTIC experience facts in code first:
   - `journeys_completed / journeys_attempted`
   - `total_steps`, `failed_actions`, `blocked_steps`, `timeouts`
   - `stuck_points`: steps where the same action failed, or ≥3 observe calls preceded an act (from step records)
   - per-journey elapsed time
3. An LLM call (reuse the pattern of `run_assessment.py:assess_completed_run()`, including its 65 s timeout and fail-soft `status="unavailable"` behaviour) then scores each persona's experience on this fixed rubric, 1–5 each, with a mandatory one-sentence justification CITING a fact from step 2 (the call receives the facts; a score whose justification cites no supplied fact MUST be rejected by validation and the whole assessment marked `unavailable` rather than trusted):
   - `ease` — could this user complete their goals without struggle?
   - `clarity` — did labels, headings, and next steps make sense?
   - `trust` — did the app feel reliable and safe to use?
   - `visual_quality` — did it look finished and coherent, or like low-quality "AI slop" (generic, messy, inconsistent)? The vision input for this dimension is the run's existing screenshots (reuse `visual_batch_evaluator.py` plumbing); if no screenshots exist, this dimension MUST be `unavailable`, not guessed.
4. Experience scores MUST NOT create, confirm, upgrade, downgrade, or delete any functional finding. Enforce this structurally: `experience_evaluator.py` writes only to a new `experience` section of the Report payload; it has no import of, and no write path to, the findings persistence used by the deterministic/deep evaluators.
5. **Market-worthy verdict (deterministic rule, computed in code in `report_generator.py` or a sibling `market_verdict.py`):**
   - Inputs: coverage = frozen journeys executed / journeys in the frozen contract; confirmed defects by severity; per-persona rubric means.
   - Output exactly one of: `ready`, `ready_with_issues`, `not_ready`, `insufficient_evidence`.
   - Rules (apply in order):
     1. If coverage < 0.6 OR fewer than 2 personas completed any journey → `insufficient_evidence`.
     2. Else if any confirmed defect of severity high/critical exists → `not_ready`.
     3. Else if any confirmed defect exists OR any persona rubric mean < 3.0 → `ready_with_issues`.
     4. Else → `ready`.
   - The verdict MUST be displayed with its inputs (coverage fraction, confirmed defect count, persona means). A verdict without visible coverage is a defect in the report (see §6.3).

---

## 5. Cross-cutting fixes (apply inside the new mode; legacy mode unchanged except §5.3)

### 5.1 Grounding fix — one source of truth for accessible names (fixes A5)

In `browser/observations.py` and `browser/actions.py`:

1. The accessible name used in observations MUST be obtained from Playwright's own accessibility machinery for that element (the same source `get_by_role(name=...)` matches against) — e.g. derive it from the element's `aria_snapshot()` fragment or Playwright's accessible-name computation — instead of the current hand-rolled JS precedence chain (aria-label → aria-labelledby → label → alt/placeholder/innerText). Where an exact Playwright accName cannot be obtained for an element, mark that element `name_source = "approximate"` in the observation, and the discovery/contract layers MUST NOT build a click step on an approximate name without a secondary locator (label or text) recorded alongside it.
2. Remove the silent-drop behaviour in `_ground_link_names()`: a link whose name cannot be grounded within its time budget MUST appear in the observation with `name_source = "unavailable"` instead of being omitted. (Silent omission makes the model believe the link does not exist.)
3. Add a regression test using the existing link-grounding test file (`tests/test_link_name_grounding.py` in the orchestrator suite): a page where the JS-chain name and the Playwright accName differ (e.g. name assembled via `aria-labelledby` across elements, or containing an arrow glyph) must produce an observation name that `semantic_locator` can click successfully on the first attempt.

### 5.2 Locator fallback chain (fixes A6 — within safety guardrails §3.4)

In `browser/actions.py:semantic_locator()` usage (practically: in the action implementations in `browser/controller.py` that resolve targets):

1. Resolution order for a recorded target: (1) role + exact accessible name; (2) label (exact); (3) visible text (exact); (4) role + accessible name with whitespace/case normalisation (non-exact match, still requiring uniqueness).
2. At EVERY strategy, `require_unique()` semantics stay: 0 matches → next strategy; >1 matches → FAIL with `ambiguous_target`, never pick one.
3. Record which strategy succeeded in the execution step payload (`locator_strategy` field in the step's recorded result). Contract generation (§4.3) stores the successful strategy with the step so replay uses the same strategy first.
4. Tests: extend the existing browser action tests with (a) duplicate-name controls with different labels resolving via strategy 2; (b) two identical controls failing as `ambiguous_target` at every strategy (no click performed — assert no navigation/state change occurred).

### 5.3 Partial-result salvage for the LEGACY mode (small, isolated, do this in Phase 1)

In `workflow/journey_executor.py`, `except TimeoutError` and `except ValidationError` branches:

1. Before returning the failed/timed-out result, attempt to build a partial result from the execution steps ALREADY persisted for that execution (they exist — steps are recorded per action): include `steps_completed` count, the last completed step, and any deterministic `AssertionResult`s present in those steps.
2. The journey result gains `partial: true` and the summary becomes "Timed out after N completed steps (last: <action> on <target>)" instead of the bare literal. The outcome remains `timed_out`/`failed` — this change is about not lying by omission in the UI, not about upgrading outcomes.
3. Do NOT attempt to parse a partial LLM final response. Only persisted step data may be used.

### 5.4 Richer observation for discovery only (fixes A4, scoped)

1. Add `browser_get_page_index()` tool (discovery agent only, not added to the legacy persona toolset): returns the FULL page's interactive elements (role + accessible name + a stable ordinal), paginated in chunks of 80 with a cursor, sourced from the accessibility tree rather than the viewport. The existing `browser_get_state()` (viewport, 80 elements) remains for step-by-step work.
2. Discovery MUST call `browser_get_page_index()` at least once per new page before deciding a feature is absent. A "feature not found" conclusion based only on viewport observations is invalid; contract generation must treat such journeys as `completed = false, blocked_reason = "target_not_found"` with a coverage note.
3. Raise `MAX_MODEL_ARIA_SNAPSHOT_CHARS` usage for the discovery agent only if the page-index tool proves insufficient in the Phase 2 fixture test — do not change the global constant pre-emptively.

### 5.5 LLM call discipline (fixes A3, new mode)

1. Every ADK `Runner`/`InMemoryRunner` created by the new mode's stages MUST receive a `RunConfig` with an explicit `max_llm_calls` (discovery: §4.2.5; contract wording LLM: 1 call, non-ADK LiteLLM call is acceptable following `run_assessment.py`'s pattern; experience evaluator: 1 call per persona).
2. Planner/persona JSON parse failures in the new mode: exactly ONE retry with the validation error appended to the prompt ("Your previous output failed validation: <first error>. Return corrected JSON only."). A second failure ends that stage gracefully (discovery: keep partial map; experience: `unavailable`). No unbounded retry loops anywhere.

### 5.6 Safety and policy guardrails (unchanged, restated because the fix touches these areas)

- Discovery and replay run under the same target authorisation, origin allowlist, and sensitive-input rules as existing modes. The approval UI (§6) MUST display the target origin(s) the contract will run against.
- Approving a contract never widens origins, never approves a sensitive click class, and never supplies credentials. Authenticated journeys remain subject to the existing HITL design and are OUT of the new mode's v1 scope: if discovery hits `authentication_required`, that journey is recorded as blocked with a coverage note, and contract generation skips it (see §10 default).
- Safe test data comes only from the existing safe-test-data mechanism. Discovery observations must never be mined for values to type into forms.

---

## 6. API and UI changes (the only UI work in this task)

### 6.1 Control API — new endpoints

New file: `services/control-api/src/markettwin_control_api/api/test_contracts.py`, registered like the other `api/*` routers, with the same auth/permission dependencies as `api/test_run.py` / `api/deep_cases.py` (inspect those and mirror them). Endpoints (all workspace- and run-scoped, all checking the same run ownership as existing run endpoints):

| Method & path | Behaviour |
|---|---|
| `GET /api/v1/workspaces/{workspace_id}/test-runs/{run_id}/contract` | Returns the current `TestContract` for the run (draft after discovery+ generation), including per-journey plain-language assertions. 404 with a clear code if discovery has not completed. |
| `PUT .../contract/journeys/{journey_key}` | Owner edits one journey: remove assertions, edit an assertion's `plain_language` AND its structured fields together (they must stay consistent — if structured fields change, the assertion is regenerated to template wording first and the owner edits from there), or exclude the journey (`excluded: true`). Only allowed while status = `draft`. Each edit bumps contract `version` and keeps status `draft`. |
| `POST .../contract/approve` | Body: `{}` (approve current draft as-is). Sets `origin = "user_approved"` on all non-excluded assertions, records approver + timestamp, status → `approved`. This is the ONLY code path that may set `origin = "user_approved"`. |
| `POST .../contract/start` | Freezes the approved contract (`status → frozen`), writes the frozen contract (id + version + content hash) into the run's configuration snapshot, and triggers Stage 3 execution through the EXISTING run-dispatch mechanism (the same one `POST .../start` for a test run uses — inspect `api/test_run.py` and the run dispatch service; do not build a second dispatch path). |

The test-run lifecycle gains explicit states surfaced to the API/UI for this mode: `discovering → awaiting_approval → executing → evaluating → completed` (map these onto existing status fields where an equivalent exists; if a new status value is required in the lifecycle model, add it following the existing lifecycle transition patterns in `persistence/run_state_repository.py` equivalents in control-api, with tests for legal/illegal transitions).

### 6.2 UI — three screens, user's words only

In `apps/web` (pages live under `src/pages/runs/`; follow existing routing/layout patterns in `src/app/router.tsx` and existing page components such as `NewRunPage.tsx` / `RunReportPage.tsx`):

1. **Screen 1 — "Here's my app"** (extend `NewRunPage.tsx` flow for this mode): URL + "What is this app and who is it for?" (one textarea) + mode selector defaulting to the new mode once Phase 7 flips the default. Button: "Send agents to explore". NO internal terminology on this screen (see terminology table §6.4).
2. **Screen 2 — "Approve the tests"** (new page `ContractApprovalPage.tsx` + route): shows the discovery summary in plain words ("Agents explored your app and found 6 features. They completed 5 journeys. 1 journey needs a login and was skipped."), then per journey a card: journey title, its steps as a numbered plain list, its checks as plain-language sentences each with a checkbox (default checked) and an Edit affordance, and "Don't test this" per journey. Sticky footer: "Approve and run tests" (calls approve → start). If discovery found 0 completed journeys, this screen says so plainly and offers "Explore again" — it MUST NOT fabricate journeys.
3. **Screen 3 — Results** (restructure `RunReportPage.tsx` output for this mode; other modes' reports unchanged): four sections in this order, with these exact user-facing headings:
   - **"What works"** — journeys whose checks all passed, with per-check evidence links (existing evidence linking).
   - **"What's broken"** — CONFIRMED defects only (replay-reproduced, grounded). Each with: plain-language check that failed, screenshot from the failing step, "failed again on re-check" note. Below the list, a clearly separated sub-section **"Seen once — not confirmed"** for unverified observations with their reason in plain words (`did not happen again on re-check`, `could not be re-checked`, `needs a login`, `ran out of time at step N of M`).
   - **"How it felt"** — per-persona cards: rubric scores (labelled in words: Hard / Okay / Easy etc., not bare numbers alone), the deterministic facts (completed X of Y journeys, stuck at: <step>), and the one-sentence justifications.
   - **"Is it market-ready?"** — the §4.5.5 verdict, ALWAYS with its inputs beside it: "Tested 5 of 6 approved journeys · 1 confirmed problem · Tester scores: Expert 4.2, First-time user 2.8, …". If verdict is `insufficient_evidence`, this section explains what was not tested and why.
   - A persistent coverage line at the top of the report: "Coverage: tested X of Y discovered features."

### 6.3 Report integrity rules (tests required)

- The report API for this mode MUST NOT return a confirmed-defect count that includes any finding lacking (frozen-contract grounding) AND (replay reproduction). Add an API-level test with a hand-built payload attempting both violations.
- "What works" MUST NOT list a journey that was excluded, blocked, or not executed.
- The market verdict MUST NOT be `ready` when coverage < 0.6 (mirrors §4.5.5 rule 1) — unit-test the boundary.

### 6.4 Terminology mapping (UI strings MUST use the left column; internal/API names stay as-is)

| User sees | Internal concept |
|---|---|
| App | Application Target |
| Testers | Persona agents |
| Journey | Journey / case |
| Check | Assertion / oracle |
| Explore | Discovery stage |
| Approve the tests | Contract approval / freeze |
| Broken (confirmed) | Verified deterministic finding |
| Seen once — not confirmed | Unverified observation |
| How it felt | Experience evaluation |
| Market-ready verdict | Market-worthiness assessment |

Do not rename internal models, routes (other than the new page), or API fields to match the left column. This is a presentation-layer mapping only.

---

## 7. Implementation phases

> Conventions for every phase: (a) add/extend tests in the existing test style of the touched service (orchestrator tests under `services/execution-orchestrator/tests/`, evaluation under its `tests/`, web under `apps/web` Vitest); (b) the full validation commands for the repo are:
> `uv sync && uv run pytest -q && uv run ruff check . && uv run pyright` (Python; note the repo's known pre-existing full-project Pyright debt — your gate is: no NEW Pyright errors in files you touched, and focused production Ruff/Pyright clean, matching the repo's existing practice recorded in `docs/CURRENT_STATE.md`)
> and for web: `npm install --legacy-peer-deps && npm run typecheck --workspace @markettwin/web && npm run test --workspace @markettwin/web && npm run build --workspace @markettwin/web`.
> Prerequisite for Python browser tests: `uv run playwright install chromium` (Phase 0 documents this).

### Phase 0 — Baseline and setup fixes (docs only + one config guard)

Files: `README.md`, `services/execution-orchestrator/README.md` (cross-check), root `package.json` (only if a script is wrong — verify first).

1. Fix the root README quickstart: npm (not pnpm), correct workspace package name `@markettwin/web`, the `--legacy-peer-deps` requirement (or, better: investigate whether adding a committed lockfile is the repo's intent — `.npmrc` currently sets `package-lock=false`; if you change that, state why in the PR), the `uv` bootstrap note for externally-managed Python environments, and the `uv run playwright install chromium` step placed BEFORE the test commands.
2. Add a startup guard in control-api: if `APP_ENV` is a local/dev value AND `outbox_relay_enabled` is `False`, log a loud `ERROR`-level line at startup: "Outbox relay is DISABLED — test runs will be created but never executed." (Do not change the default value.)
3. Acceptance: a fresh-clone walkthrough of the corrected README (install → sync → chromium → pytest collection) succeeds; startup log line verified by a unit test or a documented manual run in the PR.

### Phase 1 — Quick wins inside existing modes (grounding, salvage, discipline)

Files: `browser/observations.py`, `browser/actions.py`, `browser/controller.py`, `workflow/journey_executor.py`, relevant tests.

1. §5.1 accessible-name single source of truth + no silent link dropping + regression test.
2. §5.2 locator fallback chain + `locator_strategy` recording + tests.
3. §5.3 legacy partial-result salvage on timeout/validation error.
4. §5.5.2 one-retry-on-invalid-JSON for the legacy persona report parse (same pattern; second failure unchanged behaviour).
5. Acceptance: orchestrator suite green (baseline: 465 passed / 3 DB-opt-in skips); new tests for each item; a targeted fixture run (existing browser fixture tests) shows a previously failing link-name case now clicking first-try.

### Phase 2 — Discovery stage

Files: NEW `packages/shared-python/src/markettwin_shared/discovery_contract.py` (schemas §4.2.6 only for now), NEW `workflow/discovery.py`, `agents/persona_agents.py` (discovery agent factory) or new `agents/discovery_agent.py`, `browser/tools.py` (add `browser_get_page_index` §5.4 — gate it to the discovery toolset), `workflow/run_executor.py` (mode registration + dispatch skeleton that runs discovery and stops at `awaiting_approval`), `workflow/run_request.py` (mode plumbing mirroring deep mode).

1. Implement §4.2 completely: progress tracker with observe-loop/scroll-loop/repeat-locator termination, budgets, graceful partial map, persistence (snapshot + `discovery.completed` event), step-provenance validation (drop unprovenanced steps).
2. Tests: unit tests for the progress tracker (synthetic tool-call sequences); schema validation tests; an integration test against an existing local fixture site (reuse the fixture apps/targets used by `test_deep_testing_fixture.py` / benchmark fixtures) asserting: a completed journey in the map has ≥1 real act step per journey (not navigate-only), every step resolves to a persisted execution step, and a deliberately login-walled fixture page yields `blocked_reason = "authentication_required"` + a coverage note.
3. Acceptance: on the fixture target, discovery produces a map where ≥80% of the fixture's known features are found and at least the fixture's primary journey is `completed = true` with concrete steps. Record the map JSON in the PR.

### Phase 3 — Contract generation + approval API

Files: `discovery_contract.py` (contract schemas §4.3), NEW `workflow/contract_generation.py`, NEW `services/control-api/.../api/test_contracts.py` + router registration, control-api lifecycle additions (§6.1), evaluation-worker `deep_evaluator.py` (grounding extension §4.3.5) + its tests.

1. Implement §4.3 generation rules (deterministic translation; LLM wording-only with template fallback), versioning/immutability, approval as sole origin-setter.
2. API endpoints per §6.1 with ownership checks mirrored from existing run endpoints.
3. Evaluator grounding extension + the three unit tests mandated in §4.3.5.
4. Acceptance: end-to-end (API-level, fixture target): run discovery → GET contract returns plain-language checks → approve → contract frozen with hash recorded → a hand-injected failing assertion scenario (fixture in broken state) yields a verified finding ONLY when approved + frozen; the same scenario unapproved yields none.

### Phase 4 — Deterministic execution, replay confirmation, experience + verdict

Files: `workflow/deep_run.py` (new-mode branch or a sibling `workflow/contract_run.py` — prefer a sibling to avoid destabilising deep mode), `workflow/case_execution.py` (checkpointing §4.4.3, double-read wiring §4.4.2), `browser/controller.py` (`read_assertion` stability), NEW `services/evaluation-worker/.../experience_evaluator.py`, `services/evaluation-worker/.../workflow.py` (mode dispatch), `services/evaluation-worker/.../report_generator.py` / new `market_verdict.py` (§4.5.5), `deep_evaluator.py` (replay rule §4.4.4).

1. Implement §4.4 (execution, budgets, checkpointing, replay-once, persona variants) and §4.5 (experience facts → rubric → report section; structural separation from findings).
2. Tests: replay rule (fail-then-pass → unverified/`did_not_reproduce`; fail-then-fail → verified; replay unavailable → unverified/`replay_unavailable`); timeout checkpointing (kill a case mid-way via a slow fixture; assert persisted partial progress + "N of M steps" data present); experience evaluator (score with uncited justification → assessment `unavailable`; experience module cannot write findings — test by construction/import assertion plus a functional test); market verdict boundary tests (§6.3).
3. Acceptance: the §8 fixture benchmark, run in this mode, passes the §8.2 gates for the first time (if it does not, the phase is NOT complete — iterate within the phase; do not proceed to Phase 5/6 polish while the gate fails).

### Phase 5 — Run reliability visibility (no silent stalls)

Files: `services/control-api/.../config.py` + `main.py` (startup surfacing), execution `worker.py`, evaluation `worker.py`, control-api run read models (`api/test_run.py` / `api/test_run_results.py` — inspect and mirror), web `RunsPage.tsx` / `RunOverviewPage.tsx` (status reason display only).

1. **Worker heartbeats:** execution worker and evaluation worker each upsert a heartbeat row every 10 s into a small new table (this one migration IS authorised: `worker_heartbeats(service TEXT PRIMARY KEY, last_seen_at TIMESTAMPTZ, detail JSONB)`) via Alembic following `database/` conventions. Control API exposes them on the existing health/readiness endpoint.
2. **Pre-flight gate:** `POST` start (both legacy start and §6.1 contract start) checks: outbox relay enabled (or dispatch path healthy), Kafka reachable (if Kafka dispatch is in use), execution worker heartbeat < 30 s old, evaluation worker heartbeat < 30 s old, LLM provider configured (key present — presence only, no provider call). If any check fails, the start request is REJECTED with a plain-language reason ("The test runner is not running. Start the execution worker and try again.") instead of creating a doomed queued run. Add a `GET .../preflight` endpoint returning the same checks for the UI to display BEFORE the user presses start.
3. **Stall watchdog + reason surfacing:** a run in `queued`/`planning`/`running` with no new run event for > 60 s gains a computed `status_reason` in the run read model (e.g. "Waiting for the test runner", "Runner is busy with another test", "Waiting for the report writer") derived from heartbeat + queue state; the runs UI displays `status_reason` whenever present. Do NOT change run states themselves in this phase.
4. **Interrupted-run honesty:** when `process_command` marks a redelivered run `failed`/"interrupted", the run's user-facing failure reason MUST say "This run was interrupted (the runner restarted) and was not resumed. Start a new run." — replacing any bare internal wording in the read model.
5. Acceptance: with the execution worker stopped, the UI/API pre-flight fails with the plain reason and no queued zombie run is created (integration test); with the worker started mid-queue, `status_reason` transitions are observable in tests.

### Phase 6 — UI: three screens and the restructured report

Files: `apps/web/src/pages/runs/NewRunPage.tsx`, NEW `apps/web/src/pages/runs/ContractApprovalPage.tsx` + route in `src/app/router.tsx`, `apps/web/src/pages/runs/RunReportPage.tsx` (+ its tests), terminology per §6.4.

1. Implement §6.2 screens 1–3 and §6.3 integrity rules (frontend must render the API's confirmed/unverified separation exactly; no client-side reclassification).
2. Accessibility/i18n: follow the repo's existing patterns (the codebase has axe-tested pages; new pages must pass the same axe checks in the existing Playwright/Vitest setup).
3. Acceptance: Vitest + typecheck + build green (baseline: 138 tests); new component tests for the approval screen (approve flow calls approve→start in order; zero-journey state renders honestly) and for the report (verdict always rendered with coverage; unverified items never appear under "What's broken").

### Phase 7 — Default switch and legacy demotion (only after §8 gates pass on the new mode)

1. Default `execution_mode` for NEW runs becomes `discovery_contract_v1` (`workflow/run_executor.py` default + NewRunPage default). Legacy and deep modes remain selectable via explicit configuration/API (do not remove).
2. Add a banner/note in the legacy report view: "This report was produced by the older exploratory mode. Its findings are unverified observations." (Presentation only.)
3. Update `docs/CURRENT_STATE.md` and `docs/V1_PRODUCT_CONTRACT.md` to describe the new mode's contract accurately, and record the §8 benchmark results in `docs/V1_BENCHMARK_RESULTS.md` (append, do not rewrite history).

---

## 8. Acceptance benchmark (the compass — mandatory)

### 8.1 Fixture

Use the repository's existing controlled-benchmark fixture (the good/broken app pair used in `docs/V1_BENCHMARK_RESULTS.md` TASK 04 and the deep fixture benchmark scripts, e.g. `services/execution-orchestrator/scripts/run_deep_fixture_benchmark.py` / `run_v1_benchmark.py` — inspect and reuse; if the fixture is not runnable as-is, repairing the fixture harness is in scope and must be flagged in the PR). Seeded defects in the broken variant: (1) disabled primary button, (2) missing form validation, (3) incorrect navigation destination, (4) missing confirmation.

### 8.2 Gates (ALL must hold, on the NEW mode, live model, no scripted drivers)

Run the full loop (discover → approve programmatically via the API as a test owner would, approving all generated checks → execute → evaluate) **3 consecutive times** on the broken fixture and **3 consecutive times** on the good fixture:

| Metric | Gate |
|---|---|
| Seeded-defect recall (broken fixture) | ≥ 3 of 4 defects confirmed (verified) per run, incl. the navigation defect in at least 2 of 3 runs |
| False confirmations (good fixture) | **0** verified defects across all 3 runs |
| Journey completion | ≥ 80% of frozen journeys reach a terminal verdict (passed/failed) rather than timed_out/inconclusive |
| Inconclusive share | ≤ 20% of executed journeys |
| Silent stalls | 0 runs requiring manual worker/queue intervention |
| Report integrity | §6.3 tests pass; every confirmed defect shows screenshot evidence + replay note |

### 8.3 Reporting

Append the 6 runs' raw outcome tables (per-journey status, per-assertion verdicts, replay results) to `docs/V1_BENCHMARK_RESULTS.md`. If a gate fails, the numbers are recorded anyway and the phase is reported as NOT passing. Never tune the fixture, the seeded defects, or the gate thresholds to make a run pass.

---

## 9. Definition of done (whole task)

- [ ] Phases 0–7 merged in order, each with its tests green and results recorded in its PR.
- [ ] §8.2 gates pass and are recorded per §8.3.
- [ ] Full validation commands (§7 preamble) pass with no new failures vs the verified baselines (orchestrator 465 passed / 3 skipped; web 138 passed, typecheck clean).
- [ ] No item from §3 (Non-goals) was violated; `git diff` against baseline touches no deployment, ingestion, knowledge-worker, or observability code except where a phase explicitly names it.
- [ ] `docs/CURRENT_STATE.md` updated (Phase 7.3) so the next session does not need to re-derive any of this.

## 10. Open questions for the owner (do not block; defaults apply)

1. **Authenticated journeys in the new mode v1** — Default (already assumed in §5.6): OUT of scope; discovery records them as blocked with coverage notes. Owner may later prioritise reusing the existing HITL flow.
2. **Should the owner-approval step (§6.2 Screen 2) be skippable for repeat runs of an already-frozen contract on the same app version?** Default: NO for this task — every run's contract is approved explicitly; a "re-run same contract" fast path is a later feature.
3. **Persona set for the new mode** — Default: keep the existing 3-persona configuration; personas differ in Stage 3 only by input variants + viewport + (in Stage 3b) their scored perspective. Changing the persona roster itself is out of scope.
4. **Model choice** — Default: keep the currently configured provider/models. This fix is model-agnostic by design; do not couple it to a model migration.

## Appendix A — Key files index (verified at baseline `c455d8d`)

| Area | Path |
|---|---|
| Mode registration / dispatch | `services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/run_executor.py` |
| Run request construction (90 s override) | `.../workflow/run_request.py` |
| Blind planning (legacy) | `.../workflow/planning.py`, `.../agents/meta_agent.py` |
| Persona agent (legacy instruction, 2,048 tokens) | `.../agents/persona_agents.py` |
| Persona execution (timeout, parse, salvage target) | `.../workflow/journey_executor.py` |
| Story validation (inconclusive flip) | `.../workflow/report_validation.py` |
| Browser tools (15 tools) | `.../browser/tools.py` |
| Observations (80-element cap, name grounding) | `.../browser/observations.py`, `.../browser/contracts.py` |
| Locators (exact-only) | `.../browser/actions.py` |
| Deterministic assertions | `.../browser/assertions.py`, `.../browser/controller.py` (`read_assertion`) |
| Deep case execution | `.../workflow/case_execution.py`, `.../workflow/deep_run.py`, `.../workflow/test_case_planner.py` |
| Deep schemas / oracle types | `packages/shared-python/src/markettwin_shared/feature_plan.py`, `.../deep_testing.py` |
| Deep evaluation (grounding gate to extend) | `services/evaluation-worker/src/markettwin_evaluation_worker/deep_evaluator.py` |
| Report generation / assessment patterns | `services/evaluation-worker/.../report_generator.py`, `.../run_assessment.py`, `.../visual_batch_evaluator.py` |
| Execution worker (serial, interrupted handling) | `services/execution-orchestrator/.../worker.py`, `.../workflow/run_request_handler.py` |
| Evaluation worker (5 s poll, quarantine) | `services/evaluation-worker/.../worker.py`, `.../workflow.py` |
| Control API (routers to mirror) | `services/control-api/src/markettwin_control_api/api/test_run.py`, `.../api/deep_cases.py`, `.../config.py` |
| Web pages | `apps/web/src/pages/runs/NewRunPage.tsx`, `.../RunReportPage.tsx`, `.../RunsPage.tsx`, `src/app/router.tsx` |
| Benchmark fixtures / scripts | `services/execution-orchestrator/scripts/run_deep_fixture_benchmark.py`, `.../run_v1_benchmark.py`; results history in `docs/V1_BENCHMARK_RESULTS.md` |

## Appendix B — One-paragraph summary for the PR description

MarketTwin's agents were asked to discover, perform, and judge app journeys in one 90-second loop, against missions written without seeing the app, with no machine-checkable definition of success — so reports were vague stories that the system's own validator correctly downgraded to "inconclusive", and the deterministic alternative could not confirm findings because no caller-owned oracles ever existed. This change adds a third execution mode, `discovery_contract_v1`, that splits the loop: agents first *discover* a factual map of the app (with mechanical anti-scroll-loop discipline), the system generates a plain-language test contract from what was actually observed, the app *owner approves* it (creating the missing oracles), deterministic replay then decides pass/fail (a defect is confirmed only if it reproduces on a clean re-run), and personas separately score how the experience *felt*, feeding a coverage-honest market-ready verdict. Supporting fixes: single-source accessible names, a safe locator fallback chain, per-stage budgets with checkpointed partial results, one-retry JSON discipline, and pre-flight/heartbeat visibility so no run can ever again stall silently.
