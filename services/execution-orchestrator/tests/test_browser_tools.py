from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser.contracts import (
    BrowserActionResult,
    BrowserObservation,
    BrowserSessionHandle,
)
from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.tools import create_browser_tools


class FakeController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def _call(self, name: str, **kwargs: object) -> BrowserActionResult:
        self.calls.append((name, kwargs))
        return BrowserActionResult(
            action=name,
            observation=BrowserObservation(
                url="https://example.com",
                title="Example",
                aria_snapshot='- heading "Example"',
            ),
        )

    async def get_state(self, **kwargs: object) -> BrowserActionResult:
        return await self._call("get_state", **kwargs)

    async def navigate(self, **kwargs: object) -> BrowserActionResult:
        return await self._call("navigate", **kwargs)

    async def click(self, **kwargs: object) -> BrowserActionResult:
        return await self._call("click", **kwargs)

    async def fill(self, **kwargs: object) -> BrowserActionResult:
        return await self._call("fill", **kwargs)

    async def select(self, **kwargs: object) -> BrowserActionResult:
        return await self._call("select", **kwargs)

    async def scroll(self, **kwargs: object) -> BrowserActionResult:
        return await self._call("scroll", **kwargs)

    async def go_back(self, **kwargs: object) -> BrowserActionResult:
        return await self._call("go_back", **kwargs)

    async def wait(self, **kwargs: object) -> BrowserActionResult:
        return await self._call("wait", **kwargs)

    async def take_screenshot(self, **kwargs: object) -> BrowserActionResult:
        return await self._call("take_screenshot", **kwargs)


@pytest.mark.asyncio
async def test_tools_are_bound_to_one_session_and_journey() -> None:
    controller = FakeController()
    handle = BrowserSessionHandle(uuid4(), uuid4(), uuid4())
    tools = create_browser_tools(
        controller=cast(BrowserController, controller),
        handle=handle,
    )
    by_name = {tool.__name__: tool for tool in tools}

    result = await by_name["browser_navigate"]("https://example.com")

    assert result["action"] == "navigate"
    name, kwargs = controller.calls[-1]
    assert name == "navigate"
    assert kwargs["session_id"] == handle.session_id
    assert kwargs["execution_id"] == handle.execution_id
    assert kwargs["journey_id"] == handle.journey_id


def test_tool_surface_is_least_privilege() -> None:
    controller = FakeController()
    handle = BrowserSessionHandle(uuid4(), uuid4(), uuid4())
    tools = create_browser_tools(
        controller=cast(BrowserController, controller),
        handle=handle,
    )
    names = {tool.__name__ for tool in tools}

    assert names == {
        "browser_get_state",
        "browser_navigate",
        "browser_click",
        "browser_fill",
        "browser_select",
        "browser_scroll",
        "browser_go_back",
        "browser_wait",
        "browser_take_screenshot",
    }
    assert "page_evaluate" not in names
    assert "browser_context_new" not in names
