"""Source identity and approval checks against local PostgreSQL, rolled back afterward."""

import os
from uuid import uuid4

import pytest
from markettwin_control_api.config import get_settings
from markettwin_control_api.knowledge.repository import IngestionRepository
from markettwin_database.models import User, Workspace
from markettwin_database.models.knowledge import (
    ApplicationKnowledgeEntry,
    AssetVersion,
    BlueprintVersion,
    IngestionEntry,
    ProductBlueprint,
)
from markettwin_database.models.testing import Application
from markettwin_shared.knowledge_preview import KnowledgePreviewResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_DATABASE") != "1", reason="Opt-in local PostgreSQL check."
)
async def test_saved_source_and_review_use_the_asset_boundary():
    engine = create_async_engine(get_settings().database_url, connect_args={"timeout": 5})
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            try:
                factory = async_sessionmaker(
                    connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
                )
                user_id, workspace_id, entry_id = uuid4(), uuid4(), uuid4()
                app_one, app_two, foreign_app, foreign_workspace = (uuid4() for _ in range(4))
                async with factory() as session:
                    email = f"knowledge-test-{user_id}@example.invalid"
                    session.add(User(id=user_id, email=email, normalized_email=email))
                    await session.flush()
                    session.add(
                        Workspace(
                            id=workspace_id, name="Ingestion test", created_by_user_id=user_id
                        )
                    )
                    await session.flush()
                    preview = KnowledgePreviewResponse.model_validate(
                        {
                            "source": {
                                "name": "requirements.txt",
                                "source_item_count": 1,
                                "processed_item_count": 1,
                            },
                            "application_knowledge": [
                                {
                                    "name": "Documented behavior",
                                    "content": "Source context.",
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
                    repository = IngestionRepository(session)
                    record = await repository.create(
                        entry_id=entry_id,
                        workspace_id=workspace_id,
                        user_id=user_id,
                        name="Requirements",
                        roles=["product_knowledge"],
                        preview=preview,
                        bucket="test",
                        object_key=f"test/{entry_id}",
                        size_bytes=14,
                        sha256="a" * 64,
                        content_type="text/plain",
                    )
                    assert record.version.status == "draft"
                    assert record.pin.asset_version_id == record.asset.id
                    assert record.entry.asset_version_id == record.asset.id
                    assert await repository.get(uuid4(), entry_id) is None
                    await repository.approve(record, user_id)
                    session.add(Workspace(
                        id=foreign_workspace, name="Other workspace", created_by_user_id=user_id,
                    ))
                    await session.flush()
                    session.add_all([
                        Application(
                            id=app_one, workspace_id=workspace_id, name="First application",
                            created_by_user_id=user_id,
                        ),
                        Application(
                            id=app_two, workspace_id=workspace_id, name="Second application",
                            created_by_user_id=user_id,
                        ),
                        Application(
                            id=foreign_app, workspace_id=foreign_workspace,
                            name="Foreign application",
                            created_by_user_id=user_id,
                        ),
                    ])
                    await session.flush()
                    record.entry.application_links = [ApplicationKnowledgeEntry(
                        workspace_id=workspace_id, application_id=app_id,
                        ingestion_entry_id=entry_id,
                        attached_by_user_id=user_id,
                    ) for app_id in (app_one, app_two)]
                    await session.flush()
                    with pytest.raises(IntegrityError):
                        async with session.begin_nested():
                            session.add(ApplicationKnowledgeEntry(
                                workspace_id=workspace_id, application_id=foreign_app,
                                ingestion_entry_id=entry_id, attached_by_user_id=user_id,
                            ))
                            await session.flush()
                    await session.commit()
                async with factory() as session:
                    record = await IngestionRepository(session).get(workspace_id, entry_id)
                    assert record is not None
                    assert record.version.status == "approved"
                    assert record.version.approved_by_user_id == user_id
                    assert record.pin.roles_confirmed_by_user_id == user_id
                    assert record.asset.status == "included"
                    assert (
                        record.entry.preview["application_knowledge"]
                        == preview.model_dump(mode="json")["application_knowledge"]
                    )
                    repository = IngestionRepository(session)
                    assert await repository.get(workspace_id, entry_id, application_id=app_one)
                    assert await repository.get(
                        workspace_id, entry_id, application_id=foreign_app
                    ) is None
                    assert len(await repository.list_for_application(workspace_id, app_two)) == 1
                    record.entry.application_links = [
                        link for link in record.entry.application_links
                        if link.application_id == app_two
                    ]
                    await session.flush()
                    assert await repository.get(
                        workspace_id, entry_id, application_id=app_one
                    ) is None
                    assert await repository.get(workspace_id, entry_id, application_id=app_two)
                    await repository.archive(record)
                    await session.commit()
                async with factory() as session:
                    repository = IngestionRepository(session)
                    assert await repository.get(workspace_id, entry_id) is None
                    assert await repository.list_entries(workspace_id) == []
                    assert await repository.list_for_application(workspace_id, app_two) == []
                    blueprint = await session.get(ProductBlueprint, record.blueprint.id)
                    version = await session.get(BlueprintVersion, entry_id)
                    asset = await session.get(AssetVersion, record.asset.id)
                    retained_entry = await session.get(IngestionEntry, entry_id)
                    assert blueprint is not None and blueprint.status == "archived"
                    assert version is not None and version.status == "approved"
                    assert asset is not None and asset.object_key == f"test/{entry_id}"
                    assert retained_entry is not None
                    assert retained_entry.preview == record.entry.preview
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()
