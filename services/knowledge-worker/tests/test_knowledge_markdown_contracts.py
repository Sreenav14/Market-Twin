"""Step 0 (doc 33): the frozen Markdown-knowledge contracts prove themselves.

Validator, split guardrails, and renderer tests against the pricing fixture —
no model, no worker, no database.
"""

import json
from pathlib import Path

import pytest
from markettwin_shared.knowledge_markdown import (
    KnowledgeMarkdownValidationError,
    MarkdownEvidenceUnit,
    UnderstandResult,
    UnderstoodFile,
    UnderstoodSection,
    apply_split_guardrails,
    estimate_tokens,
    render_knowledge_file,
    validate_understood_files,
)

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_TEXT = (FIXTURES / "pricing-fixture.md").read_text(encoding="utf-8")
EXPECTED = UnderstandResult.model_validate(
    json.loads((FIXTURES / "pricing-expected.json").read_text(encoding="utf-8"))
)
EVIDENCE_TEXTS = {1: FIXTURE_TEXT}


def test_expected_fixture_set_is_valid() -> None:
    validate_understood_files(EXPECTED.files, EVIDENCE_TEXTS)


def test_invented_price_is_rejected_and_named() -> None:
    file = EXPECTED.files[0]
    section = file.sections[0].model_copy(
        update={"body_md": "The Starter plan costs $999 per month."}
    )
    broken = file.model_copy(update={"sections": (section, *file.sections[1:])})
    with pytest.raises(KnowledgeMarkdownValidationError) as caught:
        validate_understood_files((broken,), EVIDENCE_TEXTS)
    assert "$999" in str(caught.value)


def test_unknown_ordinal_is_rejected_and_named() -> None:
    file = EXPECTED.files[0]
    section = file.sections[0].model_copy(update={"evidence_ordinals": (99,)})
    broken = file.model_copy(update={"sections": (section, *file.sections[1:])})
    with pytest.raises(KnowledgeMarkdownValidationError) as caught:
        validate_understood_files((broken,), EVIDENCE_TEXTS)
    assert "99" in str(caught.value)


def test_bad_and_duplicate_slugs_are_rejected() -> None:
    file = EXPECTED.files[0]
    with pytest.raises(KnowledgeMarkdownValidationError):
        validate_understood_files(
            (file.model_copy(update={"slug": "Pricing Guide!"}),), EVIDENCE_TEXTS
        )
    with pytest.raises(KnowledgeMarkdownValidationError):
        validate_understood_files((file, file), EVIDENCE_TEXTS)


def test_multiline_description_is_rejected() -> None:
    file = EXPECTED.files[0]
    with pytest.raises(KnowledgeMarkdownValidationError):
        validate_understood_files(
            (file.model_copy(update={"description": "Two\nlines."}),), EVIDENCE_TEXTS
        )


def _small_file(slug: str, heading: str, body: str, ordinals: tuple[int, ...]) -> UnderstoodFile:
    return UnderstoodFile(
        slug=slug,
        title=slug.replace("-", " ").title(),
        description=f"About {slug}.",
        sections=(
            UnderstoodSection(heading=heading, body_md=body, evidence_ordinals=ordinals),
        ),
    )


def test_guardrails_merge_small_related_files_without_splitting_sections() -> None:
    first = _small_file("alpha", "Alpha", "Short body.", (1,))
    second = _small_file("beta", "Beta", "Also short.", (1,))
    merged = apply_split_guardrails((first, second))
    assert len(merged) == 1
    assert [section.heading for section in merged[0].sections] == ["Alpha", "Beta"]
    # The surviving sections are the original section objects, whole.
    assert merged[0].sections[0] is first.sections[0]
    assert merged[0].sections[1] is second.sections[0]


def test_guardrails_cap_the_file_count() -> None:
    files = tuple(
        _small_file(f"topic-{index}", f"Topic {index}", "x" * 2000, (index + 1,))
        for index in range(13)
    )
    result = apply_split_guardrails(files)
    assert len(result) == 12
    assert sum(len(file.sections) for file in result) == 13


def test_uncertainty_record_round_trips() -> None:
    again = UnderstandResult.model_validate(EXPECTED.model_dump(mode="json"))
    assert again == EXPECTED
    record = EXPECTED.files[0].sections[0].uncertainties[0]
    assert "tax" in record.text
    assert record.evidence_ordinals == ()


def test_renderer_emits_frontmatter_uncertainties_and_references() -> None:
    unit = MarkdownEvidenceUnit(
        ordinal=1,
        evidence_type="text",
        content_text=FIXTURE_TEXT,
        source_locator={"page": 2},
        extractor_name="text",
        extractor_version="1",
    )
    rendered = render_knowledge_file(
        EXPECTED.files[0],
        source_entry="11111111-1111-1111-1111-111111111111",
        source_name="pricing-fixture.md",
        file_version=1,
        generated_from="text 1; evidence units 1-1",
        evidence={1: unit},
    )
    assert rendered.startswith("---\n")
    assert 'title: "Pricing"' in rendered
    assert "## Uncertainties" in rendered
    assert "does not say whether prices include tax" in rendered
    assert "## Source references" in rendered
    assert "Evidence 1 — pricing-fixture.md, page 2" in rendered
    assert "**Exception:** The annual discount does not apply to the Starter plan." in rendered
    assert "$470.40" in rendered


def test_estimate_tokens_is_deterministic() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2
