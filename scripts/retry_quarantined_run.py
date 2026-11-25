"""Return one quarantined dispatch or report to its existing worker queue."""

import argparse
import asyncio
from uuid import UUID

from dotenv import load_dotenv
from markettwin_control_api.config import Settings
from markettwin_control_api.database import DatabaseRuntime
from markettwin_database.models import OutboxEvent, Report, TestRun
from markettwin_database.repositories import OutboxRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def retry(session: AsyncSession, run_id: UUID, stage: str) -> bool:
    run = await session.get(TestRun, run_id, with_for_update=True)
    if run is None:
        return False
    if stage == "dispatch":
        if run.status != "queued":
            return False
        events = (await session.scalars(select(OutboxEvent).where(
            OutboxEvent.aggregate_id == run_id,
            OutboxEvent.event_type == "run.requested",
            OutboxEvent.published_at.is_(None),
            OutboxEvent.quarantined_at.is_not(None),
        ).with_for_update().limit(2))).all()
        if len(events) != 1:
            return False
        await OutboxRepository(session).retry_quarantined(events[0])
        return True

    if run.status != "completed" or run.evaluation_quarantined_at is None:
        return False
    report = await session.scalar(select(Report.id).where(
        Report.test_run_id == run_id,
        Report.version == 1,
        Report.status == "completed",
    ).limit(1))
    if report is not None:
        return False
    run.evaluation_attempts = 0
    run.evaluation_next_attempt_at = None
    run.evaluation_quarantined_at = None
    run.evaluation_last_error = None
    return True


async def main(run_id: UUID, stage: str) -> bool:
    load_dotenv()
    runtime = DatabaseRuntime(Settings())
    try:
        async with runtime.session_factory.begin() as session:
            return await retry(session, run_id, stage)
    finally:
        await runtime.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("dispatch", "evaluation"))
    parser.add_argument("run_id", type=UUID)
    args = parser.parse_args()
    if not asyncio.run(main(args.run_id, args.stage)):
        parser.exit(1, "No eligible quarantined work was found for the specified run.\n")
    print(f"Returned {args.stage} for {args.run_id} to its worker queue.")
