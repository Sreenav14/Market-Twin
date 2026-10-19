# MarketTwin — Repository-Wide Source Audit and Remediation Register

**Assessment date:** 2026-10-18  
**Repository:** `Sreenav14/Market-Twin`  
**Pinned branch:** `feat/batch-1-aws-observability`  
**Pinned commit:** `660487b65984226002d1c6df743d5a1cb745cf45`  
**Action:** Read-only audit. No code modification or commit performed.

## 0. Important statement of scope

This is a **substantial source-code and integration-path audit**, **not a certification of every line of code**, not proof that the test suite passes, and not an inspection of the developer's local uncommitted checkout.

The remote repository tree was obtained through the connected GitHub integration: **699 tracked files** and about **5 MB** of material. Every file path was inventoried. A static, pattern-assisted retrieval sweep covered all source files under the main Control API, execution-orchestrator, Knowledge Worker, evaluation worker, web `src`, shared Python `src`, and database Python `src`; the 21 Alembic version files were also retrieved. Important execution paths were additionally read at code-block/statement level. Numerous backend/frontend tests were inspected by their names, fixtures and key assertions. **Not every branch of every file was manually walked**. Because the GitHub repo was accessible only through the connected source reader, a full local checkout and dependency setup was not available to execute `ruff`, `pyright`, `pytest`, `npm`, Playwright, Alembic, Kafka, PostgreSQL, Chromium, AWS or end-to-end workloads. A local `git ls-remote` also could not resolve `github.com` in this container. No runtime claim below should be interpreted as independently reproduced.

**Evidence labels:** **C** = confirmed source condition at pinned commit; **R** = reasoned risk that still needs reproduction; **O** = operational/configuration gap visible in source; **U** = unverified. Severity is about importance if the risk materializes, not a claim of exploitability. Paths/line numbers refer to the pinned commit. A GitHub permalink for any referenced file can be formed as `https://github.com/Sreenav14/Market-Twin/blob/660487b65984226002d1c6df743d5a1cb745cf45/<path>#L<line>`.

## 1. Executive conclusion

MarketTwin has substantial foundations: explicit target authorization, Google ADK/persona planning, Playwright browser owner, origin/network policy, cooperative HITL with leases and generations, durable database entities, an outbox/Kafka architecture, a private knowledge preview worker, and deterministic/evidence-grounded evaluation. It is **not merely a UI prototype**.

It is **not yet demonstrably optimal or production ready**. The largest practical gaps are: (a) website research occurs before durable ingestion, so Processing is never reached when crawling fails; (b) browser DNS preflight and actual network connection are not provably tied together; (c) knowledge approval state needs strict validation; (d) execution throughput and dispatch readiness are limited/poorly surfaced; (e) a temporary worker-wide logging handler was left in place without a general redaction filter; (f) live infrastructure, regression and adversarial testing were not demonstrably completed.

**Do not rewrite the platform.** Fix these gaps incrementally, retaining the existing database-backed ingestion dispatcher, Kafka outbox, execution ownership, HITL fencing, model-runtime snapshots, verified-report classification, and structured test-case modes.

## 2. Priority finding register

### MT-001 — Link ingestion is not durable before crawling [C, Critical]

**Where:** `services/control-api/src/markettwin_control_api/api/ingestion.py:101–122`; `apps/web/src/pages/knowledge/IngestionPage.tsx`; `knowledge/processor.py:70–102`.

**Proof:** `POST /link` awaits `asyncio.to_thread(research_link, url)` at line 110 and only afterwards creates an `UploadFile` and invokes `ingest_source()` at line 120. `ingest_source()` is what uploads private content and persists `IngestionEntry` and its asset version. A crawler failure or long request therefore leaves no entry to show in Processing. Frontend navigation occurs only upon successful response. This matches the reported Klaviyo failure symptom. Also `asyncio.to_thread` cancellation does not forcibly stop the underlying OS thread, so client disconnect/cancellation does not necessarily stop research.

**Correct incremental fix:** Validate the URL and workspace first; write a small versioned, immutable source manifest to private storage; create the existing ingestion entry with `source_kind=public_link`, `source_url`, and queued status; return HTTP 202 with ID immediately. Branch inside the *existing* `IngestionProcessor` to perform read-only research, save an immutable research bundle, then invoke the existing Knowledge Worker. Preserve document ingestion, deterministic source IDs, S3/DB failure cleanup, explicit approval and retry ownership. Avoid introducing Kafka just for ingestion.

**Acceptance:** Accepted link returns ID promptly even when the target subsequently rejects research; UI immediately navigates to a processing page; failed state/retry survive restart; approved link research is source-attributed and cannot be approved until ready; file upload regression stays green.

### MT-002 — Approval does not require exact ready-for-review asset state [C, High]

**Where:** `api/ingestion.py:347–367`; `knowledge/repository.py:167–177`.

**Proof:** Endpoint only blocks `asset.status in {'uploaded','processing'}`, then checks that `entry.preview` has generated content. `repository.approve()` changes version status to `approved` and asset status to `included`, without asserting `needs_user_review`. If a failed asset has retained/nonempty preview, these checks would not reject approval. This is a **state-integrity gap**, not evidence that an attacker already exploited it.

**Fix:** Require `record.version.status == 'draft'` and `record.asset.status == 'needs_user_review'`, with a completed, validated, nonempty preview and intended source review. Reject all other states; use one transactional transition and add conditional-update/failure-state tests.

### MT-003 — Browser DNS preflight is not bound to Chromium's connect target [R, High]

**Where:** `services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/controller.py:456–478`; `browser/network.py:17–81`.

**Proof:** Route handler validates allowed URL and resolves host with `resolve_and_validate_host`, then calls `route.continue_()`. Chromium's actual DNS resolution/connection may occur separately from this checked resolution. Consequently, policy validation alone is not proof of connection-level SSRF/DNS-rebinding protection. The custom public-link downloader makes an intentionally different, explicitly IP-bound connection.

**Fix:** Test with a controlled DNS-rebinding fixture and redirect/CNAME chains; enforce outbound deny rules at network layer or use an approved IP-pinning egress proxy. Allow only authorized origin plus public destination, with exception for explicitly authorized local fixture mode. Never remove existing origin checks.

### MT-004 — Ingestion dispatcher can repeatedly inspect only the oldest 20 candidates [R, Medium]

**Where:** `knowledge/processor.py:29–43`.

**Proof:** Query sorts pending assets by `created_at` with `.limit(20)`; each of four dispatch slots loops through candidates and takes a session-level advisory lock for one. Under contention, jobs beyond the top 20 may be excluded repeatedly. Whether starvation occurs in real traffic requires testing.

**Fix:** Keyset pagination, or a database claim query with `SKIP LOCKED` plus an explicitly persisted claim/lease, while preserving crash recovery, safe process-wide concurrency, and advisory-lock ownership.

### MT-005 — Crawler fallback caches only the seed download [C, Medium]

**Where:** `knowledge/link_research.py:151,173–200,259–270`.

**Proof:** `cache` is initialized with the starting page. The route handler fetches subsequent URLs but never assigns those bytes to `cache[request.url]`. `saved_html_text(candidate)` only consults this dict; fallback for additional pages will generally be absent after rendering failure. This directly reduces robustness on SPA/navigation-heavy sites.

**Fix:** Save downloaded allowed navigation resources into a bounded cache keyed by normalized URL (and verified redirect identity); separately bound memory and bytes. Add a multi-page fixture where page two times out after HTML download and check fallback output.

### MT-006 — Crawler navigation can incur unnecessary repeated network work [R, Medium]

**Where:** `knowledge/link_research.py:136–286`.

**Evidence:** Custom Python downloader fulfills browser routes, with separate rendered inspection and fallback. The first page is predownloaded, but later requests can be redownloaded; off-origin scripts/styles are blocked intentionally, which prevents some application hydration. `networkidle` waits, disclosure clicks and navigation can use substantial time on heavy sites.

**Fix:** Introduce stage-specific timings, reuse safe cached content, record page-level failures, prioritize same-origin HTML content, enforce browser close/time budgets, and distinguish a partial research result from total unreadability. Do not remove third-party blocking merely to improve page appearance without a separate security design.

### MT-007 — The progress bar displays fixed numbers rather than measured work [C, Medium]

**Where:** `apps/web/src/pages/knowledge/IngestionProgress.tsx:7–14`.

**Proof:** Queued displays `20`, processing displays `50` with `max=100`; no measured fraction is derived. This is presentation that can look like actual percentage completion.

**Fix:** Use indeterminate progress with factual stages (`queued`, `researching`, `generating`, `ready`, `failed`) and honest elapsed-time text. Do not invent or interpolate percent without bounded measurable stages.

### MT-008 — Kafka dispatch can be disabled even when tests are queued [O, High]

**Where:** `services/control-api/src/markettwin_control_api/config.py:43`; `main.py:79–92`; `.env.example` `OUTBOX_RELAY_ENABLED=false`; `services/control-api/src/markettwin_control_api/services/run_dispatch.py:36–73`.

**Proof:** Starting a run changes database state and adds an outbox event. Publisher startup is controlled by the setting, default `False`. In that configuration, the run can remain queued forever unless an external relay is independently started. Health includes connectivity and enabled flag, but does not establish delivery.

**Fix:** Make readiness explicit (Control API + DB + knowledge worker + Kafka relay + execution worker + evaluation worker). In local development either enable the relay intentionally or visibly flag queue dispatch disabled; in production refuse run-start when no delivery path is provisioned, or surface truthful queued/waiting status with a diagnostic reason. Avoid conflating Kafka-connected with run-dispatch-healthy.

### MT-009 — Head-of-line blocking of failed outbox events [R, Medium]

**Where:** `packages/database-python/src/markettwin_database/repositories/outbox_repository.py:51–98`; `services/control-api/src/markettwin_control_api/services/outbox_relay.py:29–73`.

**Proof:** The relay claims the earliest unpublished row with `SKIP LOCKED`; on publish error increments attempts and stores `last_error` but does not set `next_attempt_at`, dead-letter/quarantine state, or per-record backoff. After sleep the same oldest failed event can be selected again, repeatedly delaying healthy later events.

**Fix:** Add next retry timestamp, failure classification, max/backoff policy, dead-letter/quarantine with operator recovery, and metrics for oldest backlog age. Do not quietly discard messages.

### MT-010 — Outbox holds a database transaction across Kafka publish [C, Medium]

**Where:** `services/control-api/src/markettwin_control_api/services/outbox_relay.py:32–73`.

**Proof:** `async with session.begin()` includes `await self._producer.publish(...)`. This guarantees claim ordering, but holds a row lock and DB connection during transport latency. Under Kafka outages this creates avoidable DB pool pressure. Changing it requires care: commit-before-publish reintroduces delivery-loss risk.

**Fix:** Keep existing semantics for V1 unless measured latency makes it a bottleneck; add a bounded producer timeout, small isolated relay DB pool, monitoring, and poison-message recovery. If later using explicit claims/leases, design for at-least-once duplicate delivery.

### MT-011 — Single sequential execution worker blocks while awaiting a human [C, High operational]

**Where:** `services/execution-orchestrator/src/markettwin_execution_orchestrator/worker.py:182–220`, notably `receive → process_command → commit`.

**Proof:** The worker's own docstring states human waits occupy the single consumer, preventing receipt of the next run. This is intentional V1 behavior to avoid replay of state-changing browser actions without ownership leases. It is not a simple bug.

**Fix:** For V1, be transparent about 1-active-run throughput and queue depth. For multi-run production concurrency, implement durable execution-owner leases and fencing before multiple consumers/workers; never just add `asyncio.gather` or Kafka partitions without ownership recovery.

### MT-012 — Processed-message markers precede execution completion [R, High reliability]

**Where:** `workflow/run_request_handler.py:80–139`; `worker.py:100–179`.

**Proof:** The acceptance transaction changes run from queued to planning and records `ProcessedMessage` *before* the browser journey. On replay, the code sees the processed marker and, if the run is in planning/running/awaiting-human, deliberately fails interrupted work rather than repeating possible side effects. This is a conservative no-replay policy, but it means an ordinary worker crash may make the entire test fail, and recovery requires explicit operator-driven restart semantics.

**Fix:** Preserve no-replay and mark outcomes as interrupted/uncertain. Add test cases for crash before acceptance, immediately after acceptance, during HITL, after side effect, and after terminal commit; ensure UI doesn't mislabel infrastructure interruption as website defect.

### MT-013 — Default feature scope truncates each knowledge entry to 1,000 characters [C, High quality]

**Where:** `services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/deep_run.py:63–88`.

**Proof:** `text=json.dumps(item.get('application_knowledge', item.get('name', '')))[:1000]`. If a large approved source is selected without an explicit scoped requirements contract, most of its knowledge is omitted, and a JSON string may be cut midway. Agent planning can then look thin or repetitive even though ingestion succeeded.

**Fix:** Deterministically extract typed requirements/skills, preserve evidence IDs and priority, apply token budgets at semantic boundaries, and report omitted requirements. A raw substring is not retrieval or faithful grounding.

### MT-014 — Agent behavior needs an actual browser effectiveness benchmark [U, High product]

**Where:** `workflow/planning.py`, `workflow/test_case_planner.py`, `workflow/journey_executor.py`, `agents/meta_agent_factory.py`, `agents/persona_agents.py`, `browser/tools.py`.

**What source proves:** Both structured feature-case planning and persona browser-agent wiring exist. Planner tool lists being empty are not necessarily miswiring: the feature planner produces typed cases while separate execution code operates the browser. Authorized origins can block exploration of another subdomain; isolated journeys can each begin on the homepage.

**What source does *not* prove:** Agents discover defects on realistic sites, reach secondary pages reliably, or meet a measurable exploration objective.

**Fix:** Build a local deterministic benchmark containing valid links, forms, redirects, login, one benign defect, one inaccessible feature, and a real multi-page journey. Record first-action success, visited distinct pages, relevant actions, proven assertions, coverage and cost. Compare feature-case vs persona runs; only then decide about bounded exploration-mode changes.

### MT-015 — Temporary worker logging implementation remains installed [C, High privacy/maintainability]

**Where:** `services/execution-orchestrator/src/markettwin_execution_orchestrator/temp_failure_log.py:1–104`; `worker.py:37–44,261–265`.

**Proof:** Module explicitly states 'Temporary local failure log. Remove after the planner failure is identified.' Worker `main()` always calls `install_temp_log_handler()`. That function installs a standard root `logging.FileHandler` on `.local/temp-execution.log` *without a general redaction filter*. Explicit `record_temp_note` and `record_temp_failure` do call `redact()`, but unrelated root logger messages copied by the FileHandler do not. Exception-text regex redaction is not comprehensive.

**Fix:** Remove temporary logging after replacing its necessary diagnostic visibility with structured safe logs/OTel and existing `run_failure.py` review gates. Until then make it local-debug-only, implement a redacting `logging.Filter` for every copied log line, disable sensitive content by default, add rotation/retention/permissions, and tests proving secret/token strings are not written. Do not strip useful correlation IDs.

### MT-016 — Session cookie is explicitly non-Secure in local login [C, Low if strictly local; High if reused]

**Where:** `services/control-api/src/markettwin_control_api/api/auth.py:133–142`, `auth/providers/local.py:30–34`.

**Proof:** `secure=False`. The login provider rejects use outside local environment; thus this is **not by itself a proven production vulnerability**. However, these cookie settings must not be copied into a real production auth provider.

**Fix:** Keep local behavior if needed, but make production auth's Secure/HttpOnly/SameSite settings explicit and covered by tests; require HTTPS and rotate credentials/CSRF tokens appropriately.

### MT-017 — CSRF protection is not a uniform shared API dependency [R, Medium]

**Where:** `api/human_actions.py:210–214`, `api/execution_pause.py:45–48`; `apps/web/src/lib/api.ts:299–355`; other mutation routes.

**Proof:** HITL and pause mutations perform explicit Origin + `X-MarketTwin-Request: 1` checks. The generic API request helper does not add this header globally, and other mutation endpoints use cookie authentication without an equivalent shared check visible in their route code. `SameSite=lax` cookies provide substantial cross-site mitigation and JSON requests often trigger preflight, so **this is not a demonstrated CSRF exploit**. Same-site cross-origin, proxy, file-upload and unusual browser contexts deserve tests.

**Fix:** Define one strict mutation-origin policy and per-endpoint exceptions; cover all cookie-authenticated mutations, session changes, file uploads and privileged actions. Ensure generic client functions participate without breaking read-only endpoints.

### MT-018 — Knowledge Worker internal preview route has no explicit auth middleware [O/R, Medium]

**Where:** `services/knowledge-worker/src/markettwin_knowledge_worker/main.py:29–33`; `api/preview.py:93–127`.

**Proof:** Private `/internal/v1/knowledge/preview` processes uploads and potentially invokes costly models, with no HTTP caller authentication in the inspected handler. The architecture calls it a private worker, so safety depends on binding, VPC, firewall, service-to-service routing and deploy policy.

**Fix:** Keep worker isolated, not public; define internal service authentication and resource/rate limits if crossing an untrusted boundary. Run a network exposure test after container/AWS deployment.

### MT-019 — Knowledge Worker can perform long model calls inside HTTP request [R, Medium]

**Where:** `knowledge_worker/api/preview.py:93–127`; `knowledge_builder.py:108–170`; `control_api/knowledge/client.py`.

**Proof:** Worker receives a bounded upload, extracts, generates multiple model batches, consolidates, then replies. This is acceptable when the *Control API background ingestion worker* owns the call; unacceptable as an end-user synchronous browser request. Link ingestion currently violates this separation before reaching the background worker.

**Fix:** Only background processors invoke preview; enforce all-resource deadlines, concurrency limits, model budget, failure persistence and bounded retries.

### MT-020 — Evaluation reruns are retryable but can repeatedly prioritize the same unfinished runs [R, Medium]

**Where:** `services/evaluation-worker/src/markettwin_evaluation_worker/worker.py:61–80`.

**Proof:** Every five seconds, query oldest 20 completed runs missing a completed v1 report; call `process_run()` for each. It uses a session-level advisory lock for ownership, which is good. A permanently failing old run can incur repeated model cost and delay later runs, without visible backoff/dead-letter in this loop.

**Fix:** Persist retry attempts/next retry and diagnostics. Continue to mark a report complete only after durable evidence validation and generation. Add cost and error instrumentation.

### MT-021 — Evaluation commits an early model snapshot before final report [C, Medium]

**Where:** `services/evaluation-worker/src/markettwin_evaluation_worker/workflow.py:102–113,117–170`.

**Proof:** Code commits runtime snapshot before evaluation, contrary to `_evaluate_and_generate_report` docstring 'Create findings and report in one transaction'. This is intentional/possibly justified for provenance, but contradicts the single-transaction description; retries must be idempotent across this intermediate commit.

**Fix:** Correct contract documentation, test rerun after failure at each commit boundary, verify unique snapshot/report constraints and no duplicate findings.

### MT-022 — Frontend request and UI semantics need incremental cleanup [C, Low/Medium]

**Where:** `apps/web/src/pages/knowledge/IngestionPage.tsx`, `KnowledgeReviewPage.tsx`, `IngestionProgress.tsx`; `apps/web/src/lib/api.ts`.

**Proof:** Link submission only navigates after crawling finishes; review page polls pending ingestion every 1.5 seconds; queued and processing are collapsed into fixed-percent output; source-access link can represent a persisted text research bundle rather than the original linked website, so labels need to distinguish original URL from processed evidence.

**Fix:** Immediate ID-based routing, stage/status as a typed API contract, polling only while pending, clear failure/retry diagnostics, separate 'original web URL' and 'download retained research evidence', preserve source access authorization.

### MT-023 — Placeholder packages and infrastructure directories [C, Low maintainability; High deployment readiness]

**Where:** `packages/agent-schemas`, `packages/evaluation-rubrics`, `packages/event-schemas`, `packages/mission-schemas`, `packages/openapi-client`, `packages/policy-rules` each have placeholder `src/.gitkeep`; `.github/workflows/.gitkeep`; `infra/helm/markettwin/README.md` effectively empty; Terraform folders placeholders.

**Proof:** Inventory shows these are not substantive implemented source packages or CI/deployment definitions. These are not necessarily runtime bugs, but they can mislead maintainers about completeness.

**Fix:** Either document them as future placeholders (excluded from build graph), or remove them once the chosen long-term package boundaries are known. Do not create empty abstractions just to fill a diagram. Add a real continuous-integration workflow that installs pinned tools, runs typecheck/lint/unit tests, and gates merges. Introduce AWS IaC only for the actual selected deployment target, incrementally.

### MT-024 — Docker Compose is development infrastructure only [O, High deployment]

**Where:** `infra/compose/docker-compose.yml`.

**Proof:** It starts PostgreSQL, Kafka and MinIO, uses local development default credentials if unset, and `minio/minio:latest`, `minio/mc:latest`. It does not constitute a production-grade network/secret/backup/scale/deployment architecture.

**Fix:** Pin image digests or tested versions, replace default secrets with env-required values outside explicitly local profiles, add backups, private ingress/egress, per-service credentials and health checks, and production IaC with cost limits. Preserve lightweight local Compose for developers.

### MT-025 — Database URL constructed by raw string concatenation [R, Medium]

**Where:** `services/control-api/src/markettwin_control_api/config.py:86–96`.

**Proof:** DSN directly interpolates username/password/host strings. Passwords containing URI-reserved characters can be parsed incorrectly.

**Fix:** Construct with `sqlalchemy.engine.URL.create(...).render_as_string(hide_password=False)` as already done in execution/evaluation worker startup; add tests with `@`, `:`, `/`, `%` in credentials.

### MT-026 — Observability source exists; delivery is unverified [O/U, Medium]

**Where:** `packages/shared-python/src/markettwin_shared/observability.py`, service-specific observability modules, `.env.example`.

**Proof:** Configurable OpenTelemetry OTLP exporter and ADK/LiteLLM instrumentation exist; `.env.example` disables observability by default and shows a LangSmith endpoint as an example. Nothing in static source proves an authenticated trace reaches a specific LangSmith project.

**Fix:** Enable one sanitized test trace under a non-secret test project, follow run/agent/journey IDs across services, confirm exporter shutdown flush, check prompt/content capture off, and preserve DB as authoritative product history. Don't add another tracing vendor to solve configuration.

### MT-027 — Test suite exists but cannot be treated as passing from GitHub presence [U, High]

**Where:** `services/*/tests`, `packages/*/tests`, `apps/web/src/**/*.test.tsx`, `apps/web/e2e`.

**Proof:** There is meaningful test coverage for origin policy, HITL leases/generation, outbox, ingestion processing, visual evidence and frontend behaviors. Several PostgreSQL integration tests are opt-in and explicitly skip unless environment flags are set (e.g. `MARKETTWIN_TEST_DATABASE=1`, `MARKETTWIN_SCOPE_TEST_DATABASE=1`). Browser tests launch Chromium. No tests were executed during this source audit.

**Fix:** Run lint/typecheck/unit/integration/e2e in a pinned local environment; record commands, exact exit code, count of passed/skipped/failed, and environmental assumptions. Do not equate mocks with end-to-end proof.

### MT-028 — No code-level proof of production authentication/SSO or anti-bot coverage [U, High roadmap]

**Where:** local auth provider, HITL workflows, target verification policies.

**Proof:** Local development identity login is intentionally environment gated. The HITL controller supports human-assisted authentication and verification markers. This does **not** constitute full Cognito/SSO production integration, universal MFA support or CAPTCHA solving by agents.

**Fix:** Finish chosen identity provider in its own incremental phase; run a controlled session/HITL demo; do not claim unsupported sites or arbitrary CAPTCHA bypass.

## 3. Components that should NOT be deleted during cleanup

1. **PostgreSQL `IngestionProcessor`** and session-level advisory locks: provides durable resume, 4 local dispatch slots and double-processing defenses. Fix lifecycle and starvation rather than replace with a second queue.
2. **Transactional outbox + processed-message register:** needed for Kafka at-least-once delivery and command idempotency; do not swap out for a synchronous HTTP call.
3. **Browser target allowlist, DNS validation and network policy:** security layers to strengthen, not remove.
4. **Exclusive HITL leases, generations, viewer ticket and worker-owned browser:** preserve same-session authentication, fence stale viewers and prevent agent/human simultaneous input.
5. **Typed evidence schemas and evidence-backed report classification:** protect against AI claims being mistaken for verified defects.
6. **Two execution modes:** deterministic feature cases and bounded persona journeys solve different testing questions; simplify UI labels, benchmark both, do not merge before measured proof.
7. **Private source storage and explicit knowledge approval:** human-reviewed knowledge is a separate trust boundary from untrusted web content.
8. **LangSmith-targeted OpenTelemetry pipeline:** keep one diagnostic stack and fix wiring/testing rather than add unrelated instrumentation services.

## 4. Potentially unnecessary or misleading code

- `temp_failure_log.py`: explicitly temporary and unconditionally installed. **High-confidence cleanup candidate after safe diagnostics replacement.**
- Six placeholder package directories: scaffolding only, not proof of implemented cross-language contracts. Consolidate/remove *only if no roadmap/build references rely on them*.
- Empty CI/Helm/Terraform scaffolding: mark unimplemented or implement when deployment is specified. Do not advertise as production support.
- Repeated authorization in `ingest_link()` then `ingest_source()`: a small duplicate database/auth call, not a security reason to weaken checks. Extract shared internal authorized persistence.
- Fixed progress percentages: UI logic that conveys false precision; replace with factual stage labels.
- Large legacy CSS stylesheet: candidate for component-by-component removal **only after route/component usage and visual regression checks**; size alone does not prove dead code.
- `9edac11ff95c` no-op Alembic migration: historical revision is part of an existing chain. **Do not delete or rewrite applied migration history**; document it as an intentional no-op if needed.

## 5. Required integration trace and acceptance plan

### A. File ingestion

`POST /ingestion` authorization → validate bounded source → private S3 put → transactional knowledge entry/asset `uploaded` → 202 ID → Review page → DB dispatcher claim/lock → private source download → Knowledge Worker `/internal/v1/knowledge/preview` → evidence/generation → `needs_user_review` → explicit approval (`included`) → application association → frozen run knowledge snapshot. Cover storage failure cleanup, rejected MIME/extensions, truncation and worker outage.

### B. Link ingestion (after fix)

`POST /ingestion/link` URL-policy + workspace auth → durable source manifest + entry, no crawl → 202 ID → Processing page → existing dispatcher claim → bounded read-only research with private/pinned egress and per-page diagnostics → research bundle save → Knowledge Worker preview → review/approval. Crash during research must not run two uncontrolled crawls or incorrectly approve partial content.

### C. Test execution

Target creation → exact allowed-origin scope → owner/admin authorization → TestRun draft → run queue + outbox event (one DB tx) → relay and Kafka → consumer accept with processed-message marker → runtime snapshot/planner → bounded browser actions/Playwright → persisted steps/artifacts → optional HITL exclusive lease/verification → terminal run state → evaluation worker claim → deterministic/visual verification → durable report. Verify all cross-workspace and revoked-scope paths fail closed.

### D. HITL and live observation

One isolated browser per journey; passive read-only frame source uses generation and actor authorization; protected HITL control uses lease + single viewer; no screenshots/observations of credential entry; control mode changes atomically; stale generation cannot send input; release only resumes after approved target verification. Test refresh/disconnect/expiration/worker crash and boundary races. Don't conflate passively watching with leasing control.

### E. Reporting integrity

Model-reported outcome → explicit saved evidence IDs → authoritative scoped read of exact step/screenshot → visual/deterministic verification → verified finding only if evidence and prerequisites suffice; else unverified/blocked/untested. Visual evidence only can substantiate visual assertions, not invisible backend facts; an HTTP error or blocked origin alone does not prove product defect.

## 6. Exact local verification commands (NOT run in this audit)

Execute from a clean checkout using Python 3.12, Node >=22 and project-specific credentials. Record outputs as files; use the same SHA as this report or explicitly identify the new SHA.

```bash
git status --short
git rev-parse HEAD
git branch --show-current
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -q
npm ci
npm run typecheck
npm run build
npm test
```

**Database integration:** Start only the supported local PostgreSQL/MinIO/Kafka stack, run Alembic to head, test schema reset/upgrade and configured opt-in tests; never run `alembic downgrade` against shared/production data. Confirm `alembic heads` contains the intended single head.

**Browser E2E:** Install pinned Playwright Chromium; start Control API, Knowledge Worker, Kafka relay, execution worker, evaluation worker and frontend; verify backend health, worker availability, HITL viewer proxy, link ingestion, file ingestion, agent navigation, same-browser assisted login, approval, evidence, and reports. Then run frontend Playwright E2E for desktop + mobile using a synthetic site—not an arbitrary third-party account.

**Security tests:** Redirect from approved host to RFC1918/loopback/metadata endpoint, DNS rebinding between validation and connect, mismatched workspace IDs, stale HITL generations, stolen/expired viewer tickets, failed review-state approval, CSRF-origin/multipart variants, huge/slow ingestion, model prompt-injection text, S3 URL access, log-leak simulation, Kafka publish ambiguity and process kill/restart.

**Reliability tests:** Simulate `Knowledge Worker` down before/after enqueue, DB reconnect during locked work, producer publish success/mark commit failure, execution worker termination before and after browser side effects, evaluator model quota outage, and repeated dead-letter events. Every run must terminate honestly or remain visibly retryable without inventing a product verdict.

## 7. Small incremental remediation sequence

1. **P0-A:** Write a test reproducing failed-status approval gap; require exact reviewable status in API *and* repository; run corresponding unit + DB tests.
2. **P0-B:** Implement queued link source manifest and schema migration; return 202 before fetch; preserve upload contract; run immediate navigation test.
3. **P0-C:** Move website research into existing processor with durable stage/status/errors/retry, saved research bundle, limits and safe egress; run Klaviyo-like synthetic SPA fixture plus failures.
4. **P0-D:** Harden browser connection-level network boundary; run adversarial DNS/redirect fixture before any public deployment.
5. **P0-E:** Gate or replace temporary root-file logging; verify sensitive credentials never reach logs/OTel or screenshots during HITL.
6. **P1-A:** Make Kafka dispatch readiness and backlog explicit; enable deliberate local relay; test run start through actual consumer.
7. **P1-B:** Add bounded retry/backoff/quarantine for outbox and evaluation poison jobs with operator-visible diagnostics.
8. **P1-C:** Replace 1,000-char knowledge truncation with structured sourced requirement selection; benchmark real browsing and feature-case quality.
9. **P1-D:** Harden startup/CI and deploy configuration; run all local tests with and without opt-in services.
10. **P2:** Simplify unreferenced UI/CSS/packages only after usage detection, route regression and visual comparison. Add multiple execution-owner workers only with durable leases/fencing.

## 8. Release-readiness criteria

- No source-ingestion request holds the browser UI waiting for third-party crawling or a model.
- All accepted ingestions retain recoverable IDs and truthful status across restarts.
- Failed/queued/processing assets can never be approved; approved snapshots are immutable and source-attributed.
- Browser network isolation is tested at actual connection level; allowed-origin and user authority are separately enforced.
- HITL same-session authentication is exclusive, generation-fenced, and credentials do not leak via screenshots, logs or trace content.
- Queued Kafka run dispatch and completed evaluation are independently healthy and observable.
- No fatal head-of-line message blocks unrelated work indefinitely.
- Reports never label an agent-reported or blocked action as a verified website defect without matching evidence.
- Tests pass, including PostgreSQL opt-in, Chromium, and frontend E2E; exit status and skipped tests are recorded.
- CI checks and chosen minimum-cost AWS deployment plan exist; local secrets/defaults do not leak into production.

## 9. Coverage ledger (honest)

| Area | Actual work in this audit | Still needed |
|---|---|---|
| Repository inventory | All 699 tracked paths and categories checked | Local working tree and unpushed files |
| Control API | All `src` file paths retrieved/screened; main route/ingestion/auth/HITL/relay/readiness paths deeply inspected | Every endpoint branch manually reviewed and integration-tested |
| Execution orchestrator | All `src` file paths retrieved/screened; browser owner, policy, planning, Kafka worker, HITL, snapshots investigated | Real ADK/browser runs, interrupted-worker and DNS-rebinding tests |
| Knowledge Worker | All `src` file paths retrieved/screened; preview/extraction/builder traced | Actual multimodal document fixtures and model-budget tests |
| Evaluation Worker | All `src` paths retrieved/screened; deterministic, visual, report and worker flow traced | Full generated-report E2E and recovery tests |
| Web UI | All frontend `src` paths retrieved/screened; ingestion, HITL, live observer, new run, API examined | Live browser interactive E2E, accessibility and visual regression |
| Shared models | All main shared/database `src` paths retrieved/screened | Alembic model vs DB integration and typechecker output |
| Migrations | All migration-version files retrieved and revision links inspected | Actual upgrade/heads/downgrade in expendable DB; autogenerate diff |
| Tests | Numerous suites inspected, especially ingestion, HITL, policy, evaluation | Run every test; record pass/fail/skip and external prerequisites |
| Infra/ops | Compose, settings, env example, CI/Helm/Terraform placeholder inventory | Real deployment, secrets, IAM, network, cost and tracing validation |

**Final audit verdict:** **Architecture: promising but not proven production-ready.** Source correctness: several clear defects and risks requiring targeted fixes. Optimization: favor targeted simplification over platform rewrite. **Certification: withheld** until the local full test suite, database migrations, browser security fixtures, runtime wiring and dependency checks actually run.
