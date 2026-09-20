from __future__ import annotations

import asyncio
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
from markettwin_execution_orchestrator.browser.errors import (
    BrowserActionError,
    BrowserPolicyError,
    BrowserSessionStateError,
    BrowserTimeoutError,
)
from markettwin_execution_orchestrator.browser.tools import (
    BrowserStepRecorder,
    create_browser_tools,
)


class FakeController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        
    async def _call(self, name: str, /, **kwargs: object) -> BrowserActionResult:
        self.calls.append((name, kwargs))
        return BrowserActionResult(
            action=name,
            observation=BrowserObservation(
                url="https://example.com",
                title="Example",
                aria_snapshot='- heading "Example"',
                viewport_width=1280,
                viewport_height=720,
                scroll_y=0,
                document_height=720,
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

    async def capture_element(self, **kwargs: object) -> BrowserActionResult:
        return await self._call("capture_element", **kwargs)


class FakeRecorder:
    def __init__(self) -> None:
        self.started: list[tuple[str, str]] = []
        self.finished: list[tuple[int, str, str | None]] = []
        self.evidence: list[tuple[int, BrowserActionResult]] = []

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

    async def record_evidence(
        self,
        *,
        step_id: int,
        result: BrowserActionResult,
    ) -> None:
        self.evidence.append((step_id, result))


@pytest.mark.asyncio
async def test_concurrent_tools_serialize_recording_and_browser_actions() -> None:
    events: list[str] = []

    class YieldingRecorder(FakeRecorder):
        async def start_step(self, *, action_type: str, action_summary: str) -> int:
            events.append(f"start:{action_type}")
            await asyncio.sleep(0)  # Simulate an in-flight database flush.
            return await super().start_step(
                action_type=action_type, action_summary=action_summary
            )

        async def finish_step(
            self, *, step_id: int, status: str, observation_summary: str | None = None
        ) -> None:
            await asyncio.sleep(0)  # Simulate a commit that must finish first.
            events.append(f"finish:{step_id}")
            await super().finish_step(
                step_id=step_id, status=status, observation_summary=observation_summary
            )

    class YieldingController(FakeController):
        async def _call(self, name: str, /, **kwargs: object) -> BrowserActionResult:
            events.append(f"browser:{name}")
            await asyncio.sleep(0)
            return await super()._call(name, **kwargs)

    recorder = YieldingRecorder()
    tools = create_browser_tools(
        controller=cast(BrowserController, YieldingController()),
        handle=BrowserSessionHandle(uuid4(), uuid4(), uuid4()),
        step_recorder=cast(BrowserStepRecorder, recorder),
    )
    by_name = {tool.__name__: tool for tool in tools}
    await asyncio.gather(
        by_name["browser_navigate"]("https://example.com"),
        by_name["browser_click"](role="button", name="Continue"),
        by_name["browser_take_screenshot"](),
    )

    assert events == [
        "start:navigate", "browser:navigate", "finish:1",
        "start:click", "browser:click", "finish:2",
        "start:take_screenshot", "browser:take_screenshot", "finish:3",
    ]


@pytest.mark.asyncio
async def test_action_lock_is_released_after_tool_error() -> None:
    tools = create_browser_tools(
        controller=cast(BrowserController, PolicyBlockedController()),
        handle=BrowserSessionHandle(uuid4(), uuid4(), uuid4()),
    )
    by_name = {tool.__name__: tool for tool in tools}
    with pytest.raises(BrowserPolicyError):
        await by_name["browser_navigate"]("https://blocked.example")
    result = await asyncio.wait_for(by_name["browser_get_state"](), timeout=1)
    assert result["action"] == "get_state"


class PolicyBlockedController(FakeController):
    async def navigate(self, **kwargs: object) -> BrowserActionResult:
        raise BrowserPolicyError("Target is outside the allowlist.")


class FailingClickController(FakeController):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def click(self, **kwargs: object) -> BrowserActionResult:
        raise self.error


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    BrowserTimeoutError("Click timed out."),
    BrowserActionError("Click could not be completed."),
])
@pytest.mark.parametrize("record_steps", [False, True])
async def test_action_failure_returns_feedback_and_allows_observation(
    error: Exception, record_steps: bool,
) -> None:
    controller = FailingClickController(error)
    recorder = FakeRecorder()
    tools = create_browser_tools(
        controller=cast(BrowserController, controller),
        handle=BrowserSessionHandle(uuid4(), uuid4(), uuid4()),
        step_recorder=cast(BrowserStepRecorder, recorder) if record_steps else None,
    )
    by_name = {tool.__name__: tool for tool in tools}

    result = await by_name["browser_click"](role="link", name="Search Wikipedia")

    assert result["action"] == "click"
    assert result["status"] == "failed"
    assert result["error"] == str(error)
    
    if record_steps:
        assert result["step_id"] == 1
    else:
        assert "step_id" not in result
    assert "browser_get_state" in str(result["recovery"])
    if record_steps:
        assert result["step_id"] == 1
        assert recorder.finished == [(1, "failed", str(error))]
    else:
        assert "step_id" not in result
    state = await by_name["browser_get_state"]()
    assert state["action"] == "get_state"


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    BrowserSessionStateError("Session is closed."),
    RuntimeError("Unexpected failure."),
])
async def test_non_action_failures_still_propagate(error: Exception) -> None:
    recorder = FakeRecorder()
    tools = create_browser_tools(
        controller=cast(BrowserController, FailingClickController(error)),
        handle=BrowserSessionHandle(uuid4(), uuid4(), uuid4()),
        step_recorder=cast(BrowserStepRecorder, recorder),
    )
    by_name = {tool.__name__: tool for tool in tools}

    with pytest.raises(type(error)):
        await by_name["browser_click"](role="button", name="Search")

    assert recorder.finished == [(1, "failed", str(error))]


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
        "browser_capture_element",
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
        viewport_width=1280,
        viewport_height=720,
        scroll_y=0,
        document_height=720,
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

    navigate_result = await by_name["browser_navigate"](
        "https://example.com/path?token=secret#fragment"
    )
    fill_result = await by_name["browser_fill"](
        "password",
        "do-not-log-this",
    )
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
    assert [step_id for step_id, _ in recorder.evidence] == [1, 2]
    assert navigate_result["step_id"] == 1
    assert fill_result["step_id"] == 2


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
