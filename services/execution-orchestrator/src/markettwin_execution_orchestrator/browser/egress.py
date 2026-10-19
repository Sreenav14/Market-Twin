"""Session-owned HTTP proxy binding validated DNS answers to actual TCP sockets.

TLS stays end-to-end in CONNECT tunnels. Playwright routes remain responsible for
origin and request authorization; this boundary independently rejects unsafe IPs.
"""

import asyncio
import socket
from urllib.parse import urlsplit, urlunsplit

from markettwin_execution_orchestrator.browser.contracts import NetworkPolicy
from markettwin_execution_orchestrator.browser.network import (
    resolve_and_validate_host,
    system_host_lookup,
)


class PinnedEgressProxy:
    """Private, bounded proxy whose sockets never resolve an unchecked hostname."""

    def __init__(self, network_policy: NetworkPolicy) -> None:
        self._policy: NetworkPolicy = network_policy
        self._server: asyncio.Server | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._writers: set[asyncio.StreamWriter] = set()

    async def start(self) -> str:
        self._server = await asyncio.start_server(
            self._accept, "127.0.0.1", 0, limit=16 * 1024,
        )
        port = self._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        for writer in tuple(self._writers):
            writer.close()
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _copy(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while data := await reader.read(64 * 1024):
            writer.write(data)
            await writer.drain()

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        if len(self._tasks) >= 64:
            writer.close()
            return
        self._tasks.add(task)
        self._writers.add(writer)
        upstream: asyncio.StreamWriter | None = None
        pumps: list[asyncio.Task[None]] = []
        established = False
        try:
            async with asyncio.timeout(10):
                header = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1")
                lines = header.split("\r\n")
                method, target, version = lines[0].split(" ")
                tunnel = method == "CONNECT"
                parsed = urlsplit("https://" + target if tunnel else target)
                if (
                    version not in {"HTTP/1.0", "HTTP/1.1"}
                    or not parsed.hostname or parsed.username or parsed.password
                    or parsed.fragment or parsed.scheme != ("https" if tunnel else "http")
                    or (tunnel and (parsed.path or parsed.query))
                ):
                    raise ValueError("Invalid proxy target.")
                port = parsed.port or (443 if tunnel else 80)
                addresses = await resolve_and_validate_host(
                    parsed.hostname, self._policy, system_host_lookup,
                )
                # Pass only a validated numeric IP to the TCP dialer. Chromium
                # cannot perform a second hostname lookup for this connection.
                address = addresses[0]
                remote, upstream = await asyncio.open_connection(
                    address.address, port,
                    family=socket.AF_INET if address.family == 4 else socket.AF_INET6,
                )
                self._writers.add(upstream)
                if tunnel:
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await writer.drain()
                else:
                    path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
                    forwarded = [f"{method} {path} {version}", f"Host: {parsed.netloc}"]
                    websocket = False
                    for line in lines[1:]:
                        if not line:
                            continue
                        name, separator, value = line.partition(":")
                        if not separator or line[0].isspace():
                            raise ValueError("Invalid proxy header.")
                        if name.lower() not in {
                            "host", "connection", "proxy-connection", "proxy-authorization",
                        }:
                            forwarded.append(line)
                        if name.lower() == "upgrade" and value.strip().lower() == "websocket":
                            websocket = True
                    forwarded.append("Connection: Upgrade" if websocket else "Connection: close")
                    upstream.write(("\r\n".join(forwarded) + "\r\n\r\n").encode("latin-1"))
                    await upstream.drain()
                established = True
            pumps = [
                asyncio.create_task(self._copy(reader, upstream)),
                asyncio.create_task(self._copy(remote, writer)),
            ]
            done, _pending = await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
            for completed in done:
                completed.result()
        except asyncio.CancelledError:
            raise
        except Exception:
            if not established:
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
        finally:
            for pump in pumps:
                pump.cancel()
            if pumps:
                await asyncio.gather(*pumps, return_exceptions=True)
            for stream in (writer, upstream):
                if stream is not None:
                    self._writers.discard(stream)
                    stream.close()
            self._tasks.discard(task)
