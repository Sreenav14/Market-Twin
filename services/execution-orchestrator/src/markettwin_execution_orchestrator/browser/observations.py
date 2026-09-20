"""Compact, model-safe browser observations."""

from pathlib import Path
from typing import TypedDict, cast

from markettwin_execution_orchestrator.browser.contracts import (
    BrowserObservation,
    ElementBoundingBox,
    VisibleElement,
)
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession

MAX_VISIBLE_ELEMENTS = 80
MAX_VISIBLE_ELEMENT_NAME_CHARS = 160


class RawElementBox(TypedDict):
    x: int
    y: int
    width: int
    height: int


class RawVisibleElement(TypedDict):
    role: str
    name: str
    tag: str
    enabled: bool
    level: int | None
    bounding_box: RawElementBox


class ViewportMetrics(TypedDict):
    """Current visible position inside the page."""

    width: int
    height: int
    scroll_y: int
    document_height: int


async def build_observation(
    session: JourneyBrowserSession,
    *,
    screenshot_path: Path | None = None,
    focused_screenshot_path: Path | None = None,
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

    raw_viewport_metrics = await session.page.evaluate(
        """
        () => ({
            width: window.innerWidth,
            height: window.innerHeight,
            scroll_y: Math.round(window.scrollY),
            document_height: Math.max(
                document.documentElement.scrollHeight,
                document.body ? document.body.scrollHeight : 0
            )
        })
        """
    )

    raw_visible_elements = cast(
        list[RawVisibleElement],
        await session.page.evaluate(
            f"""
            () => {{
                const MAX_ELEMENTS = {MAX_VISIBLE_ELEMENTS};
                const MAX_NAME = {MAX_VISIBLE_ELEMENT_NAME_CHARS};

                const selectors = [
                    "a[href]",
                    "button",
                    "input",
                    "select",
                    "textarea",
                    "[role]",
                    "[contenteditable='true']",
                    "h1",
                    "h2",
                    "h3",
                    "h4",
                    "h5",
                    "h6",
                    "img[alt]",
                    "summary",
                ].join(",");

                function clean(value) {{
                    return (value || "")
                        .replace(/\\s+/g, " ")
                        .trim()
                        .slice(0, MAX_NAME);
                }}

                function accessibleName(element) {{
                    const ariaLabel = clean(
                        element.getAttribute("aria-label")
                    );

                    if (ariaLabel) {{
                        return ariaLabel;
                    }}

                    const labelledBy =
                        element.getAttribute("aria-labelledby");

                    if (labelledBy) {{
                        const label = labelledBy
                            .split(/\\s+/)
                            .map(id => document.getElementById(id))
                            .filter(Boolean)
                            .map(item => clean(item.textContent))
                            .filter(Boolean)
                            .join(" ");

                        if (label) {{
                            return clean(label);
                        }}
                    }}

                    if (
                        "labels" in element &&
                        element.labels &&
                        element.labels.length
                    ) {{
                        const labels = Array.from(element.labels)
                            .map(label => clean(label.textContent))
                            .filter(Boolean)
                            .join(" ");

                        if (labels) {{
                            return clean(labels);
                        }}
                    }}

                    return clean(
                        element.getAttribute("alt") ||
                        element.getAttribute("placeholder") ||
                        element.innerText ||
                        element.textContent ||
                        ""
                    );
                }}

                function semanticRole(element) {{
                    const explicitRole =
                        element.getAttribute("role");

                    if (explicitRole) {{
                        return explicitRole;
                    }}

                    const tag = element.tagName.toLowerCase();

                    if (/^h[1-6]$/.test(tag)) {{
                        return "heading";
                    }}

                    if (tag === "a" && element.hasAttribute("href")) {{
                        return "link";
                    }}

                    if (tag === "button" || tag === "summary") {{
                        return "button";
                    }}

                    if (tag === "select") {{
                        return "combobox";
                    }}

                    if (tag === "textarea") {{
                        return "textbox";
                    }}

                    if (tag === "img") {{
                        return "img";
                    }}

                    if (tag === "input") {{
                        const type = (
                            element.getAttribute("type") || "text"
                        ).toLowerCase();

                        if (type === "search") {{
                            return "searchbox";
                        }}

                        if (type === "checkbox") {{
                            return "checkbox";
                        }}

                        if (type === "radio") {{
                            return "radio";
                        }}

                        if (
                            type === "button" ||
                            type === "submit" ||
                            type === "reset"
                        ) {{
                            return "button";
                        }}

                        return "textbox";
                    }}

                    if (
                        element.getAttribute("contenteditable") === "true"
                    ) {{
                        return "textbox";
                    }}

                    return tag;
                }}

                return Array.from(
                    document.querySelectorAll(selectors)
                )
                    .map(element => {{
                        const rect =
                            element.getBoundingClientRect();

                        const style =
                            window.getComputedStyle(element);

                        const visible =
                            rect.width > 0 &&
                            rect.height > 0 &&
                            style.display !== "none" &&
                            style.visibility !== "hidden" &&
                            style.visibility !== "collapse" &&
                            Number(style.opacity) > 0;

                        const inViewport =
                            rect.bottom > 0 &&
                            rect.right > 0 &&
                            rect.top < window.innerHeight &&
                            rect.left < window.innerWidth;

                        if (!visible || !inViewport) {{
                            return null;
                        }}

                        const tag =
                            element.tagName.toLowerCase();

                        const headingLevel =
                            /^h[1-6]$/.test(tag)
                                ? Number(tag.slice(1))
                                : null;

                        const enabled =
                            !element.matches(":disabled") &&
                            element.getAttribute(
                                "aria-disabled"
                            ) !== "true";

                        return {{
                            role: semanticRole(element),
                            name: accessibleName(element),
                            tag,
                            enabled,
                            level: headingLevel,
                            bounding_box: {{
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height)
                            }}
                        }};
                    }})
                    .filter(Boolean)
                    .sort((left, right) =>
                        left.bounding_box.y -
                            right.bounding_box.y ||
                        left.bounding_box.x -
                            right.bounding_box.x
                    )
                    .slice(0, MAX_ELEMENTS);
            }}
            """
        ),
    )

    viewport_metrics = cast(ViewportMetrics, raw_viewport_metrics)

    visible_elements = tuple(
        VisibleElement(
            role=element["role"],
            name=element["name"],
            tag=element["tag"],
            enabled=element["enabled"],
            level=element["level"],
            bounding_box=ElementBoundingBox(
                x=element["bounding_box"]["x"],
                y=element["bounding_box"]["y"],
                width=element["bounding_box"]["width"],
                height=element["bounding_box"]["height"],
            ),
        )
        for element in raw_visible_elements
    )

    observation = BrowserObservation(
        url=session.page.url,
        title=await session.page.title(),
        aria_snapshot=aria_snapshot,
        console_errors_since_last_action=tuple(
            session.event_buffer.console_errors
        ),
        page_errors_since_last_action=tuple(
            session.event_buffer.page_errors
        ),
        failed_requests_since_last_action=tuple(
            session.event_buffer.failed_requests
        ),
        accessibility_snapshot_path=(
            str(accessibility_path) if accessibility_path else None
        ),
        page_count=len(session.context.pages),
        viewport_width=viewport_metrics["width"],
        viewport_height=viewport_metrics["height"],
        scroll_y=viewport_metrics["scroll_y"],
        document_height=viewport_metrics["document_height"],
        visible_elements=visible_elements,
        action_number=session.action_number,
        screenshot_path=(
            str(screenshot_path) if screenshot_path else None
        ),
        focused_screenshot_path=(
            str(focused_screenshot_path)
            if focused_screenshot_path
            else None
        ),
    )
    session.event_buffer.console_errors.clear()
    session.event_buffer.page_errors.clear()
    session.event_buffer.failed_requests.clear()
    return observation
