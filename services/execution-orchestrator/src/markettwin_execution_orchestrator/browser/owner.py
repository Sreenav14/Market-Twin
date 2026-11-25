"""Private same-context viewer adapter. No CDP endpoint or generic RPC is exposed."""

import asyncio
import base64
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol, cast
from uuid import UUID

from playwright.async_api import CDPSession, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel, ConfigDict, Field

from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserSessionStateError
from markettwin_execution_orchestrator.browser.offsite import validate_browsing_url, validate_human_url
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession


class ViewerRejectedError(RuntimeError):
    """Safe error with no input data, page content, or underlying browser error."""

    def __init__(
        self, message: str = "", *, reason: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.detail = detail


# Read-only observation: agent work and pending assistance only. Human control is excluded
# so an operator's entry is never exposed through the observation path.
OBSERVABLE_CONTROL_MODES = frozenset({"agent", "human_pending"})
OBSERVATION_CLEANUP_SECONDS = 0.25
OBSERVATION_MAX_BYTES = 2 * 1024 * 1024
VIEWER_OPERATION_SECONDS = 2.0
POINTER_RELEASE_SECONDS = 0.5
SCREENCAST_QUALITY = 70
SCREENCAST_MAX_WIDTH = 1280
SCREENCAST_FRAME_SECONDS = 5.0
POINTER_EVENTS = frozenset({"pointer_down", "pointer_move", "pointer_up", "pointer_cancel"})
NAVIGATION_COMMIT_TIMEOUT_MS = 1500


class ViewerInput(BaseModel):
    """Only this protocol may enter the owner; raw CDP methods are unsupported."""

    model_config = ConfigDict(extra="forbid", strict=True)
    sequence: int = Field(ge=1)
    event: Literal[
        "click", "text", "key", "scroll", "resize",
        "pointer_down", "pointer_move", "pointer_up", "pointer_cancel",
        "back", "forward", "reload",
    ]
    x: int = Field(default=0, ge=0, le=1920)
    y: int = Field(default=0, ge=0, le=1080)
    text: str = Field(default="", max_length=2048, repr=False)
    key: str = Field(default="", max_length=20)
    delta: int = Field(default=0, ge=-1000, le=1000)
    width: int = Field(default=1280, ge=320, le=1920)
    height: int = Field(default=900, ge=320, le=1080)


@dataclass(frozen=True, slots=True)
class OwnerLease:
    handle: BrowserSessionHandle
    actor_id: UUID
    lease_id: UUID
    generation: int
    expires_at: datetime
    request_id: UUID | None = None


@dataclass(slots=True)
class _ViewerConnection:
    lease: OwnerLease
    connected: bool = True
    sequence: int = 0
    input_window: datetime = field(default_factory=lambda: datetime.now(UTC))
    input_count: int = 0
    pointer_held: bool = False
    pointer_page: Page | None = None

@dataclass(slots=True)
class _ScreencastSource:
    """One persistent CDP screencast for one watched session.

    Frames arrive on the channel callback; only the latest frame is kept
    (latest-frame-only coalescing), every frame is acked, and the source
    stops when its last viewer detaches.
    """

    handle: BrowserSessionHandle
    generation: int
    channel: CDPSession
    latest_frame: bytes | None = None
    frame_event: asyncio.Event = field(default_factory=asyncio.Event)
    viewers: int = 0
    stopped: bool = False
    ack_failures: int = 0
    decode_failures: int = 0


class BrowserOwner(Protocol):
    async def attach(self, lease: OwnerLease) -> None: ...
    async def detach(self, lease: OwnerLease) -> None: ...
    async def renew(self, lease: OwnerLease) -> None: ...
    async def input(self, lease: OwnerLease, event: ViewerInput) -> None: ...
    async def frame(self, lease: OwnerLease) -> bytes: ...
    async def start_screencast(self, handle: BrowserSessionHandle, *, generation: int) -> None: ...
    async def next_screencast_frame(self, handle: BrowserSessionHandle, *, generation: int) -> bytes: ...
    async def stop_screencast(self, handle: BrowserSessionHandle) -> None: ...
    def screencast_stats(self, session_id: UUID) -> dict[str, int]: ...
    async def revoke(self, handle: BrowserSessionHandle, generation: int) -> None: ...


class ControllerBrowserOwner:
    """Internal adapter; callers must authorize the actor/lease before attachment.

    The external gateway must additionally revalidate the MarketTwin session,
    current DB lease and target entitlement for each frame and input. This class
    is not an unauthenticated public viewer service.
    """

    def __init__(self, controller: BrowserController) -> None:
        self._controller = controller
        self._connections: dict[UUID, _ViewerConnection] = {}
        self._screencasts: dict[UUID, _ScreencastSource] = {}
        # Separate from session.lock: agent actions hold that lock for whole
        # page scans, which would starve viewer attach past its timeout.
        self._screencast_locks: dict[UUID, asyncio.Lock] = {}

    def _session(self, handle: BrowserSessionHandle) -> JourneyBrowserSession:
        return self._controller._get_session(  # pyright: ignore[reportPrivateUsage]
            session_id=handle.session_id, execution_id=handle.execution_id,
            journey_id=handle.journey_id,
        )

    @asynccontextmanager
    async def _locked(
        self, session: JourneyBrowserSession, *, lease: OwnerLease | None = None,
    ) -> AsyncGenerator[None]:
        try:
            async with asyncio.timeout(VIEWER_OPERATION_SECONDS), session.lock:
                yield
        except TimeoutError:
            connection = self._connections.get(session.session_id)
            if connection is not None and connection.lease == lease:
                self._abandon_pointer(session, connection, connection.lease.generation)
            raise ViewerRejectedError("Viewer operation timed out.") from None

    @asynccontextmanager
    async def _screencast_locked(self, session_id: UUID) -> AsyncGenerator[None]:
        lock = self._screencast_locks.setdefault(session_id, asyncio.Lock())
        try:
            async with asyncio.timeout(VIEWER_OPERATION_SECONDS), lock:
                yield
        except TimeoutError:
            raise ViewerRejectedError("Viewer operation timed out.") from None

    def _abandon_pointer(
        self, session: JourneyBrowserSession, connection: _ViewerConnection, generation: int,
    ) -> None:
        current = self._connections.get(session.session_id)
        if connection.pointer_held and session.control_generation == generation and (
            current is None or current is connection
        ):
            # A stalled lock prevents safe release. Fence synchronously instead
            # of issuing mouse input outside the lock or reusing uncertain state.
            session.state = "failed"
            session.control_mode = "none"
            connection.connected = False
            if current is connection:
                self._connections.pop(session.session_id, None)

    async def _release_pointer(
        self, session: JourneyBrowserSession, connection: _ViewerConnection, generation: int,
    ) -> bool:
        """Release only this connection's button in its original live context.

        Called under the owner lock, including after an authority fence. This
        cleanup grants no new input permission and never moves the pointer.
        """
        if not connection.pointer_held:
            return True
        connection.pointer_held = False
        page, connection.pointer_page = connection.pointer_page, None
        current = self._connections.get(session.session_id)
        if session.control_generation != generation or (
            current is not None and current is not connection
        ):
            return False
        if (
            page is None or session.state != "open" or not session.browser.is_connected()
            or page.is_closed() or page.context is not session.context
        ):
            session.state = "failed"
            session.control_mode = "none"
            return False
        try:
            validate_human_url(session, page.url)
            async with asyncio.timeout(POINTER_RELEASE_SECONDS):
                await page.mouse.up(button="left")
            return True
        except Exception:
            # An uncertain held button must never reach a later human/agent
            # lease. Normal controller teardown will close this failed context.
            session.state = "failed"
            session.control_mode = "none"
            return False

    async def _fence_connection(
        self, session: JourneyBrowserSession, connection: _ViewerConnection,
    ) -> None:
        if self._connections.get(session.session_id) is not connection:
            return
        await self._release_pointer(session, connection, connection.lease.generation)
        if session.control_generation == connection.lease.generation:
            session.control_mode = "none"
        connection.connected = False
        self._connections.pop(session.session_id, None)

    async def _require_live(
        self, lease: OwnerLease, *, connected: bool = True,
    ) -> JourneyBrowserSession:
        try:
            return self._require(lease, connected=connected)
        except ViewerRejectedError:
            connection = self._connections.get(lease.handle.session_id)
            if connection is not None and connection.lease == lease and connection.pointer_held:
                await self._fence_connection(self._session(lease.handle), connection)
            raise

    def _require(self, lease: OwnerLease, *, connected: bool = True) -> JourneyBrowserSession:
        session = self._session(lease.handle)
        connection = self._connections.get(lease.handle.session_id)
        if (
            connection is None or connection.lease != lease
            or (connected and not connection.connected)
            or lease.expires_at <= datetime.now(UTC)
            or session.control_generation != lease.generation
            or session.control_mode != "human" or session.state != "open"
            or session.capture_enabled or session.tracing_active
            or not session.browser.is_connected()
        ):
            raise ViewerRejectedError("Viewer authority is unavailable.")
        try:
            validate_human_url(session, session.page.url)
        except Exception:
            raise ViewerRejectedError("Viewer origin is not authorized.") from None
        return session

    async def attach(self, lease: OwnerLease) -> None:
        session = self._session(lease.handle)
        async with self._locked(session):
            previous = self._connections.get(lease.handle.session_id)
            reconnect = (
                previous is not None and previous.lease == lease and not previous.connected
                and lease.generation == session.control_generation
            )
            if (
                lease.expires_at <= datetime.now(UTC)
                or (lease.generation <= session.control_generation and not reconnect)
                or session.control_mode != "human" or session.capture_enabled
                or session.tracing_active or session.state != "open"
                or not session.browser.is_connected()
            ):
                raise ViewerRejectedError("Viewer authority is unavailable.")
            if previous is not None and previous.pointer_held:
                if not await self._release_pointer(session, previous, session.control_generation):
                    await self._fence_connection(session, previous)
                    raise ViewerRejectedError("Viewer authority is unavailable.")
            session.control_generation = lease.generation
            if reconnect and previous is not None:
                previous.connected = True
                previous.sequence = 0
            else:
                self._connections[lease.handle.session_id] = _ViewerConnection(lease)

    async def detach(self, lease: OwnerLease) -> None:
        """End transport input without inventing a durable control generation."""
        session = self._session(lease.handle)
        async with self._locked(session, lease=lease):
            connection = self._connections.get(lease.handle.session_id)
            if connection is not None and connection.lease == lease:
                if not await self._release_pointer(session, connection, lease.generation):
                    await self._fence_connection(session, connection)
                connection.connected = False

    async def input(self, lease: OwnerLease, event: ViewerInput) -> None:
        session = self._session(lease.handle)
        async with self._locked(session, lease=lease):
            connection = self._connections.get(lease.handle.session_id)
            try:
                await self._require_live(lease)
                assert connection is not None
                await self._input(session, connection, event)
            except ViewerRejectedError:
                if connection is not None and connection.lease == lease and connection.pointer_held:
                    await self._fence_connection(session, connection)
                raise

    async def _input(
        self, session: JourneyBrowserSession, connection: _ViewerConnection, event: ViewerInput,
    ) -> None:
        now = datetime.now(UTC)
        if (now - connection.input_window).total_seconds() >= 1:
            connection.input_window, connection.input_count = now, 0
        if event.sequence <= connection.sequence or connection.input_count >= 30:
            raise ViewerRejectedError("Viewer input was rejected.")
        viewport = session.page.viewport_size
        if viewport is None:
            raise ViewerRejectedError("Viewer viewport is unavailable.")
        if (event.event == "click" or event.event in POINTER_EVENTS) and (
            event.x >= viewport["width"] or event.y >= viewport["height"]
        ):
            raise ViewerRejectedError("Viewer input was rejected.")
        if event.event == "pointer_down":
            if connection.pointer_held:
                raise ViewerRejectedError("Viewer pointer transition was rejected.")
        elif event.event in POINTER_EVENTS:
            if not connection.pointer_held or connection.pointer_page is not session.page:
                raise ViewerRejectedError("Viewer pointer transition was rejected.")
        elif connection.pointer_held:
            raise ViewerRejectedError("Viewer pointer transition was rejected.")
        if event.event == "key" and event.key not in {
            "Tab", "Shift+Tab", "Enter", "Backspace", "Delete", "Escape",
            "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End",
        }:
            raise ViewerRejectedError("Viewer input was rejected.")
        # Consume before dispatch: a timeout must never enable replay.
        connection.sequence = event.sequence
        connection.input_count += 1
        page = session.page
        try:
            if event.event == "click":
                await page.mouse.move(event.x, event.y)
                self._require(connection.lease)
                if session.page is not page:
                    raise ViewerRejectedError("Viewer page changed.")
                connection.pointer_page = page
                connection.pointer_held = True
                await page.mouse.down(button="left")
                self._require(connection.lease)
                if session.page is not page:
                    raise ViewerRejectedError("Viewer page changed.")
                await page.mouse.up(button="left")
                connection.pointer_held = False
                connection.pointer_page = None
            elif event.event == "pointer_down":
                await page.mouse.move(event.x, event.y)
                self._require(connection.lease)
                if session.page is not page:
                    raise ViewerRejectedError("Viewer page changed.")
                connection.pointer_page = page
                connection.pointer_held = True
                await page.mouse.down(button="left")
            elif event.event == "pointer_move":
                await page.mouse.move(event.x, event.y)
            elif event.event in {"pointer_up", "pointer_cancel"}:
                if event.event == "pointer_up":
                    await page.mouse.move(event.x, event.y)
                    self._require(connection.lease)
                    if session.page is not page:
                        raise ViewerRejectedError("Viewer page changed.")
                await page.mouse.up(button="left")
                connection.pointer_held = False
                connection.pointer_page = None
            elif event.event == "text":
                await session.page.keyboard.insert_text(event.text)
            elif event.event == "key":
                await session.page.keyboard.press(event.key)
            elif event.event == "scroll":
                await session.page.mouse.wheel(0, event.delta)
            elif event.event == "resize":
                await session.page.set_viewport_size({
                    "width": event.width, "height": event.height,
                })
            elif event.event in {"back", "forward", "reload"}:
                navigate = {
                    "back": page.go_back, "forward": page.go_forward, "reload": page.reload,
                }[event.event]
                try:
                    await navigate(wait_until="commit", timeout=NAVIGATION_COMMIT_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    # The command was dispatched. A slow target can still commit
                    # after this wait, so keep the lease and do not retry it.
                    pass
        except BaseException as error:
            # Playwright exceptions can include entered text/URLs. Fence
            # uncertain input and expose only this safe error.
            await self._fence_connection(session, connection)
            if isinstance(error, asyncio.CancelledError):
                raise
            raise ViewerRejectedError("Viewer input could not be confirmed.") from None

    async def renew(self, lease: OwnerLease) -> None:
        session = self._session(lease.handle)
        async with self._locked(session, lease=lease):
            connection = self._connections.get(lease.handle.session_id)
            if connection is None:
                raise ViewerRejectedError("Viewer authority is unavailable.")
            previous = connection.lease
            await self._require_live(previous, connected=False)
            if (
                lease.handle != previous.handle or lease.actor_id != previous.actor_id
                or lease.lease_id != previous.lease_id or lease.generation != previous.generation
                or lease.expires_at < previous.expires_at
            ):
                raise ViewerRejectedError("Viewer renewal was rejected.")
            connection.lease = lease

    async def frame(self, lease: OwnerLease) -> bytes:
        session = self._session(lease.handle)
        async with self._locked(session, lease=lease):
            await self._require_live(lease)
            channel = None
            try:
                channel = await session.context.new_cdp_session(session.page)
                send = cast(
                    Callable[[str, dict[str, object]], Awaitable[dict[str, object]]],
                    channel.send,  # pyright: ignore[reportUnknownMemberType]
                )
                result = await send("Page.captureScreenshot", {
                    "format": "jpeg", "quality": 65,
                    "captureBeyondViewport": False,
                })
                await self._require_live(lease)
                return base64.b64decode(cast(str, result["data"]), validate=True)
            except BaseException as error:
                connection = self._connections.get(session.session_id)
                if connection is not None and connection.lease == lease:
                    await self._fence_connection(session, connection)
                if isinstance(error, asyncio.CancelledError):
                    raise
                raise ViewerRejectedError("Viewer frame is unavailable.") from None
            finally:
                if channel is not None:
                    try:
                        async with asyncio.timeout(OBSERVATION_CLEANUP_SECONDS):
                            await channel.detach()
                    except Exception:
                        pass

    async def diagnostics(self, lease: OwnerLease) -> tuple[dict[str, str | int], ...]:
        session = self._session(lease.handle)
        async with self._locked(session, lease=lease):
            await self._require_live(lease)
            return self._controller.human_network_diagnostics(handle=lease.handle)

    def _screencast_allowed(
        self, session: JourneyBrowserSession, generation: int,
    ) -> None:
        """Watchable states: an agent or pending browser (observer path), or the
        attached human-control connection (takeover path). Nothing else."""
        if session.control_mode == "human":
            connection = self._connections.get(session.session_id)
            if (
                connection is None or not connection.connected
                or connection.lease.generation != generation
                or connection.lease.expires_at <= datetime.now(UTC)
                or session.capture_enabled or session.tracing_active
            ):
                raise ViewerRejectedError("Browser observation is unavailable.")
        elif session.control_mode not in OBSERVABLE_CONTROL_MODES:
            raise ViewerRejectedError("Browser observation is unavailable.")
        if (
            session.control_generation != generation
            or session.state != "open"
            or not session.browser.is_connected()
        ):
            raise ViewerRejectedError("Browser observation is unavailable.")
        try:
            if session.control_mode == "human":
                validate_human_url(session, session.page.url)
            else:
                validate_browsing_url(session, session.page.url)
        except Exception:
            raise ViewerRejectedError("Browser observation is unavailable.") from None

    async def _ack_screencast_frame(self, source: _ScreencastSource, session_id: int) -> None:
        try:
            send = cast(
                Callable[[str, dict[str, object]], Awaitable[dict[str, object]]],
                source.channel.send,  # pyright: ignore[reportUnknownMemberType]
            )
            await send("Page.screencastFrameAck", {"sessionId": session_id})
        except Exception:
            source.ack_failures += 1

    def screencast_stats(self, session_id: UUID) -> dict[str, int]:
        source = self._screencasts.get(session_id)
        return {"ack_failures": source.ack_failures, "decode_failures": source.decode_failures} if source else {}

    async def start_screencast(self, handle: BrowserSessionHandle, *, generation: int) -> None:
        """Start (or join) the one persistent screencast for a watched session."""
        session = self._session(handle)
        async with self._screencast_locked(handle.session_id):
            self._screencast_allowed(session, generation)
            existing = self._screencasts.get(handle.session_id)
            if existing is not None and existing.generation == generation and not existing.stopped:
                existing.viewers += 1
                return
            if existing is not None:
                await self._stop_screencast_source(existing)
            channel = await session.context.new_cdp_session(session.page)
            source = _ScreencastSource(handle=handle, generation=generation, channel=channel, viewers=1)
            source.frame_event = session.live_view_changed
            source.frame_event.clear()

            def on_frame(params: dict[str, object]) -> None:
                if source.stopped:
                    return
                # Even rejected frames must be acknowledged or CDP can stop sending.
                frame_session = params.get("sessionId")
                if isinstance(frame_session, int):
                    asyncio.ensure_future(self._ack_screencast_frame(source, frame_session))
                try:
                    data = base64.b64decode(cast(str, params["data"]), validate=True)
                except Exception:
                    source.decode_failures += 1
                    return
                if len(data) > OBSERVATION_MAX_BYTES:
                    return
                # Latest-frame-only coalescing: a slow viewer never builds a backlog.
                source.latest_frame = data
                source.frame_event.set()

            channel.on("Page.screencastFrame", on_frame)
            send = cast(
                Callable[[str, dict[str, object]], Awaitable[dict[str, object]]],
                channel.send,  # pyright: ignore[reportUnknownMemberType]
            )
            try:
                await send("Page.startScreencast", {
                    "format": "jpeg", "quality": SCREENCAST_QUALITY,
                    "maxWidth": SCREENCAST_MAX_WIDTH, "everyNthFrame": 1,
                })
            except Exception:
                try:
                    await channel.detach()
                except Exception:
                    pass
                raise ViewerRejectedError("Browser observation is unavailable.") from None
            self._screencasts[handle.session_id] = source
        # A static page may not repaint after startScreencast. Seed the first
        # view once, then use repaint-driven frames for the rest of the stream.
        # Do not replace a fresher frame that arrived while capture awaited CDP.
        if source.latest_frame is None:
            try:
                async with asyncio.timeout(VIEWER_OPERATION_SECONDS):
                    initial = await send("Page.captureScreenshot", {
                        "format": "jpeg", "quality": SCREENCAST_QUALITY,
                        "captureBeyondViewport": False,
                    })
                self._screencast_allowed(session, generation)
                data = base64.b64decode(cast(str, initial["data"]), validate=True)
                if (not source.stopped and source.latest_frame is None
                        and len(data) <= OBSERVATION_MAX_BYTES):
                    source.latest_frame = data
                    source.frame_event.set()
            except ViewerRejectedError:
                await self._stop_screencast_source(source)
                raise
            except Exception:
                # Native screencast delivery can still provide the first view.
                pass

    async def next_screencast_frame(self, handle: BrowserSessionHandle, *, generation: int) -> bytes:
        """Wait for the newest screencast frame. Never captures a screenshot and
        never holds the session lock, so watching cannot stall the executor."""
        source = self._screencasts.get(handle.session_id)
        if source is None or source.generation != generation or source.stopped:
            raise ViewerRejectedError("Browser observation is unavailable.")
        self._screencast_allowed(self._session(handle), generation)
        try:
            async with asyncio.timeout(SCREENCAST_FRAME_SECONDS):
                await source.frame_event.wait()
                while source.latest_frame is None and not source.stopped:
                    source.frame_event.clear()
                    await source.frame_event.wait()
        except TimeoutError:
            # CDP only emits on repaint; a still page must keep the stream open.
            if source.latest_frame is None:
                raise ViewerRejectedError("Browser frame is unavailable.") from None
        source.frame_event.clear()
        if source.stopped:
            raise ViewerRejectedError("Browser observation is unavailable.")
        if source.latest_frame is None:
            raise ViewerRejectedError("Browser frame is unavailable.")
        session = self._session(handle)
        self._screencast_allowed(session, generation)
        return source.latest_frame

    def current_observer_frame(
        self, handle: BrowserSessionHandle, *, generation: int,
    ) -> tuple[bytes, dict[str, object]]:
        """Read newest pixels after DB authorization, without JPEG recompression."""
        session = self._session(handle)
        self._screencast_allowed(session, generation)
        source = self._screencasts.get(handle.session_id)
        if (source is None or source.stopped or source.generation != generation
                or source.latest_frame is None):
            raise ViewerRejectedError("Browser observation is unavailable.")
        target = session.live_click_target if session.control_mode == "agent" else None
        pointer = None
        if (target is not None
                and target.width > 0 and target.height > 0
                and 0 <= target.x < target.width and 0 <= target.y < target.height):
            pointer = {"x": target.x / target.width, "y": target.y / target.height}
        return source.latest_frame, {"type": "agent_pointer", "pointer": pointer}

    async def stop_screencast(self, handle: BrowserSessionHandle) -> None:
        """Detach one viewer; the screencast stops with its last viewer."""
        source = self._screencasts.get(handle.session_id)
        if source is None:
            return
        source.viewers -= 1
        if source.viewers > 0:
            return
        async with self._screencast_locked(handle.session_id):
            await self._stop_screencast_source(source)

    async def _stop_screencast_source(self, source: _ScreencastSource) -> None:
        if self._screencasts.get(source.handle.session_id) is source:
            self._screencasts.pop(source.handle.session_id, None)
        source.stopped = True
        source.frame_event.set()
        send = cast(
            Callable[[str, dict[str, object]], Awaitable[dict[str, object]]],
            source.channel.send,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            async with asyncio.timeout(OBSERVATION_CLEANUP_SECONDS):
                await send("Page.stopScreencast", {})
        except Exception:
            pass
        try:
            async with asyncio.timeout(OBSERVATION_CLEANUP_SECONDS):
                await source.channel.detach()
        except Exception:
            pass

    async def revoke(self, handle: BrowserSessionHandle, generation: int) -> None:
        session = self._session(handle)
        if generation < session.control_generation or (
            generation == session.control_generation and (
                session.control_mode != "verifying" or handle.session_id in self._connections
            )
        ):
            raise BrowserSessionStateError("A newer control generation is required.")
        # Fence queued input synchronously before waiting for an in-flight event.
        session.control_generation = generation
        session.control_mode = "verifying"
        connection = self._connections.pop(handle.session_id, None)
        try:
            async with self._locked(session):
                if connection is not None:
                    await self._release_pointer(session, connection, generation)
                    connection.connected = False
                session.event_buffer.clear_all()
        except ViewerRejectedError:
            if connection is not None:
                self._abandon_pointer(session, connection, generation)
            raise
