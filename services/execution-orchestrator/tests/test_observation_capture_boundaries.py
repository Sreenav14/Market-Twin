"""Observation cannot retain control or deliver pixels after authority changes."""

import asyncio
import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin
from markettwin_execution_orchestrator.browser import owner as owner_module
from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.owner import (
    ControllerBrowserOwner,
    ViewerRejectedError,
)
from markettwin_execution_orchestrator.browser.owner_registry import BrowserOwnerRegistry
from markettwin_execution_orchestrator.browser.owner_service import HITLWorkerService

SECRET = "synthetic-observation-audit-secret-0123456789"


def owner_fixture():
    channel = SimpleNamespace(
        send=AsyncMock(return_value={"data": base64.b64encode(b"\xff\xd8fixture").decode()}),
        detach=AsyncMock(),
    )
    session = SimpleNamespace(
        lock=asyncio.Lock(), control_generation=0, control_mode="agent", state="open",
        browser=SimpleNamespace(is_connected=lambda: True),
        context=SimpleNamespace(new_cdp_session=AsyncMock(return_value=channel)),
        page=SimpleNamespace(url="http://127.0.0.1:8765/"),
        allowed_origins=(AllowedOrigin("http", "127.0.0.1", 8765),),
        network_policy="local_development",
    )
    controller = SimpleNamespace(_get_session=lambda **_: session)
    handle = BrowserSessionHandle(uuid4(), uuid4(), uuid4())
    return ControllerBrowserOwner(controller), session, channel, handle


async def test_slow_capture_times_out_and_releases_control_lock(monkeypatch):
    owner, session, channel, handle = owner_fixture()
    monkeypatch.setattr(owner_module, "OBSERVATION_OPERATION_SECONDS", 0.03)

    async def capture(*_):
        await asyncio.sleep(10)

    channel.send.side_effect = capture
    started = time.monotonic()
    with pytest.raises(ViewerRejectedError, match="Browser observation is unavailable"):
        await owner.observe(handle, generation=0)
    assert time.monotonic() - started < 1
    assert not session.lock.locked()
    channel.detach.assert_awaited_once()


async def test_capture_cancellation_releases_lock_and_detaches():
    owner, session, channel, handle = owner_fixture()
    entered = asyncio.Event()

    async def capture(*_):
        entered.set()
        await asyncio.sleep(10)

    channel.send.side_effect = capture
    task = asyncio.create_task(owner.observe(handle, generation=0))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not session.lock.locked()
    channel.detach.assert_awaited_once()


async def test_slow_detach_is_bounded_and_never_holds_control_lock(monkeypatch):
    owner, session, channel, handle = owner_fixture()
    monkeypatch.setattr(owner_module, "OBSERVATION_CLEANUP_SECONDS", 0.03)

    async def detach():
        assert not session.lock.locked()
        await asyncio.sleep(10)

    channel.detach.side_effect = detach
    started = time.monotonic()
    assert (await owner.observe(handle, generation=0)).startswith(b"\xff\xd8")
    assert time.monotonic() - started < 1
    assert not session.lock.locked()


@pytest.mark.parametrize("transition", ["human", "verifying", "closed", "generation", "origin"])
async def test_transition_during_capture_discards_frame(transition):
    owner, session, channel, handle = owner_fixture()

    async def capture(*_):
        if transition == "closed":
            session.state = "closed"
        elif transition == "generation":
            session.control_generation = 1
        elif transition == "origin":
            session.page.url = "http://unapproved.invalid/"
        else:
            session.control_mode = transition
        return {"data": base64.b64encode(b"\xff\xd8private").decode()}

    channel.send.side_effect = capture
    with pytest.raises(ViewerRejectedError):
        await owner.observe(handle, generation=0)
    assert not session.lock.locked()


@pytest.mark.parametrize("post_authorized", [False, True])
async def test_signed_observation_rechecks_durable_authority_after_capture(post_authorized):
    service = HITLWorkerService(
        session_factory=object(), registry=BrowserOwnerRegistry(), internal_secret=SECRET,
        allowed_origins=frozenset({"http://localhost:5173"}),
        viewer_url="ws://localhost:5173/api/v1/hitl-viewer", allow_local_ws=True,
    )
    handle = BrowserSessionHandle(uuid4(), uuid4(), uuid4())
    authority = AsyncMock(side_effect=[True, post_authorized])
    service._authority = SimpleNamespace(observer_permitted=authority)
    service._registry = SimpleNamespace(
        handle=lambda **_: handle, observe=AsyncMock(return_value=b"\xff\xd8synthetic"),
    )
    body = json.dumps({
        "actor_id": str(uuid4()), "browser_session_id": str(handle.session_id),
        "execution_id": str(handle.execution_id), "journey_id": str(handle.journey_id),
        "generation": 0,
    }).encode()
    timestamp, nonce = str(int(time.time())), uuid4().hex
    signature = hmac.new(
        SECRET.encode(), timestamp.encode() + b"." + nonce.encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=service.app), base_url="http://worker",
    ) as client:
        response = await client.post("/internal/hitl/observe", content=body, headers={
            "X-MarketTwin-HITL-Timestamp": timestamp, "X-MarketTwin-HITL-Nonce": nonce,
            "X-MarketTwin-HITL-Signature": signature,
        })
    assert authority.await_count == 2
    assert response.status_code == (200 if post_authorized else 409)
    if post_authorized:
        assert response.headers["cache-control"] == "no-store"
    else:
        assert response.json() == {"detail": "Browser observation unavailable."}
        assert b"synthetic" not in response.content
