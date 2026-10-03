"""Deterministic extraction from plain-text and Markdown files."""

from pathlib import Path

from markettwin_knowledge_worker.extraction.chunking import SourcePart, text_evidence
from markettwin_knowledge_worker.extraction.contracts import (
    ExtractionIssue,
    ExtractionResult,
)


class TextExtractionError(RuntimeError):
    """Raised when a text document cannot be extracted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class TextExtractor:
    """Extract the complete meaningful text from TXT or Markdown files."""

    name = "python-text"
    version = "1"

    def extract(self, path: Path) -> ExtractionResult:
        """Return the complete source text with line provenance."""

        try:
            text = path.read_text(
                encoding="utf-8-sig",
            ).strip()
        except (OSError, UnicodeDecodeError) as exc:
            raise TextExtractionError(
                "parsing_failed",
                f"Unable to extract text file: {path.name}",
            ) from exc

        if not text:
            return ExtractionResult(
                source_path=path,
                units=(),
                issues=(
                    ExtractionIssue(
                        code="blank_document",
                        message="Text document contains no extractable content.",
                        source_locator={},
                    ),
                ),
                source_item_count=1,
                processed_item_count=1,
            )

        parts = tuple(
            SourcePart(text=line, locator={"line": line_number})
            for line_number, line in enumerate(text.splitlines(), start=1)
            if line.strip()
        )

        return ExtractionResult(
            source_path=path,
            units=text_evidence(
                parts,
                extractor_name=self.name,
                extractor_version=self.version,
                separator="\n",
            ),
            issues=(),
            source_item_count=len(parts),
            processed_item_count=len(parts),
        )
