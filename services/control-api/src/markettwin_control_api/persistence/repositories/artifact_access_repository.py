"""Database access for evidence artifacts exposed through the Control API."""

from dataclasses import dataclass
from uuid import UUID

from markettwin_database.models import (
    AgentExecution,
    Artifact,
    PersonaJourney,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class ArtifactAccessRecord:
    """Storage metadata for one artifact belonging to a TestRun."""

    artifact_id: UUID
    test_run_id: UUID
    execution_id: UUID
    step_id: int | None
    artifact_type: str
    storage_provider: str
    bucket: str
    object_key: str
    content_type: str
    size_bytes: int | None
    sha256: str | None


class ArtifactAccessRepository:
    """Read evidence artifacts while enforcing TestRun ownership."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_for_test_run(
        self,
        *,
        artifact_id: UUID,
        test_run_id: UUID,
    ) -> ArtifactAccessRecord | None:
        """Return an artifact only when it belongs to the TestRun."""

        statement = (
            select(Artifact)
            .join(
                AgentExecution,
                AgentExecution.id == Artifact.execution_id,
            )
            .join(
                PersonaJourney,
                PersonaJourney.id == AgentExecution.journey_id,
            )
            .where(
                Artifact.id == artifact_id,
                PersonaJourney.test_run_id == test_run_id,
            )
        )

        artifact = await self._session.scalar(statement)

        if artifact is None:
            return None

        return ArtifactAccessRecord(
            artifact_id=artifact.id,
            test_run_id=test_run_id,
            execution_id=artifact.execution_id,
            step_id=artifact.step_id,
            artifact_type=artifact.artifact_type,
            storage_provider=artifact.storage_provider,
            bucket=artifact.bucket,
            object_key=artifact.object_key,
            content_type=artifact.content_type,
            size_bytes=artifact.size_bytes,
            sha256=artifact.sha256,
        )