"""Pause API reports intent, never fabricates an acknowledged browser pause."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from markettwin_control_api.api import execution_pause
from markettwin_control_api.persistence.repositories.execution_pause_repository import PauseRejected


@pytest.fixture
def paused_api(monkeypatch):
    actor, run_id, browser_id = uuid4(), uuid4(), uuid4()
    pause = SimpleNamespace(id=uuid4(), status="requested", execution_id=uuid4(), journey_id=uuid4(),
        browser_session_id=browser_id, generation=0, human_request_id=None,
        created_at=datetime.now(UTC), expires_at=datetime.now(UTC) + timedelta(minutes=5),
        acknowledged_at=None, completed_at=None)
    repository = SimpleNamespace(request=AsyncMock(return_value=pause),
                                 resume=AsyncMock(return_value=pause))

    class Context:
        async def __aenter__(self):
            return SimpleNamespace(begin=Context)

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr(execution_pause, "get_database_runtime", lambda _: SimpleNamespace(
        session_factory=Context,
    ))
    monkeypatch.setattr(execution_pause, "ExecutionPauseRepository", lambda _: repository)
    monkeypatch.setattr(execution_pause, "get_authenticated_user_id", AsyncMock(return_value=actor))
    monkeypatch.setattr(execution_pause, "get_settings", lambda: SimpleNamespace(
        web_origin="http://localhost:5173",
    ))
    app = FastAPI()
    app.include_router(execution_pause.router)
    return SimpleNamespace(app=app, run_id=run_id, actor=actor, browser_id=browser_id,
                           pause=pause, repository=repository)


async def post(state, *, resume=False, headers=True, payload=None):
    suffix = f"/{state.pause.id}/resume" if resume else ""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=state.app),
                                 base_url="http://local") as client:
        return await client.post(
            f"/api/v1/test-runs/{state.run_id}/live-browser/pause{suffix}",
            headers={"Origin": "http://localhost:5173", "X-MarketTwin-Request": "1"}
            if headers else {},
            json=payload if payload is not None else None if resume else {
                "browser_session_id": str(state.browser_id), "generation": 0,
            },
        )


async def test_pause_202_means_requested_not_acknowledged(paused_api):
    response = await post(paused_api)
    assert response.status_code == 202
    assert response.json()["status"] == "requested"
    assert response.json()["acknowledged_at"] is None
    assert response.headers["cache-control"] == "no-store"
    assert "lease_token" not in response.text and "ticket" not in response.text
    paused_api.repository.request.assert_awaited_once_with(
        run_id=paused_api.run_id, actor_id=paused_api.actor,
        browser_session_id=paused_api.browser_id, generation=0,
    )


async def test_resume_202_means_resume_requested_not_resumed(paused_api):
    paused_api.pause.status = "resume_requested"
    response = await post(paused_api, resume=True)
    assert response.status_code == 202 and response.json()["status"] == "resume_requested"


@pytest.mark.parametrize("resume", [False, True])
async def test_pause_mutations_require_same_origin(paused_api, resume):
    response = await post(paused_api, resume=resume, headers=False)
    assert response.status_code == 403
    paused_api.repository.request.assert_not_awaited()
    paused_api.repository.resume.assert_not_awaited()


@pytest.mark.parametrize("status", [404, 409, 410])
async def test_rejected_pause_is_generic_and_does_not_grant_control(paused_api, status):
    paused_api.repository.request.side_effect = PauseRejected(status)
    response = await post(paused_api)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "Execution pause is unavailable."}


async def test_pause_cannot_supply_url_script_or_input(paused_api):
    response = await post(paused_api, payload={"browser_session_id": str(paused_api.browser_id),
        "generation": 0, "script": "SECRET_CANARY"})
    assert response.status_code == 422 and "SECRET_CANARY" not in response.text
    paused_api.repository.request.assert_not_awaited()


async def test_expired_cookie_cannot_pause_or_resume(paused_api, monkeypatch):
    monkeypatch.setattr(execution_pause, "get_authenticated_user_id", AsyncMock(
        side_effect=HTTPException(401, "Invalid or expired session."),
    ))
    for resume in (False, True):
        assert (await post(paused_api, resume=resume)).status_code == 401
    paused_api.repository.request.assert_not_awaited()
    paused_api.repository.resume.assert_not_awaited()
