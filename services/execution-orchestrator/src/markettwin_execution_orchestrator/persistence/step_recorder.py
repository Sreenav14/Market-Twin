"""Database-backed recorder for authoritative browser execution steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.persistence import ExecutionRepository

StepStatus = Literal["policy_blocked", "completed", "failed"]

@dataclass
class ExecutionStepRecorder:
    """Recorder for authoritative browser execution steps."""
    
    session: AsyncSession
    execution_id: UUID
    
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
        
        await repository.finish_execuiton_step(
            execution_id=self.execution_id,
            step_id=step_id,
            status=status,
            observation_summary=observation_summary,
        )
        
        await self.session.commit()