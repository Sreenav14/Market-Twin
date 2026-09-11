"""Deletion authorization and dependency regression tests."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from markettwin_control_api.api import lifecycle
from markettwin_control_api.persistence.models import Application, ApplicationTarget, TestRun
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError


@asynccontextmanager
async def context(value=None):
    yield value


def setup(
    monkeypatch,
    entity,
    role="owner",
    *,
    absent=False,
    scalar_values=(),
    reports=(),
):
    session = SimpleNamespace(
        begin=lambda: context(),
        execute=AsyncMock(
            return_value=SimpleNamespace(one_or_none=lambda: None if absent else (entity, role))
        ),
        scalar=AsyncMock(side_effect=list(scalar_values)),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: list(reports))),
        delete=AsyncMock(),
        flush=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "get_authenticated_user_id", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(
        lifecycle,
        "get_database_runtime",
        lambda request: SimpleNamespace(session_factory=lambda: context(session)),
    )
    return session


def request():
    return Request({"type": "http", "method": "DELETE", "path": "/", "headers": []})


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["member", "viewer"])
async def test_non_admin_cannot_delete(monkeypatch, role):
    entity = TestRun(id=uuid4(), status="draft")
    session = setup(monkeypatch, entity, role)
    with pytest.raises(HTTPException) as error:
        await lifecycle.delete_resource(request(), entity.id, TestRun)
    assert error.value.status_code == 403
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_foreign_workspace_item_is_not_found(monkeypatch):
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
@pytest.mark.parametrize("state", ["planning", "queued", "running"])
async def test_active_test_cannot_be_deleted(monkeypatch, state):
    entity = TestRun(id=uuid4(), status=state)
    session = setup(monkeypatch, entity)
    with pytest.raises(HTTPException) as error:
        await lifecycle.delete_resource(request(), entity.id, TestRun)
    assert error.value.status_code == 409
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_test_with_stored_evidence_cannot_be_deleted(monkeypatch):
    entity = TestRun(id=uuid4(), status="completed")
    session = setup(monkeypatch, entity, scalar_values=(None, uuid4()), reports=("completed",))
    with pytest.raises(HTTPException) as error:
        await lifecycle.delete_resource(request(), entity.id, TestRun)
    assert error.value.status_code == 409
    assert "stored evidence" in error.value.detail
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("model", [ApplicationTarget, Application])
async def test_parent_with_tests_cannot_be_deleted(monkeypatch, model):
    entity = model(id=uuid4())
    session = setup(monkeypatch, entity, scalar_values=(uuid4(),))
    with pytest.raises(HTTPException) as error:
        await lifecycle.delete_resource(request(), entity.id, model)
    assert error.value.status_code == 409
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("reports", [(), ("generating",)])
async def test_pending_evaluation_cannot_be_deleted(monkeypatch, reports):
    entity = TestRun(id=uuid4(), status="completed")
    session = setup(monkeypatch, entity, scalar_values=(None, None), reports=reports)
    with pytest.raises(HTTPException) as error:
        await lifecycle.delete_resource(request(), entity.id, TestRun)
    assert error.value.status_code == 409
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_journey_blocks_deletion(monkeypatch):
    entity = TestRun(id=uuid4(), status="failed")
    session = setup(monkeypatch, entity, scalar_values=(uuid4(),))
    with pytest.raises(HTTPException) as error:
        await lifecycle.delete_resource(request(), entity.id, TestRun)
    assert error.value.status_code == 409
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model,state,scalar_values",
    [
        (TestRun, "draft", (None, None)),
        (TestRun, "completed", (None, None)),
        (TestRun, "failed", (None, None)),
        (TestRun, "cancelled", (None, None)),
        (ApplicationTarget, "active", (None,)),
        (Application, "active", (None, None)),
    ],
)
async def test_authorized_delete_removes_database_entity(monkeypatch, model, state, scalar_values):
    entity = model(id=uuid4(), status=state)
    session = setup(monkeypatch, entity, scalar_values=scalar_values, reports=("completed",))
    response = await lifecycle.delete_resource(request(), entity.id, model)
    assert response.status_code == 204
    session.delete.assert_awaited_once_with(entity)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_dependency_returns_conflict(monkeypatch):
    entity = ApplicationTarget(id=uuid4())
    session = setup(monkeypatch, entity, scalar_values=(None,))
    session.flush.side_effect = IntegrityError("DELETE", {}, Exception("foreign key"))
    with pytest.raises(HTTPException) as error:
        await lifecycle.delete_resource(request(), entity.id, ApplicationTarget)
    assert error.value.status_code == 409
