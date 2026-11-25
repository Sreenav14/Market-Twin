"""Application service for the understanding pass (extract -> understand)."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from markettwin_shared.knowledge_markdown import KnowledgeMarkdownUsage, UnderstandResult
from opentelemetry import trace

from markettwin_knowledge_worker.config import KnowledgeConfig
from markettwin_knowledge_worker.extraction import (
    ExtractionResult,
    UnsupportedSourceFormatError,
    extract_source,
)
from markettwin_knowledge_worker.markdown_builder import MarkdownBuilder, understanding_budget
from markettwin_knowledge_worker.services.knowledge_preview_service import (
    InvalidPreviewSourceError,
    extraction_failure_message,
)


@dataclass(frozen=True, slots=True)
class KnowledgeMarkdown:
    extraction: ExtractionResult
    result: UnderstandResult
    usage: KnowledgeMarkdownUsage


class KnowledgeMarkdownService:
    def __init__(self, builder: MarkdownBuilder, *, timeout_seconds: float = 600) -> None:
        self._builder = builder
        self._timeout_seconds = timeout_seconds

    @trace.get_tracer(__name__).start_as_current_span("knowledge.markdown")
    async def markdown(
        self, source_path: Path, *, entry_id: UUID, workspace_id: UUID
    ) -> KnowledgeMarkdown:
        async with asyncio.timeout(self._timeout_seconds):
            return await self._markdown(source_path, entry_id=entry_id)

    async def _markdown(self, source_path: Path, *, entry_id: UUID) -> KnowledgeMarkdown:
        try:
            extraction = await extract_source(source_path)
        except (UnsupportedSourceFormatError, TimeoutError):
            raise
        except Exception as exc:
            raise InvalidPreviewSourceError(extraction_failure_message(exc)) from exc
        if not extraction.units:
            raise InvalidPreviewSourceError("The source has no readable content.")
        config = KnowledgeConfig.from_env()
        with understanding_budget(
            entry_id,
            max_calls=config.understanding_max_calls,
            max_tokens=config.understanding_max_tokens,
        ):
            result, usage = await self._builder.build(extraction)
        return KnowledgeMarkdown(extraction=extraction, result=result, usage=usage)
