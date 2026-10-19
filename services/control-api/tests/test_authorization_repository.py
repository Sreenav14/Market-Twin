"""Retained authorization history must never reactivate after revocation."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from markettwin_control_api.persistence.models import TargetAuthorization
from markettwin_control_api.persistence.repositories.authorization_repository import (
    TargetAuthorizationRepository,
)
from sqlalchemy import Result, Table, create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.sql import Executable


class SessionAdapter:
    """Use an in-memory SQL database for repository behavior without external writes."""

    def __init__(self, session: Session) -> None:
        self.session = session

    async def execute(self, statement: Executable) -> Result[Any]:
        return self.session.execute(statement)

    async def flush(self) -> None:
        self.session.flush()

    def add(self, record: object) -> None:
        self.session.add(record)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        execution_options={
            "schema_translate_map": {"testing": None, "core": None},
        },
    )
    cast(Table, TargetAuthorization.__table__).create(engine)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def grant(target_id: UUID, *, age: int, expired: bool = False) -> TargetAuthorization:
    now = datetime.now(UTC)
    return TargetAuthorization(
        target_id=target_id,
        created_by_user_id=uuid4(),
        authorized_by_user_id=uuid4(),
        status="authorized",
        authorization_basis="Owned synthetic environment.",
        created_at=now - timedelta(days=age),
        authorized_at=now - timedelta(days=age),
        expires_at=now - timedelta(hours=1) if expired else None,
    )


async def test_revoke_retires_all_legacy_grants_without_reactivation(session: Session) -> None:
    target_id, other_target = uuid4(), uuid4()
    older, latest = grant(target_id, age=2), grant(target_id, age=1)
    expired, unrelated = grant(target_id, age=3, expired=True), grant(other_target, age=1)
    session.add_all([older, latest, expired, unrelated])
    session.flush()
    repository = TargetAuthorizationRepository(cast(AsyncSession, SessionAdapter(session)))
    active = await repository.get_active(target_id=target_id)
    assert active is not None and active.authorization_id == latest.id
    revoked = await repository.revoke(target_id=target_id)
    assert revoked is not None and revoked.authorization_id == latest.id
    assert await repository.get_active(target_id=target_id) is None
    for item in (older, latest, expired, unrelated):
        session.refresh(item)
    assert all(
        item.status == "revoked" and item.revoked_at is not None
        for item in (older, latest, expired)
    )
    assert all(
        item.authorization_basis == "Owned synthetic environment."
        for item in (older, latest, expired)
    )
    assert unrelated.status == "authorized" and unrelated.revoked_at is None


async def test_new_grant_retires_expired_grants_but_preserves_attestations(
    session: Session,
) -> None:
    target_id = uuid4()
    previous = grant(target_id, age=2, expired=True)
    previous_expiry = previous.expires_at
    session.add(previous)
    session.flush()
    previous_id = previous.id
    repository = TargetAuthorizationRepository(cast(AsyncSession, SessionAdapter(session)))
    assert await repository.get_active(target_id=target_id) is None
    current = await repository.authorize(
        target_id=target_id,
        user_id=uuid4(),
        authorization_basis="Freshly approved local environment.",
    )
    assert current.authorization_id != previous_id
    session.refresh(previous)
    assert previous.status == "revoked" and previous.revoked_at is not None
    assert previous.expires_at is not None and previous_expiry is not None
    assert previous.expires_at.replace(tzinfo=UTC) == previous_expiry
    assert session.get(TargetAuthorization, previous_id) is previous
    await repository.revoke(target_id=target_id)
    assert await repository.get_active(target_id=target_id) is None
