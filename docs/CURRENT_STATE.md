## Active: audited live execution implementation (2026-10-18)

User resumed implementation under the complete repository audit/live execution
master specification dated 2026-10-18 and explicitly requested parallel agents.
Current baseline is commit `38431448`; initial Git status contained only the
untracked user specification. Preserve that document and all existing source.

Current plan, ownership, findings and checks:
[Live execution audit checkpoint](LIVE_EXECUTION_AUDIT_CHECKPOINT.md).
Four slots are active: root audit/integration, worker security, Control API/read
model, and frontend. Worker observation is already committed; public API and live
UI are being added. Historical statements below saying observation is absent or
coding remains paused are superseded by this checkpoint. No full acceptance yet.

## Historical instruction: implementation paused; detailed live execution plan (2026-10-17)

User stopped coding and requested a detailed what/where/why document. Working plan:
[Live execution implementation plan](hitl/LIVE_EXECUTION_IMPLEMENTATION_PLAN.md).
It contains the audited interfaces, completed corrections, missing observation
capability, proposed read-only frame/activity contracts, exact file map, security
requirements, phases L0–L7, acceptance matrix and operational limits.

Before the stop, MT50 presentation/readiness/native-link-name corrections were
implemented and focused checks passed. Fresh isolated persona run `a548d974`
verified automatic viewer connection, real synthetic login/MFA, Done, isolated
reuse and rendered report (3 passed). Feature Cases run `28e0d372` also completed
its handoff/run/report. Details and artifact IDs are in the plan. The canonical
MT50 Human Assistance terminal message was visibly corrected in Edge.

Continuous agent observation is still MISSING: Activity is a placeholder; the
current viewer requires an active human-control lease. Coding agents confirmed
no new observation files or partial implementation were created before interruption.
No more feature coding/tests/restarts are authorized by the current instruction.
All owned integration processes finished cleanup. Existing configured services
were not restarted; external Kafka credential use remains unapproved. Preserve
the entire dirty tree. The latest turn changes documentation only.

## Historical MT-000050 investigation before corrections (2026-10-17)

User requested research before further fixes after Sup_14 appeared to request HITL
without an interactive browser. Actual Edge at localhost5173 and local DB agree:
MT50 `65d770e5-ae0e-4283-b516-5caa046726f8` completed, ZERO human requests/leases.
Ordinary runtime discovery unconditionally creates a misleading human-authentication
bootstrap record. Flow counts it as a third case, shows Journey10000 and orders it
after execution. Human Assistance incorrectly says Waiting for the test on this
completed/no-request run. Both real cases only navigate public /product; no login
was reached. Saved screenshot shows Docs/Console links even though exact-name
visibility assertions fail; accessible-name mismatch is plausible, not proven.

No feature code changed during this research. Full details and ordered surgical
corrections: latest MT50 section in docs/ui/VERIFICATION.md. Viewer is existing
same-context volatile JPEG/input transport during a human lease, not an always-on
execution monitor.20 backend tests and10 UI tests pass; default Vitest fork startup
timed out, supported serial thread retry passed. Local services ports5173/8000/8020
respond. Fresh canonical visible handoff still needs verification after UI fixes.
No external replay/provider calls/real credentials/permission expansion performed.

## Previous checkpoint: runtime-only HITL implemented and locally verified (2026-10-17)

Ordinary New Test no longer asks for login/HITL identity setup. Newly frozen runs
enable runtime assistance: execute first, pause only on an observed challenge,
control the same live context within approved origins, then Done or Skip this
case/journey. Unknown identity stays unknown; permissions and frozen expectations
are unchanged. Anonymous session reuse is bounded to run/target/origin in memory.
Skip is durable, releases/fences control, records not tested and continues
independent work. Raw traces are disabled before unexpected authentication.

Actual local React/API/PostgreSQL/outbox/Kafka/Chromium/evaluation/report checks:
Feature Cases login/MFA/reconnect/resume/reuse passed; Feature Cases Skip produced
2 passed/3 blocked/1 human-skipped/2 budget-skipped and no invented findings.
Persona good and seeded-bad produced 3 passed and 3 failed respectively. Final
persona Skip run `ec311b6b-cfc2-4b3c-bd7d-41f98f876758` completed with one skipped,
two passed and a rendered persisted report. Scripted ADK drivers prove integration,
not live-model quality. Exact artifacts/commands/limits: `docs/ui/VERIFICATION.md`.

Found and fixed a real Skip finalization bug: rollback plus synchronized bulk
update left the cached TestRun expired; mark_completed raised MissingGreenlet.
The lifecycle repository now explicitly refreshes; worker completion logs use the
immutable accepted run ID. Actual PostgreSQL regression fails on the old method
and passes on the fix. Latest focused Python batches:52 +24 passed; focused
production Ruff/Pyright pass; frontend22 tests, typecheck/build pass.

Migration `6b0e2ac784d1` was tested on fresh disposable databases and applied to
the canonical loopback DB after confirming zero active runs; current reports head.
API/execution/evaluation and frontend still need restart. Do not run duplicate
workers/reset shared offsets. Full-project
Pyright is NOT clean (1209 errors across existing source/tests); focused checks
are the passing gate. External SSO/CAPTCHA/provider behavior and comprehensive
manual security/release verification remain open. No external target, provider
call, deployment, push or real test-account credential was used.

## MT-000048/49 corrections implemented and locally verified (2026-10-17)

Scope: surgical corrections, preserving all existing uncommitted work. Details,
commands, evidence and limits: `docs/ui/VERIFICATION.md`, latest section.

Follow-up browser review:18 rendered Chromium samples (6 states ×3 widths) passed
axe/overflow checks. Fixed New Test selector-label ordering and auth checkbox-caption
alignment; DOM geometry regression, TypeScript/build and complete good/optional-bad
persona UI-to-report rerun passed. Artifact `ui-integration-result-5e9f8ec536144816a9f980f0375ff87a.json`
under `.local/`; see verification doc for screenshot paths and provider-free limits.

- Explicit exact-origin scope revisions create a NEW pending target. Separate
  owner/admin authorization is required. Old targets and frozen runs stay unchanged.
  Additive migration `31d4ef097a2b` passed on disposable PostgreSQL and was applied
  to the canonical local database; no external origin permissions were changed.
- Persona and Feature Cases share configured required/optional authentication
  escalation, verified identity and run/target/identity-bound in-memory reuse.
  Independent review found a forced-handoff concurrency gap; publishing the pending
  challenge before releasing the browser lock and rechecking after acquisition
  closes it. Real Chromium concurrency regression passes without bypassing leases.
- Assertions use unique semantic targets/rendered normalized text; explicit
  `url_path_v1` compares origin/path in memory and persists only the frozen matching
  route or a fixed mismatch marker. Unsupported reads remain unverified. Frozen
  expectations/provenance are not rewritten. Documentation navigation classification
  requires actual DOM link metadata and a frozen authorized destination.
- Actual disposable React/API/PostgreSQL/outbox/Kafka/execution/HITL/evaluation/report:
  deep good run `d660c216` passed (3 satisfied/3 rejected-blocked/2 budget-skipped);
  deep seeded-bad `9dedb52d` passed (1 satisfied/2 failed/3 blocked/2 skipped,
  2 persisted findings). Persona required-good `255b2793`: 3 passed; optional-bad
  `e946d1ed`: 3 failed with real browser evidence. One verified login per persona run
  reused across its three isolated contexts. Reports rendered for all four runs.
- No provider/model calls or external application replays. Persona model is a
  scripted local ADK integration driver, not AI quality evidence. Existing canonical
  service processes were NOT restarted: restart API/execution/evaluation before
  manual use of new code. Canonical cloud Kafka connectivity is not certified here.

## MT-000048/49 policy and HITL investigation (2026-10-17, preceding evidence)

Detailed findings/research: docs/hitl/README.md, Latest investigation section.
MT48 legacypersona: 6journeys, 4blocked/1passed/1inconclusive. All four blocked
steps explicitly deny https://console.supermemory.ai; frozen scope permits only
https://supermemory.ai with subdomainsfalse. Both48/49 publictargets, noauthpolicy,
approvalsf disabled, nohandoffrequests. Legacytools persist/rethrow policyerrors;
no authentication handoff bridge. A viewer working locally is not universal HITL.
MT49 deepfeature: 0policyblocks, 2passed/2unverified/1unsatisfied. Overview locator
matches heading+navlink; mobile visible heading falsely absent because BR joins
DOM text forgets.The vs expected forgets. The. Saved screenshot/ARIA/trace reviewed;
offlineChromium reproduced text0/heading1 and overviewtext2/heading1. AgentURLquery
privacy yields unverified; fetch200+separate503 do not establish causality.

Found ordinary target create/UI supports only baseorigin, no additional-origin
management route; SSO field requires preauthorizedorigins. Research proposes exact
scope review separate from login, explicit authcapabilities/optional-auth, shared
persona handoff, better semantic selectors and a versioned safe publicroute oracle.
Keyword policy probes also deny benign payment-docs/invite-reference/removefilters;
not observed cause of MT48. No permission/data/application-code changes, modelcalls
or external replay. Documentation only; source+DB evidence independently reviewed.

## Final local HITL/readiness correction (2026-10-16 23:20 local)

See latest correction section in [product audit](PRODUCT_AUDIT_2026-10-16.md).
Run 485b5eae case agent_format_navigation failed `absent_scope`: missing region
Page format before link Agent. Target was public with no auth verification policy.
Also found all HITL env settings absent. Appended only missing loopback configuration
and generated matching internal key; no existing .env values replaced or printed.
Canonical API/execution restarted. API session 69780/PID49064; execution session
49864/PID16500. Viewer listens 127.0.0.1:8020; API/Kafka health200, unsignedlease401.
No active runs; don't start duplicate workers. Migration head f82e4160cb9d.

Implemented one bounded assistance attempt per case for missing/ambiguous semantic
controls during click preflight, with exact target/identity verification after
Release and policy recheck before the first dispatch. Generic assistance never
creates auth reuse state. Journey UI/API now expose typed assertions and safe
failure reasons; generic recovery is not labelled authenticated. Source Pyright
passed; Ruff passed with existing E501 baseline excluded; frontend build/typecheck
passed. Final HITL/API tests59+isolated PostgreSQL1 passed; real Chromium recovery4;
frontend6. Direct integrated generic recovery and existing login/cancel/expiry passed.
Full protected synthetic persisted pipeline passed again: artifact
`.local/ui-integration-result-456f1f5453c44a7e936ce3ce12853e18.json`, run64f8f663,
3passed/3blocked/2skipped, results409->200, report rendered, axe0, overflow0 at
1440/768/390. Disposable cleanup passed, shared Kafka offsets untouched. No model
calls or external target tests. Intermittent cloud Kafka SSL errors recovered;
post-fix model quality and arbitrary complexity escalation remain unverified/limited.

## Stale execution worker replaced (2026-10-16 22:40 local)

MT-000046 (`4a0b618c-9788-4ac6-8646-5d51a91d53ba`) inspected read-only:
failed 22:33:43 local, no started_at, plan, journeys or runtime snapshots; only
execution_failed/ValueError. Exact rejected output remains unavailable.
Confirmed no queued/running/awaiting-human runs, then stopped only verified stale
worker PID 36268. Started current code with the existing uv/.env command; fresh
process chain 28384/16604/15324 started 22:40:35. Kafka group generation 655 joined
and worker reported connected/waiting at 22:40:46. Startup and connection records
are present in `.local/temp-execution.log`. Intermittent broker SSL error occurred
during startup but connection recovered. Do not start another duplicate worker.

Verification: worker/planner tests 48 passed; logger regression 1 passed after
supported escalation resolved Windows pytest temp-directory permission failures.
No model calls, external target tests, failed-run replay, offset resets or DB writes
were performed. Source fixes are now loaded, but actual Feature Cases acceptance
after restart is not verified. Worker tool session: 28136. Keep it running for the
user's next authorized run; inspect safe persisted reason before changing policy.

## Temporary execution failure log (2026-10-16)

The Activity page is still a placeholder, and the execution worker only wrote
to the terminal that started it. The process serving Sup_10 started before the
reviewed-reason logging existed, so a failed run left no file. The worker now
appends start, completion, omitted-case, and failure records to
`.local/temp-execution.log`, flushed immediately. The failure record includes
the exception class, redacted message, and file/line stack. Credential-shaped
text is replaced. Restart the existing execution worker before the next run;
this does not rewrite MT-000045.

## Product audit checkpoint — 2026-10-16

Sup_10 investigation (MT-000045, `da2c121b-21ec-4710-8fdf-59322142dd0c`):
read-only local DB confirms failed, started_at null, zero journeys/runtime snapshots,
only generic execution_failed/ValueError event. Current execution process chain
11848/18568/36268 started 2026-10-15 18:27:06 local, before worker diagnostics
(20:52:21) and latest planner correction (22:50:48). Restart required; no process
was killed/restarted during investigation. Scope has one requirement, zero approved
oracles, four safe inputs, high depth. Model invoked after Kafka connection errors;
exact post-invocation ValueError remains unrecoverable from persisted data. No new
provider call, external browsing, or application code change during investigation.

Latest evidence and verdict: [Product audit](PRODUCT_AUDIT_2026-10-16.md).
Actual protected React/API/PostgreSQL/outbox/Kafka/execution/evaluation/report E2E
passed with three passed, three blocked and two budget-skipped cases. Separate
HITL integration passed disconnect/reconnect, Release without reconnect, verified
resume, auth reuse, cancellation, request expiry and lease expiry/reclaim.
Latest protected artifact: `.local/ui-integration-result-2f92558f57a449c5aced8f57e4931359.json`.

Bounded live planning comparison completed exactly twelve calls: two accepted plans,
two weak navigation checks, no evidenced seeded defects. No further provider calls
authorized under that allowance. Corrected default persona tool registry and
planner prompt/provider schema. Combined configuration/API/planner/evaluator tests:
90 passed, five dependency deprecation warnings. URL redaction false-pass correction:
12 assertion tests passed, Ruff/Pyright passed. Query/hash URL oracles now remain
unverified to preserve secrets. Post-fix live provider quality remains untested.

Canonical worker must restart to load source/.env changes. Historical run
`ac7fc095-a35e-4073-8d08-f539fc6422a5` saved no exact ValueError reason; approved
LangSmith trace detail inspection failed to load. Do not invent its root cause.
Verdict REFOCUS: structured caller-approved oracles and domain-safe inputs are
missing from ordinary Feature Cases knowledge selection. Preserve provenance;
do not solve this by allowing model-approved truth. No migration, push or deploy.

## Synthetic Feature Cases E2E passed after evaluator correction (2026-10-16)

Strengthened `.local/ui_local_integration.py --execute-fixture` and ran the actual
React -> Control API -> disposable PostgreSQL/outbox -> loopback Kafka -> execution
worker/Playwright -> evaluation worker -> report/results API -> React pipeline.
The first lifecycle-only smoke passed but did not inspect case verdicts. Adding
that assertion exposed `valid` as unverified: the executor recorded the planned
`registration_submit` action identity while the evaluator expected generic `click`.
The evaluator now checks `action_id or action` from the frozen case, keeping exact
ownership, order, observation, and artifact validation. Three regressions prove the
exact identity passes and generic/mismatched identities fail. Evaluator tests: 12
passed; production evaluator Ruff/Pyright pass. Optional journey typing and the
internally constructed assertion-list type were made explicit for strict Pyright.

Harness fixes: assert evaluated case verdicts and artifact-backed assertions;
exercise Low/High/Medium selection and verify submitted Medium; check actual
six-case execution cap and two budget skips; count only the case-list buttons
(evidence controls caused one intermediate harness false failure); require approved
receipt counts to match decisions and rejected runs to have zero receipts;
propagate evidence-capture/check failures after cleanup; reject no-worker mode
immediately instead of waiting for a run that cannot execute.

Final passing evidence:
`.local/ui-integration-result-2d41da33ee0b4c91899a18ce6911ed14.json`.
Approved run `cc1874cb-6d01-4a49-bdfa-9372637daaf3`: 6 executed/6 passed,
0 failed assertions/blocked/inconclusive, 2 case-budget skips; five approvals
consumed with five completed receipts. Rejected run
`57f31eab-142b-407e-ad31-11d9d67a0b27`: 4 blocked/2 passed/2 skipped,
four rejections and zero receipts. All duplicate decisions returned HTTP 409.
Before evaluation results returned the expected HTTP 409; after evaluation both
returned HTTP 200. React rendered the report and eight case rows. Owned database,
MinIO container, subprocesses, and browser artifacts were cleaned up. Shared Kafka
consumer offsets and unrelated resources were preserved.

Frontend build now PASSES with local child-process permission (584.52 kB JS,
89.96 kB CSS; existing chunk-size warning). The four focused FeatureCases Vitest
tests pass with `--pool=threads --maxWorkers=1`; the default forks worker timed out.
Previous sandbox EPERM/native-module build blockers are superseded by this result.
Planner/worker/shared/API suite: 68 passed; the five real ADK boundary scenarios
were also rerun after the final test edit and passed. These do not prove live LLM
planning: the E2E uses the explicit fixture plan and no paid provider; protected
viewer/MFA scenarios were not rerun in this quick smoke. Historical `c6cb14af`
root cause remains unknown. Restart the user's execution/evaluation workers and
Control API to load changes before a new live run; canonical services were not
restarted and failed historical rows were not rewritten.

## ADK response boundary verified and reasoning extraction fixed (2026-10-16)

Checked the installed ADK source and exercised the actual `Runner` through
`generate_feature_plan`, retaining the production agent factory and output schema.
Only model responses and database I/O were substituted. With no `output_key` or
tools configured, this ADK flow does not Pydantic-validate the final response
before our parser: a mixed valid/malformed response reaches the parser and saves
seven valid cases; all malformed cases fail closed with a reviewed field reason.
The proposed output-schema bypass defect was not reproduced in this configuration.

The same tests reproduced a different defect: final response extraction included
ADK `thought=True` parts, so reasoning text preceding valid JSON caused a JSON
decode failure. Extraction now consumes only final answer text. Thought-only or
empty responses report the reviewed missing-candidates reason; malformed JSON
reports a new fixed, allowlisted invalid-JSON reason without keeping response text.
This newly reproduced defect does not establish the historical `c6cb14af` cause.

Verification: 68 focused tests passed across feature planning (including five real
Runner boundary scenarios), worker failure recording, shared safe diagnostics,
and the feature API. Four existing ADK deprecation warnings. Ruff passes for the
planner and its tests; shared diagnostics has three pre-existing E501 lines and
passes with that baseline excluded. Focused Pyright passes. No paid model call,
external browser run, service restart, or historical database rewrite was made.
Live provider planning/execution and prior frontend environment blockers remain
unverified; restart the execution worker and Control API before the next new run.

## Failure reasons are now logged and stored (2026-10-16)

Run failures previously persisted only an exception class and a fixed category
message, so a `ValueError` during case validation could not be distinguished
from any other pre-plan failure. The worker log now records the exception
class, the raising file and line, and a reviewed reason. The same reviewed
reason is stored on `run.failed` and appended to the Feature Cases failure
text. Provider bodies, secrets, and raw validation input stay omitted.
Individual generated cases that fail schema or safety checks are logged with
the case index or id and the reviewed rule, including when other cases are
kept. A restarted execution worker and control API are required before the next
run. Focused tests: 63 passed. The previous run
`c6cb14af-80a0-4578-8cdd-69244a3474a7` was not rewritten.

## Feature Cases depth selector fix (2026-10-15)

The New Test page had the depth selector disabled in Feature Cases mode, leaving
the default Medium value visible and preventing user selection. The control is
now enabled in both modes. Feature Cases maps Low/Medium/High to maximum case
budgets of 3/6/8; explicit `feature_budget.max_cases` values remain authoritative.
Verification: `test_testing_depth.py` passed (9 tests); web TypeScript typecheck
passed. Web build and Vitest could not start because Vite's config loader failed
with Windows `spawn EPERM` and Tailwind Oxide's native module emitted invalid
UTF-8. Full build/test verification remains blocked by the local Node process
environment, not by an assertion failure.

## Latest Feature Cases failure after planner response (2026-10-16)

Read-only local PostgreSQL inspection found run
`c6cb14af-80a0-4578-8cdd-69244a3474a7` failed with `ValueError` and the generic
safe category `execution_failed`. It has no persisted `test_plan.created` event,
journeys, or executions, so the failure occurred before browser case execution
and before the plan transaction committed. The allowlisted diagnostic deliberately
does not retain the exception detail; therefore the precise raising line cannot
be proven from this run. The worker received a final model-planner response per
user observation, but that response was not persisted and was not replayed.

Updated candidate selection to reject a policy-invalid generated case while
retaining unrelated candidates that pass all caller-owned authorization and
safety checks. Rejected cases add a generic coverage gap. Duplicate IDs still
fail, unsafe candidates are never executed, and a plan with no safe candidates
still fails closed. Regression coverage checks both mixed valid/unsafe and all-
unsafe candidate sets. Combined focused backend suite: 42 passed; Ruff passed;
focused Pyright reported 0 errors. The web typecheck passed; Vite build and
Vitest remain blocked on local `spawn EPERM`/Tailwind native-module loading.
The worker must restart before the fix is loaded. A new run is needed to verify
planner response acceptance and browser execution against the user's target.

## Feature Cases planner correction (2026-10-15)

User requested testing and fixing the Feature Cases failure. One bounded
provider-backed reproduction used the saved public Supermemory page observation
and frozen Sup_2 scope (test 33), with one model call, retries disabled, no
browser, no external site access and persistence stubbed. The LLM returned a
candidate response, but Pydantic rejected `cases[1].expected[0].target` with a
custom semantic-target validation error; its expectation list then fell below
the minimum. This isolates the observed failure to malformed structured planner
output, after successful provider authentication. A separate synthetic `example.test`
planner call produced two valid cases; no browser or database writes occurred.

Changed the Feature Cases planner instruction to state the selector and oracle
target rules explicitly. Added candidate-level schema parsing: malformed cases
are omitted, a fixed coverage-gap note is added, and the existing strict scope,
action and plan validators still govern every retained case. Planning still fails
closed when no schema-valid case remains. This preserves useful valid cases when
one generated item violates the Pydantic model without relaxing execution safety.

After the prompt wording update, a saved-evidence planner invocation reached the
configured provider but returned HTTP 500 before a response. It happened before
the candidate-level parser fix, so provider-backed acceptance of that fix remains
unverified. The focused regression models the observed invalid
semantic target and verifies valid cases survive while all-invalid output fails.
`test_feature_case_planner.py`: 31 passed (5 warnings, including existing ADK
deprecations and a pytest-cache permission warning). Ruff passed and focused
Pyright reported 0 errors. No external target was opened and no DB was changed.
Restart the execution worker to load the code, then submit a new Feature Cases
run; the previous failed run is unchanged. The original run ID was not present
in the local database used for read-only inspection. Kafka heartbeat expiration
and the subsequent offset commit failure were separate transport events.

## Replacement LLM key verified (2026-10-15)

User requested one new check after replacing the key. Actual scripts/check_llm.py
run in fresh uv --env-file.env process SUCCEEDED: configured openai/gpt-6-luna,
received_texttrue, reply_is_oktrue, finish_reasonstop. One fixed short prompt,
256completion-token cap,no retries,no key output,no production target access.
This proves current key/model completion works; full feature planning/execution
was not rerun. Restart existing execution/evaluation workers to load the new key
before starting a new feature run. Earlier401 evidence is historical, superseded
for the current key by this successful completion; failed runs remain unchanged.

## Reusable one-call LLM diagnostic (2026-10-15)

User asked to write small code and call the LLM after key change. Added
scripts/check_llm.py: same configured model/key precedence, fixed ReplyOK prompt,
256completion-token cap,0retries, bounded timeout, no content telemetry or secret
output. Actual one generation request from uv --env-file.env FAILED HTTP401,
AuthenticationError for openai/gpt-6-luna. No output was generated; no production
site was browsed. Earlier metadata probe in interrupted tool never launched due
automatic approval-review timeout; did not issue a second network request.
Do not infer key validity or feature-plan success. User must correct configured
MODEL_API_KEY privately. Reusecommand: uv run --no-sync --env-file.env python
scripts/check_llm.py. Do not repeatedly rerun paid requests without authorization.

## Fresh model API connection test: invalid_api_key (2026-10-15)

User requested API connection test. One authenticated model-metadata GET for
gpt-6-luna via fresh uv --env-file.env process and selected MODEL_API_KEY returned
HTTP401 AuthenticationError, providercode invalid_api_key/typeinvalid_request_error.
No generation request, token output, model planning, production browser or retry.
Key value never printed. This confirms provider rejection in a fresh process,
so restarting alone will not resolve the currently configured invalid key.
User must privately correct MODEL_API_KEY for the configured provider/endpoint.
Model availability and completion remain unverified because authentication failed.

## MT-000035 Sup_4: stale worker configuration (2026-10-15)

Readonly DB:0310df66-c044-43f7-81f1-bbc5d385db44/test35 Sup_4 failed22:41:25UTC,
started_atNULL,no case executions or run.failed event. Active local execution
worker chain uv41688/python28904/python9544 started16:58:01local. Root.env
updated17:39:57; worker diagnostic source updated17:23:18. The running process
predates both key update and failure-reporting patch; root.env edits cannot
replace its inherited process environment or imported code. No provider call was
made to test the replacement key; its validity is still unknown. Newly launched
read-only config probe selects MODEL_API_KEY matching root.env; no key printed.
User must Ctrl+C/restart the existing execution worker (not launch a second one),
with localhost9092/PLAINTEXT overrides, to load updated MODEL_API_KEY and safe
failure reporting. Restart API for new diagnostics endpoint response as well.
No processes stopped, no queued run executed, no production navigation, no DB
mutation, and no additional paid call occurred in this investigation.

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

## MT-000033 Sup_2 investigation (2026-10-15)

User reports Feature plan failed /0cases /Collector notstarted. Read-only local
DB: run7b5afaef-af69-473f-8581-84ce25564bda, deep_feature_v1, created22:11:20UTC,
failed22:11:53UTC, started_atNULL,0journeys/agentexecutions/runevents/runtime
snapshots. Frozen scope exists; offline build_run_request/scope/budget validation
passed. No predefined featureplan/auth prerequisite/fixture effects configured.
A contemporaneous local discovery trace under artifacts/runs/87a39343-fece-4e56-
90b5-d67fba730add records supermemory.ai/product documentHTTP200 and navigation
screenshot at17:11:34local; no trace Playwright call errors. This supports initial
navigation succeeded before planning/persistence failed, not a failed case/product
assertion. The worker rolls back planner snapshots and logs only exception type;
no exact historical planner exception was persisted. Current.env model resolves
openai/gpt-6-luna; no provider request/credential check was made and that model's
availability or exact running-worker configuration is not established.
Asked user for worker failure line for this UUID. Root cause remains unconfirmed
pending that log (provider/auth/rate/structured output validation cannot be
inferred from zero cases alone). No production rerun, external browse, model
call, database mutation or feature source change performed during investigation.
Synthetic fixture passes do not establish real model-generated feature planning.

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

## Duplicate Vite listener resolved (2026-10-15)

After correcting CONTROL_API_PORT, login still failed because two MarketTwin
Vite processes bound5173: stale PID21796 on127.0.0.1 and newer PID57404 on0.0.0.0.
The specific loopback listener intercepted requests, returning502. Verified the
stale PID's listener, node executable and repository Vite script immediately
before stopping only PID21796. API56592 and newer Vite remained running.
Afterwards both localhost:5173 and127.0.0.1:5173 proxied GET /api/v1/me ->401 and
empty-body POST /api/v1/auth/local/login ->422 from Uvicorn, matching directAPI.
No real account login attempted; user should refresh and retry their approved
identity. No auth bypass, database mutation, or credential use was needed.

## Local login proxy correction (2026-10-15)

Reproduced login-service unavailable as Vite GET /api/v1/me HTTP502 on both
localhost and127.0.0.1:5173. Direct API8000 /health returned200 and /api/v1/me401
(expected unauthenticated); API8001 had no listener. Root.env CONTROL_API_PORT
was8001, while user started Uvicorn8000. Changed only that exact nonsecret setting
to8000, preserving every other .env byte. Restart Vite to load the corrected
proxy; no auth/account changes, credentials, or session creation were needed.
Post-restart login success remains for the user to verify; no real login attempted.

## Local Kafka startup diagnosis (2026-10-15)

API /health returned200/statusok; / and /json/version are undefined routes,
so their404 responses do not indicate failed startup. Effective root.env selects
a non-loopback Kafka broker with SASL_SSL; local Docker Kafka is healthy and
read-only localhost:9092 metadata inspection succeeded (advertised localhost9092,
node1). This explains why local startup still attempts remote broker connections;
the precise remote timeout/network cause was not investigated or contacted.
No environment file or running process was changed. For local manual testing set
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 and KAFKA_SECURITY_PROTOCOL=PLAINTEXT in
each API/execution-worker shell before the existing uv --env-file command, then
restart those processes. Saved cloud credentials remain private and unchanged.
No messages were produced/consumed and no offsets changed by this diagnostic.

## End-to-end integration checkpoint (2026-10-15, final)

Requested synthetic local integration is verified; existing UI and user changes
are preserved and uncommitted. Five surgical fixes: missing-run Kafka delivery
acknowledgement; successful claim viewer_available contract; active-lease-only
assistance listing (reclaimed historical leases no longer duplicate rows);
privacy-safe browser close during cancellation; expired vs cancelled abandonment.
No authorization, exclusivity, generation or credential protections were relaxed.

Full protected React/API/PG/outbox/Kafka/execution/evaluation/report/React PASS:
run 98009f92-ee63-4a20-bcc7-b2580c155159,
report 9f4fcf74-5f4c-4cb3-9b1e-2d2069dd24ac completed and rendered.
One same-context login/MFA, disconnect/reconnect/Release, seven later fresh-case
snapshot installations and role reverifications. Eight cases: four completed
(recorded satisfied), four intentionally policy_blocked (recorded unverified).
React approved valid only: one completed receipt and exactly one registration;
four React rejections had no receipts; all five duplicate decisions HTTP409.
Results HTTP409 explicitly evaluation-pending ->200 after report persisted.
Report no overflow at1440/768/390, axe0. Safe metadata:
.local/ui-integration-result-f99b0ece11294e5ea9ba9c1d8657f646.json.

Independent live auth boundary additionally passed pending Cancel, successful
MFA then disconnected Release without reconnect, natural request expiry, real
lease expiry/stale input denial/reaper/fresh claim. No credential-phase captures.
Public complete pipeline passed earlier (see docs/ui/VERIFICATION.md for IDs).
An earlier evaluator stall reached observability init; explicit-off retry passed;
no precise evaluator/observability code defect established. Local telemetry-off
instructions documented; no error-suppression fallback was added.

Final focused backend85passed (4 existing ADK warnings,109.31s); real PostgreSQL
repository/approval/lease-list regression1passed35.39s; final API contracts11pass;
focused pending/ready/permission desktop/mobile UI+axe8pass. Frontend typecheck/
build passed; strict changed-source Pyright0; scoped Ruff passed excluding E501
and an existing ASYNC110 polling-test finding; diff whitespace check passed.
Counts overlap. Historical full mocked UI107pass/7skip remains below.

No source migration/new service. Existing application DB unchanged at
d7f3c2a9b108; manual startup needs upgrade to f82e4160cb9d. Disposable DBs and
exact UUID-owned local services/MinIO/artifacts cleaned. Shared Kafka offsets,
topics and unrelated messages unchanged; earliest private groups drained stale
missing-run deliveries safely. Ordinary worker must share API/outbox canonicalDB.
A human wait still occupies the single execution consumer; lost browser fails
closed, no distributed recovery. No push/deploy/spend/real-account use.
All specialist implementation/review work finished. No new redesign or rewrite.

Remaining: authorized production proxy/SSO/CAPTCHA, live process interruption,
full integrated canary sweep, manual assistive-tech/cross-browser and H12 release
certification. Hosted production remains NO-GO. Exact evidence, changed files,
startup commands and manual flow: docs/ui/VERIFICATION.md, docs/hitl/README.md.
Historical checkpoints below retain prior outcomes and are superseded where
explicitly updated by this final checkpoint (including Aiven probe disclosure).

## UI redesign checkpoint (2026-10-15)

Primary specification: root MARKETTWIN_UI_REDESIGN_RESEARCH_CODEX_MASTER_SPEC_2026-10-15.md.
Baseline: feat/batch-1-aws-observability, HEAD 339a4b3; only the supplied spec was
initially untracked. Existing HITL implementation and all user work are preserved.
Four agents implemented/reviewed exclusive shared-shell, page, run/HITL and test
scopes. Quiet Precision light UI, existing fonts, accessible responsive drawer,
action-required navigation, three-zone creation, case/finding inspectors, bounded
evidence, role-safe HITL and local-only lease secrets are implemented. Actual
rendered desktop/tablet/mobile review found and corrected contrast, focus, viewer
width, case-list height and content-hierarchy issues. Dark mode is deferred.

Final unified frontend Playwright: 107 passed, 7 intentional skips, 0 failed /114
(two workers). Unit suite: 42 passed; affected case tests rechecked after final
visual changes. Typecheck/build passed; JS 584.33 kB, CSS 89.67 kB. Local synthetic
backend browser/auth/approval suite: 47 passed; disposable PG lifecycle/migrations:
2 passed. Real UI/API/disposable-PG login/session, app/loopback-target creation,
authorization, draft and logout smoke passed. Additional shell reflow/axe checks
at 1280x800 and 1024x768 passed. API-mocked UI tests are not full-stack proof.

The application's DB remains d7f3c2a9b108, not upgraded; source head is f82e4160cb9d.
A cached local Kafka was started. Final isolated synthetic run
fcf0f1b1-6fdd-4124-8122-1ca628ea50aa consumed/committed its request and
reached completed. Its immediate results request returned non-2xx without a
retained status; evaluator/report readiness remains unverified. An earlier
nonisolated attempt timed out queued, with later ValueError in request
acceptance; old commands for deleted disposable DBs are plausible, not proven.
Default Kafka state was not reset; retained test commands can interfere with
ordinary manual startup. UUID test-group offsets were isolated. Temporary DBs,
owned workers and browser artifacts were removed. Full protected browser
login/MFA and release/reconnect end-to-end, manual assistive-tech review, field
performance and H12 release certification remain unverified. See docs/ui/VERIFICATION.md
for scope, exact changed files, safe screenshots, commands and the disclosed Aiven
health-probe incident. Subsequent test runners pin loopback Kafka and clear SASL.
No external application test, provider/model call, deployment, purchase or push.

# Current MarketTwin checkpoint

## Latest HITL integration correction (2026-10-14)

Review of commit 0682c375 fixed viewer disconnect/Release generation ordering,
durable revoke redelivery, fresh-ticket reconnect and invalid lease-token
reflection. Database authority and strict generation fencing remain intact.
Focused regressions passed, including real local PostgreSQL, signed API/worker
traffic, Playwright authentication/resume and a disposable full migration
roundtrip. Frontend typecheck/build, strict backend typing and scoped lint passed.
Application DB untouched. Pending human assistance occupies the single execution
consumer and queues later runs; no infrastructure redesign was introduced.
See [the HITL guide](hitl/README.md#essential-checks) for exact check results,
startup/manual-test instructions and remaining comprehensive E2E/H12 verification.
No external applications, real credentials, paid calls, push or deployment.

## Current HITL documentation

All current HITL details and preserved original requirements are consolidated in
[the HITL guide](hitl/README.md). It includes implementation status, architecture,
setup, migrations, tests, limitations, manual verification and historical evidence.
Six superseded HITL documents and three generated HITL debug directories were
removed after consolidation. Regression tests, fixtures and unrelated project
files are retained. Comprehensive E2E/release verification remains unexecuted.

## Active MKT implementation checkpoint (2026-10-14)

The user directed implementation to proceed autonomously and authorized the
existing approved Supermemory target. Deep feature mode, shared plan/result
contracts, browser scope/assertion actions, case execution/evaluation, case APIs,
and result UI are implemented in the working tree. Fixture runs have persisted
real browser evidence; the latest recorded eight-case good run passed 8/8 and the
bad run reported six failed assertions before source-declared root grouping was
added. Live UI verification confirmed owner auth, eight cases, exact MinIO
screenshot retrieval, and no horizontal overflow at desktop/mobile widths.

Supermemory public product-page testing is limited to recorded public navigation
and read-only inspection. A model-planned run stopped at HTTP 401 from the
configured OpenAI provider. A frozen, explicitly authored eight-case navigation
run produced three passes, one blocked, one inconclusive, and three failed inferred
URL assertions; those inferred mismatches are not confirmed product issues and
need inspection. The Console path remained blocked as out of scope. No login,
memory API, or account operation was attempted.

This continuation corrected the deep-mode flow panel, which had labeled the
deterministic feature cases as a Sequential Agent. Frontend TypeScript check passes.
The API/worker queue is not verified because Kafka is unavailable; no model
quality matrix or multi-application T10 evidence exists. Do not claim model
autonomy or release readiness. The existing workspace deletion of
MARKETTWIN_KNOWLEDGE_WORKER_UI_BRIDGE.md and untracked
docs/hitl/README.md (Appendix A: original master plan) predate this
continuation and were preserved.

## Latest checkpoint: new MKT deep-testing plan (2026-10-14)

The user requested detailed analysis of the new root MKT.md and implementation,
then explicitly requested multiple engineering agents working in parallel.
Three agents delivered independent T00/T01 work; runtime journey execution remains
sequential. See docs/agent-quality/IMPLEMENTATION_ROADMAP_2026-10.md for all T00–T13
assignments, dependencies, current-code discrepancies and acceptance gates.
This new task numbering supersedes the older TASK00–09 sequence below for this work.

T00 baseline is recorded in docs/agent-quality/BASELINE_2026-10.md and its sanitized
failure matrix. Branch/HEAD still match the MKT audit, but the dirty workspace has
newer planner/persona budgets (4096/2048), report validation, failed-action capture,
exact evidence linkage and journey API/UI. These existing changes were preserved.
Read-only historical DB inspection failed ConnectionRefusedError; live remote HEAD
was not fetched. Historical detection counts remain unvalidated, not fresh metrics.

T01 implemented a separate deep_testing_app fixture, independent versioned manifest,
and run_deep_fixture_benchmark.py. Eight core cases cover valid/invalid/boundary,
dependent controls, recovery, async state and navigation. Good/bad variants share
the feature; bad produces six case contradictions (not six independent root bugs).
The existing historical v1 fixture remains intact. The historical live benchmark
CLI now requires --local-development. New direct runner starts ephemeral loopback
only, isolates cases, restricts network/service workers, and writes actual values,
hashes, screenshots and JSON/Markdown. See docs/agent-quality/FIXTURE_BENCHMARK.md.

Verification: 75 focused existing backend tests passed; 15 final combined new
fixture/scoring tests passed (9 real Chromium +6 scoring/CLI). Ruff and strict
Pyright across four affected Python files pass with zero errors. Fresh frontend
typecheck/build and 27 unit tests pass; existing 544.84 kB bundle warning remains.
Direct good/bad runner executions each complete 8/8 cases with 8/8 ground-truth
agreement. Generated evidence is .local/deep-fixture-good and deep-fixture-bad.
Three diagnostic probes explicitly remain not_executed in runner output; fixture
tests separately verify policy/probe states. No fresh autonomous pipeline/model
run, dependency install, migration, commit, push, deployment or public target test.
Whole-workspace git diff --check still flags pre-existing trailing whitespace in
agents/schemas/plan.py; this session did not change that file.

T02–T08 and the minimum T11/T12 surfaces are now implemented in the working tree.
Versioned feature plans, scoped inspection, safe check/focus/viewport actions,
deterministic assertions, sequential case execution, assertion-aware report
diagnostics, assertion-grounded findings, case/step read APIs, and the feature-case
result panel exist. A recorded result stays unconfirmed until evaluation. This
session added budget skip accounting, repeated read-only assertion checks, report
contradiction diagnostics, case pagination/steps, and pending-result UI copy.

Verification on 2026-10-14 after those additions: 72 focused planner, assertion,
report, evaluator, and case-API tests passed on recheck, including real Chromium
assertion checks. Feature-case UI tests previously passed 2. The report boundary
now reads assertion JSON stored on assertion steps; a contradictory persona pass
becomes inconclusive. Ruff is clean on the new production modules. Strict Pyright
reports no errors in the changed production modules.
Pre-existing long lines in control-api case tests and deep_run.py were left
unchanged. No model experiment, authorized external application, migration,
commit, push, or deployment was run.

Ordinary deep runs now freeze the validated feature scope into the run snapshot
before execution. The evaluator still confirms a finding only when that same scope
contains the matching requirement assertion. Inferred expectations stay
unconfirmed. Case action rows use the persisted step status, and failed-assertion
counts count individual checks. Deep mode remains opt-in, and the executor remains
deterministic until an accuracy benchmark justifies bounded recovery.

Still open: T09 has no measured model/budget winner because no paid model matrix
was run. T10 has no reviewed form, list/filter, and navigation proof on authorized
applications. T12 has no live backend-to-browser participant trial. T13 release
checklist remains NO-GO. The deterministic case executor is not a claim that an
LLM persona performed observe–act–assert. Fixture truth still cannot be enabled
merely by a configuration snapshot. Do not rebuild already implemented evidence
pages or infer that previous local services are running from stale PIDs below.

Updated 2026-10-10. This is the authoritative current state. Historical decisions
and superseded checkpoints remain in SESSION_HANDOFF.md and V1_BENCHMARK_RESULTS.md.
The user's latest direction is build everything requested, then test/benchmark;
do not return to the earlier detection-before-UI instruction.

## Implemented

### Revised SAM architecture documents (2026-10-12)

Created docs/sam-v2/README.md, ARCHITECTURE_V2.md, RUNTIME_CONTRACTS.md and
BUILD_AND_VALIDATION_PLAN.md in response to the user's request for new architecture
docs. They carry forward the under-$20 operating constraint, proposed $19 envelope,
existing hardware first and later Mac mini migration. They define bounded helper
delegation, verification/repair, durable execution and separately evaluated GEPA.
Phone/SMS remain full-V1 requirements with cost-gated staging. These are design
documents, not an implemented or integration-tested SAM system.

### SAM budget and later hardware decision (2026-10-12)

User explicitly requires V1 operating costs under $20/month and plans to buy a
Mac mini later. This supersedes the earlier $100 recommendation below. Updated
the comprehensive SAM audit with a provisional $19 total envelope, existing
hardware first, no automatic spend increase and measured Mac migration/sizing.
Web-first staging and later phone/SMS are recommendations, not an approved
deletion of full-V1 channel requirements. No purchase or implementation started.

### Separate comprehensive SAM audit (2026-10-12)

Completed docs/sam-audit/SAM_ARCHITECTURE_AUDIT_2026-10-12.md in the user's
requested 14-section order, with 20 provisional ADRs, requirement traceability,
primary-source research, cost assumptions and 12 pending integration experiments.
User requested recommendations for unspecified constraints: existing hardware,
32 GB/1 TB planning target, three bounded workloads and $100/month pilot cap.
Two isolated stdlib/SQLite mechanisms were executed with negative/control variants:
lost-receipt replay duplicates without receiver deduplication; ten forced budget
races overspend without atomic admission and stay within budget with it. Source
and raw results are in docs/sam-audit. These are not SAM/PostgreSQL runtime proof.
Verdict: conditional go for bounded prototype; no production-readiness claim.
No application code, infrastructure, account settings or services were changed.
The existing MarketTwin plan remains unchanged.

### Separate SAM plan assessment (2026-10-11)

Reviewed the user's attached SAM_MASTER_PLAN_V1.md as a separate design request.
See SAM_PLAN_REVIEW_2026-10-11.md for feasibility findings, bounded delegation,
evidence-driven repair, GEPA/GA/RL assessment, and 36 proposed adversarial tests.
This was a document review with primary-source research, not a SAM runtime test
or implementation. No MarketTwin application code or running services changed;
the existing MarketTwin execution sequence remains unchanged.

### Agent prompt 500 fix and temporary output cleanup (2026-10-10)

MT-000024 completed, but its prompt endpoint rejected aliases generated by its
own YAML serializer because recorded structure and rerun configuration shared
an object. PromptYamlDumper now expands shared values without aliases, including
the internal validation serialization. Strict rejection of user-supplied aliases
remains. All24 prompt regressions pass; Ruff/Pyright pass. A read-only invocation
of the endpoint with Sup_1's real records returned9 agents successfully. API
restarted PID33564/session29762; health is OK.

At the user's request, removed95 generated testing files: one-off .local probes,
benchmark diagnostic exports/logs/screenshots, pytest temporary directories,
Playwright result output, artifacts/v1 UI screenshots, and web/debug.log. Kept
regression tests, benchmark harness/fixtures, reference docs, artifacts/runs,
database/object-storage records, dependencies and Kafka data. Future agents must
not rely on deleted .local diagnostic scripts.

### Queued test dispatch diagnosis (2026-10-10)

Live checks for MT-000024 (Sup_1, run31619f3d-64f4-4519-a3c9-c3cd7f642a30)
showed Kafka health connected and run.requested already published with zero
failure attempts. Earlier SSL logs were not the current blocking condition.
No execution worker was running. The execution worker was restored using the
existing .env (session64769) and connected successfully to its Kafka consumer
group. MT-000020 started running first; MT-000024 remains queued behind it in
normal sequential execution. Evaluation worker was also started (session25432).
Do not replay the command, bypass the queue, or label MT-000024 running before
its persisted status changes. Kafka connectivity alone does not prove worker
availability or completed end-to-end reporting.

### Link ingestion outage and browser research (2026-10-10)

The knowledge worker was offline on8010. It is restored; a real synthetic preview
generated knowledge/skill. Both identified failed local link entries were retried
and now need review, with4/6 proposed skills and no processing errors. Nothing was
approved. Link research now renders JavaScript, expands read-only navigation and
discovers same-origin pages recursively, bounded to30 pages/120 seconds. It saves
URLs, observed text/actions and coverage gaps through existing draft ingestion.
14 link regressions pass, including real Chromium JS/disclosure/deep-link checks;
Ruff/Pyright, frontend typing/build pass. See LINK_BROWSER_RESEARCH.md for details.
Final focused link/client/processor/ingestion suite:44 passed. Ingestion form
unit tests:8 passed. No unrelated benchmark was rerun.
Current API PID21100/session59212; worker PID34236/session44162. Kafka SSL remains
a separate unresolved gate. Successful retries used saved source bundles; they
do not prove upgraded browser coverage of the user's original sites.

### Meta-generated coverage clarification (2026-10-10)

Meta's prompt and input blueprint now prioritize application-specific end-to-end
flows with distinct persona behavior, recovery/final-state checks and coverage
gaps. Output budget is 4,096 instead of 1,024. Existing models are reused; runtime
agents remain created from Meta's actual persona/mission plan. New structural
validation and mandatory guidance for edited prompts were added. Focused suite:
38 passed; actual model/browser quality validation remains pending. Read
META_PLANNING_BLUEPRINT.md before claiming comprehensive or improved live coverage.

### Latest prompt/flow correction (2026-10-10)

The user resumed prompt/flow implementation after the ADK research. Agent Settings
now shows Meta -> Sequential Agent (recorded journey subagents) -> Collector ->
Evaluation and Report. Prompt settings are YAML-only; the separate form is removed.
Flow panels scroll internally on desktop/mobile and long historical names wrap.
The real outer ADK runtime uses a SequentialAgent journey group, with no LoopAgent
or custom dispatcher. Only sequential containers hold children in that workflow.
Eight runner regressions pass, including no overlapping executions and rejecting
over-depth plans before browsing. Existing per-journey evidence ownership, durable
collection, failures/timeouts, and reporter-author checks remain intact.

Validation: 44 focused backend checks passed before the added depth test; the
updated workflow suite then passed all 8 checks. TypeScript, runtime Pyright and
Ruff pass. All four focused desktop/mobile prompt + run-flow browser checks pass,
including YAML save/reset/rerun, accessibility and internal scroll styling. The
previous mobile Save interception is resolved. Production build passes; its
existing large-chunk warning remains (544.75 kB JS).

The compatible rerun YAML schema is retained: sequential configuration fields
provide defaults for the implicit reporter, with separate settings on extra LLM
children. A migration to explicit reporter-child-only fields remains a separate
schema change; do not claim native ADK YAML or a completed Workflow SDK migration.
See ADK_AGENT_STRUCTURE_RESEARCH.md for primary sources and current decisions.

- Evidence integrity: repeated persona claims remain Needs Verification, retain
  persona/journey/criterion/step references, never raise severity or confirmed
  totals merely through repetition. Browser evidence is required for confirmation.
- Authorized journey list/detail API: latest attempt, ordered paginated steps,
  bounded artifact metadata, safe summaries, linked classified findings. Exact
  selected-step evidence only; no unrelated screenshot fallback.
- Premium public homepage, comprehensive How page, accessible finite motion and
  reduced-motion support, working login routing and shared warm/forest theme.
  Workspace navigation and pending-evaluation messages have been simplified.
- Optional short test name and PostgreSQL identity number displayed as MT-000042.
  Full goal remains in test configuration. Identity migration f2a931c64780 is applied
  to the local DB; existing rows backfilled. Concurrent insert/backfill check passed.
- Agent Settings: project/application -> tests -> ordered per-test agent flow.
  All recorded roles are visible, including read-only evaluator/visual verifier.
  Planner/persona reruns support custom names, LlmAgent/SequentialAgent, low
  temperature (default 0.05, bounded 0?0.2), approved tools, and up to three extra
  LLM children before the structured reporter. Real ADK trees and full child
  settings are snapshotted; only primary reporter final events are parsed.
  Historical snapshots remain immutable. Requested/effective temperature are
  distinguished when a reasoning model controls sampling itself.
- Public link knowledge ingestion: bounded HTML/text research (up to five pages),
  source URL/content preservation, draft knowledge/skill generation through the
  existing pipeline, explicit review/approval. Public IP validation, pinned
  connections, redirect checks, TLS identity, byte/time/page limits. No arbitrary
  tools or automatic skill approval.
- Evidence access repair: API was signing local MinIO links with ambient AWS
  credentials instead of configured .env credentials (403 InvalidAccessKeyId).
  Configured signer/storage credentials now produce HTTP 200 image/png; local
  screenshot probe returned 39,059 bytes. Same fix covers knowledge source access.
- User screenshot showed long historical names covering the settings form.
  Agent grid items now allow shrinking and names wrap inside cards/headings/tree.
  Desktop/mobile long-name browser regression is being finalized.

## Validation and benchmark

- Journey API: 22 passed. Naming/create/knowledge API: 15 passed. Local PostgreSQL
  identity concurrency/backfill: 1 passed. Frontend units: 26 passed before adding
  one link test; targeted ingestion suite now 8 passed. Production build passed
  (existing ~547 KB JS chunk warning remains). Frontend typecheck passed.
- Public/results browser suite: 22 passed. Main/knowledge fixes: 11/12 then remaining
  mobile knowledge passed. Updated project/test agent and knowledge flows: 4 passed.
  Sequential subagent desktop/mobile and axe checks: 2 passed. Final long-name
  regression is in flight; see NEXT_SESSION.md for process/session status.
- Backend final suite: 405 passed, 4 skipped, one outdated expected visual-agent
  name. Expected name was updated to Agent_VisualVerifier_1; focused snapshot suite
  passed 2 tests. Earlier final focused feature/evidence suite: 92 passed.
- Changed production Python Ruff passed; strict Pyright passed agent configuration,
  planning/journey runtime, link research and API. Remaining credential/evaluator
  typecheck output is being collected. No dependency installs, commits or deployment.
- Working benchmark b9c94c59-d47b-4988-9037-abf5d6c443dd: completed, six journeys,
  zero findings, 22 steps, 71/71 physical artifacts.
- Latest broken benchmark 25f6f762-c5b7-4910-8be7-a3aaeb41e212: completed report
  b75a07fe-9123-4047-a8f1-10b3f723ef47; 12 journeys, 77 steps, 213/213 physical
  artifacts. Product classifier yields 7 stored observed-product issues and 14
  unverified observations. These seven are not yet manually validated detections.
  This benchmark predates the latest agent-setting/link changes. No fixture run
  is active. Do not run shared port-5191 fixture benchmarks concurrently.

## Remaining release gates

Detection recall and repeatability remain below the release contract. Manually
review latest confirmations against exact images/actions and ground truth before
claiming validated detections. Do not loosen evidence rules to raise benchmark totals.
The local API outbox previously logged Kafka SSL record-layer failures; verify the
broker connection before declaring Start-to-report pipeline ready. Login is local
identity access, not fully provisioned production authentication. Review long-name
UI screenshot, finish final checks/docs, and test real sequential rerun and link
skill output on a representative public documentation source before deployment.

## Running local preview

Vite localhost:5173, session 97555. API localhost:8001, PID 40924/session 8472.
Default sandbox shell startup fails with helper setup refresh errors; reviewed
escalated shell calls work. Never expose .env credentials or signed URLs in outputs.
# HITL implementation checkpoint — 2026-10-14

Work is in progress against `docs/hitl/README.md (Appendix A: original master plan)`.

- H00 reconciliation and H01 synthetic authenticated fixture are implemented. H01 fixture tests: 3 passed (Chromium); Ruff and Pyright passed.
- H02 additive schema and persistence repository are implemented. Local PostgreSQL migration head is `d7f3c2a9b108`; `alembic check` reported no pending operations. Repository integration test: 1 passed against isolated PostgreSQL schema.
- H03 browser takeover privacy/fencing changes are implemented in the working tree. A canary test passed after dynamically constructing its canary so Playwright source tracing did not embed it. The broader `test_browser_scoped_inspection.py` run has not been confirmed in this continuation because command execution is failing intermittently; do not mark the H03 phase gate fully passed until it is rerun. Ruff (with existing E501 baseline ignored) and strict Pyright passed.
- H04 is the next gate. The viewer transport must be selected between the plan's noVNC/headful and restricted-CDP alternatives after a local security/feasibility comparison. No viewer, external service, or additional infrastructure has been installed or selected. Stop here for the security-sensitive architecture decision; H05+ depend on it.
- 2026-10-14 continuation attempt: the H03 regression command was started, but the execution runner returned `helper_unknown_error: setup refresh had errors` before pytest reported results. Multiple retries failed at process setup (including simple PowerShell/file-read commands). Treat this as an infrastructure/tooling failure, not a test pass or test failure. H04 local comparison is still pending; no transport decision is supported by new measurements.
- Added `docs/hitl/README.md#appendix-c-historical-viewer-transport-review` with a preliminary threat-model comparison and explicit recommendation conditions. It is not a substitute for H04's required local synthetic-fixture measurements; do not mark H04 passed or proceed to H05.

Prior workspace changes and the pre-existing deletion of `MARKETTWIN_KNOWLEDGE_WORKER_UI_BRIDGE.md` are preserved. No credentials, deployment, push, or unauthorized website testing were used.
