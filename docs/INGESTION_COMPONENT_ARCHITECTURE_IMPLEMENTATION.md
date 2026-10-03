# Ingestion component architecture implementation

Date: 2026-10-03

Source of requirements: `MARKETTWIN_INGESTION_COMPONENT_TARGET_ARCHITECTURE.md`.

## Outcome and acceptance status

The immediate component refactor is implemented: deterministic document adapters and native
image/video inputs now feed one `KnowledgeBuilder`. Its structured result contains application
knowledge, procedure/artifact drafts, and Skill drafts, all using the existing evidence ordinals.
The production prompts contain general grounding rules, with no application-specific branches,
examples, expected output counts, or sample-specific filtering.

This is **not a declaration that the complete future ingestion product is finished or frozen**.
The architecture explicitly stages persistence for the additional knowledge types and Meta Agent
integration after semantic quality is stable. Live verification also found a remaining image
grounding problem with the currently configured model. Real video verification is blocked by
missing local configuration and input, described below.

## Requirements review and implementation decisions

| Architecture requirement | Implementation / decision |
|---|---|
| Preserve source evidence, locators, and ordinals | Kept the existing contracts and deterministic document adapters. Added only runtime media paths and temporary-file ownership. |
| One semantic source-understanding boundary | Added `KnowledgeBuilder`; removed model calls from image and video adapters. |
| Whole-image evidence | Each image produces one evidence unit pointing to the original local source. No observation taxonomy or observation-level rows. |
| Actual video input | Whole short video or physically trimmed long-video clips go directly into the builder. No intermediate model summary. |
| Three structured output types | Added `ApplicationKnowledgeDraft`, `ProcedureArtifactDraft`, and `KnowledgeBuildResult` alongside the existing Skill contract. |
| Preserve working Skill callers | `SkillGenerator.generate()` delegates to the builder and returns the Skill subset. |
| Batching and consolidation | Existing whole-evidence batching is generalized to all three output types. Each video clip gets its own semantic call. Consolidation receives candidate results, never fabricated source text. |
| Grounding validation | Every output item requires positive integer evidence ordinals. Batch output may cite only that batch; consolidation may cite only ordinals already present in candidates. |
| Clear failure | Missing native media, malformed output, incomplete responses, missing citations, and unknown citations fail explicitly. A model error is never converted to successful empty knowledge. |
| Extraction limitations | The model receives extraction issue messages and locators. Source regions needing fallback also produce review warnings on returned drafts. |
| Generic operation | Dispatch depends on supported file format. Semantic processing uses source content, not product names, document topics, filenames, or specific workflows. |
| Human approval | Existing persistence still writes Skills as drafts. New in-memory outputs remain proposed knowledge; no automatic approval was introduced. |
| Incremental reconciliation | Preserved the existing reconciler but kept it disconnected from ingestion, as required until explicit logical Skill-ID persistence exists. |
| Future persistence and Meta Agent use | No speculative tables, approval workflow, retrieval layer, or execution changes were added. These remain the architecture's gated later phases. |

## Code changes and reasons

### Shared contracts

`packages/shared-python/src/markettwin_shared/knowledge.py`

- Added application-knowledge drafts with a name, content, evidence ordinals, confidence, and warnings.
- Added procedure/artifact drafts with the same grounding plus a kind and optional ordered steps.
- Added one result envelope containing `application_knowledge`, `artifacts`, and `skills`.
- All three collections must appear explicitly in a structured response. Their contents may be empty.
  This fixes a validation gap found during testing: `{}` previously looked like a successful empty
  model result because all collections had defaults.
- Kept the durable Skill definition unchanged.

These are generation contracts, not new persistence tables or an alternative provenance system.

### Source contracts and adapters

`services/knowledge-worker/src/markettwin_knowledge_worker/extraction/contracts.py`

- `ExtractedEvidence.media_path` identifies actual runtime media supplied to the model.
- `ExtractionResult.cleanup_paths` identifies temporary clip directories owned by the caller.
- Neither field is persisted as source evidence. Database evidence continues to resolve through
  `AssetVersion` to the original stored source.

`extraction/image.py`

- Removed the semantic image-understanding call and its observation model.
- Produces one whole-image evidence unit with `{image: 1}`, media type, and original local path.
- Rejects unsupported image extensions, missing source files, and empty files.
- Actual image interpretation now happens in the same call that creates the final draft knowledge.

`extraction/video.py`

- Retained PyAV duration inspection and deterministic 90-second clips with 5-second overlap.
- Short videos use their original file directly. Longer videos use real FFmpeg MP4 clips.
- Removed clip-understanding summaries and the subsequent reinterpretation stage.
- Every clip retains its start/end timestamps relative to the original source.
- Adapter coverage counts prepared clips. A later model-call failure fails the build rather than
  pretending the clip was understood or persisting partially generated knowledge.
- Temporary clips survive until generation finishes, then are cleaned up on success or failure.
  Cancellation during clip preparation also triggers cleanup. Original files are preserved.

### Knowledge Builder

`services/knowledge-worker/src/markettwin_knowledge_worker/knowledge_builder.py`

- Uses a generic structured response for all three output types.
- Document content is supplied as readable evidence text with ordinals and locators.
- Native media is supplied as actual encoded image/video data, not a model-authored description.
- Preserves image/video model configuration, timeout, retries, and selectable video transport.
- Preserves character-bounded document batches and consolidates multiple candidate results.
- Validates citations before consolidation and again after consolidation.
- Rejects native-media evidence that lacks the actual media path, preventing metadata-only input
  from accidentally being treated as visual understanding.
- Treats uploaded material as untrusted data. The prompt forbids invented fields, undocumented
  ordered procedures, browser scripts/selectors, and completing a familiar system from prior knowledge.
- Explicitly distinguishes identifying metadata from source facts and named concepts from definitions.
- Adds a generic selection rule to merge overlapping application knowledge and omit artifacts that
  merely restate that a source contains a diagram or other material. The rule also applies during
  consolidation, without using source-specific examples or fixed output counts.

### Compatibility and CLI

`skill_generator.py` is now a small compatibility facade over the builder. Existing ingestion and
PDF scripts still receive `tuple[GeneratedSkillDraft, ...]`; there is no second semantic generation
implementation to maintain. `GeneratedSkills` remains an alias for existing internal imports.

`scripts/generate_source_skills.py` now returns the broader knowledge result:

| Mode | Behavior |
|---|---|
| Default | Source summary plus all three generated knowledge collections. |
| `--debug` | Adds evidence metadata, locators, extractor versions, and extraction issues. |
| `--include-evidence` | Includes full normalized source evidence content. Media bytes are not printed. |
| `--extract-only` | Runs only the adapter; makes no semantic model call and cleans temporary clips. |

Confidence and warnings remain visible on generated items in default output as well, so review
information is not hidden when debugging is disabled.

The CLI initializes the model client only after the `--extract-only` branch. Adapter-only diagnostics
therefore do not trigger model-client metadata network requests during import.

## Supported formats and grounding

The implementation is independent of the subject or application represented by the source.
That does not imply support for every possible binary file format.

| Formats | Source handling and locator |
|---|---|
| PDF | `pypdf`; ordered text and page ranges; sparse visual pages raise review issues. |
| DOCX | `python-docx`; paragraph/table ordering and bounded paragraph regions; no fabricated pages. |
| PPTX | `python-pptx`; text/tables and slide ranges; sparse visual content is flagged. |
| XLSX | `openpyxl`; worksheet and bounded row ranges. |
| CSV | Python CSV parsing and bounded row ranges. |
| TXT / MD | Deterministic bounded text with existing source line ranges. |
| JSON | Structural paths, array ranges, and recursively bounded oversized children. |
| PNG / JPEG / WebP | Original whole image and image ordinal. |
| MP4 / MOV / WebM | Actual whole video/clips with source-relative timestamps. |

Unrecognized formats fail clearly through the existing dispatcher. The refactor does not add OCR
for scanned documents or embedded-document visuals. Such content must not be represented as fully
understood when deterministic extraction is insufficient.

## Verification

The full repository suite passed with **246 passed, 5 skipped** before the final cancellation
regression test was added. The skipped checks were opt-in live/database tests. Existing dependency
deprecation and pytest collection warnings remain unrelated to this refactor.

The separate real PostgreSQL persistence proof passed: **1 passed**. It verified compact evidence,
draft Skill persistence, and durable evidence references using isolated schemas inside a rolled-back
transaction. It did not approve or modify the application's knowledge records.

The final focused Knowledge Worker run passed with **45 passed, 2 skipped**, including the added
cancellation regression. Ruff passed across `services` and `packages`. Strict Pyright passed with
zero errors.

New/updated regression coverage includes:

- all three knowledge output types and their citations;
- original image bytes reaching the semantic request;
- actual video clip bytes and timestamp metadata reaching the semantic request;
- cleanup after model success/failure and cancellation during clip preparation;
- consolidation rejecting even a real source ordinal when no candidate cited it;
- malformed/incomplete structured output and invalid positive-integer citations;
- deterministic image/video adapters and existing JSON source-range regression cases.

### Real document result

`numpy.docx` was processed with the configured model. Its 79 meaningful source items were packed
into one 3,960-character evidence unit with a paragraph-range locator. The final result contained
ten application-knowledge items, no procedures, and no Skills, all citing evidence ordinal 1.

The earlier prompt had converted independent examples into ordered procedures. The final generic
rule about supported ordering removed those invented sequences. No sample-specific correction or
fixed output count was added to production code.

### Real image result: transport passed, semantic acceptance remains open

The existing `dsd-netflix-3.png` source was inspected and sent as actual image data to the configured
model. The response completed within the token budget and cited the correct whole-image evidence.

The first response invented a Skill containing authentication requirements, file-size restrictions,
format rules, errors, and confirmation behavior not shown in the image. Generic prompt changes
removed that invented Skill; later responses returned application knowledge and an artifact.

However, the final response still expanded labels with unsupported claims, including authentication
under “User Management” and long-term retention under “Video Storage.” Therefore the strict image
criterion “unsupported rules are not invented” **has not passed**. Valid ordinals prove traceability,
not factual entailment. No automatic approval, second semantic checking agent, or sample-specific
blacklist was added to disguise this limitation. Image drafts still require human review and the
configured model's semantic quality must be resolved before this layer is called frozen.

A follow-up image check after the generic deduplication and artifact-selection rule still returned
two overlapping application-knowledge items and a diagram artifact that added little beyond the
knowledge summary. It also expanded some component labels into undocumented behavior. This is
evidence that the currently configured model does not reliably follow those selection rules.
No deterministic filter based on this example was added because a shared evidence ordinal does not
prove that two items have the same meaning: one bounded source region can support several distinct
facts. Deduplication and artifact usefulness remain human-review concerns until model quality is
proven across varied sources or an independently justified general validation method is available.

### Video verification blockers

No MP4/MOV/WebM source was available in the workspace. The user subsequently supplied a YouTube
link titled “How to use Slack: Your quick start guide.” The workspace has no `yt-dlp` downloader,
FFmpeg is not discoverable through the configured executable path, and `VIDEO_MODEL_NAME` is
unset. Although a general model API key is present, the application requires an explicit
video-capable model configuration; choosing one without direction would risk testing an unsupported
provider transport.

Mocked tests verify payload transport, grounding, clip boundaries, and cleanup, but they do not
prove provider acceptance or physical FFmpeg clipping. A real short-video model test and long-video
clip test remain outstanding. The supplied link identifies a source but does not resolve either
local media retrieval or model transport configuration. A short video requires a compatible model
and a local sample; a long-video test additionally requires FFmpeg.

## Remaining architectural work and limits

1. Resolve the live image semantic-quality failure before freezing generation behavior. Generic
   prompts reduce unsupported output but do not constitute deterministic factual verification.
2. Configure a video-capable provider/model and provide a real source for end-to-end video checks.
3. The CLI accepts local source paths. The complete source-upload → object storage → outbox → Kafka
   → Knowledge Worker integration is a future production path; this component refactor does not
   implement that integration or claim to have verified original-source uploads.
4. Current durable persistence saves evidence and Skill drafts. Application knowledge and artifacts
   are returned by the builder/CLI but are not yet persisted. The compatibility facade intentionally
   returns only Skills to existing callers. Their approval lifecycle and Meta Agent consumption must
   be defined before the architecture's later persistence phases are implemented.
5. Reconciliation remains unwired until repository updates can target an explicit existing logical
   Skill ID. Kafka ingestion idempotency also belongs with that worker integration.
6. Large document source batches are bounded, but the final combined candidate consolidation request
   still depends on the configured model's context capacity. Inline native media also depends on
   provider payload limits. These are not promises of unlimited-size ingestion.

The worktree already contained deleted planning/UI documents and unrelated image files before this
refactor. Those were preserved as user changes and are not included as implementation cleanup.

## Running the component

```powershell
uv run --env-file .env python services/knowledge-worker/scripts/generate_source_skills.py path/to/source --debug
uv run --env-file .env python services/knowledge-worker/scripts/generate_source_skills.py path/to/source --extract-only
uv run --env-file .env python services/knowledge-worker/scripts/generate_source_skills.py path/to/source --include-evidence
```

Text uses `MODEL_NAME`/`MODEL_API_KEY`; images may override them with `IMAGE_MODEL_NAME` and
`IMAGE_MODEL_API_KEY`. Video requires `VIDEO_MODEL_NAME`; `VIDEO_MODEL_API_KEY` may override the
general key. `VIDEO_INPUT_FORMAT` selects the supported transport. `FFMPEG_BINARY` selects the
FFmpeg executable for long clips. Existing chunk, timeout, and retry settings remain compatible.
