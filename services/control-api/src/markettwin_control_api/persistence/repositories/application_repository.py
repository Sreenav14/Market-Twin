"""Persistence operations for MarketTwin applications."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.persistence.models import (
    Application,
    Workspace,
    WorkspaceMember,
)


@dataclass(frozen=True, slots=True)
class ApplicationRecord:
    """Application visible through the Control API."""

    application_id: UUID
    workspace_id: UUID
    created_by_user_id: UUID
    name: str
    description: str | None
    status: str


def _to_record(
    application: Application,
) -> ApplicationRecord:
    """Convert a persisted application into an API-safe record."""

    return ApplicationRecord(
        application_id=application.id,
        workspace_id=application.workspace_id,
        created_by_user_id=application.created_by_user_id,
        name=application.name,
        description=application.description,
        status=application.status,
    )


class ApplicationRepository:
    """Database access for MarketTwin applications."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def create(
        self,
        *,
        workspace_id: UUID,
        created_by_user_id: UUID,
        name: str,
        description: str | None,
    ) -> ApplicationRecord:
        """Create an active application."""

        application = Application(
            workspace_id=workspace_id,
            created_by_user_id=created_by_user_id,
            name=name,
            description=description,
            status="active",
        )

        self._session.add(application)
        await self._session.flush()

        return _to_record(application)

    async def list_for_workspace(
        self,
        *,
        workspace_id: UUID,
    ) -> list[ApplicationRecord]:
        """List active applications in a workspace."""

        statement = (
            select(Application)
            .where(
                Application.workspace_id == workspace_id,
                Application.status == "active",
                Application.deleted_at.is_(None),
            )
            .order_by(Application.created_at)
        )

        result = await self._session.execute(statement)

        return [
            _to_record(application)
            for application in result.scalars().all()
        ]

    async def get_for_user(
        self,
        *,
        application_id: UUID,
        user_id: UUID,
    ) -> ApplicationRecord | None:
        """Return an application only when the user has workspace access."""

        statement = (
            select(Application)
            .join(
                Workspace,
                Workspace.id == Application.workspace_id,
            )
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id
                == Application.workspace_id,
            )
            .where(
                Application.id == application_id,
                WorkspaceMember.user_id == user_id,
                Application.status == "active",
                Application.deleted_at.is_(None),
                Workspace.status == "active",
                Workspace.deleted_at.is_(None),
            )
        )

        result = await self._session.execute(statement)

        application = result.scalar_one_or_none()

        if application is None:
            return None

        return _to_record(application)