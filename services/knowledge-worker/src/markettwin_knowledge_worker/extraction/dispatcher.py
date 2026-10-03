"""Dispatch source files to the correct MarketTwin extractor."""

import asyncio
from pathlib import Path

from markettwin_knowledge_worker.extraction.contracts import ExtractionResult
from markettwin_knowledge_worker.extraction.csv_file import CsvExtractor
from markettwin_knowledge_worker.extraction.docx import DocxExtractor
from markettwin_knowledge_worker.extraction.image import ImageExtractor
from markettwin_knowledge_worker.extraction.json_file import JsonExtractor
from markettwin_knowledge_worker.extraction.pdf import PdfExtractor
from markettwin_knowledge_worker.extraction.pptx import PptxExtractor
from markettwin_knowledge_worker.extraction.text import TextExtractor
from markettwin_knowledge_worker.extraction.video import VideoExtractor
from markettwin_knowledge_worker.extraction.xlsx import XlsxExtractor


class UnsupportedSourceFormatError(ValueError):
    """Raised when MarketTwin does not support a source format."""


async def extract_source(path: Path) -> ExtractionResult:
    """Extract any supported MarketTwin knowledge source."""

    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return await asyncio.to_thread(PdfExtractor().extract, path)

    if suffix == ".docx":
        return await asyncio.to_thread(DocxExtractor().extract, path)

    if suffix == ".pptx":
        return await asyncio.to_thread(PptxExtractor().extract, path)

    if suffix == ".xlsx":
        return await asyncio.to_thread(XlsxExtractor().extract, path)

    if suffix in {".txt", ".md"}:
        return await asyncio.to_thread(TextExtractor().extract, path)

    if suffix == ".csv":
        return await asyncio.to_thread(CsvExtractor().extract, path)

    if suffix == ".json":
        return await asyncio.to_thread(JsonExtractor().extract, path)

    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return await ImageExtractor().extract(path)

    if suffix in {".mp4", ".mov", ".webm"}:
        return await VideoExtractor().extract(path)

    raise UnsupportedSourceFormatError(
        f"Unsupported source format: {suffix or '<no extension>'}"
    )