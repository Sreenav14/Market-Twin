"""Shared HTTP authentication dependencies."""

from uuid import UUID

from fastapi import HTTPException, Request, status

from markettwin_control_api.api.auth import (
    SESSION_COOKIE_NAME,
    create_session_service,
    get_database_runtime,
)


async def get_authenticated_user_id(
    *,
    request: Request,
) -> UUID:
    """Return the authenticated MarketTwin user ID."""

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

            return user_session.user_id