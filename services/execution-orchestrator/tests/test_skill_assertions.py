"""A matching page cannot substitute for task outcome evidence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from markettwin_execution_orchestrator.workflow.skill_assertions import check_skill_assertions
from markettwin_shared.feature_plan import TestCaseSpec


def spec():
    return TestCaseSpec.model_validate({
        "case_id": "create_agent", "feature_key": "agents", "title": "Create agent",
        "kind": "happy_path", "steps": [{"action": "navigate", "url": "https://example.com/"}],
        "expected": [
            {"assertion_id": "ready", "oracle": "visible", "target": {"text": "Builder"},
             "expected_value": True, "after_step_ordinal": 0},
            {"assertion_id": "saved", "oracle": "visible_text",
             "target": {"role": "status", "name": "Save status"},
             "expected_value": "Agent saved", "origin": "user_approved"},
        ],
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["not_satisfied", "unverified"])
async def test_unproven_outcome_fails_even_when_steps_complete(status):
    controller = SimpleNamespace(read_assertion=AsyncMock(
        return_value=(None, SimpleNamespace(status=status))))
    handle = SimpleNamespace(session_id=1, execution_id=2, journey_id=3)
    assert await check_skill_assertions(controller, handle, spec(), checkpoint=None) == "saved"
    assert controller.read_assertion.call_args.kwargs["assertion"].assertion_id == "saved"


@pytest.mark.asyncio
async def test_checkpoint_and_approved_values_are_preserved():
    controller = SimpleNamespace(read_assertion=AsyncMock(
        return_value=(None, SimpleNamespace(status="satisfied"))))
    handle = SimpleNamespace(session_id=1, execution_id=2, journey_id=3)
    assert await check_skill_assertions(
        controller, handle, spec(), checkpoint=0, approved_values=("example",),
        run_mode="explore",
    ) is None
    arguments = controller.read_assertion.call_args.kwargs
    assert arguments["assertion"].assertion_id == "ready"
    assert arguments["approved_values"] == ("example",)
    assert arguments["run_mode"] == "explore"
