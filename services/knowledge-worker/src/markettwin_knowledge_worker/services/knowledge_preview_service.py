"""Application service around the existing source-to-knowledge pipeline."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from markettwin_shared.knowledge import KnowledgeBuildResult
from opentelemetry import trace

from markettwin_knowledge_worker.extraction import (
    ExtractionResult,
    UnsupportedSourceFormatError,
    extract_source,
)
from markettwin_knowledge_worker.knowledge_builder import KnowledgeBuilder


@dataclass(frozen=True, slots=True)
class KnowledgePreview:
    extraction: ExtractionResult
    result: KnowledgeBuildResult


class InvalidPreviewSourceError(ValueError):
    """The uploaded source cannot produce readable evidence."""


def extraction_failure_message(error: Exception) -> str:
    """User-safe reason for a failed extraction.

    Extractors raise coded errors whose messages are written for users
    (e.g. "Video requires too many clips."); preserve those verbatim.
    Anything else collapses to the generic unreadable-source message.
    """
    if getattr(error, "code", None):
        return str(error)
    return "The source could not be read."


class KnowledgePreviewService:
    def __init__(self, builder: KnowledgeBuilder, *, timeout_seconds: float = 600) -> None:
        self._builder = builder
        self._timeout_seconds = timeout_seconds

    @trace.get_tracer(__name__).start_as_current_span("knowledge.preview")
    async def preview(self, source_path: Path) -> KnowledgePreview:
        async with asyncio.timeout(self._timeout_seconds):
            return await self._preview(source_path)

    async def _preview(self, source_path: Path) -> KnowledgePreview:
        try:
            extraction = await extract_source(source_path)
        except (UnsupportedSourceFormatError, TimeoutError):
            raise
        except Exception as exc:
            raise InvalidPreviewSourceError(extraction_failure_message(exc)) from exc
        if not extraction.units:
            raise InvalidPreviewSourceError("The source has no readable content.")
        result = await self._builder.build(extraction)
        return KnowledgePreview(extraction=extraction, result=result)
