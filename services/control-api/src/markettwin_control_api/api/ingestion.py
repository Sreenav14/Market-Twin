"""Workspace ingestion, review, and approval of source-backed knowledge."""

import hashlib
import logging
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from markettwin_database.models.knowledge import ApplicationKnowledgeEntry
from markettwin_database.models.testing import Application
from markettwin_shared.knowledge_preview import (
    KnowledgePreviewResponse,
    KnowledgePreviewSourceResponse,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import get_authenticated_user_id
from markettwin_control_api.api.permissions import WORKSPACE_WRITE_ROLES
from markettwin_control_api.config import get_settings
from markettwin_control_api.evidence.artifact_url_signer import ArtifactUrlSigner
from markettwin_control_api.knowledge.repository import IngestionRecord, IngestionRepository
from markettwin_control_api.knowledge.storage import KnowledgeSourceStorage
from markettwin_control_api.persistence.repositories import WorkspaceRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/ingestion", tags=["Ingestion"])
SOURCE_ROLES = frozenset(
    {
        "demonstration",
        "product_knowledge",
        "business_rules",
        "safety_policy",
        "test_input",
        "ground_truth",
        "ui_reference",
        "persona_evidence",
        "environment_configuration",
    }
)


class IngestionSummaryResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    source_name: str
    status: str
    roles: list[str]
    created_at: datetime
    approved_at: datetime | None
    knowledge_count: int
    artifact_count: int
    skill_count: int
    issue_count: int
    processing_status: Literal["queued", "processing", "ready", "failed"]
    processing_error: str | None
    application_ids: list[UUID] = Field(default_factory=list[UUID])


class IngestionEntryResponse(IngestionSummaryResponse):
    preview: KnowledgePreviewResponse


class RenameKnowledgeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Knowledge name is required.")
        return value


class AttachKnowledgeRequest(BaseModel):
    application_ids: list[UUID] = Field(max_length=100)

    @field_validator("application_ids")
    @classmethod
    def unique_applications(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Select each application once.")
        return value


def ingestion_response(record: IngestionRecord) -> IngestionEntryResponse:
    preview = KnowledgePreviewResponse.model_validate(record.entry.preview)
    return IngestionEntryResponse(
        id=record.entry.id,
        workspace_id=record.entry.workspace_id,
        name=record.blueprint.name,
        source_name=record.asset.original_filename,
        status=record.version.status,
        roles=record.pin.roles,
        created_at=record.version.created_at,
        approved_at=record.version.approved_at,
        knowledge_count=len(preview.application_knowledge),
        artifact_count=len(preview.artifacts),
        skill_count=len(preview.skills),
        issue_count=len(preview.extraction_issues),
        processing_status=(
            "queued" if record.asset.status == "uploaded"
            else "processing" if record.asset.status == "processing"
            else "failed" if record.asset.status in {"unsupported", "too_large", "parsing_failed"}
            else "ready"
        ),
        processing_error=record.asset.status_message,
        application_ids=[link.application_id for link in record.entry.application_links],
        preview=preview,
    )


async def require_ingestion_access(request: Request, workspace_id: UUID, *, write: bool) -> UUID:
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        workspace = await WorkspaceRepository(session).get_for_user(
            workspace_id=workspace_id, user_id=user_id
        )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if write and workspace.role not in WORKSPACE_WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Workspace write access is required.")
    return user_id


@router.get("", response_model=list[IngestionSummaryResponse])
async def list_ingestion(
    workspace_id: UUID, request: Request, application_id: UUID | None = None
) -> list[IngestionSummaryResponse]:
    await require_ingestion_access(request, workspace_id, write=False)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        repository = IngestionRepository(session)
        if application_id is None:
            records = await repository.list_entries(workspace_id)
        else:
            application = await session.get(Application, application_id)
            if (
                application is None or application.workspace_id != workspace_id
                or application.status != "active" or application.deleted_at is not None
            ):
                raise HTTPException(status_code=404, detail="Application not found.")
            records = await repository.list_for_application(workspace_id, application_id)
        return [
            IngestionSummaryResponse.model_validate(ingestion_response(record).model_dump())
            for record in records
        ]


@router.get("/{entry_id}", response_model=IngestionEntryResponse)
async def get_ingestion(
    workspace_id: UUID, entry_id: UUID, request: Request
) -> IngestionEntryResponse:
    await require_ingestion_access(request, workspace_id, write=False)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        record = await IngestionRepository(session).get(workspace_id, entry_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Knowledge set not found.")
        return ingestion_response(record)


@router.post("", response_model=IngestionEntryResponse, status_code=202)
async def ingest_source(
    workspace_id: UUID,
    request: Request,
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form(min_length=1, max_length=200)],
    roles: Annotated[list[str], Form()],
) -> IngestionEntryResponse:
    user_id = await require_ingestion_access(request, workspace_id, write=True)
    name = name.strip()
    if not name or not roles or len(set(roles)) != len(roles) or not set(roles) <= SOURCE_ROLES:
        raise HTTPException(
            status_code=422, detail="Enter a name and at least one valid source role."
        )
    if (
        not file.filename
        or len(file.filename) > 512
        or any(c in file.filename for c in ("/", "\\", "\x00"))
    ):
        raise HTTPException(status_code=422, detail="A valid source filename is required.")
    settings = get_settings()
    digest, size = hashlib.sha256(), 0
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > settings.knowledge_preview_max_bytes:
            raise HTTPException(status_code=413, detail="This source is too large for ingestion.")
        digest.update(chunk)
    if size == 0:
        raise HTTPException(status_code=422, detail="The source file is empty.")
    await file.seek(0)
    preview = KnowledgePreviewResponse(
        source=KnowledgePreviewSourceResponse(
            name=file.filename, source_item_count=0, processed_item_count=0
        ),
        application_knowledge=(), artifacts=(), skills=(), evidence=(), extraction_issues=(),
    )
    entry_id = uuid4()
    key = f"knowledge/{workspace_id}/{entry_id}/source"
    try:
        storage = KnowledgeSourceStorage(settings)
        await storage.put(key=key, stream=file.file, content_type=file.content_type)
    except Exception as exc:
        logger.exception("Could not store ingestion source")
        raise HTTPException(status_code=503, detail="Source storage is unavailable.") from exc
    database = get_database_runtime(request)
    try:
        async with database.session_factory() as session:
            async with session.begin():
                record = await IngestionRepository(session).create(
                    entry_id=entry_id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    name=name,
                    roles=roles,
                    preview=preview,
                    bucket=storage.bucket,
                    object_key=key,
                    size_bytes=size,
                    sha256=digest.hexdigest(),
                    content_type=file.content_type,
                    pending=True,
                )
                response = ingestion_response(record)
    except Exception as exc:
        try:
            await storage.delete(key=key)
        except Exception:
            logger.exception("Could not remove source after ingestion transaction failed")
        if isinstance(exc, IntegrityError):
            raise HTTPException(
                status_code=409, detail="A knowledge set with that name already exists."
            ) from exc
        raise
    return response


@router.delete("/{entry_id}", status_code=204)
async def delete_ingestion(workspace_id: UUID, entry_id: UUID, request: Request) -> Response:
    await require_ingestion_access(request, workspace_id, write=True)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        async with session.begin():
            repository = IngestionRepository(session)
            record = await repository.get(workspace_id, entry_id, lock=True)
            if record is None:
                raise HTTPException(status_code=404, detail="Knowledge set not found.")
            await repository.archive(record)
    return Response(status_code=204)


@router.patch("/{entry_id}", response_model=IngestionEntryResponse)
async def rename_ingestion(
    workspace_id: UUID, entry_id: UUID, payload: RenameKnowledgeRequest, request: Request
) -> IngestionEntryResponse:
    await require_ingestion_access(request, workspace_id, write=True)
    database = get_database_runtime(request)
    try:
        async with database.session_factory() as session:
            async with session.begin():
                record = await IngestionRepository(session).get(workspace_id, entry_id, lock=True)
                if record is None:
                    raise HTTPException(status_code=404, detail="Knowledge set not found.")
                record.blueprint.name = payload.name
                await session.flush()
                return ingestion_response(record)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="A knowledge set with that name exists."
        ) from exc


@router.put("/{entry_id}/applications", response_model=IngestionEntryResponse)
async def attach_ingestion(
    workspace_id: UUID, entry_id: UUID, payload: AttachKnowledgeRequest, request: Request
) -> IngestionEntryResponse:
    user_id = await require_ingestion_access(request, workspace_id, write=True)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        async with session.begin():
            record = await IngestionRepository(session).get(workspace_id, entry_id, lock=True)
            if record is None:
                raise HTTPException(status_code=404, detail="Knowledge set not found.")
            if record.version.status != "approved" or record.asset.status != "included":
                raise HTTPException(
                    status_code=409, detail="Approve knowledge before attaching it."
                )
            selected = set(payload.application_ids)
            valid = set((await session.scalars(select(Application.id).where(
                Application.id.in_(selected), Application.workspace_id == workspace_id,
                Application.status == "active", Application.deleted_at.is_(None),
            ))).all())
            if valid != selected:
                raise HTTPException(status_code=404, detail="Selected application not found.")
            existing = {link.application_id: link for link in record.entry.application_links}
            record.entry.application_links = [
                existing[app_id] if app_id in existing else ApplicationKnowledgeEntry(
                    workspace_id=workspace_id, application_id=app_id, ingestion_entry_id=entry_id,
                    attached_by_user_id=user_id,
                ) for app_id in payload.application_ids
            ]
            await session.flush()
            return ingestion_response(record)


@router.post("/{entry_id}/approve", response_model=IngestionEntryResponse)
async def approve_ingestion(
    workspace_id: UUID, entry_id: UUID, request: Request
) -> IngestionEntryResponse:
    user_id = await require_ingestion_access(request, workspace_id, write=True)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        async with session.begin():
            repository = IngestionRepository(session)
            record = await repository.get(workspace_id, entry_id, lock=True)
            if record is None:
                raise HTTPException(status_code=404, detail="Knowledge set not found.")
            if record.asset.status in {"uploaded", "processing"}:
                raise HTTPException(status_code=409, detail="Knowledge is still processing.")
            preview = KnowledgePreviewResponse.model_validate(record.entry.preview)
            if not (preview.application_knowledge or preview.artifacts or preview.skills):
                raise HTTPException(
                    status_code=409, detail="There is no generated knowledge to approve."
                )
            await repository.approve(record, user_id)
            return ingestion_response(record)


@router.post("/{entry_id}/retry", response_model=IngestionEntryResponse, status_code=202)
async def retry_ingestion(
    workspace_id: UUID, entry_id: UUID, request: Request
) -> IngestionEntryResponse:
    await require_ingestion_access(request, workspace_id, write=True)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        async with session.begin():
            repository = IngestionRepository(session)
            record = await repository.get(workspace_id, entry_id, lock=True)
            if record is None:
                raise HTTPException(status_code=404, detail="Knowledge set not found.")
            if record.asset.status not in {"unsupported", "too_large", "parsing_failed"}:
                raise HTTPException(status_code=409, detail="Only failed ingestion can be retried.")
            record.asset.status = "uploaded"
            record.asset.status_message = None
            record.asset.processed_at = None
            await session.flush()
            return ingestion_response(record)


@router.get("/{entry_id}/source-access")
async def source_access(workspace_id: UUID, entry_id: UUID, request: Request) -> dict[str, str]:
    await require_ingestion_access(request, workspace_id, write=False)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        record = await IngestionRepository(session).get(workspace_id, entry_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Knowledge set not found.")
        settings = get_settings()
        signer = ArtifactUrlSigner(region=settings.s3_region, endpoint_url=settings.s3_endpoint_url)
        return {
            "url": signer.create_download_url(
                bucket=record.asset.bucket,
                object_key=record.asset.object_key,
                download_filename=record.asset.original_filename,
            )
        }
