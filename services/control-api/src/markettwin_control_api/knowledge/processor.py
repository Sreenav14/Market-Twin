"""Dispatch persisted ingestion to the existing private worker, independently of the UI."""

import asyncio
import hashlib
import logging
from datetime import UTC, datetime
from io import BytesIO
from tempfile import TemporaryFile
from typing import BinaryIO, cast
from uuid import UUID

from markettwin_database.models.knowledge import AssetVersion, IngestionEntry, ProductBlueprint
from markettwin_shared.knowledge_preview import KnowledgePreviewResponse
from sqlalchemy import select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from markettwin_control_api.config import Settings
from markettwin_control_api.knowledge.client import KnowledgeWorkerClient, KnowledgeWorkerError
from markettwin_control_api.knowledge.link_research import (
    LINK_MARKER_TYPE,
    decode_link_marker,
    research_link,
)
from markettwin_control_api.knowledge.repository import IngestionRepository
from markettwin_control_api.knowledge.storage import KnowledgeSourceStorage

logger = logging.getLogger(__name__)
PENDING_STATUSES = ("uploaded", "processing")


class LinkResearchFailed(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class IngestionProcessor:
    def __init__(self, engine: AsyncEngine, settings: Settings) -> None:
        self.engine = engine
        self.settings = settings

    async def process_next(self) -> bool:
        cursor: tuple[datetime, UUID] | None = None
        while True:
            statement = (
                select(IngestionEntry.workspace_id, IngestionEntry.id, AssetVersion.created_at)
                .join(AssetVersion, AssetVersion.id == IngestionEntry.asset_version_id)
                .join(ProductBlueprint, ProductBlueprint.id == IngestionEntry.blueprint_id)
                .where(
                    ProductBlueprint.status == "active", AssetVersion.status.in_(PENDING_STATUSES)
                )
                .order_by(AssetVersion.created_at, IngestionEntry.id).limit(20)
            )
            if cursor is not None:
                statement = statement.where(
                    tuple_(AssetVersion.created_at, IngestionEntry.id) > cursor
                )
            async with AsyncSession(self.engine) as session:
                candidates = (await session.execute(statement)).all()
            for workspace_id, entry_id, _created_at in candidates:
                if await self.process_entry(workspace_id, entry_id):
                    return True
            if len(candidates) < 20:
                return False
            cursor = (candidates[-1][2], candidates[-1][1])

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
                researching = record.asset.declared_content_type == LINK_MARKER_TYPE
                record.asset.status_message = (
                    "Researching public pages — 0 inspected, 0 inaccessible."
                    if researching else None
                )
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
                if content_type == LINK_MARKER_TYPE:
                    prepared = await self._research_queued_link(
                        connection, workspace_id, entry_id, key, stream,
                    )
                    if prepared is None:
                        return
                    filename, content_type, payload = prepared
                    stream.seek(0)
                    stream.truncate()
                    stream.write(payload)
                    stream.seek(0)
                result = await self._preview_with_retry(
                    filename=filename, content_type=content_type, stream=stream
                )
        except LinkResearchFailed as error:
            await self._save(connection, workspace_id, entry_id, error=error.message)
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

    async def _note(
        self, connection: AsyncConnection, workspace_id: UUID, entry_id: UUID, message: str,
    ) -> None:
        async with AsyncSession(connection, expire_on_commit=False) as session:
            async with session.begin():
                record = await IngestionRepository(session).get(workspace_id, entry_id, lock=True)
                if record is not None and record.asset.status == "processing":
                    record.asset.status_message = message

    async def _research_queued_link(
        self,
        connection: AsyncConnection,
        workspace_id: UUID,
        entry_id: UUID,
        key: str,
        stream: BinaryIO,
    ) -> tuple[str, str, bytes] | None:
        """Retain the queued manifest and persist a separate immutable research bundle."""
        url = decode_link_marker(stream.read())
        if url is None:
            raise LinkResearchFailed("The queued link manifest is invalid. Submit the link again.")
        progress = {"inspected": 0, "inaccessible": 0}

        def report(inspected: int, inaccessible: int) -> None:
            progress["inspected"] = inspected
            progress["inaccessible"] = inaccessible

        task = asyncio.create_task(asyncio.to_thread(research_link, url, report))
        try:
            while not task.done():
                await self._note(
                    connection, workspace_id, entry_id,
                    "Researching public pages — "
                    f"{progress['inspected']} inspected, {progress['inaccessible']} inaccessible.",
                )
                await asyncio.wait({task}, timeout=2)
            filename, content = task.result()
        except ValueError as error:
            raise LinkResearchFailed(str(error)[:500]) from error
        except OSError as error:
            raise LinkResearchFailed(
                "The linked source could not be reached. Check the link or upload a document."
            ) from error
        finally:
            # to_thread cannot stop its thread. Keep advisory ownership even if a
            # progress update fails or shutdown cancels this coroutine mid-crawl.
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
        digest = hashlib.sha256(content).hexdigest()
        research_key = f"{key}/research/{digest}.txt"
        await KnowledgeSourceStorage(self.settings).put(
            key=research_key, stream=BytesIO(content), content_type="text/plain",
        )
        async with AsyncSession(connection, expire_on_commit=False) as session:
            async with session.begin():
                record = await IngestionRepository(session).get(workspace_id, entry_id, lock=True)
                if record is None:
                    return None
                record.asset.original_filename = filename
                record.asset.object_key = research_key
                record.asset.declared_content_type = "text/plain"
                record.asset.size_bytes = len(content)
                record.asset.sha256 = digest
                record.asset.status_message = "Generating knowledge."
        return filename, "text/plain", content

    async def _preview_with_retry(
        self, *, filename: str, content_type: str | None, stream: BinaryIO,
    ) -> KnowledgePreviewResponse:
        client = KnowledgeWorkerClient(self.settings)
        for attempt in range(3):
            stream.seek(0)
            try:
                return await client.preview(
                    filename=filename, content_type=content_type, stream=stream,
                )
            except KnowledgeWorkerError as error:
                terminal = (
                    error.status_code not in {502, 503, 504}
                    or error.message.startswith("Knowledge generation reached its output limit.")
                )
                if terminal or attempt == 2:
                    raise
                logger.warning(
                    "Knowledge worker returned %s; retrying attempt %s of 3",
                    error.status_code, attempt + 2,
                )
                await asyncio.sleep(2 ** (attempt + 1))
        raise RuntimeError("Knowledge preview exhausted its retry attempts.")

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
                    previous = KnowledgePreviewResponse.model_validate(record.entry.preview)
                    source = result.source.model_copy(update={
                        "original_url": previous.source.original_url,
                    })
                    record.entry.preview = result.model_copy(update={"source": source}).model_dump(
                        mode="json"
                    )
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
