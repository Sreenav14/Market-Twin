# Generic knowledge grounding correction

Completed October 4, 2026. This supplements
[the ingestion workflow implementation](INGESTION_WORKFLOW_UI_AND_REVIEW.md).

## Problem and success criteria

The original live architecture-image upload succeeded, but its semantic output
contained two overlapping application-knowledge summaries, an artifact that
mostly restated the diagram, and a Request Handling Skill with failure signals
not established by the image. Valid JSON and an evidence ordinal did not make
those individual claims grounded.

The correction must preserve useful context without inventing behavior, while
still producing Skills from actual requirements. A component diagram can
legitimately produce context and no Skills; a requirements document describing
an upload, supported formats, size limits, and processing outcomes should retain
those capabilities and rules.

## Research and approach

OpenAI's [structured-output guidance](https://developers.openai.com/api/docs/guides/structured-outputs)
explains that schema-conforming output can still contain mistakes, and recommends
clear schema descriptions and evaluation. Its
[prompt-engineering guidance](https://developers.openai.com/api/docs/guides/prompt-engineering)
describes input/output examples as a way to demonstrate the desired behavior.
We applied these principles inside the existing semantic boundary. They are
design guidance, not a guarantee of factual correctness.

## Changes and reasons

| File | Change | Reason |
| --- | --- | --- |
| `packages/shared-python/src/markettwin_shared/knowledge.py` | Added field descriptions for context, artifacts, Skills, and optional Skill details. | Put grounding and category boundaries next to the structured fields the model fills. Keys, types, defaults, and existing validation remain compatible. |
| `services/knowledge-worker/src/markettwin_knowledge_worker/knowledge_builder.py` | Added a short formal-requirements rule and two illustrative input/output exchanges to the existing request. Clearly separated actual source evidence from examples. | Demonstrate both sides: labels/connections remain context; explicitly documented actions, rules, and outcomes become Skills. Examples do not introduce another model call. |
| `services/knowledge-worker/tests/test_knowledge_builder.py` | Locate the actual source message at the end of the request. | Keep existing original-image/video transport assertions meaningful after adding illustrative exchanges. |
| `services/knowledge-worker/tests/test_knowledge_grounding_live.py` | Added five opt-in checks with real configured-model responses and SDK cleanup. | Check semantic behavior rather than supplying mocked answers; avoid live API costs in ordinary test runs and drain callbacks before the test loop closes. |

The existing instructions already required distinct knowledge, meaningful
artifacts, empty optional fields, and source grounding. Repeating those rules
alone had not prevented the observed failure. The added examples make the
category choice concrete. The requirements rule also addresses a failure caught
during verification: over-cautious generation initially returned context only
for a PDF that explicitly described testable capabilities. The final checks
verify both restraint and preservation of valid Skills.

Runtime examples use abstract component labels and generic data-submission
requirements. There is no application-name detection, filename-based filtering,
architecture-image special case, provider-specific postprocessor, or added
semantic service. The actual source remains the final message, original media
is still supplied, and ordinal validation still checks references against the
real extracted evidence. Existing batching, consolidation, extraction cleanup,
model selection, and storage behavior remain in place.

## Verification

- **Five live semantic checks passed in 50.59 seconds** using the existing
  configured `openai/gpt-4o-mini` model: unfamiliar component labels, a documented
  action with and without a stated failure, the authorized architecture image,
  and a three-page requirements PDF.
- The image produced **one application-knowledge item, zero artifacts, and zero
  Skills**. The PDF retained three documented capabilities: upload a resume,
  request analysis, and download the report, including the documented upload
  formats, size restriction, authentication requirement, and parsing failure.
- Final ordinary Python regression: **268 passed, 11 skipped**. Skips are
  explicit live-model/database opt-ins. Existing dependency deprecations and
  pytest collection warnings remain; there were no test failures.
- Ruff passed for all four changed Python files. Focused Pyright checks passed
  with zero errors and zero warnings for those same files. The broader
  repository check found 132 errors, concentrated
  in API test annotations and dependency test-client types, including two SDK
  import diagnostics in the new live test that were subsequently corrected.
  These broader test typing problems are recorded rather than claiming a clean
  repository-wide type check. `git diff --check` passed.
- Reloaded the local worker on port 8010 with the final code. An authenticated
  upload through the public Control API returned **201 in 5.25 seconds** and
  persisted the expected one-context/zero-artifact/zero-Skill output, no
  extraction issues, and evidence ordinal 1. Fetching the saved entry returned
  the same result. The temporary API login was logged out. The live Chrome
  review page displayed the saved context, empty artifacts and Skills, original
  source link, and disabled approval button until review confirmation.

The corrected draft is **Architecture image - grounding verified**, ID
`37ead68b-1bbb-4375-a6e5-82b4a172955f`, available in
[Review knowledge](http://localhost:5173/knowledge/review/37ead68b-1bbb-4375-a6e5-82b4a172955f).
It remains a draft for user review; no automatic approval was performed.
The earlier diagnostic draft is historical and was not overwritten.

## Generic support and limits

The same builder handles the existing PDF, DOCX, PPTX, XLSX, TXT/Markdown, CSV,
JSON, PNG/JPEG/WebP, and MP4/MOV/WebM extraction paths. This change does not
claim support for arbitrary binary formats. New formats still require suitable
extraction adapters. Model configuration remains replaceable through the
existing settings; neither the model nor credentials were changed.

These checks demonstrate that the observed regressions are fixed with the
current model. Other documents, videos, languages, or replacement models can
still produce incorrect claims. Human review remains necessary, and these
semantic checks should be run when changing the model. Ordinal validity is
provenance validation, not an automatic proof of every generated claim.

The browser automation extension's file-URL permission remains disabled.
Consequently, the live upload used the same authenticated API as the UI, rather
than claiming a successful automated browser picker-to-model run. Earlier
desktop/mobile tests verified actual file inputs and multipart requests with
controlled API responses. No browser permission setting was changed.

Temporary scripts, local result JSON, and test directories from this check are
removed after verification. Original source images, saved sources, and execution
evidence functionality are retained.
