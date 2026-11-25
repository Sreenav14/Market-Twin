"""Bounded private upload adapter for the understanding pass (doc 33)."""

import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from litellm.exceptions import APIError
from litellm.exceptions import Timeout as ModelTimeout
from markettwin_shared.knowledge_markdown import (
    KnowledgeMarkdownResponse,
    KnowledgeMarkdownSource,
    MarkdownEvidenceUnit,
    MarkdownExtractionIssue,
)
from pydantic import ValidationError

from markettwin_knowledge_worker.api.preview import (
    DEFAULT_MAX_BYTES,
    _safe_filename,
    _write_upload,
)
from markettwin_knowledge_worker.extraction import UnsupportedSourceFormatError
from markettwin_knowledge_worker.knowledge_builder import KnowledgeOutputLimitError
from markettwin_knowledge_worker.services.knowledge_markdown_service import KnowledgeMarkdown
from markettwin_knowledge_worker.services.knowledge_preview_service import (
    InvalidPreviewSourceError,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Internal knowledge markdown"])


def _response(markdown: KnowledgeMarkdown) -> KnowledgeMarkdownResponse:
    extraction = markdown.extraction
    return KnowledgeMarkdownResponse(
        source=KnowledgeMarkdownSource(
            name=extraction.source_path.name,
            source_item_count=extraction.source_item_count,
            processed_item_count=extraction.processed_item_count,
        ),
        files=markdown.result.files,
        evidence=tuple(
            MarkdownEvidenceUnit(
                ordinal=unit.ordinal,
                evidence_type=unit.evidence_type,
                content_text=unit.content_text,
                content_json=unit.content_json,
                source_locator=unit.source_locator,
                extractor_name=unit.extractor_name,
                extractor_version=unit.extractor_version,
            )
            for unit in extraction.units
        ),
        extraction_issues=tuple(
            MarkdownExtractionIssue(
                code=issue.code,
                message=issue.message,
                source_locator=issue.source_locator,
                requires_fallback=issue.requires_fallback,
            )
            for issue in extraction.issues
        ),
        usage=markdown.usage,
    )


@router.post("/internal/v1/knowledge/markdown", response_model=KnowledgeMarkdownResponse)
async def markdown_knowledge(
    request: Request,
    file: Annotated[UploadFile, File()],
    entry_id: Annotated[str, Form()],
    workspace_id: Annotated[str, Form()],
) -> KnowledgeMarkdownResponse:
    filename = _safe_filename(file.filename)
    try:
        entry_uuid = UUID(entry_id)
        workspace_uuid = UUID(workspace_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Valid entry and workspace identifiers are required."
        ) from exc
    max_bytes = int(os.getenv("KNOWLEDGE_PREVIEW_MAX_BYTES", str(DEFAULT_MAX_BYTES)))
    if max_bytes < 1:
        raise RuntimeError("KNOWLEDGE_PREVIEW_MAX_BYTES must be positive.")
    with TemporaryDirectory(prefix="markettwin-markdown-") as root:
        source_path = Path(root) / filename
        await _write_upload(file, source_path, max_bytes)
        try:
            markdown = await request.app.state.markdown_service.markdown(
                source_path, entry_id=entry_uuid, workspace_id=workspace_uuid
            )
        except UnsupportedSourceFormatError as exc:
            raise HTTPException(status_code=415, detail="Unsupported source format.") from exc
        except (TimeoutError, ModelTimeout) as exc:
            logger.warning("Knowledge markdown model timed out (%s)", type(exc).__name__)
            raise HTTPException(status_code=504, detail="Knowledge generation timed out.") from exc
        except InvalidPreviewSourceError as exc:
            logger.warning("Knowledge markdown could not read the source (%s)", type(exc).__name__)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KnowledgeOutputLimitError as exc:
            logger.warning("Knowledge generation reached its output limit (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=502,
                detail="Knowledge generation reached its output limit. "
                "Try a smaller source or a model with a larger output limit.",
            ) from exc
        except (ValueError, RuntimeError, ValidationError, APIError) as exc:
            logger.warning("Knowledge markdown model failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=502, detail="Knowledge generation failed.") from exc
        except Exception as exc:
            logger.warning("Knowledge markdown failed unexpectedly (%s)", type(exc).__name__)
            raise HTTPException(status_code=500, detail="Knowledge generation failed.") from exc
        return _response(markdown)
