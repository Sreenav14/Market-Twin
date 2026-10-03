"""Normalize DOCX paragraphs and tables in document order, then bound source chunks."""

from pathlib import Path
from zipfile import BadZipFile

import docx
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.text.paragraph import Paragraph

from markettwin_knowledge_worker.extraction.chunking import SourcePart, text_evidence
from markettwin_knowledge_worker.extraction.contracts import ExtractionIssue, ExtractionResult


class DocxExtractionError(RuntimeError):
    """Raised when a DOCX document cannot be extracted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DocxExtractor:
    """Keep meaningful structural parts together instead of persisting parser objects."""

    name = "python-docx"
    version = docx.__version__

    def extract(self, path: Path) -> ExtractionResult:
        try:
            document = Document(str(path))
        except (OSError, PackageNotFoundError, BadZipFile, ValueError, KeyError) as exc:
            raise DocxExtractionError(
                "parsing_failed", f"Unable to extract DOCX: {path.name}"
            ) from exc
        parts: list[SourcePart] = []
        paragraph_number = table_number = 0
        for item in document.iter_inner_content():
            if isinstance(item, Paragraph):
                paragraph_number += 1
                text = item.text.strip()
                if text:
                    style = item.style
                    style_name = style.name if style is not None else None
                    if style_name is not None and style_name.startswith("Heading "):
                        level = style_name.removeprefix("Heading ")
                        if level.isdigit():
                            text = f"{'#' * int(level)} {text}"
                    parts.append(SourcePart(text, {"paragraph": paragraph_number}))
            else:
                table_number += 1
                rows = [
                    " | ".join(cell.text.strip() for cell in row.cells)
                    for row in item.rows
                    if any(cell.text.strip() for cell in row.cells)
                ]
                if rows:
                    parts.append(
                        SourcePart(
                            "[TABLE]\n" + "\n".join(rows) + "\n[/TABLE]", {"table": table_number}
                        )
                    )
        units = text_evidence(parts, extractor_name=self.name, extractor_version=self.version)
        issues = (
            ()
            if units
            else (ExtractionIssue("blank_document", "DOCX contains no extractable content.", {}),)
        )
        return ExtractionResult(path, units, issues, len(parts), len(parts))
