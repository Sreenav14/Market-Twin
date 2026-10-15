"""Private same-context viewer adapter. No CDP endpoint or generic RPC is exposed."""

import base64
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserSessionStateError
from markettwin_execution_orchestrator.browser.policy import validate_target_url
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession


class ViewerRejectedError(RuntimeError):
    """Safe error with no input data, page content, or underlying browser error."""


class ViewerInput(BaseModel):
    """Only this protocol may enter the owner; raw CDP methods are unsupported."""

    model_config = ConfigDict(extra="forbid", strict=True)
    sequence: int = Field(ge=1)
    event: Literal["click", "text", "key", "scroll", "resize"]
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


class BrowserOwner(Protocol):
    async def attach(self, lease: OwnerLease) -> None: ...
    async def detach(self, lease: OwnerLease) -> None: ...
    async def renew(self, lease: OwnerLease) -> None: ...
    async def input(self, lease: OwnerLease, event: ViewerInput) -> None: ...
    async def frame(self, lease: OwnerLease) -> bytes: ...
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

    def _session(self, handle: BrowserSessionHandle) -> JourneyBrowserSession:
        return self._controller._get_session(  # pyright: ignore[reportPrivateUsage]
            session_id=handle.session_id, execution_id=handle.execution_id,
            journey_id=handle.journey_id,
        )

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
            validate_target_url(session.page.url, session.allowed_origins, session.network_policy)
        except Exception:
            raise ViewerRejectedError("Viewer origin is not authorized.") from None
        return session

    async def attach(self, lease: OwnerLease) -> None:
        session = self._session(lease.handle)
        async with session.lock:
            previous = self._connections.get(lease.handle.session_id)
            reconnect = (
                previous is not None and previous.lease == lease and not previous.connected
                and lease.generation == session.control_generation
            )
            if (
                lease.expires_at <= datetime.now(UTC)
                or (lease.generation <= session.control_generation and not reconnect)
                or session.control_mode != "human" or session.capture_enabled
                or session.tracing_active
            ):
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
        async with session.lock:
            connection = self._connections.get(lease.handle.session_id)
            if connection is not None and connection.lease.lease_id == lease.lease_id:
                connection.connected = False

    async def input(self, lease: OwnerLease, event: ViewerInput) -> None:
        session = self._session(lease.handle)
        async with session.lock:
            self._require(lease)
            connection = self._connections[lease.handle.session_id]
            now = datetime.now(UTC)
            if (now - connection.input_window).total_seconds() >= 1:
                connection.input_window, connection.input_count = now, 0
            if event.sequence <= connection.sequence or connection.input_count >= 30:
                raise ViewerRejectedError("Viewer input was rejected.")
            viewport = session.page.viewport_size
            if viewport is None:
                raise ViewerRejectedError("Viewer viewport is unavailable.")
            if event.event == "click" and (
                event.x >= viewport["width"] or event.y >= viewport["height"]
            ):
                raise ViewerRejectedError("Viewer input was rejected.")
            if event.event == "key" and event.key not in {
                "Tab", "Shift+Tab", "Enter", "Backspace", "Delete", "Escape",
                "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End",
            }:
                raise ViewerRejectedError("Viewer input was rejected.")
            # Consume before dispatch: a timeout must never enable replay.
            connection.sequence = event.sequence
            connection.input_count += 1
            try:
                if event.event == "click":
                    await session.page.mouse.click(event.x, event.y)
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
            except Exception:
                # Playwright exceptions can include entered text/URLs. Fence
                # uncertain input and expose only this safe error.
                session.control_mode = "none"
                self._connections.pop(lease.handle.session_id, None)
                raise ViewerRejectedError("Viewer input could not be confirmed.") from None

    async def renew(self, lease: OwnerLease) -> None:
        session = self._session(lease.handle)
        async with session.lock:
            connection = self._connections.get(lease.handle.session_id)
            if connection is None:
                raise ViewerRejectedError("Viewer authority is unavailable.")
            previous = connection.lease
            self._require(previous, connected=False)
            if (
                lease.handle != previous.handle or lease.actor_id != previous.actor_id
                or lease.lease_id != previous.lease_id or lease.generation != previous.generation
                or lease.expires_at < previous.expires_at
            ):
                raise ViewerRejectedError("Viewer renewal was rejected.")
            connection.lease = lease

    async def frame(self, lease: OwnerLease) -> bytes:
        session = self._session(lease.handle)
        async with session.lock:
            self._require(lease)
            channel = await session.context.new_cdp_session(session.page)
            try:
                send = cast(
                    Callable[[str, dict[str, object]], Awaitable[dict[str, object]]],
                    channel.send,  # pyright: ignore[reportUnknownMemberType]
                )
                result = await send("Page.captureScreenshot", {
                    "format": "jpeg", "quality": 65,
                    "captureBeyondViewport": False,
                })
                self._require(lease)
                return base64.b64decode(cast(str, result["data"]), validate=True)
            except Exception:
                raise ViewerRejectedError("Viewer frame is unavailable.") from None
            finally:
                await channel.detach()

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
        self._connections.pop(handle.session_id, None)
        async with session.lock:
            session.event_buffer.clear_all()
