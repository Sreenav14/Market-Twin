"""Plain Python Google ADK tools bound to one MarketTwin Journey browser."""

from collections.abc import Awaitable, Callable
from typing import Literal

from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.controller import BrowserController

BrowserTool = Callable[..., Awaitable[dict[str, object]]]


def create_browser_tools(
    *,
    controller: BrowserController,
    handle: BrowserSessionHandle,
) -> list[BrowserTool]:
    """Create a least-privilege tool set permanently bound to one Journey."""

    async def browser_get_state() -> dict[str, object]:
        """Observe the current page without changing it."""
        return (
            await controller.get_state(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
            )
        ).to_dict()

    async def browser_navigate(url: str) -> dict[str, object]:
        """Navigate to an HTTP(S) URL allowed by this Journey's target policy."""
        return (
            await controller.navigate(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                url=url,
            )
        ).to_dict()

    async def browser_click(
        role: str | None = None,
        name: str | None = None,
        label: str | None = None,
        text: str | None = None,
    ) -> dict[str, object]:
        """Click one exact semantic element by role+name, label, or visible text."""
        return (
            await controller.click(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                role=role,
                name=name,
                label=label,
                text=text,
            )
        ).to_dict()

    async def browser_fill(label: str, value: str) -> dict[str, object]:
        """Fill non-secret text into one exactly labelled input field."""
        return (
            await controller.fill(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                label=label,
                value=value,
            )
        ).to_dict()

    async def browser_select(label: str, value: str) -> dict[str, object]:
        """Choose one value from an exactly labelled select control."""
        return (
            await controller.select(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                label=label,
                value=value,
            )
        ).to_dict()

    async def browser_scroll(
        direction: Literal["up", "down"],
        amount: int = 600,
    ) -> dict[str, object]:
        """Scroll the page up or down by at most 2000 pixels."""
        return (
            await controller.scroll(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                direction=direction,
                amount=amount,
            )
        ).to_dict()

    async def browser_go_back() -> dict[str, object]:
        """Go back once within the same policy-controlled browser session."""
        return (
            await controller.go_back(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
            )
        ).to_dict()

    async def browser_wait(milliseconds: int = 500) -> dict[str, object]:
        """Wait up to five seconds for a bounded asynchronous UI transition."""
        return (
            await controller.wait(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                milliseconds=milliseconds,
            )
        ).to_dict()

    async def browser_take_screenshot() -> dict[str, object]:
        """Capture explicit screenshot evidence and return the current page state."""
        return (
            await controller.take_screenshot(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
            )
        ).to_dict()

    return [
        browser_get_state,
        browser_navigate,
        browser_click,
        browser_fill,
        browser_select,
        browser_scroll,
        browser_go_back,
        browser_wait,
        browser_take_screenshot,
    ]
