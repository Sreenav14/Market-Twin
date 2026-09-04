"""Local browser-evidence capture for MarketTwin Journey execution."""

import json
from dataclasses import asdict
from pathlib import Path

from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession


async def start_trace(session: JourneyBrowserSession) -> None:
    """Start a new trace segment when evidence capture is allowed."""

    if session.tracing_active or not session.capture_enabled:
        return
    session.trace_segment += 1
    await session.context.tracing.start(
        screenshots=True,
        snapshots=True,
        sources=True,
    )
    session.tracing_active = True


async def stop_trace(session: JourneyBrowserSession) -> Path | None:
    """Stop the active trace segment and return its path."""

    if not session.tracing_active:
        return None
    path = session.artifact_directory / f"trace-{session.trace_segment:03d}.zip"
    await session.context.tracing.stop(path=path)
    session.tracing_active = False
    return path


async def capture_screenshot(
    session: JourneyBrowserSession,
    *,
    label: str,
) -> Path | None:
    """Capture a full-page PNG outside human-controlled secret entry."""

    if not session.capture_enabled:
        return None
    safe_label = "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in label.lower()
    ).strip("-") or "state"
    path = session.artifact_directory / (
        f"action-{session.action_number:04d}-{safe_label}.png"
    )
    await session.page.screenshot(path=path, full_page=True)
    return path


async def write_event_logs(session: JourneyBrowserSession) -> tuple[Path, Path, Path]:
    """Persist safe browser-error metadata collected for the Journey."""

    console_path = session.artifact_directory / "console-errors.json"
    page_path = session.artifact_directory / "page-errors.json"
    failed_path = session.artifact_directory / "failed-requests.json"
    console_path.write_text(
        json.dumps(session.event_buffer.all_console_errors, indent=2),
        encoding="utf-8",
    )
    page_path.write_text(
        json.dumps(session.event_buffer.all_page_errors, indent=2),
        encoding="utf-8",
    )
    failed_path.write_text(
        json.dumps(
            [asdict(item) for item in session.event_buffer.all_failed_requests],
            indent=2,
        ),
        encoding="utf-8",
    )
    return console_path, page_path, failed_path
