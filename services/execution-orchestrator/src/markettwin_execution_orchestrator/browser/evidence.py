"""Local browser-evidence capture for MarketTwin Journey execution."""

import json
from dataclasses import asdict
from pathlib import Path

from PIL import Image
from playwright.async_api import Locator

from markettwin_execution_orchestrator.browser.contracts import (
    ElementBoundingBox,
)
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession

FOCUSED_CROP_PADDING_PX = 48


def bounding_box_intersects_viewport(
    *,
    bounding_box: ElementBoundingBox,
    viewport_width: int,
    viewport_height: int,
) -> bool:
    """Return whether an element box contains pixels inside the viewport."""

    return (
        bounding_box.width > 0
        and bounding_box.height > 0
        and bounding_box.x < viewport_width
        and bounding_box.y < viewport_height
        and bounding_box.x + bounding_box.width > 0
        and bounding_box.y + bounding_box.height > 0
    )


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
    await session.page.screenshot(path=path, full_page=False)
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
async def capture_element_screenshot(
    session: JourneyBrowserSession,
    *,
    locator: Locator,
) -> Path | None:
    """Capture one visible element as focused PNG evidence."""

    if not session.capture_enabled:
        return None

    path = session.artifact_directory / (
        f"action-{session.action_number:04d}-element.png"
    )

    await locator.screenshot(
        path=path,
        timeout=session.timeout_ms,
    )

    return path

def crop_viewport_screenshot(
    *,
    viewport_path: Path,
    bounding_box: ElementBoundingBox,
    output_path: Path,
    padding: int = FOCUSED_CROP_PADDING_PX,
) -> Path:
    """Create focused evidence from an already captured viewport screenshot."""

    if padding < 0:
        raise ValueError("Crop padding cannot be negative.")

    with Image.open(viewport_path) as image:
        if not bounding_box_intersects_viewport(
            bounding_box=bounding_box,
            viewport_width=image.width,
            viewport_height=image.height,
        ):
            raise ValueError(
                "Focused crop does not intersect the viewport."
            )

        left = max(
            0,
            bounding_box.x - padding,
        )
        top = max(
            0,
            bounding_box.y - padding,
        )
        right = min(
            image.width,
            bounding_box.x
            + bounding_box.width
            + padding,
        )
        bottom = min(
            image.height,
            bounding_box.y
            + bounding_box.height
            + padding,
        )

        if right <= left or bottom <= top:
            raise ValueError(
                "Focused crop does not intersect the viewport."
            )

        cropped = image.crop(
            (left, top, right, bottom)
        )

        cropped.save(
            output_path,
            format="PNG",
        )

    return output_path
