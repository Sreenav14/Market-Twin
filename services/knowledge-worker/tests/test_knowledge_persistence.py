"""Persist one real extraction as draft, grounded Skill versions."""

import os
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from markettwin_database import Base
from markettwin_database.models import (
    AssetVersion,
    BlueprintVersion,
    EvidenceUnit,
    ProductBlueprint,
    Skill,
    SkillEvidenceReference,
    SkillVersion,
    SourceAsset,
    User,
    Workspace,
)
from markettwin_knowledge_worker.extraction import PdfExtractor
from markettwin_knowledge_worker.persistence import EvidenceRepository, SkillRepository
from markettwin_knowledge_worker.services import KnowledgeIngestionService
from markettwin_knowledge_worker.skill_generator import SkillGenerator
from markettwin_shared.knowledge import GeneratedSkillDraft
from sqlalchemy import Table, func, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema

from .conftest import write_pdf


@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_DATABASE") != "1",
    reason="Set MARKETTWIN_TEST_DATABASE=1 to verify PostgreSQL persistence.",
)
async def test_real_source_persists_grounded_drafts(tmp_path: Path) -> None:
    database_url = os.environ["DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql+asyncpg://"
    )
    engine = create_async_engine(database_url, connect_args={"timeout": 5})
    suffix = uuid4().hex
    schemas = {
        "core": f"ingest_test_core_{suffix}",
        "knowledge": f"ingest_test_knowledge_{suffix}",
    }
    tables = tuple(
        cast(Table, model.__table__)
        for model in (
            User,
            Workspace,
            ProductBlueprint,
            BlueprintVersion,
            SourceAsset,
            AssetVersion,
            EvidenceUnit,
            Skill,
            SkillVersion,
            SkillEvidenceReference,
        )
    )
    try:
        async with engine.connect() as raw_connection:
            transaction = await raw_connection.begin()
            try:
                for schema in schemas.values():
                    await raw_connection.execute(CreateSchema(schema))
                connection = await raw_connection.execution_options(schema_translate_map=schemas)
                await connection.run_sync(
                    lambda sync: Base.metadata.create_all(sync, tables=list(tables))
                )
                ids = {
                    name: uuid4()
                    for name in ("user", "workspace", "blueprint", "version", "source", "asset")
                }
                await _seed_boundary(connection, ids)

                source = tmp_path / "requirements.pdf"
                write_pdf(source, ("Users can upload PDF resumes up to 10 MB.",))
                extraction = PdfExtractor().extract(source)
                draft = GeneratedSkillDraft.model_validate(
                    {
                        "name": "Upload Resume",
                        "definition": {
                            "intent": "Upload a resume",
                            "constraints": ["Maximum size is 10 MB"],
                            "expected_outcomes": ["Resume is accepted"],
                        },
                        "evidence_ordinals": [1],
                        "grounding_confidence": "high",
                    }
                )
                generator = AsyncMock(spec=SkillGenerator)
                generator.generate.return_value = (draft,)
                factory = async_sessionmaker(connection, expire_on_commit=False)
                async with factory() as session:
                    service = KnowledgeIngestionService(
                        skill_generator=generator,
                        evidence_repository=EvidenceRepository(session),
                        skill_repository=SkillRepository(session),
                    )
                    result = await service.ingest(
                        workspace_id=ids["workspace"],
                        blueprint_id=ids["blueprint"],
                        blueprint_version_id=ids["version"],
                        asset_version_id=ids["asset"],
                        created_by_user_id=ids["user"],
                        extraction=extraction,
                    )
                    assert len(result.evidence_unit_ids) == 1
                    assert len(result.skill_version_ids) == 1
                    assert await session.scalar(select(func.count()).select_from(EvidenceUnit)) == 1
                    assert await session.scalar(select(SkillVersion.status)) == "draft"
                    assert (
                        await session.scalar(
                            select(func.count()).select_from(SkillEvidenceReference)
                        )
                        == 1
                    )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _seed_boundary(connection: AsyncConnection, ids: dict[str, UUID]) -> None:
    await connection.execute(
        insert(User).values(
            id=ids["user"],
            email="ingestion@example.invalid",
            normalized_email="ingestion@example.invalid",
        )
    )
    await connection.execute(
        insert(Workspace).values(
            id=ids["workspace"], name="Ingestion test", created_by_user_id=ids["user"]
        )
    )
    await connection.execute(
        insert(ProductBlueprint).values(
            id=ids["blueprint"],
            workspace_id=ids["workspace"],
            created_by_user_id=ids["user"],
            name="Ingestion test",
        )
    )
    await connection.execute(
        insert(BlueprintVersion).values(
            id=ids["version"],
            workspace_id=ids["workspace"],
            blueprint_id=ids["blueprint"],
            version_number=1,
            created_by_user_id=ids["user"],
        )
    )
    await connection.execute(
        insert(SourceAsset).values(
            id=ids["source"],
            workspace_id=ids["workspace"],
            blueprint_id=ids["blueprint"],
            created_by_user_id=ids["user"],
            name="Requirements",
        )
    )
    await connection.execute(
        insert(AssetVersion).values(
            id=ids["asset"],
            workspace_id=ids["workspace"],
            blueprint_id=ids["blueprint"],
            source_asset_id=ids["source"],
            version_number=1,
            created_by_user_id=ids["user"],
            original_filename="requirements.pdf",
            storage_provider="s3",
            bucket="ingestion-test",
            object_key=str(ids["asset"]),
        )
    )
