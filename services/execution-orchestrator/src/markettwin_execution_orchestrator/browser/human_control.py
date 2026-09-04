"""Same-context human-control state transitions.

This module owns only the browser-side control boundary. The Control API and
persistence layers own authorization, leases, and the user workflow. A future
interactive viewer must attach to this exact context and must not create a
replacement browser session.
"""

from markettwin_execution_orchestrator.browser.evidence import start_trace, stop_trace
from markettwin_execution_orchestrator.browser.errors import BrowserSessionStateError
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession


async def begin_human_control(session: JourneyBrowserSession) -> None:
    """Disable agent evidence/tool capture before a human enters secrets."""

    if session.state != "open":
        raise BrowserSessionStateError(
            f"Human control requires an open session; current state is {session.state}."
        )
    await stop_trace(session)
    session.capture_enabled = False
    session.state = "human_control"


async def end_human_control(session: JourneyBrowserSession) -> None:
    """Return the same BrowserContext to the agent after verified handoff."""

    if session.state != "human_control":
        raise BrowserSessionStateError(
            "Cannot resume agent control because human control is not active."
        )
    session.capture_enabled = True
    session.state = "open"
    await start_trace(session)
