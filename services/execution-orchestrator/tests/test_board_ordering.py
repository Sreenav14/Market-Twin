"""Phase 3 Board-ordering tests (doc 22 section 10, 17): T-RK1 —
the checkpoint's rank_items order is adopted when it is a valid
permutation that changes the order (source 'lead'), and skill items
are never among the candidates. T-RK2 — an invalid permutation, a
door failure, or an order that merely agrees with the Board leaves
board_order_source 'board'.
"""

import pytest
from markettwin_execution_orchestrator.models import ask
from markettwin_execution_orchestrator.workflow.lead_review import (
    review_checkpoint,
)

ITEMS = [
    {"id": "item-a", "label": "Check the pricing page"},
    {"id": "item-b", "label": "Check the signup form"},
    {"id": "item-c", "label": "Check the footer links"},
    {"id": "skill-1", "label": "Replay checkout", "skill_item": True},
]


@pytest.fixture
def lead_review_door(monkeypatch):
    async def fake_model_json(system, user, *, max_tokens=512):
        return {"decision": "continue", "reason": "Plenty of board left."}

    monkeypatch.setattr(ask, "_model_json", fake_model_json)


@pytest.mark.asyncio
async def test_t_rk1_lead_order_adopted_and_skill_items_never_ranked(
    monkeypatch, lead_review_door
):
    seen: dict = {}

    async def fake_rank_items(*, candidates, context):
        seen["candidates"] = candidates
        return ["item-c", "item-a", "item-b"]

    monkeypatch.setattr(ask, "rank_items", fake_rank_items)
    result = await review_checkpoint(
        objective="Test the app",
        evidence={"checked_delta": 3},
        pending_items=ITEMS,
    )
    assert result["decision"] == "continue"
    assert result["board_order"] == ["item-c", "item-a", "item-b"]
    assert result["board_order_source"] == "lead"
    candidate_ids = [c["id"] for c in seen["candidates"]]
    assert candidate_ids == ["item-a", "item-b", "item-c"]  # no skill item


@pytest.mark.asyncio
async def test_t_rk2_invalid_permutation_keeps_board_order(
    monkeypatch, lead_review_door
):
    async def bad_rank_items(*, candidates, context):
        return ["item-a", "item-a", "item-b"]  # duplicate, one missing

    monkeypatch.setattr(ask, "rank_items", bad_rank_items)
    result = await review_checkpoint(
        objective="Test the app",
        evidence={"checked_delta": 3},
        pending_items=ITEMS,
    )
    assert result["board_order"] is None
    assert result["board_order_source"] == "board"


@pytest.mark.asyncio
async def test_t_rk2_agreeing_order_is_board_source(
    monkeypatch, lead_review_door
):
    async def same_rank_items(*, candidates, context):
        return [c["id"] for c in candidates]

    monkeypatch.setattr(ask, "rank_items", same_rank_items)
    result = await review_checkpoint(
        objective="Test the app",
        evidence={"checked_delta": 3},
        pending_items=ITEMS,
    )
    assert result["board_order"] == ["item-a", "item-b", "item-c"]
    assert result["board_order_source"] == "board"


@pytest.mark.asyncio
async def test_t_rk2_door_failure_keeps_board_order(
    monkeypatch, lead_review_door
):
    async def broken_rank_items(*, candidates, context):
        raise RuntimeError("door down")

    monkeypatch.setattr(ask, "rank_items", broken_rank_items)
    result = await review_checkpoint(
        objective="Test the app",
        evidence={"checked_delta": 3},
        pending_items=ITEMS,
    )
    assert result["board_order"] is None
    assert result["board_order_source"] == "board"


@pytest.mark.asyncio
async def test_no_pending_items_means_no_order_keys(lead_review_door):
    # The pre-Phase-3 result shape is exact when no ordering was
    # requested (the incumbent checkpoint contract).
    result = await review_checkpoint(
        objective="Test the app", evidence={"checked_delta": 1}
    )
    assert "board_order" not in result
    assert "board_order_source" not in result
