from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from markettwin_execution_orchestrator.workflow import persona_goal
from markettwin_execution_orchestrator.browser.errors import BrowserActionBlockedError


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", [False, True])
async def test_goal_account_never_becomes_verified_completion(monkeypatch, blocked):
    async def browser_click(**kw):
        raise BrowserActionBlockedError("Observed signup control requires human authentication")
    monkeypatch.setattr(persona_goal, "create_browser_tools", lambda **kw: [browser_click])
    monkeypatch.setattr(persona_goal, "create_model", lambda **kw: object())
    captured = {}
    def agent(**kw):
        captured.update(kw)
        return object()
    monkeypatch.setattr(persona_goal, "LlmAgent", agent)
    monkeypatch.setattr(persona_goal, "InMemorySessionService", lambda: SimpleNamespace(create_session=AsyncMock()))

    class Runner:
        def __init__(self, **kw):
            pass

        async def run_async(self, **kw):
            assert kw["run_config"].max_llm_calls == 16
            prompt = kw["new_message"].parts[0].text
            assert "Find pricing" in prompt
            assert "Sourced app reference data" not in prompt
            assert "supplied sourced app knowledge" not in captured["instruction"]
            if blocked:
                await captured["tools"][0]()
            yield SimpleNamespace(is_final_response=lambda: True,
                content=SimpleNamespace(parts=[SimpleNamespace(text="I found the pricing page.")]))

    monkeypatch.setattr(persona_goal, "Runner", Runner)
    definition = SimpleNamespace(name="New visitor",
        voice=SimpleNamespace(perspective="First visit", focus="Understand pricing"),
        conditions=SimpleNamespace(input="pointer"))
    result = await persona_goal.attempt_goal(controller=object(), handle=object(),
        definition=definition, objective="Find pricing", seconds=5)
    assert result["status"] == ("blocked" if blocked else "attempted")
    assert result["verified_completion"] is False
    assert result["knowledge_requirement_ids"] == []
    if blocked:
        assert result["blocker"]["tool"] == "browser_click"
        assert "human authentication" in result["account"]
        assert result["action_trace"] == [{"tool": "browser_click", "status": "blocked"}]


@pytest.mark.asyncio
async def test_goal_call_limit_exhaustion_is_a_named_ending(monkeypatch):
    """FIX-3: ADK raises LlmCallsLimitExceededError out of the run stream
    when the attempt's model-call budget is spent (live run MT-000163).
    It must end THIS attempt named, with the original error retained --
    not escape and fail the whole persona run."""
    from google.adk.agents.invocation_context import LlmCallsLimitExceededError

    async def browser_click(**kw):
        return None
    monkeypatch.setattr(persona_goal, "create_browser_tools", lambda **kw: [browser_click])
    monkeypatch.setattr(persona_goal, "create_model", lambda **kw: object())
    monkeypatch.setattr(persona_goal, "LlmAgent", lambda **kw: object())
    monkeypatch.setattr(persona_goal, "InMemorySessionService", lambda: SimpleNamespace(create_session=AsyncMock()))

    class Runner:
        def __init__(self, **kw):
            pass

        async def run_async(self, **kw):
            raise LlmCallsLimitExceededError("Max number of llm calls limit of `16` exceeded.")
            yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(persona_goal, "Runner", Runner)
    definition = SimpleNamespace(name="New visitor",
        voice=SimpleNamespace(perspective="First visit", focus="Understand pricing"),
        conditions=SimpleNamespace(input="pointer"))
    result = await persona_goal.attempt_goal(controller=object(), handle=object(),
        definition=definition, objective="Find pricing", seconds=5)
    assert result["status"] == "call_limit_exhausted"
    assert result["blocker"]["error_type"] == "LlmCallsLimitExceededError"
    assert "16" in result["blocker"]["reason"]
    assert "call limit" in result["account"]
    assert result["verified_completion"] is False
