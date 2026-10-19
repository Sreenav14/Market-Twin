"""Actual TCP-boundary tests; no external network or provider access."""

import asyncio
import ssl
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.contracts import ResolvedAddress
from markettwin_execution_orchestrator.browser.egress import PinnedEgressProxy
from markettwin_execution_orchestrator.browser.errors import BrowserNavigationError
from websockets.asyncio.server import ServerConnection, serve


@pytest.mark.parametrize("method", ["GET", "CONNECT"])
async def test_dns_change_cannot_rebind_an_approved_socket(monkeypatch: pytest.MonkeyPatch,
                                                        method: str) -> None:
    hits: list[bytes] = []

    async def destination(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        data = await reader.read(4096)
        hits.append(data)
        if method == "GET":
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        else:
            writer.write(data)
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(destination, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    resolutions = 0

    async def changing_dns(_host: str) -> tuple[ResolvedAddress, ...]:
        nonlocal resolutions
        resolutions += 1
        return (ResolvedAddress("127.0.0.1" if resolutions == 1 else "10.0.0.1", 4),)

    monkeypatch.setattr(
        "markettwin_execution_orchestrator.browser.egress.system_host_lookup", changing_dns,
    )
    proxy = PinnedEgressProxy("local_development")
    proxy_url = urlsplit(await proxy.start())
    try:
        for attempt in range(2):
            reader, writer = await asyncio.open_connection("127.0.0.1", proxy_url.port)
            target = (f"rebind.invalid:{port}" if method == "CONNECT"
                      else f"http://rebind.invalid:{port}/proof")
            writer.write(f"{method} {target} HTTP/1.1\r\nHost: rebind.invalid\r\n\r\n".encode())
            await writer.drain()
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
            if attempt == 0:
                assert b"200" in header
                if method == "CONNECT":
                    writer.write(b"pinned-connection")
                    await writer.drain()
                    assert await reader.readexactly(17) == b"pinned-connection"
                else:
                    assert await reader.readexactly(2) == b"OK"
            else:
                assert b"502" in header
            writer.close()
            await writer.wait_closed()
        assert resolutions == 2
        assert len(hits) == 1
    finally:
        await proxy.close()
        server.close()
        await server.wait_closed()


async def test_public_proxy_rejects_loopback_without_dialing() -> None:
    proxy = PinnedEgressProxy("public_only")
    target = urlsplit(await proxy.start())
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", target.port)
        writer.write(b"CONNECT 127.0.0.1:80 HTTP/1.1\r\n\r\n")
        await writer.drain()
        assert b"502" in await asyncio.wait_for(reader.read(), 3)
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.close()


async def test_chromium_connects_through_pinned_proxy_for_unresolvable_hostname(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    hits: list[bytes] = []

    async def destination(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        hits.append(await reader.readuntil(b"\r\n\r\n"))
        body = b"<html><body>Pinned destination</body></html>"
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: "
                     + str(len(body)).encode() + b"\r\n\r\n" + body)
        await writer.drain()
        writer.close()

    async def lookup(_host: str) -> tuple[ResolvedAddress, ...]:
        return (ResolvedAddress("127.0.0.1", 4),)

    async def preflight(*_args: object, **_kwargs: object) -> tuple[ResolvedAddress, ...]:
        return await lookup("")

    monkeypatch.setattr(
        "markettwin_execution_orchestrator.browser.egress.system_host_lookup", lookup,
    )
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.browser.controller.resolve_and_validate_host", preflight,
    )
    server = await asyncio.start_server(destination, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        async with BrowserController(artifact_root=tmp_path) as controller:
            handle = await controller.create_session(
                execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
                allowed_origins=(AllowedOrigin("http", "rebind.invalid", port),
                                 AllowedOrigin("http", "127.0.0.1", port)),
            )
            await controller.navigate(session_id=handle.session_id,
                                      url=f"http://rebind.invalid:{port}/proof")
            session = controller._get_session(  # pyright: ignore[reportPrivateUsage]
                session_id=handle.session_id,
            )
            assert await session.page.inner_text("body") == "Pinned destination"
            await controller._egress_proxies[handle.session_id].close()  # pyright: ignore[reportPrivateUsage]
            hits.clear()
            with pytest.raises(BrowserNavigationError):
                await controller.navigate(session_id=handle.session_id,
                                          url=f"http://127.0.0.1:{port}/no-bypass")
            assert hits == []
    finally:
        server.close()
        await server.wait_closed()


async def test_chromium_websocket_uses_pinned_proxy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    async def echo(connection: ServerConnection) -> None:
        async for payload in connection:
            await connection.send(payload)

    async def lookup(_host: str) -> tuple[ResolvedAddress, ...]:
        return (ResolvedAddress("127.0.0.1", 4),)

    async def preflight(*_args: object, **_kwargs: object) -> tuple[ResolvedAddress, ...]:
        return await lookup("")

    monkeypatch.setattr(
        "markettwin_execution_orchestrator.browser.egress.system_host_lookup", lookup,
    )
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.browser.controller.resolve_and_validate_host", preflight,
    )
    async with serve(echo, "127.0.0.1", 0) as server:
        port = int(next(iter(server.sockets)).getsockname()[1])
        async with BrowserController(artifact_root=tmp_path) as controller:
            handle = await controller.create_session(
                execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
                allowed_origins=(AllowedOrigin("http", "rebind.invalid", port),),
            )
            session = controller._get_session(  # pyright: ignore[reportPrivateUsage]
                session_id=handle.session_id,
            )
            assert await asyncio.wait_for(session.page.evaluate(
                """url => new Promise((resolve, reject) => {
                    const socket = new WebSocket(url);
                    socket.onopen = () => socket.send('pinned-websocket');
                    socket.onmessage = event => { socket.close(); resolve(event.data); };
                    socket.onerror = () => reject(new Error('socket failed'));
                })""", f"ws://rebind.invalid:{port}/socket",
            ), 10) == "pinned-websocket"


async def test_connect_preserves_end_to_end_tls_hostname_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "rebind.invalid")])
    certificate = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("rebind.invalid")]),
                       critical=False).sign(key, hashes.SHA256())
    )
    cert, private_key = tmp_path / "fixture.pem", tmp_path / "fixture-key.pem"
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private_key.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_tls.load_cert_chain(cert, private_key)

    async def destination(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        assert await reader.readexactly(5) == b"proof"
        writer.write(b"verified")
        await writer.drain()
        writer.close()

    async def lookup(_host: str) -> tuple[ResolvedAddress, ...]:
        return (ResolvedAddress("127.0.0.1", 4),)

    monkeypatch.setattr(
        "markettwin_execution_orchestrator.browser.egress.system_host_lookup", lookup,
    )
    server = await asyncio.start_server(destination, "127.0.0.1", 0, ssl=server_tls)
    port = server.sockets[0].getsockname()[1]
    proxy = PinnedEgressProxy("local_development")
    target = urlsplit(await proxy.start())
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", target.port)
        writer.write(f"CONNECT rebind.invalid:{port} HTTP/1.1\r\n\r\n".encode())
        await writer.drain()
        assert b"200" in await reader.readuntil(b"\r\n\r\n")
        await writer.start_tls(ssl.create_default_context(cafile=str(cert)),
                               server_hostname="rebind.invalid")
        writer.write(b"proof")
        await writer.drain()
        assert await reader.readexactly(8) == b"verified"
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.close()
        server.close()
        await server.wait_closed()
