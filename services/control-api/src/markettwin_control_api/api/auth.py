"""Authentication HTTP endpoints."""

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.auth.providers.local import LocalAuthProvider
from markettwin_control_api.auth.services import (
    LocalAuthService,
    LocalIdentityNotApprovedError,
    SessionService,
)
from markettwin_control_api.config import get_settings
from markettwin_control_api.database import DatabaseRuntime
from markettwin_control_api.persistence.models import User
from markettwin_control_api.persistence.repositories import IdentityRepository

SESSION_COOKIE_NAME = "markettwin_session"


router = APIRouter(
    tags=["Authentication"],
)


class LocalLoginRequest(BaseModel):
    """Local-development login request."""

    email: str


class CurrentUserResponse(BaseModel):
    """Authenticated MarketTwin user returned to the frontend."""

    id: UUID
    email: str
    normalized_email: str
    display_name: str | None


def get_database_runtime(request: Request) -> DatabaseRuntime:
    """Return the Control API database runtime."""

    database = getattr(
        request.app.state,
        "database",
        None,
    )

    if not isinstance(database, DatabaseRuntime):
        raise RuntimeError(
            "Database runtime has not been initialized."
        )

    return database


def create_session_service(
    *,
    database_session: AsyncSession,
) -> SessionService:
    """Create the shared MarketTwin session service."""

    settings = get_settings()

    return SessionService(
        database_session=database_session,
        idle_timeout=timedelta(
            minutes=settings.session_idle_timeout_minutes
        ),
        absolute_timeout=timedelta(
            hours=settings.session_absolute_timeout_hours
        ),
    )


@router.post(
    "/api/v1/auth/local/login",
    response_model=CurrentUserResponse,
)
async def local_login(
    payload: LocalLoginRequest,
    request: Request,
    response: Response,
) -> CurrentUserResponse:
    """Log in using a pre-approved local development identity."""

    settings = get_settings()

    if settings.app_env != "local":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
        )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            identity_repository = IdentityRepository(
                database_session
            )

            auth_service = LocalAuthService(
                provider=LocalAuthProvider(
                    app_env=settings.app_env
                ),
                identity_repository=identity_repository,
            )

            try:
                identity = await auth_service.authenticate(
                    email=payload.email,
                )
            except LocalIdentityNotApprovedError as exc:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Local identity is not approved.",
                ) from exc

            session_service = create_session_service(
                database_session=database_session
            )

            raw_token = await session_service.create_session(
                user_id=identity.user_id,
                identity_id=identity.identity_id,
            )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
        max_age=(
            settings.session_absolute_timeout_hours
            * 60
            * 60
        ),
    )

    return CurrentUserResponse(
        id=identity.user_id,
        email=identity.email,
        normalized_email=identity.normalized_email,
        display_name=identity.display_name,
    )


@router.get(
    "/api/v1/me",
    response_model=CurrentUserResponse,
)
async def get_current_user(
    request: Request,
) -> CurrentUserResponse:
    """Return the currently authenticated MarketTwin user."""

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

            return CurrentUserResponse(
                id=user.id,
                email=user.email,
                normalized_email=user.normalized_email,
                display_name=user.display_name,
            )


@router.post(
    "/api/v1/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    request: Request,
    response: Response,
) -> None:
    """Revoke the current MarketTwin session."""

    raw_token = request.cookies.get(
        SESSION_COOKIE_NAME
    )

    if raw_token is not None:
        database = get_database_runtime(request)

        async with database.session_factory() as database_session:
            async with database_session.begin():
                session_service = create_session_service(
                    database_session=database_session
                )

                await session_service.revoke_session(
                    raw_token=raw_token
                )

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
    )