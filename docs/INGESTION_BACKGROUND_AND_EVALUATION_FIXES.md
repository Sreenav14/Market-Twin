# Ingestion, application attachment, tracing, and evaluation follow-up

October 4, 2026. This extends [the workspace ingestion implementation](INGESTION_WORKFLOW_UI_AND_REVIEW.md).

## Problems found

| Symptom | Verified cause | Correction |
| --- | --- | --- |
| Deleting reviewed knowledge returned Method Not Allowed | The development API still had the previous routes loaded. | Added/verified the archive endpoint and reloaded the identified local API process. |
| Attaching knowledge to wiki returned Not Found | The hot-reloaded UI called the new attachment route, which was absent from the running API's OpenAPI document. | Reloaded the API, saved the attachment, and verified the set appears in wiki's test-creation form. |
| Uploading source appeared to take the whole model-generation time | The old request awaited extraction and generation before responding. | Store the source and queue record first; return 202 before the model call. |
| Knowledge preview failed | Worker logs showed incomplete structured output with finish_reason=length. | Make the output budget configurable, increase its default, and preserve a safe, specific truncation error through both HTTP boundaries. |
| Knowledge Worker traces were missing | Its startup never initialized instrumentation, and the builder imported a model function directly. | Initialize the existing OTLP exporter and LiteLLM instrumentor at worker startup; resolve the instrumented function from its module at call time. |
| Evaluation traces were missing | The visual verifier retained a function reference captured before instrumentation. | Resolve the module function at call time and add an evaluation.run parent span. |
| Completed tests lacked reports | The execution worker completed browser execution, but no persistent process invoked the existing evaluation workflow. | Add an independent evaluation worker that discovers completed tests without reports. |

The existing tracing flag, content-capture setting, LangSmith endpoint, and OTLP
headers were already configured locally. Missing LANGSMITH_* SDK variables were
not the cause: this project uses OpenTelemetry export rather than the LangSmith
SDK. No credentials were changed. The subsequent explicit model request selected
openai/gpt-6-luna through the existing .env model setting; compatibility and
verification are described below.

## Background ingestion

The current request and processing flow is:

```text
Ingest knowledge -> authenticated Control API -> original source in private storage
                 -> PostgreSQL source/version/pin + queued entry -> HTTP 202
                 -> Review knowledge with progress

API-owned dispatcher -> saved source -> private Knowledge Worker
                     -> existing extraction + KnowledgeBuilder
                     -> saved typed result or safe error
                     -> UI polling reveals the reviewable result
```

The dispatcher is owned by the API lifespan and has four bounded slots. It polls
persisted uploaded/processing records. A PostgreSQL session advisory lock owns
each job on a pinned connection; it is explicitly released, or the connection
is invalidated if cancellation/error prevents cleanup. Row transactions are
short and do not remain open during a model call.

Pending work survives browser navigation and API restarts. After a process crash,
an unfinished read-only generation can run again; this is not an exactly-once
model-call guarantee. A deleted set cannot be resurrected by a late worker result.

The UI opens Review as soon as the source is saved. Lists and detail pages poll
every 1.5 seconds while work is pending. Progress represents saved/generating
stages, not a measured token percentage. Review controls appear after generation;
failures show an error and offer Retry using the already stored original.

Uploads still transfer through the bounded multipart/spooled-file path. This
removes model latency from the upload response; it does not remove network or
object-storage upload time. Direct presigned uploads remain separate future work.

## Naming, deletion, and application attachment

- A user can name the set before ingestion and rename a saved set afterward.
  Names are trimmed, required, and limited to 200 characters. Existing database
  uniqueness returns a conflict rather than silently overwriting another set.
- Delete archives the ProductBlueprint. Archived sets disappear from the active
  library and future test selection. Original source/version data and existing
  test configuration snapshots are retained.
- An approved set can attach to multiple active applications in its workspace.
  Attachment does not copy knowledge into each application or change its owner.
- Migration c82e73a9b114 adds knowledge.application_knowledge_entries and the
  ingestion-entry workspace/ID uniqueness required by its composite foreign key.
  Both application and ingestion references include workspace ID, preventing
  cross-workspace links at the database level. The migration is applied locally.
- Test creation lists approved knowledge attached to the selected application.
  The API also requires that attachment; client-side filtering is insufficient.
  Each test still freezes its selected approved content before agent creation.
- Existing permission checks apply: readers can review; writers can ingest,
  approve, rename, delete, and change attachments. Approval remains explicit.

All ingestion endpoints have prefix /api/v1/workspaces/{workspace_id}/ingestion:

| Method and suffix | Behavior |
| --- | --- |
| POST | Save original source and queued draft; return 202. |
| GET | List active sets; optional application_id filters attachments. |
| GET /{id} | Read the result, processing state, and safe error. |
| PATCH /{id} | Rename the set. |
| DELETE /{id} | Archive; return 204. |
| POST /{id}/retry | Requeue a failed entry; return 202. |
| POST /{id}/approve | Approve generated content after processing. |
| PUT /{id}/applications | Replace attachments with validated workspace applications. |
| GET /{id}/source-access | Authorize and sign original-source access. |

## Output budget and tracing

KNOWLEDGE_MODEL_MAX_OUTPUT_TOKENS defaults to 16384 instead of the former fixed
8192. It must be positive and can be lowered for a replacement model's limits.
The previous gpt-4o-mini model supports up to 16,384 output tokens, according to its
[official model documentation](https://developers.openai.com/api/docs/models/gpt-4o-mini).
The initial default increase to 16K addressed observed truncation. A later
32K trial during model migration was reverted: Luna's successful document output
fit within 16K. Current local KNOWLEDGE_MODEL_MAX_OUTPUT_TOKENS is 16384.
If output grows again, inspect duplicate/noisy selection before increasing the
budget. A token limit never establishes semantic correctness.

Knowledge and evaluation reuse MARKETTWIN_OBSERVABILITY_ENABLED,
MARKETTWIN_OBSERVABILITY_CAPTURE_CONTENT, OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
and OTEL_EXPORTER_OTLP_HEADERS. The worker declares its LiteLLM instrumentation
dependency explicitly. No second callback exporter or LangSmith SDK is added.
The content flag controls prompt, result, and image capture; disabled tracing
does not initialize the exporter. Shutdown flushes queued spans.

Look for knowledge.preview and evaluation.run in the existing LangSmith project.
Model calls are child LLM spans. An evaluation using only deterministic checks
has no LLM calls. This uses LangSmith's documented
[non-LangChain OpenTelemetry integration](https://docs.langchain.com/langsmith/trace-with-opentelemetry)
and the instrumentor's documented
[LiteLLM support](https://github.com/Arize-ai/openinference/blob/main/python/instrumentation/openinference-instrumentation-litellm/README.md).

## Evaluation and reports

Run the evaluation process separately from the execution worker:

```powershell
uv run --env-file .env python -m markettwin_evaluation_worker.worker
```

PostgreSQL completed-test state is its durable input; a persisted version-1
report is its completion marker. It checks every five seconds and processes one
test at a time using the existing deterministic, visual, finding, and report
components. This independently scheduled V1 path does not add an evaluation
Kafka topic or change browser execution.

A pinned advisory lock prevents concurrent evaluation of the same test. The
manual run_evaluation.py script uses that same claim/completion path. A restart
discovers unfinished evaluation again. Evaluation failures release ownership
and roll back uncommitted findings/report data before retrying. The existing
runtime snapshot may already be committed; subsequent attempts reuse it.
Browser actions are not replayed. The UI's existing completed-run results poll
reveals the report when it is ready.

## Verification and limits

Verification covers ordinary Python regressions, real PostgreSQL attachment and
archive behavior inside a rolled-back transaction, UI unit tests, desktop/mobile
workflow and accessibility checks, focused type/lint checks, and a production
web build. Final check results are recorded below.

The live synthetic ingestion check returned 202 in 1.06 seconds, transitioned
queued -> processing -> ready, and finished in 10.38 seconds without errors.
Its knowledge.preview trace was visible in the configured LangSmith project.
The disposable set was archived and its temporary API login logged out.

The actual approved MARKETTWIN_COMPLETE_PROJECT_HANDOFF set was attached to wiki
through the live UI. The wiki test form then offered that set for selection.
No test was created or started by this attachment check.

The diagram relationship-quality limitation is deliberately deferred at the
user's request. The live relationship evaluation reproduced omitted directed
edges even though categories and evidence ordinals were correct. Its opt-in
regression is retained for a later model change; no source-specific relation
patch was added. The subsequent requested Luna migration verifies transport
and real outputs, but does not establish complete diagram relationship recall.

Existing supported formats remain unchanged. This remains one-source ingestion
with whole-set approval, not arbitrary binary-format support, multi-source
revision editing, or normalized per-item persistence. The execution worker's
one-owner browser recovery policy remains unchanged and is not horizontally
scalable without execution leases. Evaluation and ingestion use PostgreSQL
ownership for their own read-only processing jobs.


## Canonical persistence decision

For V1, IngestionEntry.preview is the canonical generated and approved knowledge
snapshot. Approval metadata belongs to BlueprintVersion; test creation freezes
the approved snapshot into each test configuration. The legacy
KnowledgeIngestionService/persist_pdf_skills.py path writes experimental
normalized drafts and is explicitly labeled as such. It is not invoked by the
public ingestion, approval, attachment, or planning flow. Existing normalized
Evidence/Skill tables and regression tests are retained. Before adding incremental
reconciliation or version updates, either migrate approval into that domain or
retire the experiment; do not mix both as canonical production writes.

## Transient failure handling

A dispatch attempts the private worker at most three times. HTTP 502, 503, and
504 retry after two and four seconds; each attempt rewinds the same downloaded
source stream. The entry remains processing throughout, retaining the advisory
lock without an open row transaction. Unsupported/unreadable/oversized sources
fail immediately. A known output-limit failure is also terminal: repeating the
same bounded request does not repair selection or truncation. The final failure
is saved for review and manual Retry. Attempts are bounded per dispatch; process
crash recovery can start a new dispatch, not a lifetime-global retry counter.

## Environment-driven model selection

MODEL_NAME is a provider-qualified LiteLLM identifier. Text knowledge, Meta and
Persona agents, reconciliation, and visual evaluation use it. IMAGE_MODEL_NAME,
VIDEO_MODEL_NAME, and VISUAL_MODEL_NAME are optional explicit workload overrides;
when absent, their paths use MODEL_NAME. Provider-qualified agent models determine
the provider, while the existing Ollama connection/context settings remain
supported. Provider credentials and media capabilities must match the selected
model; selecting a text/image model does not give it native video support.

The active local model is openai/gpt-6-luna. The installed LiteLLM version did
not recognize its reasoning parameter and initially sent an unsupported
max_tokens request. Shared completion_parameters now sends
max_completion_tokens for OpenAI, forwards the explicitly configured
MODEL_REASONING_EFFORT through allowed_openai_params, and omits temperature when
reasoning is enabled. Other providers keep their own max_tokens parameter and
do not inherit the OpenAI reasoning override. Current local effort is none,
required for Luna function calling on the existing Chat Completions agent path.
No endpoint/tool-handler migration or source-specific semantic patch was needed.
See [official Luna documentation](https://developers.openai.com/api/docs/models/gpt-6-luna)
and [GPT-6 compatibility guidance](https://developers.openai.com/api/docs/guides/latest-model).

Restart affected workers after editing .env; existing processes retain their
startup environment. Historic runtime snapshots and existing reports keep their
original model/configuration rather than being rewritten. Knowledge and evaluation
workers are running locally with Luna. Evaluation visual snapshots record actual
request parameters; agent snapshots retain their semantic max_tokens budget and
record configured reasoning effort.

The failed MARKETTWIN_COMPLETE_PROJECT entry (25dcb61c-9803-431d-8f5d-661bc7730a9a)
was retried through the live UI after worker reload. It is now ready with seven
knowledge items, three artifacts, three Skills, and no processing error. LangSmith
shows its successful knowledge.preview trace f246fbcdd712392ed0a8196574c0cf8d
with 17.74 seconds latency and 14.39K total tokens. Total usage already includes
input, so its output fit below the restored 16K output budget. The user's subsequent
img.Test source also became ready with one context item and no forced artifact
or Skill; its trace is 9205e299fba67effb0e38f306718d7d0.

A separate synthetic function-call check returned model gpt-6-luna,
finish_reason=tool_calls, and verify_setup({ready:true}). No browser action was
executed by that check.

## Frontend/API port consistency

Vite reads CONTROL_API_PORT from the repository-root environment rather than
hardcoding 8001. Its fallback, .env.example, and Control API Settings all use
8000. The current local .env deliberately uses 8001, matching the verified running
API and avoiding interruption of the separate existing 8000 process. No credentials
are exposed to the browser; the proxy reads only CONTROL_API_ variables. Restart
Vite after changing these server settings; explicit uvicorn --port must match.

## Completed report recovery

The evaluation worker completed the three previously missing reports:

| TestRun | Report |
| --- | --- |
| 6c88583f-78fa-4016-bfe3-e52785c5c71f | ac088886-93b5-4578-b092-f3f153d8b81f |
| d5ee75e6-df5e-4d14-94a8-ed6e466d0f32 | 3802a64c-172b-44ec-99d3-360f67052d17 |
| 94a72bdf-33e7-4ed7-a0d8-0b34c1ecb606 | ca481640-c935-4979-9894-0c6a1c883153 |

All three authenticated results endpoints returned 200. Their evaluation.run
traces are visible in the existing LangSmith project, with trace IDs
4c4fc09d566fde9183668402504b284d, 242a30ade9247a6c21d726bbfed502f0, and
48f845d7bf35b06a18955db435507e46. No browser executions were replayed.

## Remaining production boundaries

V1 bounded ingestion works, including the streamed 50 MB upload limit.
Production upload hardening remains: presigned direct browser-to-object-storage
upload and API completion confirmation. This change does not implement it.

Planning can currently select up to ten attached knowledge sets and includes
their full approved JSON. Before larger deployments, add goal-based relevant-item
selection and a character/token budget. RAG is not required for that next step.
This is documented follow-up work, not added orchestration in this increment.


## Final verification

- Full ordinary Python suite: **315 passed, 12 skipped** (52.41 seconds). Skips
  are explicitly opt-in database/model checks, not silently ignored failures.
- Real PostgreSQL attachment/archive regression: **1 passed**, with test data
  rolled back. Cross-workspace attachment rejection was verified.
- UI unit suite: **23 passed**. Final frontend TypeScript check passed and
  production build passed (5.28 seconds).
- Desktop and mobile ingestion/review/attachment/test-selection E2E: **2 passed**
  sequentially. Seven states in each browser passed accessibility and horizontal
  overflow assertions. The expanded workflow has a 60-second total test budget;
  individual expectations retain their normal timeouts.
- Transient-retry/client suite: **15 passed**. It verifies source rewind,
  recovery from 502/503/504, terminal 415/422/output-limit handling, and exhaustion.
- Focused runtime type check: **0 errors**. Focused Ruff check and git diff
  whitespace check passed. Whole-repository typing still has pre-existing errors
  outside this scope; this is not a claim that the entire repository is type clean.
- Executed Vite configuration checks returned 8001 for the local setting, 8123
  for an override, and 8000 when unset/empty.
- Live ingestion, model function calling, three report endpoints, and both
  LangSmith trace families were verified as described above.

## Separate Kafka diagnostic

After the final API reload, the outbox relay logged SSL record-layer failures
for advertised broker 1. A read-only metadata and TLS check established:
bootstrap hostname TLS succeeds; advertised broker 2 TLS succeeds; broker 1's
advertised IP fails TLS when used as the server name, but succeeds when the
configured bootstrap hostname is used as TLS SNI. This points to a broker
advertisement/SNI routing mismatch; it is not evidence that Luna or ingestion
broke Kafka. Kafka server/advertised-name configuration needs correction before
claiming execution delivery is healthy. This change does not disable certificate
verification, change broker settings, or hide the connection error.


## Cleanup

Removed the explicitly identified temporary pytest work directories and the
desktop/mobile E2E output directory after inspection. Its 14 UI screenshots were
test artifacts only. Original uploaded files, stored knowledge sources, runtime
evidence, durable regression tests, and implementation documentation are retained.
