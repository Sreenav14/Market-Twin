"""Dispatch source files to the correct MarketTwin extractor."""

import asyncio
import hashlib
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path

from opentelemetry import trace

from markettwin_knowledge_worker.extraction.contracts import ExtractionResult
from markettwin_knowledge_worker.extraction.image import ImageExtractor
from markettwin_knowledge_worker.extraction.isolated import extract_document
from markettwin_knowledge_worker.extraction.video import VideoExtractor


class UnsupportedSourceFormatError(ValueError):
    """Raised when MarketTwin does not support a source format."""


_DOCUMENT_SUFFIXES = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".csv", ".json"}
# The preview and markdown calls receive the same source bytes back to back,
# and document parsing runs in an isolated subprocess, so one content-addressed
# cache entry per distinct source removes the duplicate parse. Media results
# are not cached: image extraction is a stat, and video results own temporary
# clip files whose cleanup belongs to the first caller.
_EXTRACTION_CACHE_ENTRIES = 4
_document_extraction_cache: OrderedDict[str, ExtractionResult] = OrderedDict()


def _content_key(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"{digest.hexdigest()}{path.suffix.lower()}"


async def _extract_document_shared(path: Path) -> ExtractionResult:
    key = await asyncio.to_thread(_content_key, path)
    span = trace.get_current_span()
    cached = _document_extraction_cache.get(key)
    if cached is not None:
        _document_extraction_cache.move_to_end(key)
        span.set_attribute("knowledge.extraction.cache_hit", True)
        return replace(cached, source_path=path)
    span.set_attribute("knowledge.extraction.cache_hit", False)
    result = await extract_document(path)
    _document_extraction_cache[key] = result
    while len(_document_extraction_cache) > _EXTRACTION_CACHE_ENTRIES:
        _document_extraction_cache.popitem(last=False)
    return result


def clear_extraction_cache() -> None:
    """Drop cached document extractions (test hygiene; unused at runtime)."""
    _document_extraction_cache.clear()


async def extract_source(path: Path) -> ExtractionResult:
    """Extract any supported MarketTwin knowledge source."""

    suffix = path.suffix.lower()

    if suffix in _DOCUMENT_SUFFIXES:
        return await _extract_document_shared(path)

    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return await ImageExtractor().extract(path)

    if suffix in {".mp4", ".mov", ".webm"}:
        return await VideoExtractor().extract(path)

    raise UnsupportedSourceFormatError(
        f"Unsupported source format: {suffix or '<no extension>'}"
    )
