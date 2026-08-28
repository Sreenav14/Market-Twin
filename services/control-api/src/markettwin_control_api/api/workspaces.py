"""Workspace HTTP endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from markettwin_control_api.api.auth import (
    SESSION_COOKIE_NAME,
    create_session_service,
    get_database_runtime,
)
from markettwin_control_api.api.dependencies import (
    get_authenticated_user_id,
)
from markettwin_control_api.persistence.models import User
from markettwin_control_api.persistence.repositories import (
    WorkspaceRepository,
)

router = APIRouter(
    prefix="/api/v1/workspaces",
    tags=["Workspaces"],
)


class WorkspaceResponse(BaseModel):
    """Workspace visible to the authenticated user."""

    id: UUID
    name: str
    status: str
    role: str


async def get_authenticated_user(
    *,
    request: Request,
) -> User:
    """Resolve the currently authenticated MarketTwin user."""

    raw_token = request.cookies.get(
        SESSION_COOKIE_NAME
    )

    if raw_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            session_service = create_session_service(
                database_session=database_session
            )

            user_session = await session_service.resolve_session(
                raw_token=raw_token
            )

            if user_session is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired session.",
                )

            user = await database_session.get(
                User,
                user_session.user_id,
            )

            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid session.",
                )

            return user


@router.get(
    "",
    response_model=list[WorkspaceResponse],
)
async def list_workspaces(
    request: Request,
) -> list[WorkspaceResponse]:
    """Return workspaces available to the current user."""

    user = await get_authenticated_user(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        repository = WorkspaceRepository(
            database_session
        )

        workspaces = await repository.list_for_user(
            user_id=user.id
        )

    return [
        WorkspaceResponse(
            id=workspace.workspace_id,
            name=workspace.name,
            status=workspace.status,
            role=workspace.role,
        )
        for workspace in workspaces
    ]


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
)
async def get_workspace(
    workspace_id: UUID,
    request: Request,
) -> WorkspaceResponse:
    """Return a workspace when the current user is a member."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        repository = WorkspaceRepository(
            database_session
        )

        workspace = await repository.get_for_user(
            workspace_id=workspace_id,
            user_id=user_id,
        )

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace access denied.",
        )

    return WorkspaceResponse(
        id=workspace.workspace_id,
        name=workspace.name,
        status=workspace.status,
        role=workspace.role,
    )