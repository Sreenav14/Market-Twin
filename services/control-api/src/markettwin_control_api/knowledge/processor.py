"""Dispatch persisted ingestion to the existing private worker, independently of the UI."""

import asyncio
import logging
from datetime import UTC, datetime
from tempfile import TemporaryFile
from typing import BinaryIO, cast
from uuid import UUID

from markettwin_database.models.knowledge import AssetVersion, IngestionEntry, ProductBlueprint
from markettwin_shared.knowledge_preview import KnowledgePreviewResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from markettwin_control_api.config import Settings
from markettwin_control_api.knowledge.client import KnowledgeWorkerClient, KnowledgeWorkerError
from markettwin_control_api.knowledge.repository import IngestionRepository
from markettwin_control_api.knowledge.storage import KnowledgeSourceStorage

logger = logging.getLogger(__name__)
PENDING_STATUSES = ("uploaded", "processing")


class IngestionProcessor:
    def __init__(self, engine: AsyncEngine, settings: Settings) -> None:
        self.engine = engine
        self.settings = settings

    async def process_next(self) -> bool:
        async with AsyncSession(self.engine) as session:
            candidates = (await session.execute(
                select(IngestionEntry.workspace_id, IngestionEntry.id)
                .join(AssetVersion, AssetVersion.id == IngestionEntry.asset_version_id)
                .join(ProductBlueprint, ProductBlueprint.id == IngestionEntry.blueprint_id)
                .where(
                    ProductBlueprint.status == "active", AssetVersion.status.in_(PENDING_STATUSES)
                )
                .order_by(AssetVersion.created_at).limit(20)
            )).all()
        for workspace_id, entry_id in candidates:
            if await self.process_entry(workspace_id, entry_id):
                return True
        return False

    async def process_entry(self, workspace_id: UUID, entry_id: UUID) -> bool:
        # Pin a connection: session locks must never be left on a pooled connection.
        async with self.engine.connect() as connection:
            key = {"key": f"markettwin-ingestion:{entry_id}"}
            locked = await connection.scalar(text(
                "SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"
            ), key)
            await connection.commit()
            if not locked:
                return False
            try:
                await self._process(connection, workspace_id, entry_id)
                return True
            finally:
                try:
                    await connection.rollback()
                    await connection.execute(text(
                        "SELECT pg_advisory_unlock(hashtextextended(:key, 0))"
                    ), key)
                    await connection.commit()
                except BaseException:
                    # Discard the physical connection if shutdown/error prevents lock cleanup.
                    await connection.invalidate()
                    raise

    async def _process(
        self, connection: AsyncConnection, workspace_id: UUID, entry_id: UUID
    ) -> None:
        async with AsyncSession(connection, expire_on_commit=False) as session:
            async with session.begin():
                record = await IngestionRepository(session).get(workspace_id, entry_id, lock=True)
                if record is None or record.asset.status not in PENDING_STATUSES:
                    return
                record.asset.status = "processing"
                record.asset.status_message = None
                filename, bucket, key = (
                    record.asset.original_filename, record.asset.bucket, record.asset.object_key
                )
                content_type = record.asset.declared_content_type
        try:
            with TemporaryFile(prefix="markettwin-ingestion-") as temporary:
                stream = cast(BinaryIO, temporary)
                await KnowledgeSourceStorage(self.settings).download(
                    bucket=bucket, key=key, stream=stream
                )
                result = await KnowledgeWorkerClient(self.settings).preview(
                    filename=filename, content_type=content_type, stream=stream
                )
        except KnowledgeWorkerError as error:
            await self._save(connection, workspace_id, entry_id, error=error.message)
        except Exception:
            logger.exception("Ingestion failed for entry %s", entry_id)
            await self._save(
                connection, workspace_id, entry_id,
                error="Knowledge processing failed. Please try again.",
            )
        else:
            await self._save(connection, workspace_id, entry_id, result=result)

    @staticmethod
    async def _save(
        connection: AsyncConnection, workspace_id: UUID, entry_id: UUID, *,
        result: KnowledgePreviewResponse | None = None, error: str | None = None,
    ) -> None:
        async with AsyncSession(connection, expire_on_commit=False) as session:
            async with session.begin():
                record = await IngestionRepository(session).get(workspace_id, entry_id, lock=True)
                if record is None:  # Deleted while the private worker was processing.
                    return
                if result is not None:
                    record.entry.preview = result.model_dump(mode="json")
                record.asset.status = "parsing_failed" if error else "needs_user_review"
                record.asset.status_message = error
                record.asset.processed_at = datetime.now(UTC)


async def run_ingestion_processor(engine: AsyncEngine, settings: Settings) -> None:
    """Four bounded dispatch slots; persisted unfinished jobs resume after restart."""
    processor = IngestionProcessor(engine, settings)

    async def dispatch() -> None:
        while True:
            try:
                if await processor.process_next():
                    continue
            except Exception:
                logger.exception("Could not dispatch ingestion")
            await asyncio.sleep(1)

    async with asyncio.TaskGroup() as group:
        for _ in range(4):
            group.create_task(dispatch())
