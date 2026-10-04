# Workspace Ingestion, review, and test selection

## Scope and decisions

This completes the UI bridge around the existing Knowledge Worker and applies
the subsequent product corrections: knowledge belongs to the workspace, is
reusable across Applications, has its own sidebar pages, and is selected
explicitly when creating a test. The sidebar calls the upload area **Ingestion**;
the upload action is **Ingest knowledge**. **Review knowledge** is a separate
sidebar destination.

The original `MARKETTWIN_KNOWLEDGE_WORKER_UI_BRIDGE.md` described a temporary,
Application-scoped preview. The later user instructions supersede its location
and its restrictions on persistence and approval. Its service boundary and
semantic-core restrictions are still followed: React calls Control API, Control
API calls the worker, and the worker reuses `extract_source()` and
`KnowledgeBuilder.build()`. No second generator, prompt, extraction dispatcher,
or source-specific UI pipeline was introduced.

This is a bounded synchronous ingestion increment. It is not a new Kafka
ingestion worker or a claim that arbitrary file types and arbitrarily large
videos are supported. Existing extractor capabilities remain authoritative.

## Navigation research and rationale

The previous Application tab put a reusable workspace resource under an
individual product. It also made previewing and approving look like one task.
The revised journey uses task-oriented destinations:

1. Open **Ingestion** from the workspace sidebar or Overview.
2. Choose a source, name the knowledge set, and choose its purpose.
3. Click **Ingest knowledge**. Processing stays on this page with a visible status.
4. Review the saved draft on its own page, including source locators and issues.
5. Download the original source, check the generated content, confirm the source
   purpose, and explicitly approve the set.
6. Open an Application and create a test. Choose one or more approved sets in the
   test form before creating the run and before agent planning begins.

Task-oriented categories and descriptive destination labels improve
findability; this motivated keeping Ingestion and Review knowledge visible at
workspace level. See [NN/g: information architecture mistakes](https://www.nngroup.com/articles/3-ia-mistakes/).
The separate review stage follows the principle of giving users a chance to
check information before committing it, described by [GOV.UK: check answers](https://design-system.service.gov.uk/patterns/check-answers/).
Knowledge sets use checkboxes because multiple selections are allowed, and
nothing is preselected; see [GOV.UK: checkboxes](https://design-system.service.gov.uk/components/checkboxes/).
Source purpose uses a single select rather than a difficult native multiselect;
see [GOV.UK: select](https://design-system.service.gov.uk/components/select/).

These are design references, not a claim that a human usability study was
conducted. Verification used real desktop and mobile browsers, keyboard and
workflow assertions, screenshots inspected visually, and automated accessibility
checks. A later tree test with users could validate whether the labels match
their expectations; [NN/g: tree testing](https://www.nngroup.com/articles/tree-testing/)
describes that research method.

## What changed and why

### UI structure and visual consistency

- Added `/ingestion`, `/knowledge/review`, and `/knowledge/review/:entryId`.
- Removed the Application knowledge tab. Its old route redirects to Ingestion
  so existing bookmarks reach the new workspace destination.
- Updated sidebar, breadcrumbs, command menu, and Overview entry points.
- Reused existing dark theme tokens, panels, typography, inputs, buttons,
  loading/error states, icons, and responsive list conventions.
- Split the result renderer from the old upload page. Application knowledge,
  artifacts, Skills, evidence, and extraction issues remain separate categories.
  Zero Skills is a valid outcome; the UI does not manufacture capabilities.
- Kept source-purpose choices generic. The browser does not maintain a second
  extension allowlist. Unsupported formats fail through the existing dispatcher.
- Added clear processing, failure, and retry behavior. A failed upload preserves
  the chosen file and form values; controls recover after failure.
- Added an explicit review checkbox before approval. Its state is scoped to the
  current workspace and set, so reviewing one set does not confirm another.
- Added original-source access with an authorized, short-lived signed URL. While
  the review page is active, it refreshes the link every two minutes; the signer
  uses a five-minute expiry. Source responses force attachment download and
  octet-stream rather than rendering user-declared HTML inline. Existing execution
  evidence URLs retain their previous behavior.
- Fixed a real visual defect found in screenshots: the existing list grid expects
  a leading icon. Evidence locators and source names had landed in its narrow
  first column. Restored that structure and grouped row actions, with wrapping
  at small widths. No global button-size or color reset was needed.

### Upload failure and service boundary

The file picker itself worked. Inspection found no knowledge HTTP worker
listening on port 8010, so the Control API could not forward the selected file.
Started the worker locally and verified its process startup. The existing API
was also running without the new routes loaded, so it was reloaded after
verifying its process identity. The user's Vite proxy change to
`http://127.0.0.1:8001` was preserved.

The request path is:

```text
React multipart upload
  -> authenticated workspace Control API
  -> private worker preview endpoint
  -> existing extractor + KnowledgeBuilder
  -> typed result
  -> private source storage + draft database transaction
  -> review UI
```

The browser sets the multipart boundary itself. Uploads are read in chunks for
size/hash validation and forwarded from the spooled file, without loading the
whole original into a Python byte string. The worker writes the temporary source
in chunks and removes its temporary directory on completion or failure. The
builder retains ownership of its existing media/clip cleanup.

### Public API and authorization

All routes below use `/api/v1/workspaces/{workspace_id}/ingestion`:

| Method and suffix | Behavior |
| --- | --- |
| `GET` | List source/set summaries in the authenticated workspace. |
| `POST` | Accept one multipart `file`, `name`, and one or more `roles`; generate and save a draft. |
| `GET /{entry_id}` | Return one saved typed result for review. |
| `POST /{entry_id}/approve` | Require write access and generated semantic content; approve under a database row lock. |
| `GET /{entry_id}/source-access` | Authorize workspace access before signing the exact original object for download. |

Existing session and workspace permissions are reused. Viewers can read but
cannot ingest or approve. Cross-workspace IDs are not accepted. Empty semantic
results cannot be approved. Approval records the user and timestamp and confirms
the pinned source roles.

Errors remain actionable and safe: unavailable worker/storage 503, unsupported
format 415, empty/unsafe/unreadable source 422, size limit 413, model/provider
failure 502, timeout 504, and duplicate set name 409. Provider details and stack
traces stay in server logs. Failed database transactions trigger source-object
cleanup; a cleanup failure is logged without masking the original error.

### Persistence uses the existing Source Asset boundary

Each successful upload creates existing `ProductBlueprint`, `BlueprintVersion`,
`SourceAsset`, `AssetVersion`, and `BlueprintVersionAsset` records. It stores
original bytes privately and records object location, size, SHA-256, declared
content type, source purpose, and review lifecycle on those existing entities.

Added just one table, `knowledge.ingestion_entries`, to hold the typed generated
result snapshot. Its ID is the Blueprint Version ID. Composite foreign keys
bind it to the same workspace, Blueprint, Blueprint Version, and Asset Version.
Approval and storage metadata are not duplicated in this table. Migration
`b41d7c210a33`, following `9edac11ff95c`, creates the table and workspace index.
The migration was applied to the local PostgreSQL database.

This snapshot preserves draft results for review. It does not create a second
Evidence service or persist every generated item into the existing normalized
Skill/Evidence repositories. The current increment approves a whole source set.

### Explicit selection reaches planning

`CreateTestRunRequest` now accepts optional `knowledge_entry_ids`, with at most
ten distinct UUIDs. The API resolves each ID within the run's workspace and
rejects missing or unapproved sets. No knowledge is selected automatically.

The run's existing `configuration_snapshot` freezes each selected set's ID,
name, source name, roles, application knowledge, artifacts, and Skills. This
keeps a run tied to the reviewed content it selected rather than later edits.
The run overview shows the selected names.

The execution request passes that snapshot into `MetaPlanningRequest` and the
planner context before agent creation. Instructions treat it as source-derived
context for relevant missions and expected behavior; it cannot override the
system rules, authorized target scope, or user testing goal. Existing runs with
no knowledge snapshot remain supported. The existing persona-count, mission,
and journey-allocation policy was not rewritten in this increment.

## Running locally

Use three terminals from the repository root. PostgreSQL and the configured
private S3/MinIO bucket must also be available. The model configuration remains
the existing `.env` configuration.

```powershell
uv run --env-file .env uvicorn markettwin_knowledge_worker.main:app --host 127.0.0.1 --port 8010
```

```powershell
uv run --env-file .env uvicorn markettwin_control_api.main:app --host 127.0.0.1 --port 8001
```

```powershell
cd apps/web
npm.cmd run dev
```

On a fresh database, apply the existing Alembic migrations through the project's
database configuration before using Ingestion. The local migration is already
applied for this workspace.

| Setting | Default | Purpose |
| --- | --- | --- |
| `KNOWLEDGE_WORKER_URL` | `http://127.0.0.1:8010` | Control API's private worker address. |
| `KNOWLEDGE_PREVIEW_MAX_BYTES` | `52428800` | Bounded upload limit, enforced by API and worker. |
| `KNOWLEDGE_MODEL_TIMEOUT_SECONDS` | `180` | Existing per-model timeout. |
| `KNOWLEDGE_PREVIEW_TIMEOUT_SECONDS` | `240` | Worker HTTP timeout; must exceed model timeout. |

The worker endpoint stays private. `/health` remains process health; these
changes do not make Control API health depend on Kafka or a model provider.

## Verification and remaining limits

- Python regression: **244 passed, 6 skipped** across Control API, Knowledge
  Worker, execution, shared contracts, and database model suites. Skips are
  explicit database/live-model opt-ins.
- Local PostgreSQL checks: **3 passed**, covering the saved source/version/pin
  boundary, approval metadata, and existing model constraints. Test records
  were rolled back.
- React unit suite: **19 passed in 7 files**.
- Desktop and mobile browser workflow: **2 passed**, using actual file inputs
  and multipart requests with controlled API responses. Checks include review
  gating, no automatic selection, draft exclusion, selection payload,
  evidence-locator width, populated lists, accessibility, and horizontal overflow.
- Broader browser regression: **56 of 60 passed initially**. The four failures
  were two assertions on each browser: the create payload now includes an empty
  knowledge selection, and the search term "tests" now matches Review knowledge
  as well as Tests. Updated those expectations and reran both affected flows
  plus ingestion on desktop/mobile: **6 passed**. The entire 60-test suite was
  not rerun after these assertion-only corrections.
- Python type checking passed with zero errors for the changed service/model
  boundaries; new adapters, contracts, migration, and focused tests passed lint.
- TypeScript checking and the production web build passed.
- Final local readiness check: Control API `/health` returned 200, its workspace
  ingestion routes were loaded, and the private worker preview route was loaded.

### Authorized live model check, October 4, 2026

After the user explicitly approved sending the architecture image to the
configured OpenAI model, the live authenticated API upload returned **201 in
9.12 seconds**. This used the real worker, existing image extractor, and model
call, with no stubbed builder or API response. The generated draft was fetched
again from the API and displayed and visually inspected in the live Chrome UI.

The saved draft is **Architecture image — live verification**, entry
`8248fe34-a6af-4a88-9376-46c4c468ef5f`. Results were two application-knowledge
items, one artifact, one Skill, one image EvidenceUnit at ordinal 1, and no
extraction issues. The downloaded stored original matched the local image's
SHA-256, and the signed response forced attachment download. No local media
path was exposed. The temporary login session created for the API check was
logged out; the user's existing browser session was kept.

The automation extension blocked the browser file-selection step because its
file-access permission was disabled. No security or extension setting was
changed. The source was therefore uploaded through the same authenticated public
API used by the UI, then reviewed in the live browser. This proves the live
API/worker/model/storage/UI-result integration; it does **not** claim a live
browser-file-picker-to-model test. The earlier automated browser checks covered
file inputs and multipart requests with controlled API responses.

**Historical finding: transport passed; semantic quality needed work.** Comparison with the
original image found overlapping overview/component summaries, an artifact
that merely describes the diagram rather than adding reusable structure, and
unsupported failure signals such as request timeout and service unavailable.
Some component descriptions also introduce conventional meanings absent from
the source labels. The output's high confidence and valid evidence ordinal do
not establish claim-level grounding. The existing builder already instructs the
model to avoid these problems, so prompt presence alone is insufficient evidence
that they are solved. The draft was deliberately left **unapproved**. No
source-specific filtering or semantic-core rewrite was added during this bridge
verification. These findings should inform a separate generic semantic-quality
improvement and its regression examples.

The subsequent generic correction is complete and documented in
[Knowledge grounding correction](KNOWLEDGE_GROUNDING_FIX.md). Five real-model
semantic checks passed, including preservation of requirements-derived Skills.
A new saved architecture-image draft contains one context item, no artifact,
and no Skill; the original diagnostic draft remains unapproved and unchanged.

Current limits are one source per new set, whole-set approval, one purpose in
the UI (the API supports multiple roles), synchronous bounded processing, and
existing format support. Multi-source revisions, item editing, durable Kafka
processing/recovery, presigned direct uploads for large media, and normalization
into individual Skill/Evidence records remain separate work. Closing the page
does not turn synchronous processing into a background job, and retries should
not be described as exactly-once ingestion.

Removed **14 temporary UI screenshots** after inspection, together with the
temporary test directories created for these checks. Stored source files and
execution evidence functionality were kept.
The later live check saved no screenshot files; its temporary script and local
result JSON were removed. Its source-backed draft remains available for review.
