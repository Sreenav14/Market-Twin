"""Persistence operations for target authorizations."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.persistence.models import (
    TargetAuthorization,
)


@dataclass(frozen=True, slots=True)
class TargetAuthorizationRecord:
    """Authorization state for a MarketTwin target."""

    authorization_id: UUID
    target_id: UUID
    created_by_user_id: UUID
    authorized_by_user_id: UUID | None
    status: str
    authorization_basis: str
    created_at: datetime
    authorized_at: datetime | None
    revoked_at: datetime | None
    expires_at: datetime | None


def _to_record(
    authorization: TargetAuthorization,
) -> TargetAuthorizationRecord:
    """Convert an ORM model into repository data."""

    return TargetAuthorizationRecord(
        authorization_id=authorization.id,
        target_id=authorization.target_id,
        created_by_user_id=authorization.created_by_user_id,
        authorized_by_user_id=authorization.authorized_by_user_id,
        status=authorization.status,
        authorization_basis=authorization.authorization_basis,
        created_at=authorization.created_at,
        authorized_at=authorization.authorized_at,
        revoked_at=authorization.revoked_at,
        expires_at=authorization.expires_at,
    )


class TargetAuthorizationRepository:
    """Database operations for target authorization."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_latest(
        self,
        *,
        target_id: UUID,
    ) -> TargetAuthorizationRecord | None:
        """Return the newest authorization record."""

        statement = (
            select(TargetAuthorization)
            .where(
                TargetAuthorization.target_id == target_id
            )
            .order_by(
                TargetAuthorization.created_at.desc()
            )
            .limit(1)
        )

        result = await self._session.execute(statement)

        authorization = result.scalar_one_or_none()

        if authorization is None:
            return None

        return _to_record(authorization)

    async def get_active(
        self,
        *,
        target_id: UUID,
    ) -> TargetAuthorizationRecord | None:
        """Return a currently valid authorization."""

        now = datetime.now(UTC)

        statement = (
            select(TargetAuthorization)
            .where(
                TargetAuthorization.target_id == target_id,
                TargetAuthorization.status == "authorized",
                TargetAuthorization.revoked_at.is_(None),
                or_(
                    TargetAuthorization.expires_at.is_(None),
                    TargetAuthorization.expires_at > now,
                ),
            )
            .order_by(
                TargetAuthorization.created_at.desc()
            )
            .limit(1)
        )

        result = await self._session.execute(statement)

        authorization = result.scalar_one_or_none()

        if authorization is None:
            return None

        return _to_record(authorization)

    async def authorize(
        self,
        *,
        target_id: UUID,
        user_id: UUID,
        authorization_basis: str,
    ) -> TargetAuthorizationRecord:
        """Create an explicit authorization attestation."""

        now = datetime.now(UTC)

        authorization = TargetAuthorization(
            target_id=target_id,
            created_by_user_id=user_id,
            authorized_by_user_id=user_id,
            status="authorized",
            authorization_basis=authorization_basis,
            authorized_at=now,
            revoked_at=None,
            expires_at=None,
        )

        self._session.add(authorization)
        await self._session.flush()

        return _to_record(authorization)

    async def revoke(
        self,
        *,
        target_id: UUID,
    ) -> TargetAuthorizationRecord | None:
        """Revoke the current active authorization."""

        now = datetime.now(UTC)

        statement = (
            select(TargetAuthorization)
            .where(
                TargetAuthorization.target_id == target_id,
                TargetAuthorization.status == "authorized",
                TargetAuthorization.revoked_at.is_(None),
                or_(
                    TargetAuthorization.expires_at.is_(None),
                    TargetAuthorization.expires_at > now,
                ),
            )
            .order_by(
                TargetAuthorization.created_at.desc()
            )
            .limit(1)
        )

        result = await self._session.execute(statement)

        authorization = result.scalar_one_or_none()

        if authorization is None:
            return None

        authorization.status = "revoked"
        authorization.revoked_at = now

        await self._session.flush()

        return _to_record(authorization)