"""Durable, secret-free lifecycle for resumable human-action checkpoints."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from markettwin_database.models.execution import (
    BrowserSession,
    ExecutionStep,
    ExecutionSuspension,
    HumanActionRequest,
)
from markettwin_database.models.testing import TestRun
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class SuspensionConflictError(RuntimeError):
    """The checkpoint is stale, expired, or has already been consumed."""


@dataclass(frozen=True, slots=True)
class SuspensionCheckpoint:
    id: UUID
    test_run_id: UUID
    journey_id: UUID
    execution_id: UUID
    browser_session_id: UUID
    phase: str
    planned_step_index: int
    remaining_ms: int
    checkpoint_version: int
    owner_generation: int


def checkpoint_record(row: ExecutionSuspension) -> SuspensionCheckpoint:
    return SuspensionCheckpoint(
        id=row.id,
        test_run_id=row.test_run_id,
        journey_id=row.journey_id,
        execution_id=row.execution_id,
        browser_session_id=row.browser_session_id,
        phase=row.phase,
        planned_step_index=row.planned_step_index,
        remaining_ms=row.active_deadline_remaining_ms,
        checkpoint_version=row.checkpoint_version,
        owner_generation=row.owner_generation,
    )


class ExecutionSuspensionRepository:
    """Persist continuation cursors without browser state or human input."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_waiting(
        self,
        *,
        test_run_id: UUID,
        journey_id: UUID,
        execution_id: UUID,
        browser_session_id: UUID,
        request_id: UUID,
        last_durable_step_id: int | None,
        owner_generation: int,
        phase: str,
        planned_step_index: int,
        remaining: timedelta,
        human_deadline: datetime,
    ) -> SuspensionCheckpoint:
        now = datetime.now(UTC)
        if (
            phase not in {"auth_preflight", "case_action", "assertion"}
            or planned_step_index < 0
            or remaining <= timedelta(0)
            or human_deadline <= now
            or human_deadline > now + timedelta(hours=24)
        ):
            raise ValueError("Invalid human suspension deadline or continuation cursor.")
        run = await self._session.scalar(
            select(TestRun).where(TestRun.id == test_run_id).with_for_update()
        )
        if run is None or run.status not in {"running", "awaiting_human"}:
            raise SuspensionConflictError("The test run cannot be suspended.")
        browser = await self._session.scalar(
            select(BrowserSession)
            .where(
                BrowserSession.id == browser_session_id,
                BrowserSession.execution_id == execution_id,
            )
            .with_for_update()
        )
        request = await self._session.scalar(
            select(HumanActionRequest).where(
                HumanActionRequest.id == request_id,
                HumanActionRequest.execution_id == execution_id,
                HumanActionRequest.browser_session_id == browser_session_id,
            )
        )
        if (
            browser is None or browser.state != "open"
            or browser.control_mode not in {"human_pending", "human", "verifying"}
            or browser.control_generation != owner_generation
            or request is None or request.status != "leased"
        ):
            raise SuspensionConflictError("The browser handoff is not active.")
        if last_durable_step_id is not None:
            step = await self._session.scalar(
                select(ExecutionStep.id).where(
                    ExecutionStep.id == last_durable_step_id,
                    ExecutionStep.execution_id == execution_id,
                )
            )
            if step is None:
                raise SuspensionConflictError("Checkpoint references an unknown step.")
        version = int(await self._session.scalar(
            select(func.coalesce(func.max(ExecutionSuspension.checkpoint_version), 0))
            .where(ExecutionSuspension.test_run_id == test_run_id)
        ) or 0) + 1
        row = ExecutionSuspension(
            id=uuid4(), test_run_id=test_run_id, journey_id=journey_id,
            execution_id=execution_id, browser_session_id=browser_session_id,
            pending_request_id=request_id, last_durable_step_id=last_durable_step_id,
            checkpoint_version=version, owner_generation=owner_generation,
            phase=phase, planned_step_index=planned_step_index,
            active_deadline_remaining_ms=max(1, int(remaining.total_seconds() * 1000)),
            suspended_at=now, human_deadline=human_deadline, resume_count=0, status="waiting",
        )
        self._session.add(row)
        await self._session.flush()
        return checkpoint_record(row)

    async def claim_ready(self, *, suspension_id: UUID) -> SuspensionCheckpoint:
        now = datetime.now(UTC)
        row = await self._session.scalar(
            select(ExecutionSuspension)
            .where(ExecutionSuspension.id == suspension_id)
            .with_for_update(skip_locked=True)
        )
        if row is None or row.status != "ready" or row.human_deadline <= now:
            raise SuspensionConflictError("The continuation is not ready.")
        row.status = "consumed"
        row.resume_count += 1
        await self._session.flush()
        return checkpoint_record(row)
