"""Inspect findings for the latest TestRun."""

import asyncio
import os

from markettwin_database import (
    create_database_engine,
    create_session_factory,
)
from markettwin_database.models import (
    Finding,
    FindingEvidence,
    FindingJourney,
    TestRun,
)
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

            findings = (
                await session.scalars(
                    select(Finding)
                    .where(Finding.test_run_id == test_run.id)
                    .order_by(Finding.created_at)
                )
            ).all()

            print(f"TestRun: {test_run.id}")
            print(f"Findings: {len(findings)}")

            for index, finding in enumerate(findings, start=1):
                journey_count = await session.scalar(
                    select(func.count())
                    .select_from(FindingJourney)
                    .where(
                        FindingJourney.finding_id == finding.id
                    )
                )

                evidence_count = await session.scalar(
                    select(func.count())
                    .select_from(FindingEvidence)
                    .where(
                        FindingEvidence.finding_id == finding.id
                    )
                )

                print()
                print(
                    f"{index}. [{finding.severity}] "
                    f"{finding.category}"
                )
                print(f"   {finding.title}")
                print(f"   Journeys: {journey_count}")
                print(f"   Evidence refs: {evidence_count}")
                print(f"   Summary: {finding.summary}")
                print(
                    f"   Recommendation: "
                    f"{finding.recommendation}"
                )

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())