"""Read-only observation must not outlive its authenticated user session."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.owner import ViewerRejectedError
from markettwin_execution_orchestrator.browser.viewer_gateway import ObserverLease, ViewerGateway


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
            if not authority.active:
                raise ViewerRejectedError("End synthetic stream.")
            authority.active = False
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
    with pytest.raises(ViewerRejectedError):
        await gateway._connect_observer(socket, actor_id, lease)
    assert socket.frames == []
    assert owner.stopped
    assert lease.handle.session_id not in gateway._observing
