"""PDF extraction preserves source pages and exposes extraction limits."""

from pathlib import Path

import pytest
from markettwin_knowledge_worker.extraction import PdfExtractionError, PdfExtractor
from pypdf import PdfReader, PdfWriter

from .conftest import write_pdf


def test_pdf_extractor_preserves_text_and_flags_visual_pages(tmp_path: Path) -> None:
    path = tmp_path / "requirements.pdf"
    write_pdf(
        path,
        ("Resume Upload\nUsers may upload PDF or DOCX resumes.\nMaximum size is 10 MB.",),
        visual_page=True,
    )
    result = PdfExtractor().extract(path)
    assert result.source_item_count == result.processed_item_count == 2
    assert result.coverage_complete
    assert len(result.units) == 1
    assert result.units[0].source_locator == {"page_start": 1, "page_end": 1}
    assert result.units[0].ordinal == 1
    assert result.units[0].extractor_name == "pypdf"
    assert "10 MB" in (result.units[0].content_text or "")
    assert [issue.source_locator for issue in result.issues if issue.requires_fallback] == [
        {"page": 2}
    ]


def test_requirement_pages_keep_numbered_provenance(requirements_pdf: Path) -> None:
    result = PdfExtractor().extract(requirements_pdf)
    assert [unit.ordinal for unit in result.units] == [1]
    assert result.units[0].source_locator == {"page_start": 1, "page_end": 3}
    assert "match score" in (result.units[0].content_text or "")
    assert not result.issues


def test_empty_pdf_page_has_no_fake_evidence(tmp_path: Path) -> None:
    path = tmp_path / "blank.pdf"
    write_pdf(path, ("",))
    result = PdfExtractor().extract(path)
    assert not result.units
    assert result.issues[0].code == "blank_page"


def test_password_protected_pdf_is_rejected(requirements_pdf: Path, tmp_path: Path) -> None:
    path = tmp_path / "protected.pdf"
    with PdfWriter() as writer:
        writer.append(PdfReader(requirements_pdf))
        writer.encrypt("test-password")
        writer.write(path)
    with pytest.raises(PdfExtractionError) as error:
        PdfExtractor().extract(path)
    assert error.value.code == "password_protected"


def test_corrupt_pdf_is_reported_as_parsing_failed(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a PDF")
    with pytest.raises(PdfExtractionError) as error:
        PdfExtractor().extract(path)
    assert error.value.code == "parsing_failed"
