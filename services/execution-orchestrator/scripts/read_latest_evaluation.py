"""Inspect evaluation records for the latest TestRun."""

import asyncio
import os

from markettwin_database import (
    create_database_engine,
    create_session_factory,
)
from markettwin_database.models.evaluation import (
    Finding,
    Report,
)
from markettwin_database.models.testing import TestRun
from sqlalchemy import func, select


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

            finding_count = await session.scalar(
                select(func.count())
                .select_from(Finding)
                .where(Finding.test_run_id == test_run.id)
            )

            reports = (
                await session.scalars(
                    select(Report)
                    .where(Report.test_run_id == test_run.id)
                    .order_by(Report.version)
                )
            ).all()

            print(f"TestRun: {test_run.id}")
            print(f"Status: {test_run.status}")
            print(f"Findings: {finding_count}")
            print(f"Reports: {len(reports)}")

            for report in reports:
                print(
                    f"  version={report.version} "
                    f"status={report.status} "
                    f"generated_at={report.generated_at}"
                )

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())