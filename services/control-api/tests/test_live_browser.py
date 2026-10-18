"""Observation is authorized twice, read-only, bounded and never cached."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from markettwin_control_api.api import live_browser
from markettwin_control_api.persistence.repositories.live_browser_repository import (
    LiveBrowserRepository,
    decode_cursor,
)
from markettwin_control_api.services.hitl_worker_client import BrowserObservationUnavailable


@pytest.fixture
def observation(monkeypatch):
    run_id, actor, browser_id, execution_id, journey_id = (uuid4() for _ in range(5))
    browser = {"browser_session_id": browser_id, "execution_id": execution_id,
               "journey_id": journey_id, "generation": 0, "control_state": "agent",
               "viewer_state": "available", "journey_title": "Synthetic journey",
               "requesting_agent": "Synthetic tester"}
    repository = SimpleNamespace(
        authorized_run=AsyncMock(return_value=SimpleNamespace(id=run_id, status="running")),
        selected_browser=AsyncMock(return_value=browser),
        activity=AsyncMock(return_value={"items": [], "next_cursor": None}),
    )

    class Context:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr(live_browser, "get_authenticated_user_id", AsyncMock(return_value=actor))
    monkeypatch.setattr(live_browser, "get_database_runtime", lambda _: SimpleNamespace(
        session_factory=Context,
    ))
    monkeypatch.setattr(live_browser, "LiveBrowserRepository", lambda _: repository)
    monkeypatch.setattr(live_browser, "ExecutionPauseRepository", lambda _: SimpleNamespace(
        latest=AsyncMock(return_value=None),
    ))
    worker = SimpleNamespace(observe_frame=AsyncMock(return_value=b"\xff\xd8fixture\xff\xd9"))
    monkeypatch.setattr(live_browser, "worker_client", lambda: worker)
    monkeypatch.setattr(live_browser, "_frame_slots", asyncio.Semaphore(4))
    app = FastAPI()
    app.include_router(live_browser.router)
    return SimpleNamespace(app=app, run_id=run_id, actor=actor, browser=browser,
                           repository=repository, worker=worker)


async def call(state, suffix="", params=None, method="GET"):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=state.app),
                                 base_url="http://local") as client:
        return await client.request(
            method, f"/api/v1/test-runs/{state.run_id}/live-browser{suffix}", params=params,
        )


async def test_metadata_is_durable_identity_without_control_grant(observation):
    response = await call(observation)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["browser"]["browser_session_id"] == str(
        observation.browser["browser_session_id"],
    )
    assert "ticket" not in response.text and "lease" not in response.text
    observation.worker.observe_frame.assert_not_awaited()


async def test_no_open_browser_is_explicitly_null(observation):
    observation.repository.selected_browser.return_value = None
    assert (await call(observation)).json()["browser"] is None


async def test_unauthorized_run_hides_activity_and_frame(observation):
    observation.repository.authorized_run.return_value = None
    for suffix in ("", "/frame"):
        response = await call(observation, suffix, {
            "browser_session_id": observation.browser["browser_session_id"], "generation": 0,
        })
        assert response.status_code == 404
        assert response.headers["cache-control"] == "no-store"
    observation.repository.activity.assert_not_awaited()
    observation.worker.observe_frame.assert_not_awaited()


@pytest.mark.parametrize("change", [None, {"generation": 1}, {"viewer_state": "suppressed"}])
async def test_stale_closed_or_protected_browser_never_calls_worker(observation, change):
    observation.repository.selected_browser.return_value = (
        None if change is None else {**observation.browser, **change}
    )
    response = await call(observation, "/frame", {
        "browser_session_id": observation.browser["browser_session_id"], "generation": 0,
    })
    assert response.status_code == 409
    observation.worker.observe_frame.assert_not_awaited()


async def test_frame_binds_exact_identity_and_rechecks_after_capture(observation):
    response = await call(observation, "/frame", {
        "browser_session_id": observation.browser["browser_session_id"], "generation": 0,
    })
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"
    assert observation.repository.authorized_run.await_count == 2
    observation.worker.observe_frame.assert_awaited_once_with(
        actor_id=observation.actor,
        browser_session_id=observation.browser["browser_session_id"],
        execution_id=observation.browser["execution_id"],
        journey_id=observation.browser["journey_id"], generation=0,
    )


@pytest.mark.parametrize("race", ["authorization", "generation", "control", "closed"])
async def test_capture_races_discard_bytes(observation, race):
    run = observation.repository.authorized_run.return_value
    if race == "authorization":
        observation.repository.authorized_run.side_effect = [run, None]
    else:
        selection = (None if race == "closed" else {**observation.browser,
                     **({"generation": 1} if race == "generation"
                        else {"viewer_state": "suppressed", "control_state": "human"})})
        observation.repository.selected_browser.side_effect = [observation.browser, selection]
    response = await call(observation, "/frame", {
        "browser_session_id": observation.browser["browser_session_id"], "generation": 0,
    })
    assert response.status_code in {404, 409}
    assert b"fixture" not in response.content
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("failure,status", [
    (BrowserObservationUnavailable("private secret"), 409), (RuntimeError("private secret"), 503),
])
async def test_worker_failure_is_safe_and_not_a_product_failure(observation, failure, status):
    observation.worker.observe_frame.side_effect = failure
    response = await call(observation, "/frame", {
        "browser_session_id": observation.browser["browser_session_id"], "generation": 0,
    })
    assert response.status_code == status
    assert "secret" not in response.text
    assert response.headers["cache-control"] == "no-store"


async def test_no_input_endpoint_and_invalid_cursor_is_sanitized(observation):
    assert (await call(observation, method="POST")).status_code == 405
    response = await call(observation, "/frame", {"browser_session_id": "SECRET_CANARY"})
    assert response.status_code == 422
    assert "SECRET_CANARY" not in response.text
    observation.repository.activity.side_effect = ValueError("SECRET_CANARY")
    response = await call(observation, params={"cursor": "bad"})
    assert response.status_code == 422 and "SECRET_CANARY" not in response.text


@pytest.mark.parametrize("cursor", ["bad", "W10=", "e30=", "WyJiYWQiLCJzdGVwOjEiXQ=="])
def test_invalid_activity_cursor_fails_safely(cursor):
    with pytest.raises(ValueError, match="Invalid activity cursor"):
        decode_cursor(cursor)


async def test_authority_query_restricts_role_tenant_target_and_active_user():
    session = SimpleNamespace(scalar=AsyncMock(return_value=None))
    result = await LiveBrowserRepository(session).authorized_run(run_id=uuid4(), actor_id=uuid4())
    assert result is None
    sql = str(session.scalar.await_args.args[0])
    for required in ("workspace_members.role IN", "users.status", "users.deleted_at",
                     "workspaces.status", "application_targets.application_id",
                     "target_authorizations.revoked_at", "target_authorizations.expires_at"):
        assert required in sql


async def test_activity_is_redacted_stable_and_refreshed_without_a_watermark():
    run_id, execution_id, journey_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    step = SimpleNamespace(id=10, created_at=now, action_type="fill", status="running",
                           action_summary="PASSWORD_CANARY", observation_summary="TOKEN_CANARY")
    execution = SimpleNamespace(runtime_name="persona", id=execution_id, journey_id=journey_id)
    queries = []

    class Session:
        async def execute(self, statement):
            queries.append(statement)
            rows = [(step, execution)] if "execution_steps" in str(statement) else []
            return SimpleNamespace(all=lambda: rows)

    repository = LiveBrowserRepository(Session())
    first = await repository.activity(run_id=run_id, cursor=None, limit=50)
    step.status = "completed"
    second = await repository.activity(run_id=run_id, cursor=None, limit=50)
    assert first["items"][0]["id"] == second["items"][0]["id"] == "step:10"
    assert first["items"][0]["status"] == "running"
    assert second["items"][0]["status"] == "completed"
    assert "CANARY" not in str(second)
    assert all(run_id in query.compile().params.values() for query in queries)


async def test_session_revocation_during_capture_discards_frame(observation, monkeypatch):
    monkeypatch.setattr(live_browser, "get_authenticated_user_id", AsyncMock(side_effect=[
        observation.actor, HTTPException(401, "Invalid or expired session."),
    ]))
    response = await call(observation, "/frame", {
        "browser_session_id": observation.browser["browser_session_id"], "generation": 0,
    })
    assert response.status_code == 401
    assert b"fixture" not in response.content
    assert response.headers["cache-control"] == "no-store"


async def test_busy_observer_fails_without_stalling_execution(observation, monkeypatch):
    monkeypatch.setattr(live_browser, "_frame_slots", asyncio.Semaphore(0))
    response = await call(observation, "/frame", {
        "browser_session_id": observation.browser["browser_session_id"], "generation": 0,
    })
    assert response.status_code == 429
    observation.worker.observe_frame.assert_not_awaited()


async def test_historical_cursor_never_filters_the_latest_refresh():
    import base64
    import json

    now = datetime.now(UTC)
    run_id, execution_id, journey_id = uuid4(), uuid4(), uuid4()
    execution = SimpleNamespace(runtime_name="persona", id=execution_id, journey_id=journey_id)
    visible = [SimpleNamespace(id=20, created_at=now, action_type="click", status="completed")]

    class Session:
        async def execute(self, statement):
            values = [(item, execution) for item in visible]
            if "execution_steps" not in str(statement):
                values = []
            return SimpleNamespace(all=lambda: values)

    repository = LiveBrowserRepository(Session())
    first = await repository.activity(run_id=run_id, cursor=None, limit=50)
    # A lower allocated identity commits later. A fresh window, unlike after_id,
    # still projects it and lets the UI reconcile its stable ID.
    visible.append(SimpleNamespace(id=19, created_at=now, action_type="fill", status="completed"))
    second = await repository.activity(run_id=run_id, cursor=None, limit=50)
    assert [item["id"] for item in first["items"]] == ["step:20"]
    assert {item["id"] for item in second["items"]} == {"step:19", "step:20"}
    opaque = base64.urlsafe_b64encode(json.dumps([now.isoformat(), "step:20"]).encode()).decode()
    assert decode_cursor(opaque) == (now, "step:20")
