"""Authentication services."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.auth.providers.local import LocalAuthProvider
from markettwin_control_api.persistence.models import User, UserSession
from markettwin_control_api.persistence.repositories import (
    IdentityRepository,
    ResolvedIdentity,
)


class LocalIdentityNotApprovedError(RuntimeError):
    """The local identity was not approved."""


class LocalAuthService:
    """Service for authenticating local identities."""

    def __init__(
        self,
        *,
        provider: LocalAuthProvider,
        identity_repository: IdentityRepository,
    ) -> None:
        self._provider = provider
        self._identity_repository = identity_repository

    async def authenticate(
        self,
        *,
        email: str,
    ) -> ResolvedIdentity:
        """Authenticate an approved local MarketTwin user."""

        identity = await self._provider.authenticate(
            email=email,
        )

        resolved_identity = (
            await self._identity_repository.resolve_active_identity(
                issuer=identity.issuer,
                subject=identity.subject,
            )
        )

        if resolved_identity is None:
            raise LocalIdentityNotApprovedError(
                "The local identity was not approved."
            )

        return resolved_identity


class SessionService:
    """Manage server-side MarketTwin browser sessions."""

    def __init__(
        self,
        *,
        database_session: AsyncSession,
        idle_timeout: timedelta,
        absolute_timeout: timedelta,
    ) -> None:
        if idle_timeout <= timedelta(0):
            raise ValueError("Idle timeout must be positive.")

        if absolute_timeout <= timedelta(0):
            raise ValueError("Absolute timeout must be positive.")

        if idle_timeout > absolute_timeout:
            raise ValueError(
                "Idle timeout cannot exceed absolute timeout."
            )

        self._database_session = database_session
        self._idle_timeout = idle_timeout
        self._absolute_timeout = absolute_timeout

    @staticmethod
    def hash_token(token: str) -> str:
        """Return the SHA-256 hash used to identify a session."""

        return hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()

    async def create_session(
        self,
        *,
        user_id: UUID,
        identity_id: UUID,
    ) -> str:
        """Create a session and return the raw browser token."""

        now = datetime.now(UTC)

        raw_token = secrets.token_urlsafe(32)
        token_hash = self.hash_token(raw_token)

        absolute_expires_at = now + self._absolute_timeout
        idle_expires_at = min(
            now + self._idle_timeout,
            absolute_expires_at,
        )

        user_session = UserSession(
            user_id=user_id,
            identity_id=identity_id,
            session_token_hash=token_hash,
            last_seen_at=now,
            idle_expires_at=idle_expires_at,
            absolute_expires_at=absolute_expires_at,
        )

        self._database_session.add(user_session)

        await self._database_session.flush()

        return raw_token

    async def resolve_session(
        self,
        *,
        raw_token: str,
    ) -> UserSession | None:
        """Resolve an active browser session."""

        if not raw_token:
            return None

        now = datetime.now(UTC)
        token_hash = self.hash_token(raw_token)

        statement = (
            select(UserSession)
            .join(
                User,
                User.id == UserSession.user_id,
            )
            .where(
                UserSession.session_token_hash == token_hash,
                UserSession.revoked_at.is_(None),
                UserSession.idle_expires_at > now,
                UserSession.absolute_expires_at > now,
                User.status == "active",
                User.deleted_at.is_(None),
            )
        )

        result = await self._database_session.execute(statement)

        user_session = result.scalar_one_or_none()

        if user_session is None:
            return None

        user_session.last_seen_at = now
        user_session.idle_expires_at = min(
            now + self._idle_timeout,
            user_session.absolute_expires_at,
        )

        await self._database_session.flush()

        return user_session

    async def revoke_session(
        self,
        *,
        raw_token: str,
    ) -> bool:
        """Revoke a session if it exists."""

        if not raw_token:
            return False

        token_hash = self.hash_token(raw_token)

        statement = select(UserSession).where(
            UserSession.session_token_hash == token_hash,
        )

        result = await self._database_session.execute(statement)

        user_session = result.scalar_one_or_none()

        if user_session is None:
            return False

        if user_session.revoked_at is None:
            user_session.revoked_at = datetime.now(UTC)
            await self._database_session.flush()

        return True