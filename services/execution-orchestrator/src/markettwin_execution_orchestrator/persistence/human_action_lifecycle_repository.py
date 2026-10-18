"""Worker-side durable lifecycle for authenticated browser handoff requests."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from markettwin_database.models import (
    ApplicationTarget,
    BrowserSession,
    ExecutionSuspension,
    HumanActionRequest,
    HumanControlLease,
    TargetAuthorization,
    TestRun,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession


class HumanHandoffUnavailable(RuntimeError):
    """The frozen run or browser cannot safely enter a human handoff."""


@dataclass(frozen=True, slots=True)
class HumanActionState:
    request_status: str
    control_mode: str
    control_generation: int
    request_expires_at: datetime | None


class HumanActionLifecycleRepository:
    """Persist and finish login handoffs without importing the Control API."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_login_request(
        self,
        *,
        test_run_id: UUID,
        execution_id: UUID,
        browser_session_id: UUID,
        expires_at: datetime,
        assistance_reason: Literal[
            "absent_scope", "ambiguous_scope", "absent_target", "ambiguous_target"
        ] | None = None,
    ) -> UUID:
        if assistance_reason is not None and assistance_reason not in {
            "absent_scope", "ambiguous_scope", "absent_target", "ambiguous_target",
        }:
            raise ValueError("Unsupported recovery reason.")
        now = datetime.now(UTC)
        if expires_at <= now or expires_at > now + timedelta(minutes=15):
            raise ValueError("Human handoff expiry must be within 15 minutes.")

        run = await self._session.scalar(
            select(TestRun)
            .join(ApplicationTarget, ApplicationTarget.id == TestRun.target_id)
            .join(TargetAuthorization, TargetAuthorization.target_id == ApplicationTarget.id)
            .where(
                TestRun.id == test_run_id,
                TestRun.status == "running",
                ApplicationTarget.status == "active",
                ApplicationTarget.deleted_at.is_(None),
                TargetAuthorization.status == "authorized",
                TargetAuthorization.revoked_at.is_(None),
                (TargetAuthorization.expires_at.is_(None))
                | (TargetAuthorization.expires_at > now),
            )
            .order_by(TargetAuthorization.created_at.desc())
            .limit(1)
            .with_for_update(of=(TestRun, ApplicationTarget, TargetAuthorization))
        )
        browser = await self._session.scalar(
            select(BrowserSession)
            .where(
                BrowserSession.id == browser_session_id,
                BrowserSession.execution_id == execution_id,
            )
            .with_for_update()
        )
        if run is None or browser is None or browser.state != "open":
            raise HumanHandoffUnavailable("The authorized browser handoff is unavailable.")

        idempotency_key = (
            "auth-preflight-v1" if browser.control_generation == 0
            else f"auth-preflight-v1:{browser.control_generation}"
        )
        if assistance_reason is not None:
            idempotency_key = f"case-recovery-v1:{browser.control_generation}"
        existing = await self._session.scalar(
            select(HumanActionRequest).where(
                HumanActionRequest.execution_id == execution_id,
                HumanActionRequest.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.browser_session_id != browser_session_id:
                raise HumanHandoffUnavailable("The authentication handoff has changed.")
            return existing.id
        if browser.control_mode != "agent":
            raise HumanHandoffUnavailable("The browser is already in a control transition.")

        request_id = uuid4()
        self._session.add(
            HumanActionRequest(
                id=request_id,
                execution_id=execution_id,
                browser_session_id=browser_session_id,
                request_type="other" if assistance_reason else "login",
                idempotency_key=idempotency_key,
                status="pending",
                instructions=(
                    f"The planned control could not be resolved ({assistance_reason}). "
                    "Prepare the current page so that the planned control is available, "
                    "then Release. Do not perform the pending action. The worker will "
                    "verify the original target and recheck policy before continuing. "
                    "Cancel if the plan describes a control that does not exist."
                    if assistance_reason else
                    "Sign in to the authorized test account, then release control."
                ),
                expires_at=expires_at,
            )
        )
        browser.control_mode = "human_pending"
        run.status = "awaiting_human"
        await self._session.flush()
        return request_id

    async def state(self, *, request_id: UUID) -> HumanActionState | None:
        row = await self._session.execute(
            select(HumanActionRequest, BrowserSession)
            .join(BrowserSession, BrowserSession.id == HumanActionRequest.browser_session_id)
            .where(HumanActionRequest.id == request_id)
            .execution_options(populate_existing=True)
        )
        pair = row.one_or_none()
        if pair is None:
            return None
        request, browser = pair
        return HumanActionState(
            request_status=request.status,
            control_mode=browser.control_mode,
            control_generation=browser.control_generation,
            request_expires_at=request.expires_at,
        )

    async def acknowledge_skipped(self, *, request_id: UUID) -> None:
        """Let independent work continue after the worker observes durable Skip."""
        request = await self._session.scalar(
            select(HumanActionRequest).where(HumanActionRequest.id == request_id).with_for_update()
        )
        if request is None or request.status != "skipped":
            raise HumanHandoffUnavailable("The skipped handoff is unavailable.")
        await self._resume_run(execution_id=request.execution_id)
        await self._session.flush()

    async def finish_verification(
        self,
        *,
        request_id: UUID,
        expected_generation: int,
        verified: bool,
    ) -> None:
        pair = await self._session.execute(
            select(HumanActionRequest, BrowserSession)
            .join(BrowserSession, BrowserSession.id == HumanActionRequest.browser_session_id)
            .where(HumanActionRequest.id == request_id)
            .with_for_update(of=(HumanActionRequest, BrowserSession))
            .execution_options(populate_existing=True)
        )
        row = pair.one_or_none()
        if row is None:
            raise HumanHandoffUnavailable("The authentication handoff is unavailable.")
        request, browser = row
        if request.status != "leased" or browser.control_mode != "verifying":
            raise HumanHandoffUnavailable("The authentication handoff is no longer active.")
        if browser.control_generation != expected_generation:
            raise HumanHandoffUnavailable("The browser control generation has changed.")

        suspension = await self._session.scalar(
            select(ExecutionSuspension)
            .where(
                ExecutionSuspension.pending_request_id == request_id,
                ExecutionSuspension.status == "waiting",
            )
            .with_for_update()
        )
        if verified:
            request.status = "completed"
            request.completed_at = datetime.now(UTC)
            browser.control_mode = "agent"
            if suspension is not None:
                suspension.status = "ready"
        else:
            request.status = "cancelled"
            browser.control_mode = "none"
            if suspension is not None:
                suspension.status = "abandoned"
        await self._resume_run(execution_id=request.execution_id)
        await self._session.flush()

    async def abandon(self, *, request_id: UUID) -> None:
        pair = await self._session.execute(
            select(HumanActionRequest, BrowserSession)
            .join(BrowserSession, BrowserSession.id == HumanActionRequest.browser_session_id)
            .where(HumanActionRequest.id == request_id)
            .with_for_update(of=(HumanActionRequest, BrowserSession))
            .execution_options(populate_existing=True)
        )
        row = pair.one_or_none()
        if row is None:
            return
        request, browser = row
        if request.status in {"pending", "leased"}:
            request.status = (
                "expired"
                if request.expires_at is not None and request.expires_at <= datetime.now(UTC)
                else "cancelled"
            )
            browser.control_generation += 1
            browser.control_mode = "none"
            leases = await self._session.scalars(
                select(HumanControlLease)
                .where(
                    HumanControlLease.request_id == request_id,
                    HumanControlLease.released_at.is_(None),
                )
                .with_for_update()
            )
            for lease in leases:
                lease.released_at = datetime.now(UTC)
        suspension = await self._session.scalar(
            select(ExecutionSuspension)
            .where(
                ExecutionSuspension.pending_request_id == request_id,
                ExecutionSuspension.status.in_(("waiting", "ready")),
            )
            .with_for_update()
        )
        if suspension is not None:
            suspension.status = "abandoned"
        await self._resume_run(execution_id=request.execution_id)
        await self._session.flush()

    async def _resume_run(self, *, execution_id: UUID) -> None:
        from markettwin_database.models import AgentExecution, PersonaJourney

        await self._session.execute(
            update(TestRun).where(
                TestRun.id.in_(
                    select(PersonaJourney.test_run_id)
                    .join(AgentExecution, AgentExecution.journey_id == PersonaJourney.id)
                    .where(AgentExecution.id == execution_id)
                ),
                TestRun.status == "awaiting_human",
            ).values(status="running")
        )
