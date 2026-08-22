"""Persistence operations for authentication identities."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.persistence.models import User, UserIdentity


@dataclass(frozen=True, slots=True)
class ResolvedIdentity:
    """An authentication identity resolved to an active MarketTwin user."""

    identity_id: UUID
    user_id: UUID
    email: str
    normalized_email: str
    display_name: str | None


class IdentityRepository:
    """Database access for authentication identities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_active_identity(
        self,
        *,
        issuer: str,
        subject: str,
    ) -> ResolvedIdentity | None:
        """Resolve an identity to an active MarketTwin user."""

        statement = (
            select(UserIdentity, User)
            .join(
                User,
                User.id == UserIdentity.user_id,
            )
            .where(
                UserIdentity.issuer == issuer,
                UserIdentity.subject == subject,
                User.status == "active",
                User.deleted_at.is_(None),
            )
        )

        result = await self._session.execute(statement)
        row = result.one_or_none()

        if row is None:
            return None

        identity, user = row

        return ResolvedIdentity(
            identity_id=identity.id,
            user_id=user.id,
            email=user.email,
            normalized_email=user.normalized_email,
            display_name=user.display_name,
        )