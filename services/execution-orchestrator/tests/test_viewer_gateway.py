"""Real TLS websocket boundary tests, with no real identities or credentials."""

import asyncio
import json
import socket
import ssl
import threading
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.owner import (
    ControllerBrowserOwner,
    OwnerLease,
    ViewerInput,
)
from markettwin_execution_orchestrator.browser.viewer_gateway import ViewerGateway
from playwright.async_api import expect
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus


class SyntheticAuthority:
    def __init__(self, actor_id: UUID) -> None:
        self.actor_id = actor_id
        self.session_active = True
        self.target_active = True

    async def actor(self, session_cookie: str) -> UUID | None:
        return (
            self.actor_id if self.session_active and session_cookie == "synthetic-session" else None
        )

    async def permitted(self, actor_id: UUID, lease: OwnerLease) -> bool:
        return self.target_active and actor_id == self.actor_id == lease.actor_id


class RecordingOwner:
    """Records counts only: deliberately never retains text or pixel frames."""

    def __init__(self) -> None:
        self.inputs = 0
        self.revoked = 0

    async def attach(self, lease: OwnerLease) -> None:
        pass

    async def input(self, lease: OwnerLease, event: ViewerInput) -> None:
        self.inputs += 1

    async def renew(self, lease: OwnerLease) -> None:
        pass

    async def frame(self, lease: OwnerLease) -> bytes:
        return b"synthetic-frame"

    async def revoke(self, handle: BrowserSessionHandle, generation: int) -> None:
        self.revoked += 1


@pytest.fixture
async def gateway_server(
    tmp_path: Path,
) -> AsyncIterator[
    tuple[str, ssl.SSLContext, ViewerGateway, SyntheticAuthority, RecordingOwner, OwnerLease]
]:
    owner = RecordingOwner()
    actor_id = uuid4()
    authority = SyntheticAuthority(actor_id)
    lease = OwnerLease(
        BrowserSessionHandle(uuid4(), uuid4(), uuid4()),
        actor_id,
        uuid4(),
        1,
        datetime.now(UTC) + timedelta(seconds=30),
        request_id=uuid4(),
    )
    gateway = ViewerGateway(
        owner, authority, allowed_origins=frozenset({"https://fixture.invalid"})
    )
    app = FastAPI()
    app.include_router(gateway.router)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "HITL local synthetic test")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "test-cert.pem", tmp_path / "test-key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    client_ssl = ssl.create_default_context(cafile=str(cert_path))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            log_level="critical",
            access_log=False,
            ssl_certfile=str(cert_path),
            ssl_keyfile=str(key_path),
            ws_max_size=4096,
        )
    )
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        yield (
            f"wss://127.0.0.1:{port}/api/v1/hitl-viewer",
            client_ssl,
            gateway,
            authority,
            owner,
            lease,
        )
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        sock.close()


@pytest.mark.parametrize(
    "attack", ["origin", "cookie", "query", "ticket", "malformed", "oversized"]
)
async def test_gateway_rejects_unauthorized_and_malformed_connections(
    gateway_server: tuple[
        str, ssl.SSLContext, ViewerGateway, SyntheticAuthority, RecordingOwner, OwnerLease
    ],
    attack: str,
) -> None:
    url, tls, gateway, _, owner, lease = gateway_server
    token = await gateway.issue_ticket(lease.actor_id, lease)
    try:
        async with connect(
            url + ("?ticket=" + token if attack == "query" else ""),
            ssl=tls,
            origin="https://foreign.invalid" if attack == "origin" else "https://fixture.invalid",
            additional_headers={
                "Cookie": "markettwin_session="
                + ("foreign-session" if attack == "cookie" else "synthetic-session")
            },
        ) as websocket:
            await websocket.send(json.dumps({"ticket": "invalid" if attack == "ticket" else token}))
            if attack in {"malformed", "oversized"}:
                assert await websocket.recv() == b"synthetic-frame"
                await websocket.send("{" if attack == "malformed" else "x" * 5000)
            with pytest.raises(ConnectionClosed):
                while True:
                    await asyncio.wait_for(websocket.recv(), 3)
    except InvalidStatus as error:
        assert attack in {"origin", "cookie", "query"}
        assert error.response.status_code == 403
    assert owner.inputs == 0


@pytest.mark.parametrize("revocation", ["session", "target"])
async def test_live_session_and_target_revocation_stops_input(
    gateway_server: tuple[
        str, ssl.SSLContext, ViewerGateway, SyntheticAuthority, RecordingOwner, OwnerLease
    ],
    revocation: str,
) -> None:
    url, tls, gateway, authority, owner, lease = gateway_server
    token = await gateway.issue_ticket(lease.actor_id, lease)
    async with connect(
        url,
        ssl=tls,
        origin="https://fixture.invalid",
        additional_headers={"Cookie": "markettwin_session=synthetic-session"},
    ) as websocket:
        await websocket.send(json.dumps({"ticket": token}))
        assert await websocket.recv() == b"synthetic-frame"
        await websocket.send(json.dumps({"sequence": 1, "event": "key", "key": "Tab"}))
        while isinstance(response := await websocket.recv(), bytes):
            pass
        assert json.loads(response) == {"accepted_sequence": 1}
        if revocation == "session":
            authority.session_active = False
        else:
            authority.target_active = False
        await websocket.send(json.dumps({"sequence": 2, "event": "text", "text": "not-retained"}))
        with pytest.raises(ConnectionClosed):
            while True:
                await asyncio.wait_for(websocket.recv(), 3)
    assert owner.inputs == 1
    assert owner.revoked == 1
    # Used ticket is gone and cannot create another connection.
    authority.session_active = True
    authority.target_active = True
    async with connect(
        url,
        ssl=tls,
        origin="https://fixture.invalid",
        additional_headers={"Cookie": "markettwin_session=synthetic-session"},
    ) as websocket:
        await websocket.send(json.dumps({"ticket": token}))
        with pytest.raises(ConnectionClosed):
            await websocket.recv()


async def test_live_lease_expiry_closes_socket_without_input(
    gateway_server: tuple[
        str, ssl.SSLContext, ViewerGateway, SyntheticAuthority, RecordingOwner, OwnerLease
    ],
) -> None:
    url, tls, gateway, _, owner, original = gateway_server
    lease = replace(original, expires_at=datetime.now(UTC) + timedelta(seconds=0.3))
    token = await gateway.issue_ticket(lease.actor_id, lease)
    async with connect(
        url,
        ssl=tls,
        origin="https://fixture.invalid",
        additional_headers={"Cookie": "markettwin_session=synthetic-session"},
    ) as websocket:
        await websocket.send(json.dumps({"ticket": token}))
        assert await websocket.recv() == b"synthetic-frame"
        with pytest.raises(ConnectionClosed):
            while True:
                await asyncio.wait_for(websocket.recv(), 2)
    assert owner.inputs == 0
    assert owner.revoked == 1


async def test_signed_request_revocation_fences_even_before_viewer_connects(
    gateway_server: tuple[
        str, ssl.SSLContext, ViewerGateway, SyntheticAuthority, RecordingOwner, OwnerLease
    ],
) -> None:
    _, _, gateway, _, owner, lease = gateway_server
    ticket = await gateway.issue_ticket(lease.actor_id, lease)
    assert ticket
    assert lease.request_id is not None
    await gateway.revoke_request(lease.request_id, generation=2)
    assert owner.revoked == 1
    assert lease.handle.session_id not in gateway._connected  # pyright: ignore[reportPrivateUsage]


async def test_tls_gateway_operates_the_original_browser_context(
    gateway_server: tuple[
        str, ssl.SSLContext, ViewerGateway, SyntheticAuthority, RecordingOwner, OwnerLease
    ],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url, tls, gateway, _, _, original = gateway_server
    directory = Path(__file__).parent / "fixtures/hitl_app"

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(directory)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        async with BrowserController(artifact_root=tmp_path / "browser-artifacts") as controller:
            handle = await controller.create_session(
                execution_id=uuid4(),
                journey_id=uuid4(),
                network_policy="local_development",
                allowed_origins=(AllowedOrigin("http", "127.0.0.1", server.server_port),),
            )
            await controller.navigate(
                session_id=handle.session_id,
                url=f"http://127.0.0.1:{server.server_port}/index.html?view=login",
            )
            session = cast(Any, controller)._get_session(session_id=handle.session_id)
            context = session.context
            lease = replace(original, handle=handle)
            revoked = asyncio.Event()
            original_revoke = ControllerBrowserOwner.revoke

            async def signal_revoke(
                owner: ControllerBrowserOwner,
                browser_handle: BrowserSessionHandle,
                generation: int,
            ) -> None:
                await original_revoke(owner, browser_handle, generation)
                revoked.set()

            monkeypatch.setattr(ControllerBrowserOwner, "revoke", signal_revoke)
            gateway._owner = ControllerBrowserOwner(controller)  # pyright: ignore[reportPrivateUsage]
            await controller.begin_human_control(session_id=handle.session_id)
            token = await gateway.issue_ticket(lease.actor_id, lease)
            async with connect(
                url,
                ssl=tls,
                origin="https://fixture.invalid",
                additional_headers={"Cookie": "markettwin_session=synthetic-session"},
            ) as websocket:
                await websocket.send(json.dumps({"ticket": token}))
                assert isinstance(await websocket.recv(), bytes)
                sequence = 0

                async def send(**payload: object) -> None:
                    nonlocal sequence
                    sequence += 1
                    await websocket.send(json.dumps({"sequence": sequence, **payload}))
                    while isinstance(response := await websocket.recv(), bytes):
                        pass
                    assert json.loads(response) == {"accepted_sequence": sequence}

                box = await session.page.get_by_label("Username").bounding_box()
                assert box is not None
                await send(
                    event="click",
                    x=int(box["x"] + box["width"] / 2),
                    y=int(box["y"] + box["height"] / 2),
                )
                await send(event="text", text="fixture-user")
                await send(event="key", key="Tab")
                await send(event="text", text="synthetic-password")
                await send(event="key", key="Tab")
                await send(event="key", key="Enter")
                await expect(session.page.get_by_label("One-time code")).to_be_visible()
                box = await session.page.get_by_label("One-time code").bounding_box()
                await send(
                    event="click",
                    x=int(box["x"] + box["width"] / 2),
                    y=int(box["y"] + box["height"] / 2),
                )
                await send(event="text", text="246810")
                await send(event="key", key="Tab")
                await send(event="key", key="Enter")
                await expect(
                    session.page.get_by_text("Signed in as user", exact=True)
                ).to_be_visible()
                assert session.context is context
                assert session.session_id == handle.session_id
            await asyncio.wait_for(revoked.wait(), timeout=2)
            assert session.control_mode == "verifying"
            assert not session.capture_enabled
            assert not session.tracing_active
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=2)
