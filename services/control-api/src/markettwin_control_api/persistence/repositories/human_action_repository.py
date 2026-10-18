"""Transactional persistence for same-browser human-control requests and leases."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from markettwin_database.models.execution import (
    AgentExecution,
    BrowserSession,
    ExecutionSuspension,
    HumanActionRequest,
    HumanControlLease,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.api.permissions import TARGET_AUTHORIZATION_ROLES
from markettwin_control_api.persistence.models import (
    ApplicationTarget,
    PersonaJourney,
    TargetAuthorization,
    TestRun,
    Workspace,
    WorkspaceMember,
)


class HumanActionError(RuntimeError):
    """Base error for a rejected human-control operation."""


class HumanActionNotAuthorizedError(HumanActionError):
    """The actor does not have current target-operator permission."""


class HumanActionConflictError(HumanActionError):
    """The request or browser is already controlled or in another state."""


class HumanActionExpiredError(HumanActionError):
    """The request or lease has expired."""


@dataclass(frozen=True, slots=True)
class HumanActionRecord:
    request_id: UUID
    execution_id: UUID
    browser_session_id: UUID
    request_type: str
    status: str
    expires_at: datetime | None
    terminal_generation: int | None = None


@dataclass(frozen=True, slots=True)
class HumanLeaseGrant:
    """Internal one-time claim result; callers must not serialize lease_token."""

    request_id: UUID
    browser_session_id: UUID
    execution_id: UUID
    journey_id: UUID
    lease_id: UUID
    lease_token: str
    generation: int
    expires_at: datetime


def _request_record(request: HumanActionRequest) -> HumanActionRecord:
    return HumanActionRecord(
        request_id=request.id,
        execution_id=request.execution_id,
        browser_session_id=request.browser_session_id,
        request_type=request.request_type,
        status=request.status,
        expires_at=request.expires_at,
        terminal_generation=request.terminal_generation,
    )


class HumanActionRepository:
    """Atomic request and lease operations; caller owns the DB transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_request(
        self,
        *,
        execution_id: UUID,
        browser_session_id: UUID,
        request_type: str,
        idempotency_key: str,
        expires_at: datetime,
    ) -> HumanActionRecord:
        if request_type not in {"login", "password", "mfa", "captcha", "other"}:
            raise ValueError("Unsupported human action request type.")
        if not idempotency_key or len(idempotency_key) > 256:
            raise ValueError("A bounded request idempotency key is required.")
        now = datetime.now(UTC)
        if expires_at <= now:
            raise ValueError("Human action request expiry must be in the future.")

        browser_result = await self._session.execute(
            select(BrowserSession)
            .where(
                BrowserSession.id == browser_session_id,
                BrowserSession.execution_id == execution_id,
            )
            .with_for_update()
        )
        browser = browser_result.scalar_one_or_none()
        if browser is None or browser.state != "open":
            raise HumanActionConflictError("The browser session is not available.")

        request_id = uuid4()
        inserted = await self._session.execute(
            pg_insert(HumanActionRequest)
            .values(
                id=request_id,
                execution_id=execution_id,
                browser_session_id=browser_session_id,
                request_type=request_type,
                idempotency_key=idempotency_key,
                status="pending",
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    HumanActionRequest.execution_id,
                    HumanActionRequest.idempotency_key,
                ],
                index_where=HumanActionRequest.idempotency_key.is_not(None),
            )
            .returning(HumanActionRequest.id)
        )
        inserted_id = inserted.scalar_one_or_none()
        if inserted_id is None:
            existing_result = await self._session.execute(
                select(HumanActionRequest).where(
                    HumanActionRequest.execution_id == execution_id,
                    HumanActionRequest.idempotency_key == idempotency_key,
                )
            )
            existing = existing_result.scalar_one()
            return _request_record(existing)
        request_result = await self._session.execute(
            select(HumanActionRequest).where(HumanActionRequest.id == inserted_id)
        )
        return _request_record(request_result.scalar_one())

    async def _lock_operator_request(
        self,
        *,
        request_id: UUID,
        actor_id: UUID,
    ) -> tuple[HumanActionRequest, BrowserSession] | None:
        now = datetime.now(UTC)
        statement = (
            select(HumanActionRequest, BrowserSession)
            .join(
                BrowserSession,
                BrowserSession.id == HumanActionRequest.browser_session_id,
            )
            .join(AgentExecution, AgentExecution.id == HumanActionRequest.execution_id)
            .join(PersonaJourney, PersonaJourney.id == AgentExecution.journey_id)
            .join(TestRun, TestRun.id == PersonaJourney.test_run_id)
            .join(Workspace, Workspace.id == TestRun.workspace_id)
            .join(
                WorkspaceMember,
                (WorkspaceMember.workspace_id == TestRun.workspace_id)
                & (WorkspaceMember.user_id == actor_id),
            )
            .join(
                ApplicationTarget,
                ApplicationTarget.id == TestRun.target_id,
            )
            .join(
                TargetAuthorization,
                TargetAuthorization.target_id == ApplicationTarget.id,
            )
            .where(
                HumanActionRequest.id == request_id,
                Workspace.status == "active",
                Workspace.deleted_at.is_(None),
                WorkspaceMember.role.in_(TARGET_AUTHORIZATION_ROLES),
                ApplicationTarget.status == "active",
                ApplicationTarget.deleted_at.is_(None),
                TargetAuthorization.status == "authorized",
                TargetAuthorization.revoked_at.is_(None),
                (TargetAuthorization.expires_at.is_(None))
                | (TargetAuthorization.expires_at > now),
            )
            .order_by(TargetAuthorization.created_at.desc())
            .limit(1)
            .with_for_update(of=(HumanActionRequest, BrowserSession, TargetAuthorization))
        )
        result = await self._session.execute(statement)
        return result.tuples().one_or_none()

    async def claim(
        self,
        *,
        request_id: UUID,
        actor_id: UUID,
        lease_duration: timedelta = timedelta(seconds=30),
    ) -> HumanLeaseGrant:
        if lease_duration <= timedelta(0) or lease_duration > timedelta(minutes=1):
            raise ValueError("Lease heartbeat must be between 0 and 60 seconds.")
        row = await self._lock_operator_request(request_id=request_id, actor_id=actor_id)
        if row is None:
            raise HumanActionNotAuthorizedError("Human control is not authorized for this request.")
        request, browser = row
        now = datetime.now(UTC)
        if request.expires_at is None or request.expires_at <= now:
            raise HumanActionExpiredError("The human action request has expired.")
        if request.status not in {"pending", "leased"}:
            raise HumanActionConflictError("The human action request is no longer available.")
        if browser.state != "open" or browser.control_mode not in {
            "agent", "human_pending", "human",
        }:
            raise HumanActionConflictError("The browser is not available for human control.")

        leases_result = await self._session.execute(
            select(HumanControlLease)
            .where(
                HumanControlLease.browser_session_id == browser.id,
                HumanControlLease.released_at.is_(None),
            )
            .with_for_update()
        )
        leases = list(leases_result.scalars().all())
        active = [lease for lease in leases if lease.expires_at > now]
        if active:
            raise HumanActionConflictError("Another operator currently controls this browser.")
        for lease in leases:
            lease.released_at = now

        generation = browser.control_generation + 1
        browser.control_generation = generation
        browser.control_mode = "human_pending"
        request.status = "leased"
        raw_token = secrets.token_urlsafe(32)
        expires_at = min(now + lease_duration, request.expires_at)
        lease = HumanControlLease(
            id=uuid4(),
            request_id=request.id,
            browser_session_id=browser.id,
            user_id=actor_id,
            lease_token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            generation=generation,
            expires_at=expires_at,
        )
        self._session.add(lease)
        journey_id = await self._session.scalar(
            select(AgentExecution.journey_id).where(AgentExecution.id == request.execution_id)
        )
        if journey_id is None:
            raise HumanActionConflictError("The browser execution is unavailable.")
        await self._session.flush()
        return HumanLeaseGrant(
            request_id=request.id,
            browser_session_id=browser.id,
            execution_id=request.execution_id,
            journey_id=journey_id,
            lease_id=lease.id,
            lease_token=raw_token,
            generation=generation,
            expires_at=expires_at,
        )

    async def renew(
        self,
        *,
        lease_id: UUID,
        actor_id: UUID,
        lease_token: str,
        generation: int,
        expected_request_id: UUID | None = None,
        lease_duration: timedelta = timedelta(seconds=30),
    ) -> datetime:
        if lease_duration <= timedelta(0) or lease_duration > timedelta(minutes=1):
            raise ValueError("Lease heartbeat must be between 0 and 60 seconds.")
        await self._authorize_lease(lease_id=lease_id, actor_id=actor_id)
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(HumanControlLease, BrowserSession, HumanActionRequest)
            .join(BrowserSession, BrowserSession.id == HumanControlLease.browser_session_id)
            .join(HumanActionRequest, HumanActionRequest.id == HumanControlLease.request_id)
            .where(
                HumanControlLease.id == lease_id,
                HumanControlLease.user_id == actor_id,
                HumanControlLease.released_at.is_(None),
            )
            .with_for_update(of=(HumanControlLease, BrowserSession, HumanActionRequest))
        )
        row = result.one_or_none()
        if row is None:
            raise HumanActionNotAuthorizedError("The human control lease is unavailable.")
        lease, browser, request = row
        if expected_request_id is not None and request.id != expected_request_id:
            raise HumanActionNotAuthorizedError("The human control lease is unavailable.")
        token_hash = hashlib.sha256(lease_token.encode("utf-8")).hexdigest()
        if not secrets.compare_digest(lease.lease_token_hash, token_hash):
            raise HumanActionNotAuthorizedError("The human control lease is unavailable.")
        if (
            lease.expires_at <= now
            or lease.generation != generation
            or browser.control_generation != generation
            or browser.control_mode != "human"
            or request.expires_at is None
            or request.expires_at <= now
        ):
            raise HumanActionExpiredError("The human control lease has expired or been revoked.")
        lease.expires_at = min(now + lease_duration, request.expires_at)
        await self._session.flush()
        return lease.expires_at

    async def release_for_verification(
        self,
        *,
        lease_id: UUID,
        actor_id: UUID,
        lease_token: str,
        generation: int,
        expected_request_id: UUID | None = None,
    ) -> int:
        lease, browser = await self._lock_lease(
            lease_id=lease_id,
            actor_id=actor_id,
            lease_token=lease_token,
            generation=generation,
            allow_released=True,
        )
        if expected_request_id is not None:
            request_id = await self._session.scalar(
                select(HumanControlLease.request_id).where(HumanControlLease.id == lease_id)
            )
            if request_id != expected_request_id:
                raise HumanActionNotAuthorizedError("The human control lease is unavailable.")
        if browser.control_mode != "human":
            if lease.released_at is not None and browser.control_mode == "verifying":
                request = await self._session.get(HumanActionRequest, lease.request_id)
                if (request is not None and request.status == "leased"
                        and request.expires_at is not None
                        and request.expires_at > datetime.now(UTC)):
                    return browser.control_generation
            raise HumanActionConflictError("The browser is not in human control.")
        lease.released_at = datetime.now(UTC)
        browser.control_generation += 1
        browser.control_mode = "verifying"
        await self._session.flush()
        return browser.control_generation

    async def abort_claim(
        self,
        *,
        lease_id: UUID,
        actor_id: UUID,
        lease_token: str,
        generation: int,
        expected_request_id: UUID,
    ) -> int:
        """Return a failed handoff to the agent and fence any late ticket."""
        lease, browser = await self._lock_lease(
            lease_id=lease_id,
            actor_id=actor_id,
            lease_token=lease_token,
            generation=generation,
        )
        request = await self._session.get(HumanActionRequest, expected_request_id)
        if request is None or request.id != lease.request_id:
            raise HumanActionNotAuthorizedError("The human control lease is unavailable.")
        if browser.control_mode not in {"human_pending", "human"}:
            raise HumanActionConflictError("The browser handoff is no longer active.")
        lease.released_at = datetime.now(UTC)
        browser.control_generation += 1
        browser.control_mode = "agent"
        request.status = "pending"
        await self._session.flush()
        return browser.control_generation

    async def _lock_lease(
        self,
        *,
        lease_id: UUID,
        actor_id: UUID,
        lease_token: str,
        generation: int,
        allow_released: bool = False,
    ) -> tuple[HumanControlLease, BrowserSession]:
        await self._authorize_lease(lease_id=lease_id, actor_id=actor_id)
        result = await self._session.execute(
            select(HumanControlLease, BrowserSession)
            .join(BrowserSession, BrowserSession.id == HumanControlLease.browser_session_id)
            .where(
                HumanControlLease.id == lease_id,
                HumanControlLease.user_id == actor_id,
                (HumanControlLease.released_at.is_(None)) | allow_released,
            )
            .with_for_update(of=(HumanControlLease, BrowserSession))
        )
        row = result.one_or_none()
        if row is None:
            raise HumanActionNotAuthorizedError("The human control lease is unavailable.")
        lease, browser = row
        token_hash = hashlib.sha256(lease_token.encode("utf-8")).hexdigest()
        release_retry = (
            allow_released and lease.released_at is not None
            and browser.control_mode == "verifying"
            and browser.control_generation == generation + 1
        )
        if (
            not secrets.compare_digest(lease.lease_token_hash, token_hash)
            or lease.generation != generation
            or (lease.released_at is not None and not release_retry)
            or (not release_retry and (
                browser.control_generation != generation or lease.expires_at <= datetime.now(UTC)
            ))
        ):
            raise HumanActionNotAuthorizedError("The human control lease is unavailable.")
        return lease, browser

    async def _authorize_lease(self, *, lease_id: UUID, actor_id: UUID) -> None:
        """Lock request/browser before lease, matching the claim lock order."""
        request_id = await self._session.scalar(
            select(HumanControlLease.request_id).where(
                HumanControlLease.id == lease_id, HumanControlLease.user_id == actor_id,
            )
        )
        if request_id is None or await self._lock_operator_request(
            request_id=request_id, actor_id=actor_id,
        ) is None:
            raise HumanActionNotAuthorizedError("Human control is no longer authorized.")

    async def validate_active_lease(
        self, *, lease_id: UUID, actor_id: UUID, generation: int,
    ) -> bool:
        """Revalidate viewer authority without exposing or requiring the lease secret."""
        lease = await self._session.get(HumanControlLease, lease_id)
        if lease is None or lease.user_id != actor_id:
            return False
        row = await self._lock_operator_request(request_id=lease.request_id, actor_id=actor_id)
        if row is None:
            return False
        request, browser = row
        now = datetime.now(UTC)
        return (
            lease.released_at is None and lease.expires_at > now
            and lease.generation == generation == browser.control_generation
            and browser.state == "open" and browser.control_mode == "human"
            and request.status == "leased"
            and request.expires_at is not None and request.expires_at > now
        )

    async def finish_verification(
        self,
        *,
        request_id: UUID,
        expected_generation: int,
        verified: bool,
    ) -> HumanActionRecord:
        result = await self._session.execute(
            select(HumanActionRequest, BrowserSession)
            .join(BrowserSession, BrowserSession.id == HumanActionRequest.browser_session_id)
            .where(HumanActionRequest.id == request_id)
            .with_for_update(of=(HumanActionRequest, BrowserSession))
        )
        row = result.one_or_none()
        if row is None:
            raise HumanActionNotAuthorizedError("The human action request is unavailable.")
        request, browser = row
        if (
            request.status != "leased"
            or browser.control_mode != "verifying"
            or browser.control_generation != expected_generation
        ):
            raise HumanActionConflictError("The browser verification state has changed.")
        if verified:
            request.status = "completed"
            request.completed_at = datetime.now(UTC)
            browser.control_mode = "agent"
            suspension_status = "ready"
        else:
            request.status = "cancelled"
            browser.control_mode = "none"
            suspension_status = "abandoned"
        suspension = await self._session.scalar(
            select(ExecutionSuspension)
            .where(
                ExecutionSuspension.pending_request_id == request.id,
                ExecutionSuspension.status == "waiting",
            )
            .with_for_update()
        )
        if suspension is not None:
            suspension.status = suspension_status
        await self._session.flush()
        return _request_record(request)

    async def expire_due(self, *, limit: int = 100) -> int:
        now = datetime.now(UTC)
        expired_lease_result = await self._session.execute(
            select(HumanActionRequest, BrowserSession)
            .join(HumanControlLease, HumanControlLease.request_id == HumanActionRequest.id)
            .join(BrowserSession, BrowserSession.id == HumanActionRequest.browser_session_id)
            .where(
                HumanControlLease.released_at.is_(None),
                HumanControlLease.expires_at <= now,
            )
            .order_by(HumanControlLease.expires_at)
            .limit(limit)
            .with_for_update(of=(HumanActionRequest, BrowserSession), skip_locked=True)
        )
        expired_lease_requests = expired_lease_result.unique().all()
        for request, browser in expired_lease_requests:
            lease_result = await self._session.execute(
                select(HumanControlLease)
                .where(
                    HumanControlLease.request_id == request.id,
                    HumanControlLease.released_at.is_(None),
                )
                .with_for_update()
            )
            for lease in lease_result.scalars().all():
                lease.released_at = now
            browser.control_generation += 1
            if request.status == "leased" and request.expires_at and request.expires_at > now:
                request.status = "pending"
                browser.control_mode = "human_pending"
            elif request.status == "leased":
                request.status = "expired"
                browser.control_mode = "none"
                await self._abandon_suspension(request.id)

        result = await self._session.execute(
            select(HumanActionRequest, BrowserSession)
            .join(BrowserSession, BrowserSession.id == HumanActionRequest.browser_session_id)
            .where(
                HumanActionRequest.status.in_(("pending", "leased")),
                HumanActionRequest.expires_at <= now,
            )
            .order_by(HumanActionRequest.expires_at)
            .limit(limit)
            .with_for_update(of=(HumanActionRequest, BrowserSession), skip_locked=True)
        )
        requests = result.unique().all()
        for request, browser in requests:
            lease_result = await self._session.execute(
                select(HumanControlLease).where(
                    HumanControlLease.request_id == request.id,
                    HumanControlLease.released_at.is_(None),
                ).with_for_update()
            )
            for lease in lease_result.scalars().all():
                lease.released_at = now
            browser.control_generation += 1
            browser.control_mode = "none"
            request.status = "expired"
            await self._abandon_suspension(request.id)
        await self._session.flush()
        return len(requests) + len(expired_lease_requests)

    async def cancel(self, *, request_id: UUID, actor_id: UUID) -> HumanActionRecord:
        return await self._stop_request(
            request_id=request_id, actor_id=actor_id, terminal_status="cancelled",
        )

    async def skip(self, *, request_id: UUID, actor_id: UUID) -> HumanActionRecord:
        """Abandon only the waiting work item, fencing live human control once."""
        return await self._stop_request(
            request_id=request_id, actor_id=actor_id, terminal_status="skipped",
        )

    async def _stop_request(
        self, *, request_id: UUID, actor_id: UUID, terminal_status: str,
    ) -> HumanActionRecord:
        row = await self._lock_operator_request(request_id=request_id, actor_id=actor_id)
        if row is None:
            raise HumanActionNotAuthorizedError("Human control is not authorized for this request.")
        request, browser = row
        if request.status == "skipped" and terminal_status == "skipped":
            return _request_record(request)
        if request.status not in {"pending", "leased"}:
            raise HumanActionConflictError("The human action request is no longer active.")
        now = datetime.now(UTC)
        if terminal_status == "skipped" and request.expires_at and request.expires_at <= now:
            raise HumanActionExpiredError("The human action request has expired.")
        lease_result = await self._session.execute(
            select(HumanControlLease).where(
                HumanControlLease.request_id == request.id,
                HumanControlLease.released_at.is_(None),
            ).with_for_update()
        )
        for lease in lease_result.scalars().all():
            lease.released_at = now
        browser.control_generation += 1
        browser.control_mode = "none"
        request.status = terminal_status
        request.terminal_generation = browser.control_generation
        await self._abandon_suspension(request.id)
        await self._session.flush()
        return _request_record(request)

    async def _abandon_suspension(self, request_id: UUID) -> None:
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
