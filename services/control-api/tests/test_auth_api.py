"""Test the authentication HTTP endpoints."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from httpx import Cookies, Response
from markettwin_control_api.api import auth as auth_api
from markettwin_control_api.auth.services import SessionService
from markettwin_control_api.database import DatabaseRuntime
from markettwin_control_api.main import app
from markettwin_control_api.persistence.models import (
    User,
    UserIdentity,
    UserSession,
)
from sqlalchemy.ext.asyncio import AsyncSession


class AsyncContext:
    """Minimal asynchronous context manager for mocked sessions."""

    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> bool:
        return False


def make_database(
    session: MagicMock,
) -> SimpleNamespace:
    """Create a mocked database runtime."""

    return SimpleNamespace(
        session_factory=MagicMock(return_value=AsyncContext(session)),
    )


def make_database_session() -> MagicMock:
    """Create a mocked SQLAlchemy async session."""

    session = MagicMock(spec=AsyncSession)

    session.begin.return_value = AsyncContext(None)
    session.flush = AsyncMock()

    return session


def local_settings() -> SimpleNamespace:
    """Return local authentication settings for endpoint tests."""

    return SimpleNamespace(
        app_env="local",
        session_idle_timeout_minutes=30,
        session_absolute_timeout_hours=8,
    )


def patch_database(
    monkeypatch: pytest.MonkeyPatch,
    session: MagicMock,
) -> None:
    """Make authentication endpoints use the mocked database."""

    database = make_database(session)

    def get_database_runtime(_request: Request) -> DatabaseRuntime:
        return cast(DatabaseRuntime, database)

    monkeypatch.setattr(
        auth_api,
        "get_database_runtime",
        get_database_runtime,
    )

    monkeypatch.setattr(
        auth_api,
        "get_settings",
        local_settings,
    )


def test_local_login_sets_opaque_http_only_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approved local login should create a server-side session."""

    user_id = uuid4()
    identity_id = uuid4()

    identity = UserIdentity(
        id=identity_id,
        user_id=user_id,
        issuer="markettwin-local",
        subject="user@example.com",
    )

    user = User(
        id=user_id,
        email="User@Example.com",
        normalized_email="user@example.com",
        display_name="Test User",
        status="active",
        deleted_at=None,
    )

    result = MagicMock()
    result.one_or_none.return_value = (
        identity,
        user,
    )

    session = make_database_session()
    session.execute = AsyncMock(return_value=result)

    patch_database(
        monkeypatch,
        session,
    )

    with TestClient(app) as client:
        response = cast(
            Response,
            client.post(  # pyright: ignore[reportUnknownMemberType]
                "/api/v1/auth/local/login",
                json={
                    "email": "User@Example.com",
                },
            ),
        )

        cookies = cast(
            Cookies,
            client.cookies,  # pyright: ignore[reportUnknownMemberType]
        )
        raw_token = cookies.get(auth_api.SESSION_COOKIE_NAME)

    assert response.status_code == 200

    assert response.json() == {
        "id": str(user_id),
        "email": "User@Example.com",
        "normalized_email": "user@example.com",
        "display_name": "Test User",
    }

    assert raw_token is not None

    set_cookie = response.headers["set-cookie"].lower()

    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "secure" not in set_cookie

    stored_sessions = [
        call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], UserSession)
    ]

    assert len(stored_sessions) == 1

    stored_session = stored_sessions[0]

    assert stored_session.session_token_hash == (SessionService.hash_token(raw_token))

    assert stored_session.session_token_hash != raw_token


def test_local_login_rejects_unapproved_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown local identities must not be allowed to log in."""

    result = MagicMock()
    result.one_or_none.return_value = None

    session = make_database_session()
    session.execute = AsyncMock(return_value=result)

    patch_database(
        monkeypatch,
        session,
    )

    with TestClient(app) as client:
        response = cast(
            Response,
            client.post(  # pyright: ignore[reportUnknownMemberType]
                "/api/v1/auth/local/login",
                json={
                    "email": "unknown@example.com",
                },
            ),
        )

    assert response.status_code == 403

    assert response.json() == {"detail": "Local identity is not approved."}

    session.add.assert_not_called()


def test_me_returns_authenticated_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid session cookie should resolve the current user."""

    raw_token = "test-session-token"

    user_id = uuid4()
    identity_id = uuid4()

    now = datetime.now(UTC)

    user_session = UserSession(
        user_id=user_id,
        identity_id=identity_id,
        session_token_hash=SessionService.hash_token(raw_token),
        last_seen_at=now,
        idle_expires_at=now + timedelta(minutes=30),
        absolute_expires_at=now + timedelta(hours=8),
    )

    user = User(
        id=user_id,
        email="user@example.com",
        normalized_email="user@example.com",
        display_name="Test User",
        status="active",
        deleted_at=None,
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = user_session

    session = make_database_session()
    session.execute = AsyncMock(return_value=result)
    session.get = AsyncMock(return_value=user)

    patch_database(
        monkeypatch,
        session,
    )

    with TestClient(app) as client:
        cookies = cast(
            Cookies,
            client.cookies,  # pyright: ignore[reportUnknownMemberType]
        )
        cookies.set(
            auth_api.SESSION_COOKIE_NAME,
            raw_token,
            domain="testserver.local",
            path="/",
        )

        response = cast(
            Response,
            client.get(  # pyright: ignore[reportUnknownMemberType]
                "/api/v1/me"
            ),
        )

    assert response.status_code == 200

    assert response.json() == {
        "id": str(user_id),
        "email": "user@example.com",
        "normalized_email": "user@example.com",
        "display_name": "Test User",
    }


def test_me_requires_session_cookie() -> None:
    """Requests without a session cookie must be rejected."""

    with TestClient(app) as client:
        response = cast(
            Response,
            client.get(  # pyright: ignore[reportUnknownMemberType]
                "/api/v1/me"
            ),
        )

    assert response.status_code == 401

    assert response.json() == {"detail": "Authentication required."}


def test_logout_revokes_session_and_clears_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Logout should revoke the DB session and remove the cookie."""

    raw_token = "test-session-token"

    now = datetime.now(UTC)

    user_session = UserSession(
        user_id=uuid4(),
        identity_id=uuid4(),
        session_token_hash=SessionService.hash_token(raw_token),
        last_seen_at=now,
        idle_expires_at=now + timedelta(minutes=30),
        absolute_expires_at=now + timedelta(hours=8),
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = user_session

    session = make_database_session()
    session.execute = AsyncMock(return_value=result)

    patch_database(
        monkeypatch,
        session,
    )

    with TestClient(app) as client:
        cookies = cast(
            Cookies,
            client.cookies,  # pyright: ignore[reportUnknownMemberType]
        )
        cookies.set(
            auth_api.SESSION_COOKIE_NAME,
            raw_token,
            domain="testserver.local",
            path="/",
        )

        logout_response = cast(
            Response,
            client.post(  # pyright: ignore[reportUnknownMemberType]
                "/api/v1/auth/logout"
            ),
        )

        assert cookies.get(auth_api.SESSION_COOKIE_NAME) is None

        me_response = cast(
            Response,
            client.get(  # pyright: ignore[reportUnknownMemberType]
                "/api/v1/me"
            ),
        )

    assert logout_response.status_code == 204

    assert user_session.revoked_at is not None

    assert me_response.status_code == 401
