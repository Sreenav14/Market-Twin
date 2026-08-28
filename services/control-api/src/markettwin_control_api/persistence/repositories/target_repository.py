"""Persistence operations for application targets."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.persistence.models import (
    Application,
    ApplicationTarget,
    TargetAllowedOrigin,
    Workspace,
    WorkspaceMember,
)


@dataclass(frozen=True, slots=True)
class AllowedOriginRecord:
    """A browser origin allowed for a target."""

    scheme: str
    hostname: str
    port: int | None
    include_subdomains: bool


@dataclass(frozen=True, slots=True)
class TargetRecord:
    """Application target returned by the repository."""

    target_id: UUID
    application_id: UUID
    name: str
    environment: str
    base_url: str
    requires_auth: bool
    status: str
    allowed_origins: tuple[AllowedOriginRecord, ...]


def _origin_record(
    origin: TargetAllowedOrigin,
) -> AllowedOriginRecord:
    return AllowedOriginRecord(
        scheme=origin.scheme,
        hostname=origin.hostname,
        port=origin.port,
        include_subdomains=origin.include_subdomains,
    )


class TargetRepository:
    """Database access for application targets."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def create(
        self,
        *,
        application_id: UUID,
        name: str,
        environment: str,
        base_url: str,
        requires_auth: bool,
        scheme: str,
        hostname: str,
        port: int | None,
    ) -> TargetRecord:
        """Create a target with its initial allowed origin."""

        target = ApplicationTarget(
            application_id=application_id,
            name=name,
            environment=environment,
            base_url=base_url,
            requires_auth=requires_auth,
            status="active",
        )

        self._session.add(target)
        await self._session.flush()

        origin = TargetAllowedOrigin(
            target_id=target.id,
            scheme=scheme,
            hostname=hostname,
            port=port,
            include_subdomains=False,
        )

        self._session.add(origin)
        await self._session.flush()

        return TargetRecord(
            target_id=target.id,
            application_id=target.application_id,
            name=target.name,
            environment=target.environment,
            base_url=target.base_url,
            requires_auth=target.requires_auth,
            status=target.status,
            allowed_origins=(
                _origin_record(origin),
            ),
        )

    async def list_for_application(
        self,
        *,
        application_id: UUID,
    ) -> list[TargetRecord]:
        """List active targets belonging to an application."""

        target_statement = (
            select(ApplicationTarget)
            .where(
                ApplicationTarget.application_id
                == application_id,
                ApplicationTarget.status == "active",
                ApplicationTarget.deleted_at.is_(None),
            )
            .order_by(ApplicationTarget.created_at)
        )

        target_result = await self._session.execute(
            target_statement
        )

        targets = list(
            target_result.scalars().all()
        )

        if not targets:
            return []

        target_ids = [
            target.id
            for target in targets
        ]

        origin_statement = (
            select(TargetAllowedOrigin)
            .where(
                TargetAllowedOrigin.target_id.in_(
                    target_ids
                )
            )
        )

        origin_result = await self._session.execute(
            origin_statement
        )

        origins_by_target: dict[
            UUID,
            list[AllowedOriginRecord],
        ] = {
            target_id: []
            for target_id in target_ids
        }

        for origin in origin_result.scalars().all():
            origins_by_target[origin.target_id].append(
                _origin_record(origin)
            )

        return [
            TargetRecord(
                target_id=target.id,
                application_id=target.application_id,
                name=target.name,
                environment=target.environment,
                base_url=target.base_url,
                requires_auth=target.requires_auth,
                status=target.status,
                allowed_origins=tuple(
                    origins_by_target[target.id]
                ),
            )
            for target in targets
        ]

    async def get_for_user(
        self,
        *,
        target_id: UUID,
        user_id: UUID,
    ) -> TargetRecord | None:
        """Return a target only when the user has workspace access."""

        statement = (
            select(ApplicationTarget)
            .join(
                Application,
                Application.id
                == ApplicationTarget.application_id,
            )
            .join(
                Workspace,
                Workspace.id
                == Application.workspace_id,
            )
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id
                == Workspace.id,
            )
            .where(
                ApplicationTarget.id == target_id,
                WorkspaceMember.user_id == user_id,
                ApplicationTarget.status == "active",
                ApplicationTarget.deleted_at.is_(None),
                Application.status == "active",
                Application.deleted_at.is_(None),
                Workspace.status == "active",
                Workspace.deleted_at.is_(None),
            )
        )

        result = await self._session.execute(
            statement
        )

        target = result.scalar_one_or_none()

        if target is None:
            return None

        origin_statement = select(
            TargetAllowedOrigin
        ).where(
            TargetAllowedOrigin.target_id == target.id
        )

        origin_result = await self._session.execute(
            origin_statement
        )

        origins = tuple(
            _origin_record(origin)
            for origin
            in origin_result.scalars().all()
        )

        return TargetRecord(
            target_id=target.id,
            application_id=target.application_id,
            name=target.name,
            environment=target.environment,
            base_url=target.base_url,
            requires_auth=target.requires_auth,
            status=target.status,
            allowed_origins=origins,
        )