"""Build a report from the persisted harness board, without upgrading its claims."""

from typing import cast
from uuid import UUID

from markettwin_database.models import PersonaJourney
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_evaluation_worker.board_evaluator import compute_board_verdict
from markettwin_evaluation_worker.persistence.evaluation_repository import EvaluationRepository
from markettwin_evaluation_worker.persistence.report_repository import ReportRepository


async def generate_harness_report(
    *, test_run_id: UUID, snapshot: dict[str, object], session: AsyncSession,
) -> UUID:
    raw_board = snapshot.get("harness_state")
    if not isinstance(raw_board, dict):
        raise ValueError("Completed harness run has no recorded work board.")
    board = cast(dict[str, object], raw_board)
    raw_items = board.get("items")
    if isinstance(raw_items, dict):
        raw_items = list(cast(dict[str, object], raw_items).values())
    if not isinstance(raw_items, list):
        raise ValueError("Completed harness run has an invalid work board.")
    values = cast(list[object], raw_items)
    if any(not isinstance(item, dict) for item in values):
        raise ValueError("Completed harness run has an invalid work board.")
    board_items = cast(list[dict[str, object]], values)
    item_ids = [item.get("item_id") for item in board_items]
    if any(not isinstance(item_id, str) or not item_id for item_id in item_ids):
        raise ValueError("Completed harness run has invalid item identity.")
    if len(set(cast(list[str], item_ids))) != len(item_ids):
        raise ValueError("Completed harness run has duplicate item identity.")
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
            raise ValueError("Completed harness run has an invalid item status.")
        event = events.get(cast(str, item["item_id"]))
        if event is not None and event.get("board_status") != item.get("status"):
            raise ValueError("Board result contradicts its saved item status.")
        if (event is not None and "_journey_id" in event
                and event["_journey_id"] != str(item.get("journey_id"))):
            raise ValueError("Board result does not belong to its saved item journey.")
        if item.get("status") in {"worked", "broken"}:
            try:
                owned = UUID(str(item.get("journey_id"))) in journey_ids
            except ValueError:
                owned = False
            if not owned:
                events.pop(cast(str, item["item_id"]), None)
    board_section = compute_board_verdict(board_document=board, board_results=events)
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
    return await ReportRepository(session).create_completed_report(
        test_run_id=test_run_id, executive_summary=summary,
        report_payload={"schema_version": 1, "mode": "harness_v1",
                        "run_kind": "explore_test", "items": items,
                        "verdict": board_section["verdict"], "board": board_section},
    )
