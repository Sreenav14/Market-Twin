"""Persistence for MarketTwin evidence artifact metadata."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.persistence.artifact_storage import (
    StoredArtifact,
)
from markettwin_execution_orchestrator.persistence.models import (
    Artifact,
)


class ArtifactRepository:
    """Persist uploaded evidence metadata."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        execution_id: UUID,
        step_id: int,
        artifact_type: str,
        stored: StoredArtifact,
        metadata: dict[str, object] | None = None,
    ) -> UUID:
        artifact = Artifact(
            execution_id=execution_id,
            step_id=step_id,
            artifact_type=artifact_type,
            storage_provider=stored.storage_provider,
            bucket=stored.bucket,
            object_key=stored.object_key,
            content_type=stored.content_type,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            metadata_json=metadata or {},
        )

        self._session.add(artifact)
        await self._session.flush()

        return artifact.id
