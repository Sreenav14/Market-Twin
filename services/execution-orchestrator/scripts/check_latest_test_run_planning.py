"""Run Meta Agent planning for the latest TestRun without persisting changes."""

import asyncio
import os

from markettwin_database import (
    create_database_engine,
    create_session_factory,
)
from markettwin_database.models.testing import TestRun
from markettwin_execution_orchestrator.workflow.planning import (
    MetaPlanningRequest,
    generate_meta_agent_plan,
)
from sqlalchemy import select


def database_url() -> str:
    """Build the async PostgreSQL URL from environment variables."""

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
            statement = (
                select(TestRun)
                .order_by(TestRun.created_at.desc())
                .limit(1)
            )

            test_run = await session.scalar(statement)

            if test_run is None:
                print("No TestRun found.")
                return

            study_brief = test_run.configuration_snapshot.get(
                "study_brief"
            )

            if not isinstance(study_brief, str):
                raise RuntimeError(
                    "TestRun configuration_snapshot does not contain "
                    "a valid study_brief."
                )

            print(f"TestRun: {test_run.id}")
            print(f"Current status: {test_run.status}")
            print(f"Study brief: {study_brief}")
            print("\nRunning Meta Agent planning only...\n")

            plan = await generate_meta_agent_plan(
                MetaPlanningRequest(
                    test_run_id=test_run.id,
                    study_brief=study_brief,
                    target_snapshot=test_run.target_snapshot,
                )
            )

            print("Planning SUCCESS")
            print(f"Mission summary: {plan.mission_summary}")
            print(f"Personas: {len(plan.personas)}")
            print(f"Missions: {len(plan.missions)}")

            for index, persona in enumerate(
                plan.personas,
                start=1,
            ):
                print(
                    f"  Persona {index}: "
                    f"{persona.name}"
                )

            for index, mission in enumerate(
                plan.missions,
                start=1,
            ):
                print(
                    f"  Mission {index}: "
                    f"{mission.name}"
                )

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())