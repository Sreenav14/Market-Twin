"""Deterministic page text extraction using pypdf."""

from pathlib import Path

import pypdf
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from markettwin_knowledge_worker.extraction.contracts import (
    ExtractedEvidence,
    ExtractionIssue,
    ExtractionResult,
)


class PdfExtractionError(RuntimeError):
    """Raised when a PDF cannot be safely extracted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PdfExtractor:
    """Extract page text and flag sparse visual pages for review; no OCR."""

    name = "pypdf"
    version = pypdf.__version__

    def __init__(self, *, minimum_visual_page_text_chars: int = 40) -> None:
        self._minimum_visual_page_text_chars = minimum_visual_page_text_chars

    def extract(self, path: Path) -> ExtractionResult:
        """Return numbered evidence with page provenance, not estimated boxes."""
        units: list[ExtractedEvidence] = []
        issues: list[ExtractionIssue] = []
        try:
            with path.open("rb") as stream:
                reader = PdfReader(stream)
                if reader.is_encrypted:
                    raise PdfExtractionError("password_protected", "PDF is password protected.")
                page_count = len(reader.pages)
                for page_number, page in enumerate(reader.pages, start=1):
                    contents = page.get_contents()
                    has_visual_content = contents is not None and any(
                        operator in {b"Do", b"re", b"m", b"l", b"c", b"v", b"y", b"sh"}
                        for _args, operator in contents.operations
                    )
                    text = (page.extract_text() or "").strip()
                    if text:
                        units.append(
                            ExtractedEvidence(
                                evidence_type="text",
                                content_text=text,
                                content_json=None,
                                source_locator={"page": page_number},
                                extractor_name=self.name,
                                extractor_version=self.version,
                                ordinal=len(units) + 1,
                            )
                        )
                    if has_visual_content and len(text) < self._minimum_visual_page_text_chars:
                        issues.append(
                            ExtractionIssue(
                                code="needs_visual_fallback",
                                message="Page contains visual content but little extractable text.",
                                source_locator={"page": page_number},
                                requires_fallback=True,
                            )
                        )
                    elif not text:
                        issues.append(
                            ExtractionIssue(
                                code="blank_page",
                                message="Page contains no extractable text or visual content.",
                                source_locator={"page": page_number},
                            )
                        )
        except (OSError, PdfReadError, ValueError) as exc:
            raise PdfExtractionError(
                "parsing_failed", f"Unable to extract PDF: {path.name}"
            ) from exc
        return ExtractionResult(
            source_path=path,
            units=tuple(units),
            issues=tuple(issues),
            source_item_count=page_count,
            processed_item_count=page_count,
        )
