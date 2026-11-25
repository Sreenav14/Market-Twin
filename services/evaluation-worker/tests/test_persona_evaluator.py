"""U-P5-05: the persona report groups quotes and carries NO verdict."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from markettwin_evaluation_worker import persona_evaluator


def _event(persona_id: str, kind: str, quote: str) -> SimpleNamespace:
    return SimpleNamespace(event_type="persona.impression", payload={
        "persona_id": persona_id, "persona_name": "Impatient mobile user",
        "persona_type": "impatient_mobile", "kind": kind, "quote": quote,
        "journey_url": "https://app.example.test/home", "page_title": "Home",
        "signal": {"load_ms": 4200} if kind == "slow_load" else {},
    })


@pytest.mark.asyncio
async def test_persona_report_groups_quotes_and_has_no_verdict(monkeypatch) -> None:
    events = [
        _event("impatient_mobile-1", "slow_load", "I waited 4.2 seconds…"),
        _event("impatient_mobile-1", "fast_and_clean", "That felt easy."),
        _event("expert-1", "page_errors", "Something broke…"),
    ]
    captured: dict = {}

    class _Reports:
        def __init__(self, session):
            pass

        async def create_completed_report(self, **kwargs):
            captured.update(kwargs)
            return uuid4()

    monkeypatch.setattr(persona_evaluator, "ReportRepository", _Reports)
    result = Mock()
    result.scalars = Mock(return_value=iter(events))
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    session.scalars = AsyncMock(return_value=[])
    finding_ids, report_id = await persona_evaluator.evaluate_persona_run(
        test_run_id=uuid4(), session=session,
    )
    assert finding_ids == ()
    payload = captured["report_payload"]
    assert payload["run_kind"] == "persona"
    assert "verdict" not in payload
    assert payload["total_impressions"] == 3
    assert payload["friction_count"] == 2
    by_id = {p["persona_id"]: p for p in payload["personas"]}
    assert by_id["impatient_mobile-1"]["friction_count"] == 1
    assert by_id["expert-1"]["impressions"][0]["quote"] == "Something broke…"
    assert "score" not in str(payload).lower()
def _typed_event(event_type: str, payload: dict) -> SimpleNamespace:
    return SimpleNamespace(event_type=event_type, payload=payload)


@pytest.mark.asyncio
async def test_a4_report_preserves_type_friction_stop_and_partiality(monkeypatch) -> None:
    """Astra A4: the report projection used to drop run context —
    persona_type stayed null when the first event could not carry it
    (the goal attempt's task result has no persona_type), a
    focus_indicator_invisible impression never counted as friction,
    the Lead stop's stop_kind/reason were projected away, and the
    run.collection event carrying partial + stopped_personas was
    never even selected."""
    events = [
        _typed_event("persona.task.result", {
            "persona_id": "keyboard-1", "persona_name": "Keyboard-only user",
            "objective": "Find pricing", "status": "attempted",
            "account": "Tried the menus", "source": "simulated_persona",
            "verified_completion": False, "action_trace": [{"action": "open menu"}],
            "blocker": "Pricing link missing", "knowledge_requirement_ids": [],
        }),
        _typed_event("persona.keyboard_walk", {
            "persona_id": "keyboard-1", "journey_url": "https://app.example.test/home",
            "tabs": 2, "steps": [{"tab": 1, "role": "button", "name": "Buy",
                                  "indicator_visible": False}, {"tab": 2, "focused": None}],
        }),
        _typed_event("persona.keyboard_walk", {
            "persona_id": "keyboard-1", "tabs": 0, "steps": [], "failure": "TimeoutError",
        }),
        _typed_event("persona.impression", {
            "persona_id": "keyboard-1", "persona_name": "Keyboard-only user",
            "persona_type": "keyboard_only",
            "kind": "focus_indicator_invisible",
            "quote": "I tabbed to Buy and could not see where I was",
            "journey_url": "https://app.example.test/home",
            "page_title": "Home",
            "signal": {"element": "Buy (button)", "tab": 3},
        }),
        _typed_event("persona.task.result", {
            "persona_id": "keyboard-1", "persona_name": "Keyboard-only user",
            "persona_type": "keyboard_only", "status": "stopped_at_checkpoint",
            "stop_kind": "safety", "reason": "Unsafe page",
            "source": "lead_stop", "impressions": 1,
        }),
        _typed_event("run.collection", {
            "run_kind": "persona", "journey_count": 1, "personas_selected": 1,
            "partial": True,
            "stopped_personas": [
                {"persona_id": "keyboard-1", "stop_kind": "safety"},
            ],
        }),
    ]
    captured: dict = {}

    class _Reports:
        def __init__(self, session):
            pass

        async def create_completed_report(self, **kwargs):
            captured.update(kwargs)
            return uuid4()

    monkeypatch.setattr(persona_evaluator, "ReportRepository", _Reports)
    result = Mock()
    result.scalars = Mock(return_value=iter(events))
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    session.scalars = AsyncMock(return_value=[{"decision": "stop", "reason": "Unsafe page"}])
    finding_ids, report_id = await persona_evaluator.evaluate_persona_run(
        test_run_id=uuid4(), session=session,
    )
    assert finding_ids == ()
    payload = captured["report_payload"]
    assert len(payload["personas"]) == 1
    entry = payload["personas"][0]
    assert entry["persona_type"] == "keyboard_only"
    assert entry["friction_count"] == 1
    assert payload["friction_count"] == 1
    assert payload["total_impressions"] == 1
    assert entry["tasks"][0]["action_trace"] == [{"action": "open menu"}]
    assert entry["tasks"][0]["blocker"] == "Pricing link missing"
    assert "knowledge_requirement_ids" not in entry["tasks"][0]
    assert entry["keyboard_walk"] == {
        "tabs": 2, "steps": [{"tab": 1, "role": "button", "name": "Buy",
                              "indicator_visible": False}, {"tab": 2, "focused": None}],
    }
    assert payload["activity_checkpoints"] == [{"decision": "stop", "reason": "Unsafe page"}]
    stop_task = next(
        task for task in entry["tasks"]
        if task["status"] == "stopped_at_checkpoint"
    )
    assert stop_task["stop_kind"] == "safety"
    assert stop_task["reason"] == "Unsafe page"
    assert payload["collection"]["partial"] is True
    assert payload["collection"]["stopped_personas"] == [
        {"persona_id": "keyboard-1", "stop_kind": "safety"},
    ]
