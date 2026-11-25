"""Persist source-backed knowledge sets using the existing asset boundary."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from markettwin_database.models.knowledge import (
    ApplicationKnowledgeEntry,
    AssetVersion,
    BlueprintVersion,
    BlueprintVersionAsset,
    IngestionEntry,
    KnowledgeFile,
    ProductBlueprint,
    SourceAsset,
)
from markettwin_shared.knowledge_preview import KnowledgePreviewResponse
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class IngestionRecord:
    entry: IngestionEntry
    version: BlueprintVersion
    blueprint: ProductBlueprint
    asset: AssetVersion
    pin: BlueprintVersionAsset


@dataclass(frozen=True)
class KnowledgeFileInput:
    """One rendered file to index, as produced by the processor (doc 33 §3.4)."""

    slug: str
    title: str
    description: str
    object_key: str
    sha256: str
    token_count: int


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

    async def current_knowledge_file_version(self, entry_id: UUID) -> int:
        """Highest knowledge-file version written for the entry (0 = none)."""
        value = await self.session.scalar(
            select(func.max(KnowledgeFile.version)).where(
                KnowledgeFile.ingestion_entry_id == entry_id
            )
        )
        return int(value or 0)

    async def record_knowledge_files(
        self,
        record: IngestionRecord,
        *,
        version: int,
        files: Sequence[KnowledgeFileInput],
    ) -> None:
        """Index one processing pass's files at ``version`` (doc 33 §3.4).

        The previous version's unapproved rows are superseded in the same
        transaction; approved rows are never touched by a reprocess.
        """
        await self.session.execute(
            update(KnowledgeFile)
            .where(
                KnowledgeFile.ingestion_entry_id == record.entry.id,
                KnowledgeFile.version < version,
                KnowledgeFile.status == "generated",
            )
            .values(status="superseded")
        )
        self.session.add_all(
            [
                KnowledgeFile(
                    id=uuid4(),
                    workspace_id=record.entry.workspace_id,
                    ingestion_entry_id=record.entry.id,
                    slug=file.slug,
                    title=file.title,
                    description=file.description,
                    object_key=file.object_key,
                    sha256=file.sha256,
                    token_count=file.token_count,
                    version=version,
                    status="generated",
                )
                for file in files
            ]
        )
        await self.session.flush()

    async def list_knowledge_files(self, entry_id: UUID) -> list[KnowledgeFile]:
        """The entry's current-version files, superseded rows excluded."""
        version = await self.current_knowledge_file_version(entry_id)
        if not version:
            return []
        result = await self.session.execute(
            select(KnowledgeFile)
            .where(
                KnowledgeFile.ingestion_entry_id == entry_id,
                KnowledgeFile.version == version,
                KnowledgeFile.status != "superseded",
            )
            .order_by(KnowledgeFile.slug)
        )
        return list(result.scalars().all())

    async def get_knowledge_file(
        self, entry_id: UUID, slug: str
    ) -> KnowledgeFile | None:
        for file in await self.list_knowledge_files(entry_id):
            if file.slug == slug:
                return file
        return None

    async def knowledge_file_counts(
        self, entry_ids: Sequence[UUID]
    ) -> dict[UUID, int]:
        """Current-version file count per entry, for list summaries."""
        if not entry_ids:
            return {}
        latest = (
            select(
                KnowledgeFile.ingestion_entry_id.label("entry_id"),
                func.max(KnowledgeFile.version).label("version"),
            )
            .where(KnowledgeFile.ingestion_entry_id.in_(entry_ids))
            .group_by(KnowledgeFile.ingestion_entry_id)
            .subquery()
        )
        result = await self.session.execute(
            select(KnowledgeFile.ingestion_entry_id, func.count())
            .join(
                latest,
                and_(
                    KnowledgeFile.ingestion_entry_id == latest.c.entry_id,
                    KnowledgeFile.version == latest.c.version,
                ),
            )
            .where(KnowledgeFile.status != "superseded")
            .group_by(KnowledgeFile.ingestion_entry_id)
        )
        return {entry_id: count for entry_id, count in result.all()}

    async def update_knowledge_file(
        self,
        file: KnowledgeFile,
        *,
        title: str | None = None,
        description: str | None = None,
    ) -> None:
        if title is not None:
            file.title = title
        if description is not None:
            file.description = description
        await self.session.flush()

    async def approve(self, record: IngestionRecord, user_id: UUID) -> None:
        validate_approval(record)
        now = datetime.now(UTC)
        record.version.status = "approved"
        record.version.approved_by_user_id = user_id
        record.version.approved_at = now
        record.pin.roles_confirmed_by_user_id = user_id
        record.pin.roles_confirmed_at = now
        record.asset.status = "included"
        file_version = await self.current_knowledge_file_version(record.entry.id)
        if file_version:
            await self.session.execute(
                update(KnowledgeFile)
                .where(
                    KnowledgeFile.ingestion_entry_id == record.entry.id,
                    KnowledgeFile.version == file_version,
                    KnowledgeFile.status == "generated",
                )
                .values(status="approved")
            )
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


def validate_approval(record: IngestionRecord) -> None:
    if (record.version.status != "draft" or record.asset.status != "needs_user_review"
            or record.asset.processed_at is None):
        raise ValueError("Knowledge must be ready for review before approval.")
    preview = KnowledgePreviewResponse.model_validate(record.entry.preview)
    if not (preview.application_knowledge or preview.artifacts or preview.skills):
        raise ValueError("There is no generated knowledge to approve.")
