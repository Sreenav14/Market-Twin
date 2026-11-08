"""Persistence for agent and browser execution lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
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
        runtime_name: str = "google_adk",
    ) -> None:
        execution = AgentExecution(
            id=execution_id,
            journey_id=journey_id,
            attempt_number=attempt_number,
            status="running",
            runtime_name=runtime_name,
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
        test_run_id: UUID | None = None,
        session_role: str = "legacy",
    ) -> None:
        browser_session = BrowserSession(
            id=browser_session_id,
            execution_id=execution_id,
            browser_type="chromium",
            state="open",
            started_at=_utc_now(),
            test_run_id=test_run_id,
            session_role=session_role,
        )

        self._session.add(browser_session)
        await self._session.flush()

    async def rebind_browser_session(
        self,
        *,
        browser_session_id: UUID,
        execution_id: UUID,
    ) -> None:
        """Point a Room's browser row at its current borrowing execution.

        Watch/activity read models join browser rows to executions; the
        Room's row must follow the in-memory rebind or the live view
        would keep showing the previous item's execution (U-P3-03).
        """

        statement = (
            update(BrowserSession)
            .where(BrowserSession.id == browser_session_id)
            .values(execution_id=execution_id)
        )
        await self._session.execute(statement)
        await self._session.flush()

    async def reap_open_browser_sessions(self) -> int:
        """Close every still-open browser-session row (U-P2-04).

        The worker is a single-owner process (advisory lock in
        worker.main): at startup, no live browser can exist yet, so
        any row left 'starting'/'open' by a crashed predecessor is an
        orphan whose browser died with its process.
        """

        statement = (
            update(BrowserSession)
            .where(BrowserSession.state.in_(("starting", "open")))
            .values(state="closed", closed_at=_utc_now())
        )
        result = await self._session.execute(statement)
        await self._session.flush()
        return int(result.rowcount or 0)

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
            action_summary=action_summary,
            status="running",
            started_at=_utc_now(),
        )
        
        self._session.add(step)
        await self._session.flush()
        
        return step.id

    async def finish_execution_step(
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
