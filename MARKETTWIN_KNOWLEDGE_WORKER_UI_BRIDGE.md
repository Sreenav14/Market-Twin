# MarketTwin — Knowledge Worker UI Bridge (Focused Implementation Plan)

**Scope:** Only the changes needed to let the React UI exercise the existing Knowledge Worker and `KnowledgeBuilder`.

**Goal:** Add the thinnest clean backend contract for UI testing **without changing the current ingestion architecture**.

---

# 1. What We Are NOT Changing

The current ingestion core should remain frozen.

Keep:

```text
extract_source(...)
    ↓
ExtractionResult
    ↓
KnowledgeBuilder().build(...)
    ↓
KnowledgeBuildResult
    ├── application_knowledge
    ├── artifacts
    └── skills
```

Do **not** change:

- `KnowledgeBuilder`
- document extractors
- image source adapter
- video source adapter
- evidence ordinals
- source locators
- batching
- consolidation
- Skill schema
- grounding rules
- current prompt architecture

The UI integration should sit **around** the existing pipeline.

---

# 2. Exact Problem We Are Solving

Today we can run:

```powershell
uv run --env-file .env python services/knowledge-worker/scripts/generate_source_skills.py "<file>" --include-evidence
```

and receive:

```json
{
  "source": {...},
  "application_knowledge": [...],
  "artifacts": [...],
  "skills": [...],
  "evidence": [...],
  "extraction_issues": [...]
}
```

That proves the Knowledge Worker works.

The missing piece is:

```text
React UI
   ↓
authenticated backend API
   ↓
existing Knowledge Worker
   ↓
existing KnowledgeBuilder
   ↓
same result shown in UI
```

We should **not create another generator or another prompt for the UI**.

---

# 3. Best-Practice Boundary

Use this boundary:

```text
React
   ↓
Control API
   ↓
Knowledge Worker preview API
   ↓
extract_source()
   ↓
KnowledgeBuilder().build()
   ↓
KnowledgeBuildResult
```

Why this is better than importing Knowledge Worker code directly into the Control API:

```text
Control API = user-facing control plane
Knowledge Worker = source processing + model reasoning
```

Keep those service responsibilities separate.

The Control API should **not** import and execute `KnowledgeBuilder` directly.

The React app should also **not** call the Knowledge Worker directly.

The browser should continue talking to the Control API.

---

# 4. First UI Bridge Is a Preview Contract

For the immediate UI-testing stage, add a **Knowledge Preview** API.

This is not approval.
This is not final persisted application knowledge.
This is not the production Kafka ingestion flow.

It is a legitimate long-term endpoint for previewing how MarketTwin understands a source before approval.

Recommended public endpoint:

```http
POST /api/v1/applications/{application_id}/knowledge/preview
```

Use:

```text
multipart/form-data
```

with one file.

Why call it `preview`:

- result is generated draft knowledge;
- it is not yet approved;
- application knowledge/artifacts are not fully persisted yet;
- it makes the lifecycle truthful;
- the endpoint can remain useful later instead of becoming throwaway code.

---

# 5. Public Control API Contract

## Request

```http
POST /api/v1/applications/{application_id}/knowledge/preview
Content-Type: multipart/form-data
```

Form field:

```text
file
```

One source per request.

Do not support multi-file preview in the first step.

---

## Response

The public response should be very close to the current CLI output:

```json
{
  "source": {
    "name": "architecture.png",
    "source_item_count": 1,
    "processed_item_count": 1
  },
  "application_knowledge": [],
  "artifacts": [],
  "skills": [],
  "evidence": [],
  "extraction_issues": []
}
```

Do **not** return the local filesystem path.

The CLI currently exposes:

```json
"path": "C:\..."
```

That is useful for development, but it should never be part of the browser-facing API.

---

# 6. UI-Facing Response Models

Create API DTOs instead of returning arbitrary dictionaries.

Recommended models:

```python
class KnowledgePreviewSourceResponse(BaseModel):
    name: str
    source_item_count: int
    processed_item_count: int


class KnowledgePreviewEvidenceResponse(BaseModel):
    ordinal: int
    evidence_type: str
    content_text: str | None = None
    content_json: dict[str, object] | None = None
    source_locator: dict[str, object]
    extractor_name: str
    extractor_version: str


class KnowledgePreviewIssueResponse(BaseModel):
    code: str
    message: str
    source_locator: dict[str, object]
    requires_fallback: bool


class KnowledgePreviewResponse(BaseModel):
    source: KnowledgePreviewSourceResponse
    application_knowledge: tuple[ApplicationKnowledgeDraft, ...]
    artifacts: tuple[ProcedureArtifactDraft, ...]
    skills: tuple[GeneratedSkillDraft, ...]
    evidence: tuple[KnowledgePreviewEvidenceResponse, ...]
    extraction_issues: tuple[KnowledgePreviewIssueResponse, ...]
```

Reuse the existing shared knowledge contracts for:

```text
ApplicationKnowledgeDraft
ProcedureArtifactDraft
GeneratedSkillDraft
```

Do not duplicate those schemas in the Control API.

---

# 7. Important Media Rule

For image/video evidence, the response should **not** include:

```text
base64 image
base64 video
local media_path
temporary clip paths
```

The evidence response should remain small:

```json
{
  "ordinal": 1,
  "evidence_type": "image",
  "content_json": {
    "media_type": "image/png"
  },
  "source_locator": {
    "image": 1
  }
}
```

For video:

```json
{
  "ordinal": 2,
  "evidence_type": "video_segment",
  "source_locator": {
    "start_seconds": 85.0,
    "end_seconds": 175.0
  }
}
```

This is enough for the first UI result screen.

Actual source preview can be added later through stored-source access.

---

# 8. Knowledge Worker Change

Do not put HTTP/serialization logic inside `KnowledgeBuilder`.

Add one small application service around the existing pipeline.

Recommended file:

```text
services/knowledge-worker/src/markettwin_knowledge_worker/services/knowledge_preview_service.py
```

Conceptually:

```python
class KnowledgePreviewService:
    async def preview(self, source_path: Path) -> KnowledgePreview:
        extraction = await extract_source(source_path)

        try:
            result = await KnowledgeBuilder().build(extraction)
        finally:
            # KnowledgeBuilder already owns extraction cleanup_paths.
            # Do not duplicate media cleanup here.
            pass

        return KnowledgePreview(
            extraction=extraction,
            result=result,
        )
```

Prefer injecting `KnowledgeBuilder`:

```python
class KnowledgePreviewService:
    def __init__(self, builder: KnowledgeBuilder) -> None:
        self._builder = builder
```

Then:

```python
result = await self._builder.build(extraction)
```

This makes focused tests easy.

---

# 9. Preview Result Contract Inside Knowledge Worker

Use a tiny internal dataclass:

```python
@dataclass(frozen=True, slots=True)
class KnowledgePreview:
    extraction: ExtractionResult
    result: KnowledgeBuildResult
```

That is enough.

Do not add another semantic domain model.

Do not flatten everything inside the Knowledge Worker merely because HTTP needs JSON.

HTTP transformation belongs at the API boundary.

---

# 10. Knowledge Worker HTTP Adapter

Add a very small internal HTTP surface to the Knowledge Worker.

Recommended:

```text
services/knowledge-worker/src/markettwin_knowledge_worker/api/preview.py
services/knowledge-worker/src/markettwin_knowledge_worker/main.py
```

Internal endpoint:

```http
POST /internal/v1/knowledge/preview
```

This endpoint is not browser-facing.

Its job is only:

```text
receive temporary source
↓
write it safely to temp file
↓
KnowledgePreviewService.preview(...)
↓
serialize result
↓
return
```

Do not put application/workspace authorization in the Knowledge Worker.

That belongs to the Control API.

---

# 11. Temporary File Handling

Because all existing source adapters operate on `Path`, the HTTP adapter should write the upload to a temporary directory.

Use:

```python
TemporaryDirectory
```

or `mkdtemp()` with explicit cleanup.

Conceptual:

```python
with TemporaryDirectory(prefix="markettwin-preview-") as root:
    source_path = Path(root) / safe_filename
    await write_upload(source_path, upload)
    preview = await service.preview(source_path)
```

Best practices:

- never use the user filename as an arbitrary filesystem path;
- use only the basename;
- reject empty filenames;
- do not allow `../`;
- always clean the temporary directory;
- do not retain preview files after the request;
- do not expose the temp path in the response.

---

# 12. Preview Size Limit

This synchronous preview route should have an explicit limit.

Why:

```text
React → Control API → Knowledge Worker
```

is appropriate for UI semantic testing, but should not become the final transport for multi-GB media.

Add configuration such as:

```text
KNOWLEDGE_PREVIEW_MAX_BYTES
```

Choose a practical development/V1 value based on the actual sources you are testing.

Do not hardcode the limit into React.

If the file is too large:

```http
413 Payload Too Large
```

with safe message:

```text
This source is too large for knowledge preview.
```

Later, the production ingestion path uses object storage + background processing.

The preview API can remain for bounded interactive preview.

---

# 13. Do Not Read Huge Uploads Into Memory

Avoid:

```python
content = await upload.read()
```

for the whole file.

Stream in chunks to disk:

```python
while chunk := await upload.read(CHUNK_SIZE):
    ...
```

Track total bytes while writing.

Stop once the configured preview limit is exceeded.

This matters especially for video.

---

# 14. Supported Formats

Do not maintain a second manual extension list in the API if possible.

Let:

```python
extract_source(source_path)
```

remain authoritative.

Map:

```python
UnsupportedSourceFormatError
```

to:

```http
415 Unsupported Media Type
```

This prevents the API and dispatcher from drifting.

---

# 15. Knowledge Worker Error Mapping

The internal Knowledge Worker endpoint should return clean error types.

Suggested mapping:

```text
UnsupportedSourceFormatError
→ 415

empty/invalid source
→ 422

KnowledgeBuilder incomplete structured response
→ 502

model/provider timeout
→ 504

unexpected internal failure
→ 500
```

Do not return stack traces to the Control API response.

Log full exceptions server-side.

---

# 16. Control API Endpoint

Recommended new file:

```text
services/control-api/src/markettwin_control_api/api/knowledge_preview.py
```

Public route:

```python
@router.post(
    "/api/v1/applications/{application_id}/knowledge/preview",
    response_model=KnowledgePreviewResponse,
)
```

Responsibilities:

```text
1. authenticate user
2. load application
3. verify workspace/application access
4. require write permission
5. require active application
6. accept one upload
7. call internal Knowledge Worker preview endpoint
8. translate safe errors
9. return typed response
```

Nothing more.

---

# 17. Reuse Existing Application Authorization

The repository already has:

```text
get_authenticated_user_id(...)
ApplicationRepository.get_for_user(...)
WORKSPACE_WRITE_ROLES
```

Use the same authorization model as other application-management endpoints.

Do not create a separate Knowledge-specific permission system now.

Rule:

```text
User may preview knowledge when:
- they can access the Application;
- their workspace role has write permission;
- application is active.
```

Read-only viewing can be added once preview results are persisted.

For the first synchronous preview request there is nothing durable for read-only users to revisit.

---

# 18. Control API → Knowledge Worker Client

Do not scatter raw `httpx` calls inside the route.

Add a narrow client/service.

Example:

```text
services/control-api/src/markettwin_control_api/knowledge/
    client.py
```

Conceptual:

```python
class KnowledgeWorkerClient:
    async def preview(
        self,
        *,
        filename: str,
        content_type: str | None,
        stream: ...
    ) -> KnowledgePreviewResponse:
        ...
```

The route should remain thin.

---

# 19. Knowledge Worker URL Configuration

Add server configuration:

```text
KNOWLEDGE_WORKER_URL
```

Example locally:

```text
http://127.0.0.1:8010
```

Do not hardcode service hostnames into route code.

Production can later use internal service discovery.

---

# 20. Internal API Authentication

For local development, services may initially communicate only on the private/local network.

But keep the design ready for internal authentication.

Do not expose:

```text
/internal/v1/knowledge/preview
```

through the public ingress in production.

Long-term options:

```text
private VPC/service network
service identity
signed internal token
mTLS
```

Do not implement complex service auth before there is production infrastructure requiring it.

---

# 21. Timeout Behavior

The current Knowledge Builder already has:

```text
KNOWLEDGE_MODEL_TIMEOUT_SECONDS
```

The Control API client timeout must be slightly larger than the worker/model timeout.

Example principle:

```text
model timeout = 180s
worker HTTP timeout > 180s
Control API request timeout > worker timeout
```

Do not set the proxy timeout shorter than model timeout.

For large/long-running video, use the later async ingestion path instead of raising synchronous preview timeout indefinitely.

---

# 22. Cancellation

If the browser cancels the public request:

```text
Control API request cancelled
↓
internal request should be cancelled
↓
Knowledge Worker coroutine should be cancelled
↓
video temporary clips should still clean up
```

Your current video extractor already has cleanup behavior around cancellation.

Do not catch `CancelledError` and convert it into a generic 500.

Let cancellation propagate while cleanup runs.

---

# 23. UI Contract Should Match Existing Builder Output

React should receive:

```text
application_knowledge
artifacts
skills
evidence
extraction_issues
```

Do not return only Skills.

Do not create:

```text
/image-preview
/video-preview
/document-preview
```

separate semantic endpoints.

One endpoint should support all current source formats through the existing dispatcher.

That is the entire value of the current ingestion architecture.

---

# 24. React API Method

In:

```text
apps/web/src/lib/api.ts
```

add a separate multipart request helper.

The current generic request helper always sets:

```text
Content-Type: application/json
```

Do not use that for `FormData`.

Add something like:

```ts
async function requestForm<T>(
  path: string,
  form: FormData,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    credentials: "include",
    body: form,
    signal,
  });

  ...
}
```

Important:

**Do not manually set `Content-Type` for FormData.**

The browser must add the multipart boundary.

---

# 25. React API Method Shape

Add:

```ts
previewApplicationKnowledge: (
  applicationId: string,
  file: File,
  signal?: AbortSignal,
) => {
  const form = new FormData();
  form.append("file", file);

  return requestForm<KnowledgePreviewResponse>(
    `/api/v1/applications/${applicationId}/knowledge/preview`,
    form,
    signal,
  );
}
```

That is the only frontend API method needed for the first step.

---

# 26. TypeScript Types

Mirror the backend contracts.

Add:

```ts
type GroundingConfidence = "low" | "medium" | "high";
```

and interfaces for:

```text
ApplicationKnowledgeDraft
ProcedureArtifactDraft
SkillDefinition
GeneratedSkillDraft
KnowledgePreviewEvidence
KnowledgePreviewIssue
KnowledgePreviewResponse
```

Do not use:

```ts
any
```

for the generated knowledge structures.

`source_locator` can remain:

```ts
Record<string, unknown>
```

because locator shape varies by source format.

---

# 27. First UI Page After API Exists

Only after the thin API works, create:

```text
/applications/:applicationId/knowledge
```

First UI version should be tiny:

```text
Knowledge

[ Choose file ]
[ Build preview ]

Processing...

Application Knowledge
...

Artifacts
...

Skills
...

Evidence
...
```

Do not build source persistence, source history, approval, filters, or a complex upload manager yet.

The purpose is to test the semantic pipeline from the actual browser.

---

# 28. Evidence Rendering in First UI

Use deterministic locator formatting.

Examples:

```text
PDF
Pages 3–5

PowerPoint
Slides 2–4

XLSX
Sheet Plans, rows 1–20

Image
Image 1

Video
01:30–03:00
```

No exact-line requirement.

Do not display raw dictionaries as the primary UI.

---

# 29. What NOT to Add Yet

Do not add:

```text
new database tables for Application Knowledge
new Artifact persistence
approval workflow
source history
Kafka integration
S3/MinIO upload workflow
vector database
RAG
knowledge search
manual Skill editing
source-specific UI logic
another model call
semantic verifier agent
```

Those are separate increments.

This step is only:

```text
browser
→ API
→ existing KnowledgeBuilder
→ browser
```

---

# 30. Why This Is Not Throwaway Work

The preview endpoint remains useful even after asynchronous persisted ingestion exists.

Future product can support:

```text
Preview source
↓
review generated draft
↓
Add to application knowledge
```

while production ingestion supports:

```text
Upload source
↓
background durable processing
↓
approval
```

So the preview contract is a legitimate product capability, not merely a test hack.

The only V1 restriction is its bounded synchronous file size.

---

# 31. Knowledge Worker Files to Add/Change

Recommended Knowledge Worker changes:

```text
ADD
services/knowledge-worker/src/markettwin_knowledge_worker/services/knowledge_preview_service.py

ADD
services/knowledge-worker/src/markettwin_knowledge_worker/api/__init__.py

ADD
services/knowledge-worker/src/markettwin_knowledge_worker/api/preview.py

ADD
services/knowledge-worker/src/markettwin_knowledge_worker/main.py

CHANGE
services/knowledge-worker/pyproject.toml
- FastAPI/uvicorn only if not already available through workspace dependencies

CHANGE
.env.example
- KNOWLEDGE_PREVIEW_MAX_BYTES
- KNOWLEDGE_WORKER_URL (Control API side)
```

Do not modify `knowledge_builder.py` unless a real bug is discovered.

---

# 32. Control API Files to Add/Change

Recommended:

```text
ADD
services/control-api/src/markettwin_control_api/api/knowledge_preview.py

ADD
services/control-api/src/markettwin_control_api/knowledge/__init__.py

ADD
services/control-api/src/markettwin_control_api/knowledge/client.py

CHANGE
services/control-api/src/markettwin_control_api/main.py
- include knowledge preview router

CHANGE
services/control-api/src/markettwin_control_api/config.py
- KNOWLEDGE_WORKER_URL
- internal request timeout
```

Keep the route thin.

---

# 33. React Files for the Very Next UI Step

After backend contract is proven:

```text
CHANGE
apps/web/src/lib/api.ts

CHANGE
apps/web/src/app/router.tsx

ADD
apps/web/src/pages/applications/ApplicationKnowledgePage.tsx
```

That is enough for the first browser smoke.

Do not build a large component tree immediately.

---

# 34. Worthwhile Tests Only

## Knowledge Worker

Add focused tests for:

```text
preview service calls extract_source + KnowledgeBuilder
unsupported source returns expected error
temporary upload file is cleaned
file size limit is enforced
```

Do **not** mock-test every KnowledgeBuilder field again.

Its own tests already own semantic contract behavior.

## Control API

Add:

```text
unauthenticated → denied
user without application access → denied
read-only workspace role → denied
valid writer → worker client called
worker 415/422/502 → safe mapped response
```

## React

Initially:

```text
multipart request helper does not set JSON Content-Type
preview response renders all three categories
empty Skills renders as valid empty state
```

No large E2E suite yet.

---

# 35. First End-to-End Proof

Use the exact image you are already testing.

Flow:

```text
1. Start Knowledge Worker HTTP service.
2. Start Control API.
3. Start React.
4. Open an Application.
5. Open Knowledge.
6. Select:
   1_PB7v7MmW9NpdNn-_mfTj_A.png
7. Click Build preview.
8. Browser calls Control API.
9. Control API authenticates and forwards source.
10. Knowledge Worker calls existing extract_source().
11. Existing ImageExtractor creates one image EvidenceUnit.
12. Existing KnowledgeBuilder receives the actual image.
13. Result returns through Control API.
14. UI displays:
    - application knowledge
    - artifacts
    - skills
    - evidence
    - extraction issues
15. Confirm output matches the CLI architecture.
```

The exact wording may differ between model runs.

The architectural result shape must match.

---

# 36. Definition of Done for This Increment

This increment is complete when:

```text
✓ KnowledgeBuilder itself was not duplicated or rewritten.
✓ React can upload one supported source for preview.
✓ Control API authenticates/authorizes the request.
✓ React never calls Knowledge Worker directly.
✓ Knowledge Worker receives the actual file.
✓ Existing extract_source() is used.
✓ Existing KnowledgeBuilder().build() is used.
✓ Image/video native media behavior remains unchanged.
✓ Result contains application knowledge + artifacts + skills.
✓ Evidence ordinals and locators are returned.
✓ Local paths/media_path/base64 are not exposed to React.
✓ Temporary files are always cleaned.
✓ Unsupported format fails cleanly.
✓ Cancellation does not leak video clips/temp files.
✓ The architecture image can be tested completely from UI.
```

---

# 37. After This Works

Only then move to the next UI increment:

```text
Application Knowledge page
↓
better cards/tabs/evidence presentation
```

After semantic quality is acceptable:

```text
persistent sources
↓
persistent Application Knowledge / Artifacts / Skills
↓
human approval
↓
Meta Agent consumption
```

Do not mix those changes into this first bridge.

---

# 38. Final Rule

The next code should be only this:

```text
React
↓
thin authenticated Control API contract
↓
thin Knowledge Worker HTTP adapter
↓
existing extract_source()
↓
existing KnowledgeBuilder
↓
typed KnowledgePreviewResponse
↓
React
```

Everything semantic stays exactly where it is today.
