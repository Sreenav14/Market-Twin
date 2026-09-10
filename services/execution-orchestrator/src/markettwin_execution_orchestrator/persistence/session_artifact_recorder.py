"""Persistence for browser-session-level evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.browser.contracts import (
    BrowserSessionArtifacts,
)
from markettwin_execution_orchestrator.persistence.artifact_repository import (
    ArtifactRepository,
)
from markettwin_execution_orchestrator.persistence.artifact_storage import (
    S3ArtifactStorage,
)


@dataclass(slots=True)
class SessionArtifactRecorder:
    """Upload evidence belonging to the whole browser session."""

    session: AsyncSession
    execution_id: UUID
    storage: S3ArtifactStorage

    async def record(
        self,
        artifacts: BrowserSessionArtifacts,
    ) -> None:
        repository = ArtifactRepository(self.session)

        for trace_path in artifacts.trace_paths:
            await self._record_file(
                repository=repository,
                path=trace_path,
                artifact_type="trace",
                content_type="application/zip",
                kind="playwright_trace",
            )

        await self._record_file(
            repository=repository,
            path=artifacts.console_log_path,
            artifact_type="console_log",
            content_type="application/json",
            kind="console_errors",
        )

        await self._record_file(
            repository=repository,
            path=artifacts.page_log_path,
            artifact_type="other",
            content_type="application/json",
            kind="page_errors",
        )

        await self._record_file(
            repository=repository,
            path=artifacts.network_log_path,
            artifact_type="network_log",
            content_type="application/json",
            kind="failed_requests",
        )

        await self.session.commit()

    async def _record_file(
        self,
        *,
        repository: ArtifactRepository,
        path: Path | None,
        artifact_type: str,
        content_type: str,
        kind: str,
    ) -> None:
        if path is None:
            return

        object_key = (
            f"executions/{self.execution_id}/"
            f"session/{path.name}"
        )

        stored = await self.storage.upload(
            local_path=path,
            object_key=object_key,
            content_type=content_type,
        )

        await repository.create(
            execution_id=self.execution_id,
            step_id=None,
            artifact_type=artifact_type,
            stored=stored,
            metadata={
                "kind": kind,
            },
        )