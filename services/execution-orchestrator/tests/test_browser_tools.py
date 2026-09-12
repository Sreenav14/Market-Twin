from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser.contracts import (
    MAX_MODEL_ARIA_SNAPSHOT_CHARS,
    BrowserActionResult,
    BrowserObservation,
    BrowserSessionHandle,
)
from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserPolicyError
from markettwin_execution_orchestrator.browser.tools import (
    BrowserStepRecorder,
    create_browser_tools,
)


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


class FakeRecorder:
    def __init__(self) -> None:
        self.started: list[tuple[str, str]] = []
        self.finished: list[tuple[int, str, str | None]] = []

    async def start_step(
        self,
        *,
        action_type: str,
        action_summary: str,
    ) -> int:
        self.started.append((action_type, action_summary))
        return len(self.started)

    async def finish_step(
        self,
        *,
        step_id: int,
        status: str,
        observation_summary: str | None = None,
    ) -> None:
        self.finished.append((step_id, status, observation_summary))


class PolicyBlockedController(FakeController):
    async def navigate(self, **kwargs: object) -> BrowserActionResult:
        raise BrowserPolicyError("Target is outside the allowlist.")


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


def test_observation_limits_snapshot_only_in_model_payload() -> None:
    full_snapshot = "x" * (MAX_MODEL_ARIA_SNAPSHOT_CHARS + 10)
    observation = BrowserObservation(
        url="https://example.com",
        title="Example",
        aria_snapshot=full_snapshot,
        accessibility_snapshot_path="full-snapshot.yml",
    )

    payload = observation.to_dict()
    model_snapshot = payload["aria_snapshot"]

    assert observation.aria_snapshot == full_snapshot
    assert isinstance(model_snapshot, str)
    assert model_snapshot.startswith("x" * MAX_MODEL_ARIA_SNAPSHOT_CHARS)
    assert "Snapshot truncated for model context" in model_snapshot
    assert payload["accessibility_snapshot_path"] == "full-snapshot.yml"


@pytest.mark.asyncio
async def test_tools_record_safe_action_summaries_and_results() -> None:
    controller = FakeController()
    recorder = FakeRecorder()
    handle = BrowserSessionHandle(uuid4(), uuid4(), uuid4())
    tools = create_browser_tools(
        controller=cast(BrowserController, controller),
        handle=handle,
        step_recorder=cast(BrowserStepRecorder, recorder),
    )
    by_name = {tool.__name__: tool for tool in tools}

    await by_name["browser_navigate"](
        "https://example.com/path?token=secret#fragment"
    )
    await by_name["browser_fill"]("Password", "do-not-log-this")

    assert recorder.started == [
        ("navigate", "Navigate to https://example.com/path."),
        ("fill", "Fill an approved non-secret text field."),
    ]
    assert all(
        "token=secret" not in summary and "do-not-log-this" not in summary
        for _, summary in recorder.started
    )
    assert [status for _, status, _ in recorder.finished] == [
        "completed",
        "completed",
    ]


@pytest.mark.asyncio
async def test_policy_errors_are_recorded_before_being_raised() -> None:
    recorder = FakeRecorder()
    handle = BrowserSessionHandle(uuid4(), uuid4(), uuid4())
    tools = create_browser_tools(
        controller=cast(BrowserController, PolicyBlockedController()),
        handle=handle,
        step_recorder=cast(BrowserStepRecorder, recorder),
    )
    by_name = {tool.__name__: tool for tool in tools}

    with pytest.raises(BrowserPolicyError):
        await by_name["browser_navigate"]("https://blocked.example")

    assert recorder.finished == [
        (1, "policy_blocked", "Target is outside the allowlist.")
    ]
