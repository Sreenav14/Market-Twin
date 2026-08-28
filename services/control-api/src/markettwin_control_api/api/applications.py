"""Application HTTP endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import (
    get_authenticated_user_id,
)
from markettwin_control_api.api.permissions import (
    WORKSPACE_WRITE_ROLES,
)
from markettwin_control_api.persistence.repositories import (
    ApplicationRecord,
    ApplicationRepository,
    WorkspaceAccess,
    WorkspaceRepository,
)

router = APIRouter(
    tags=["Applications"],
)


class CreateApplicationRequest(BaseModel):
    """Request for creating a MarketTwin application."""

    name: str = Field(
        min_length=1,
        max_length=200,
    )

    description: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(
        cls,
        value: str,
    ) -> str:
        """Reject empty or whitespace-only names."""

        cleaned = value.strip()

        if not cleaned:
            raise ValueError(
                "Application name is required."
            )

        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(
        cls,
        value: str | None,
    ) -> str | None:
        """Normalize an optional description."""

        if value is None:
            return None

        cleaned = value.strip()

        return cleaned or None


class ApplicationResponse(BaseModel):
    """Application returned to the frontend."""

    id: UUID
    workspace_id: UUID
    created_by_user_id: UUID
    name: str
    description: str | None
    status: str


def application_response(
    application: ApplicationRecord,
) -> ApplicationResponse:
    """Convert repository data into an HTTP response."""

    return ApplicationResponse(
        id=application.application_id,
        workspace_id=application.workspace_id,
        created_by_user_id=application.created_by_user_id,
        name=application.name,
        description=application.description,
        status=application.status,
    )


async def require_workspace_access(
    *,
    database_session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
) -> WorkspaceAccess:
    """Require membership in an active workspace."""

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

    return workspace


@router.post(
    "/api/v1/workspaces/{workspace_id}/applications",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application(
    workspace_id: UUID,
    payload: CreateApplicationRequest,
    request: Request,
) -> ApplicationResponse:
    """Create an application inside an accessible workspace."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            workspace = await require_workspace_access(
                database_session=database_session,
                workspace_id=workspace_id,
                user_id=user_id,
            )

            if workspace.role not in WORKSPACE_WRITE_ROLES:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Your workspace role cannot "
                        "create applications."
                    ),
                )

            repository = ApplicationRepository(
                database_session
            )

            application = await repository.create(
                workspace_id=workspace_id,
                created_by_user_id=user_id,
                name=payload.name,
                description=payload.description,
            )

    return application_response(application)


@router.get(
    "/api/v1/workspaces/{workspace_id}/applications",
    response_model=list[ApplicationResponse],
)
async def list_applications(
    workspace_id: UUID,
    request: Request,
) -> list[ApplicationResponse]:
    """List applications in an accessible workspace."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            await require_workspace_access(
                database_session=database_session,
                workspace_id=workspace_id,
                user_id=user_id,
            )

            repository = ApplicationRepository(
                database_session
            )

            applications = await repository.list_for_workspace(
                workspace_id=workspace_id
            )

    return [
        application_response(application)
        for application in applications
    ]


@router.get(
    "/api/v1/applications/{application_id}",
    response_model=ApplicationResponse,
)
async def get_application(
    application_id: UUID,
    request: Request,
) -> ApplicationResponse:
    """Return an application available to the current user."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            repository = ApplicationRepository(
                database_session
            )

            application = await repository.get_for_user(
                application_id=application_id,
                user_id=user_id,
            )

    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    return application_response(application)