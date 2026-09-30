"""Persistence for TestRun execution lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from markettwin_database.models.testing import TestRun
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession


class RunStateRepository:
    """Manage deterministic TestRun lifecycle transitions."""
    
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        
    async def mark_planning(
        self,
        *,
        test_run_id: UUID,
    ) -> None:
        run = await self._get_run(test_run_id)
        
        if run.status == "planning":
            return
        
        if run.status != "draft":
            raise RuntimeError(
                f'Cannot move TestRun from "{run.status}"'
                'to "planning".'
            )
            
        run.status = "planning"
        
        await self._session.flush()
        
    
    async def mark_running(
        self,
        *,
        test_run_id: UUID,
    ) -> None:
        run = await self._get_run(test_run_id)
        
        if run.status not in {"planning", "queued"}:
            raise RuntimeError(
                f'Cannot move TestRun from "{run.status}"'
                'to "running".'
            )
        
        run.status = "running"
        
        if run.started_at is None:
            run.started_at = datetime.now(UTC)
            
        await self._session.flush()
        
    async def mark_completed(
        self,
        *,
        test_run_id: UUID,
    ) -> None:
        run = await self._get_run(test_run_id)
        
        if run.status != "running":
            raise RuntimeError(
                f'Cannot move TestRun from "{run.status}"'
                'to "completed".'
            )
            
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        
        await self._session.flush()
        
    async def mark_failed(
        self,
        *,
        test_run_id: UUID,
    ) -> None:
        run = await self._get_run(test_run_id)
        
        if run.status not in {
            "planning",
            "queued",
            "running",
        }:
            raise RuntimeError(
                f'Cannot move TestRun from "{run.status}"'
                'to "failed".'
            )
            
        run.status = "failed"
        run.completed_at = datetime.now(UTC)
        
        await self._session.flush()
        
        
    async def _get_run(
        self,
        test_run_id: UUID,
    ) -> TestRun:
        run = await self._session.get(
            TestRun,
            test_run_id,
        )
        
        if run is None:
            raise ValueError(
                f'TestRun "{test_run_id}" not found.'
            )
            
        return run
    
    async def claim_queued_for_planning(
        self,
        *,
        test_run_id: UUID,
    ) -> bool:
        """Atomically claim one queued TestRun for planning."""

        statement = (
            update(TestRun)
            .where(
                TestRun.id == test_run_id,
                TestRun.status == "queued",
            )
            .values(status="planning")
            .returning(TestRun.id)
        )

        result = await self._session.execute(statement)

        return result.scalar_one_or_none() is not None