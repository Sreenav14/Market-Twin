"""Fast deterministic PDF extraction using PyMuPDF."""

from pathlib import Path
from typing import cast

import pymupdf

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
    """Extract text blocks from a PDF while auditing visual coverage."""

    name = "pymupdf"
    version = pymupdf.VersionBind

    def __init__(
        self,
        *,
        minimum_visual_page_text_chars: int = 40,
    ) -> None:
        self._minimum_visual_page_text_chars = minimum_visual_page_text_chars

    def extract(self, path: Path) -> ExtractionResult:
        """Extract evidence and identify pages needing visual fallback."""

        units: list[ExtractedEvidence] = []
        issues: list[ExtractionIssue] = []

        ordinal = 1
        processed_pages = 0

        try:
            document = pymupdf.open(path)
        except Exception as exc:
            raise PdfExtractionError(
                "parsing_failed",
                f"Unable to open PDF: {path.name}",
            ) from exc

        try:
            if document.needs_pass:
                raise PdfExtractionError(
                    "password_protected",
                    f"PDF is password protected: {path.name}",
                )

            page_count = document.page_count

            for page_index in range(page_count):
                page = document.load_page(page_index)
                page_number = page_index + 1
                processed_pages += 1

                raw_blocks = cast(
                    list[tuple[object, ...]],
                    page.get_text(
                        "blocks",
                        sort=True,
                    ),
                )

                page_character_count = 0

                for raw_block in raw_blocks:
                    if len(raw_block) < 5:
                        continue

                    # PyMuPDF block type 0 = text.
                    if len(raw_block) >= 7:
                        block_type = raw_block[6]

                        if isinstance(block_type, int) and block_type != 0:
                            continue

                    raw_text = raw_block[4]

                    if not isinstance(raw_text, str):
                        continue

                    text = raw_text.strip()

                    if not text:
                        continue

                    x0 = float(raw_block[0])
                    y0 = float(raw_block[1])
                    x1 = float(raw_block[2])
                    y1 = float(raw_block[3])

                    page_character_count += len(text)

                    units.append(
                        ExtractedEvidence(
                            evidence_type="text",
                            content_text=text,
                            content_json=None,
                            source_locator={
                                "page": page_number,
                                "bbox": [
                                    x0,
                                    y0,
                                    x1,
                                    y1,
                                ],
                            },
                            extractor_name=self.name,
                            extractor_version=self.version,
                            ordinal=ordinal,
                        )
                    )

                    ordinal += 1

                image_count = len(page.get_images(full=True))
                drawing_count = len(page.get_drawings())

                visual_object_count = image_count + drawing_count

                if (
                    visual_object_count > 0
                    and page_character_count
                    < self._minimum_visual_page_text_chars
                ):
                    issues.append(
                        ExtractionIssue(
                            code="needs_visual_fallback",
                            message=(
                                "Page contains visual content but little "
                                "extractable text."
                            ),
                            source_locator={
                                "page": page_number,
                            },
                            requires_fallback=True,
                        )
                    )

                elif page_character_count == 0:
                    issues.append(
                        ExtractionIssue(
                            code="blank_page",
                            message=(
                                "Page contains no extractable text "
                                "or detected visual content."
                            ),
                            source_locator={
                                "page": page_number,
                            },
                        )
                    )

            return ExtractionResult(
                source_path=path,
                units=tuple(units),
                issues=tuple(issues),
                source_item_count=page_count,
                processed_item_count=processed_pages,
            )

        finally:
            document.close()