# Knowledge Worker UI bridge implementation

> Historical first-preview report. The Application tab and public route below
> were replaced following the user's workspace reuse and approval requirements.
> See [Workspace Ingestion, review, and test selection](INGESTION_WORKFLOW_UI_AND_REVIEW.md)
> for the current routes, persistence, startup instructions, and verification.

This records the first, temporary source preview described in
[`MARKETTWIN_KNOWLEDGE_WORKER_UI_BRIDGE.md`](../MARKETTWIN_KNOWLEDGE_WORKER_UI_BRIDGE.md).
The boundary is deliberately synchronous and handles one source per request. It
does not create a Source Asset, persist generated knowledge, or approve Skills.

## Resulting request path

1. A user opens an application's **Knowledge** tab and selects one file. The
   browser sends `multipart/form-data` with a single `file` field to
   `POST /api/v1/applications/{application_id}/knowledge/preview`. The browser
   includes the existing session credentials and does not set the multipart
   `Content-Type` header itself, allowing the browser to add the boundary.
2. The Control API resolves the session, checks that the application is active
   and visible to the user, then requires a workspace write role. A read-only
   member cannot submit a preview. The Control API forwards the file through
   `KnowledgeWorkerClient`; React never contacts the worker directly.
3. The worker's private `POST /internal/v1/knowledge/preview` writes the upload
   in 1 MiB chunks to a temporary directory, rejecting empty uploads, unsafe
   filenames, and files exceeding `KNOWLEDGE_PREVIEW_MAX_BYTES` (50 MiB by
   default). It passes the temporary path through the existing
   `extract_source()` dispatcher and `KnowledgeBuilder.build()`.
4. The worker returns typed source counts, application knowledge, artifacts,
   Skills, evidence ordinals and locators, and extraction issues. The UI shows
   each category separately, including meaningful empty states. Temporary
   source files are removed as the request exits, including error or
   cancellation paths. The response omits local source paths, `media_path`,
   media bytes, and base64 data.

The common Python DTOs are in
`packages/shared-python/src/markettwin_shared/knowledge_preview.py`. They reuse
the existing knowledge draft contracts; there is no second builder schema.
Worker code lives in `services/knowledge-worker/src/markettwin_knowledge_worker/`
(`main.py`, `api/preview.py`, `services/knowledge_preview_service.py`). The
Control API adapter lives in `services/control-api/src/markettwin_control_api/`
(`api/knowledge_preview.py`, `knowledge/client.py`). The React route, page, and
API helper live under `apps/web/src/`.

## Configuration and operation

The new `.env.example` settings are:

| Setting | Default | Purpose |
| --- | --- | --- |
| `KNOWLEDGE_WORKER_URL` | `http://127.0.0.1:8010` | Private worker base URL used by the Control API. |
| `KNOWLEDGE_MODEL_TIMEOUT_SECONDS` | `180` | Existing model call timeout; shown for comparison. |
| `KNOWLEDGE_PREVIEW_TIMEOUT_SECONDS` | `240` | Control API worker HTTP timeout; validated to exceed the model timeout. |
| `KNOWLEDGE_PREVIEW_MAX_BYTES` | `52428800` | Worker-side upload limit. |

Run the worker alongside the existing Control API and web app, for example:

```powershell
uv run --env-file .env uvicorn markettwin_knowledge_worker.main:app --host 127.0.0.1 --port 8010
```

The worker endpoint is intended for a private/local network and has no service
authentication in this increment. Do not publish `/internal/v1/knowledge/preview`
through public ingress. The public endpoint still requires an authenticated
session and workspace write access. This preview does not use Kafka, outbox, or
object storage. Large or long-running videos need the later asynchronous
ingestion flow rather than an indefinitely extended HTTP timeout.

## Error and data behavior

Unsupported source formats return 415. Empty, unreadable, or unsafe sources
return 422. Files over the limit return 413. Model/structured-output failures
return a safe 502 where identified; timeouts return 504. An unavailable worker
returns 503 from the Control API, and unexpected worker failures are not sent
to the browser as stack traces. Full exceptions remain in server logs.

The preview reflects the builder's current output. Application knowledge,
artifacts, and Skills are not forced into existence: an image may yield
knowledge with zero Skills. Evidence remains grounded by ordinal and a
source-specific locator (page, slide, sheet row, image number, or video time).
The UI uses those locators and does not invent source-derived metadata.

## Verification

- Worker route tests cover the existing extractor receiving an uploaded image,
  response redaction, temporary-file cleanup, unsupported format, size limit,
  invalid filename, empty source, and safe model errors.
- Control API tests cover missing authentication, application visibility,
  read-only denial, a writer's forwarding, actual multipart encoding by the
  private client, response validation, and safe error propagation.
- React tests cover multipart form behavior without a manually set content
  type, rendered empty Skill state, and preview interaction.
- The Knowledge Worker and Control API Python suites passed with a
  workspace-local pytest temp directory: **113 passed, 4 skipped** (database
  and live-model checks are opt-in). The first run used the system temp
  directory and failed during existing `tmp_path` fixture setup because that
  directory was inaccessible in the sandbox; rerunning with `--basetemp` in
  the workspace passed. The full React suite passed: **18 tests in 7 files**.
  Python lint/format and Pyright, React typecheck, and production build passed.
- The named `1_PB7v7MmW9NpdNn-_mfTj_A.png` was submitted through the real
  worker HTTP route with the builder call stubbed. The existing image extractor
  received the actual image bytes, returned one EvidenceUnit, and the HTTP
  response contained no `media_path`.

The complete live browser-to-model proof is **not yet verified**. The first
model attempt in the restricted sandbox failed to connect. A subsequent
unsandboxed attempt was rejected by automatic approval review because the
image would be sent to the externally configured model endpoint in `.env`
without explicit authorization for that destination. No model result was
obtained from that attempt. With an authorized model endpoint and the three
services running, open the application's Knowledge tab, select that image,
build the preview, and check the returned category counts and grounding in
the browser. This is the remaining external integration check; it does not
require changing the extractor or builder.
