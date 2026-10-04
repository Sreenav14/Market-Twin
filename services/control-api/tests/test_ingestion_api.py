"""Workspace permissions, saved source drafts, and explicit approval."""

from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.testclient import TestClient
from markettwin_control_api.api import ingestion
from markettwin_control_api.knowledge.repository import IngestionRecord
from markettwin_database.models.knowledge import (
    AssetVersion,
    BlueprintVersion,
    BlueprintVersionAsset,
    IngestionEntry,
    ProductBlueprint,
)
from markettwin_shared.knowledge_preview import KnowledgePreviewResponse


class Context:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *args):
        return False


def request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": []})


def preview() -> KnowledgePreviewResponse:
    return KnowledgePreviewResponse.model_validate(
        {
            "source": {"name": "source.txt", "source_item_count": 1, "processed_item_count": 1},
            "application_knowledge": [
                {
                    "name": "Context",
                    "content": "Source facts",
                    "evidence_ordinals": [1],
                    "grounding_confidence": "high",
                    "warnings": [],
                }
            ],
            "artifacts": [],
            "skills": [],
            "evidence": [],
            "extraction_issues": [],
        }
    )


def record(status="draft") -> IngestionRecord:
    workspace_id, blueprint_id, entry_id, asset_id = (uuid4() for _ in range(4))
    return IngestionRecord(
        IngestionEntry(
            id=entry_id,
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            asset_version_id=asset_id,
            preview=preview().model_dump(mode="json"),
        ),
        BlueprintVersion(
            id=entry_id,
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            status=status,
            created_at=datetime.now(UTC),
        ),
        ProductBlueprint(id=blueprint_id, name="Source knowledge"),
        AssetVersion(
            id=asset_id, original_filename="source.txt", bucket="sources", object_key="source"
        ),
        BlueprintVersionAsset(roles=["product_knowledge"]),
    )


def patch_database(monkeypatch):
    session = SimpleNamespace(begin=Context, flush=AsyncMock(), scalars=AsyncMock())
    monkeypatch.setattr(
        ingestion,
        "get_database_runtime",
        lambda _: SimpleNamespace(session_factory=lambda: Context(session)),
    )
    return session


def test_ingestion_requires_a_session() -> None:
    app = FastAPI()
    app.include_router(ingestion.router)
    with TestClient(app) as client:
        response = client.get(f"/api/v1/workspaces/{uuid4()}/ingestion")
    assert response.status_code == 401


async def test_read_only_member_cannot_ingest(monkeypatch):
    patch_database(monkeypatch)
    monkeypatch.setattr(ingestion, "get_authenticated_user_id", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(
        ingestion,
        "WorkspaceRepository",
        lambda _: SimpleNamespace(
            get_for_user=AsyncMock(return_value=SimpleNamespace(role="viewer"))
        ),
    )
    with pytest.raises(HTTPException) as failure:
        await ingestion.require_ingestion_access(request(), uuid4(), write=True)
    assert failure.value.status_code == 403


async def test_upload_persists_a_draft_and_original_bytes(monkeypatch):
    patch_database(monkeypatch)
    saved = record()
    saved.asset.status = "uploaded"
    create = AsyncMock(return_value=saved)
    put = AsyncMock()
    monkeypatch.setattr(ingestion, "require_ingestion_access", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(ingestion, "IngestionRepository", lambda _: SimpleNamespace(create=create))
    monkeypatch.setattr(
        ingestion, "KnowledgeSourceStorage", lambda _: SimpleNamespace(bucket="sources", put=put)
    )
    response = await ingestion.ingest_source(
        saved.entry.workspace_id,
        request(),
        UploadFile(file=BytesIO(b"original bytes"), filename="source.txt"),
        "Source knowledge",
        ["product_knowledge"],
    )
    assert response.status == "draft"
    assert response.processing_status == "queued"
    assert response.skill_count == 0
    assert put.await_args.kwargs["stream"].getvalue() == b"original bytes"
    assert create.await_args.kwargs["size_bytes"] == len(b"original bytes")
    assert len(create.await_args.kwargs["sha256"]) == 64
    assert create.await_args.kwargs["pending"] is True
    assert create.await_args.kwargs["preview"].skills == ()


async def test_source_storage_failure_does_not_persist_a_job(monkeypatch):
    monkeypatch.setattr(ingestion, "require_ingestion_access", AsyncMock(return_value=uuid4()))
    create = AsyncMock()
    monkeypatch.setattr(
        ingestion, "IngestionRepository", lambda _: SimpleNamespace(create=create)
    )
    monkeypatch.setattr(
        ingestion, "KnowledgeSourceStorage",
        lambda _: SimpleNamespace(put=AsyncMock(side_effect=RuntimeError("storage unavailable"))),
    )
    with pytest.raises(HTTPException) as failure:
        await ingestion.ingest_source(
            uuid4(),
            request(),
            UploadFile(file=BytesIO(b"bytes"), filename="source.txt"),
            "Knowledge",
            ["product_knowledge"],
        )
    assert failure.value.status_code == 503
    create.assert_not_awaited()


async def test_foreign_workspace_source_cannot_be_reviewed(monkeypatch):
    patch_database(monkeypatch)
    monkeypatch.setattr(ingestion, "require_ingestion_access", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(
        ingestion,
        "IngestionRepository",
        lambda _: SimpleNamespace(get=AsyncMock(return_value=None)),
    )
    with pytest.raises(HTTPException) as failure:
        await ingestion.get_ingestion(uuid4(), uuid4(), request())
    assert failure.value.status_code == 404


@pytest.mark.parametrize("empty", [True, False])
async def test_approval_requires_generated_content(monkeypatch, empty):
    patch_database(monkeypatch)
    saved = record()
    if empty:
        saved.entry.preview["application_knowledge"] = []
    approve = AsyncMock()
    monkeypatch.setattr(ingestion, "require_ingestion_access", AsyncMock(return_value=uuid4()))
    get = AsyncMock(return_value=saved)
    monkeypatch.setattr(
        ingestion,
        "IngestionRepository",
        lambda _: SimpleNamespace(get=get, approve=approve),
    )
    if empty:
        with pytest.raises(HTTPException) as failure:
            await ingestion.approve_ingestion(saved.entry.workspace_id, saved.entry.id, request())
        assert failure.value.status_code == 409
        approve.assert_not_awaited()
    else:
        await ingestion.approve_ingestion(saved.entry.workspace_id, saved.entry.id, request())
        approve.assert_awaited_once()
    get.assert_awaited_once_with(saved.entry.workspace_id, saved.entry.id, lock=True)


async def test_failed_database_write_keeps_original_error_when_cleanup_fails(monkeypatch):
    patch_database(monkeypatch)
    monkeypatch.setattr(ingestion, "require_ingestion_access", AsyncMock(return_value=uuid4()))
    delete = AsyncMock(side_effect=RuntimeError("storage cleanup failure"))
    monkeypatch.setattr(
        ingestion,
        "KnowledgeSourceStorage",
        lambda _: SimpleNamespace(bucket="sources", put=AsyncMock(), delete=delete),
    )
    monkeypatch.setattr(
        ingestion,
        "IngestionRepository",
        lambda _: SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("database failure"))),
    )
    with pytest.raises(RuntimeError, match="database failure"):
        await ingestion.ingest_source(
            uuid4(),
            request(),
            UploadFile(file=BytesIO(b"bytes"), filename="source.txt"),
            "Knowledge",
            ["product_knowledge"],
        )
    delete.assert_awaited_once()


@pytest.mark.parametrize("status", ["draft", "approved"])
async def test_delete_archives_draft_and_approved_sets(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    patch_database(monkeypatch)
    saved = record(status)
    access = AsyncMock(return_value=uuid4())
    get = AsyncMock(return_value=saved)
    archive = AsyncMock()
    monkeypatch.setattr(ingestion, "require_ingestion_access", access)
    monkeypatch.setattr(
        ingestion, "IngestionRepository", lambda _: SimpleNamespace(get=get, archive=archive)
    )
    http_request = request()
    response = await ingestion.delete_ingestion(
        saved.entry.workspace_id, saved.entry.id, http_request
    )
    assert response.status_code == 204
    access.assert_awaited_once_with(http_request, saved.entry.workspace_id, write=True)
    get.assert_awaited_once_with(saved.entry.workspace_id, saved.entry.id, lock=True)
    archive.assert_awaited_once_with(saved)


async def test_delete_missing_or_foreign_workspace_set_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_database(monkeypatch)
    monkeypatch.setattr(ingestion, "require_ingestion_access", AsyncMock(return_value=uuid4()))
    archive = AsyncMock()
    monkeypatch.setattr(
        ingestion,
        "IngestionRepository",
        lambda _: SimpleNamespace(get=AsyncMock(return_value=None), archive=archive),
    )
    with pytest.raises(HTTPException) as failure:
        await ingestion.delete_ingestion(uuid4(), uuid4(), request())
    assert failure.value.status_code == 404
    archive.assert_not_awaited()


async def test_rename_updates_the_name_without_changing_source(monkeypatch: pytest.MonkeyPatch):
    patch_database(monkeypatch)
    saved = record()
    monkeypatch.setattr(ingestion, "require_ingestion_access", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(
        ingestion, "IngestionRepository",
        lambda _: SimpleNamespace(get=AsyncMock(return_value=saved)),
    )
    response = await ingestion.rename_ingestion(
        saved.entry.workspace_id, saved.entry.id,
        ingestion.RenameKnowledgeRequest(name="  Reusable context  "), request(),
    )
    assert response.name == "Reusable context"
    assert response.source_name == "source.txt"


@pytest.mark.parametrize("status", ["draft", "approved"])
async def test_attach_requires_approval_and_workspace_applications(
    monkeypatch: pytest.MonkeyPatch, status: str,
):
    session = patch_database(monkeypatch)
    saved, application_id = record(status), uuid4()
    saved.asset.status = "included" if status == "approved" else "needs_user_review"
    session.scalars.return_value = SimpleNamespace(all=lambda: [application_id])
    monkeypatch.setattr(ingestion, "require_ingestion_access", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(
        ingestion, "IngestionRepository",
        lambda _: SimpleNamespace(get=AsyncMock(return_value=saved)),
    )
    if status == "draft":
        with pytest.raises(HTTPException) as failure:
            await ingestion.attach_ingestion(
                saved.entry.workspace_id, saved.entry.id,
                ingestion.AttachKnowledgeRequest(application_ids=[application_id]), request(),
            )
        assert failure.value.status_code == 409
    else:
        result = await ingestion.attach_ingestion(
            saved.entry.workspace_id, saved.entry.id,
            ingestion.AttachKnowledgeRequest(application_ids=[application_id]), request(),
        )
        assert result.application_ids == [application_id]
        session.scalars.return_value = SimpleNamespace(all=lambda: [])
        with pytest.raises(HTTPException) as failure:
            await ingestion.attach_ingestion(
                saved.entry.workspace_id, saved.entry.id,
                ingestion.AttachKnowledgeRequest(application_ids=[uuid4()]), request(),
            )
        assert failure.value.status_code == 404


async def test_processing_content_cannot_be_approved(monkeypatch: pytest.MonkeyPatch):
    patch_database(monkeypatch)
    saved = record()
    saved.asset.status = "processing"
    monkeypatch.setattr(ingestion, "require_ingestion_access", AsyncMock(return_value=uuid4()))
    approve = AsyncMock()
    monkeypatch.setattr(
        ingestion, "IngestionRepository",
        lambda _: SimpleNamespace(get=AsyncMock(return_value=saved), approve=approve),
    )
    with pytest.raises(HTTPException) as failure:
        await ingestion.approve_ingestion(saved.entry.workspace_id, saved.entry.id, request())
    assert failure.value.status_code == 409
    approve.assert_not_awaited()
