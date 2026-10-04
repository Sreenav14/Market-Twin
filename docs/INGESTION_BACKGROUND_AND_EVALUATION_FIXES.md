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
SDK. No credentials or model selection were changed.

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
The configured gpt-4o-mini supports up to 16,384 output tokens, according to its
[official model documentation](https://developers.openai.com/api/docs/models/gpt-4o-mini).
A larger budget reduces this particular truncation risk; it does not guarantee
every document will fit or every generated claim will be correct.

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
web build. Exact final results and live evaluation results are recorded below
after the checks complete.

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
patch or model swap was added.

Existing supported formats remain unchanged. This remains one-source ingestion
with whole-set approval, not arbitrary binary-format support, multi-source
revision editing, or normalized per-item persistence. The execution worker's
one-owner browser recovery policy remains unchanged and is not horizontally
scalable without execution leases. Evaluation and ingestion use PostgreSQL
ownership for their own read-only processing jobs.
