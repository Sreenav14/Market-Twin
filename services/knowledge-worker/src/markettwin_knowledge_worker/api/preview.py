"""Bounded private upload adapter for knowledge preview."""

import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from litellm.exceptions import APIError
from litellm.exceptions import Timeout as ModelTimeout
from markettwin_shared.knowledge_preview import (
    KnowledgePreviewEvidenceResponse,
    KnowledgePreviewIssueResponse,
    KnowledgePreviewResponse,
    KnowledgePreviewSourceResponse,
)
from pydantic import ValidationError

from markettwin_knowledge_worker.extraction import UnsupportedSourceFormatError
from markettwin_knowledge_worker.knowledge_builder import KnowledgeOutputLimitError
from markettwin_knowledge_worker.services.knowledge_preview_service import (
    InvalidPreviewSourceError,
    KnowledgePreview,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Internal knowledge preview"])
CHUNK_BYTES = 1024 * 1024
DEFAULT_MAX_BYTES = 50 * 1024 * 1024


def _safe_filename(filename: str | None) -> str:
    if (
        not filename
        or filename in {".", ".."}
        or any(character in filename for character in ("/", "\\", "\x00"))
    ):
        raise HTTPException(status_code=422, detail="A valid source filename is required.")
    return filename


async def _write_upload(upload: UploadFile, destination: Path, max_bytes: int) -> None:
    total = 0
    with destination.open("wb") as stream:
        while chunk := await upload.read(CHUNK_BYTES):
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail="This source is too large for knowledge preview.",
                )
            stream.write(chunk)
    if total == 0:
        raise HTTPException(status_code=422, detail="The source file is empty.")


def _response(preview: KnowledgePreview) -> KnowledgePreviewResponse:
    extraction = preview.extraction
    return KnowledgePreviewResponse(
        source=KnowledgePreviewSourceResponse(
            name=extraction.source_path.name,
            source_item_count=extraction.source_item_count,
            processed_item_count=extraction.processed_item_count,
        ),
        application_knowledge=preview.result.application_knowledge,
        artifacts=preview.result.artifacts,
        skills=preview.result.skills,
        evidence=tuple(
            KnowledgePreviewEvidenceResponse(
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
            KnowledgePreviewIssueResponse(
                code=issue.code,
                message=issue.message,
                source_locator=issue.source_locator,
                requires_fallback=issue.requires_fallback,
            )
            for issue in extraction.issues
        ),
    )


@router.post("/internal/v1/knowledge/preview", response_model=KnowledgePreviewResponse)
async def preview_knowledge(
    request: Request, file: Annotated[UploadFile, File()]
) -> KnowledgePreviewResponse:
    filename = _safe_filename(file.filename)
    max_bytes = int(os.getenv("KNOWLEDGE_PREVIEW_MAX_BYTES", str(DEFAULT_MAX_BYTES)))
    if max_bytes < 1:
        raise RuntimeError("KNOWLEDGE_PREVIEW_MAX_BYTES must be positive.")
    with TemporaryDirectory(prefix="markettwin-preview-") as root:
        source_path = Path(root) / filename
        await _write_upload(file, source_path, max_bytes)
        try:
            preview = await request.app.state.preview_service.preview(source_path)
        except UnsupportedSourceFormatError as exc:
            raise HTTPException(status_code=415, detail="Unsupported source format.") from exc
        except (TimeoutError, ModelTimeout) as exc:
            logger.exception("Knowledge preview model timed out")
            raise HTTPException(status_code=504, detail="Knowledge preview timed out.") from exc
        except InvalidPreviewSourceError as exc:
            logger.exception("Knowledge preview could not read the source")
            raise HTTPException(status_code=422, detail="The source could not be read.") from exc
        except KnowledgeOutputLimitError as exc:
            logger.exception("Knowledge generation reached its output limit")
            raise HTTPException(
                status_code=502,
                detail="Knowledge generation reached its output limit. "
                "Try a smaller source or a model with a larger output limit.",
            ) from exc
        except (ValueError, RuntimeError, ValidationError, APIError) as exc:
            logger.exception("Knowledge preview model failed")
            raise HTTPException(status_code=502, detail="Knowledge preview failed.") from exc
        except Exception as exc:
            logger.exception("Knowledge preview failed unexpectedly")
            raise HTTPException(status_code=500, detail="Knowledge preview failed.") from exc
        return _response(preview)
