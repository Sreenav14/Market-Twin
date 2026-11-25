"""Internal knowledge-file reads for the execution orchestrator.

Doc 33 section 3.6's read seam: the orchestrator gains no S3
credentials, so control-api serves file content and collection
manifests here, behind the same internal-secret pattern as the
knowledge-worker client. The caller pins file ids and sha256 hashes
in the run snapshot at creation; this surface returns the bytes and
the index data, and integrity is verified against the pin on both
sides (here against the index row, there against the snapshot).
"""

import hmac
import json
from hashlib import sha256
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.config import get_settings
from markettwin_control_api.knowledge.files import (
    KnowledgeFileRepository,
    manifest_object_key,
)
from markettwin_control_api.knowledge.storage import KnowledgeSourceStorage

router = APIRouter(
    tags=["Internal Knowledge Files"],
)


def _require_internal_secret(request: Request) -> None:
    """Bearer-check against KNOWLEDGE_INTERNAL_SECRET when configured.

    Settings already require the secret outside local/test; where it
    is unset the client sends no header either (the worker client
    pattern), so the check is a no-op there."""

    secret = get_settings().knowledge_internal_secret
    if secret is None:
        return
    expected = f"Bearer {secret.get_secret_value()}"
    provided = request.headers.get("authorization", "")
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Internal authentication required.",
        )


async def _download_text(object_key: str) -> str:
    settings = get_settings()
    storage = KnowledgeSourceStorage(settings)
    stream = BytesIO()
    await storage.download(
        bucket=settings.s3_bucket, key=object_key, stream=stream
    )
    return stream.getvalue().decode("utf-8")


@router.get("/internal/v1/knowledge-files/{file_id}/content")
async def knowledge_file_content(
    file_id: UUID, request: Request,
) -> dict[str, object]:
    """One pinned file's Markdown text plus its index metadata."""

    _require_internal_secret(request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        record = await KnowledgeFileRepository(session).get_by_id(file_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge file not found.",
        )
    try:
        text = await _download_text(record.object_key)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Knowledge file content is unavailable.",
        ) from None
    if sha256(text.encode("utf-8")).hexdigest() != record.sha256:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Knowledge file content failed its integrity check.",
        )
    return {
        "file_id": str(record.id),
        "entry_id": str(record.ingestion_entry_id),
        "slug": record.slug,
        "title": record.title,
        "description": record.description,
        "object_key": record.object_key,
        "sha256": record.sha256,
        "token_count": record.token_count,
        "version": record.version,
        "text": text,
    }


@router.get("/internal/v1/knowledge-files/collections/{entry_id}/manifest")
async def knowledge_collection_manifest(
    entry_id: UUID, request: Request, version: int = Query(gt=0),
) -> dict[str, object]:
    """One pinned collection version's file index (titles and
    descriptions only — never bodies). Section headings are merged
    from the stored manifest when it can be read; the index rows
    alone are sufficient for selection."""

    _require_internal_secret(request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        rows = await KnowledgeFileRepository(session).list_entry_version(
            entry_id=entry_id, version=version,
        )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge collection version not found.",
        )
    headings: dict[str, list[str]] = {}
    try:
        manifest = json.loads(
            await _download_text(
                manifest_object_key(rows[0].workspace_id, entry_id, version)
            )
        )
        for entry in manifest.get("files", []):
            if isinstance(entry, dict) and isinstance(entry.get("slug"), str):
                raw = entry.get("section_headings")
                headings[entry["slug"]] = (
                    [str(item) for item in raw if isinstance(item, str)]
                    if isinstance(raw, list) else []
                )
    except Exception:
        headings = {}
    return {
        "entry_id": str(entry_id),
        "version": version,
        "files": [
            {
                "file_id": str(row.id),
                "slug": row.slug,
                "title": row.title,
                "description": row.description,
                "object_key": row.object_key,
                "sha256": row.sha256,
                "token_count": row.token_count,
                "section_headings": headings.get(row.slug, []),
            }
            for row in rows
        ],
    }
