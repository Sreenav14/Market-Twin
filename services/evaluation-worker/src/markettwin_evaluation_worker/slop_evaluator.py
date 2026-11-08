"""Slop evaluation (U-P6-05): three family numbers, no verdict.

Reads the executor's slop.state.result verdict rows and aggregates
them with the shared three-family aggregate. The payload carries the
slop percentage (or its suppression headline), the defect counts,
and the effort family's honest empty state — three currencies,
never blended, and no verdict key: readiness comes only from
Explore & Test.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_database.models import RunEvent
from markettwin_shared.slop_aggregate import aggregate_run

from markettwin_evaluation_worker.persistence.report_repository import (
    ReportRepository,
)


async def evaluate_slop_run(
    *, test_run_id: UUID, session: AsyncSession,
) -> tuple[tuple[UUID, ...], UUID]:
    result = await session.execute(
        select(RunEvent)
        .where(
            RunEvent.test_run_id == test_run_id,
            RunEvent.event_type == "slop.state.result",
        )
        .order_by(RunEvent.occurred_at, RunEvent.id)
    )
    states = [
        {
            "url": event.payload.get("url"),
            "elements": event.payload.get("elements", []),
            "page_signals": event.payload.get("page_signals", []),
            "js_errors": event.payload.get("js_errors", []),
        }
        for event in result.scalars()
    ]
    families = aggregate_run(states)
    slop = families["slop"]
    defects = families["defects"]
    summary = (
        f"Checked the look of {families['states_visited']} page(s): "
        f"slop {slop['headline']} from {slop['judged']} judged element(s) "
        f"({slop['severe']} severe, {slop['minor']} minor); "
        f"{defects['serious']} serious and {defects['minor']} minor "
        "JavaScript/defect signal(s). These numbers describe the look "
        "and the code health; they do not change any verdict."
    )
    report_id = await ReportRepository(session).create_completed_report(
        test_run_id=test_run_id,
        executive_summary=summary,
        report_payload={
            "run_kind": "slop",
            "families": families,
            "states": [
                {
                    "url": state["url"],
                    "page_signals": state["page_signals"],
                    "js_errors": state["js_errors"],
                }
                for state in states
            ],
        },
    )
    return (), report_id
