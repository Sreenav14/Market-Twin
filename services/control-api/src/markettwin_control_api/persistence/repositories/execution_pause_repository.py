"""Durable cooperative pause intent; only the worker acknowledges or resumes execution."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from markettwin_database.models import (
    AgentExecution,
    BrowserSession,
    ExecutionPauseRequest,
    HumanActionRequest,
    HumanControlLease,
    PersonaJourney,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.persistence.repositories.live_browser_repository import (
    LiveBrowserRepository,
)

ACTIVE_PAUSES = ("requested", "paused", "resume_requested")


class PauseRejected(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__("Execution pause is unavailable.")
        self.status_code = status_code


class ExecutionPauseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def request(
        self, *, run_id: UUID, actor_id: UUID, browser_session_id: UUID, generation: int,
    ) -> ExecutionPauseRequest:
        run = await LiveBrowserRepository(self.session).authorized_run(run_id=run_id,
                                                                       actor_id=actor_id)
        if run is None:
            raise PauseRejected(404)
        row = (await self.session.execute(
            select(BrowserSession, AgentExecution, PersonaJourney)
            .join(AgentExecution, AgentExecution.id == BrowserSession.execution_id)
            .join(PersonaJourney, PersonaJourney.id == AgentExecution.journey_id)
            .where(BrowserSession.id == browser_session_id, PersonaJourney.test_run_id == run_id)
            .with_for_update(of=BrowserSession).execution_options(populate_existing=True)
        )).one_or_none()
        if row is None:
            raise PauseRejected(409)
        browser, execution, journey = row
        if (run.status not in {"planning", "running", "awaiting_human"} or browser.state != "open"
                or execution.status != "running" or browser.control_generation != generation):
            raise PauseRejected(409)
        pending = await self.session.scalar(select(ExecutionPauseRequest).where(
            ExecutionPauseRequest.browser_session_id == browser_session_id,
            ExecutionPauseRequest.status.in_(ACTIVE_PAUSES),
        ).with_for_update())
        if pending is not None:
            if pending.expires_at <= datetime.now(UTC):
                raise PauseRejected(410)
            if pending.generation != generation:
                raise PauseRejected(409)
            return pending
        if browser.control_mode != "agent" or run.status not in {"planning", "running"}:
            raise PauseRejected(409)
        pause = ExecutionPauseRequest(
            test_run_id=run_id, journey_id=journey.id, execution_id=execution.id,
            browser_session_id=browser_session_id, requested_by_user_id=actor_id,
            generation=generation, status="requested",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        self.session.add(pause)
        await self.session.flush()
        return pause

    async def resume(self, *, run_id: UUID, pause_id: UUID,
                     actor_id: UUID) -> ExecutionPauseRequest:
        run = await LiveBrowserRepository(self.session).authorized_run(run_id=run_id,
                                                                       actor_id=actor_id)
        if run is None:
            raise PauseRejected(404)
        # Resolve IDs, then lock browser → linked human request → pause, matching
        # worker order. Revalidate every status after acquiring those locks.
        candidate = await self.session.scalar(select(ExecutionPauseRequest).where(
            ExecutionPauseRequest.id == pause_id, ExecutionPauseRequest.test_run_id == run_id,
        ))
        if candidate is None:
            raise PauseRejected(404)
        browser = await self.session.scalar(select(BrowserSession)
        .join(AgentExecution, AgentExecution.id == BrowserSession.execution_id).where(
            BrowserSession.id == candidate.browser_session_id,
            BrowserSession.execution_id == candidate.execution_id,
            AgentExecution.status == "running",
        ).with_for_update(of=BrowserSession).execution_options(populate_existing=True))
        human = await self.session.scalar(select(HumanActionRequest).where(
            HumanActionRequest.id == candidate.human_request_id,
            HumanActionRequest.browser_session_id == candidate.browser_session_id,
            HumanActionRequest.execution_id == candidate.execution_id,
        ).with_for_update().execution_options(populate_existing=True))
        pause = await self.session.scalar(select(ExecutionPauseRequest).where(
            ExecutionPauseRequest.id == pause_id, ExecutionPauseRequest.test_run_id == run_id,
        ).with_for_update().execution_options(populate_existing=True))
        if pause is None or browser is None or human is None:
            raise PauseRejected(409)
        if pause.expires_at <= datetime.now(UTC):
            raise PauseRejected(410)
        if (run.status != "awaiting_human" or pause.status not in {"paused", "resume_requested"}
                or browser.state != "open" or browser.control_mode != "human_pending"
                or browser.control_generation != pause.generation or human.status != "pending"):
            raise PauseRejected(409)
        lease = await self.session.scalar(select(HumanControlLease.id).where(
            HumanControlLease.browser_session_id == browser.id,
            HumanControlLease.released_at.is_(None),
            HumanControlLease.expires_at > datetime.now(UTC),
        ).limit(1))
        if lease is not None:
            raise PauseRejected(409)
        pause.status = "resume_requested"
        pause.resume_requested_by_user_id = actor_id
        await self.session.flush()
        return pause

    async def latest(self, *, run_id: UUID,
                     browser_session_id: UUID) -> ExecutionPauseRequest | None:
        return await self.session.scalar(select(ExecutionPauseRequest).where(
            ExecutionPauseRequest.test_run_id == run_id,
            ExecutionPauseRequest.browser_session_id == browser_session_id,
        ).order_by(ExecutionPauseRequest.created_at.desc(),
                   ExecutionPauseRequest.id.desc()).limit(1))
