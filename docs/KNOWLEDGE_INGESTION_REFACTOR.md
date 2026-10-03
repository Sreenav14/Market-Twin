# Knowledge ingestion refactor implementation

This document records the implementation of
`MARKETTWIN_KNOWLEDGE_INGESTION_REFACTOR_PLAN.md`. The work is limited to the Knowledge Worker,
its persistence proof, shared configuration, and focused tests. Execution, Kafka, Meta Agent,
Persona Agent, browser, evaluator, reporting, and frontend behavior were not changed.

## Resulting pipeline

```text
source file
→ format parser / multimodal understanding
→ normalized, bounded Evidence units
→ bounded Skill-generation batches
→ candidate consolidation only when more than one batch exists
→ grounded draft Skills
→ optional reconciliation with approved Skills
→ human review and approval
```

Parser objects are not persisted. Evidence units represent coherent model-ready source ranges and
retain approximate page, slide, paragraph, table, row, line, JSON-path, image, or video-time
provenance.

## Implemented changes

### Shared limits

`KnowledgeConfig` reads and validates these settings:

| Setting | Default |
| --- | ---: |
| `KNOWLEDGE_SOURCE_CHUNK_MAX_CHARS` | 24000 |
| `KNOWLEDGE_SKILL_BATCH_MAX_CHARS` | 64000 |
| `KNOWLEDGE_MODEL_TIMEOUT_SECONDS` | 180 |
| `KNOWLEDGE_MODEL_NUM_RETRIES` | 0 |

The source limit must be positive and smaller than the Skill batch limit. Image, video, Skill
generation, and reconciliation model calls use the common timeout and retry settings.

### Deterministic extraction

| Format | Normalization and chunking behavior |
| --- | --- |
| DOCX | Paragraphs and tables remain in document order. Headings and table boundaries are retained before deterministic packing. |
| PDF | Nonempty page text is packed into page ranges. Sparse visual pages continue to require visual fallback. |
| PPTX | Slide text and table rows are packed into slide ranges. Sparse visual slides remain visible as fallback issues. |
| XLSX | Nonempty rows are packed per worksheet. Every chunk contains its worksheet name and row provenance. |
| CSV | Nonempty rows become readable row text and are packed into row ranges. |
| TXT / Markdown | Nonempty lines are packed in order with line ranges. |
| JSON | Small documents remain whole. Large objects split at keys, arrays split at item groups, and oversized strings split into valid JSON scalar payloads. |
| Image | One multimodal call produces one evidence unit. Source content is explicitly treated as untrusted. |
| Video | Clips remain 90 seconds with 5 seconds overlap. Coverage counts only successfully understood clips. |

The dispatcher remains explicit about supported extensions. Unsupported formats fail directly.

### Skill generation

The prompt now produces user capabilities and business behavior while excluding document titles,
introductions, chapter headings, learning objectives, conclusions, and summaries. It asks for the
smallest useful set of distinct capabilities so examples and related methods do not become many
near-duplicate Skills.

Whole evidence units are packed up to `KNOWLEDGE_SKILL_BATCH_MAX_CHARS`. A source that fits in one
batch uses one model call. A larger source uses one generation call per batch, followed by one
consolidation call containing candidate Skills only. Citations are checked after every generation
call and again after consolidation. Consolidation cannot introduce an evidence ordinal that was not
already cited by a candidate.

The command-line runner prints evidence type, size, provenance, and extractor information by
default. `--include-evidence` adds full extracted content when detailed debugging is needed.

### Persistence, reconciliation, and approval

`KnowledgeIngestionService` generates candidates before opening persistence work, then stores
EvidenceUnit rows, draft SkillVersion rows, and SkillEvidenceReference rows. Generated or reconciled
content never becomes approved automatically.

`SkillReconciler` compares candidates from only the new source with current approved Skills. It
returns exactly one of `CREATE`, `UPDATE_EXISTING`, or `UNCHANGED` per candidate. There is no delete
action. Candidate indices, approved Skill IDs, and new evidence ordinals are validated locally after
the model response. Updates remain proposed drafts so existing approved knowledge is unchanged until
human approval.

## Verification

- NumPy DOCX: 79 meaningful parser parts became one 3,960-character evidence unit with all content
  preserved in document order and no extraction issues.
- Live NumPy generation: completed without truncation and returned 10 grounded capability Skills,
  all citing evidence ordinal 1.
- Cross-format and boundary suite: 33 tests passed; the live-model and database tests remain opt-in
  in the normal suite.
- Full repository regression suite: 235 passed and 5 opt-in tests skipped.
- PostgreSQL proof: one real extracted PDF persisted one EvidenceUnit, one draft SkillVersion, and
  one SkillEvidenceReference in isolated temporary schemas; the transaction was rolled back.
- Ruff: passed.
- Strict Pyright: passed with zero errors and warnings.

Useful commands:

```powershell
uv run --no-sync --env-file .env python services/knowledge-worker/scripts/generate_source_skills.py numpy.docx

$env:MARKETTWIN_TEST_DATABASE = "1"
uv run --no-sync --env-file .env python -m pytest services/knowledge-worker/tests/test_knowledge_persistence.py -q

.venv\Scripts\python.exe -m pytest services/knowledge-worker/tests -q
.venv\Scripts\ruff.exe check services/knowledge-worker
.venv\Scripts\pyright.exe services/knowledge-worker/src services/knowledge-worker/tests
```

## Errors found and resolved

1. The original NumPy generation response ended at the model output limit. Capability filtering and
   bounded generation removed the truncation; the final live call completed normally.
2. Video extraction counted planned clips as processed even when understanding failed. It now counts
   only successful clips, so `coverage_complete` remains honest.
3. The example database URL selected `psycopg`, while the database package installs `asyncpg`. The
   example now uses `postgresql+asyncpg://`.
4. `litellm` appeared twice in the Knowledge Worker dependencies. The duplicate declaration was
   removed.

## Deliberate V1 limits

This work does not add RAG, embeddings, vector retrieval, semantic model chunking, a knowledge
graph, universal OCR, video frame/audio decomposition, automatic Skill deletion, or automatic
approval. PDF and presentation visual fallback issues remain visible for later review rather than
being silently treated as complete extraction.
