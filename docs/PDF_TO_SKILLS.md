# V1 PDF-to-Skills proof

## Scope and changes

This step proves `PDF -> extracted evidence -> LLM -> GeneratedSkillDraft[]` before adding
database persistence or changing the Meta Agent's planning behavior.

| Change | Why |
| --- | --- |
| Replace `evidence_unit_ids` with positive integer `evidence_ordinals` in the shared draft contract | The model cites source evidence without depending on database-generated UUIDs. The old field is rejected. |
| Replace PyMuPDF with pypdf; update the worker dependencies and `uv.lock` | Use a permissively licensed PDF dependency for the simple V1 text path. LiteLLM is declared directly because this worker now uses it. |
| Simplify PDF extraction to one text unit per nonempty page | Keep content and page provenance without estimated bounding boxes or a layout-processing subsystem. Ordinals start at one and count extracted units, not blank pages. |
| Preserve encrypted/corrupt PDF errors and sparse-visual-page issues | Missing text must remain visible to the caller. Inspection uses PDF content operations because text extraction can skip drawing-only pages. |
| Add one `SkillGenerator` with a structured response schema | Generate capabilities, business constraints and expected behavior in one call, then validate the draft schema and cited evidence membership. |
| Attach visual-review issues to generated draft warnings | A text-only result must not hide known missing visual content. No OCR or fallback orchestration is added. |
| Add a local CLI and opt-in live regression check | Make the intelligence path runnable and reviewable without Kafka or database writes. CLI JSON includes evidence, issues and drafts. |

PyMuPDF's upstream [licensing page](https://pymupdf.io/licensing) describes its AGPL and commercial
routes. pypdf's [upstream license](https://github.com/py-pdf/pypdf/blob/main/LICENSE) permits source
and binary redistribution with attribution conditions. This implementation now uses pypdf.
Structured generation follows LiteLLM's [Pydantic response-format API](https://docs.litellm.ai/docs/completion/json_mode).

## Live proof and review

The live check creates a real three-page PDF from synthetic product requirements in
`services/knowledge-worker/tests/conftest.py`, extracts it with pypdf, and calls the configured model.
This is a representative fixture, not validation against a customer document.

The final live response contained:

| Generated draft | Evidence ordinal / PDF page | Behavior retained |
| --- | --- | --- |
| Resume Upload | 1 / 1 | Signed-in user; PDF or DOCX; maximum 10 MB; oversized and unsupported-format errors; accepted resume ready for analysis. |
| Resume Analysis Request | 2 / 2 | Accepted resume and user job description; report with match score, missing keywords and recommendations; parsing error with retry. |
| Report Download | 3 / 3 | Completed analysis required; PDF report containing the documented report fields; download unavailable before completion. |

Review of the first response found omitted PDF output format and retry behavior. The prompt was
strengthened to preserve output formats and recovery actions, and the live test now checks both.
The final configured-model run passed those checks. There is no fixed Skill count in the generator;
the fixture test expects its three documented capabilities to remain separate and discoverable.

## Checks and reproduction

- Full Python regression suite: **224 passed, 4 skipped**. Skipped checks require database or live-model opt-in.
- Knowledge Worker tests: extraction provenance, drawing-only pages, blanks, encrypted/corrupt PDFs,
  structured schema failures, unknown citations, positive integer ordinals, empty input,
  duplicate input ordinals, truncated output and visible review warnings.
- Live PDF-to-Skills check: **passed**, including output format and retry assertions.
- Ruff and strict Pyright checks for the changed worker and shared contract: **passed**.

```powershell
uv sync
uv run --env-file .env python services/knowledge-worker/scripts/generate_pdf_skills.py path/to/requirements.pdf

$env:MARKETTWIN_TEST_LLM = '1'
uv run --env-file .env python -m pytest services/knowledge-worker/tests/test_skill_generator.py::test_live_pdf_produces_useful_grounded_skills -q -s
```

The live check makes a model API call and prints the generated drafts for review. It is disabled
in the default test run. During verification, an isolated workspace `--basetemp` and
`-p no:cacheprovider` avoided inaccessible existing Windows pytest temporary/cache directories.

## Current limits

Page text extraction does not provide OCR, visual understanding or reliable complex-table layout.
Citation validation proves that the referenced ordinal exists; it does not prove semantic entailment.
Drafts still require human review and approval. Large-document batching is not implemented; model
context or output-limit errors are surfaced instead of silently truncating the source or accepting
partial output.

Evidence/Skill tables and migrations remain in place. `persistence/evidence_repository.py` and its
package initializer remain empty. No evidence repository, persistence service, fallback pipeline,
Meta Agent rewrite or Cartesian-product planning change is included in this step.
