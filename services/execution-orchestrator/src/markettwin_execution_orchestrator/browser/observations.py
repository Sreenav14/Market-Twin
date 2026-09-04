"""Compact, model-safe browser observations."""

from pathlib import Path

from markettwin_execution_orchestrator.browser.contracts import BrowserObservation
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession


async def build_observation(
    session: JourneyBrowserSession,
    *,
    screenshot_path: Path | None = None,
) -> BrowserObservation:
    """Return current page state and drain per-action error buffers."""

    try:
        aria_snapshot = await session.page.locator("body").aria_snapshot(
            timeout=session.timeout_ms,
        )
    except Exception:
        aria_snapshot = ""

    accessibility_path: Path | None = None
    if session.capture_enabled and aria_snapshot:
        accessibility_path = session.artifact_directory / (
            f"action-{session.action_number:04d}-accessibility.yml"
        )
        accessibility_path.write_text(aria_snapshot, encoding="utf-8")

    observation = BrowserObservation(
        url=session.page.url,
        title=await session.page.title(),
        aria_snapshot=aria_snapshot,
        console_errors_since_last_action=tuple(session.event_buffer.console_errors),
        page_errors_since_last_action=tuple(session.event_buffer.page_errors),
        failed_requests_since_last_action=tuple(session.event_buffer.failed_requests),
        accessibility_snapshot_path=str(accessibility_path) if accessibility_path else None,
        page_count=len(session.context.pages),
        action_number=session.action_number,
        screenshot_path=str(screenshot_path) if screenshot_path else None,
    )
    session.event_buffer.console_errors.clear()
    session.event_buffer.page_errors.clear()
    session.event_buffer.failed_requests.clear()
    return observation
