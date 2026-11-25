"""Project saved Lead checkpoints for the Results activity flow."""

from uuid import UUID

from markettwin_database.models import RunEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def load_activity_checkpoints(
    *, test_run_id: UUID, session: AsyncSession,
) -> list[dict[str, object]]:
    payloads = await session.scalars(
        select(RunEvent.payload)
        .where(RunEvent.test_run_id == test_run_id, RunEvent.event_type == "lead.checkpoint")
        .order_by(RunEvent.occurred_at, RunEvent.id)
    )
    return [
        {"decision": payload["decision"], "reason": payload["reason"]}
        for payload in payloads
        if isinstance(payload.get("decision"), str) and isinstance(payload.get("reason"), str)
    ]
