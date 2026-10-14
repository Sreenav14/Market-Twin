"""Run MarketTwin evaluation for one completed TestRun."""

import argparse
import asyncio
import os
from uuid import UUID

from markettwin_database import (
    create_database_engine,
)
from markettwin_evaluation_worker.worker import process_run


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

    try:
        result = await process_run(engine, test_run_id)
        if result is None:
            print("Evaluation is already complete, already owned, or the TestRun is not completed.")
            return
        print("MarketTwin evaluation finished.")
        print(f"TestRun: {result.test_run_id}")
        print(f"Findings: {len(result.finding_ids)}")
        print(f"Report: {result.report_id}")

    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("test_run_id", type=UUID)
    args = parser.parse_args()

    asyncio.run(main(args.test_run_id))
