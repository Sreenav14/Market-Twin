"""Dispatch source files to the correct MarketTwin extractor."""

from pathlib import Path

from markettwin_knowledge_worker.extraction.contracts import ExtractionResult
from markettwin_knowledge_worker.extraction.image import ImageExtractor
from markettwin_knowledge_worker.extraction.isolated import extract_document
from markettwin_knowledge_worker.extraction.video import VideoExtractor


class UnsupportedSourceFormatError(ValueError):
    """Raised when MarketTwin does not support a source format."""


async def extract_source(path: Path) -> ExtractionResult:
    """Extract any supported MarketTwin knowledge source."""

    suffix = path.suffix.lower()

    if suffix in {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".csv", ".json"}:
        return await extract_document(path)

    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return await ImageExtractor().extract(path)

    if suffix in {".mp4", ".mov", ".webm"}:
        return await VideoExtractor().extract(path)

    raise UnsupportedSourceFormatError(
        f"Unsupported source format: {suffix or '<no extension>'}"
    )
