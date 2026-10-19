"""Focused tests for the fixed synthetic fixture approval dispatch boundary."""

import asyncio
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.sensitive_action_policy import classify_click_action
from markettwin_execution_orchestrator.persistence.step_recorder import ExecutionStepRecorder
from markettwin_execution_orchestrator.workflow import case_execution
from markettwin_execution_orchestrator.workflow.deep_run import case_journey
from markettwin_execution_orchestrator.workflow.journey_executor import (
    PersonaJourneyExecutionRequest,
)
from markettwin_execution_orchestrator.workflow.test_case_planner import (
    fixture_case_candidates,
    fixture_feature_scope,
)


@pytest.mark.asyncio
async def test_registration_fixture_receipt_is_consumed_immediately_before_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []

    class Recorder:
        async def begin_sensitive_action(self, **_kwargs: object):
            order.append("wait")
            await asyncio.sleep(0.06)
            order.append("consume")
            return uuid4()

        async def finish_sensitive_action(self, **kwargs: object) -> None:
            order.append(str(kwargs["outcome"]))

    scope = fixture_feature_scope("http://127.0.0.1:5191/index.html")
    case = next(item for item in fixture_case_candidates(scope).cases if item.case_id == "valid")
    action = case.steps[-1]
    assert action.action_id == "registration_submit"
    request = PersonaJourneyExecutionRequest(
        test_run_id=uuid4(),
        execution_id=uuid4(),
        journey_id=uuid4(),
        persona_id=uuid4(),
        mission_id=uuid4(),
        journey=case_journey(case),
        start_url=scope.starting_url,
        allowed_origins=(),
        network_policy="local_development",
    )
    # Only the IDs/network policy are used by this dispatch boundary.
    handle = BrowserSessionHandle(request.execution_id, request.journey_id, uuid4())
    async def origin(**_kwargs: object) -> str:
        return "http://127.0.0.1:5191"

    controller = cast(
        BrowserController, SimpleNamespace(click=async_click(order), current_origin=origin)
    )
    intent = classify_click_action(role="button", name="Save", label=None, text=None)
    assert intent is not None
    started = asyncio.get_running_loop().time()
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.20) as case_timeout:
            await case_execution._approved_case_action(  # pyright: ignore[reportPrivateUsage]
                step_id=1,
                request=request,
                controller=controller,
                handle=handle,
                recorder=cast(ExecutionStepRecorder, Recorder()),
                intent=intent,
                action=action,
                scope=scope,
                planned_step_index=0,
                case_timeout=case_timeout,
            )
            await asyncio.sleep(0.22)
    elapsed = asyncio.get_running_loop().time() - started
    assert elapsed >= 0.24
    assert order == ["wait", "consume", "click", "completed"]


def async_click(order: list[str]):
    async def click(**_kwargs: object):
        order.append("click")
        return SimpleNamespace()

    return click
