"""Persistence for agent and browser execution lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.persistence.models import (
    AgentExecution,
    BrowserSession,
    ExecutionStep,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ExecutionRepository:
    """Persist one Persona Journey execution lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_agent_execution(
        self,
        *,
        execution_id: UUID,
        journey_id: UUID,
        attempt_number: int = 1,
    ) -> None:
        execution = AgentExecution(
            id=execution_id,
            journey_id=journey_id,
            attempt_number=attempt_number,
            status="running",
            runtime_name="google_adk",
            started_at=_utc_now(),
        )

        self._session.add(execution)
        await self._session.flush()

    async def finish_agent_execution(
        self,
        *,
        execution_id: UUID,
        status: str,
        outcome: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        execution = await self._session.get(
            AgentExecution,
            execution_id,
        )

        if execution is None:
            raise ValueError(
                f'AgentExecution "{execution_id}" does not exist.'
            )

        execution.status = status
        execution.outcome = outcome
        execution.error_code = error_code
        execution.error_message = error_message
        execution.completed_at = _utc_now()

        await self._session.flush()

    async def create_browser_session(
        self,
        *,
        browser_session_id: UUID,
        execution_id: UUID,
    ) -> None:
        browser_session = BrowserSession(
            id=browser_session_id,
            execution_id=execution_id,
            browser_type="chromium",
            state="open",
            started_at=_utc_now(),
        )

        self._session.add(browser_session)
        await self._session.flush()

    async def mark_browser_session_closed(
        self,
        *,
        browser_session_id: UUID,
    ) -> None:
        browser_session = await self._get_browser_session(
            browser_session_id
        )

        browser_session.state = "closed"
        browser_session.closed_at = _utc_now()

        await self._session.flush()

    async def mark_browser_session_failed(
        self,
        *,
        browser_session_id: UUID,
    ) -> None:
        browser_session = await self._get_browser_session(
            browser_session_id
        )

        browser_session.state = "failed"
        browser_session.closed_at = _utc_now()

        await self._session.flush()

    async def _get_browser_session(
        self,
        browser_session_id: UUID,
    ) -> BrowserSession:
        browser_session = await self._session.get(
            BrowserSession,
            browser_session_id,
        )

        if browser_session is None:
            raise ValueError(
                f'BrowserSession "{browser_session_id}" does not exist.'
            )

        return browser_session
    
    async def create_execution_step(
        self,
        *,
        execution_id: UUID,
        step_number: int,
        action_type: str,
        action_summary: str,
    ) -> int:
        """Create one authoritative browser/tool execution step."""
        
        step = ExecutionStep(
            execution_id=execution_id,
            step_number=step_number,
            action_type=action_type,
            status="running",
            started_at=_utc_now(),
        )
        
        self._session.add(step)
        await self._session.flush()
        
        return step.id

    async def finish_execuiton_step(
        self,
        *,
        execution_id: UUID,
        step_id: int,
        status: str,
        observation_summary: str | None = None,
    ) -> None:
        """Finish one execution step."""
        
        step = await self._session.get(
            ExecutionStep,
            step_id,
        )
        
        if step is None or step.execution_id != execution_id:
            raise ValueError(
                f'ExecutionStep "{step_id}" does not belong to'
                f'AgentExecution "{execution_id}".'
            )
            
        
        step.status = status
        step.observation_summary = observation_summary
        step.completed_at = _utc_now()
        
        await self._session.flush()