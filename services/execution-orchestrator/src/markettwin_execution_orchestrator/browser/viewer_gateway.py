"""Volatile viewer gateway; authentication is supplied by the control plane.

This router is not registered by default. Production requires WSS termination,
an explicit origin allowlist, and a live session/lease authority implementation.
"""

import asyncio
import hashlib
import json
import logging
import secrets
import time
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast
from uuid import UUID

from fastapi import APIRouter, WebSocket

from markettwin_execution_orchestrator.browser.network_diagnostics import (
    NETWORK_DIAGNOSTIC_DESTINATIONS,
    NETWORK_DIAGNOSTIC_REASONS,
)
from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.owner import (
    BrowserOwner,
    OwnerLease,
    ViewerInput,
    ViewerRejectedError,
)

logger = logging.getLogger(__name__)

# Observer loop exits (doc 11 section 2.3): every exit of the observer loop
# carries exactly one of these reasons, logged server-side and used as the
# WebSocket close reason. Authority exits (revoked, expired) close 1008;
# stream/owner exits close 1011. This is the gateway's exit vocabulary; the
# connect-path refusal enum reconciles with it (doc 24 section 5.3).
OBSERVER_EXIT_REASONS = frozenset(
    {"authority_revoked", "lease_expired", "owner_gone", "stream_error",
     "screencast_not_allowed"},
)
_AUTHORITY_EXIT_REASONS = frozenset(
    {"authority_revoked", "lease_expired", "screencast_not_allowed"},
)

# Connect-path refusal classes (doc 24 section 5.3): the closed enum
# a connect() refusal may carry. For an authenticated caller the
# class rides the WebSocket close reason; the structured log line
# records class + sub-condition + session id server-side. An
# unauthenticated caller (no valid cookie) still gets exactly the
# incumbent bland close — no class is observable before auth.
CONNECT_REFUSAL_REASONS = frozenset({
    "no_session", "ticket_invalid", "ticket_consumed", "ticket_expired",
    "lease_expired", "authority_unmet", "screencast_not_allowed",
    "owner_gone", "gateway_error",
})


class _ObserverStreamExit(Exception):
    """Internal control flow only: carries the observer loop's classified
    exit to the observer branch of connect(), which closes the socket with
    its code and reason before the generic boundary can see the exception.
    The `reason` attribute name matches the connect-path exception shape
    (doc 24 section 5.3) so the two surfaces share one mechanism."""

    def __init__(self, reason: str, close_code: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.close_code = close_code


class ViewerAuthority(Protocol):
    """Must consult current login, target entitlement and lease, not a snapshot."""

    async def actor(self, session_cookie: str) -> UUID | None: ...
    async def permitted(self, actor_id: UUID, lease: OwnerLease) -> bool: ...
    async def refresh_lease(self, actor_id: UUID, lease_id: UUID) -> OwnerLease | None: ...


@dataclass(frozen=True, slots=True)
class _Ticket:
    lease: OwnerLease
    expires_at: datetime

@dataclass(frozen=True, slots=True)
class ObserverLease:
    """Read-only watch grant: an exact browser + generation, no input channel."""

    handle: BrowserSessionHandle
    actor_id: UUID
    generation: int
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class _ObserverTicket:
    lease: ObserverLease
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
        self._observer_tickets: dict[str, _ObserverTicket] = {}
        # Digests of tickets already consumed, kept only until the
        # ticket would have expired, so a re-presented ticket reads
        # ticket_consumed rather than ticket_invalid (section 5.3).
        self._consumed_digests: dict[str, datetime] = {}
        # Watch instrumentation (U-P3-04): frames actually sent per
        # observed browser, so fps is measured, never assumed.
        self._observer_frames: dict[UUID, int] = {}
        self._observer_heartbeats: dict[UUID, int] = {}
        self._observer_started_at: dict[UUID, float] = {}
        self._last_observer_stats: dict[str, float | int] = {}
        self._connected: set[UUID] = set()
        self._observing: set[UUID] = set()
        self._attached: set[UUID] = set()
        self._leases: dict[UUID, OwnerLease] = {}
        self.router = APIRouter()
        self.router.add_api_websocket_route("/api/v1/hitl-viewer", self.connect)

    async def issue_ticket(self, actor_id: UUID, lease: OwnerLease) -> str:
        now = datetime.now(UTC)
        self._tickets = {
            key: value for key, value in self._tickets.items() if value.expires_at > now
        }
        self._consumed_digests = {
            key: value for key, value in self._consumed_digests.items()
            if value > now
        }
        if actor_id != lease.actor_id:
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="authority_unmet", detail="actor_mismatch",
            )
        if lease.expires_at <= now:
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="lease_expired", detail="lease_expired",
            )
        if not await self._authority.permitted(actor_id, lease):
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="authority_unmet", detail="permitted_false",
            )
        if lease.handle.session_id in self._connected:
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="authority_unmet", detail="already_connected",
            )
        if len(self._tickets) >= 100:
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="gateway_error", detail="ticket_capacity",
            )
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

    async def issue_observer_ticket(self, actor_id: UUID, lease: ObserverLease) -> str:
        """Same ticket discipline as issue_ticket: only a digest is kept, the
        ticket lives 30 s, is single-use, and a newer ticket for the same
        browser invalidates the older one. The URL is never logged."""
        now = datetime.now(UTC)
        self._observer_tickets = {
            key: value for key, value in self._observer_tickets.items() if value.expires_at > now
        }
        if actor_id != lease.actor_id:
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="authority_unmet", detail="actor_mismatch",
            )
        if lease.expires_at <= now:
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="lease_expired", detail="lease_expired",
            )
        if not await self._observer_permitted(actor_id, lease):
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="authority_unmet", detail="permitted_false",
            )
        if lease.handle.session_id in self._observing:
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="authority_unmet", detail="already_observing",
            )
        if len(self._observer_tickets) >= 100:
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="gateway_error", detail="ticket_capacity",
            )
        self._observer_tickets = {
            key: value
            for key, value in self._observer_tickets.items()
            if value.lease.handle.session_id != lease.handle.session_id
        }
        token = secrets.token_urlsafe(32)
        self._observer_tickets[hashlib.sha256(token.encode()).hexdigest()] = _ObserverTicket(
            lease, min(now + timedelta(seconds=30), lease.expires_at),
        )
        return token

    def observer_stats(self) -> dict[str, float | int]:
        """Frames/second of the live (or last) observer stream (U-P3-04).

        With several streams observed over the gateway's life, the
        live one is the most recently started; reporting the first
        entry ever recorded would freeze the number on a dead stream.
        """

        if self._observer_started_at:
            session_id, started = max(
                self._observer_started_at.items(), key=lambda item: item[1],
            )
            seconds = max(time.monotonic() - started, 0.001)
            frames = self._observer_frames.get(session_id, 0)
            heartbeats = self._observer_heartbeats.get(session_id, 0)
            return {
                **self._screencast_stats(session_id),
                "frames": frames,
                "heartbeats": heartbeats,
                "seconds": round(seconds, 3),
                "fps": round((frames + heartbeats) / seconds, 2),
            }
        return dict(self._last_observer_stats)

    def _screencast_stats(self, session_id: UUID) -> dict[str, int]:
        read = getattr(self._owner, "screencast_stats", None)
        return read(session_id) if callable(read) else {}

    async def _observer_permitted(self, actor_id: UUID, lease: ObserverLease) -> bool:
        if lease.expires_at <= datetime.now(UTC):
            return False
        check = getattr(self._authority, "observer_permitted", None)
        if not callable(check):
            return False
        return await cast(
            Callable[[UUID, BrowserSessionHandle, int], Awaitable[bool]], check,
        )(actor_id, lease.handle, lease.generation)

    async def _connect_observer(self, websocket: WebSocket, actor_id: UUID, lease: ObserverLease) -> None:
        """Observer connection: screencast frames out, nothing in.

        There is deliberately no receive task: an observer ticket can never
        reach owner.input, whatever the client sends after the handshake.
        Human-control leases keep using connect()'s unchanged path.
        """
        cookie = websocket.cookies.get("markettwin_session", "")
        if actor_id != lease.actor_id:
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="authority_unmet", detail="actor_mismatch",
            )
        if await self._authority.actor(cookie) != actor_id:
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="authority_unmet", detail="cookie_actor_mismatch",
            )
        if not await self._observer_permitted(actor_id, lease):
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="authority_unmet", detail="permitted_false",
            )
        if lease.handle.session_id in self._connected:
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="authority_unmet", detail="already_connected",
            )
        if lease.handle.session_id in self._observing:
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="authority_unmet", detail="already_observing",
            )
        self._observing.add(lease.handle.session_id)
        self._observer_frames[lease.handle.session_id] = 0
        self._observer_heartbeats[lease.handle.session_id] = 0
        self._observer_started_at[lease.handle.session_id] = time.monotonic()
        stream_context = AsyncExitStack()
        exit_reason = "stream_error"
        try:
            try:
                observer_stream = getattr(self._authority, "observer_stream", None)
                if callable(observer_stream):
                    context = cast(Callable[[], AbstractAsyncContextManager[None]], observer_stream)
                    await stream_context.enter_async_context(context())
                try:
                    await self._owner.start_screencast(lease.handle, generation=lease.generation)
                except ViewerRejectedError:
                    # Observation refused for this session's state:
                    # the stream never started, which is
                    # screencast_not_allowed — not an owner vanishing
                    # mid-stream (owner_gone in the loop below).
                    raise ViewerRejectedError(
                        "Browser observation is unavailable.",
                        reason="screencast_not_allowed",
                        detail="screencast_refused",
                    ) from None
                last_frame: bytes | None = None
                # The connect-time gate above just ran the full authority
                # check, so the first in-loop check is the cached outcome.
                last_sent_at = 0.0
                last_check_at = time.monotonic()
                last_permitted = True
                while True:
                    # Lease expiry is local and free: checked every iteration
                    # and never folded into the authority cache, so expiry
                    # and revocation stay distinct exits (doc 11 section 2.2).
                    if lease.expires_at <= datetime.now(UTC):
                        exit_reason = "lease_expired"
                        break
                    frame: bytes | None = None
                    try:
                        async with asyncio.timeout(1.0):
                            frame = await self._owner.next_screencast_frame(
                                lease.handle, generation=lease.generation,
                            )
                    except TimeoutError:
                        # Owner silence (a static page during a model call):
                        # fall through to the snapshot below. Cancelling the
                        # wait is safe; frames are acked in the owner's
                        # screencast callback, not in the wait itself.
                        frame = None
                    # Full authority check at most every 2 s; between checks
                    # the cached outcome is reused. A denied fresh check
                    # exits at once (revocation latency <= 2 s is the
                    # accepted trade, doc 11 section 2.2).
                    now = time.monotonic()
                    if now - last_check_at >= 2.0:
                        combined = getattr(self._authority, "observer_permitted_session", None)
                        if callable(combined):
                            check = cast(
                                Callable[[str, UUID, BrowserSessionHandle, int], Awaitable[bool]], combined,
                            )
                            last_permitted = await check(
                                cookie, actor_id, lease.handle, lease.generation,
                            )
                        else:
                            current_actor, permitted = await asyncio.gather(
                                self._authority.actor(cookie), self._observer_permitted(actor_id, lease),
                            )
                            last_permitted = permitted and current_actor == actor_id
                        last_check_at = now
                    if not last_permitted:
                        exit_reason = "authority_revoked"
                        break
                    async with asyncio.timeout(5):
                        current_frame = getattr(self._owner, "current_observer_frame", None)
                        if callable(current_frame):
                            # Discard pixels that became stale during the wait.
                            snapshot = cast(
                                Callable[..., tuple[bytes, dict[str, object]]], current_frame,
                            )
                            frame, pointer = snapshot(lease.handle, generation=lease.generation)
                            await websocket.send_json(pointer)
                        if frame is not None and (
                            frame is not last_frame or now - last_sent_at >= 1.0
                        ):
                            heartbeat = frame is last_frame
                            await websocket.send_bytes(frame)
                            last_frame = frame
                            last_sent_at = now
                            if heartbeat:
                                self._observer_heartbeats[lease.handle.session_id] += 1
                            else:
                                self._observer_frames[lease.handle.session_id] += 1
            except ViewerRejectedError as exc:
                exit_reason = (
                    "screencast_not_allowed"
                    if exc.reason == "screencast_not_allowed"
                    else "owner_gone"
                )
            except asyncio.CancelledError:
                raise  # Cancellation is not an exit classification.
            except Exception:
                exit_reason = "stream_error"
            # Reason code + session id only: no exception text, cookie or
            # ticket may reach the logs (connect()'s boundary discipline).
            logger.info(
                "observer stream exit: reason=%s session=%s",
                exit_reason, lease.handle.session_id,
            )
            raise _ObserverStreamExit(
                exit_reason, 1008 if exit_reason in _AUTHORITY_EXIT_REASONS else 1011,
            )
        finally:
            started = self._observer_started_at.pop(lease.handle.session_id, None)
            frames = self._observer_frames.pop(lease.handle.session_id, 0)
            heartbeats = self._observer_heartbeats.pop(lease.handle.session_id, 0)
            if started is not None:
                seconds = max(time.monotonic() - started, 0.001)
                self._last_observer_stats = {
                    **self._screencast_stats(lease.handle.session_id),
                    "frames": frames,
                    "heartbeats": heartbeats,
                    "seconds": round(seconds, 3),
                    "fps": round((frames + heartbeats) / seconds, 2),
                }
            self._observing.discard(lease.handle.session_id)
            try:
                await self._owner.stop_screencast(lease.handle)
            except Exception:
                pass
            await stream_context.aclose()

    async def _permitted(self, cookie: str, lease: OwnerLease) -> bool:
        if lease.expires_at <= datetime.now(UTC):
            return False
        combined = getattr(self._authority, "permitted_session", None)
        if callable(combined):
            return await cast(Callable[[str, OwnerLease], Awaitable[bool]], combined)(cookie, lease)
        return (
            await self._authority.actor(cookie) == lease.actor_id
            and await self._authority.permitted(lease.actor_id, lease)
        )

    async def prune_expired(self, *, detached_lease_id: UUID | None = None) -> None:
        """Release expired disconnected bookkeeping without breaking live renewal."""
        now = datetime.now(UTC)
        self._tickets = {
            key: ticket for key, ticket in self._tickets.items() if ticket.expires_at > now
        }
        self._observer_tickets = {
            key: ticket for key, ticket in self._observer_tickets.items() if ticket.expires_at > now
        }
        self._consumed_digests = {
            key: value for key, value in self._consumed_digests.items()
            if value > now
        }
        for lease_id, lease in tuple(self._leases.items()):
            if lease.expires_at > now or lease.handle.session_id in self._connected:
                continue
            # Remove before awaiting: a newer ticket must not be removed by this sweep.
            self._leases.pop(lease_id, None)
            was_attached = lease_id in self._attached
            self._attached.discard(lease_id)
            if was_attached and lease_id != detached_lease_id:
                try:
                    await self._owner.detach(lease)
                except ViewerRejectedError:
                    pass  # The live browser may already have been disposed.

    async def renew(self, actor_id: UUID, lease: OwnerLease) -> None:
        previous = self._leases.get(lease.lease_id)
        if previous is None:
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="no_session", detail="no_lease",
            )
        if (
            actor_id != lease.actor_id
            or previous.handle != lease.handle or previous.actor_id != lease.actor_id
            or previous.generation != lease.generation or previous.request_id != lease.request_id
            or lease.expires_at < previous.expires_at
        ):
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="authority_unmet", detail="lease_mismatch",
            )
        if not await self._authority.permitted(actor_id, lease):
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="authority_unmet", detail="permitted_false",
            )
        if lease.lease_id in self._attached:
            await self._owner.renew(lease)
        self._leases[lease.lease_id] = lease

    async def renew_for_actor(self, actor_id: UUID, lease_id: UUID) -> None:
        lease = await self._authority.refresh_lease(actor_id, lease_id)
        if lease is None:
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="no_session", detail="refresh_missed",
            )
        await self.renew(actor_id, lease)

    async def revoke_lease(
        self,
        lease_id: UUID,
        generation: int,
        session_id: UUID | None = None,
    ) -> None:
        lease = self._leases.get(lease_id)
        if lease is not None and session_id is not None and lease.handle.session_id != session_id:
            raise ViewerRejectedError(
                "Viewer authority is unavailable.",
                reason="authority_unmet", detail="session_mismatch",
            )
        if lease is not None:
            if generation <= lease.generation:
                raise ViewerRejectedError(
                    "A newer control generation is required.",
                    reason="authority_unmet", detail="generation_stale",
                )
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
            digest = hashlib.sha256(token.encode()).hexdigest()
            observer_ticket = self._observer_tickets.pop(digest, None)
            if observer_ticket is not None:
                if observer_ticket.expires_at <= datetime.now(UTC):
                    raise ViewerRejectedError(
                        "Viewer ticket is unavailable.",
                        reason="ticket_expired",
                        detail="observer_ticket_expired",
                    )
                self._consumed_digests[digest] = observer_ticket.expires_at
                try:
                    await self._connect_observer(websocket, actor_id, observer_ticket.lease)
                except _ObserverStreamExit as stream_exit:
                    # The observer loop classified its own exit (doc 11
                    # section 2.3): close with its code and reason here, so
                    # the generic boundary below never sees the exception.
                    # The human path's boundary behaviour is unchanged.
                    try:
                        await websocket.close(
                            code=stream_exit.close_code, reason=stream_exit.reason,
                        )
                    except Exception:
                        pass
                return
            ticket = self._tickets.pop(digest, None)
            if ticket is None:
                consumed = digest in self._consumed_digests
                raise ViewerRejectedError(
                    "Viewer ticket is unavailable.",
                    reason="ticket_consumed" if consumed else "ticket_invalid",
                    detail="ticket_reused" if consumed else "ticket_unknown",
                )
            if ticket.expires_at <= datetime.now(UTC):
                raise ViewerRejectedError(
                    "Viewer ticket is unavailable.",
                    reason="ticket_expired", detail="ticket_expired",
                )
            self._consumed_digests[digest] = ticket.expires_at
            lease = self._leases.get(ticket.lease.lease_id)
            if lease is None:
                raise ViewerRejectedError(
                    "Viewer authority is unavailable.",
                    reason="no_session", detail="lease_gone",
                )
            if actor_id != lease.actor_id:
                raise ViewerRejectedError(
                    "Viewer authority is unavailable.",
                    reason="authority_unmet", detail="actor_mismatch",
                )
            if lease.expires_at <= datetime.now(UTC):
                raise ViewerRejectedError(
                    "Viewer authority is unavailable.",
                    reason="lease_expired", detail="lease_expired",
                )
            if not await self._permitted(cookie, lease):
                raise ViewerRejectedError(
                    "Viewer authority is unavailable.",
                    reason="authority_unmet", detail="permitted_false",
                )
            if lease.handle.session_id in self._connected:
                raise ViewerRejectedError(
                    "Viewer authority is unavailable.",
                    reason="authority_unmet", detail="already_connected",
                )
            self._connected.add(lease.handle.session_id)
            registered = True
            try:
                await self._owner.attach(lease)
            except ViewerRejectedError:
                raise ViewerRejectedError(
                    "Viewer authority is unavailable.",
                    reason="owner_gone", detail="attach_failed",
                ) from None
            attached = True
            self._attached.add(lease.lease_id)

            async def send_frames() -> None:
                previous_diagnostics: list[dict[str, str | int]] = []
                # Human view rides the same CDP screencast as the
                # observer (U-P3-05) instead of 2 fps screenshot polls,
                # when the owner offers it and no observer already owns
                # the stream for this browser.
                start_screencast = getattr(self._owner, "start_screencast", None)
                use_screencast = (
                    callable(start_screencast)
                    and callable(getattr(self._owner, "next_screencast_frame", None))
                    and lease.handle.session_id not in self._observing
                )
                if use_screencast:
                    await start_screencast(lease.handle, generation=lease.generation)
                last_diagnostics_check = 0.0
                try:
                    while True:
                        current = self._leases[lease.lease_id]
                        if not await self._permitted(cookie, current):
                            break
                        if use_screencast:
                            frame = await self._owner.next_screencast_frame(
                                current.handle, generation=current.generation,
                            )
                        else:
                            frame = await self._owner.frame(current)
                        if not await self._permitted(cookie, current):
                            break
                        async with asyncio.timeout(5):
                            await websocket.send_bytes(frame)
                        if use_screencast and time.monotonic() - last_diagnostics_check < 0.5:
                            continue
                        last_diagnostics_check = time.monotonic()
                        diagnostics = getattr(self._owner, "diagnostics", None)
                        if callable(diagnostics):
                            snapshot = await cast(
                                Callable[[OwnerLease], Awaitable[tuple[dict[str, str | int], ...]]],
                                diagnostics,
                            )(current)
                            # Rebuild the fixed schema here: no owner payload can leak
                            # a URL, cookie, exception or private page content.
                            safe_snapshot: list[dict[str, str | int]] = []
                            for entry in snapshot[:18]:
                                reason, destination, count = (
                                    entry.get("reason"), entry.get("destination"), entry.get("count")
                                )
                                if (reason in NETWORK_DIAGNOSTIC_REASONS
                                        and destination in NETWORK_DIAGNOSTIC_DESTINATIONS
                                        and type(count) is int and 1 <= count <= 128):
                                    safe_snapshot.append({
                                        "reason": reason, "destination": destination, "count": count,
                                    })
                            if not await self._permitted(cookie, current):
                                break
                            if safe_snapshot != previous_diagnostics:
                                async with asyncio.timeout(5):
                                    await websocket.send_json({"network_diagnostics": safe_snapshot})
                                previous_diagnostics = safe_snapshot
                        if not use_screencast:
                            await asyncio.sleep(0.5)
                    raise ViewerRejectedError(
                        "Viewer authority is unavailable.",
                        reason="authority_unmet",
                        detail="permitted_revoked_midstream",
                    )
                finally:
                    if use_screencast:
                        try:
                            await self._owner.stop_screencast(lease.handle)
                        except Exception:
                            pass

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
        except Exception as exc:
            # Only a safe close code leaves the boundary. No payload or exception
            # text may reach logs, traces, Kafka, artifacts or error responses.
            # The refusal class (doc 24 section 5.3) is safe on the wire for
            # this authenticated caller; the structured log line records the
            # class, the sub-condition and the session id — never a ticket
            # digest, a cookie value, or exception text beyond its type.
            reason = (
                exc.reason
                if isinstance(exc, ViewerRejectedError)
                and exc.reason in CONNECT_REFUSAL_REASONS
                else "gateway_error"
            )
            logger.warning(
                "viewer connect refused: class=%s detail=%s session=%s type=%s",
                reason,
                exc.detail if isinstance(exc, ViewerRejectedError) else None,
                lease.handle.session_id if lease is not None else None,
                type(exc).__name__,
            )
            try:
                await websocket.close(code=1008, reason=reason)
            except Exception:
                pass
        finally:
            if lease is not None and registered:
                detached_lease_id = None
                if attached:
                    try:
                        # Renewals change expiry while retaining this connection's
                        # identity. Detach its current lease so a held drag releases.
                        current = self._leases.get(lease.lease_id, lease)
                        if (current.handle == lease.handle and current.actor_id == lease.actor_id
                                and current.generation == lease.generation):
                            await self._owner.detach(current)
                            detached_lease_id = current.lease_id
                            # Detach ends transport, but the owner retains this
                            # lease for reconnect. Renew its expiry even while
                            # disconnected so the next attach has the same lease.
                    except Exception:
                        pass
                self._connected.discard(lease.handle.session_id)
                await self.prune_expired(detached_lease_id=detached_lease_id)
