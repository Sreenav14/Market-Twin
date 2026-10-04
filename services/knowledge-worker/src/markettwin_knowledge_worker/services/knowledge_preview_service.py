"""Application service around the existing source-to-knowledge pipeline."""

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


class KnowledgePreviewService:
    def __init__(self, builder: KnowledgeBuilder) -> None:
        self._builder = builder

    @trace.get_tracer(__name__).start_as_current_span("knowledge.preview")
    async def preview(self, source_path: Path) -> KnowledgePreview:
        try:
            extraction = await extract_source(source_path)
        except UnsupportedSourceFormatError:
            raise
        except Exception as exc:
            raise InvalidPreviewSourceError("The source could not be read.") from exc
        if not extraction.units:
            raise InvalidPreviewSourceError("The source has no readable content.")
        result = await self._builder.build(extraction)
        return KnowledgePreview(extraction=extraction, result=result)
