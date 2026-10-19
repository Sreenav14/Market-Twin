"""Exercise real MCP protocol sessions against fake, journey-bound browser tools."""

import asyncio
from contextlib import AsyncExitStack
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import anyio
import pytest
from google.adk.tools import ToolContext
from markettwin_execution_orchestrator.browser.contracts import (
    BrowserActionResult,
    BrowserObservation,
    BrowserSessionHandle,
)
from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserPolicyError
from markettwin_execution_orchestrator.browser.mcp_tools import connect_controlled_browser_tools
from markettwin_execution_orchestrator.browser.tools import (
    BrowserStepRecorder,
    create_browser_tools,
)
from markettwin_shared.observability import (
    MarketTwinCorrelationSpanProcessor,
    use_observability_correlation,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy.exc import SQLAlchemyError

CONTEXT = cast(ToolContext, None)  # Bound tools never trust agent-supplied context for identity.


class FakeController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def cooperative_checkpoint(self, handle: BrowserSessionHandle) -> None:
        pass

    def require_agent_control(self, handle: BrowserSessionHandle) -> None:
        pass

    async def inspect_click_approval(self, **kwargs: object) -> None:
        return None

    async def _call(self, name: str, /, **kwargs: object) -> BrowserActionResult:
        self.calls.append((name, kwargs))
        await asyncio.sleep(0)
        return BrowserActionResult(
            action=name,
            observation=BrowserObservation(
                url="https://example.com",
                title="Example",
                aria_snapshot="- button Continue",
                viewport_width=1280,
                viewport_height=720,
                scroll_y=0,
                document_height=720,
            ),
        )

    async def navigate(self, **kwargs: object) -> BrowserActionResult:
        return await self._call("navigate", **kwargs)

    async def get_state(self, **kwargs: object) -> BrowserActionResult:
        return await self._call("get_state", **kwargs)

    async def click(self, **kwargs: object) -> BrowserActionResult:
        return await self._call("click", **kwargs)


class PolicyBlockedController(FakeController):
    async def navigate(self, **kwargs: object) -> BrowserActionResult:
        raise BrowserPolicyError("Target is outside the allowlist.")


def recorder_mock() -> AsyncMock:
    recorder = AsyncMock(spec=BrowserStepRecorder)
    recorder.start_step.side_effect = [1, 2]
    return recorder


async def test_mcp_discovers_and_calls_only_journey_bound_tools_with_recorded_evidence() -> None:
    controller = FakeController()
    recorder = recorder_mock()
    handle = BrowserSessionHandle(uuid4(), uuid4(), uuid4())
    original = create_browser_tools(
        controller=cast(BrowserController, controller),
        handle=handle,
        step_recorder=cast(BrowserStepRecorder, recorder),
    )
    async with connect_controlled_browser_tools(original) as connected:
        assert {tool.name for tool in connected} == {tool.__name__ for tool in original}
        by_name = {tool.name: tool for tool in connected}
        result = await by_name["browser_navigate"].run_async(
            args={"url": "https://example.com"}, tool_context=CONTEXT
        )
        assert isinstance(result, dict) and result["step_id"] == 1
        assert result["action"] == "navigate"
        assert recorder.record_evidence.await_count == 1
        assert controller.calls[0][1]["session_id"] == handle.session_id
        assert controller.calls[0][1]["execution_id"] == handle.execution_id


async def test_policy_blocking_survives_mcp_and_unlocks_observation() -> None:
    original = create_browser_tools(
        controller=cast(BrowserController, PolicyBlockedController()),
        handle=BrowserSessionHandle(uuid4(), uuid4(), uuid4()),
    )
    async with connect_controlled_browser_tools(original) as connected:
        by_name = {tool.name: tool for tool in connected}
        with pytest.raises(BrowserPolicyError, match="outside the allowlist"):
            await by_name["browser_navigate"].run_async(
                args={"url": "https://blocked.example"}, tool_context=CONTEXT
            )
        result = await by_name["browser_get_state"].run_async(args={}, tool_context=CONTEXT)
        assert isinstance(result, dict) and result["action"] == "get_state"


async def test_mcp_calls_retain_original_action_lock_and_recorder() -> None:
    recorder = recorder_mock()
    original = create_browser_tools(
        controller=cast(BrowserController, FakeController()),
        handle=BrowserSessionHandle(uuid4(), uuid4(), uuid4()),
        step_recorder=cast(BrowserStepRecorder, recorder),
    )
    async with connect_controlled_browser_tools(original) as connected:
        by_name = {tool.name: tool for tool in connected}
        await asyncio.gather(
            by_name["browser_navigate"].run_async(
                args={"url": "https://example.com"}, tool_context=CONTEXT
            ),
            by_name["browser_click"].run_async(
                args={"role": "button", "name": "Continue"}, tool_context=CONTEXT
            ),
        )
    assert [call.kwargs["step_id"] for call in recorder.finish_step.await_args_list] == [1, 2]
    assert recorder.record_evidence.await_count == 2


async def test_lost_response_never_replays_completed_browser_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = FakeController()
    original = create_browser_tools(
        controller=cast(BrowserController, controller),
        handle=BrowserSessionHandle(uuid4(), uuid4(), uuid4()),
    )
    async with connect_controlled_browser_tools(original) as connected:
        tool = next(item for item in connected if item.name == "browser_click")
        actual_call = tool.client.call_tool

        async def lose_response(*args: object, **kwargs: object) -> object:
            await actual_call(*args, **kwargs)
            raise ConnectionError("Response lost after action")

        monkeypatch.setattr(tool.client, "call_tool", lose_response)
        with pytest.raises(ConnectionError, match="Response lost"):
            await tool.run_async(args={"role": "button", "name": "Continue"}, tool_context=CONTEXT)
        assert len(controller.calls) == 1


async def test_mcp_connection_closes_and_cannot_execute_after_exit() -> None:
    controller = FakeController()
    original = create_browser_tools(
        controller=cast(BrowserController, controller),
        handle=BrowserSessionHandle(uuid4(), uuid4(), uuid4()),
    )
    async with connect_controlled_browser_tools(original) as connected:
        tool = next(item for item in connected if item.name == "browser_get_state")
        await tool.run_async(args={}, tool_context=CONTEXT)
    with pytest.raises((RuntimeError, anyio.ClosedResourceError)):
        await asyncio.wait_for(tool.run_async(args={}, tool_context=CONTEXT), timeout=1)
    assert len(controller.calls) == 1


async def test_agent_cannot_supply_browser_identity_or_arbitrary_tool() -> None:
    controller = FakeController()
    original = create_browser_tools(
        controller=cast(BrowserController, controller),
        handle=BrowserSessionHandle(uuid4(), uuid4(), uuid4()),
    )
    async with connect_controlled_browser_tools(original) as connected:
        tool = next(item for item in connected if item.name == "browser_get_state")
        with pytest.raises(RuntimeError, match="Additional properties"):
            await tool.run_async(args={"session_id": str(uuid4())}, tool_context=CONTEXT)
        unknown = await tool.client.call_tool("create_session", {})
        assert unknown.isError
    assert controller.calls == []


async def test_cancelled_call_closes_server_task_without_replay() -> None:
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    class BlockingController(FakeController):
        async def click(self, **kwargs: object) -> BrowserActionResult:
            self.calls.append(("click", kwargs))
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
            raise AssertionError("Blocking action should have been cancelled")

    controller = BlockingController()
    original = create_browser_tools(
        controller=cast(BrowserController, controller),
        handle=BrowserSessionHandle(uuid4(), uuid4(), uuid4()),
    )
    async with connect_controlled_browser_tools(original) as connected:
        tool = next(item for item in connected if item.name == "browser_click")
        call = asyncio.create_task(
            tool.run_async(args={"role": "button", "name": "Continue"}, tool_context=CONTEXT)
        )
        await asyncio.wait_for(entered.wait(), timeout=2)
        call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await call
    assert cancelled.is_set()
    assert len(controller.calls) == 1


async def test_durable_recording_error_is_not_downgraded_to_browser_feedback() -> None:
    controller = FakeController()
    recorder = recorder_mock()
    recorder.start_step.side_effect = SQLAlchemyError("Evidence transaction failed")
    original = create_browser_tools(
        controller=cast(BrowserController, controller),
        handle=BrowserSessionHandle(uuid4(), uuid4(), uuid4()),
        step_recorder=cast(BrowserStepRecorder, recorder),
    )
    async with connect_controlled_browser_tools(original) as connected:
        tool = next(item for item in connected if item.name == "browser_click")
        with pytest.raises(SQLAlchemyError, match="Evidence transaction failed"):
            await tool.run_async(args={"role": "button", "name": "Continue"}, tool_context=CONTEXT)
    assert controller.calls == []


async def test_mcp_background_actions_keep_journey_trace_correlation() -> None:
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(MarketTwinCorrelationSpanProcessor())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("controlled-browser-mcp-test")
    run_id, journey_id, snapshot_id = uuid4(), uuid4(), uuid4()

    async def browser_get_state() -> dict[str, object]:
        with tracer.start_as_current_span("recorded_browser_action"):
            return {"step_id": 1}

    try:
        async with AsyncExitStack() as resources:
            with use_observability_correlation(
                test_run_id=run_id,
                journey_id=journey_id,
                agent_snapshot_id=snapshot_id,
                agent_role="persona",
            ):
                connected = await resources.enter_async_context(
                    connect_controlled_browser_tools([browser_get_state])
                )
            # The calling coroutine has left its scope; the server task must
            # retain the values inherited at connection creation.
            await connected[0].run_async(args={}, tool_context=CONTEXT)
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes is not None
        assert spans[0].attributes["markettwin.test_run_id"] == str(run_id)
        assert spans[0].attributes["markettwin.journey_id"] == str(journey_id)
        assert spans[0].attributes["markettwin.agent_snapshot_id"] == str(snapshot_id)
    finally:
        provider.shutdown()
