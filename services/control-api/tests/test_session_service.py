from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from markettwin_control_api.auth.services import SessionService
from markettwin_control_api.persistence.models import UserSession
from sqlalchemy.ext.asyncio import AsyncSession


def make_database_session() -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    session.flush = AsyncMock()

    return session


@pytest.mark.asyncio
async def test_create_session_stores_only_token_hash() -> None:
    database_session = make_database_session()

    service = SessionService(
        database_session=database_session,
        idle_timeout=timedelta(minutes=30),
        absolute_timeout=timedelta(hours=8),
    )

    raw_token = await service.create_session(
        user_id=uuid4(),
        identity_id=uuid4(),
    )

    assert raw_token
    assert len(raw_token) >= 32

    database_session.add.assert_called_once()

    stored_session = database_session.add.call_args.args[0]

    assert isinstance(stored_session, UserSession)

    assert stored_session.session_token_hash == service.hash_token(
        raw_token
    )

    assert stored_session.session_token_hash != raw_token
    assert len(stored_session.session_token_hash) == 64

    database_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_session_returns_active_session() -> None:
    database_session = make_database_session()

    now = datetime.now(UTC)

    stored_session = UserSession(
        user_id=uuid4(),
        identity_id=uuid4(),
        session_token_hash=SessionService.hash_token("secret-token"),
        last_seen_at=now,
        idle_expires_at=now + timedelta(minutes=10),
        absolute_expires_at=now + timedelta(hours=2),
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = stored_session

    database_session.execute = AsyncMock(
        return_value=result
    )

    service = SessionService(
        database_session=database_session,
        idle_timeout=timedelta(minutes=30),
        absolute_timeout=timedelta(hours=8),
    )

    resolved = await service.resolve_session(
        raw_token="secret-token",
    )

    assert resolved is not None
    assert resolved is stored_session

    assert resolved.last_seen_at >= now
    assert (
        resolved.idle_expires_at
        <= resolved.absolute_expires_at
    )


@pytest.mark.asyncio
async def test_resolve_session_returns_none_when_not_found() -> None:
    database_session = make_database_session()

    result = MagicMock()
    result.scalar_one_or_none.return_value = None

    database_session.execute = AsyncMock(
        return_value=result
    )

    service = SessionService(
        database_session=database_session,
        idle_timeout=timedelta(minutes=30),
        absolute_timeout=timedelta(hours=8),
    )

    resolved = await service.resolve_session(
        raw_token="unknown-token",
    )

    assert resolved is None


@pytest.mark.asyncio
async def test_revoke_session_marks_session_revoked() -> None:
    database_session = make_database_session()

    now = datetime.now(UTC)

    stored_session = UserSession(
        user_id=uuid4(),
        identity_id=uuid4(),
        session_token_hash=SessionService.hash_token("secret-token"),
        last_seen_at=now,
        idle_expires_at=now + timedelta(minutes=30),
        absolute_expires_at=now + timedelta(hours=8),
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = stored_session

    database_session.execute = AsyncMock(
        return_value=result
    )

    service = SessionService(
        database_session=database_session,
        idle_timeout=timedelta(minutes=30),
        absolute_timeout=timedelta(hours=8),
    )

    revoked = await service.revoke_session(
        raw_token="secret-token",
    )

    assert revoked is True
    assert stored_session.revoked_at is not None


def test_session_service_rejects_invalid_timeouts() -> None:
    database_session = make_database_session()

    with pytest.raises(ValueError):
        SessionService(
            database_session=database_session,
            idle_timeout=timedelta(hours=9),
            absolute_timeout=timedelta(hours=8),
        )