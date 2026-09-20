"""Run MarketTwin evaluation for one completed TestRun."""

import argparse
import asyncio
import os
from uuid import UUID

from markettwin_database import (
    create_database_engine,
    create_session_factory,
)
from markettwin_evaluation_worker.workflow import (
    evaluate_and_generate_report,
)


def database_url() -> str:
    return (
        "postgresql+asyncpg://"
        f"{os.environ['POSTGRES_USER']}:"
        f"{os.environ['POSTGRES_PASSWORD']}@"
        f"{os.environ['POSTGRES_HOST']}:"
        f"{os.environ['POSTGRES_PORT']}/"
        f"{os.environ['POSTGRES_DB']}"
    )


async def main(test_run_id: UUID) -> None:
    engine = create_database_engine(database_url())
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            result = await evaluate_and_generate_report(
                test_run_id=test_run_id,
                session=session,
            )

            print("MarketTwin evaluation finished.")
            print(f"TestRun: {result.test_run_id}")
            print(f"Findings: {len(result.finding_ids)}")
            print(f"Visual checks:"
                  f"{result.visual_evaluation_count}"
                  )
            print(f"Report: {result.report_id}")

    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("test_run_id", type=UUID)
    args = parser.parse_args()

    asyncio.run(main(args.test_run_id))