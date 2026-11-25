"""Build a report from the persisted harness board, without upgrading its claims."""

import logging
from typing import cast
from uuid import UUID

from markettwin_database.models import PersonaJourney
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_evaluation_worker.activity_checkpoints import load_activity_checkpoints
from markettwin_evaluation_worker.errors import InvalidEvaluationInput
from markettwin_evaluation_worker.board_evaluator import (
    compute_board_verdict,
    market_verdict_section,
)
from markettwin_evaluation_worker.persistence.evaluation_repository import EvaluationRepository
from markettwin_evaluation_worker.persistence.report_repository import ReportRepository

logger = logging.getLogger(__name__)


async def generate_harness_report(
    *, test_run_id: UUID, snapshot: dict[str, object], session: AsyncSession,
) -> UUID:
    raw_board = snapshot.get("harness_state")
    if not isinstance(raw_board, dict):
        raise InvalidEvaluationInput("board_missing", "Completed harness run has no recorded work board.")
    board = cast(dict[str, object], raw_board)
    raw_items = board.get("items")
    if isinstance(raw_items, dict):
        raw_items = list(cast(dict[str, object], raw_items).values())
    if not isinstance(raw_items, list):
        raise InvalidEvaluationInput("board_invalid", "Completed harness run has an invalid work board.")
    values = cast(list[object], raw_items)
    if any(not isinstance(item, dict) for item in values):
        raise InvalidEvaluationInput("board_invalid", "Completed harness run has an invalid work board.")
    board_items = cast(list[dict[str, object]], values)
    item_ids = [item.get("item_id") for item in board_items]
    if any(not isinstance(item_id, str) or not item_id for item_id in item_ids):
        raise InvalidEvaluationInput("board_item_identity", "Completed harness run has invalid item identity.")
    if len(set(cast(list[str], item_ids))) != len(item_ids):
        raise InvalidEvaluationInput("board_item_identity", "Completed harness run has duplicate item identity.")
    journey_ids = set((await session.scalars(select(PersonaJourney.id).where(
        PersonaJourney.test_run_id == test_run_id,
    ))).all())
    events = await EvaluationRepository(session).list_board_item_results(
        test_run_id=test_run_id, strict=True,
    )
    allowed = {"worked", "broken", "could_not_check", "not_checked", "blocked",
               "owner_disabled", "pending", "running", "needs_human_login"}
    for item in board_items:
        if item.get("status") not in allowed:
            raise InvalidEvaluationInput("board_item_status", "Completed harness run has an invalid item status.")
        event = events.get(cast(str, item["item_id"]))
        if event is not None and event.get("board_status") != item.get("status"):
            raise InvalidEvaluationInput("board_result_status_mismatch", "Board result contradicts its saved item status.")
        if (event is not None and "_journey_id" in event
                and event["_journey_id"] != str(item.get("journey_id"))):
            raise InvalidEvaluationInput("board_result_owner_mismatch", "Board result does not belong to its saved item journey.")
        if item.get("status") in {"worked", "broken"}:
            try:
                owned = UUID(str(item.get("journey_id"))) in journey_ids
            except ValueError:
                owned = False
            if not owned:
                events.pop(cast(str, item["item_id"]), None)
    board_section = compute_board_verdict(board_document=board, board_results=events)
    market_section = market_verdict_section(board_section)
    if (market_section["verdict"] == "insufficient_evidence"
            and board_section["verdict"] != "Can't tell yet"):
        logger.warning(
            "market_verdict projection fell back to cannot-tell for a board "
            "verdict of %r; the report carries the explicit fallback section.",
            board_section["verdict"],
        )
    outcomes = cast(list[dict[str, object]], board_section["items"])
    items: list[dict[str, object]] = []
    for item, outcome in zip(board_items, outcomes, strict=True):
        name = item.get("name")
        role = item.get("role")
        status = outcome["effective_status"]
        journey_id = None
        try:
            candidate = UUID(str(item.get("journey_id")))
            if candidate in journey_ids:
                journey_id = str(candidate)
        except ValueError:
            pass
        if journey_id is not None:
            outcome["journey_id"] = journey_id
        reason = item.get("reason") or item.get("blocker")
        if outcome["missing_result_event"]:
            reason = "missing_result_event"
        locator = item.get("locator")
        if not reason and isinstance(locator, dict):
            reason = cast(dict[str, object], locator).get("tier")
        items.append({
            "name": name if isinstance(name, str) and name else "Unnamed check",
            "role": role if isinstance(role, str) else "",
            "status": status if isinstance(status, str) else "unknown",
            "reason": reason if isinstance(reason, str) else None,
            "journey_id": journey_id,
        })
    coverage = cast(dict[str, object], board_section["coverage"])
    summary = (f"{board_section['verdict']}. Checked {coverage['checked']} of "
               f"{coverage['total_items']} discovered items; "
               f"{coverage['denominator']} eligible after owner exclusions. "
               "The verdict applies only to the recorded scope.")
    checkpoints = await load_activity_checkpoints(test_run_id=test_run_id, session=session)
    return await ReportRepository(session).create_completed_report(
        test_run_id=test_run_id, executive_summary=summary,
        report_payload={"schema_version": 1, "mode": "harness_v1",
                        "run_kind": "explore_test", "items": items,
                        "verdict": board_section["verdict"], "board": board_section,
                        "market_verdict": market_section,
                        **({"budget_counters": board["budget_counters"]}
                           if "budget_counters" in board else {}),
                        **({"activity_checkpoints": checkpoints} if checkpoints else {})},
    )
