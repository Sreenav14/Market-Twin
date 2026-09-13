"""Inspect persisted Journey results for the latest TestRun."""

import asyncio
import os

from markettwin_database import (
    create_database_engine,
    create_session_factory,
)
from markettwin_database.models.execution import RunEvent
from markettwin_database.models.testing import TestRun
from sqlalchemy import select


def database_url() -> str:
    return (
        "postgresql+asyncpg://"
        f"{os.environ['POSTGRES_USER']}:"
        f"{os.environ['POSTGRES_PASSWORD']}@"
        f"{os.environ['POSTGRES_HOST']}:"
        f"{os.environ['POSTGRES_PORT']}/"
        f"{os.environ['POSTGRES_DB']}"
    )


async def main() -> None:
    engine = create_database_engine(database_url())
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            test_run = await session.scalar(
                select(TestRun)
                .order_by(TestRun.created_at.desc())
                .limit(1)
            )

            if test_run is None:
                print("No TestRun records found.")
                return

            events = (
                await session.scalars(
                    select(RunEvent)
                    .where(
                        RunEvent.test_run_id == test_run.id,
                        RunEvent.event_type == "journey.result",
                    )
                    .order_by(RunEvent.id)
                )
            ).all()

            print(f"TestRun: {test_run.id}")
            print(f"Journey results: {len(events)}")

            for index, event in enumerate(events, start=1):
                payload = event.payload

                print(f"\nJourney {index}:")
                print(f"  key: {payload.get('journey_key')}")
                print(f"  status: {payload.get('status')}")
                print(f"  outcome: {payload.get('outcome')}")
                print(f"  summary: {payload.get('summary')}")
                print(f"  blockers: {payload.get('blockers')}")
                print(f"  final_url: {payload.get('final_url')}")

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())