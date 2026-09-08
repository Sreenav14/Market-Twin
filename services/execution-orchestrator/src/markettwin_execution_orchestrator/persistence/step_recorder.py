"""Database-backed recorder for authoritative browser execution steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.browser.contracts import BrowserActionResult
from markettwin_execution_orchestrator.persistence.artifact_repository import ArtifactRepository
from markettwin_execution_orchestrator.persistence.artifact_storage import S3ArtifactStorage
from markettwin_execution_orchestrator.persistence.execution_repository import ExecutionRepository

StepStatus = Literal["policy_blocked", "completed", "failed"]

@dataclass
class ExecutionStepRecorder:
    """Recorder for authoritative browser execution steps."""
    
    session: AsyncSession
    execution_id: UUID
    storage: S3ArtifactStorage
    
    _next_step_number: int = field(
        default = 1,
        init = False,
    )
    
    async def start_step(
        self,
        *,
        action_type: str,
        action_summary: str,
    ) -> int:
        step_number = self._next_step_number
        self._next_step_number += 1
        
        repository = ExecutionRepository(self.session)
        
        step_id = await repository.create_execution_step(
            execution_id=self.execution_id,
            step_number=step_number,
            action_type=action_type,
            action_summary=action_summary,
        )
        
        await self.session.commit()
        
        return step_id
    

    async def finish_step(
        self,
        *,
        step_id: int,
        status: StepStatus,
        observation_summary: str | None = None,
    ) -> None:
        repository = ExecutionRepository(self.session)
        
        await repository.finish_execution_step(
            execution_id=self.execution_id,
            step_id=step_id,
            status=status,
            observation_summary=observation_summary,
        )
        
        await self.session.commit()

    async def record_evidence(
        self,
        *,
        step_id: int,
        result: BrowserActionResult,
    ) -> None:
        repository = ArtifactRepository(self.session)
        observation = result.observation

        if observation.screenshot_path:
            screenshot_path = Path(observation.screenshot_path)
            object_key = (
                f"executions/{self.execution_id}/steps/{step_id}/{screenshot_path.name}"
            )
            stored = await self.storage.upload(
                local_path=screenshot_path,
                object_key=object_key,
                content_type="image/png",
            )
            await repository.create(
                execution_id=self.execution_id,
                step_id=step_id,
                artifact_type="screenshot",
                stored=stored,
                metadata={"browser_action": result.action},
            )

        if observation.accessibility_snapshot_path:
            accessibility_path = Path(observation.accessibility_snapshot_path)
            object_key = (
                f"executions/{self.execution_id}/steps/{step_id}/{accessibility_path.name}"
            )
            stored = await self.storage.upload(
                local_path=accessibility_path,
                object_key=object_key,
                content_type="text/yaml",
            )
            await repository.create(
                execution_id=self.execution_id,
                step_id=step_id,
                artifact_type="other",
                stored=stored,
                metadata={
                    "kind": "accessibility_snapshot",
                    "browser_action": result.action,
                },
            )

        await self.session.commit()
