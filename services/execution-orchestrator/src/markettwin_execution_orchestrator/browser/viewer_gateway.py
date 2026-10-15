"""Volatile viewer gateway; authentication is supplied by the control plane.

This router is not registered by default. Production requires WSS termination,
an explicit origin allowlist, and a live session/lease authority implementation.
"""

import asyncio
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast
from uuid import UUID

from fastapi import APIRouter, WebSocket

from markettwin_execution_orchestrator.browser.owner import (
    BrowserOwner,
    OwnerLease,
    ViewerInput,
    ViewerRejectedError,
)


class ViewerAuthority(Protocol):
    """Must consult current login, target entitlement and lease, not a snapshot."""

    async def actor(self, session_cookie: str) -> UUID | None: ...
    async def permitted(self, actor_id: UUID, lease: OwnerLease) -> bool: ...
    async def refresh_lease(self, actor_id: UUID, lease_id: UUID) -> OwnerLease | None: ...


@dataclass(frozen=True, slots=True)
class _Ticket:
    lease: OwnerLease
    expires_at: datetime


class ViewerGateway:
    """One ticket/connection per lease; neither frames nor input are recorded."""

    def __init__(
        self,
        owner: BrowserOwner,
        authority: ViewerAuthority,
        *,
        allowed_origins: frozenset[str],
        allow_local_ws: bool = False,
    ) -> None:
        if not allowed_origins:
            raise ValueError("An explicit viewer origin allowlist is required.")
        self._owner = owner
        self._authority = authority
        self._origins = allowed_origins
        self._local_ws = allow_local_ws
        self._tickets: dict[str, _Ticket] = {}
        self._connected: set[UUID] = set()
        self._attached: set[UUID] = set()
        self._leases: dict[UUID, OwnerLease] = {}
        self.router = APIRouter()
        self.router.add_api_websocket_route("/api/v1/hitl-viewer", self.connect)

    async def issue_ticket(self, actor_id: UUID, lease: OwnerLease) -> str:
        now = datetime.now(UTC)
        self._tickets = {
            key: value for key, value in self._tickets.items() if value.expires_at > now
        }
        if (
            actor_id != lease.actor_id
            or lease.expires_at <= now
            or not await self._authority.permitted(actor_id, lease)
            or lease.handle.session_id in self._connected
            or len(self._tickets) >= 100
        ):
            raise ViewerRejectedError("Viewer authority is unavailable.")
        # Keep only a digest at rest; a subsequent ticket invalidates the old one.
        self._tickets = {
            key: value
            for key, value in self._tickets.items()
            if value.lease.lease_id != lease.lease_id
        }
        token = secrets.token_urlsafe(32)
        if lease.lease_id in self._leases:
            await self.renew(actor_id, lease)
        self._tickets[hashlib.sha256(token.encode()).hexdigest()] = _Ticket(
            lease,
            min(now + timedelta(seconds=30), lease.expires_at),
        )
        self._leases[lease.lease_id] = lease
        return token

    async def _permitted(self, cookie: str, lease: OwnerLease) -> bool:
        return (
            lease.expires_at > datetime.now(UTC)
            and await self._authority.actor(cookie) == lease.actor_id
            and await self._authority.permitted(lease.actor_id, lease)
        )

    async def renew(self, actor_id: UUID, lease: OwnerLease) -> None:
        previous = self._leases.get(lease.lease_id)
        if (
            previous is None
            or actor_id != lease.actor_id
            or previous.handle != lease.handle or previous.actor_id != lease.actor_id
            or previous.generation != lease.generation or previous.request_id != lease.request_id
            or lease.expires_at < previous.expires_at
            or not await self._authority.permitted(actor_id, lease)
        ):
            raise ViewerRejectedError("Viewer authority is unavailable.")
        if lease.lease_id in self._attached:
            await self._owner.renew(lease)
        self._leases[lease.lease_id] = lease

    async def renew_for_actor(self, actor_id: UUID, lease_id: UUID) -> None:
        lease = await self._authority.refresh_lease(actor_id, lease_id)
        if lease is None:
            raise ViewerRejectedError("Viewer authority is unavailable.")
        await self.renew(actor_id, lease)

    async def revoke_lease(
        self,
        lease_id: UUID,
        generation: int,
        session_id: UUID | None = None,
    ) -> None:
        lease = self._leases.get(lease_id)
        if lease is not None and session_id is not None and lease.handle.session_id != session_id:
            raise ViewerRejectedError("Viewer authority is unavailable.")
        if lease is not None:
            if generation <= lease.generation:
                raise ViewerRejectedError("A newer control generation is required.")
            await self._owner.revoke(lease.handle, generation)
            self._leases.pop(lease_id, None)
            self._attached.discard(lease_id)
            self._tickets = {
                key: ticket for key, ticket in self._tickets.items()
                if ticket.lease.lease_id != lease_id
            }

    async def revoke_request(self, request_id: UUID, generation: int) -> None:
        for lease_id, lease in tuple(self._leases.items()):
            if lease.request_id == request_id:
                await self.revoke_lease(lease_id, generation)

    async def connect(self, websocket: WebSocket) -> None:
        loopback = websocket.client is not None and websocket.client.host in {"127.0.0.1", "::1"}
        if (
            websocket.headers.get("origin") not in self._origins
            or websocket.url.query
            or (websocket.url.scheme != "wss" and not (self._local_ws and loopback))
        ):
            await websocket.close(code=1008)
            return
        cookie = websocket.cookies.get("markettwin_session", "")
        actor_id = await self._authority.actor(cookie)
        if actor_id is None:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        lease: OwnerLease | None = None
        attached = False
        registered = False
        try:
            async with asyncio.timeout(5):
                message = await websocket.receive_text()
            if len(message.encode()) > 512:
                raise ViewerRejectedError("Viewer handshake was rejected.")
            raw_payload = json.loads(message)
            if not isinstance(raw_payload, dict):
                raise ViewerRejectedError("Viewer handshake was rejected.")
            payload = cast(dict[str, object], raw_payload)
            if set(payload) != {"ticket"}:
                raise ViewerRejectedError("Viewer handshake was rejected.")
            token = payload["ticket"]
            if not isinstance(token, str) or len(token) > 128:
                raise ViewerRejectedError("Viewer handshake was rejected.")
            ticket = self._tickets.pop(hashlib.sha256(token.encode()).hexdigest(), None)
            if ticket is None or ticket.expires_at <= datetime.now(UTC):
                raise ViewerRejectedError("Viewer ticket is unavailable.")
            lease = self._leases.get(ticket.lease.lease_id)
            if (
                lease is None
                or actor_id != lease.actor_id
                or not await self._permitted(cookie, lease)
                or lease.handle.session_id in self._connected
            ):
                raise ViewerRejectedError("Viewer authority is unavailable.")
            self._connected.add(lease.handle.session_id)
            registered = True
            await self._owner.attach(lease)
            attached = True
            self._attached.add(lease.lease_id)

            async def send_frames() -> None:
                while True:
                    current = self._leases[lease.lease_id]
                    if not await self._permitted(cookie, current):
                        break
                    frame = await self._owner.frame(current)
                    if not await self._permitted(cookie, current):
                        break
                    await websocket.send_bytes(frame)
                    await asyncio.sleep(0.5)
                raise ViewerRejectedError("Viewer authority is unavailable.")

            async def receive_input() -> None:
                while True:
                    message = await websocket.receive_text()
                    current = self._leases[lease.lease_id]
                    if len(message.encode()) > 4096 or not await self._permitted(cookie, current):
                        raise ViewerRejectedError("Viewer input was rejected.")
                    # Do not serialize ValidationError: it can contain secret input.
                    event = ViewerInput.model_validate_json(message)
                    await self._owner.input(current, event)
                    await websocket.send_json({"accepted_sequence": event.sequence})

            async with asyncio.TaskGroup() as group:
                group.create_task(send_frames())
                group.create_task(receive_input())
        except Exception:
            # Only a safe close code leaves the boundary. No payload or exception
            # text may reach logs, traces, Kafka, artifacts or error responses.
            try:
                await websocket.close(code=1008)
            except Exception:
                pass
        finally:
            if lease is not None and registered:
                if attached:
                    try:
                        await self._owner.detach(lease)
                    except Exception:
                        pass
                self._connected.discard(lease.handle.session_id)
