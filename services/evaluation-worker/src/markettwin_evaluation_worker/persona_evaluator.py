"""Persona evaluation (U-P5-05): a quotes report with NO verdict.

The report groups the walk's anchored impressions by persona and
counts friction signals. There is deliberately no verdict key in the
payload and no score anywhere: feelings are reported, never graded,
and they can never move the product verdict (which only Explore &
Test runs produce, from the Board).
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_database.models import RunEvent

from markettwin_evaluation_worker.persistence.report_repository import (
    ReportRepository,
)

_FRICTION_KINDS = {"slow_load", "page_errors", "small_targets", "no_keyboard_focus"}


async def evaluate_persona_run(
    *, test_run_id: UUID, session: AsyncSession,
) -> tuple[tuple[UUID, ...], UUID]:
    """Build the persona report; returns (finding_ids, report_id).

    Persona runs produce no findings — the empty tuple is the point:
    impressions are not defects and are never promoted silently (the
    one-way valve requires an owner-approved checklist item first).
    """

    result = await session.execute(
        select(RunEvent)
        .where(
            RunEvent.test_run_id == test_run_id,
            RunEvent.event_type == "persona.impression",
        )
        .order_by(RunEvent.occurred_at, RunEvent.id)
    )
    personas: dict[str, dict[str, object]] = {}
    total = 0
    friction_total = 0
    for event in result.scalars():
        payload = event.payload
        persona_id = str(payload.get("persona_id", "unknown"))
        entry = personas.setdefault(persona_id, {
            "persona_id": persona_id,
            "persona_name": payload.get("persona_name"),
            "persona_type": payload.get("persona_type"),
            "impressions": [],
            "friction_count": 0,
        })
        kind = str(payload.get("kind", "observation"))
        entry["impressions"].append({  # type: ignore[union-attr]
            "kind": kind,
            "quote": payload.get("quote"),
            "journey_url": payload.get("journey_url"),
            "page_title": payload.get("page_title"),
            "signal": payload.get("signal") or {},
        })
        total += 1
        if kind in _FRICTION_KINDS:
            entry["friction_count"] = int(entry["friction_count"]) + 1  # type: ignore[arg-type]
            friction_total += 1
    summary = (
        f"{len(personas)} persona(s) walked the app and left {total} "
        f"impression(s), {friction_total} of them friction. Impressions "
        "are reported as quotes; they do not change any verdict."
    )
    report_id = await ReportRepository(session).create_completed_report(
        test_run_id=test_run_id,
        executive_summary=summary,
        report_payload={
            "run_kind": "persona",
            "personas": list(personas.values()),
            "total_impressions": total,
            "friction_count": friction_total,
        },
    )
    return (), report_id
