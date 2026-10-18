"""Skip uses operator authorization, durable state, and browser-generation fencing."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from markettwin_control_api.api import human_actions
from markettwin_control_api.persistence.repositories.human_action_repository import (
    HumanActionConflictError,
    HumanActionNotAuthorizedError,
)
from starlette.requests import Request


@pytest.mark.asyncio
@pytest.mark.parametrize("delivery_failed", [False, True])
async def test_skip_notifies_exact_durable_generation(monkeypatch, delivery_failed) -> None:
    actor_id, request_id = uuid4(), uuid4()
    record = SimpleNamespace(request_id=request_id, status="skipped", terminal_generation=7)
    repository = SimpleNamespace(skip=AsyncMock(return_value=record))

    @asynccontextmanager
    async def session_factory():
        yield SimpleNamespace(begin=session_factory)

    monkeypatch.setattr(human_actions, "_csrf", lambda request: None)
    monkeypatch.setattr(
        human_actions, "get_authenticated_user_id", AsyncMock(return_value=actor_id),
    )
    monkeypatch.setattr(human_actions, "get_database_runtime", lambda request: SimpleNamespace(
        session_factory=session_factory,
    ))
    monkeypatch.setattr(human_actions, "HumanActionRepository", lambda session: repository)
    live_generation = AsyncMock(return_value=900)
    monkeypatch.setattr(human_actions, "_get_request_generation", live_generation)
    worker = SimpleNamespace(notify=AsyncMock(
        side_effect=RuntimeError("Synthetic owner unavailable") if delivery_failed else None,
    ))
    monkeypatch.setattr(human_actions, "_worker_client", lambda: worker)
    result = await human_actions.skip_human_action(request_id, Request({"type": "http"}))
    assert result == {"id": str(request_id), "status": "skipped"}
    repository.skip.assert_awaited_once_with(request_id=request_id, actor_id=actor_id)
    live_generation.assert_not_awaited()
    worker.notify.assert_awaited_once_with(
        path="/internal/hitl/leases/revoke",
        payload={"request_id": str(request_id), "generation": 7},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("error,code", [
    (HumanActionNotAuthorizedError, 404), (HumanActionConflictError, 409),
])
async def test_skip_rejects_unauthorized_or_terminal_request(monkeypatch, error, code) -> None:
    @asynccontextmanager
    async def session_factory():
        yield SimpleNamespace(begin=session_factory)

    monkeypatch.setattr(human_actions, "_csrf", lambda request: None)
    monkeypatch.setattr(human_actions, "get_authenticated_user_id", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(human_actions, "get_database_runtime", lambda request: SimpleNamespace(
        session_factory=session_factory,
    ))
    monkeypatch.setattr(human_actions, "HumanActionRepository", lambda session: SimpleNamespace(
        skip=AsyncMock(side_effect=error("Synthetic rejection")),
    ))
    worker = AsyncMock()
    monkeypatch.setattr(human_actions, "_worker_client", worker)
    with pytest.raises(HTTPException) as caught:
        await human_actions.skip_human_action(uuid4(), Request({"type": "http"}))
    assert caught.value.status_code == code
    worker.assert_not_called()


@pytest.mark.asyncio
async def test_skip_requires_csrf_before_loading_actor(monkeypatch) -> None:
    actor = AsyncMock()
    monkeypatch.setattr(human_actions, "get_authenticated_user_id", actor)
    with pytest.raises(HTTPException) as caught:
        await human_actions.skip_human_action(uuid4(), Request({"type": "http", "headers": []}))
    assert caught.value.status_code == 403
    actor.assert_not_awaited()
