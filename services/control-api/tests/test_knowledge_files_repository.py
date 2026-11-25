"""Doc 33 step 2: knowledge_files repository behaviour on real rows.

Runs the real IngestionRepository against the real KnowledgeFile table
(SQLite in-memory with the `knowledge` schema attached; only the S3
boundary is absent — these methods never touch it).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from markettwin_control_api.knowledge.repository import (
    IngestionRecord,
    IngestionRepository,
    KnowledgeFileInput,
)
from markettwin_database.models.knowledge import (
    AssetVersion,
    BlueprintVersion,
    BlueprintVersionAsset,
    IngestionEntry,
    KnowledgeFile,
    ProductBlueprint,
)
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool


@asynccontextmanager
async def _repository() -> AsyncIterator[tuple[IngestionRepository, AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _attach(dbapi_connection, _record):  # noqa: ANN001, ANN202
        dbapi_connection.execute("ATTACH DATABASE ':memory:' AS knowledge")

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: KnowledgeFile.__table__.create(sync_connection)
        )
    async with AsyncSession(engine) as session:
        yield IngestionRepository(session), session
    await engine.dispose()


def _record(entry_id, workspace_id) -> IngestionRecord:  # noqa: ANN001, ANN202
    blueprint_id, asset_id = uuid4(), uuid4()
    preview = {
        "source": {"name": "guide.md", "source_item_count": 1, "processed_item_count": 1},
        "application_knowledge": [
            {
                "name": "Context", "content": "Source facts", "evidence_ordinals": [1],
                "grounding_confidence": "high", "warnings": [],
            }
        ],
        "artifacts": [], "skills": [], "evidence": [], "extraction_issues": [],
    }
    return IngestionRecord(
        IngestionEntry(
            id=entry_id, workspace_id=workspace_id, blueprint_id=blueprint_id,
            asset_version_id=asset_id, preview=preview,
        ),
        BlueprintVersion(
            id=entry_id, workspace_id=workspace_id, blueprint_id=blueprint_id,
            status="draft", created_at=datetime.now(UTC),
        ),
        ProductBlueprint(id=blueprint_id, name="Guide"),
        AssetVersion(
            id=asset_id, original_filename="guide.md", bucket="sources",
            object_key="source", status="needs_user_review",
            processed_at=datetime.now(UTC),
        ),
        BlueprintVersionAsset(roles=["product_knowledge"]),
    )


def _file(slug: str) -> KnowledgeFileInput:
    return KnowledgeFileInput(
        slug=slug, title=slug.title(), description=f"About {slug}.",
        object_key=f"knowledge/files/{slug}.md", sha256="a" * 64, token_count=42,
    )


async def test_record_list_get_and_counts() -> None:
    entry_id, workspace_id = uuid4(), uuid4()
    async with _repository() as (repository, _session):
        record = _record(entry_id, workspace_id)
        assert await repository.current_knowledge_file_version(entry_id) == 0
        await repository.record_knowledge_files(
            record, version=1, files=[_file("pricing"), _file("refunds")],
        )
        assert await repository.current_knowledge_file_version(entry_id) == 1
        files = await repository.list_knowledge_files(entry_id)
        assert [file.slug for file in files] == ["pricing", "refunds"]
        assert all(file.status == "generated" and file.version == 1 for file in files)
        found = await repository.get_knowledge_file(entry_id, "refunds")
        assert found is not None and found.title == "Refunds"
        assert await repository.get_knowledge_file(entry_id, "missing") is None
        assert await repository.knowledge_file_counts([entry_id]) == {entry_id: 2}


async def test_second_version_supersedes_the_first() -> None:
    entry_id, workspace_id = uuid4(), uuid4()
    async with _repository() as (repository, session):
        record = _record(entry_id, workspace_id)
        await repository.record_knowledge_files(
            record, version=1, files=[_file("pricing"), _file("refunds")],
        )
        await repository.record_knowledge_files(record, version=2, files=[_file("pricing")])
        rows = list((await session.execute(select(KnowledgeFile))).scalars().all())
        by_version = {(row.version, row.slug): row.status for row in rows}
        assert by_version == {
            (1, "pricing"): "superseded",
            (1, "refunds"): "superseded",
            (2, "pricing"): "generated",
        }
        assert [f.slug for f in await repository.list_knowledge_files(entry_id)] == ["pricing"]
        assert await repository.knowledge_file_counts([entry_id]) == {entry_id: 1}


async def test_approve_flips_current_version_files() -> None:
    entry_id, workspace_id = uuid4(), uuid4()
    async with _repository() as (repository, _session):
        record = _record(entry_id, workspace_id)
        await repository.record_knowledge_files(record, version=1, files=[_file("pricing")])
        await repository.record_knowledge_files(record, version=2, files=[_file("pricing")])
        await repository.approve(record, uuid4())
        files = await repository.list_knowledge_files(entry_id)
        assert [file.status for file in files] == ["approved"]
        assert record.version.status == "approved"


async def test_update_knowledge_file_metadata() -> None:
    entry_id, workspace_id = uuid4(), uuid4()
    async with _repository() as (repository, _session):
        record = _record(entry_id, workspace_id)
        await repository.record_knowledge_files(record, version=1, files=[_file("pricing")])
        row = await repository.get_knowledge_file(entry_id, "pricing")
        assert row is not None
        await repository.update_knowledge_file(row, title="Plans and pricing")
        assert row.title == "Plans and pricing"
        assert row.description == "About pricing."
