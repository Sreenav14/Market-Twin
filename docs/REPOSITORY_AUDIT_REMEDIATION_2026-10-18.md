# Repository audit remediation — October 18, 2026

## Scope and evidence

Requested source audit: `MARKETTWIN_REPOSITORY_AUDIT_2026-10-18.md`.
The audit's pinned commit matches checkout HEAD,
`660487b65984226002d1c6df743d5a1cb745cf45`. Existing uncommitted link-ingestion
and CAPTCHA-widget changes were present before remediation and were preserved.
Historical checkpoint documents describe earlier commits; they are not the
baseline for these changes.

Four agents worked concurrently (the maximum available): integration/API/web/CI,
ingestion/knowledge security, execution/browser privacy, and durable backend
recovery. Findings were checked against local code and regression tests, rather
than assumed correct because they appeared in the audit. No provider calls,
third-party authenticated browsing, deployment, commit or push were performed.

“Fixed” below describes the concrete source defect and its regression coverage.
It does not certify production deployment, model accuracy, universal SSO/CAPTCHA
support, or all possible execution interleavings.

## Finding-by-finding disposition

| Finding | Disposition | Evidence, changes, or remaining work |
| --- | --- | --- |
| MT-001 durable links | Fixed and strengthened | Existing queued-first endpoint returns 202 before crawling. Original link manifest remains immutable; research uses content-addressed private objects. Cancelling processor work retains advisory ownership until its crawl thread stops. Regressions cover immediate navigation, failed research and cancellation. |
| MT-002 approval state | Fixed | API and repository require draft version, exact `needs_user_review` state, completed processing and schema-valid nonempty preview. Failed retained previews cannot be approved. Actual PostgreSQL regression passed. |
| MT-003 browser connection isolation | TCP connection gap fixed; deployment isolation unverified | Every Chromium session now owns a bounded loopback HTTP/CONNECT proxy. The proxy resolves and validates all DNS answers, then dials a validated numeric IP; Chromium does not resolve that destination again. Existing origin/redirect/WebSocket checks remain. Loopback bypass is disabled, QUIC disabled and nonproxied WebRTC UDP disabled. Controlled changing-DNS, unsafe-address rejection, real Chromium HTTP/WebSocket and end-to-end TLS tests cover the socket boundary. Production OS/container egress policy remains defense in depth and is not deployed here. |
| MT-004 ingestion starvation | Fixed for candidate-window exclusion | Dispatcher keyset-pages through `(created_at, entry_id)` beyond twenty contended records while retaining advisory locks. This removes the fixed-window starvation mechanism, not every possible distributed fairness issue. |
| MT-005 seed-only cache | Fixed | Allowed downloaded resources enter a fragment-normalized cache after redirect checks, bounded to 256 entries/40 MiB. Real Chromium regression verifies second-page raw HTML survives rendering failure. |
| MT-006 crawler repeated work/bounds | Partially fixed | Safe response reuse and multi-page fallback improved. Existing 100-page/20-minute budgets and third-party blocking retained. Blocking DNS resolution and complete stage timing/partial-result observability remain. |
| MT-007 fixed progress | Fixed | Removed fabricated 20/50 percent values; pending work displays indeterminate progress and factual saved/processing messages. |
| MT-008 queue dispatch readiness | Partial; existing warning confirmed | Existing Kafka badge explicitly says relay off; it does not claim execution availability. Production worker availability/backlog readiness and an explicit external-relay provisioning contract remain necessary. No automatic enabling of cloud Kafka or duplicate workers. |
| MT-009 poison outbox | Fixed | Persistent exponential retry, eight-attempt quarantine, retained payload, operator recovery, safe exception-class diagnostics, partial pending index. Actual PostgreSQL test proves later messages remain claimable and retained messages recover. |
| MT-010 transaction around publish | Bounded, intentionally retained | Thirty-second producer timeout limits the transaction duration while preserving acknowledgement-before-mark semantics. Ambiguous publish can duplicate on retry; consumer idempotency remains required. Isolated relay pool and latency instrumentation remain. |
| MT-011 one active execution | Intentional V1 limit retained | Parallel input without durable owner leases/fencing would weaken safety. Durable multi-run ownership, queue-depth presentation and production capacity work remain. |
| MT-012 processed-before-execution | Conservative no-replay retained | Existing interrupted-run handling remains; side effects are not blindly replayed. Execution command rejection and regression results are recorded below. Durable resume after a browser-owner crash remains a separate design task. |
| MT-013 knowledge truncation | Fixed for default feature scope | Replaced slicing serialized JSON at 1,000 characters with bounded whole semantic fields/requirements and explicit omitted-item diagnostics. This improves deterministic grounding; it does not establish model effectiveness. |
| MT-014 effectiveness benchmark | Unverified product gate | Deterministic browser fixtures/benchmark tests exist; scripted acceptance does not establish live-model defect discovery, quality or cost. A controlled, budgeted provider comparison is still required. |
| MT-015 temporary root log | Fixed default privacy boundary | Worker no longer installs root-file copying. Explicit temporary diagnostics are opt-in and rotate at bounded size; default path writes no diagnostic file. Sensitive-field and failed-request URL regressions added. This is not a claim that arbitrary opt-in debug payloads are universally redacted. |
| MT-016 local cookie | Intentional local-only behavior retained | Local login remains disabled outside local environment. `HttpOnly`/`SameSite=lax` and insecure localhost cookie behavior remain; production identity/HTTPS cookie implementation is not supplied by this patch. Blank login now returns 422 rather than escaping validation. |
| MT-017 uniform browser mutations | Fixed for Control API browser entry points | Application-wide dependency validates exact configured Origin plus `X-MarketTwin-Request: 1` on requests carrying browser origin/fetch metadata or a session cookie. JSON and multipart clients send the header. Browser login, logout and privileged mutation regressions cover foreign/null/missing origins. Headerless non-cookie CLI requests still pass endpoint authentication. Existing stricter HITL checks remain. |
| MT-018 preview caller identity | Hardened | Shared internal bearer secret is required outside local/test; configured secrets are enforced in every environment before multipart processing. Local/test may omit it for existing local development. Requires matching operator configuration on API and worker; private listener/network controls still matter. |
| MT-019 long preview calls | Parser bounds fixed; deployment limits remain | Document parsers and native video probe/clip wrappers run in killable/reaped resource-limited children: 45 CPU seconds and 2 GiB memory through POSIX limits or Windows Job Objects. Document/probe wall limit60s; video clipping120s with bounded descendants, clip count and scratch output. Office archive/output limits, pre-multipart two-slot admission and full-preview deadline added. Actual FFmpeg transcoding is unverified because the executable is absent. Upload connection deadlines and deployment-global capacity remain partial. |
| MT-020 evaluation poison jobs | Fixed | Persisted retry timestamps, five-attempt quarantine and safe diagnostics exclude failing runs from the oldest candidate window. Rows remain recoverable; operator SQL is documented in `services/evaluation-worker/RETRY_RECOVERY.md`. |
| MT-021 early snapshot commit | Contract corrected and retries tested | Provenance commit is explicitly separate from final findings/report transaction. Failure-boundary/retry tests added. Semantic snapshot hash reuse and worker advisory ownership retained; no uniqueness migration that could reject existing history. |
| MT-022 ingestion semantics | Fixed for new entries | Original public URL persists immediately in the typed preview source, survives worker replacement, and appears separately from the signed retained-evidence link. API processing stages derive from durable status/content type; UI displays queued/research/generation/review/failure truthfully. Existing entries without the original URL require resubmission or a deliberate backfill; no poll-time storage downloads were introduced. |
| MT-023 placeholders/CI | Source lint/type gates fixed; deployment remains | Full Ruff now passes. All six production Python source trees pass Pyright. CI blocks on both, plus unit/typecheck/build jobs with locked dependencies. Full test/script Pyright remains a nonblocking artifact with about 1,697 diagnostics at the latest checkpoint. Source/migration wrapping was AST-equivalent; no applied migration behavior changed. Placeholder infrastructure stays explicitly documented; hosted CI and actual deployment remain unverified. |
| MT-024 Compose | Local hardening fixed; production remains open | Required Postgres/MinIO passwords, loopback published ports and installed MinIO image digests replace embedded password fallback/unrestricted binds/latest tags. Compose validates without starting containers. Existing volumes do not rotate passwords automatically. Backups, IAM, private production ingress/egress and AWS cost limits remain deployment work. |
| MT-025 DSN escaping | Fixed | SQLAlchemy `URL.create` round-trips reserved username/password characters; regression covers `@`, `:`, `/`, `%`. |
| MT-026 trace delivery | Prior local delivery evidence; content-off acceptance remains | Existing session records confirm a smoke span and workflow roots reached `markettwin-local`; morning export timeouts also occurred. This continuation made no collector calls. Complete capture-off/correlation/flush acceptance remains unverified; local delivery is not a production observability guarantee. |
| MT-027 verification | Expanded; see results below | Tests actually run, including Chromium and disposable PostgreSQL. Root collection succeeds on this checkout; earlier collection-failure checkpoint was stale. Opt-in tests and mocked API browser tests are distinguished from full live-stack/model acceptance. |
| MT-028 production identity/anti-bot | Open roadmap | Local auth/HITL is not production Cognito/SSO or universal anti-bot support. No arbitrary CAPTCHA bypass was added. |

## Additional confirmed local-audit fixes

- Agent `select()` now uses the same sensitive-fill policy as text/check controls.
- Failed-request observations retain only sanitized origin, omitting credentials,
  query, fragments, sensitive paths and raw transport failure text.
- Knowledge filenames reject Windows drive/ADS syntax, device names, trailing
  spaces/dots and invalid characters before filesystem writes.
- Visual evidence storage validates provider, configured bucket and artifact key
  namespace before download.
- Incomplete evaluation reports no longer block their intended recovery path.
- Kafka settings hide password repr, reject empty SASL credentials and require
  TLS for SASL; explicitly local non-SASL plaintext remains supported.
- Runtime snapshots recursively remove credential/DSN/private-key fields while
  preserving a narrow allowlist of semantic journey/persona/mission keys.
- Passive observation enforces the same minimum internal secret length as control.
  Control API accepts the worker's canonical `MARKETTWIN_HITL_INTERNAL_SECRET`,
  with legacy API alias compatibility.
- Viewer tickets are sent only to the exact same-host, matching ws/wss protocol,
  queryless `/api/v1/hitl-viewer` endpoint, including after reconnection.
- File-upload and URL-entry fields have distinct React identities when switching
  source type, preventing uncontrolled file inputs from being reused as controlled
  URL fields. The final Chromium ingestion workflow passed after this correction.
- Empty testing-depth metadata no longer crashes rendering; top-level render
  errors have a recoverable fallback without exception payload contents.
- Nonlocal API schema/docs are disabled; nonlocal Kafka diagnostic probes require
  authentication before opening broker connections.
- Artifact signing rechecks active authorization of the run's exact target.
  Revocation retires all retained authorized grants, preventing older-grant
  reactivation; historical attestations and frozen run/report records remain.
- Workspace-mismatched and terminal-run execution commands now commit separate
  rejection receipts before Kafka acknowledgement. Rejected replay cannot enter
  accepted-run interruption recovery. Database errors and queued/active failed
  claims remain retryable; malformed/unsupported envelope handling is not broadened.

## Initial remediation verification (superseded where noted below)

Environment: existing Windows Python 3.12 environment and installed Chromium,
repository lockfiles, local PostgreSQL. Windows sandbox denied subprocess/temp
access on initial attempts; corresponding commands were rerun with approved
escalation. Initial failures during concurrent edits are not final acceptance.

- Root `pytest --collect-only -q -p no:cacheprovider`: exit 0, 1,018 tests collected
  at that checkpoint (subsequent regressions increase the count).
- Ingestion/API/processor/crawler/preview focused suite: exit 0, 72 passed,
  including real Chromium multi-page, JavaScript and raw fallback fixtures.
- Backend shared/evaluation/database/outbox batch: exit 0, 140 passed, one DB
  opt-in skip; additional boundary/recovery regressions passed separately.
- Final combined Control API and Knowledge Worker suites: exit 0, 412 passed,
  18 skipped, 13 warnings. Skips are opt-in PostgreSQL/live-model cases; scoped
  production Ruff/Pyright checks passed.
- Disposable PostgreSQL: seven opt-in tests passed. Upgrade to `a7d8e9201b34`,
  downgrade to its parent and re-upgrade succeeded with retained unpublished
  payload/attempt counts. Generated database removed; canonical database untouched.
- Auth/origin/Kafka/observation configuration focused batch: exit 0, 31 passed.
- Frontend viewer/ingestion focused batch: exit 0, 20 passed.
- Final ingestion/activity/new-run focused batch: exit 0, 15 passed. Under the
  concurrent Chromium load, default one-second React test waits and five-second
  test budgets produced scheduling failures; async render waits now allow five
  seconds, and the verification command uses `--testTimeout=15000`.
- Frontend typecheck and production build: exit 0. Existing bundle-size warning
  remains; no unrelated code splitting changes.
- Final frontend unit suite: exit 0, 109 passed across 26 files. Vitest emitted
  its existing jsdom `scrollTo()` not-implemented warning; no test failed.
- Scoped changed-production Ruff and Pyright checks passed. Full Ruff initially
  reported 284 errors. Full Pyright at a concurrent-edit checkpoint reported
  1,746 errors, including existing and added test typing debt; this is not a clean
  repository-wide gate. Raw diagnostic logs are under `.local/audit/remediation-*`.
- `docker compose --env-file .env -f infra/compose/docker-compose.yml config --quiet`:
  exit 0; no containers started/reconfigured by that command.
- Playwright initial desktop/mobile suite: 100 passed, nine stale desktop
  assertions failed, seven intentional mobile duplicate-viewport skips (18.4 min).
  All nine corrected cases then passed (two workbench + seven desktop reruns).
  Every runnable mobile case passed; final post-input-fix Chromium ingestion
  workflow also passed. This is complete composite coverage, **not a claim of a
  single green full invocation**. APIs/data were mocked/synthetic. Evidence paths:
  `.local/e2e-focused-audit-20261018`, `.local/e2e-audit-corrected-desktop`,
  `.local/e2e-audit-ingestion-final`. Only owned Vite 5199 was stopped afterward.

- Final execution-orchestrator suite: exit 0, 459 passed, three opt-in database
  skips, 72 warnings. The popup expiry test initially asserted frame rejection
  after its mocked clock had ended; both input and frame checks now run within
  the frozen-clock scope. The focused real-browser regression and full suite pass.
- Overall Python root collection completed at its earlier checkpoint (1,018
  tests); the per-service final runs above provide the recorded pass evidence.
- The earlier 60% estimate was a rough checkpoint. Use the dispositions above:
  source fixes and runtime/deployment/provider acceptance have different scopes.

## Continuation verification and local schema upgrade

- After introducing the pinned proxy: full execution suite 463 passed, three
  explicit database skips; six subsequent focused proxy tests cover WebSockets,
  end-to-end TLS and fail-closed Chromium behavior after proxy shutdown, including
  direct loopback targets. No external target or model was used.
- Parser/admission/source-format batch: 40 passed. Additional Windows isolation
  tests verified hard memory allocation rejection and CPU-bound child termination.
  Video/source-format/parser follow-up: 19 passed; final video regression4passed.
  Tests verify native descendant termination on timeout/cancellation; real FFmpeg
  transcoding remains unverified because no executable is installed locally.
- Ingestion contract: 48 API/processor tests and ten frontend tests passed;
  frontend typecheck passed. Integrated API/Knowledge Worker run: 430 passed,
  18 opt-in skips, 13 warnings. Frontend final run: 110 passed across 26 files;
  production build passed with the existing bundle-size warning.
- Full Ruff: zero findings. Production Pyright across all six source trees: zero
  errors/warnings. Full test/script typing remains separate debt; raw checkpoint
  report is `.local/audit/pyright-current-static.json`.
- Canonical **local** database upgraded from `9e3a24b17c60` to `a7d8e9201b34`.
  Before upgrade, a full custom-format PostgreSQL backup was created and verified
  with `pg_restore --list`: `.local/audit/pre-audit-schema-20261019T015217Z.dump`
  (1,649,941 bytes). No service restarted and no downgrade/data deletion performed.
- Proxy bypass behavior follows Chromium's documented
  [loopback subtraction rule](https://chromium.googlesource.com/chromium/src/+/5e87dfef0c85687ea/net/docs/proxy.md)
  through Playwright's [launch proxy configuration](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-option-proxy).

## Loading these changes

The canonical local database is now upgraded to `a7d8e9201b34`; apply this additive
migration before upgrading any other database whose services read the retry columns.
Configure matching `KNOWLEDGE_INTERNAL_SECRET` on API and Knowledge Worker for
nonlocal environments; `MARKETTWIN_HITL_INTERNAL_SECRET` is the shared browser-owner
secret name. Restart existing service owners rather than starting duplicate
execution/evaluation consumers. No user service was restarted during this work.

Former Compose fallback passwords must be rotated wherever actually used. This
patch removes fallbacks; it does not change credentials in existing volumes or
remote services. Production identity/hosting selection is pending user input.
Public deployment requires the operational/network isolation acceptance above.
