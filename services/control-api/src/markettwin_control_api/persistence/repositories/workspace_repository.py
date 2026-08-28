""" Persistence operations for MarketTwin workspaces."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.persistence.models import Workspace, WorkspaceMember


@dataclass(frozen=True, slots=True)
class WorkspaceAccess:
    """Workspace access visible to a markettwin user."""
    
    workspace_id: UUID
    name: str
    status: str
    role: str
    
    
class WorkspaceRepository:
    """ Database access for workspace memebership."""
    
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session
        
    
    async def list_for_user(
        self,
        *,
        user_id: UUID,
    ) -> list[WorkspaceAccess]:
        """ Database access for workspace membership."""
        
        statement = (
            select(
                Workspace,
                WorkspaceMember,
            )
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id == Workspace.id,
            )
            .where(
                WorkspaceMember.user_id == user_id,
                Workspace.status == "active",
                Workspace.deleted_at.is_(None),
            )
            .order_by(Workspace.created_at)
        )
        
        result = await self._session.execute(statement)
        
        
        return [
            WorkspaceAccess(
                workspace_id=workspace.id,
                name=workspace.name,
                status=workspace.status,
                role=membership.role,
            )
            for workspace, membership in result.all()
        ]
        
    
    async def get_for_user(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
    ) -> WorkspaceAccess | None:
        """ Return a workspace only when the user is a member."""

        
        statement = (
            select(
                Workspace,
                WorkspaceMember,
            )
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id == workspace_id,
            )
            .where(
                Workspace.id == workspace_id,
                WorkspaceMember.user_id == user_id,
                Workspace.status == "active",
                Workspace.deleted_at.is_(None),
            )
        )

        result = await self._session.execute(statement)
        
        row = result.one_or_none()
        
        if row is None:
            return None
        
        workspace, membership = row
        
        return WorkspaceAccess(
            workspace_id=workspace_id,
            name=workspace.name,
            status = workspace.status,
            role=membership.role,
        )