"""Read-only observation must not outlive its authenticated user session."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest
from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.viewer_gateway import (
    ObserverLease,
    ViewerGateway,
    _ObserverStreamExit,
)
from markettwin_execution_orchestrator.browser.viewer_authority import DatabaseViewerAuthority


async def test_observer_drops_frame_if_login_is_revoked_during_capture() -> None:
    actor_id = uuid4()

    class Authority:
        active = True

        async def actor(self, cookie):
            return actor_id if cookie == "synthetic-session" and self.active else None

        async def observer_permitted(self, actor, handle, generation):
            # Entitlement stays valid: only the login session was revoked.
            return True

    authority = Authority()

    class Owner:
        stopped = False

        async def start_screencast(self, handle, *, generation):
            pass

        async def next_screencast_frame(self, handle, *, generation):
            # The login is revoked while this capture is in flight. The
            # capture never completes -- the gateway's bounded wait
            # cancels it -- so the private frame is never delivered.
            authority.active = False
            await asyncio.sleep(30)
            return b"private-frame"

        async def stop_screencast(self, handle):
            self.stopped = True

    class Socket:
        cookies = {"markettwin_session": "synthetic-session"}
        frames = []

        async def send_bytes(self, frame):
            self.frames.append(frame)

    owner, socket = Owner(), Socket()
    gateway = ViewerGateway(owner, authority, allowed_origins=frozenset({"https://fixture.invalid"}))
    lease = ObserverLease(
        BrowserSessionHandle(uuid4(), uuid4(), uuid4()), actor_id, 0,
        datetime.now(UTC) + timedelta(minutes=15),
    )
    started = time.monotonic()
    with pytest.raises(_ObserverStreamExit) as caught:
        await gateway._connect_observer(socket, actor_id, lease)
    elapsed = time.monotonic() - started
    # Doc 11: revocation takes effect at the next authority cadence check
    # (<= 2 s) and ends the stream with the reason-coded close, instead of
    # the old per-frame re-check raising out of the loop.
    assert caught.value.reason == "authority_revoked"
    assert caught.value.close_code == 1008
    assert 1.8 <= elapsed <= 4.0
    assert socket.frames == []
    assert owner.stopped
    assert lease.handle.session_id not in gateway._observing


async def test_combined_authority_delivers_newest_frame_and_pointer_without_duplicate_pixels():
    actor_id = uuid4()
    newest_frame = b"newest-frame"

    class Authority:
        checks = 0

        async def actor(self, cookie):
            return actor_id

        async def observer_permitted(self, actor, handle, generation):
            return True

        async def observer_permitted_session(self, cookie, actor, handle, generation):
            self.checks += 1
            owner.latest = newest_frame
            return self.checks <= 2

    class Owner:
        latest = b"stale-frame"

        async def start_screencast(self, handle, *, generation):
            pass

        async def next_screencast_frame(self, handle, *, generation):
            # The wait's own return is stale by the time it lands; the
            # snapshot below holds the newest frame. The sleep paces the
            # loop so the 2 s authority cadence drives the checks.
            await asyncio.sleep(0.7)
            self.latest = newest_frame
            return b"stale-frame"

        def current_observer_frame(self, handle, *, generation):
            return self.latest, {"type": "agent_pointer", "pointer": {"x": 0.5, "y": 0.5}}

        async def stop_screencast(self, handle):
            pass

    class Socket:
        cookies = {"markettwin_session": "synthetic-session"}

        def __init__(self):
            self.frames = []
            self.updates = []

        async def send_bytes(self, frame):
            self.frames.append((time.monotonic(), frame))

        async def send_json(self, update):
            self.updates.append(update)

    owner, authority, socket = Owner(), Authority(), Socket()
    gateway = ViewerGateway(owner, authority, allowed_origins=frozenset({"https://fixture.invalid"}))
    lease = ObserverLease(BrowserSessionHandle(uuid4(), uuid4(), uuid4()), actor_id, 0,
                          datetime.now(UTC) + timedelta(minutes=15))
    started = time.monotonic()
    with pytest.raises(_ObserverStreamExit) as caught:
        await gateway._connect_observer(socket, actor_id, lease)
    elapsed = time.monotonic() - started
    # Doc 11: the combined check runs on the 2 s cadence, not per frame.
    # The third check denies and ends the stream with the reason-coded
    # close -- revocation still stops both pixels and pointer metadata.
    assert caught.value.reason == "authority_revoked"
    assert caught.value.close_code == 1008
    assert authority.checks == 3
    assert elapsed >= 3.8  # Two permitted cadence checks precede the denial.
    # Only the newest frame is ever delivered -- the wait's stale return
    # is always discarded for the snapshot -- and the identical frame is
    # re-sent only as the >= 1 s heartbeat, never as duplicate pixels.
    assert socket.frames
    assert all(frame == newest_frame for _, frame in socket.frames)
    gaps = [later - earlier for (earlier, _), (later, _) in zip(socket.frames, socket.frames[1:])]
    assert all(gap >= 0.9 for gap in gaps)
    assert len(socket.updates) >= 2
    assert all(update["type"] == "agent_pointer" for update in socket.updates)


async def test_combined_observer_query_keeps_login_and_entitlement_checks():
    session = AsyncMock()
    session.scalar.return_value = uuid4()
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    authority = DatabaseViewerAuthority(factory, MagicMock())
    handle = BrowserSessionHandle(uuid4(), uuid4(), uuid4())
    assert not await authority.observer_permitted_session("", uuid4(), handle, 0)
    session.scalar.assert_not_called()
    assert await authority.observer_permitted_session("synthetic-session", uuid4(), handle, 0)
    session.scalar.assert_awaited_once()
    statement = str(session.scalar.call_args.args[0])
    for required in ("auth.user_sessions", "session_token_hash", "revoked_at IS NULL",
                     "idle_expires_at", "absolute_expires_at", "control_generation",
                     "workspace_members", "target_authorizations"):
        assert required in statement
    session.scalar.return_value = None
    assert not await authority.observer_permitted_session("synthetic-session", uuid4(), handle, 0)


async def test_stream_reuses_connection_without_caching_permissions():
    session = AsyncMock()
    session.scalar.side_effect = [uuid4(), None]
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    authority = DatabaseViewerAuthority(factory, MagicMock())
    handle = BrowserSessionHandle(uuid4(), uuid4(), uuid4())
    async with authority.observer_stream():
        assert await authority.observer_permitted_session("cookie", uuid4(), handle, 0)
        assert not await authority.observer_permitted_session("cookie", uuid4(), handle, 0)
    assert factory.call_count == 1
    session.connection.assert_awaited_once_with(
        execution_options={"isolation_level": "AUTOCOMMIT"})
    assert session.scalar.await_count == 2
    assert authority._stream_session.get() is None
