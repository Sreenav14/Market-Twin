"""Live PostgreSQL authority checks for the worker-hosted browser viewer."""

import hashlib
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from markettwin_database.models import (
    AgentExecution,
    ApplicationTarget,
    BrowserSession,
    HumanActionRequest,
    HumanControlLease,
    PersonaJourney,
    TargetAuthorization,
    TestRun,
    User,
    Workspace,
    WorkspaceMember,
)
from sqlalchemy import select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.owner import OwnerLease
from markettwin_execution_orchestrator.browser.owner_registry import BrowserOwnerRegistry


class DatabaseViewerAuthority:
    """Recheck user session, lease, workspace membership and target approval live."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        registry: BrowserOwnerRegistry,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry

    async def actor(self, session_cookie: str) -> UUID | None:
        if not session_cookie:
            return None
        token_hash = hashlib.sha256(session_cookie.encode("utf-8")).hexdigest()
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT u.id
                    FROM auth.user_sessions AS s
                    JOIN core.users AS u ON u.id = s.user_id
                    WHERE s.session_token_hash = :token_hash
                      AND s.revoked_at IS NULL
                      AND s.idle_expires_at > :now
                      AND s.absolute_expires_at > :now
                      AND u.status = 'active'
                      AND u.deleted_at IS NULL
                    LIMIT 1
                """),
                {"token_hash": token_hash, "now": now},
            )
            actor_id = result.scalar_one_or_none()
            return UUID(str(actor_id)) if actor_id is not None else None

    async def revoked_handle(
        self, *, generation: int, request_id: UUID | None,
        lease_id: UUID | None, session_id: UUID | None,
    ) -> tuple[BrowserSessionHandle, UUID, bool] | None:
        """Only a committed database transition may fence the live owner or wake it."""
        statement = (
            select(BrowserSession.id, BrowserSession.execution_id,
                   AgentExecution.journey_id, HumanActionRequest.id,
                   BrowserSession.control_mode, HumanActionRequest.status)
            .join(HumanActionRequest, HumanActionRequest.browser_session_id == BrowserSession.id)
            .join(AgentExecution, AgentExecution.id == HumanActionRequest.execution_id)
            .where(
                BrowserSession.control_generation == generation,
                BrowserSession.execution_id == HumanActionRequest.execution_id,
                BrowserSession.control_mode.in_(("verifying", "none", "agent", "human_pending")),
            )
        )
        if lease_id is not None:
            if session_id is None:
                return None
            statement = statement.join(
                HumanControlLease, HumanControlLease.request_id == HumanActionRequest.id,
            ).where(
                HumanControlLease.id == lease_id,
                HumanControlLease.browser_session_id == session_id,
                BrowserSession.id == session_id,
                HumanControlLease.released_at.is_not(None),
                HumanControlLease.generation < generation,
            )
        elif request_id is None:
            return None
        if request_id is not None:
            statement = statement.where(HumanActionRequest.id == request_id)
        async with self._session_factory() as session:
            row = (await session.execute(statement)).one_or_none()
        if row is None:
            return None
        browser_id, execution_id, journey_id, durable_request_id, mode, status = row
        try:
            return self._registry.handle(
                session_id=browser_id, execution_id=execution_id, journey_id=journey_id,
            ), durable_request_id, mode == "agent" and status == "completed"
        except Exception:
            return None

    async def permitted(self, actor_id: UUID, lease: OwnerLease) -> bool:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            statement = (
                select(HumanControlLease.id)
                .join(
                    HumanActionRequest,
                    HumanActionRequest.id == HumanControlLease.request_id,
                )
                .join(
                    BrowserSession,
                    BrowserSession.id == HumanControlLease.browser_session_id,
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
                .join(ApplicationTarget, ApplicationTarget.id == TestRun.target_id)
                .join(
                    TargetAuthorization,
                    TargetAuthorization.target_id == ApplicationTarget.id,
                )
                .join(User, User.id == actor_id)
                .where(
                    HumanControlLease.id == lease.lease_id,
                    HumanControlLease.request_id == lease.request_id,
                    HumanControlLease.browser_session_id == lease.handle.session_id,
                    HumanControlLease.user_id == actor_id,
                    HumanControlLease.released_at.is_(None),
                    HumanControlLease.generation == lease.generation,
                    HumanControlLease.expires_at > now,
                    HumanActionRequest.id == lease.request_id,
                    HumanActionRequest.execution_id == lease.handle.execution_id,
                    HumanActionRequest.status == "leased",
                    HumanActionRequest.expires_at > now,
                    BrowserSession.execution_id == lease.handle.execution_id,
                    BrowserSession.control_generation == lease.generation,
                    BrowserSession.control_mode.in_(("human_pending", "human")),
                    BrowserSession.state == "open",
                    AgentExecution.journey_id == lease.handle.journey_id,
                    Workspace.status == "active",
                    Workspace.deleted_at.is_(None),
                    WorkspaceMember.role.in_(("owner", "admin")),
                    ApplicationTarget.status == "active",
                    ApplicationTarget.deleted_at.is_(None),
                    TargetAuthorization.status == "authorized",
                    TargetAuthorization.revoked_at.is_(None),
                    (TargetAuthorization.expires_at.is_(None))
                    | (TargetAuthorization.expires_at > now),
                    User.status == "active",
                    User.deleted_at.is_(None),
                )
                .limit(1)
            )
            return (await session.scalar(statement)) is not None

    async def refresh_lease(self, actor_id: UUID, lease_id: UUID) -> OwnerLease | None:
        async with self._session_factory() as session:
            row = await session.execute(
                select(
                    HumanControlLease.request_id,
                    HumanControlLease.browser_session_id,
                    HumanControlLease.generation,
                    HumanControlLease.expires_at,
                    BrowserSession.execution_id,
                    AgentExecution.journey_id,
                )
                .join(
                    BrowserSession,
                    BrowserSession.id == HumanControlLease.browser_session_id,
                )
                .join(
                    HumanActionRequest,
                    HumanActionRequest.id == HumanControlLease.request_id,
                )
                .join(AgentExecution, AgentExecution.id == HumanActionRequest.execution_id)
                .where(
                    HumanControlLease.id == lease_id,
                    HumanControlLease.user_id == actor_id,
                    HumanControlLease.released_at.is_(None),
                    HumanControlLease.expires_at > datetime.now(UTC),
                    HumanActionRequest.status == "leased",
                )
            )
            values = row.one_or_none()
        if values is None:
            return None
        request_id, session_id, generation, expires_at, execution_id, journey_id = values
        try:
            handle = self._registry.handle(
                session_id=session_id,
                execution_id=execution_id,
                journey_id=journey_id,
            )
        except Exception:
            return None
        lease = OwnerLease(
            handle=handle,
            actor_id=actor_id,
            lease_id=lease_id,
            generation=generation,
            expires_at=expires_at,
            request_id=request_id,
        )
        return lease if await self.permitted(actor_id, lease) else None

    async def validate_lease_token(self, lease: OwnerLease, token: str) -> bool:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        async with self._session_factory() as session:
            result = await session.scalar(
                select(HumanControlLease.id).where(
                    HumanControlLease.id == lease.lease_id,
                    HumanControlLease.request_id == lease.request_id,
                    HumanControlLease.browser_session_id == lease.handle.session_id,
                    HumanControlLease.user_id == lease.actor_id,
                    HumanControlLease.lease_token_hash == token_hash,
                    HumanControlLease.generation == lease.generation,
                    HumanControlLease.released_at.is_(None),
                    HumanControlLease.expires_at == lease.expires_at,
                )
            )
        return result is not None and await self.permitted(lease.actor_id, lease)

    async def activate_human(self, lease: OwnerLease) -> bool:
        """Persist the transition after local capture has been disabled."""

        if not await self.permitted(lease.actor_id, lease):
            return False
        async with self._session_factory() as session:
            async with session.begin():
                result = cast(
                    CursorResult[Any],
                    await session.execute(
                        update(BrowserSession)
                        .where(
                            BrowserSession.id == lease.handle.session_id,
                            BrowserSession.execution_id == lease.handle.execution_id,
                            BrowserSession.control_generation == lease.generation,
                            BrowserSession.control_mode.in_(("human_pending", "human")),
                            BrowserSession.state == "open",
                        )
                        .values(control_mode="human")
                    ),
                )
                updated = result.rowcount == 1
            return updated


__all__ = ["DatabaseViewerAuthority"]
