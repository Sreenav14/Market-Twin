# markettwin-knowledge-worker

MarketTwin ingestion and knowledge-generation worker.

This is an independently deployable MarketTwin component.

## V1 PDF-to-Skills proof

```powershell
uv sync
uv run --env-file .env python services/knowledge-worker/scripts/generate_pdf_skills.py path/to/requirements.pdf
```

The script reads a local PDF, extracts numbered page evidence, and makes one structured model call.
It prints the extracted evidence, extraction issues and validated Skill drafts as JSON.
It does not use Kafka or write database rows. The empty persistence package remains unused.

Set `MODEL_NAME` to a LiteLLM model identifier (default: `openai/gpt-4o-mini`) and set
`MODEL_API_KEY` or `OPENAI_API_KEY` in `.env`. Generated Skills are drafts requiring human review.

`GeneratedSkillDraft.evidence_ordinals` contains positive source-local integers, not database UUIDs.
Every returned ordinal must exist in the supplied extraction. Mapping ordinals to persisted
EvidenceUnit IDs belongs to a later persistence step.

The extractor uses pypdf and records page provenance. It does not estimate bounding boxes,
perform OCR, or understand diagram/table layout. Sparse visual pages are flagged for review;
those issues are also attached to generated drafts. Encrypted and unreadable PDFs are rejected.

### Checks

```powershell
uv run python -m pytest services/knowledge-worker/tests -q
# Optional: makes a real model call with a generated three-page requirements PDF.
$env:MARKETTWIN_TEST_LLM = '1'

uv run --env-file .env python -m pytest services/knowledge-worker/tests/test_skill_generator.py::test_live_pdf_produces_useful_grounded_skills -q -s
```

The live check verifies separate upload, analysis and download capabilities, evidence citations,
PDF/DOCX inputs, the 10 MB limit, PDF report output, and documented retry behavior.
The three-page fixture is synthetic product documentation, not a customer PDF.

See [the change and verification record](../../docs/PDF_TO_SKILLS.md) for rationale and limits.
