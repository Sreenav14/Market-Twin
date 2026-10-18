"""Compact, model-safe browser observations."""

import asyncio
import json
import re
from pathlib import Path
from typing import NotRequired, TypedDict, cast
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import Locator

from markettwin_execution_orchestrator.browser.contracts import (
    BrowserObservation,
    ElementBoundingBox,
    FormFieldState,
    VisibleElement,
)
from markettwin_execution_orchestrator.browser.errors import HumanControlActiveError
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession

MAX_VISIBLE_ELEMENTS = 80
MAX_VISIBLE_ELEMENT_NAME_CHARS = 160
MAX_FORM_FIELDS = 40


async def inspect_form_fields(root: Locator) -> tuple[tuple[FormFieldState, ...], bool]:
    controls = root.locator("input:not([type=hidden]), select, textarea")
    count = await controls.count()
    fields: list[FormFieldState] = []
    for index in range(min(count, MAX_FORM_FIELDS)):
        control = controls.nth(index)
        raw = cast(dict[str, object], await control.evaluate("""element => ({
            label: (element.getAttribute('aria-label') || Array.from(element.labels || [])
                .map(label => label.textContent).join(' ') || '').slice(0,160),
            input_type: element.type || element.tagName.toLowerCase(),
            required: !!element.required, enabled: !element.matches(':disabled') &&
                element.getAttribute('aria-disabled') !== 'true',
            checked: ['checkbox','radio'].includes(element.type) ? element.checked : null,
            valid: element.validity ? element.validity.valid : null
        })"""))
        # Values and validationMessage are deliberately never read. Selection is
        # represented as option positions rather than potentially sensitive text.
        selected = tuple(cast(list[int], await control.evaluate(
            "element => Array.from(element.selectedOptions || []).map(option => option.index)"
        )))
        fields.append(FormFieldState(
            label=str(raw["label"]), input_type=str(raw["input_type"]),
            required=bool(raw["required"]), enabled=bool(raw["enabled"]),
            checked=cast(bool | None, raw["checked"]), selected_options=selected,
            valid=cast(bool | None, raw["valid"]),
        ))
    return tuple(fields), count > MAX_FORM_FIELDS


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
    link_index: NotRequired[int | None]


async def _ground_link_names(
    session: JourneyBrowserSession, elements: list[RawVisibleElement],
) -> tuple[list[RawVisibleElement], bool]:
    """Use Playwright's exact accessible names, not an innerText approximation.

    CSS generated content can contribute to a link's accessible name; aria-hidden
    children cannot. Read only each already-visible link, discard the raw snapshot
    (which can include its URL), and never inspect the protected page as a whole.
    """
    links = session.page.locator('a[href], [role="link"]')
    grounded: list[RawVisibleElement] = []
    omitted = False
    deadline = asyncio.get_running_loop().time() + 2
    for element in elements:
        index = element.get("link_index")
        if element["role"] != "link" or index is None:
            grounded.append(element)
            continue
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            omitted = True
            continue
        try:
            async with asyncio.timeout(remaining):
                snapshot = await links.nth(index).aria_snapshot(
                    timeout=min(session.timeout_ms, 500),
                )
            first_line = snapshot.splitlines()[0] if snapshot else ""
            # Playwright quotes an accessible name as a JSON string inside its
            # YAML role key. The key itself can be single-quoted by the renderer.
            match = re.match(r"""^- (?:')?link ("(?:[^"\\]|\\.)*")""", first_line)
            name = json.loads(match.group(1)) if match else None
        except Exception:
            # Missing/stale/unreadable nodes must not become invented locators.
            name = None
        if not isinstance(name, str) or not name or len(name) > MAX_VISIBLE_ELEMENT_NAME_CHARS:
            omitted = True
            continue
        grounded.append({**element, "name": name})
    return grounded, omitted


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
    aria_snapshot_override: str | None = None,
    form_fields: tuple[FormFieldState, ...] = (),
    more_available: bool = False,
) -> BrowserObservation:
    """Return current page state and drain per-action error buffers."""

    if not session.capture_enabled or session.control_mode != "agent":
        raise HumanControlActiveError("Browser observations are disabled during handoff.")

    try:
        aria_snapshot = aria_snapshot_override
        if aria_snapshot is None:
            aria_snapshot = "" if session.authenticated_session else (
                await session.page.locator("body").aria_snapshot(timeout=session.timeout_ms)
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
                const authenticated = {str(session.authenticated_session).lower()};
                const MAX_ELEMENTS = {MAX_VISIBLE_ELEMENTS + 1};
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
                const links = Array.from(document.querySelectorAll('a[href], [role="link"]'));

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
                        if (authenticated && (
                            element.closest('pre, code, [data-sensitive], [data-secret]') ||
                            !['button', 'link', 'heading', 'textbox', 'searchbox', 'combobox',
                              'checkbox', 'radio'].includes(semanticRole(element))
                        )) return null;
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
                            link_index: semanticRole(element) === "link"
                                ? links.indexOf(element) : null,
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

    more_available = more_available or len(raw_visible_elements) > MAX_VISIBLE_ELEMENTS
    raw_visible_elements, omitted_links = await _ground_link_names(session, raw_visible_elements)
    more_available = more_available or omitted_links

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
        for element in raw_visible_elements[:MAX_VISIBLE_ELEMENTS]
    )

    observed_url = session.page.url
    if session.authenticated_session:
        parsed_url = urlsplit(observed_url)
        observed_url = urlunsplit((parsed_url.scheme, parsed_url.netloc, parsed_url.path, "", ""))
    observation = BrowserObservation(
        url=observed_url,
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
        form_fields=form_fields,
        truncated=more_available or len(raw_visible_elements) > MAX_VISIBLE_ELEMENTS,
        more_available=more_available or len(raw_visible_elements) > MAX_VISIBLE_ELEMENTS,
    )
    session.event_buffer.console_errors.clear()
    session.event_buffer.page_errors.clear()
    session.event_buffer.failed_requests.clear()
    return observation
