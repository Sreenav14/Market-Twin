# MarketTwin Ingestion Component — Target Architecture and Refactor Plan

**Status:** Intended V1/V1.1 target design  
**Scope:** Knowledge ingestion only  
**Primary goal:** Convert arbitrary product source material into grounded application knowledge that the Meta Agent can later use to understand the app, plan tests, and create testing agents.

---

# 1. Executive Summary

MarketTwin ingestion should **not** be designed as a pipeline whose only purpose is:

```text
source files
→ extract text
→ generate Skills
```

The ingestion component is responsible for building a grounded knowledge representation of the application from heterogeneous source material such as:

- documents
- PDFs
- PowerPoint files
- spreadsheets
- CSV files
- JSON
- plain text / Markdown
- images
- screenshots
- diagrams
- videos

That knowledge must eventually support three major knowledge classes:

```text
1. Application / Automation Knowledge
2. SOPs / Procedures / Knowledge Artifacts
3. Reusable Skills
```

These three outputs serve different purposes.

- **Application / Automation Knowledge** tells MarketTwin what the product is, what major capabilities exist, how important concepts relate, what rules are documented, and what the product is known to do.
- **SOPs / Procedures / Artifacts** preserve documented workflows, procedures, state transitions, rule matrices, process flows, and other structured operational knowledge.
- **Skills** are reusable, test-relevant product capabilities that downstream test planning and execution agents can select and use.

The ingestion architecture should therefore be:

```text
ORIGINAL SOURCE
      │
      ├──────────────→ Object Storage (MinIO locally / S3 production)
      │
      ▼
THIN SOURCE ADAPTER
decode / normalize / preserve provenance
NO semantic product interpretation
      │
      ▼
MODEL-READY SOURCE UNITS
      │
      ▼
ONE SEMANTIC KNOWLEDGE-BUILDING STAGE
deeply understand the supplied source
      │
      ├──→ Application / Automation Knowledge
      ├──→ SOPs / Procedures / Artifacts
      └──→ Skill Candidates
      │
      ▼
GROUNDING VALIDATION
      │
      ▼
PERSIST + HUMAN APPROVAL
```

The most important simplification is:

> **We do not need a separate semantic extraction LLM whose output is then interpreted by another Skill-generation LLM.**

For deterministic document formats, parsing should be done by normal libraries. For native multimodal formats such as images and video, the actual media should be given directly to the semantic knowledge-generation call whenever possible.

This keeps MarketTwin grounded while avoiding a chain of model-generated interpretations.

---

# 2. Core Design Principles

## 2.1 Original files remain canonical source truth

The original uploaded source must remain preserved in object storage.

```text
User Upload
→ MinIO locally / S3 production
→ AssetVersion
```

The database should not become the canonical replacement for the original source.

If MarketTwin later needs to answer:

> “Why does the system believe this?”

it must always be possible to trace the knowledge back to the original source.

## 2.2 Parsing is not semantic understanding

A parser should answer:

> “How do I make this source readable and preserve where it came from?”

A parser should **not** answer:

> “What product capability does this mean?”

For example:

```text
DOCX
→ python-docx
→ ordered readable document content
```

is deterministic source normalization.

Semantic interpretation belongs only in the knowledge-building stage and only when the source supports it.

## 2.3 One semantic intelligence layer

Avoid:

```text
source
→ LLM semantic extraction
→ LLM interpretation
→ LLM Skill generation
```

because unsupported assumptions can compound across stages.

Preferred:

```text
source
→ deterministic normalization OR direct multimodal source
→ semantic knowledge generation
→ grounded outputs
```

## 2.4 Grounding is more important than elaborate extraction structure

The ingestion component does not need a large ontology for every source.

Image extraction does not need to classify every visible thing as:

```text
entity
state
action
relationship
structure
location
```

Grounding should instead be maintained through:

```text
knowledge output
→ evidence ordinal
→ EvidenceUnit
→ source locator
→ AssetVersion
→ original source
```

## 2.5 Evidence should point to meaningful source regions

MarketTwin does not require forensic line-level citation.

The intended grounding level is:

```text
PDF / paginated document
→ page number or page range

PPTX
→ slide number or slide range

XLSX / CSV
→ worksheet + row range

Image
→ image itself

Video
→ start second + end second
→ corresponding trimmed clip when available

TXT / MD
→ bounded section/chunk

JSON
→ logical path / bounded structural chunk
```

Exact source lines are not required.

The goal is:

> “Show me the meaningful source region this knowledge came from.”

---

# 3. What We Are Building

The ingestion component should ultimately produce an approved application knowledge package:

```text
ApplicationKnowledgePackage
├── application_knowledge
├── procedures_and_artifacts
└── skills
```

Each item must remain grounded to one or more source evidence regions.

---

# 4. Downstream Product Flow

```text
SOURCE MATERIAL
      ↓
INGESTION
      ↓
APPROVED APP KNOWLEDGE
      ↓
USER TESTING OBJECTIVE
      ↓
META AGENT
      ↓
select relevant:
- application knowledge
- SOPs / artifacts
- Skills
      ↓
understand relevant application behavior
      ↓
determine test coverage
      ↓
create personas / missions / agent hierarchy
      ↓
AGENT FACTORY
      ↓
persona agents / subagents
      ↓
real application interaction
      ↓
findings + test evidence
```

Boundary:

```text
Meta Agent = reasoning / planning brain
Agent Factory = runtime agent builder
Persona Agents = test executors
```

The ingestion component should not create browser execution scripts or selectors.

---

# 5. Knowledge Types

## 5.1 Application / Automation Knowledge

Broad product knowledge, including when supported:

- major capabilities
- documented product behavior
- business rules
- supported states
- availability conditions
- relationships among features or workflows
- architecture/context useful for reasoning
- implementation facts useful to downstream understanding
- product terminology
- documented limits
- role descriptions

This knowledge does not have to be independently executable.

A fact may be useful knowledge without being a Skill.

## 5.2 SOPs / Procedures / Artifacts

Represent workflows or structured operational knowledge.

Examples:

- onboarding flow
- content publishing procedure
- account recovery procedure
- approval workflow
- documented state transitions
- permissions matrix
- feature availability matrix
- supported-format table
- business-rule table
- process flow
- operational checklist

Only source-supported steps may be included.

Do not fill missing workflow steps using common knowledge.

## 5.3 Skills

A Skill is reusable test-relevant product knowledge.

Current durable contract:

```python
class SkillDefinition(BaseModel):
    intent: str
    preconditions: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    expected_outcomes: tuple[str, ...]
    failure_signals: tuple[str, ...] = ()
```

A Skill should represent one coherent product capability or behavior that a tester can meaningfully exercise, observe, or verify.

Do not create Skills merely for:

```text
database
cache
queue
server
storage system
document title
architecture section
technology name
background explanation
```

unless the source establishes meaningful test-relevant behavior associated with it.

---

# 6. One Source Can Produce Multiple Knowledge Types

Example source:

```text
Users may upload files up to 50 MB.
After submission, files enter processing.
When processing completes, the file becomes searchable.
```

Possible outputs:

```text
APPLICATION KNOWLEDGE

- File upload capability exists.
- A processing state exists.
- Search availability follows processing completion.

SOP

Upload
→ Processing
→ Searchable

SKILL

Upload Content
constraint:
- Maximum file size: 50 MB

SKILL

Search Content
precondition:
- Processing completed
```

All may cite the same evidence.

---

# 7. Existing Components We Keep

## 7.1 `ExtractedEvidence`

Keep it.

Purpose:

- one bounded model-ready source region
- source provenance
- stable evidence ordinal
- content supplied to semantic generation

It should not become an ontology.

## 7.2 `ExtractionIssue`

Keep it for:

- unreadable regions
- unsupported formatting
- visual ambiguity
- parser failures
- missing/partial content
- multimodal uncertainty

Generated knowledge must never claim failed extraction content was understood.

## 7.3 `ExtractionResult`

Keep:

```text
source_path
units
issues
source_item_count
processed_item_count
```

## 7.4 Deterministic bounded packing

Keep deterministic packing.

Remember:

```text
parser granularity
≠ persistence granularity
≠ LLM-call granularity
```

Do not create one EvidenceUnit for every parser paragraph, row, cell, or visible image item.

---

# 8. What We Simplify or Remove

## 8.1 Remove semantic image-observation ontology

Do not use:

```text
ImageObservation
├── kind
├── text
├── location
├── uncertainty
```

with semantic categories such as:

```text
entity
state
action
relationship
structure
```

It encourages interpretation during extraction and produces unnecessary fragmentation.

## 8.2 Do not create one EvidenceUnit per image observation

Avoid:

```text
1 image
→ 18 observations
→ 18 EvidenceUnits
```

Preferred:

```text
1 image
→ 1 image EvidenceUnit
```

## 8.3 No semantic extraction LLM for documents

Avoid:

```text
DOCX
→ parser
→ semantic extraction LLM
→ summary
→ Skill LLM
```

Preferred:

```text
DOCX
→ parser
→ normalized bounded content
→ semantic knowledge builder
```

## 8.4 Do not force every source into nested JSON

Use structured JSON/Pydantic only where there is a real application contract.

Use strict structured output for:

- Skills
- application knowledge objects
- SOP/artifact objects
- consolidation results
- reconciliation decisions

For most source content, `content_text` is enough.

Actual JSON source files may naturally use `content_json`.

---

# 9. Source Adapter Responsibilities

Every source adapter has only four responsibilities:

```text
1. Read/decode the source.
2. Preserve meaningful source ordering.
3. Produce bounded model-ready content when necessary.
4. Attach a useful source locator.
```

It should not:

```text
infer business behavior
invent missing rules
decide what is a Skill
build test cases
create selectors
plan browser workflows
decide Meta Agent missions
```

---

# 10. Per-Format Target Behavior

## 10.1 TXT / Markdown

```text
TXT / MD
→ read text
→ normalize encoding
→ preserve order
→ deterministic bounded chunks
→ content_text
```

Grounding:

```json
{
  "chunk": 1
}
```

Exact lines are unnecessary.

## 10.2 DOCX

Use `python-docx`.

Responsibilities:

- preserve paragraph/table order
- retain headings
- retain readable table structure
- avoid one EvidenceUnit per paragraph
- pack bounded evidence units

Important limitation: DOCX does not naturally expose reliable page numbers through `python-docx`.

Therefore do **not fake page numbers**.

V1 may use a bounded document region/paragraph range for DOCX unless page-aware rendering is later added.

Example model-ready content:

```text
# Account Settings

Users can update their profile.

[TABLE]
Field | Requirement
Email | Required
Phone | Optional
[/TABLE]
```

## 10.3 PDF

Use deterministic text extraction where suitable.

Current tool:

```text
pypdf
```

Pipeline:

```text
PDF
→ page text
→ preserve page order
→ pack bounded page groups
→ content_text
```

Grounding:

```json
{
  "page_start": 12,
  "page_end": 15
}
```

If a page is primarily visual and text extraction is insufficient, record an extraction issue rather than claiming it was understood.

## 10.4 PPTX

Use `python-pptx`.

```text
PowerPoint
→ slide text/tables
→ preserve slide order
→ pack bounded slide groups
→ content_text
```

Grounding:

```json
{
  "slide_start": 4,
  "slide_end": 7
}
```

Sparse visual slides may later use multimodal fallback if needed.

## 10.5 XLSX

Use `openpyxl`.

```text
Workbook
→ worksheet
→ rows/cells/formulas as readable text
→ bounded row groups
→ content_text
```

Grounding:

```json
{
  "sheet": "Plans",
  "row_start": 10,
  "row_end": 75
}
```

Readable representation:

```text
[SHEET: Plans]

Row 10: Free | $0 | 1 user
Row 11: Pro | $20 | 10 users
```

## 10.6 CSV

Use Python CSV parsing.

```text
CSV
→ rows
→ normalized row text
→ bounded row groups
→ content_text
```

Grounding:

```json
{
  "row_start": 1,
  "row_end": 100
}
```

## 10.7 JSON

JSON is naturally structured.

Small JSON:

```text
keep whole source
```

Large JSON:

```text
split deterministically by structural boundaries
```

Examples:

- top-level keys
- bounded array item ranges
- recursively split oversized children

Grounding may use:

```json
{
  "json_path": "$.plans"
}
```

or:

```json
{
  "json_path": "$.items",
  "item_start": 100,
  "item_end": 150
}
```

`content_json` is appropriate here.

## 10.8 Images

Preferred:

```text
original image
→ multimodal semantic knowledge generation
→ grounded knowledge / SOPs / Skill candidates
```

Do not require an intermediate semantic image ontology.

Evidence grounding:

```json
{
  "image": 1
}
```

For V1, the whole image is sufficient.

Potential future enhancement: region/bounding-box grounding only if review workflows prove it is necessary.

## 10.9 Video

Short video:

```text
video
→ actual video model input
→ semantic knowledge generation
```

Long video:

```text
video
→ deterministic clip segmentation
→ actual clips
→ knowledge generation per clip
→ consolidation
```

Current target clip behavior:

```text
target ≈ 90 seconds
overlap ≈ 5 seconds
```

Grounding:

```json
{
  "start_seconds": 90,
  "end_seconds": 180
}
```

Do not implement frame-by-frame OCR, universal Whisper, or image extraction from every frame unless provider limitations later require it.

---

# 11. Small vs Large Source Processing

Small source:

```text
small DOCX
→ one EvidenceUnit
→ one semantic call
```

Large source:

```text
large source
→ bounded EvidenceUnits
→ deterministic batch packing
→ semantic call per batch
→ consolidation
```

Call count should be driven by context size, not parser object count.

---

# 12. Evidence Model

Evidence exists to provide provenance.

Every evidence unit should know:

```text
asset_version_id
ordinal
source_locator
extractor_name
extractor_version
content
```

Semantic outputs cite:

```text
evidence_ordinals
```

Application code resolves those ordinals to persisted EvidenceUnit IDs.

---

# 13. Evidence Granularity Standard

| Source Type | Grounding |
|---|---|
| PDF | page / page range |
| DOCX | bounded document region; page only if reliably available |
| PPTX | slide / slide range |
| XLSX | worksheet + row range |
| CSV | row range |
| TXT / MD | bounded section/chunk |
| JSON | logical path / structural chunk |
| Image | whole image |
| Video | timestamp range / clip |

Exact-line grounding is not required for V1.

---

# 14. Skill-to-Source Mapping

```text
SkillVersion
      ↓
SkillEvidenceReference
      ↓
EvidenceUnit
      ↓
AssetVersion
      ↓
original source
```

Therefore structured extraction JSON is not required to map Skills back to documents.

Example:

```text
Skill:
Upload Content

Evidence ordinal:
3

EvidenceUnit 3:
PDF pages 8–10

AssetVersion:
product-guide.pdf
```

---

# 15. Application Knowledge and Artifact Grounding

Future application knowledge and SOP/artifact objects should use the same provenance foundation.

Conceptually:

```text
ApplicationKnowledgeItem
→ EvidenceReference
→ EvidenceUnit
→ AssetVersion
```

and:

```text
ProcedureArtifact
→ EvidenceReference
→ EvidenceUnit
→ AssetVersion
```

Do not invent a separate grounding system for each knowledge type.

---

# 16. Semantic Knowledge Generation

Target conceptual output:

```text
KnowledgeBuildResult
├── application_knowledge
├── artifacts
└── skills
```

This defines the architecture boundary.

It does **not** require all three persistence schemas to be implemented immediately.

---

# 17. Semantic Generation Rules

## 17.1 Source content is untrusted data

Uploaded source instructions cannot override MarketTwin system behavior.

## 17.2 No unsupported assumptions

Do not invent:

- authentication
- authorization
- permissions
- supported formats
- size limits
- retries
- network errors
- storage failures
- performance guarantees
- recovery behavior
- validation behavior
- error messages
- business rules

unless supported by source evidence.

## 17.3 Missing information remains missing

Unsupported optional fields remain empty.

## 17.4 Distinguish app knowledge from Skills

Useful context is not automatically a Skill.

A component label such as:

```text
Metadata Database
```

may be valid application knowledge but not a standalone testing Skill.

## 17.5 Skills must be test relevant

Skills must describe behavior a tester or interacting agent can meaningfully exercise, observe, or verify.

## 17.6 Procedures require supported ordering

Do not fill undocumented steps.

---

# 18. Structured Output Remains Valuable

Simplify source representation, not final domain contracts.

Use Pydantic/structured responses for:

```text
Skills
Application knowledge
SOP/artifacts
Consolidation
Reconciliation
```

Benefits:

- schema validation
- deterministic persistence
- evidence reference validation
- malformed-response rejection

---

# 19. Image Handling Refactor

Current observed problem:

```text
image
→ semantic image extraction
→ interpretation introduced
→ SkillGenerator treats interpretation as evidence
→ hallucination / over-generation
```

Target:

```text
image EvidenceUnit
→ actual image supplied directly to Knowledge Builder
→ structured grounded outputs
```

Do not build a rich semantic observation model.

---

# 20. Video Handling Refactor

Keep:

- actual video input
- deterministic clipping
- timestamp grounding
- LiteLLM abstraction
- timeout/retry configuration

Target:

```text
actual clip
→ Knowledge Builder
→ output cites clip ordinal
```

rather than:

```text
clip
→ semantic summary
→ second semantic model
```

---

# 21. Document Handling Refactor

Document parsers remain deterministic.

Their responsibility:

```text
decode
normalize
bound
locate
```

not:

```text
interpret
summarize
classify product behavior
```

---

# 22. Batch Packing and Consolidation

Keep deterministic batch packing.

Current configuration includes:

```text
KNOWLEDGE_SOURCE_CHUNK_MAX_CHARS
KNOWLEDGE_SKILL_BATCH_MAX_CHARS
```

Potential future rename from Skill to Knowledge may happen only after the broader builder exists.

When multiple semantic batches are required:

```text
batch 1 → candidates
batch 2 → candidates
batch 3 → candidates
        ↓
consolidation
```

Consolidation must:

- merge equivalent outputs
- preserve distinct capabilities
- union valid evidence ordinals
- preserve exact documented rules
- preserve warnings
- never invent new facts
- never invent new ordinals

---

# 23. Human Approval

Generated knowledge remains proposed until approved.

```text
source
→ generated draft knowledge
→ human review
→ approved knowledge
```

This is important because approved knowledge later influences autonomous test planning.

---

# 24. Incremental New-Source Processing

Do not reprocess all historical sources whenever a new source arrives.

Preferred:

```text
new source
→ candidate knowledge
      +
existing approved knowledge
→ reconcile
→ CREATE / UPDATE / UNCHANGED
→ human approval
```

Do not infer deletion because a new source omits old knowledge.

---

# 25. Existing Skill Reconciler

Keep the current reconciliation direction:

```text
CREATE
UPDATE_EXISTING
UNCHANGED
```

No automatic `DELETE`.

Pending persistence requirement:

An update must eventually target an explicit existing logical Skill ID, not only resolve by exact name.

Do not wire this until persistence semantics are correct.

---

# 26. Persistence Strategy

Safe ordering:

```text
generate drafts first
→ validate output
→ persist EvidenceUnits
→ persist knowledge drafts
→ persist evidence references
```

Avoid partially persisted knowledge when semantic generation fails.

---

# 27. Evidence Persistence

Evidence should remain compact.

Do not store:

```text
one row per paragraph
one row per table cell
one row per image observation
one row per visible label
```

Store meaningful bounded source regions.

---

# 28. Idempotency

Kafka will eventually deliver ingestion work with at-least-once semantics.

Duplicate delivery must not create duplicate ingestion state.

Future idempotency should be defined around:

```text
AssetVersion
+
extractor version
+
ingestion/source state
```

Do not solve this with blind duplicate inserts.

Implement alongside worker/Kafka integration.

---

# 29. Object Storage Flow

Production path:

```text
React
→ Control API
→ presigned upload
→ S3 / MinIO
→ upload complete
→ AssetVersion + OutboxEvent
→ Kafka
→ Knowledge Worker
```

Do not stream large binaries through the FastAPI Control API.

Original files remain available for:

- audit
- reprocessing
- review
- model upgrades
- future knowledge versions

---

# 30. Extraction Issues and Partial Success

A source can be partially readable.

Example:

```text
pages 1–20 extracted
page 21 unreadable visual page
pages 22–30 extracted
```

Knowledge generation may continue from supported evidence.

It must never claim page 21 was understood.

Warnings should propagate when they materially affect generated knowledge.

---

# 31. Grounding Confidence

Confidence describes evidence quality, not model emotion.

High:

```text
important details are explicit and unambiguous
```

Medium/low:

```text
supported but relevant ambiguity remains
```

Lower confidence never permits invention.

---

# 32. Prompt Architecture

Production prompts must remain generic.

Do not hardcode source-specific examples such as:

```text
Netflix
upload
search
database
queue
architecture diagram
```

just because a test source contained them.

Tests may use examples. Core prompts should encode generic rules.

---

# 33. Model Input Design

Preferred textual input:

```text
SOURCE METADATA

Evidence 1
locator: pages 1–5

<normalized source content>

Evidence 2
locator: pages 6–10

<normalized source content>
```

Multimodal:

```text
Evidence 1
locator: image 1

<actual image>
```

Video:

```text
Evidence 4
locator: 90s–180s

<actual clip>
```

Do not require deeply nested JSON just to supply evidence.

---

# 34. Model Output Design

Target conceptual contract:

```python
class KnowledgeBuildResult(BaseModel):
    application_knowledge: tuple[...]
    artifacts: tuple[...]
    skills: tuple[GeneratedSkillDraft, ...]
```

Do not create placeholder persistence tables just because the target contract names these domains.

Implement persistence only when lifecycle and downstream use are understood.

---

# 35. Evidence Ordinal Validation

Application code must validate:

```text
all ordinals are positive
all referenced ordinals exist
consolidation cannot invent ordinals
reconciliation cannot invent ordinals
```

The model never receives or creates real EvidenceUnit UUIDs.

It cites temporary ordinals.

Application code maps:

```text
ordinal → persisted EvidenceUnit ID
```

---

# 36. Why Exact Text Excerpts Are Not Required

Grounding is established by:

```text
source region
+
original source
```

Example:

```text
Skill:
Reset Password

Evidence:
product-guide.pdf pages 18–19
```

This is sufficient for V1 review.

Exact sentence offsets can be added later only if real review workflows require them.

---

# 37. Retrieval Is Future Work

When approved knowledge becomes large:

```text
user test objective
→ identify relevant product area
→ select relevant knowledge / SOPs / Skills
→ Meta Agent planning
```

Do not build a vector database or full RAG platform now.

Start with deterministic filtering/model selection.

Add retrieval infrastructure only when scale requires it.

---

# 38. Explicit Non-Goals for V1

Do not add:

```text
vector database
knowledge graph
generic plugin/extractor registry database
semantic chunking agent
multi-agent ingestion
one agent per Skill
automatic Playwright generation during ingestion
OCR pipeline for every image
frame pipeline for every video
Whisper everywhere
SOP execution engine
GEPA
browser selectors inside Skills
source-specific prompt logic
```

---

# 39. Testing Philosophy

Add only tests that protect durable invariants.

Good tests:

- parser preserves source order
- chunking preserves all content
- page/slide/row/timestamp locators are correct
- oversized JSON splitting preserves source data
- unsupported formats fail clearly
- output rejects unknown evidence ordinals
- consolidation cannot invent evidence
- reconciliation cannot duplicate candidate decisions
- database proof persists evidence + references

Avoid brittle tests such as:

- LLM must always generate exactly N Skills
- generated names must match one exact phrase
- image model must word a fact in one exact way

Use real smoke tests for semantic quality.

---

# 40. Smoke-Test Acceptance Criteria

## Image

- actual image reaches multimodal model
- knowledge is grounded to image evidence
- unsupported rules are not invented
- internal labels do not automatically become Skills
- Skill count does not explode
- response completes within token budget

## Video

Short video:

- actual video reaches provider
- provider accepts selected transport
- result references correct ordinal
- timestamp range is correct

Long video:

- clips are valid
- target/overlap boundaries are correct
- all clips process
- consolidation preserves clip grounding

## Documents

- all meaningful source content is preserved
- source ordering is preserved
- evidence is not unnecessarily fragmented
- locator is correct
- semantic output cites only supplied evidence

---

# 41. CLI / Debugging

Recommended modes:

```text
default
→ concise source + generated knowledge

--debug
→ evidence counts/types/locators
→ extraction issues
→ confidence/warnings

--include-evidence
→ full normalized evidence

--extract-only
→ source-adapter output only
→ do not call semantic generation
```

`--extract-only` is valuable because it separates:

```text
source adapter bug
from
semantic generation bug
```

---

# 42. Configuration

Current relevant configuration:

```text
KNOWLEDGE_SOURCE_CHUNK_MAX_CHARS
KNOWLEDGE_SKILL_BATCH_MAX_CHARS
KNOWLEDGE_MODEL_TIMEOUT_SECONDS
KNOWLEDGE_MODEL_NUM_RETRIES
IMAGE_MODEL_NAME
IMAGE_MODEL_API_KEY
VIDEO_MODEL_NAME
VIDEO_MODEL_API_KEY
VIDEO_INPUT_FORMAT
FFMPEG_BINARY
```

Potential future rename:

```text
SKILL_BATCH → KNOWLEDGE_BATCH
```

only after broader Knowledge Builder implementation.

---

# 43. Provider Portability

Avoid depending on every LLM provider supporting every raw file format.

Preferred:

```text
structured documents
→ deterministic parse

native multimodal media
→ multimodal model
```

This preserves LiteLLM provider portability.

---

# 44. Error Handling

Use clear failures for:

- unsupported source format
- source read failure
- parser failure
- blank source
- multimodal failure
- incomplete model response
- invalid structured response
- invalid evidence ordinal
- persistence failure

Do not silently turn failed semantic generation into empty knowledge.

An empty result is valid only when the model completed normally and no grounded knowledge could be produced.

---

# 45. Security Boundary

Uploaded source is untrusted.

A source must never be able to instruct MarketTwin to:

- ignore system instructions
- reveal secrets
- change schema
- call unrelated tools
- invent actions
- override safety/policy

Source content is evidence, not policy.

---

# 46. Current Refactor Direction by File/Component

## `extraction/chunking.py`

**KEEP**

Purpose:

```text
bounded deterministic source packing
```

No semantic NLP chunking.

## `extraction/docx.py`

**KEEP PARSER**

Responsibility becomes:

```text
decode + normalize + locate
```

No semantic extraction stage.

## `extraction/pdf.py`

**KEEP PAGE EXTRACTION**

Keep page-range locators.

Add multimodal fallback only when proven necessary.

## `extraction/pptx.py`

**KEEP SLIDE EXTRACTION**

Potential future actual-slide-image fallback only for sparse visual slides.

## `extraction/xlsx.py`

**KEEP**

Sheet/row normalization + bounded row groups.

## `extraction/csv_file.py`

**KEEP**

Bounded row extraction.

## `extraction/text.py`

**KEEP**

Normalized bounded text.

## `extraction/json_file.py`

**KEEP**

Structural splitting. JSON remains a natural use for `content_json`.

## `extraction/image.py`

**CHANGE SUBSTANTIALLY**

Remove rich semantic observation taxonomy.

Target role:

```text
prepare original image evidence for semantic Knowledge Builder
```

Long-term preferred:

```text
actual image
→ Knowledge Builder
```

## `extraction/video.py`

**KEEP**

- duration inspection
- short whole-video path
- long physical clipping
- timestamp locators

Change semantic flow toward:

```text
actual clip
→ Knowledge Builder
```

rather than:

```text
clip
→ model summary
→ SkillGenerator
```

## `skill_generator.py`

**GENERALIZE INCREMENTALLY**

Conceptual target:

```text
Application Knowledge Builder
```

Do not discard working:

- batching
- evidence validation
- consolidation

Generalize them.

---

# 47. Migration Strategy

Do not rewrite everything at once.

## Phase 1 — Freeze evidence architecture

Keep:

```text
ExtractedEvidence
ExtractionIssue
ExtractionResult
EvidenceUnit
source_locator
evidence_ordinals
```

Standardize grounding levels.

## Phase 2 — Remove over-structured image extraction

Remove semantic observation taxonomy.

Keep one image EvidenceUnit.

## Phase 3 — Explicit Source Adapter vs Knowledge Builder boundary

Documents remain deterministic.

## Phase 4 — Direct multimodal knowledge generation

Image/video actual media goes to semantic generation.

Verify with real provider smoke tests.

## Phase 5 — Generalize SkillGenerator internally

Move toward Knowledge Builder while preserving current Skill behavior.

## Phase 6 — Add Application Knowledge domain model

Only when:

- contract is clear
- approval lifecycle is clear
- grounding is clear
- Meta Agent consumption is clear

## Phase 7 — Add SOP / Artifact domain model

Same rule: no generic blob tables without a real contract.

## Phase 8 — Meta Agent integration

```text
user objective
→ select relevant knowledge / artifacts / Skills
→ plan testing
→ Agent Factory
```

---

# 48. Expected Final Architecture

```text
                         ┌──────────────────────┐
                         │    User Uploads      │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │   MinIO / S3 Source  │
                         └──────────┬───────────┘
                                    │
                                    ▼
                     ┌────────────────────────────┐
                     │      Source Dispatcher     │
                     └──────────────┬─────────────┘
                                    │
                 ┌──────────────────┼──────────────────┐
                 │                  │                  │
                 ▼                  ▼                  ▼
            Documents            Images             Videos
                 │                  │                  │
                 ▼                  │                  ▼
        deterministic parse         │        deterministic clipping
        normalize + locate          │        + timestamp locator
                 │                  │                  │
                 └──────────────────┼──────────────────┘
                                    │
                                    ▼
                       MODEL-READY SOURCE EVIDENCE
                                    │
                                    ▼
                       ┌─────────────────────────┐
                       │     Knowledge Builder    │
                       │ one semantic reasoning  │
                       │         boundary         │
                       └───────────┬─────────────┘
                                   │
                   ┌───────────────┼────────────────┐
                   │               │                │
                   ▼               ▼                ▼
           App Knowledge     SOPs / Artifacts     Skills
                   │               │                │
                   └───────────────┼────────────────┘
                                   │
                                   ▼
                        Evidence Validation
                                   │
                                   ▼
                          Draft Persistence
                                   │
                                   ▼
                           Human Approval
                                   │
                                   ▼
                       Approved App Knowledge
```

---

# 49. Relationship to O2A

Useful O2A lesson:

```text
source
→ decode / normalize
→ bounded processing when necessary
→ model reasoning
→ consolidation
→ generated artifact
```

MarketTwin should borrow that processing shape.

MarketTwin differs in purpose.

MarketTwin is building a grounded application knowledge system for:

```text
Meta Agent test planning
persona creation
mission planning
agent selection
real application testing
```

Therefore MarketTwin should preserve stronger explicit provenance from generated knowledge back to source evidence.

Do not copy O2A's:

- exact agent topology
- SOP execution implementation
- Playwright-generation approach
- automation-script architecture

unless MarketTwin later has a direct need.

---

# 50. Architectural Invariants

1. Original source remains canonical.
2. Every generated knowledge item is traceable to evidence.
3. Models cite evidence ordinals, never DB UUIDs.
4. Source adapters do not invent product semantics.
5. Semantic generation does not invent unsupported facts.
6. Missing information remains missing.
7. Internal implementation facts do not automatically become Skills.
8. Evidence is coarse enough to be understandable.
9. Evidence is fine enough to identify the supporting source region.
10. Parser objects do not map 1:1 to EvidenceUnits.
11. Small sources should normally require one semantic call.
12. Large sources may require bounded calls + consolidation.
13. Consolidation may merge; it may not invent.
14. New-source ingestion should be incremental.
15. Human approval remains before knowledge is trusted.
16. No vector database is required for V1.
17. No semantic image ontology is required.
18. No one-agent-per-Skill architecture.
19. No browser selectors inside Skills.
20. Knowledge ingestion remains separate from execution.

---

# 51. Definition of Done for the Refactor

## Source handling

- Supported formats decode reliably.
- Original files remain in object storage.
- Large sources are bounded deterministically.
- Source order is preserved.
- Locators are meaningful.

## Semantic architecture

- One primary semantic reasoning boundary exists.
- Document parsers do not semantically interpret.
- Images are not converted into a large observation ontology.
- Video processing uses real clips.
- Unsupported facts are not inserted to complete schemas.

## Grounding

- Every Skill references valid evidence.
- Future knowledge/artifact outputs use the same provenance foundation.
- Evidence resolves to AssetVersion.
- page/slide/row/image/time evidence is sufficient.
- exact line citation is unnecessary.

## Output quality

- internal architecture labels do not automatically become Skills
- Skills represent test-relevant behavior
- app knowledge preserves useful non-Skill context
- SOPs contain only supported steps
- semantic output does not explode into tiny duplicates

## Persistence

- evidence remains compact
- draft outputs persist safely
- evidence references are durable
- human approval is supported
- incremental reconciliation preserves older valid knowledge

## Verification

- Ruff passes
- strict Pyright passes
- focused parser tests pass
- evidence validation tests pass
- real image smoke test passes
- real short-video smoke test passes
- DB persistence proof passes

---

# 52. Immediate Implementation Order

```text
STEP 1
Freeze evidence locator rules.

STEP 2
Simplify image handling.
Remove observation taxonomy.
Do not create observation-level EvidenceUnits.

STEP 3
Keep one image EvidenceUnit pointing to the original image.

STEP 4
Refactor semantic generation so image knowledge is produced from the actual image,
not from a model-generated interpretation.

STEP 5
Apply the same principle to video clips.

STEP 6
Keep document adapters deterministic and text-first.

STEP 7
Generalize Skill generation internally toward a Knowledge Builder
without prematurely adding database tables.

STEP 8
Prove grounded generation with:
- one real document
- one real image
- one real short video

STEP 9
After semantic quality is stable, add persistent Application Knowledge
and SOP / Artifact contracts.

STEP 10
Connect approved knowledge to Meta Agent selection and planning.
```

---

# 53. Final Mental Model

The ingestion component is not:

```text
turn files into Skills
```

It is:

```text
build grounded knowledge of the application
```

Final target:

```text
SOURCE
↓
grounded application understanding
↓
Application Knowledge
+ SOPs / Artifacts
+ Skills
↓
human-approved knowledge base
↓
Meta Agent
↓
understand app + user testing objective
↓
test plan
↓
Agent Factory
↓
testing agents
```

The implementation should stay simple:

> **Deterministic source handling where normal software can decode the format.  
> Multimodal models where the source itself is multimodal.  
> One semantic knowledge-building boundary.  
> Strong provenance underneath everything.**
