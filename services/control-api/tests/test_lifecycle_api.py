"""Deletion authorization and dependency regression tests."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Request
from markettwin_control_api.api import lifecycle
from markettwin_control_api.database import DatabaseRuntime
from markettwin_control_api.persistence.models import (
    Application,
    ApplicationTarget,
    TestRun,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

type Entity = Application | ApplicationTarget | TestRun
type EntityModel = type[Application] | type[ApplicationTarget] | type[TestRun]


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


def setup(
    monkeypatch: pytest.MonkeyPatch,
    entity: Entity,
    role: str = "owner",
    *,
    absent: bool = False,
    scalar_values: tuple[UUID | None, ...] = (),
) -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    session.begin.return_value = AsyncContext(None)
    result = MagicMock()
    result.one_or_none.return_value = None if absent else (entity, role)
    session.execute = AsyncMock(return_value=result)
    session.scalar = AsyncMock(side_effect=list(scalar_values))
    session.delete = AsyncMock()
    session.flush = AsyncMock()

    def get_database_runtime(_request: Request) -> DatabaseRuntime:
        runtime = SimpleNamespace(
            session_factory=MagicMock(return_value=AsyncContext(session)),
        )
        return cast(DatabaseRuntime, runtime)

    monkeypatch.setattr(
        lifecycle,
        "get_authenticated_user_id",
        AsyncMock(return_value=uuid4()),
    )
    monkeypatch.setattr(
        lifecycle,
        "get_database_runtime",
        get_database_runtime,
    )
    return session


def request() -> Request:
    return Request({"type": "http", "method": "DELETE", "path": "/", "headers": []})


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["member", "viewer"])
async def test_non_admin_cannot_delete(
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    entity = TestRun(id=uuid4(), status="draft")
    session = setup(monkeypatch, entity, role)
    with pytest.raises(HTTPException) as error:
        await lifecycle.delete_resource(request(), entity.id, TestRun)
    assert error.value.status_code == 403
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_foreign_workspace_item_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity = TestRun(id=uuid4(), status="draft")
    session = setup(monkeypatch, entity, absent=True)
    with pytest.raises(HTTPException) as error:
        await lifecycle.delete_resource(request(), entity.id, TestRun)
    assert error.value.status_code == 404
    sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "workspace_members.user_id =" in sql
    assert "FOR UPDATE OF test_runs" in sql
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["planning", "queued", "running", "completed"])
async def test_started_or_completed_test_cannot_be_deleted(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    entity = TestRun(id=uuid4(), status=state)
    session = setup(monkeypatch, entity)
    with pytest.raises(HTTPException) as error:
        await lifecycle.delete_resource(request(), entity.id, TestRun)
    assert error.value.status_code == 409
    assert "retained" in error.value.detail
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["failed", "cancelled"])
async def test_aborted_test_can_be_deleted(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    entity = TestRun(id=uuid4(), status=state)
    session = setup(monkeypatch, entity)
    response = await lifecycle.delete_resource(request(), entity.id, TestRun)
    assert response.status_code == 204
    session.delete.assert_awaited_once_with(entity)


@pytest.mark.asyncio
async def test_draft_test_with_persisted_journey_cannot_be_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity = TestRun(id=uuid4(), status="draft")
    session = setup(monkeypatch, entity, scalar_values=(uuid4(),))
    with pytest.raises(HTTPException) as error:
        await lifecycle.delete_resource(request(), entity.id, TestRun)
    assert error.value.status_code == 409
    assert "already started" in error.value.detail
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("model", [ApplicationTarget, Application])
async def test_parent_with_tests_cannot_be_deleted(
    monkeypatch: pytest.MonkeyPatch,
    model: EntityModel,
) -> None:
    entity = model(id=uuid4())
    session = setup(monkeypatch, entity, scalar_values=(uuid4(),))
    with pytest.raises(HTTPException) as error:
        await lifecycle.delete_resource(request(), entity.id, model)
    assert error.value.status_code == 409
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model,state,scalar_values",
    [
        (TestRun, "draft", (None,)),
        (ApplicationTarget, "active", (None,)),
        (Application, "active", (None, None)),
    ],
)
async def test_authorized_delete_removes_database_entity(
    monkeypatch: pytest.MonkeyPatch,
    model: EntityModel,
    state: str,
    scalar_values: tuple[UUID | None, ...],
) -> None:
    entity = model(id=uuid4(), status=state)
    session = setup(monkeypatch, entity, scalar_values=scalar_values)
    response = await lifecycle.delete_resource(request(), entity.id, model)
    assert response.status_code == 204
    session.delete.assert_awaited_once_with(entity)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_dependency_returns_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity = ApplicationTarget(id=uuid4())
    session = setup(monkeypatch, entity, scalar_values=(None,))
    session.flush.side_effect = IntegrityError("DELETE", {}, Exception("foreign key"))
    with pytest.raises(HTTPException) as error:
        await lifecycle.delete_resource(request(), entity.id, ApplicationTarget)
    assert error.value.status_code == 409
