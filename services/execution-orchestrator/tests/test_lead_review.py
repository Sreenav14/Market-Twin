from unittest.mock import AsyncMock

import pytest

from markettwin_execution_orchestrator.workflow import lead_review
from markettwin_execution_orchestrator.slop.visual_review import review_screenshots


@pytest.mark.asyncio
async def test_unavailable_lead_stops_instead_of_running_unsupervised(monkeypatch):
    monkeypatch.setattr(lead_review.ask, "_model_json", AsyncMock(side_effect=TimeoutError))
    result = await lead_review.review_checkpoint(objective="Audit", evidence={})
    assert result["decision"] == "stop"


@pytest.mark.asyncio
async def test_missing_screenshot_is_unassessed_not_clean():
    result = await review_screenshots([{"screenshot_path": None}])
    assert result[0]["rule_id"] == "UI_VISUAL_UNASSESSED"


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", [None, "", "   "])
async def test_lead_cannot_continue_without_explanation(monkeypatch, reason):
    monkeypatch.setattr(lead_review.ask, "_model_json", AsyncMock(
        return_value={"decision": "continue", "reason": reason}))
    result = await lead_review.review_checkpoint(objective="Audit", evidence={})
    assert result["decision"] == "stop"
    assert result["source"] == "fallback"


@pytest.mark.asyncio
async def test_stagnation_continue_without_a_named_change_is_gated(monkeypatch):
    monkeypatch.setattr(lead_review.ask, "_model_json", AsyncMock(
        return_value={"decision": "continue", "reason": "Keep going."}))
    result = await lead_review.review_checkpoint(
        objective="Audit", evidence={"stagnation": True})
    assert result["decision"] == "stop"
    assert result["source"] == "stagnation_gate"


@pytest.mark.asyncio
async def test_stagnation_continue_with_a_named_change_passes(monkeypatch):
    monkeypatch.setattr(lead_review.ask, "_model_json", AsyncMock(
        return_value={"decision": "continue", "reason": "Try the other queue first.",
                      "change": "Reorder the queue to pending routes first."}))
    result = await lead_review.review_checkpoint(
        objective="Audit", evidence={"stagnation": True})
    assert result["decision"] == "continue"
    assert result["source"] == "lead"
    assert result["change"] == "Reorder the queue to pending routes first."


@pytest.mark.asyncio
async def test_continue_without_stagnation_is_unchanged(monkeypatch):
    monkeypatch.setattr(lead_review.ask, "_model_json", AsyncMock(
        return_value={"decision": "continue", "reason": "Coverage is growing."}))
    result = await lead_review.review_checkpoint(
        objective="Audit", evidence={"checked_delta": 5})
    assert result == {"decision": "continue", "reason": "Coverage is growing.",
                      "source": "lead"}


@pytest.mark.asyncio
async def test_stagnation_stop_with_measured_progress_is_vetoed(monkeypatch):
    monkeypatch.setattr(lead_review.ask, "_model_json", AsyncMock(
        return_value={"decision": "stop", "reason": "Nothing is moving.",
                      "stop_kind": "stagnation"}))
    result = await lead_review.review_checkpoint(
        objective="Audit", evidence={"productive_delta": 4, "checked_delta": 5})
    assert result["decision"] == "continue"
    assert result["source"] == "harness_veto"
    assert result["overruled_stop"] == "Nothing is moving."


@pytest.mark.asyncio
async def test_safety_stop_stands_despite_measured_progress(monkeypatch):
    monkeypatch.setattr(lead_review.ask, "_model_json", AsyncMock(
        return_value={"decision": "stop", "reason": "Unsafe control.",
                      "stop_kind": "safety"}))
    result = await lead_review.review_checkpoint(
        objective="Audit", evidence={"productive_delta": 4})
    assert result["decision"] == "stop"
    assert result["source"] == "lead"
    assert result["stop_kind"] == "safety"


@pytest.mark.asyncio
async def test_stagnation_stop_with_zero_progress_stands(monkeypatch):
    monkeypatch.setattr(lead_review.ask, "_model_json", AsyncMock(
        return_value={"decision": "stop", "reason": "Nothing is moving.",
                      "stop_kind": "stagnation"}))
    result = await lead_review.review_checkpoint(
        objective="Audit", evidence={"productive_delta": 0, "checked_delta": 0})
    assert result["decision"] == "stop"
    assert result["source"] == "lead"


@pytest.mark.asyncio
async def test_untyped_stop_stands_despite_measured_progress(monkeypatch):
    monkeypatch.setattr(lead_review.ask, "_model_json", AsyncMock(
        return_value={"decision": "stop", "reason": "I judge this stuck."}))
    result = await lead_review.review_checkpoint(
        objective="Audit", evidence={"productive_delta": 4})
    assert result["decision"] == "stop"
    assert result["source"] == "lead"
    assert "stop_kind" not in result


@pytest.mark.asyncio
async def test_access_blocker_stop_with_few_blocked_and_much_unattempted_is_vetoed(monkeypatch):
    # MT-000162 / MT-000164: the Lead stopped at 15/175 with 4-5 blocked
    # and 160 items never attempted; the verdict came out "Can't tell
    # yet" on a board that was barely touched.
    monkeypatch.setattr(lead_review.ask, "_model_json", AsyncMock(
        return_value={"decision": "stop",
                      "reason": "The Sign up control is blocked, and the evidence shows five blocked items.",
                      "stop_kind": "access_blocker"}))
    result = await lead_review.review_checkpoint(
        objective="Audit", evidence={
            "discovered_items": 175,
            "remaining_items": 160,
            "counts": {"worked": 6, "broken": 4, "blocked": 5,
                       "pending": 160, "not_checked": 0,
                       "could_not_check": 0},
        })
    assert result["decision"] == "continue"
    assert result["source"] == "harness_veto"
    assert result["overruled_stop"] == (
        "The Sign up control is blocked, and the evidence shows five "
        "blocked items.")


@pytest.mark.asyncio
async def test_access_blocker_stop_stands_when_all_remaining_are_blocked(monkeypatch):
    monkeypatch.setattr(lead_review.ask, "_model_json", AsyncMock(
        return_value={"decision": "stop", "reason": "Everything left is blocked.",
                      "stop_kind": "access_blocker"}))
    result = await lead_review.review_checkpoint(
        objective="Audit", evidence={
            "discovered_items": 15,
            "remaining_items": 0,
            "counts": {"worked": 3, "broken": 0, "blocked": 12,
                       "pending": 0, "not_checked": 0,
                       "could_not_check": 0},
        })
    assert result["decision"] == "stop"
    assert result["source"] == "lead"
    assert result["stop_kind"] == "access_blocker"


@pytest.mark.asyncio
async def test_access_blocker_stop_stands_when_blocked_share_is_large(monkeypatch):
    monkeypatch.setattr(lead_review.ask, "_model_json", AsyncMock(
        return_value={"decision": "stop", "reason": "Most of the site refuses access.",
                      "stop_kind": "access_blocker"}))
    result = await lead_review.review_checkpoint(
        objective="Audit", evidence={
            "discovered_items": 175,
            "remaining_items": 60,
            "counts": {"worked": 20, "broken": 5, "blocked": 90,
                       "pending": 60, "not_checked": 0,
                       "could_not_check": 0},
        })
    assert result["decision"] == "stop"
    assert result["source"] == "lead"
    assert result["stop_kind"] == "access_blocker"
