"""Workspace ingestion, review, and approval of source-backed knowledge."""

import hashlib
import logging
from datetime import datetime
from io import BytesIO
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from markettwin_database.models.knowledge import ApplicationKnowledgeEntry, KnowledgeFile
from markettwin_database.models.testing import Application
from markettwin_shared.knowledge_markdown import (
    KnowledgeEvidenceIndex,
    KnowledgeManifest,
    MarkdownEvidenceUnit,
)
from markettwin_shared.knowledge_preview import (
    KnowledgePreviewResponse,
    KnowledgePreviewSourceResponse,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import Headers

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import get_authenticated_user_id
from markettwin_control_api.api.permissions import WORKSPACE_WRITE_ROLES
from markettwin_control_api.config import get_settings
from markettwin_control_api.evidence.artifact_url_signer import ArtifactUrlSigner
from markettwin_control_api.knowledge.link_research import (
    LINK_MARKER_TYPE,
    decode_link_marker,
    encode_link_marker,
    validate_link_target,
)
from markettwin_control_api.knowledge.repository import (
    IngestionRecord,
    IngestionRepository,
    validate_approval,
)
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


class KnowledgeFileIndexResponse(BaseModel):
    """One knowledge_files index row (doc 33 §3.5); bodies are not served here."""

    id: UUID
    slug: str
    title: str
    description: str
    token_count: int
    sha256: str
    version: int
    status: str


class KnowledgeFileContentResponse(BaseModel):
    slug: str
    title: str
    description: str
    markdown: str
    evidence: list[MarkdownEvidenceUnit]


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
    file_count: int = 0
    processing_status: Literal["queued", "processing", "ready", "failed"]
    processing_error: str | None
    original_source_url: str | None = None
    processing_stage: Literal["queued", "researching", "generating", "review", "approved", "failed"]
    application_ids: list[UUID] = Field(default_factory=list[UUID])


class IngestionEntryResponse(IngestionSummaryResponse):
    preview: KnowledgePreviewResponse
    files: list[KnowledgeFileIndexResponse] = Field(default_factory=list)


class UpdateKnowledgeFileRequest(BaseModel):
    """Title/description edit (doc 33 §3.5, OD-K2: bodies are not editable)."""

    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=200)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("A file title is required.")
        return value

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if "\n" in value or "\r" in value:
            raise ValueError("A file description is one line.")
        return value


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


class LinkKnowledgeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    name: str = Field(min_length=1, max_length=200)
    roles: list[str] = Field(min_length=1, max_length=9)


@router.post("/link", response_model=IngestionEntryResponse, status_code=202)
async def ingest_link(
    workspace_id: UUID, payload: LinkKnowledgeRequest, request: Request,
) -> IngestionEntryResponse:
    await require_ingestion_access(request, workspace_id, write=True)
    if (not payload.name.strip() or len(set(payload.roles)) != len(payload.roles)
            or not set(payload.roles) <= SOURCE_ROLES):
        raise HTTPException(422, "Enter a name and valid source purposes.")
    try:
        url = validate_link_target(payload.url)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    host = urlsplit(url).hostname or "link"
    source = UploadFile(
        filename=f"{host}-link.txt",
        file=BytesIO(encode_link_marker(url)),
        headers=Headers({"content-type": LINK_MARKER_TYPE}),
    )
    try:
        return await ingest_source(workspace_id, request, source, payload.name, payload.roles)
    finally:
        await source.close()


def knowledge_file_response(row: KnowledgeFile) -> KnowledgeFileIndexResponse:
    return KnowledgeFileIndexResponse(
        id=row.id, slug=row.slug, title=row.title, description=row.description,
        token_count=row.token_count, sha256=row.sha256, version=row.version,
        status=row.status,
    )


def ingestion_response(
    record: IngestionRecord,
    *,
    files: list[KnowledgeFile] | None = None,
    file_count: int | None = None,
) -> IngestionEntryResponse:
    preview = KnowledgePreviewResponse.model_validate(record.entry.preview)
    asset_status = record.asset.status
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
        file_count=(
            file_count if file_count is not None
            else len(files) if files is not None
            else 0
        ),
        files=[knowledge_file_response(row) for row in files] if files is not None else [],
        processing_status=(
            "queued" if record.asset.status == "uploaded"
            else "processing" if record.asset.status == "processing"
            else "failed" if record.asset.status in {"unsupported", "too_large", "parsing_failed"}
            else "ready"
        ),
        processing_error=record.asset.status_message,
        original_source_url=preview.source.original_url,
        processing_stage=(
            "queued" if asset_status == "uploaded"
            else "researching" if asset_status == "processing"
            and record.asset.declared_content_type == LINK_MARKER_TYPE
            else "generating" if asset_status == "processing"
            else "failed" if asset_status in {"unsupported", "too_large", "parsing_failed"}
            else "approved" if record.version.status == "approved"
            else "review"
        ),
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
        counts = await repository.knowledge_file_counts(
            [record.entry.id for record in records]
        )
        return [
            IngestionSummaryResponse.model_validate(
                ingestion_response(
                    record, file_count=counts.get(record.entry.id, 0)
                ).model_dump()
            )
            for record in records
        ]


@router.get("/{entry_id}", response_model=IngestionEntryResponse)
async def get_ingestion(
    workspace_id: UUID, entry_id: UUID, request: Request
) -> IngestionEntryResponse:
    await require_ingestion_access(request, workspace_id, write=False)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        repository = IngestionRepository(session)
        record = await repository.get(workspace_id, entry_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Knowledge set not found.")
        files = await repository.list_knowledge_files(entry_id)
        return ingestion_response(record, files=files)


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
    original_url = None
    if file.content_type == LINK_MARKER_TYPE:
        if size > 4096:
            raise HTTPException(status_code=422, detail="The link manifest is invalid.")
        original_url = decode_link_marker(await file.read())
        if original_url is None:
            raise HTTPException(status_code=422, detail="The link manifest is invalid.")
        try:
            original_url = validate_link_target(original_url)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        await file.seek(0)
    preview = KnowledgePreviewResponse(
        source=KnowledgePreviewSourceResponse(
            name=file.filename, source_item_count=0, processed_item_count=0,
            original_url=original_url,
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
            try:
                validate_approval(record)
            except ValueError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            await repository.approve(record, user_id)
            files = await repository.list_knowledge_files(entry_id)
            return ingestion_response(record, files=files)


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
        signer = ArtifactUrlSigner(region=settings.s3_region, endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.aws_access_key_id,
            secret_access_key=(settings.aws_secret_access_key.get_secret_value()
                               if settings.aws_secret_access_key else None),
            session_token=(settings.aws_session_token.get_secret_value()
                           if settings.aws_session_token else None))
        return {
            "url": signer.create_download_url(
                bucket=record.asset.bucket,
                object_key=record.asset.object_key,
                download_filename=record.asset.original_filename,
            )
        }


async def _read_knowledge_object(storage: KnowledgeSourceStorage, key: str) -> bytes:
    buffer = BytesIO()
    await storage.download(bucket=storage.bucket, key=key, stream=buffer)
    return buffer.getvalue()


@router.get("/{entry_id}/files/{slug}", response_model=KnowledgeFileContentResponse)
async def get_knowledge_file_content(
    workspace_id: UUID, entry_id: UUID, slug: str, request: Request
) -> KnowledgeFileContentResponse:
    await require_ingestion_access(request, workspace_id, write=False)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        repository = IngestionRepository(session)
        record = await repository.get(workspace_id, entry_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Knowledge set not found.")
        row = await repository.get_knowledge_file(entry_id, slug)
        if row is None:
            raise HTTPException(status_code=404, detail="Knowledge file not found.")
    storage = KnowledgeSourceStorage(get_settings())
    prefix = row.object_key.rsplit("/", 1)[0]
    try:
        markdown = await _read_knowledge_object(storage, row.object_key)
        manifest = KnowledgeManifest.model_validate_json(
            await _read_knowledge_object(storage, f"{prefix}/manifest.json")
        )
        index = KnowledgeEvidenceIndex.model_validate_json(
            await _read_knowledge_object(storage, f"{prefix}/evidence.json")
        )
    except Exception as exc:
        logger.exception("Could not read knowledge file %s for entry %s", slug, entry_id)
        raise HTTPException(
            status_code=503, detail="Knowledge file content is unavailable."
        ) from exc
    cited = next(
        (file.evidence_ordinals for file in manifest.files if file.slug == slug), ()
    )
    wanted = set(cited)
    return KnowledgeFileContentResponse(
        slug=row.slug, title=row.title, description=row.description,
        markdown=markdown.decode("utf-8"),
        evidence=[unit for unit in index.units if unit.ordinal in wanted],
    )


@router.patch("/{entry_id}/files/{slug}", response_model=KnowledgeFileIndexResponse)
async def update_knowledge_file(
    workspace_id: UUID, entry_id: UUID, slug: str,
    payload: UpdateKnowledgeFileRequest, request: Request,
) -> KnowledgeFileIndexResponse:
    await require_ingestion_access(request, workspace_id, write=True)
    if payload.title is None and payload.description is None:
        raise HTTPException(
            status_code=422, detail="Provide a title or a description to update."
        )
    database = get_database_runtime(request)
    storage = KnowledgeSourceStorage(get_settings())
    async with database.session_factory() as session:
        async with session.begin():
            repository = IngestionRepository(session)
            record = await repository.get(workspace_id, entry_id, lock=True)
            if record is None:
                raise HTTPException(status_code=404, detail="Knowledge set not found.")
            row = await repository.get_knowledge_file(entry_id, slug)
            if row is None:
                raise HTTPException(status_code=404, detail="Knowledge file not found.")
            await repository.update_knowledge_file(
                row, title=payload.title, description=payload.description,
            )
            # Title/description are the selection surface (§3.5): the
            # version's manifest carries the same fields for run-start
            # selection, so it is updated in step. The .md bytes and
            # their sha never change (OD-K3). A storage failure aborts
            # the transaction, leaving row and manifest in step.
            prefix = row.object_key.rsplit("/", 1)[0]
            try:
                manifest = KnowledgeManifest.model_validate_json(
                    await _read_knowledge_object(storage, f"{prefix}/manifest.json")
                )
                manifest = manifest.model_copy(update={
                    "files": tuple(
                        file.model_copy(update={
                            "title": row.title, "description": row.description,
                        }) if file.slug == slug else file
                        for file in manifest.files
                    ),
                })
                await storage.put(
                    key=f"{prefix}/manifest.json",
                    stream=BytesIO(manifest.model_dump_json().encode("utf-8")),
                    content_type="application/json",
                )
            except HTTPException:
                raise
            except Exception as exc:
                logger.exception(
                    "Could not sync manifest for knowledge file %s of entry %s",
                    slug, entry_id,
                )
                raise HTTPException(
                    status_code=503, detail="Knowledge file storage is unavailable."
                ) from exc
            return knowledge_file_response(row)
