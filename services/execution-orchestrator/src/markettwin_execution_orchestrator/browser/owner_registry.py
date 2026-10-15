"""Process-local bridge from durable browser handles to their live Playwright owner."""

from uuid import UUID

from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.owner import (
    ControllerBrowserOwner,
    OwnerLease,
    ViewerInput,
    ViewerRejectedError,
)


class BrowserOwnerRegistry:
    """Resolve worker handoffs to the exact live context that created the handle."""

    def __init__(self) -> None:
        self._sessions: dict[
            UUID, tuple[BrowserSessionHandle, BrowserController, ControllerBrowserOwner]
        ] = {}

    def register(self, controller: BrowserController, handle: BrowserSessionHandle) -> None:
        if handle.session_id in self._sessions:
            raise RuntimeError("Browser session is already registered.")
        self._sessions[handle.session_id] = (
            handle,
            controller,
            ControllerBrowserOwner(controller),
        )

    def unregister(self, handle: BrowserSessionHandle) -> None:
        entry = self._sessions.get(handle.session_id)
        if entry is not None and entry[0] == handle:
            self._sessions.pop(handle.session_id, None)

    def handle(
        self,
        *,
        session_id: UUID,
        execution_id: UUID,
        journey_id: UUID,
    ) -> BrowserSessionHandle:
        entry = self._sessions.get(session_id)
        expected = BrowserSessionHandle(session_id, execution_id, journey_id)
        if entry is None or entry[0] != expected:
            raise ViewerRejectedError("Browser authority is unavailable.")
        return entry[0]

    def _owner(self, handle: BrowserSessionHandle) -> ControllerBrowserOwner:
        entry = self._sessions.get(handle.session_id)
        if entry is None or entry[0] != handle:
            raise ViewerRejectedError("Browser authority is unavailable.")
        return entry[2]

    async def begin_human_control(
        self, handle: BrowserSessionHandle, *, generation: int,
    ) -> None:
        entry = self._sessions[handle.session_id]
        self._owner(handle)
        await entry[1].ensure_human_control(handle=handle, generation=generation)

    async def attach(self, lease: OwnerLease) -> None:
        await self._owner(lease.handle).attach(lease)

    async def detach(self, lease: OwnerLease) -> None:
        await self._owner(lease.handle).detach(lease)

    async def renew(self, lease: OwnerLease) -> None:
        await self._owner(lease.handle).renew(lease)

    async def input(self, lease: OwnerLease, event: ViewerInput) -> None:
        await self._owner(lease.handle).input(lease, event)

    async def frame(self, lease: OwnerLease) -> bytes:
        return await self._owner(lease.handle).frame(lease)

    async def revoke(self, handle: BrowserSessionHandle, generation: int) -> None:
        await self._owner(handle).revoke(handle, generation)


browser_owner_registry = BrowserOwnerRegistry()
