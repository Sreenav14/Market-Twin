# MarketTwin code research

## November 24 — independent MT-000226 cross-check

Compared the clean payload export with the served report.payload and found exact equality. Independently counted 19,476 element verdicts, 55 state records and 3,870 pending URLs. Read the validator's later image-fetch addendum; the repo root validation report is now 21,335 bytes. The desktop and mobile capture first screens prioritize coverage counts; the captured documents measure 4,941 and 7,551 pixels tall. The CAPTCHA checkpoint proves provider rendering in a fresh controller only. Stream D proves ingestion through plan loading in MT-000225 and records the missing requirement-to-browser proof. Use the November 24 planner section for release decisions.

## November 23 — source knowledge from upload to test execution

Control API's ingestion processor builds and stores generated Markdown before calling the preview worker on the same source. Both worker services invoke extract_source independently. Preview failure after the object writes prevents the final database registration. This establishes repeated parsing and a partial-write window. Storage leakage, cost and latency have not been measured on live workloads.

In workflow/app_plan.py, prepare_app_plan creates the initial checks before loading pinned source Markdown. Loaded texts then enter the shared study brief, snapshot and app.plan.created event. Version pinning, SHA checks, source ordinals, model budgets and omission reasons are worth retaining. An opened event demonstrates a read. It cannot establish that a particular requirement influenced a check.

In workflow/knowledge_loading.py the collection shortlist scores English ASCII keyword overlap over titles, descriptions and headings. Only eight positive matches survive by default. Synonyms and non-Latin queries can miss a relevant file before model selection. Loading spends the default 24,000 estimated tokens in whole files, direct attachments first. It fetches plan-time content before checking whether it fits. In lead_review.py a checkpoint may request an additional file, but a repository search found no production caller of open_knowledge_file or reader of knowledge_open_requests. Tests exercise the parts independently.

Link research uses a deadline, queue and resource limits, but records only the first 30,000 characters of base page text. Long videos use timestamped, overlapping clips. Markdown batches run sequentially, followed by consolidation for multi-batch inputs. These establish plausible tradeoffs. A representative benchmark is needed before changing parallelism or asserting extraction accuracy.

Verification on the current tree: 90 worker tests passed, six opt-in grounding cases skipped, and 45 targeted ingestion processor, source pinning and orchestrator loading tests passed. No live upload-to-agent run was performed. Release evidence should include a source-only requirement, a second file learned mid-run, a paraphrased brief, and a late-page/late-video requirement. Compare retrieved and cited requirements, verified checks, elapsed time, model usage and stored bytes.

## Marley — Results UI research note (2026-11-23)

Two sourced passes on results/report UI design are summarised in `results-ui-research-marley.md` in this folder (full rule list + sources there). Three findings bear directly on this file's report-correctness record: (1) group by cause — Sentry, axe, BrowserStack and ReportPortal all fold occurrences into one row per fingerprint, the presentation counterpart of the MT-000199 diagnostic-repetition problem recorded below (the 1,625 empty-response and 924 client-blocked occurrences are two grouped rows, tagged test conditions, not defect counts); (2) denominator discipline — a percentage prints its denominator in the same visual unit or not at all, and below a coverage gate the number becomes a labelled state (the 0.2%-from-18-pages headline is the failure this prevents); (3) pending inventory belongs grouped by path with individual URLs one click deeper (Codecov's missing-lines pattern), matching the MT-000222 handoff's "3,780 pending URLs across 569 paths". — Marley

## November 23 — what the MT-000223 results screen communicates

The supplied screenshot gives the most prominent space to 102 recorded pages, 17 unverified pages, 3,772 pending URLs across 560 paths and 103 recorded page states. A finished run can have partial coverage. None of these numbers tells the owner what needs attention. The page explains how to interpret a percentage while hiding the score. The Findings tab shows zero alongside one minor and six severe element observations. These are different units, but the page gives the reader no way to reconcile them. Repeated article links next to similar placeholder claims make it difficult to identify a distinct fix.

The cause is visible in `apps/web/src/pages/runs/SlopReport.tsx`. Coverage precedes the assessment, the headline lives in a closed “Score and diagnostic counts” disclosure, and `reportPriorities` selects only three groups. Its grouping key includes the observed label and interaction path. Small text differences can split one underlying issue, while the same URL can legitimately refer to several distinct measurements. Group presentation needs to preserve every evidence target.

The shared aggregator defines the existing headline as 100 × (severe + 0.5 × minor) / judged elements, rounded to one decimal. It publishes a percentage only with at least 80% of elements judged and at most 10% undecided weight. It also records provenance errors. Raw counts on a screenshot cannot establish an eligible score. This score combines several rule types, including measured UI defects. Calling it a probability of AI authorship or a pure measure of generic styling would misdescribe the calculation. The aggregate exposes no denominator for cross-page consistency checks.

The shared link selects `acme_support_kb` inside a technical article. A literal example can be appropriate there. Contrast and suspected placeholder text on that span are separate claims with different evidence. A design that promotes every severe rule match into a confirmed user problem risks prioritizing the wrong fix.

Astra independently reviewed the screenshot and recommended bringing the assessment forward, showing scope beside each measure and grouping repeated evidence. For comparisons we selected directly labeled horizontal bars with a zero baseline. Severity also needs text or a symbol that remains meaningful without color. [ONS bar chart guidance](https://service-manual.ons.gov.uk/data-visualisation/chart-types/bar-charts) · [W3C use of color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html)

## MT-000206 final coverage reconciliation

Read the terminal run's `slop.page.inspected` events and expanded the state arrays inside `slop.page.checkpoint`. All 421 starts can be accounted for: 394 successful measurement records (392 distinct final URL strings), 21 exclusions, two unassessed states and four lane failures. Another 424 discovered addresses were pending. Checkpoints name the four failed claims in order: 415 (lane 1), 417 (lane 2), 420 (lane 3), 421 (lane 0). Each stores the coarse category `lane_error`. They occurred within four seconds. This establishes which claims failed and reinforces that committed states include unsuccessful attempts. The exception responsible for each lane error remains unknown. Coverage summaries must keep unsuccessful attempts out of measured-page counts.

## 2026-11-21 | What the visual audit actually established

MT-000206, Sup_3303, execution `f25fad6e-1870-411a-b402-f74a222dabcb`. Compared the local run checkpoint, entry assessment, URL events, retained original screenshot, desktop review selector, evaluator and report priority/coverage code. Counts below are timestamped samples of a changing run.

| Question | Observation | Engineering or design judgment |
|---|---|---|
| Is the browser stuck? | At 8m47s, 280 starts for 280 distinct requested URLs, 255 measurements for 254 distinct final strings, 21 excluded, four active, 471 pending. | The watch impression of repeating the entry is misleading for this interval. The counts do not establish content uniqueness or that all 471 pages need individual visual review. |
| Are we spending effort on the submitted experience? | At 20:39:57 UTC, 62 blog, 60 docs and 59 changelog states out of 203. | These sections matter for a site-wide audit. Their combined 89% share makes state count a poor proxy for breadth across product experiences. The distribution alone cannot show that a particular important route was omitted. |
| Can the user verify the entry verdict? | 259 judged desktop elements. Three minor entry findings cited the same 1280 × 900 screenshot (142,401 bytes), artifact `8627d49a-d29d-4678-bc4d-d895932f2673`. It shows the selected Product nav, a prominent three-line heading, muted body copy, a comparison table and small category labels. | The screenshot contradicts the implication that one typeface means no display/body contrast. Small labels visibly distinguish categories. This viewport cannot verify all 27 labels or identify which peers allegedly miss alignment by 2–6 px. None of these three alone establishes AI authorship or a user-impacting defect. |
| Are checks covering all UI? | The fast desktop path measures the loaded state and extracts links. The entry screenshot itself shows a Human/Agent switch. The checkpoint does not demonstrate switching it. | Navigation evidence, static control inspection, interaction evidence and task completion must be counted separately. |
| Are real issues prioritized with proof? | In 203 states, 19 had screenshot references. Of 13 flagged element observations, five occurred on states without one. The same sample had 178 default-font and 176 template-chrome signals. No UI_VISUAL_REVIEW signal was present in the sample. | A missing screenshot may be acceptable for a reproducible measured issue. The absence of a visual finding does not establish that no review ran. Frequency measures recurring style as well as potential problems. |
| Does the report preserve meaning? | Desktop capture selection considers entry, sampled layout and severe page signals. Report highlights consider flagged elements. Coverage adds recorded state URLs to pending URLs. MT-000199 independently reproduced a 0.2% element metric that excludes page signals. | An important page-level issue can disappear from priorities. An error landing can count as a visited URL. A site-wide quality percentage is unsupported by this denominator. |

Trace the three decisions in [desktop review and entry assessment](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/slop_run.py#L475), [aggregation](services/evaluation-worker/src/markettwin_evaluation_worker/slop_evaluator.py#L53) and [report](apps/web/src/pages/runs/SlopReport.tsx#L93). Historical functional, persona, knowledge and takeover findings below are regression leads. This visual run supplies no fresh end-to-end proof for those modes. No independent panel has adjudicated all Supermemory findings.

### MT-000199 report correctness and readability

Read the persisted evaluation report and recounted its 52 state records. The 16,648 clean, 37 minor and 14 severe element observations reproduce the displayed weighted 0.2% across 16,699 judged observations. Another 711 were unjudged. These are observations across states and viewports. The score excludes page-level design signals. The 14 severe elements fired the broken-media rule and collapse to seven distinct URL and label pairs, which alone cannot establish seven broken assets. The report also contains a visual observation about a clipped mobile error page. That evidence needs page classification and image verification before attribution to the intended content.

The payload has 9,504 aggregate page signals, including 8,912 pending-page entries in the underlying states. SlopReport maps informational signals to an expanded list and builds detail children for every state. Two browser messages alone account for 1,625 empty responses and 924 client-blocked occurrences. The 289 serious and 2,814 minor defect counts cannot establish that many separate product failures. Reviewed stored data and rendering code. Independent screenshot reproduction and a rendered visual inspection remain open.

### MT-000199 discovery audit

The first page-start events already recorded 8,891 URLs pending. The Slop workflow reads the target site's sitemap index and child sitemaps before starting browser workers, then adds links from rendered pages. The final checkpoint held 8,912 unique URL strings on www.klaviyo.com, covering 8,901 distinct host/path pairs. Seven locale prefixes accounted for 6,522 entries and the root blog prefix for another 1,050. Individual URL provenance is unavailable in this checkpoint. The final collection marked coverage partial with 18 pages recorded. These counts describe this saved run.

## Scope and evidence

Reviewed the working tree at HEAD `50799ab` on November 19, 2026. The audited source includes local modified and untracked files. Chose **Create an Explore & Test run → Start → View report** as the first path because it crosses the main product boundaries and tests the fundamentals before optional features. The audit scope also covers surrounding workflows and infrastructure. The line-by-line review is in progress. [Progress](progress.md)

`docs/CURRENT_STATE.md` and `docs/SESSION_HANDOFF.md` are deleted in the working tree. Their HEAD copies describe an earlier accepted benchmark and follow-up verification. The current README still links to those files and names a prior execution-mode default. Treat those results as historical until the current code passes an equivalent run. [README](README.md)

The most consequential complexity is at the points where one component hands work to another. Draft creation waits on a freshness worker even though Start is a separate action. A queued row can outlive its dispatch. Browser execution and evaluation use separate lifecycles. Within the harness, the event stream and the resume snapshot can commit separately. Knowledge ingestion similarly depends on a second processing pipeline before surfacing the first result. Each extra state or copy requires explicit agreement about who writes it, when users see it, and what happens on retry.

## Findings

### 0. High · A workspace member can create a draft and has no Start button

**Source-verified and checked with the current permission helpers.** The New Run form is available to members through `canWriteWorkspace`. It always creates a draft and navigates to Overview. The API permits members to start that draft through `WORKSPACE_WRITE_ROLES`. The Overview header renders Start using `canManageLifecycle`, which admits only owners and admins. Evaluating the two helpers for `member` produced `true` for Create and `false` for the Start button gate. The member's normal path ends at a draft that the API would let them start. [Create permission](apps/web/src/pages/runs/NewRunPage.tsx#L81) · [Start button](apps/web/src/layouts/RunLayout.tsx#L155) · [Web role helpers](apps/web/src/lib/permissions.ts) · [API start authorization](services/control-api/src/markettwin_control_api/api/test_run.py#L1720) · [API writer roles](services/control-api/src/markettwin_control_api/api/permissions.py#L4)

### 1. High · Creating a draft can time out in the browser before the API returns

**Source-verified.** The web client's common request wrapper applies a 30,000 ms abort deadline. The Create test form awaits the response before navigating. An Explore & Test run with an existing ready app map and a due freshness check queues a preflight, then polls for up to 600 seconds by default before persisting the draft. A slow or unavailable preflight consumer therefore can produce a browser timeout before a draft ID exists in the UI. The form discards no inputs on the error path, but its feedback lacks the queued preflight ID, so the user has no way to tell how far the request got. Whether the server continues after client disconnect and commits a draft depends on the serving stack. That outcome and retry duplication remain unverified. [Request deadline](apps/web/src/lib/api.ts#L376) · [Form submit](apps/web/src/pages/runs/NewRunPage.tsx#L149) · [Default wait](services/control-api/src/markettwin_control_api/config.py#L62) · [Polling loop](services/control-api/src/markettwin_control_api/api/test_run.py#L788) · [Draft persistence](services/control-api/src/markettwin_control_api/api/test_run.py#L1123)

The preflight uses a separate transaction so the worker can see its row while the request's original transaction remains open. Every pending create request can retain its original database session and open additional sessions during polling. Connection-pool contention under load is a hypothesis to measure. Single-flight joins existing preflight work for the map, while each request still waits in its own loop. [Transaction and poll code](services/control-api/src/markettwin_control_api/api/test_run.py#L788)

The API tests use a fake session and shortened waits. One expects expiry to successfully create a run on the original map. The selected Playwright run-flow tests fulfill API calls directly. These checks do not exercise a real browser deadline against an API holding a real draft transaction. A useful regression would delay a disposable worker past the client deadline, assert what the browser displays, then verify the database outcome and retry behavior. [Preflight test](services/control-api/tests/test_preflight_creation.py#L486) · [Playwright run flow](apps/web/e2e/ui-workflow.spec.ts#L570)

### 2. High · A reachable web app can still be unable to start a run

**Observed in a local log and traced through source.** The ignored local execution log contains 279 entries labeled `KafkaConnectionError`, with bootstrap failures in the execution consumer. Start checks that relay dispatch is enabled, Kafka is reachable, and execution and evaluation heartbeats are connected and under 30 seconds old. A failed mandatory check yields HTTP 503 before invoking dispatch. The log therefore describes a blocker for the configured worker at the recorded times. Its root cause could be networking, credentials, broker configuration, or the local process environment. [Start handler](services/control-api/src/markettwin_control_api/api/test_run.py#L1656) · [Readiness rules](services/control-api/src/markettwin_control_api/services/run_readiness.py#L41) · [Worker bootstrap](services/execution-orchestrator/src/markettwin_execution_orchestrator/worker.py#L378)

The live loopback probe later returned Kafka connected, relay enabled, and both worker heartbeats ready. The earlier failure is historical. Current health is a point-in-time observation before dispatch and report generation. [Health endpoints](services/control-api/src/markettwin_control_api/main.py#L169)

The diagnosis loses information at two boundaries. The readiness Kafka probe reduces exceptions to `False`. The heartbeat lookup turns any SQLAlchemy error into absent heartbeats. A missing migration, database query failure, or inactive worker can consequently produce the same worker-offline message. The model check is explicitly advisory and reflects Control API configuration. A green readiness screen still leaves the worker's ability to make a model call unverified. [Probe and heartbeat code](services/control-api/src/markettwin_control_api/services/run_readiness.py#L41)

### 3. Medium · Draft creation encodes unrelated concerns in one long request

**Source-verified complexity.** The form builds a 15-argument request with positional booleans and `undefined` placeholders. The API handler spans 294 lines and owns workspace and target checks, authentication options, fixture eligibility, snapshot construction, map freshness, task learning, knowledge selection, and persistence. Adding an input requires reasoning about the form, the serializer, the schema, snapshot encoding, and consumers. Field omission can change behavior where defaults differ. The form also requests authorization individually for every listed target and fails the entire picker on any authorization error besides 404. [Form](apps/web/src/pages/runs/NewRunPage.tsx#L80) · [API client](apps/web/src/lib/api.ts#L708) · [Create handler](services/control-api/src/markettwin_control_api/api/test_run.py#L881)

### 4. Medium · One user-visible workflow has several distinct completion boundaries

**Source-verified architecture.** Create persists a draft. Start queues it using a transactional outbox. A worker executes browser work and a separate evaluation phase finalizes the report. A completed run can return HTTP 409 while evaluation is pending, or 503 if evaluation is quarantined. The layout polls the results query while it sees 409. The run query stops automatic polling once the run becomes terminal. The user needs a way to distinguish accepted, queued, executing, waiting for evidence, and report generation failed. Existing endpoints provide some of those facts, but execution and report completion are already separate concepts in the same UI. [Run layout](apps/web/src/layouts/RunLayout.tsx#L46) · [Results endpoint](services/control-api/src/markettwin_control_api/api/test_run_results.py#L419)

### 5. Medium · Legacy run semantics remain spread across current screens

**Source-verified duplication.** The shared Python resolver maps legacy modes to three unified kinds. The run layout prefers the canonical kind for its title but checks legacy snapshot fields for stages. Activity, prompts, journeys, missions, perspectives, and results layout still branch on historical values directly. Activity labels a run “Simulated tester journeys” when neither old deep nor discovery mode is in its snapshot, which includes new Explore & Test runs that store the kind separately. Compatibility data is still needed to interpret history. Repeating these decisions in each view makes copy and report behavior drift as new runs are added. [Kind resolver](packages/shared-python/src/markettwin_shared/run_kind.py#L53) · [New snapshot](services/control-api/src/markettwin_control_api/api/test_run.py#L1037) · [Activity labels](apps/web/src/pages/runs/RunActivityPage.tsx#L92) · [Run layout](apps/web/src/layouts/RunLayout.tsx#L115)

### 6. Medium · Execution orchestration is concentrated in two large functions

**Measured and confirmed by source inspection.** `execute_harness_run` spans 1,706 lines. One function owns setup, work selection, scheduling, browser lifecycle, pause and resume, Board updates, and completion. `execute_test_case` spans 856 lines. The harness test module alone has 4,333 lines. Coupling is visible when reviewing cancellation, owner stop, park, and report publication because control flow enters and exits the same long function through multiple paths. These counts identify review targets. A migration function of similar length has a different maintenance profile. [Harness entry point](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/harness_run.py#L1521) · [Case entry point](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/case_execution.py#L1109) · [Harness tests](services/execution-orchestrator/tests/test_harness_run.py)

### 7. Medium · CI evidence bypasses the service chain behind the first user action

**Source-verified CI coverage gap.** The checked-in workflow installs Chromium for Python suites, and runs web typecheck, build, and Vitest. It has no job that starts the web app, API, database, Kafka relay, execution, and evaluation together. Some local Playwright scenarios intercept run, start, and results routes, and database tests often require opt-in. A green checked-in CI run can therefore coexist with the client/API deadline mismatch or a missing runtime dependency. Fresh npm installs also lack a lockfile, so their transitive dependency graph can change across environments. [CI workflow](.github/workflows/ci.yml) · [npm settings](.npmrc) · [Stubbed results](apps/web/e2e/ui-workflow.spec.ts#L199)

### 8. High · A quarantined dispatch can appear to be a busy runner

**Source-verified failure path.** Start changes the row to queued and writes the outbox event in one transaction. That atomic transition is useful and should remain explicit. After eight publish failures the outbox repository quarantines the event and its claim query excludes it. The relay updates the outbox row and leaves the run queued. After a minute without events, the queued-run diagnosis reads execution heartbeat state and returns “Runner is busy with another test” when the heartbeat is healthy. This can describe a runner that has never received the command. Readiness also considers dispatch ready from the enable flag and tests a newly created Kafka producer, so it gives no direct evidence that the relay is currently publishing. [Queue transaction](services/control-api/src/markettwin_control_api/services/run_dispatch.py#L36) · [Relay](services/control-api/src/markettwin_control_api/services/outbox_relay.py#L36) · [Outbox persistence](packages/database-python/src/markettwin_database/repositories/outbox_repository.py#L51) · [Stall diagnosis](services/control-api/src/markettwin_control_api/services/run_readiness.py#L173)

### 9. High · Knowledge ingestion performs two processing passes before exposing either result

**Source-verified.** The API records an upload and its object storage pointer, then its background processor claims the entry and holds a PostgreSQL connection for advisory ownership. The processor calls the private worker to build Markdown, writes the generated objects, then calls the private worker again to build the legacy preview from the same source. Both worker services independently extract the source. Each remote call can be attempted up to three times, and the retry classifier partly depends on the English error message. A preview failure after Markdown storage prevents the Markdown index from becoming visible and marks the entry as parsing failed. A retry can redo both passes. This makes upload latency and failure probability depend on two processing pipelines, with one broad UI failure state for either pipeline. [Upload](services/control-api/src/markettwin_control_api/api/ingestion.py#L309) · [Processor and retries](services/control-api/src/markettwin_control_api/knowledge/processor.py#L76) · [Markdown extraction](services/knowledge-worker/src/markettwin_knowledge_worker/services/knowledge_markdown_service.py#L42) · [Preview extraction](services/knowledge-worker/src/markettwin_knowledge_worker/services/knowledge_preview_service.py#L38)

### 10. Medium · Knowledge file metadata has two write authorities

**Source-verified failure window.** The metadata endpoint mutates the SQL row and overwrites its object-backed manifest within the SQL transaction. If object storage fails, SQL rolls back as intended. If storage succeeds and SQL commit then fails, the object manifest has already changed and the handler has no compensating write. The file view reads row metadata alongside manifest evidence, while run creation uses snapshot and manifest-selection data. Verify this path with a disposable commit-failure injection before treating metadata as atomic across both stores. The ingestion processor has a similar boundary for written objects followed by index publication. [Metadata update](services/control-api/src/markettwin_control_api/api/ingestion.py#L578) · [File content read](services/control-api/src/markettwin_control_api/api/ingestion.py#L538) · [Knowledge snapshot](services/control-api/src/markettwin_control_api/api/test_run.py#L281) · [Object writes and publication](services/control-api/src/markettwin_control_api/knowledge/processor.py#L301)

### 11. High · The overview can say evaluation is in progress after it has stopped

**Source-verified.** The evaluator quarantines the run after five failures and excludes it from its selection query. The results endpoint returns 503 with an operator recovery message. The layout maps the request to an error state, but Overview derives its banner from the execution status and whether report data exists. A completed execution with a quarantined report therefore produces “Evaluation in progress” and “currently compiling” in the banner while the results boundary has an error. The evaluator's heartbeat continues to advertise `connected: true` while the process is alive even if its polling or report work is failing. [Worker retry and heartbeat](services/evaluation-worker/src/markettwin_evaluation_worker/worker.py#L29) · [503 response](services/control-api/src/markettwin_control_api/api/test_run_results.py#L461) · [Layout error mapping](apps/web/src/layouts/RunLayout.tsx#L128) · [Overview banner](apps/web/src/pages/runs/RunOverviewPage.tsx#L58)

### 12. Medium · Freshness reuse trusts map fields without checking the preflight receipt

**Source-verified failure window.** The worker writes map freshness metrics before appending history, completing the preflight, and publishing its completion event. Its exception handler can mark the job failed after those freshness metrics were written. Draft creation reuses the map when the timestamp is recent and a preflight ID exists. It does not load that job's terminal status. An injected failure after the metrics write would test whether the next draft can label a failed job as reused. The worker's own docstring acknowledges that later failures can leave stage writes behind. [Worker transitions](services/execution-orchestrator/src/markettwin_execution_orchestrator/freshness/freshness_job.py#L67) · [Reuse test in API](services/control-api/src/markettwin_control_api/api/test_run.py#L805)

### 13. Medium · Frontend tests drifted with the API, accessibility labels, and provider setup

**Reproduced.** The full web suite recorded 338 passed and five failed. The two report failures query a region named “Test result,” while the report now renders it as “Coverage summary.” The assertions stop before exercising the evidence requirements they were intended to cover. The summary fixture omits the QueryClient provider, which the new StopRunButton uses when mounted. The production entry point supplies the provider. Both run-list timeouts wait for data from a mock of `api.listRuns` while the selected-application page now uses `api.listRunsPage`. This is a concrete fixture wiring mismatch. The timeout alone does not establish that sorting or filtering in the real application is broken. [Report assertions](apps/web/src/pages/runs/RunReportPage.test.tsx#L57) · [Current label](apps/web/src/pages/runs/RunReportPage.tsx#L164) · [Summary fixture](apps/web/src/pages/runs/RunFindingsPage.test.tsx#L10) · [Provider](apps/web/src/main.tsx#L29) · [Run-list mocks](apps/web/src/pages/runs/RunsPage.test.tsx#L33) · [Live list request](apps/web/src/pages/applications/ApplicationRunsPage.tsx#L37)

### 14. High · Board evidence can commit before the resume checkpoint

**Source-verified failure window.** The harness persists an item as running and commits before executing it. In the ordinary completion path, it appends the terminal `board.item.result` event, marks `board_result_published` on the in-memory item, and commits before serializing the updated board to the run snapshot. The helper that appends the event does not serialize the item. A restart between those two commits can leave a terminal event and a snapshot that still says running. The resume path loads that snapshot and resets running items to pending. A disposable restart regression should verify whether the same logical item runs again or produces a second terminal event after this interruption. The close-sweep comment currently says event and flag share a commit. For this path the code does not enforce that invariant. [Running checkpoint](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/harness_run.py#L2347) · [Terminal event and commits](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/harness_run.py#L2827) · [Snapshot persistence](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/harness_state.py#L227) · [Resume](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/harness_run.py#L1686)

### 15. Medium · Harvest API tests fail before verifying the job transition

**Reproduced.** Two tests fail when their fake session receives `with_for_update=True` in `get()`. The repository uses the row lock to serialize starting harvest. The fake does not model that call signature, so the tests never reach their assertions about creation and in-flight reuse. The other four tests in the file passed. This is a test compatibility issue. A real concurrent claim remains a separate verification need. [Harvest test](services/control-api/tests/test_harvest_api.py#L203) · [Repository lock](services/control-api/src/markettwin_control_api/knowledge/map_repository.py#L600)

### 16. Medium · Optional task capture can interfere with a finished case

**Source-verified failure windows.** The executor captures terminal state for task learning inside the same timeout that governs case actions and assertions. If the deadline expires during capture, cancellation leaves the capture block and is converted to a case timeout. After computing the result, the executor tries to persist an optional task-spec snapshot using the same SQLAlchemy session as the mandatory completion event. The snapshot writer flushes. The trace helper catches errors without rolling back or isolating that write, so a failed flush can leave the transaction unable to accept the mandatory completion event. Inject latency in terminal capture and a database flush failure in task-spec storage to verify each behavior. [Optional trace handling](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/case_execution.py#L1182) · [Terminal state capture](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/case_execution.py#L1797) · [Completion](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/case_execution.py#L1962) · [Task-spec write](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/task_spec_store.py#L21)

### 17. High · Draft creation can pin a preflight successor that failed its map gate

**Source-verified.** The initial map lookup requires map status `ready` and release state `partial` or `trusted`. Reconcile can set the successor to `failed` when the inventory gate fails, then still return its ID. The preflight's own terminal status comes from the sweep, so a preflight can end `ready` or `partial` while its successor failed the map gate. The API loads that successor directly and replaces the initial map without reapplying the initial eligibility predicate. A related publication window exists because reconcile commits release status before enrichment and skill demotion. The two lifecycle contracts need a regression covering a successful sweep with an ineligible successor and a late reconciliation failure. [Initial map eligibility](services/control-api/src/markettwin_control_api/knowledge/map_repository.py#L266) · [Successor gate](services/execution-orchestrator/src/markettwin_execution_orchestrator/freshness/reconcile.py#L184) · [Separate release transaction](services/execution-orchestrator/src/markettwin_execution_orchestrator/freshness/freshness_repository.py#L785) · [Preflight status](services/execution-orchestrator/src/markettwin_execution_orchestrator/freshness/freshness_job.py#L139) · [API pinning](services/control-api/src/markettwin_control_api/api/test_run.py#L1125)

## Local runtime snapshot

Read-only queries against the configured loopback PostgreSQL database, alongside the live health endpoints. The database includes historical records across workspaces. These counts describe that database and do not measure a current-release success rate.

| Observation | Result |
| --- | --- |
| Web and Control API | HTTP 200. Control API process health returned `ok`. |
| Kafka and workers | Kafka connected, relay enabled, execution and evaluation heartbeat ready. |
| Stored runs | 72 completed execution, 38 failed, 3 draft, 1 queued. |
| Report gap | 22 of the 72 completed executions lack a completed version-1 report. All 22 are quarantined and retain `RuntimeError` as the error classification. They have no stored unified run kind and were quarantined November 4–5 UTC. The exception class is too broad to establish the cause. |
| Dispatch | No unpublished or quarantined `run.requested` events. The one queued run has no matching published outbox event. Its origin is unresolved. |
| Freshness jobs | Three stored preflights, all manual and failed. One stalled. Both other records say `FetchHop.__init__() got an unexpected keyword argument 'location'`. Current source constructs the hop with the two supported fields. A checked-in regression drives the production fetcher against a stubbed HTTP redirect. No stored preflight in this sample came from draft creation. |

The redirect failure is a concrete example of the same data contract implemented at multiple layers. The Control API census and execution worker preflight each implement their own HTTP fetcher around the shared `FetchHop` model. Both current call sites agree with that model. The historical row proves the earlier mismatch and the unit regression exercises the current constructor. A live preflight through completion remains unverified. [Shared hop](packages/shared-python/src/markettwin_shared/census_sources.py#L64) · [Control API fetcher](services/control-api/src/markettwin_control_api/knowledge/census.py#L267) · [Worker fetcher](services/execution-orchestrator/src/markettwin_execution_orchestrator/freshness/freshness_job.py#L598) · [Redirect regression](services/execution-orchestrator/tests/test_freshness_job.py#L670)

## Repository inventory

Enumerated present tracked and nonignored untracked files, deduplicated names, and counted physical lines for first-party Python, JS/TS, CSS, HTML, SQL, shell, YAML, TOML and Dockerfile source. Excluded local diagnostics, runtime artifacts, editor metadata and installed dependencies. Python AST parsing succeeded for all 620 inventoried Python files and found 72 functions of at least 150 lines across production, tests and migrations. The installed Oxc parser parsed all 220 web TypeScript and TSX files and found 53 functions or callbacks of at least 150 lines. The longest were the workspace dashboard at 501 lines, New Run at 497, the public landing page callback at 477 and Run Journeys at 447. Render markup contributes to those spans. Semantic review coverage is recorded below.

| Area | Files | Physical lines |
| --- | ---: | ---: |
| Web | 246 | 44,072 |
| Control API | 159 | 37,725 |
| Execution Orchestrator | 272 | 77,192 |
| Evaluation Worker | 48 | 8,083 |
| Knowledge Worker | 42 | 4,742 |
| Database package | 21 | 7,212 |
| Shared Python | 47 | 8,062 |
| Migrations and database scripts | 37 | 6,143 |
| Infrastructure, CI, scripts and root config | 8 | 742 |
| **Total** | **880** | **193,973** |

## Verification and manual review ledger

| Check | Result |
| --- | --- |
| Web TypeScript | Passed |
| Python run API, preflight creation, readiness | 83 passed, 6 warnings |
| Python ingestion API/processor, report readiness and Markdown | 81 passed, 2 warnings |
| Python Harvest API | 4 passed, 2 failed. Both failures stem from the stale fake session signature. |
| Python freshness job | 12 passed, including the redirect constructor regression |
| Ruff in services and packages | 445 diagnostics, including 255 line-length, 109 import-order and 17 unused-import findings |
| Full web Vitest | 338 passed, 5 failed across 56 files using the native config loader. Default loader hit sandbox process creation error. |
| Focused web Vitest | 21 passed, 3 failed. Report and summary failures reproduced. |
| Migration graph | Alembic reports one head at `c4f7a91b2d08`. |
| Full Python suite | 1,967 passed, 8 failed, 31 skipped, 110 warnings in 16m 36s. Several database and provider checks require opt-in. |

| Python failures | What the failure establishes |
| --- | --- |
| Harvest enqueue and duplicate request (two) | The fake session rejects a real locking argument before either test reaches the asserted outcome. [Tests](services/control-api/tests/test_harvest_api.py#L203) |
| Browser policy | The target-session double has no `offsite` attribute. The current route handler reads it before the mocked decision and handles an attribute error as a blocked request. Fixture drift is supported by the call sequence. [Fixture](services/execution-orchestrator/tests/test_browser_policy.py#L231) · [Handler](services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/controller.py#L842) |
| Browser network diagnostics | The HTTP session double lacks the same attribute. The fallback classifies an unexpected exception as `browser_transport_failed`, while the test expects `target_origin_denied`. The equivalent WebSocket case passed. [Fixture](services/execution-orchestrator/tests/test_human_network_diagnostics.py#L123) · [Classifier](services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/controller.py#L970) |
| Keyboard-only Select | The fake returns a Boolean for a DOM query that expects a string. The test exits before verifying keyboard interaction. [Fake](services/execution-orchestrator/tests/test_keyboard_enforcement.py#L30) |
| UI audit browser fixture | The clean fixture still has clean individual controls, but its page now records two `UI_STATE_UNASSESSED` notices where the test expects no page signals. One observed notice comes from an approval requirement on a settings control. This is a mismatch over coverage reporting, and the expected contract needs verification. [Test](services/execution-orchestrator/tests/test_slop_fixture.py#L151) |
| Invalid persisted testing depth | The code rejects an unknown depth with `ValueError`. The test expects `KeyError`. No expansion of coverage was observed in this failure. [Test](services/execution-orchestrator/tests/test_testing_depth.py#L19) |
| Login timeout handoff | Unawaitable session mocks fail before the timeout branch. This fixture no longer verifies the cleanup assertion it was written for. [Test](services/execution-orchestrator/tests/test_workflow_auth_handoff.py#L260) |

| Source | Review in this pass |
| --- | --- |
| `NewRunPage.tsx` | Target selection, input validation, submission, busy/error states, draft navigation |
| `api.ts` | Shared request ceiling, run mutation and results client |
| `test_run.py` | Freshness poll contract, relevant draft creation branches, Start handler |
| `run_readiness.py` | Heartbeat interpretation, Kafka probe, mandatory/advisory gate, stall reasons |
| `RunLayout.tsx`, `test_run_results.py` | Status polling, result availability, failure and quarantine handling |
| Execution `worker.py`, lines 239–424 | Command acceptance, restart handling, exception behavior, heartbeat and Kafka commit loop |
| `harness_run.py`, lines 1521–3226 | Initialization, rehydration, inventory frontier, browser ownership, lane claims, proof, checkpoints, park, terminal persistence and post-run compilation. Earlier helpers remain pending. |
| `case_execution.py`, lines 1109–1964 | Session ownership, budgets, action and assertion evidence, timeout routing, result and optional trace persistence. Earlier helpers pending. |
| Evaluation `worker.py`, lines 1–171 | Polling, claim, finalization, retry, quarantine and heartbeats |
| `freshness_job.py`, lines 67–1215, and `preflight_sweep.py` / `reconcile.py` | Worker transitions, independent commits, orphan and stall supervision, claims, redirect handling, page capture, tiered comparisons, successor release and demotion |
| `run_dispatch.py`, `outbox_relay.py`, `outbox_repository.py` | Dispatch state change, broker acknowledgment, retry and quarantine branches |
| `ingestion.py`, `knowledge/processor.py`, `knowledge_markdown_service.py`, `knowledge_preview_service.py` | Entry status, enqueue, upload storage, extraction, retries, object publication and metadata edits |
| Remaining source, migrations, templates, styles, tests | Inventory pass. Continue semantic review in batches. |

## Original verification backlog

Use [planner.md](planner.md) for the current implementation sequence. The checks below retain their original audit scope.

1. Establish one repeatable Explore & Test run against an owned disposable fixture. Verify owner and member access to Start, a draft ID, one accepted dispatch, a browser result with an evidence reference, and a persisted report rendered in the UI.
2. Test broker failure and recovery after queueing. Verify that the run tells the user whether publication is pending, retrying, or quarantined. Test a delayed map preflight independently and verify browser feedback and the draft count after retry.
3. Test a report that cannot be generated. Verify one consistent error across Overview and Results with a verified recovery path.
4. Interrupt a disposable harness run between terminal event insertion and snapshot persistence. Verify one durable terminal result and inspect the recovered item and execution attempts.
5. Record the two knowledge worker calls for a single upload. Inject a legacy preview failure and a manifest write/SQL commit mismatch. Confirm what the interface shows and what persists before simplifying dual processing or metadata ownership.
6. Restore regression coverage in the failing frontend and Harvest API tests, then review repeated run-kind and lifecycle decisions where they affect observed behavior.

## Product behavior follow-up · November 19

Read-only aggregate queries joined local `testing.test_runs` and `execution.run_events` by run ID. Selected runs by their stored kind and counted the `visited` and `pending` arrays under `configuration_snapshot.discovery_frontier`. The ten rows carrying this field were all Explore runs. Eight saved one visited URL. Five failed with 131 URLs pending. Two completed with 131 pending and one completed with 2,059 pending. The two other rows failed with 2 visited / 130 pending and 10 visited / 341 pending. All three completed rows emitted `harness.coverage.frontier` with reason `frontier_remaining`. Their checkpoint events include two continue and two access-blocker stop decisions in aggregate. These historical snapshot counts measure attempted URL keys. They cannot independently establish the number of distinct reachable screens or the root cause of a particular user's run.

Across all 13 explicitly typed Explore runs, nine failed. The recorded failure types were integrity error (3), stall watchdog (2), host resolution (1), browser session missing (1), runtime error (1) and browser timeout (1). The stored sanitized integrity messages yielded no quoted constraint name. The Persona sample had two completed and one failed with a model-call limit. Current persona goal code already catches that exception. The UI audit sample had six completed, five failed and one draft. Reproduce on the current revision before attributing these errors to current lines.

**18. Exploration can terminate before visiting a queued successor.** The first inventory call breaks after one indexed page. The caller raises on an empty item list before the scheduling loop that can fetch another queued route. With eligible controls the loop instead favors pending cases and drains active lanes before crawling the next page. These are two different routes to poor breadth. No stored failure in the sample was identified as the empty-inventory exception. [First crawl](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/harness_run.py#L1864) · [Guard and scheduler](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/harness_run.py#L2140)

**19. A bare URL can bypass persisted app planning.** With no knowledge context, app map or pinned source block, preparation returns immediately. The builder otherwise starts with zero checks, and fallback route selection uses the start URL. Current dispatch chooses among three separate executors. The MetaAgentPlan schema and dynamic persona task runner are distinct from this dispatcher. [Plan](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/app_plan.py#L101) · [Dispatch](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/run_executor.py#L140)

**20. Live FPS includes repeat frames; control metadata has its own delay.** Observer diagnostics divide frames plus heartbeats by elapsed time. The gateway can send the previous frame after a second of silence. Metadata and handoff status poll separately. A still page can have positive reported FPS, and a changing screen needs client paint measurements to identify the source of jumps. The operator path already supports a requested pause and exclusive claim. The remaining verification is the same-session, refreshable end-to-end handoff across modes. [Gateway](services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/viewer_gateway.py#L247) · [Activity](apps/web/src/pages/runs/RunActivityPage.tsx#L36) · [Claim](apps/web/src/pages/runs/HumanActionPage.tsx#L118)

**21. Source selection and task-level grounding measure different things.** Oversized files can be skipped wholesale. The shared brief embeds the loaded file text, while the persona goal result initializes its knowledge requirement IDs to an empty list. A file-open receipt cannot by itself connect a source passage to an observed result. [Loader](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/knowledge_loading.py#L169) · [Brief](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/app_plan.py#L156) · [Persona result](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/persona_goal.py)

Reran five focused Python modules covering app-map planning, observer gateway, knowledge loading, persona graph derivation and discovery checkpoints. **41 passed, four deprecation warnings.** These tests and the stored data do not measure capture-to-paint latency or verify a current full-stack login handoff. The [implementation plan](planner.md) specifies those acceptance runs and the detailed evidence for each product area.

## Independent verification of the recovery plan

A repeatable-read, read-only query grouped runs by status, counted both frontier arrays and read the persisted `configuration_snapshot.lead_stop` field for each run. It reconfirmed the 72 completed, 38 failed, three drafts and one queued row. Both one-page completions with 131 pending stored `source=lead` and `stop_kind=access_blocker`. The completion with 2,059 pending stored `source=handoff`. The current handoff branch drains and stops the run after certain unverified handbacks. A missing queue, empty inventory and expired budget are therefore inadequate explanations for these three recorded stops. The original access conditions and deployed revision remain unknown. [Handoff stop](services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/harness_run.py#L2855)

Reproduced finding 18 against the actual harness function with the existing in-memory session and browser doubles. Set the planned routes to an empty index followed by a page with one Search button. The function raised `BrowserDiscoveryEmptyError` with one visited and one still pending. Four neighboring regressions passed, including first-page work before next-page discovery and reporting of a capped frontier. This verifies the control-flow defect independently of historical data. Web TypeScript also passed again. The full-suite totals above belong to the original audit run. [Existing fixtures](services/execution-orchestrator/tests/test_harness_run.py#L937)

Source pinning already happens during draft creation. The revised plan preserves this behavior and requires the same source through Start and resume. The existing FPS probe includes real Chromium, the browser owner and a local gateway, an animated fixture, a simplified authority and a Python WebSocket client. It counts binary messages including any repeats. It cannot establish motion smoothness inside the React viewer. [Attachment snapshot](services/control-api/src/markettwin_control_api/api/test_run.py#L1145) ? [Benchmark](scripts/measure_watch_fps.py)


The 30-second Watch benchmark received 1,788 binary frames, or 59.60 fps. The gateway counted zero heartbeat repeats, acknowledgment failures or decode failures. This is a healthy local transport baseline on an animated page. The real Activity screen, deployed proxy and operator input path were outside the probe. A separate read-only query confirmed completed version-1 reports exist for all three one-page completions. It also reconfirmed 22 quarantined completed runs without a completed version-1 report and three failed manual preflights.

## Explore recovery follow-up

- The same-URL regression showed that routine inventory refresh could revisit a known modal state and recreate controls inherited from its closed state. Preserving the discovered state's opener path prevents the refresh from adding the opener as another check. The regression is test_same_url_revealed_control_replays_its_opener_for_both_attempts.
- The Board checkpoint used to return every running item to pending. The browser execution recorder commits a step before applying the input, so an interrupted step can have taken effect before the Board saves its verdict. Explore now uses the persisted step to report an uncertain effect and gives the operator the journey link for verification.
- The Board verdict formula can return Ready at 50 percent coverage. The recovered fixture exposed that distinction on Results when one check worked and the other needed verification. The report now qualifies Ready when discovered work remains, using the persisted coverage counts.

### Report information hierarchy

The GOV.UK Design System recommends keeping broadly needed information visible and using descriptive disclosures for secondary detail. Its summary lists pair labels and values. Applied these principles to the existing MarketTwin typography and evidence flows. The large historical report drove the choice to show scope first, group example findings by rule, and make pending URLs searchable in batches. Sources: https://design-system.service.gov.uk/components/details/ and https://design-system.service.gov.uk/components/summary-list/
## Lane failure research — MT-000236/237/238 (Marley, 2026-11-24)

Why three of four Check-the-look lanes stopped inspecting in MT-000237, what actually caused it, what was ruled out, and what is still unprovable. Every claim below was established by eight parallel analysis tracks and then re-checked by a five-leg verification pass, including an experimental reproduction with the real production code. Full working files are listed under Pointers at the end.

### Symptom

MT-000237 (Klaviyo, Check the look, 4 lanes, ran on the execution worker restarted 2026-11-24 22:23 CST — the first run after the lane-recovery fix):

- Lane 0 recorded 24 pages. Lanes 1–3 recorded almost nothing: per-lane inspected counts were lane 1 = 3, lane 3 = 3, lane 2 = 0.
- The checkpoint census shows ~898 failure states stamped `browser_policy` with `policy_code: "target_url"` — lane 1 ×299, lane 2 ×301, lane 3 ×298, lane 0 ×0. These are the only 898 `policy_code` values in the entire database, and all of them are `target_url`.
- Each failed claim finished in ~0.5–0.8 s (median failed page 0.82 s vs 20.6 s for a real inspection) with zero network activity — the refusal happened before any page load.
- Run totals: 24 pages recorded, 1,598 pending, 901 unverified; the run ended partial on its time budget ("The desktop scan reached its time budget before all work finished").
- Zero lanes retired — the lane-recovery fix did its half: lanes stayed alive and kept claiming. They just failed every claim.
- F-S2 was proven in this same run: the report's executive summary natively carries the honest serious/minor split. Evaluation published correctly on starved input; evaluation was not the inspection problem.

MT-000236 (the run before it, pre-restart code) had the same disease in the older shape: lanes 1–3 retired ~20 s in with cause `browser_policy`, `replacement_scheduled: false`, and lane 0 alone did all 30 inspections.

MT-000238 (supermemory.ai, same worker generation) is the contrasting case: all four lanes inspected (36/38/14/21 measured pages), zero policy states anywhere in the run — yet still partial, because lane 2 retired on a `browser_timeout` (see "Held open" below) and the frontier (3,888 discovered URLs) far exceeded the time budget.

### Method

Eight analysis tracks ran in parallel over the run records and the code:

1. Forensic analyst — core root-cause pass over MT-000237's checkpoint states, phase accounting, and claim timing.
2. Policy-code tracer — mapped every policy code to its raising condition in `browser/policy.py` / `browser/offsite.py`.
3. Lane-construction tracer — how each lane's session is built (Room session vs sibling contexts) and what each inherits.
4. Run-record data miner — full census of all 52 slop runs in the database: first appearance of the failure, per-lane history, the before/after boundary.
5. Test-suite auditor — why no existing test could see this failure.
6. Timeline archaeologist — file mtimes, worker start times, and which code each run actually executed.
7. Prototype investigator — reproduction in Marley's sandbox with the real production pool/policy/controller code copied read-only, against a fake Klaviyo-like site.
8. External-patterns researcher — how comparable systems fail this way (session-bound authorization, Playwright context inheritance, Luhn false positives).

Five verification legs then re-checked the synthesis adversarially:

- V1 code anchors — every file:line claim re-read against the live code (8 of 9 confirmed; one imprecise, see Corrections).
- V2 mechanism resolution — raw round-1 state dumps, a full timeout census of the navigation path, and a step trace of claim 2's navigation.
- V3 regression diff — hash-chained snapshot diff of `controller.py` across the suspected change window.
- V4 numbers + gate — independent recompute of every figure from the database, plus the evaluation gate read in code.
- Prototype experiments — baseline run plus probes A/C (challenge timeout), B (server-redirect drift), B2 (idle client redirect → error page), D/D2 (recovery controls).

### The mechanism

In plain language: a lane's browser page can come to *rest* on a page that is not a real web address — most importantly a browser error page. Before every single action a lane takes, a pre-flight check re-validates **where the page is currently sitting** — not where it is being sent. If the resting page fails that check, the action is refused. That includes the navigation that would move the page somewhere healthy. So one bad resting state vetoes every later claim on that lane, forever, in about half a second each, and nothing in the code ever resets the page. The lane is not broken and the claim is not illegal; the lane is trapped by where its own page is parked.

Three wedge shapes were reproduced experimentally, all through the same pre-flight:

1. **Error-page rest (the MT-000237 signature).** The lane's page comes to rest on `chrome-error://chromewebdata/` — for example when a client-side redirect fires while the lane is idle and the cross-origin navigation is killed, leaving the error page behind. The pre-flight's resting-URL check raises `TargetUrlValidationError` ("Only HTTP and HTTPS URLs are supported."), which the desktop inspection maps to `policy_code: "target_url"`. Instant (~0 s in the probe, ~0.5 s in production), zero network, permanent.
2. **Stalled challenge re-inspection.** If the resting page's sensitive-challenge inspection stalls, the pre-flight re-runs that inspection before every action and hits the 10-second bound every time — the lane fails every claim at 10 s forever. The same 10 s timeout, inside `navigate`'s post-load checkpoint, also converts a successfully loaded page into a recorded load failure.
3. **Off-origin rest.** If the resting page sits on a public URL outside the allowed origins, the same check raises the offsite refusal (`policy_refused`) before every action — same permanence, different code.

And the control result that explains MT-000238: a failure that leaves the page at `about:blank` (which the pre-flight explicitly skips) or resting on-origin does **not** wedge the lane — the next claim proceeds normally. MT-000238's lane 3 absorbed 16 load failures and kept inspecting. Load failures do not wedge lanes; **the URL the failed page leaves behind does.**

Code anchors (all re-verified in the live tree):

- `browser/controller.py` `_agent_control_action` (lines 838–856): before every agent action it (a) runs `_authentication_checkpoint(session)`, re-inspecting the resting page for a sensitive challenge, and (b) at lines 849–850, when `session.offsite is not None` and `session.page.url != "about:blank"`, calls `validate_browsing_url(session, session.page.url)`. Any raise aborts the action — including the rescuing `navigate()`.
- `browser/offsite.py` `validate_browsing_url` → `public_url` (lines 36–42): with offsite supervision attached, an ordinary off-origin resting page yields `policy_refused`; `TargetUrlValidationError` escapes only when the resting URL is not a plain public http(s) hostname URL at all — error page, `blob:`/`data:` URL, embedded credentials, no hostname, or a localhost/IP-literal-class host. Unit pin with the real functions: `validate_browsing_url(session, "chrome-error://chromewebdata/")` raises exactly `TargetUrlValidationError: Only HTTP and HTTPS URLs are supported.`
- `browser/controller.py:1284` `_configure_page` executes `session.page = page` for **every** new page the context reports — any popup the loaded page opens is adopted as the lane's working page, which is one route by which a lane's resting page can become a non-public URL it never navigated to.
- `browser/auth_verifier.py:29` `SENSITIVE_CHALLENGE_TIMEOUT_SECONDS = 10`; `has_active_sensitive_challenge` (lines 59–78) raises `BrowserTimeoutError` on timeout. The post-load checkpoint that calls it (`controller.py:1820`, via `_authentication_checkpoint`) early-returns unless an authentication handler is bound — handlers are bound only when `runtime_human_assistance` is on, and MT-000237's own configuration snapshot records `runtime_human_assistance = true`, so the checkpoint was live in that run.
- `workflow/slop_run.py:1406–1425` maps `TargetUrlValidationError` to `policy_code: "target_url"` on the absorbed state; the pool's own failure path never sets a policy code, so all 898 codes are genuine controller refusals.
- Phase accounting from the run record: 928 navigation-phase entries vs 25 settle / 24 measured — the failures are inside `navigate`'s entry, before any page work.

Why lane 0 survived MT-000237: it has no code-level protection. In the prototype baseline all four lanes behave identically; lane 0 in production simply never landed on a bad resting state in its 24 inspections.

### Evidence table

| Claim | How proven |
|---|---|
| ~898 `target_url` states, lanes 1–3 only, ~0.5–0.8 s each, zero network | V4 independent recompute from the database (census exact: 299/301/298/0; DB-wide `policy_code` total = 898, all in MT-000237) |
| Failures occur inside `navigate`'s entry, before page load | Phase accounting (928 navigation vs 25 settle / 24 measured) + failure-window event census (V2/V4) |
| The raising call site is the resting-page check at `controller.py:850` | V2 step trace eliminating every rival raise site in code order; prototype instrumentation printing exception class, claim URL, and `session.page.url` at the failure |
| An error-page rest reproduces the exact production signature | Prototype test B2: idle client redirect → rest on `chrome-error://chromewebdata/` → next claim fails in 0.0 s with `target_url`; unit pin with the real `validate_browsing_url` |
| A stalled challenge check is a second, 10 s-per-claim wedge | Prototype tests A/C: claim 1 load-fails at 10.1 s resting on the claim URL; claims 2–3 fail identically at 10.0 s, page never moves |
| An off-origin rest wedges as `policy_refused`, not `target_url` | Prototype test B (302 drift): page lands off-origin, later claims fail in 0.1 s validating the resting URL |
| Blank/on-origin rests recover — load failures alone do not wedge | Prototype test D (connection RST → rest on `about:blank` → next claim inspects); MT-000238 lane 3's 16 absorbed load failures in production |
| Allowlists are identical on all lanes | Code: sibling sessions copy the Room's `allowed_origins`/`network_policy` verbatim (`controller.py:568–569`); V1 confirmed |
| Claim URLs were legal | Frontier admission runs the identical `validate_target_url` on identical inputs and silently skips failures (`slop_run.py:441–454`) — every refused URL had already passed once |
| MT-000237 ran with the challenge checkpoint live | `configuration_snapshot.runtime_human_assistance = true` pulled from `testing.test_runs` (V2); MT-000238 also `true` |
| The score gate never sees site coverage | Gate code read verbatim (V4): `packages/shared-python` `slop_aggregate.py` `slop_family()` computes coverage/undecided from recorded states only; the collection payload is attached to the report as data, never fed to the decision |

### What was ruled out

- **Allowlist / configuration differences between lanes.** Siblings inherit the Room's allowed origins and network policy verbatim; MT-000237 and MT-000238 have structurally identical target configs (one origin, `include_subdomains=false`, `requires_auth=false`, assistance on). Configuration explains none of the difference; site behaviour does.
- **The claim URLs.** Each passed the identical validation at frontier admission (above). A frontier URL refusing at navigation time with unchanged inputs is never intended behaviour.
- **The egress / tracker classifier (the TikTok story).** A separate mechanism in a separate layer: it aborts individual cross-origin requests on pages that loaded and never fails a page. MT-000237 had 40 egress blocks vs ~898 refusals; blocks appear in healthy runs too.
- **Resource contention.** One Chromium process with four contexts, not four browsers; no pool semaphore; starved lanes would be *slow* — these are refused in ~0.5 s with no network activity while lane 0 sustains ~45 s inspections concurrently. The one real contention found — the absorber/database lock (4,080 waits, 236.5 s total, max 3.6 s, recorded as `desktop_performance.phases.database_lock_wait`) — is a throughput tax on all lanes and cannot refuse a page.
- **The pool and the lane-recovery fix.** The fix changed refusal *handling* only (record the subtype, keep the lane claiming) — MT-000237 proves that half live with zero retirements. It never touched session construction or the pre-flight, which is where the failure lives. The prototype's baseline (real pool, plain site) inspects cleanly on all four lanes.
- **A durable offsite stop / handoff parking.** Zero `offsite.*` events in MT-000237; a stop codes as `offsite_limit`, not `target_url`; lanes cycled every ~0.7 s with no handoff events.
- **The 2026-11-24 09:30 controller change as the regression** — see Corrections; refuted by the hash-chained diff (V3).

### Corrections to the first analysis

The first synthesis got the destination right (controller pre-flight, resting page) but five details wrong or overstated. The verification pass caught all five; they are recorded here so nobody builds on the early version.

1. **"The regression arrived with the 09:30 controller.py change (MT-000230 handover patch)" — REFUTED.** V3 rebuilt the hash chain of preserved snapshots (Nov 22 → the exact state MT-000232's healthy worker ran → current): `navigate`, `_agent_control_action`, `cooperative_checkpoint`, `verify_handoff_destination`, `_create_sibling_session` and all challenge-check call sites are **byte-identical** across all three states. The entire healthy→failing controller diff is two hunks inside the `control_mode == "human"` branch that lanes never enter, plus a diagnostics relabel that cannot raise. `auth_verifier.py` was not written on Nov 24 at all (mtime Nov 21). The flip between healthy MT-000232 and broken MT-000236/237 therefore lives in what changed *around* the unchanged machinery — the slop-layer edits later that day (`pool.py` 21:49, `slop_run.py` 22:08: lane recovery + section-roots-first crawl order) and/or exposure: 236/237 were the first runs where this machinery met a full ~2,400-URL Klaviyo frontier, where MT-000232's crawl was small and bounded.
2. **"Lanes 1–3 succeeded on their first claims" — WRONG.** The data miner's first reading counted no-failure checkpoint states as successes. V4's recompute: in **both** MT-000236 and MT-000237, every worker lane's first claim was already an `action_failed` load failure with 0 elements (236: 8.46/8.62/8.09 s; 237: 10.12/9.63/10.31 s). No worker lane ever completed a page in either run. The forensic analyst's reading stood; the miner's did not.
3. **"87 egress blocks, all to TikTok" — WRONG in destination.** All 87 MT-000236 blocks are `payment_card_value`, but the destinations are TikTok 57 (29 `/api/v2/pixel` + 28 `/pixel/act`), Capterra 25, Facebook 3, and 2 events endpoints. The Luhn false-positive class is trackers generally, not one pixel.
4. **"Stage 1 = the 10 s challenge timeout" — DEMOTED from strong inference to one of two live possibilities, and disproven for one lane.** The record stores only the string `action_failed` — the same `reason_code` for `BrowserTimeoutError` and `BrowserNavigationError` — so round 1 is proven only as "a `BrowserActionError` inside `navigate` on each lane's first page". Worse for the timeout story: lane 2's round-1 claim lasted **9.627 s end-to-end**, and a full 10.0 s wait inside `navigate` cannot fit inside it. Lanes 1/3 (10.12 s / 10.31 s) remain consistent with the timeout. The mechanism itself is real — the prototype reproduced it (tests A/C) — but MT-000237's production signature (~0.5 s claims) matches the error-page route, not the 10 s one. Note also V1's precision catch: the checkpoint chain exists exactly as cited, but `_authentication_checkpoint` early-returns when no auth handler is bound; the analysis had not stated that precondition (it happened to hold in MT-000237 — assistance was on).
5. **"Undecided 2.25%" as the gate's input — IMPRECISE.** 2.25% is the element-*count* share (183/8,132). The figure the gate actually consumed is `undecided_weight = 0.0255` (2.55%), `undecided_basis: "area"`. Both pass the 10% limit, so MT-000237's publish decision is unaffected — but MT-000236 proves the distinction matters: it was withheld on `undecided_weight 0.1232` (area) while its count share was only 5.29% and would have passed.

### The second defect — the evaluation gate reads the wrong denominator

Confirmed in code (V4, quoted in VERIFY-GATE-DATA.md): `slop_family()` in `packages/shared-python/src/markettwin_shared/slop_aggregate.py` computes coverage as judged / (judged + cant_tell) **over element verdicts in the recorded states only**, and publishes iff coverage ≥ 0.80 and `undecided_weight` ≤ 0.10. The evaluator passes only state records to the aggregate; the collection payload carrying pages recorded / pending / unverified is attached to the report as data and never fed to the decision.

Consequences, both live:

- MT-000237: judged-set coverage 0.9775, undecided_weight 0.0255 → **0.0% published**, while site coverage was 24 / 2,523 = **0.95%** (site-level undecided 99.05%).
- MT-000238: **published 0.0%** (judged 47,749, coverage 0.9939, undecided_weight 0.0061) at site coverage 102 / 3,888 = **2.62%**.

The settled rule — score shown only if coverage ≥ 80% and undecided weight ≤ 10% — was designed against **site** coverage. As implemented, a run that inspects 1–3% of a site publishes a clean score. This defect is independent of the lane failure and is held as a separate fix (see planner.md); it is recorded here because it is the precise form of "the evaluation is not optimal": the gate is honest about the pages it saw and blind to the site it didn't.

### Held open — two smaller items

- **Timeout-killed lanes get no replacement (MT-000238 lane 2).** Lane 2 retired at 04:50:21 UTC on its ~20th page: a `BrowserTimeoutError` raised *outside* `navigate` (settle/probe) → `LaneDiedError("browser_timeout")` → pool retirement with `replacement_scheduled: false`, because the pool replaces only `browser_session` deaths (`slop/pool.py:437–451`). Failure isolation worked as designed; whether a timeout death should also earn the one replacement is an owner decision, deliberately not bundled into the lane fix.
- **Frontier vs budget.** MT-000237 admitted ~2,523 URLs and MT-000238 ~3,888 against a ~10-minute budget; even with all lanes healthy, both runs end partial. Crawl-order and budget policy are separate questions from the wedge.

### Test-suite gap — why nothing caught this

Every relevant test replaces at least one of the three things that failed *together* in production — the real controller, the real validation inputs, or the production policy mode:

- The four-lane refusal regression (`test_slop_pool.py`) mocks the controller's `navigate()` to throw `TargetUrlValidationError`; it proves the pool *survives* a refusal and never asks whether production should produce one. (MT-000237 confirms the pool half live.)
- The workflow tests monkeypatch the entire `BrowserController`.
- The real-Chromium fixtures (`test_slop_fixture.py`) use a local 127.0.0.1 target with `network_policy="local_development"`, where the allowed origins are built from the same string that generates every candidate URL — a `target_url` refusal on a same-origin page is impossible by construction.
- The pair (real Chromium + `public_only` + a public-style hostname) never occurs anywhere in the suite; candidates are never truly *discovered*; and every validation failure class collapses into the single code `target_url` with the detail stripped — so even production could not say which rule fired.

The one test that would have caught it: the fixture shape with `public_only`, a public-style hostname target, the production lane-session factory with nothing about the browser mocked, and an assertion that every lane records ≥ 1 inspected page with zero `target_url` states on same-origin URLs. That test is part of the fix plan.

### What remains unprovable

- **The exact wedged URL string per lane in MT-000237, and round 1's exact error subclass.** Both are unrecoverable from the records: exception text is stripped by design (`slop_run.py:1124–1126, 1435–1437`) and no worker traceback exists for these runs. The prototype proves the error-page resting state reproduces the production signature exactly, and the candidate first dominoes are enumerable (a navigation killed after commit — e.g. an egress-proxy 502; a redirect chain dying mid-flight; an idle-time client redirect) — but which one fired for each lane cannot be settled from the record. One live Klaviyo run with the probe line from the fix plan (exception class + message + claim URL + resting `session.page.url`, logged in the two catches at `slop_run.py:1406–1429` and `slop_run.py:1239`) names both.
- **Which of the two flip candidates (slop-layer edits vs frontier exposure) turned the unchanged machinery lethal** is narrowed but not pinned; it does not change the fix, because the wedge is a property of the pre-flight's design, not of either trigger.

### Pointers

- PC `.local\marley-skr\ANALYSIS-MT237-LANES.md` — the forensic synthesis (27 KB), with the exhaustive lane-0 vs lanes-1–3 difference table and the second-gates catalogue.
- PC `.local\marley-skr\DEEP-POLICY.md`, `DEEP-LANES.md`, `DEEP-DATA.md`, `DEEP-TESTS.md`, `DEEP-TIMELINE.md` — the five deep-dive slices.
- PC `.local\marley-skr\VERIFY-CODE.md`, `VERIFY-MECHANISM.md`, `VERIFY-DIFF.md`, `VERIFY-GATE-DATA.md` — the verification pass: code anchors, mechanism resolution, regression diff, numbers + gate.
- `~/workspace/lane-prototype/README.md` — the experimental reproduction: baseline, probes A/C, B, B2, D/D2, the bisection log, and the decisive-input statement. Runnable: `runner.py` (baseline), `scenarios.py` (probes).
- `~/workspace/lane-prototype/DEEP-EXTERNAL.md` — the external-patterns brief.
