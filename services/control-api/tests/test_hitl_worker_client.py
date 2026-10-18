"""Tests for the signed internal browser-owner bridge."""

import hashlib
import hmac
import json
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from markettwin_control_api.api import human_actions
from markettwin_control_api.config import Settings
from markettwin_control_api.services.hitl_worker_client import HitlWorkerClient
from pydantic import SecretStr


@pytest.mark.asyncio
async def test_issue_grant_signs_nonce_and_exact_raw_envelope() -> None:
    secret = "unit-test-hitl-key"
    seen: dict[str, object] = {}

    async def respond(request: httpx.Request) -> httpx.Response:
        body = request.content
        timestamp = request.headers["X-MarketTwin-HITL-Timestamp"]
        nonce = request.headers["X-MarketTwin-HITL-Nonce"]
        assert 24 <= len(nonce) <= 64
        signature = request.headers["X-MarketTwin-HITL-Signature"]
        expected = hmac.new(
            secret.encode(),
            timestamp.encode() + b"." + nonce.encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        assert hmac.compare_digest(signature, expected)
        seen.update(path=request.url.path, body=json.loads(body), signature=signature)
        return httpx.Response(
            200,
            json={"ticket": "t" * 40, "viewer_url": "wss://localhost/api/v1/hitl-viewer"},
        )

    client = HitlWorkerClient(
        base_url="http://worker.test",
        secret=SecretStr(secret),
        transport=httpx.MockTransport(respond),
    )
    actor, action, browser, lease, execution, journey = (uuid4() for _ in range(6))
    grant = await client.issue_viewer_grant(
        actor_id=actor,
        request_id=action,
        browser_session_id=browser,
        lease_id=lease,
        lease_token="l" * 43,
        generation=4,
        expires_at="2026-10-14T18:00:00+00:00",
        execution_id=execution,
        journey_id=journey,
    )

    assert seen["path"] == "/internal/hitl/leases"
    envelope = seen["body"]
    assert isinstance(envelope, dict)
    assert envelope["actor_id"] == str(actor)
    assert envelope["lease_token"] == "l" * 43
    assert envelope["execution_id"] == str(execution)
    assert grant.ticket == "t" * 40
    assert grant.viewer_url.scheme == "wss"
    assert "t" * 40 not in repr(grant)


@pytest.mark.asyncio
async def test_worker_errors_are_sanitized() -> None:
    async def reject(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="sensitive internal diagnostic")

    client = HitlWorkerClient(
        base_url="http://worker.test",
        secret=SecretStr("unit-test-hitl-key"),
        transport=httpx.MockTransport(reject),
    )
    with pytest.raises(RuntimeError, match="supervised browser owner") as error:
        await client.notify(path="/internal/hitl/leases/revoke", payload={"lease_id": "x"})
    assert "sensitive internal diagnostic" not in str(error.value)


def test_viewer_url_must_be_same_origin_and_query_free(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(app_env="local", web_origin="http://localhost:5173")
    monkeypatch.setattr(human_actions, "get_settings", lambda: settings)
    def grant(url: str) -> human_actions.ViewerGrant:
        return human_actions.ViewerGrant(ticket="t" * 40, viewer_url=url)

    assert human_actions._validate_viewer_url(  # pyright: ignore[reportPrivateUsage]
        grant("ws://localhost:5173/api/v1/hitl-viewer")
    ) == "ws://localhost:5173/api/v1/hitl-viewer"
    for invalid in (
        "ws://attacker.invalid/api/v1/hitl-viewer",
        "wss://localhost:5173/api/v1/hitl-viewer?ticket=secret",
        "ws://localhost:5173/not-the-viewer",
    ):
        with pytest.raises(HTTPException):
            human_actions._validate_viewer_url(  # pyright: ignore[reportPrivateUsage]
                grant(invalid)
            )


async def test_invalid_lease_request_never_reflects_secret_input() -> None:
    app = FastAPI()
    app.include_router(human_actions.router)
    canary = "CANARY_TOKEN"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://api",
    ) as client:
        response = await client.post(f"/api/v1/human-actions/{uuid4()}/viewer", json={
            "lease_id": str(uuid4()), "lease_token": canary, "generation": 1,
        })
    assert response.status_code == 422
    assert canary not in response.text


@pytest.mark.parametrize("case", ["valid", "oversized", "wrong_type", "invalid", "denied"])
async def test_observation_is_signed_bounded_and_has_no_input_authority(case: str) -> None:
    actor, browser, execution, journey = (uuid4() for _ in range(4))
    secret = "synthetic-observer-secret"

    async def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/hitl/observe"
        payload = json.loads(request.content)
        assert payload == {
            "actor_id": str(actor), "browser_session_id": str(browser),
            "execution_id": str(execution), "journey_id": str(journey), "generation": 0,
        }
        timestamp = request.headers["X-MarketTwin-HITL-Timestamp"]
        nonce = request.headers["X-MarketTwin-HITL-Nonce"]
        expected = hmac.new(secret.encode(), timestamp.encode() + b"." + nonce.encode()
                            + b"." + request.content, hashlib.sha256).hexdigest()
        assert hmac.compare_digest(expected, request.headers["X-MarketTwin-HITL-Signature"])
        if case == "denied":
            return httpx.Response(409, text="CANARY_PRIVATE_ERROR")
        image = (b"\xff\xd8" + b"x" * (2 * 1024 * 1024) + b"\xff\xd9"
                 if case == "oversized" else b"invalid" if case == "invalid"
                 else b"\xff\xd8fixture\xff\xd9")
        return httpx.Response(200, content=image, headers={
            "Content-Type": "text/plain" if case == "wrong_type" else "image/jpeg",
        })

    client = HitlWorkerClient(base_url="http://worker.test", secret=SecretStr(secret),
                             transport=httpx.MockTransport(respond))
    if case == "valid":
        image = await client.observe_frame(actor_id=actor, browser_session_id=browser,
                                           execution_id=execution, journey_id=journey, generation=0)
        assert image == b"\xff\xd8fixture\xff\xd9"
    else:
        with pytest.raises(RuntimeError) as error:
            await client.observe_frame(actor_id=actor, browser_session_id=browser,
                                       execution_id=execution, journey_id=journey, generation=0)
        assert "CANARY" not in str(error.value)


async def test_observation_total_timeout_is_bounded():
    import asyncio

    async def respond(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, content=b"\xff\xd8fixture\xff\xd9",
                              headers={"Content-Type": "image/jpeg"})

    client = HitlWorkerClient(base_url="http://worker.test", secret=SecretStr("synthetic"),
                             timeout_seconds=0.01, transport=httpx.MockTransport(respond))
    with pytest.raises(RuntimeError, match="owner is unavailable"):
        await client.observe_frame(actor_id=uuid4(), browser_session_id=uuid4(),
                                   execution_id=uuid4(), journey_id=uuid4(), generation=0)
