"""Same-context human-control state transitions.

This module owns only the browser-side control boundary. The Control API and
persistence layers own authorization, leases, and the user workflow. A future
interactive viewer must attach to this exact context and must not create a
replacement browser session.
"""

from markettwin_execution_orchestrator.browser.errors import BrowserSessionStateError
from markettwin_execution_orchestrator.browser.evidence import start_trace, stop_trace
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession


async def begin_human_control(session: JourneyBrowserSession) -> None:
    """Disable agent evidence/tool capture before a human enters secrets."""

    if session.state != "open" or session.control_mode != "agent":
        raise BrowserSessionStateError(
            "Human control requires an open session under agent authority."
        )
    session.control_mode = "quiescing"
    session.capture_enabled = False
    session.authenticated_session = True
    session.event_buffer.clear_all()
    try:
        await stop_trace(session)
    except Exception:
        session.control_mode = "none"
        raise
    session.control_mode = "human"


async def end_human_control(
    session: JourneyBrowserSession,
    *,
    verified: bool = False,
    safe_to_capture: bool = False,
) -> None:
    """Resume only after trusted verification and a reviewed safe page."""

    if session.state != "open" or session.control_mode not in {"human", "verifying"}:
        raise BrowserSessionStateError(
            "Cannot resume agent control because human control is not active."
        )
    session.control_mode = "verifying"
    if not verified or not safe_to_capture:
        session.control_mode = "none"
        raise BrowserSessionStateError(
            "Agent control requires verified authentication and a reviewed safe page."
        )
    session.capture_enabled = True
    try:
        await start_trace(session)
    except Exception:
        session.capture_enabled = False
        session.control_mode = "none"
        raise
    session.control_mode = "agent"
