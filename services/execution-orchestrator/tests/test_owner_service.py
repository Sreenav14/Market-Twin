"""Focused worker listener and signed owner-handoff tests."""

import hashlib
import hmac
import socket
import time
from typing import cast

import httpx
import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.owner import ViewerRejectedError
from markettwin_execution_orchestrator.browser.owner_registry import BrowserOwnerRegistry
from markettwin_execution_orchestrator.browser.owner_service import HITLWorkerService
from markettwin_execution_orchestrator.worker import build_hitl_worker_service
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

SECRET = "synthetic-worker-secret-that-is-long-enough-012345"


def build_service() -> HITLWorkerService:
    return HITLWorkerService(
        session_factory=cast(async_sessionmaker[AsyncSession], object()),
        registry=BrowserOwnerRegistry(),
        internal_secret=SECRET,
        allowed_origins=frozenset({"http://localhost:5173"}),
        viewer_url="ws://localhost:5173/api/v1/hitl-viewer",
        allow_local_ws=True,
    )


@pytest.mark.asyncio
async def test_internal_handoff_signature_binds_body_and_rejects_nonce_replay() -> None:
    service = build_service()
    timestamp = str(int(time.time()))
    nonce = "N" * 24
    body = b"{}"
    signature = hmac.new(
        SECRET.encode(),
        timestamp.encode() + b"." + nonce.encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    headers = {
        "X-MarketTwin-HITL-Timestamp": timestamp,
        "X-MarketTwin-HITL-Nonce": nonce,
        "X-MarketTwin-HITL-Signature": signature,
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=service.app),
        base_url="http://worker",
    ) as client:
        first = await client.post("/internal/hitl/leases", content=body, headers=headers)
        replay = await client.post("/internal/hitl/leases", content=body, headers=headers)
    assert first.status_code == 400  # signed body is not a lease envelope
    assert replay.status_code == 401


@pytest.mark.asyncio
async def test_internal_handoff_rejects_wrong_signature_stale_time_and_oversize() -> None:
    service = build_service()
    nonce = "Q" * 24
    body = b"{}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=service.app),
        base_url="http://worker",
    ) as client:
        wrong = await client.post(
            "/internal/hitl/leases",
            content=body,
            headers={
                "X-MarketTwin-HITL-Timestamp": str(int(time.time())),
                "X-MarketTwin-HITL-Nonce": nonce,
                "X-MarketTwin-HITL-Signature": "0" * 64,
            },
        )
        stale = await client.post(
            "/internal/hitl/leases",
            content=body,
            headers={
                "X-MarketTwin-HITL-Timestamp": "1",
                "X-MarketTwin-HITL-Nonce": "R" * 24,
                "X-MarketTwin-HITL-Signature": "0" * 64,
            },
        )
        oversized = await client.post(
            "/internal/hitl/leases",
            content=b"x" * 4097,
            headers={
                "X-MarketTwin-HITL-Timestamp": str(int(time.time())),
                "X-MarketTwin-HITL-Nonce": "S" * 24,
                "X-MarketTwin-HITL-Signature": "0" * 64,
            },
        )
    assert wrong.status_code == 401
    assert stale.status_code == 401
    assert oversized.status_code == 413


def test_worker_hitl_configuration_absent_or_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    names = (
        "MARKETTWIN_HITL_INTERNAL_SECRET",
        "MARKETTWIN_HITL_VIEWER_ORIGINS",
        "MARKETTWIN_HITL_VIEWER_URL",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
    factory = cast(async_sessionmaker[AsyncSession], object())
    assert build_hitl_worker_service(factory) is None

    monkeypatch.setenv(names[0], SECRET)
    with pytest.raises(RuntimeError, match="configuration is incomplete"):
        build_hitl_worker_service(factory)


@pytest.mark.asyncio
async def test_worker_viewer_service_starts_and_stops_on_loopback() -> None:
    service = build_service()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    with pytest.raises(ValueError, match="TLS files"):
        await service.start(host="127.0.0.1", port=port, cert_file="cert", key_file=None)
    await service.start(host="127.0.0.1", port=port, cert_file=None, key_file=None)
    assert service.is_running
    await service.stop()
    assert not service.is_running


@pytest.mark.asyncio
async def test_browser_controller_registers_only_its_live_exact_handle(tmp_path) -> None:
    from uuid import uuid4

    from markettwin_execution_orchestrator.browser.owner_registry import browser_owner_registry

    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(),
            journey_id=uuid4(),
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", 54321),),
            network_policy="local_development",
        )
        assert (
            browser_owner_registry.handle(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
            )
            == handle
        )
        await controller.close_session(session_id=handle.session_id)
        with pytest.raises(ViewerRejectedError):
            browser_owner_registry.handle(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
            )
