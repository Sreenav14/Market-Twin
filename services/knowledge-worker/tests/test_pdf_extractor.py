"""Tests for deterministic PDF extraction."""

from pathlib import Path

import pymupdf
from markettwin_knowledge_worker.extraction import PdfExtractor


def _create_test_pdf(path: Path) -> None:
    document = pymupdf.open()

    text_page = document.new_page()

    text_page.insert_text(
        (72, 72),
        "Resume Upload",
    )

    text_page.insert_text(
        (72, 100),
        "Users may upload PDF or DOCX resumes.",
    )

    text_page.insert_text(
        (72, 128),
        "Maximum upload size is 10 MB.",
    )

    visual_page = document.new_page()

    visual_page.draw_rect(
        pymupdf.Rect(
            100,
            100,
            400,
            400,
        )
    )

    document.save(path)
    document.close()


def test_pdf_extractor_preserves_text_and_flags_visual_pages(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "requirements.pdf"

    _create_test_pdf(pdf_path)

    result = PdfExtractor().extract(pdf_path)

    assert result.source_item_count == 2
    assert result.processed_item_count == 2
    assert result.coverage_complete is True

    extracted_text = "\n".join(
        unit.content_text or ""
        for unit in result.units
    )

    assert "Resume Upload" in extracted_text
    assert "PDF or DOCX" in extracted_text
    assert "10 MB" in extracted_text

    assert all(
        unit.source_locator["page"] == 1
        for unit in result.units
    )

    fallback_pages = {
        issue.source_locator["page"]
        for issue in result.issues
        if issue.requires_fallback
    }

    assert fallback_pages == {2}
    assert result.requires_fallback is True