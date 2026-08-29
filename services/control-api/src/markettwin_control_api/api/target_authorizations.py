"""Target authorization HTTP endpoints."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    status,
)
from pydantic import (
    BaseModel,
    Field,
    field_validator,
)
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.api.auth import (
    get_database_runtime,
)
from markettwin_control_api.api.dependencies import (
    get_authenticated_user_id,
)
from markettwin_control_api.api.permissions import (
    TARGET_AUTHORIZATION_ROLES,
)
from markettwin_control_api.persistence.repositories import (
    ApplicationRepository,
    TargetAuthorizationRecord,
    TargetAuthorizationRepository,
    TargetRecord,
    TargetRepository,
    WorkspaceRepository,
)

router = APIRouter(
    tags=["Target Authorization"],
)


class AuthorizeTargetRequest(BaseModel):
    """Explicit authorization attestation."""

    confirm_authorized: Literal[True]

    authorization_basis: str = Field(
        min_length=10,
        max_length=2000,
    )

    @field_validator("authorization_basis")
    @classmethod
    def clean_authorization_basis(
        cls,
        value: str,
    ) -> str:
        """Normalize the authorization explanation."""

        cleaned = value.strip()

        if not cleaned:
            raise ValueError(
                "Authorization basis is required."
            )

        return cleaned


class TargetAuthorizationResponse(BaseModel):
    """Authorization state returned by the API."""

    id: UUID
    target_id: UUID
    created_by_user_id: UUID
    authorized_by_user_id: UUID | None
    status: str
    authorization_basis: str
    created_at: datetime
    authorized_at: datetime | None
    revoked_at: datetime | None
    expires_at: datetime | None


def authorization_response(
    authorization: TargetAuthorizationRecord,
) -> TargetAuthorizationResponse:
    """Convert repository data into an HTTP response."""

    return TargetAuthorizationResponse(
        id=authorization.authorization_id,
        target_id=authorization.target_id,
        created_by_user_id=(
            authorization.created_by_user_id
        ),
        authorized_by_user_id=(
            authorization.authorized_by_user_id
        ),
        status=authorization.status,
        authorization_basis=(
            authorization.authorization_basis
        ),
        created_at=authorization.created_at,
        authorized_at=authorization.authorized_at,
        revoked_at=authorization.revoked_at,
        expires_at=authorization.expires_at,
    )


async def require_target_access(
    *,
    database_session: AsyncSession,
    target_id: UUID,
    user_id: UUID,
) -> TargetRecord:
    """Require access to the target through workspace membership."""

    repository = TargetRepository(
        database_session
    )

    target = await repository.get_for_user(
        target_id=target_id,
        user_id=user_id,
    )

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target not found.",
        )

    return target


async def require_authorization_role(
    *,
    database_session: AsyncSession,
    target: TargetRecord,
    user_id: UUID,
) -> None:
    """Require owner/admin permission."""

    application_repository = ApplicationRepository(
        database_session
    )

    application = await application_repository.get_for_user(
        application_id=target.application_id,
        user_id=user_id,
    )

    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target not found.",
        )

    workspace_repository = WorkspaceRepository(
        database_session
    )

    workspace = await workspace_repository.get_for_user(
        workspace_id=application.workspace_id,
        user_id=user_id,
    )

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target not found.",
        )

    if workspace.role not in TARGET_AUTHORIZATION_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Your workspace role cannot "
                "authorize targets."
            ),
        )


@router.post(
    "/api/v1/targets/{target_id}/authorization",
    response_model=TargetAuthorizationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def authorize_target(
    target_id: UUID,
    payload: AuthorizeTargetRequest,
    request: Request,
) -> TargetAuthorizationResponse:
    """Authorize MarketTwin testing for a target."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            target = await require_target_access(
                database_session=database_session,
                target_id=target_id,
                user_id=user_id,
            )

            await require_authorization_role(
                database_session=database_session,
                target=target,
                user_id=user_id,
            )

            repository = TargetAuthorizationRepository(
                database_session
            )

            active = await repository.get_active(
                target_id=target_id
            )

            if active is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Target is already authorized.",
                )

            authorization = await repository.authorize(
                target_id=target_id,
                user_id=user_id,
                authorization_basis=(
                    payload.authorization_basis
                ),
            )

    return authorization_response(authorization)


@router.get(
    "/api/v1/targets/{target_id}/authorization",
    response_model=TargetAuthorizationResponse,
)
async def get_target_authorization(
    target_id: UUID,
    request: Request,
) -> TargetAuthorizationResponse:
    """Return the latest authorization state."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            await require_target_access(
                database_session=database_session,
                target_id=target_id,
                user_id=user_id,
            )

            repository = TargetAuthorizationRepository(
                database_session
            )

            authorization = await repository.get_latest(
                target_id=target_id
            )

    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target authorization not found.",
        )

    return authorization_response(authorization)


@router.post(
    "/api/v1/targets/{target_id}/authorization/revoke",
    response_model=TargetAuthorizationResponse,
)
async def revoke_target_authorization(
    target_id: UUID,
    request: Request,
) -> TargetAuthorizationResponse:
    """Revoke permission to test a target."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            target = await require_target_access(
                database_session=database_session,
                target_id=target_id,
                user_id=user_id,
            )

            await require_authorization_role(
                database_session=database_session,
                target=target,
                user_id=user_id,
            )

            repository = TargetAuthorizationRepository(
                database_session
            )

            authorization = await repository.revoke(
                target_id=target_id
            )

            if authorization is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Target is not currently authorized."
                    ),
                )

    return authorization_response(authorization)