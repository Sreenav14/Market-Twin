"""Source Asset boundary checks; PostgreSQL tests use rolled-back isolated schemas."""

import os
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from markettwin_control_api.config import get_settings
from markettwin_database import Base
from markettwin_database.models import (
    AssetVersion,
    BlueprintVersion,
    BlueprintVersionAsset,
    ProductBlueprint,
    SourceAsset,
    User,
    Workspace,
)
from sqlalchemy import Table, delete, insert, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateSchema, CreateTable
from sqlalchemy.sql import Executable

KNOWLEDGE_TABLES = tuple(
    cast(Table, model.__table__)
    for model in (
        ProductBlueprint,
        BlueprintVersion,
        SourceAsset,
        AssetVersion,
        BlueprintVersionAsset,
    )
)


def test_knowledge_models_register_and_compile() -> None:
    """Importing the public registry must resolve every composite FK and PG type."""
    configure_mappers()
    for table in KNOWLEDGE_TABLES:
        assert table in Base.metadata.sorted_tables
        assert str(CreateTable(table).compile(dialect=postgresql.dialect()))


async def assert_rejected(
    connection: AsyncConnection, statement: Executable, constraint: str
) -> None:
    """Keep exercising the boundary after each expected constraint violation."""
    with pytest.raises(IntegrityError, match=constraint):
        async with connection.begin_nested():
            await connection.execute(statement)


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_DATABASE") != "1",
    reason="Set MARKETTWIN_TEST_DATABASE=1 to verify PostgreSQL constraints.",
)
async def test_source_asset_boundary_in_postgresql() -> None:
    """Check historical pins, tenant isolation, validation and deletion semantics."""
    engine = create_async_engine(get_settings().database_url, connect_args={"timeout": 5})
    suffix = uuid4().hex
    schemas = {"core": f"asset_test_core_{suffix}", "knowledge": f"asset_test_knowledge_{suffix}"}
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            try:
                for schema in schemas.values():
                    await connection.execute(CreateSchema(schema))
                connection = await connection.execution_options(schema_translate_map=schemas)
                await connection.run_sync(
                    lambda sync: Base.metadata.create_all(
                        sync,
                        tables=[
                            cast(Table, User.__table__),
                            cast(Table, Workspace.__table__),
                            *KNOWLEDGE_TABLES,
                        ],
                    )
                )
                user, workspace, other_workspace = (uuid4() for _ in range(3))
                blueprint, other_blueprint = uuid4(), uuid4()
                version1, version2, other_version = (uuid4() for _ in range(3))
                source, other_source = uuid4(), uuid4()
                asset1, asset2, other_asset = (uuid4() for _ in range(3))
                await connection.execute(
                    insert(User).values(
                        id=user,
                        email="asset-test@example.invalid",
                        normalized_email="asset-test@example.invalid",
                    )
                )
                for workspace_id in (workspace, other_workspace):
                    await connection.execute(
                        insert(Workspace).values(
                            id=workspace_id,
                            name="Asset boundary test",
                            created_by_user_id=user,
                        )
                    )
                for blueprint_id in (blueprint, other_blueprint):
                    await connection.execute(
                        insert(ProductBlueprint).values(
                            id=blueprint_id,
                            workspace_id=workspace,
                            created_by_user_id=user,
                            name=str(blueprint_id),
                        )
                    )
                for version_id, blueprint_id, number in (
                    (version1, blueprint, 1),
                    (version2, blueprint, 2),
                    (other_version, other_blueprint, 1),
                ):
                    await connection.execute(
                        insert(BlueprintVersion).values(
                            id=version_id,
                            workspace_id=workspace,
                            blueprint_id=blueprint_id,
                            version_number=number,
                            created_by_user_id=user,
                        )
                    )
                for source_id, blueprint_id in (
                    (source, blueprint),
                    (other_source, other_blueprint),
                ):
                    await connection.execute(
                        insert(SourceAsset).values(
                            id=source_id,
                            workspace_id=workspace,
                            blueprint_id=blueprint_id,
                            created_by_user_id=user,
                            name="Requirements",
                        )
                    )
                asset_values: dict[str, object] = {
                    "workspace_id": workspace,
                    "blueprint_id": blueprint,
                    "source_asset_id": source,
                    "version_number": 3,
                    "created_by_user_id": user,
                    "original_filename": "requirements.pdf",
                    "storage_provider": "s3",
                    "bucket": "asset-test",
                    "object_key": "revision3.pdf",
                    "sha256": "a" * 64,
                    "declared_content_type": "application/pdf",
                    "detected_content_type": "application/octet-stream",
                }
                for asset_id, source_id, blueprint_id, number in (
                    (asset1, source, blueprint, 1),
                    (asset2, source, blueprint, 2),
                    (other_asset, other_source, other_blueprint, 1),
                ):
                    await connection.execute(
                        insert(AssetVersion).values(
                            {
                                **asset_values,
                                "id": asset_id,
                                "source_asset_id": source_id,
                                "blueprint_id": blueprint_id,
                                "version_number": number,
                                "object_key": str(asset_id),
                            }
                        )
                    )
                assert (
                    await connection.scalar(
                        select(AssetVersion.status).where(AssetVersion.id == asset1)
                    )
                    == "created"
                )
                pin_values: dict[str, object] = {
                    "workspace_id": workspace,
                    "blueprint_id": blueprint,
                    "blueprint_version_id": version1,
                    "source_asset_id": source,
                    "asset_version_id": asset1,
                    "roles": ["product_knowledge", "business_rules"],
                }
                await connection.execute(insert(BlueprintVersionAsset).values(pin_values))
                assert await connection.scalar(select(BlueprintVersionAsset.is_required)) is True
                await connection.execute(
                    insert(BlueprintVersionAsset).values(
                        {
                            **pin_values,
                            "blueprint_version_id": version2,
                            "asset_version_id": asset2,
                            "is_required": False,
                            "roles_confirmed_by_user_id": user,
                            "roles_confirmed_at": datetime.now(UTC),
                        }
                    )
                )
                pins = (
                    await connection.execute(
                        select(
                            BlueprintVersionAsset.blueprint_version_id,
                            BlueprintVersionAsset.asset_version_id,
                        )
                    )
                ).all()
                assert set(pins) == {(version1, asset1), (version2, asset2)}
                assert (
                    await connection.scalar(
                        select(BlueprintVersionAsset.is_required).where(
                            BlueprintVersionAsset.blueprint_version_id == version2,
                        )
                    )
                    is False
                )
                assert (
                    await connection.execute(
                        select(
                            AssetVersion.sha256,
                            AssetVersion.declared_content_type,
                            AssetVersion.detected_content_type,
                        ).where(AssetVersion.id.in_([asset1, asset2]))
                    )
                ).all() == [
                    ("a" * 64, "application/pdf", "application/octet-stream"),
                    ("a" * 64, "application/pdf", "application/octet-stream"),
                ]

                # Use an unpinned version so FK checks cannot be masked by pin uniqueness.
                unpinned_version = uuid4()
                await connection.execute(
                    insert(BlueprintVersion).values(
                        id=unpinned_version,
                        workspace_id=workspace,
                        blueprint_id=blueprint,
                        version_number=3,
                        created_by_user_id=user,
                    )
                )
                pin_values["blueprint_version_id"] = unpinned_version

                await assert_rejected(
                    connection,
                    insert(SourceAsset).values(
                        workspace_id=other_workspace,
                        blueprint_id=blueprint,
                        created_by_user_id=user,
                        name="Wrong workspace",
                    ),
                    "fk_source_assets_workspace_id_product_blueprints",
                )
                for changes in (
                    {"workspace_id": other_workspace},
                    {"blueprint_id": other_blueprint},
                    {"source_asset_id": other_source},
                ):
                    await assert_rejected(
                        connection,
                        insert(AssetVersion).values(
                            {
                                **asset_values,
                                **changes,
                            }
                        ),
                        "fk_asset_versions_workspace_id_source_assets",
                    )
                for changes in (
                    {"workspace_id": other_workspace},
                    {"blueprint_version_id": other_version},
                ):
                    await assert_rejected(
                        connection,
                        insert(BlueprintVersionAsset).values(
                            {
                                **pin_values,
                                **changes,
                            }
                        ),
                        "fk_blueprint_version_assets_workspace_id_blueprint_versions",
                    )
                for changes in (
                    {"source_asset_id": other_source},
                    {"asset_version_id": other_asset},
                ):
                    await assert_rejected(
                        connection,
                        insert(BlueprintVersionAsset).values(
                            {
                                **pin_values,
                                **changes,
                            }
                        ),
                        "fk_blueprint_version_assets_workspace_id_asset_versions",
                    )
                await assert_rejected(
                    connection,
                    insert(BlueprintVersionAsset).values(
                        {
                            **pin_values,
                            "asset_version_id": asset2,
                            "blueprint_version_id": version1,
                        }
                    ),
                    "uq_blueprint_version_assets_source",
                )
                for roles, constraint in (
                    ([], "ck_blueprint_version_assets_roles_nonempty"),
                    (["unknown"], "ck_blueprint_version_assets_roles_allowed"),
                    ([None], "ck_blueprint_version_assets_roles_allowed"),
                ):
                    await assert_rejected(
                        connection,
                        insert(BlueprintVersionAsset).values(
                            {
                                **pin_values,
                                "roles": roles,
                            }
                        ),
                        constraint,
                    )
                for changes in (
                    {"roles_confirmed_by_user_id": user},
                    {"roles_confirmed_at": datetime.now(UTC)},
                ):
                    await assert_rejected(
                        connection,
                        insert(BlueprintVersionAsset).values(
                            {
                                **pin_values,
                                **changes,
                            }
                        ),
                        "ck_blueprint_version_assets_role_confirmation_consistent",
                    )
                for changes, constraint in (
                    ({"version_number": 0}, "ck_asset_versions_version_positive"),
                    ({"size_bytes": -1}, "ck_asset_versions_size_nonnegative"),
                    ({"storage_provider": "unknown"}, "ck_asset_versions_storage_provider_allowed"),
                    ({"status": "unknown"}, "ck_asset_versions_status_allowed"),
                    ({"version_number": 1}, "uq_asset_versions_asset_version"),
                    ({"object_key": str(asset1)}, "uq_asset_versions_storage_location"),
                ):
                    await assert_rejected(
                        connection,
                        insert(AssetVersion).values(
                            {
                                **asset_values,
                                **changes,
                            }
                        ),
                        constraint,
                    )
                await connection.execute(
                    insert(AssetVersion).values(
                        {
                            **asset_values,
                            "storage_provider": "minio",
                            "size_bytes": 2**40,
                            "status": "needs_ocr",
                        }
                    )
                )
                await assert_rejected(
                    connection,
                    delete(AssetVersion).where(
                        AssetVersion.id == asset1,
                    ),
                    "fk_blueprint_version_assets_workspace_id_asset_versions",
                )
                await connection.execute(
                    delete(BlueprintVersion).where(BlueprintVersion.id == version1)
                )
                assert (
                    await connection.scalar(
                        select(BlueprintVersionAsset.id).where(
                            BlueprintVersionAsset.blueprint_version_id == version1,
                        )
                    )
                    is None
                )
                await connection.execute(delete(AssetVersion).where(AssetVersion.id == asset1))
                await connection.execute(delete(SourceAsset).where(SourceAsset.id == other_source))
                assert (
                    await connection.scalar(
                        select(AssetVersion.id).where(
                            AssetVersion.id == other_asset,
                        )
                    )
                    is None
                )
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()
