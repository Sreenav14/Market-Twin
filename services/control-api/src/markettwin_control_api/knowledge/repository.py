"""Persist source-backed knowledge sets using the existing asset boundary."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from markettwin_database.models.knowledge import (
    ApplicationKnowledgeEntry,
    AssetVersion,
    BlueprintVersion,
    BlueprintVersionAsset,
    IngestionEntry,
    ProductBlueprint,
    SourceAsset,
)
from markettwin_shared.knowledge_preview import KnowledgePreviewResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class IngestionRecord:
    entry: IngestionEntry
    version: BlueprintVersion
    blueprint: ProductBlueprint
    asset: AssetVersion
    pin: BlueprintVersionAsset


class IngestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _statement(self, workspace_id: UUID):
        return (
            select(
                IngestionEntry,
                BlueprintVersion,
                ProductBlueprint,
                AssetVersion,
                BlueprintVersionAsset,
            )
            .join(BlueprintVersion, BlueprintVersion.id == IngestionEntry.id)
            .join(ProductBlueprint, ProductBlueprint.id == IngestionEntry.blueprint_id)
            .join(AssetVersion, AssetVersion.id == IngestionEntry.asset_version_id)
            .join(
                BlueprintVersionAsset,
                BlueprintVersionAsset.blueprint_version_id == IngestionEntry.id,
            )
            .where(
                IngestionEntry.workspace_id == workspace_id,
                ProductBlueprint.status == "active",
            )
        )

    async def list_entries(self, workspace_id: UUID) -> list[IngestionRecord]:
        result = await self.session.execute(
            self._statement(workspace_id).order_by(BlueprintVersion.created_at.desc())
        )
        return [IngestionRecord(*row) for row in result.all()]

    async def get(
        self, workspace_id: UUID, entry_id: UUID, *, lock: bool = False,
        application_id: UUID | None = None,
    ) -> IngestionRecord | None:
        statement = self._statement(workspace_id).where(IngestionEntry.id == entry_id)
        if application_id is not None:
            statement = statement.join(
                ApplicationKnowledgeEntry,
                ApplicationKnowledgeEntry.ingestion_entry_id == IngestionEntry.id,
            ).where(ApplicationKnowledgeEntry.application_id == application_id)
        if lock:
            statement = statement.with_for_update(
                of=(ProductBlueprint, BlueprintVersion, AssetVersion)
            )
        row = (await self.session.execute(statement)).one_or_none()
        return IngestionRecord(*row) if row is not None else None

    async def create(
        self,
        *,
        entry_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        name: str,
        roles: list[str],
        preview: KnowledgePreviewResponse,
        bucket: str,
        object_key: str,
        size_bytes: int,
        sha256: str,
        content_type: str | None,
        pending: bool = False,
    ) -> IngestionRecord:
        blueprint_id, source_id, asset_id = uuid4(), uuid4(), uuid4()
        now = datetime.now(UTC)
        blueprint = ProductBlueprint(
            id=blueprint_id,
            workspace_id=workspace_id,
            created_by_user_id=user_id,
            name=name,
            status="active",
        )
        self.session.add(blueprint)
        await self.session.flush()
        version = BlueprintVersion(
            id=entry_id,
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            version_number=1,
            status="draft",
            created_by_user_id=user_id,
        )
        source = SourceAsset(
            id=source_id,
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            created_by_user_id=user_id,
            name=preview.source.name,
            status="active",
        )
        self.session.add_all([version, source])
        await self.session.flush()
        asset = AssetVersion(
            id=asset_id,
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            source_asset_id=source_id,
            version_number=1,
            created_by_user_id=user_id,
            original_filename=preview.source.name,
            declared_content_type=content_type,
            storage_provider="s3",
            bucket=bucket,
            object_key=object_key,
            size_bytes=size_bytes,
            sha256=sha256,
            status="uploaded" if pending else "needs_user_review",
            uploaded_at=now,
            processed_at=None if pending else now,
        )
        self.session.add(asset)
        await self.session.flush()
        pin = BlueprintVersionAsset(
            id=uuid4(),
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            blueprint_version_id=entry_id,
            source_asset_id=source_id,
            asset_version_id=asset_id,
            roles=roles,
            is_required=True,
        )
        entry = IngestionEntry(
            id=entry_id,
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            asset_version_id=asset_id,
            preview=preview.model_dump(mode="json"),
            application_links=[],
        )
        self.session.add_all([pin, entry])
        await self.session.flush()
        await self.session.refresh(version)
        return IngestionRecord(entry, version, blueprint, asset, pin)

    async def approve(self, record: IngestionRecord, user_id: UUID) -> None:
        if record.version.status == "approved":
            return
        now = datetime.now(UTC)
        record.version.status = "approved"
        record.version.approved_by_user_id = user_id
        record.version.approved_at = now
        record.pin.roles_confirmed_by_user_id = user_id
        record.pin.roles_confirmed_at = now
        record.asset.status = "included"
        await self.session.flush()

    async def archive(self, record: IngestionRecord) -> None:
        """Remove a set from the active library while preserving its source and history."""
        record.blueprint.status = "archived"
        await self.session.flush()

    async def list_for_application(
        self, workspace_id: UUID, application_id: UUID
    ) -> list[IngestionRecord]:
        result = await self.session.execute(
            self._statement(workspace_id).join(
                ApplicationKnowledgeEntry,
                ApplicationKnowledgeEntry.ingestion_entry_id == IngestionEntry.id,
            ).where(ApplicationKnowledgeEntry.application_id == application_id)
            .order_by(BlueprintVersion.created_at.desc())
        )
        return [IngestionRecord(*row) for row in result.all()]
