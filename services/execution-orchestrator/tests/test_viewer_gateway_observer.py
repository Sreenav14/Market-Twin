"""Observer-loop tests for the viewer gateway (doc 11).

The incumbent fakes in test_viewer_gateway.py cannot drive _connect_observer
(no screencast methods, no observer authority surface), so this sibling file
carries scripted observer-capable fakes and drives the loop directly with a
fake WebSocket. Two authority variants cover both in-loop branches: one
exposing observer_permitted_session (combined), one without it (the gather
fallback).
"""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.owner import OwnerLease, ViewerRejectedError
from markettwin_execution_orchestrator.browser.viewer_gateway import (
    ObserverLease,
    ViewerGateway,
    _ObserverStreamExit,
)

FRAME_A = b"synthetic-frame-a"
FRAME_B = b"synthetic-frame-b"
FRAME_C = b"synthetic-frame-c"
POINTER = {"type": "agent_pointer", "pointer": {"x": 0.25, "y": 0.5}}


class FakeSocket:
    """Records sends with monotonic timestamps; never retains a real client."""

    def __init__(self) -> None:
        self.cookies = {"markettwin_session": "synthetic-session"}
        self.bytes_sent: list[tuple[float, bytes]] = []
        self.json_sent: list[dict[str, object]] = []
        self.closed: list[tuple[int, str]] = []

    async def send_bytes(self, payload: bytes) -> None:
        self.bytes_sent.append((time.monotonic(), payload))

    async def send_json(self, payload: dict[str, object]) -> None:
        self.json_sent.append(payload)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed.append((code, reason))


class ScriptedOwner:
    """Frame script: (delay, frame-or-exception) per next_screencast_frame
    call; silence once the script is exhausted, like a static page."""

    def __init__(self, script: list[tuple[float, bytes | BaseException]]) -> None:
        self._script = list(script)
        self.latest: bytes | None = None
        self.started = 0
        self.stopped = 0

    async def start_screencast(self, handle: BrowserSessionHandle, *, generation: int) -> None:
        self.started += 1

    async def stop_screencast(self, handle: BrowserSessionHandle) -> None:
        self.stopped += 1

    async def next_screencast_frame(
        self, handle: BrowserSessionHandle, *, generation: int,
    ) -> bytes:
        if self._script:
            delay, outcome = self._script.pop(0)
            if delay:
                await asyncio.sleep(delay)
            if isinstance(outcome, BaseException):
                raise outcome
            self.latest = outcome
            return outcome
        await asyncio.sleep(30)  # Owner silence; the gateway wait cancels it.
        raise AssertionError("The gateway wait must cancel owner silence first.")

    def current_observer_frame(
        self, handle: BrowserSessionHandle, *, generation: int,
    ) -> tuple[bytes, dict[str, object]]:
        if self.latest is None:
            raise ViewerRejectedError("Browser frame is unavailable.")
        return self.latest, POINTER


class CombinedAuthority:
    """Exposes observer_permitted_session: the combined in-loop branch."""

    def __init__(self, actor_id: UUID) -> None:
        self.actor_id = actor_id
        self.session_result = True
        self.session_calls = 0
        self.permitted_calls = 0

    async def actor(self, session_cookie: str) -> UUID | None:
        return self.actor_id if session_cookie == "synthetic-session" else None

    async def permitted(self, actor_id: UUID, lease: OwnerLease) -> bool:
        return actor_id == self.actor_id

    async def refresh_lease(self, actor_id: UUID, lease_id: UUID) -> OwnerLease | None:
        return None

    async def observer_permitted(
        self, actor_id: UUID, handle: BrowserSessionHandle, generation: int,
    ) -> bool:
        self.permitted_calls += 1
        return actor_id == self.actor_id

    async def observer_permitted_session(
        self, cookie: str, actor_id: UUID, handle: BrowserSessionHandle, generation: int,
    ) -> bool:
        self.session_calls += 1
        return self.session_result and cookie == "synthetic-session"


class FallbackAuthority:
    """No observer_permitted_session: the gather fallback branch."""

    def __init__(self, actor_id: UUID) -> None:
        self.actor_id = actor_id
        self.actor_calls = 0
        self.permitted_calls = 0

    async def actor(self, session_cookie: str) -> UUID | None:
        self.actor_calls += 1
        return self.actor_id if session_cookie == "synthetic-session" else None

    async def permitted(self, actor_id: UUID, lease: OwnerLease) -> bool:
        return actor_id == self.actor_id

    async def refresh_lease(self, actor_id: UUID, lease_id: UUID) -> OwnerLease | None:
        return None

    async def observer_permitted(
        self, actor_id: UUID, handle: BrowserSessionHandle, generation: int,
    ) -> bool:
        self.permitted_calls += 1
        return actor_id == self.actor_id


def make_lease(actor_id: UUID, *, seconds: float = 60.0) -> ObserverLease:
    return ObserverLease(
        BrowserSessionHandle(uuid4(), uuid4(), uuid4()),
        actor_id,
        1,
        datetime.now(UTC) + timedelta(seconds=seconds),
    )


def make_gateway(owner: ScriptedOwner, authority: object) -> ViewerGateway:
    return ViewerGateway(
        owner, authority, allowed_origins=frozenset({"https://fixture.invalid"}),
    )


async def test_static_page_heartbeats_and_authority_cadence() -> None:
    """T1 (doc 11 section 3.1): one frame, then owner silence -> heartbeat
    resends at ~1 s cadence; authority consulted on connect, then <= once
    per 2 s inside the loop."""
    actor_id = uuid4()
    owner = ScriptedOwner([(0.0, FRAME_A)])
    authority = CombinedAuthority(actor_id)
    gateway = make_gateway(owner, authority)
    socket = FakeSocket()
    task = asyncio.create_task(
        gateway._connect_observer(socket, actor_id, make_lease(actor_id)),
    )
    await asyncio.sleep(3.6)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    sent = socket.bytes_sent
    assert len(sent) >= 4  # One new frame plus at least three heartbeats.
    assert sent[0][1] is FRAME_A
    assert all(payload is FRAME_A for _, payload in sent)
    gaps = [later - earlier for (earlier, _), (later, _) in zip(sent, sent[1:])]
    assert all(0.6 <= gap <= 1.7 for gap in gaps)
    stats = gateway.observer_stats()
    assert stats["frames"] == 1
    assert stats["heartbeats"] == len(sent) - 1
    assert authority.permitted_calls >= 1  # The connect-time gate.
    assert authority.session_calls == 1  # One fresh in-loop check in 3.6 s.


async def test_changing_frames_pass_through_immediately() -> None:
    """T2 (doc 11 section 3.2): new frames are sent on arrival, never held
    for the heartbeat tick."""
    actor_id = uuid4()
    owner = ScriptedOwner([(0.0, FRAME_A), (0.2, FRAME_B), (0.2, FRAME_C)])
    gateway = make_gateway(owner, CombinedAuthority(actor_id))
    socket = FakeSocket()
    task = asyncio.create_task(
        gateway._connect_observer(socket, actor_id, make_lease(actor_id)),
    )
    await asyncio.sleep(1.8)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    sent = socket.bytes_sent
    assert [payload for _, payload in sent[:3]] == [FRAME_A, FRAME_B, FRAME_C]
    assert sent[1][0] - sent[0][0] < 1.0
    assert sent[2][0] - sent[1][0] < 1.0
    assert len(sent) >= 4 and sent[3][1] is FRAME_C  # Then heartbeats of C.
    stats = gateway.observer_stats()
    assert stats["frames"] == 3
    assert stats["heartbeats"] == len(sent) - 3


async def test_authority_denial_exits_revoked_within_cadence() -> None:
    """T3 (doc 11 section 3.3): a denied fresh check breaks the loop within
    the 2 s cadence, classified authority_revoked / 1008."""
    actor_id = uuid4()
    owner = ScriptedOwner([(0.0, FRAME_A)])
    authority = CombinedAuthority(actor_id)
    gateway = make_gateway(owner, authority)
    socket = FakeSocket()
    started = time.monotonic()
    task = asyncio.create_task(
        gateway._connect_observer(socket, actor_id, make_lease(actor_id)),
    )
    await asyncio.sleep(0.5)
    authority.session_result = False
    with pytest.raises(_ObserverStreamExit) as caught:
        await task
    elapsed = time.monotonic() - started
    assert caught.value.reason == "authority_revoked"
    assert caught.value.close_code == 1008
    assert 1.8 <= elapsed <= 4.0
    assert gateway.observer_stats()["frames"] == 1


async def test_lease_expiry_beats_fresh_authority_cache() -> None:
    """T4 (doc 11 section 3.4): expiry is checked every iteration and never
    rides the cache, so it breaks the loop even with a permit cached at
    ~2 s. Uses the fallback authority so the gather branch is covered."""
    actor_id = uuid4()
    owner = ScriptedOwner([(0.0, FRAME_A)])
    authority = FallbackAuthority(actor_id)
    gateway = make_gateway(owner, authority)
    socket = FakeSocket()
    started = time.monotonic()
    task = asyncio.create_task(
        gateway._connect_observer(socket, actor_id, make_lease(actor_id, seconds=2.5)),
    )
    with pytest.raises(_ObserverStreamExit) as caught:
        await task
    elapsed = time.monotonic() - started
    assert caught.value.reason == "lease_expired"
    assert caught.value.close_code == 1008
    assert elapsed >= 2.5  # It did not exit on the fresh ~2 s permit.
    assert authority.actor_calls >= 2  # Connect gate + the gather fallback.
    assert authority.permitted_calls >= 2


async def test_owner_failure_exits_owner_gone() -> None:
    """Doc 11 section 2.3: an owner raise classifies owner_gone / 1011."""
    actor_id = uuid4()
    owner = ScriptedOwner([(0.0, ViewerRejectedError("Browser observation is unavailable."))])
    gateway = make_gateway(owner, CombinedAuthority(actor_id))
    task = asyncio.create_task(
        gateway._connect_observer(FakeSocket(), actor_id, make_lease(actor_id)),
    )
    with pytest.raises(_ObserverStreamExit) as caught:
        await task
    assert caught.value.reason == "owner_gone"
    assert caught.value.close_code == 1011


async def test_unexpected_failure_exits_stream_error() -> None:
    """Doc 11 section 2.3: anything else classifies stream_error / 1011."""
    actor_id = uuid4()
    owner = ScriptedOwner([(0.0, RuntimeError("synthetic owner failure"))])
    gateway = make_gateway(owner, CombinedAuthority(actor_id))
    task = asyncio.create_task(
        gateway._connect_observer(FakeSocket(), actor_id, make_lease(actor_id)),
    )
    with pytest.raises(_ObserverStreamExit) as caught:
        await task
    assert caught.value.reason == "stream_error"
    assert caught.value.close_code == 1011


async def test_connect_closes_observer_socket_with_exit_code_and_reason() -> None:
    """The classified exit reaches the wire through connect(): the observer
    branch closes with the carried code + reason, before the generic
    boundary (which would close 1008 with no reason) can see it."""
    actor_id = uuid4()
    owner = ScriptedOwner([(0.0, FRAME_A)])
    authority = CombinedAuthority(actor_id)
    authority.session_result = False  # First fresh in-loop check denies.
    gateway = make_gateway(owner, authority)
    lease = make_lease(actor_id)
    token = await gateway.issue_observer_ticket(actor_id, lease)

    class ConnectSocket(FakeSocket):
        headers = {"origin": "https://fixture.invalid"}
        url = SimpleNamespace(query="", scheme="wss")
        client = SimpleNamespace(host="203.0.113.7")
        accepted = False

        async def accept(self) -> None:
            self.accepted = True

        async def receive_text(self) -> str:
            return json.dumps({"ticket": token})

    socket = ConnectSocket()
    await gateway.connect(socket)
    assert socket.accepted
    assert socket.closed == [(1008, "authority_revoked")]
