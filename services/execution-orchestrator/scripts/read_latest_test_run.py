"""Inspect the latest persisted MarketTwin TestRun."""

import asyncio
import os
from typing import Literal, cast

from markettwin_database import (
    create_database_engine,
    create_session_factory,
)
from markettwin_database.models.testing import (
    PersonaJourney,
    RunMission,
    RunPersona,
    TestRun,
)
from markettwin_execution_orchestrator.browser import AllowedOrigin
from markettwin_execution_orchestrator.workflow.run_executor import (
    MarketTwinRunRequest,
)
from sqlalchemy import func, select


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
                print("No TestRun records found.")
                return

            target_snapshot = test_run.target_snapshot
            configuration_snapshot = test_run.configuration_snapshot

            study_brief = cast(
                str,
                configuration_snapshot["study_brief"],
            )

            start_url = cast(
                str,
                target_snapshot["base_url"],
            )

            raw_origins = cast(
                list[dict[str, object]],
                target_snapshot["allowed_origins"],
            )

            allowed_origins = tuple(
                AllowedOrigin(
                    scheme=cast(
                        Literal["http", "https"],
                        origin["scheme"],
                    ),
                    hostname=cast(
                        str,
                        origin["hostname"],
                    ),
                    port=cast(
                        int | None,
                        origin["port"],
                    ),
                    include_subdomains=cast(
                        bool,
                        origin["include_subdomains"],
                    ),
                )
                for origin in raw_origins
            )

            run_request = MarketTwinRunRequest(
                run_id=test_run.id,
                study_brief=study_brief,
                target_snapshot=target_snapshot,
                start_url=start_url,
                allowed_origins=allowed_origins,
            )

            print("MarketTwinRunRequest:")
            print(f"  run_id: {run_request.run_id}")
            print(f"  study_brief: {run_request.study_brief}")
            print(f"  start_url: {run_request.start_url}")
            print(f"  network_policy: {run_request.network_policy}")

            for origin in run_request.allowed_origins:
                print(
                    "  allowed_origin: "
                    f"{origin.scheme}://{origin.hostname}"
                )

            print("\nLatest TestRun:")
            print(f"  id: {test_run.id}")
            print(f"  status: {test_run.status}")
            print(f"  started_at: {test_run.started_at}")
            print(f"  completed_at: {test_run.completed_at}")
            print(f"  application_id: {test_run.application_id}")
            print(f"  target_id: {test_run.target_id}")

            persona_count = await session.scalar(
                select(func.count())
                .select_from(RunPersona)
                .where(
                    RunPersona.test_run_id == test_run.id
                )
            )

            mission_count = await session.scalar(
                select(func.count())
                .select_from(RunMission)
                .where(
                    RunMission.test_run_id == test_run.id
                )
            )

            journey_count = await session.scalar(
                select(func.count())
                .select_from(PersonaJourney)
                .where(
                    PersonaJourney.test_run_id == test_run.id
                )
            )

            print("\nPersisted planning records:")
            print(f"  personas: {persona_count}")
            print(f"  missions: {mission_count}")
            print(f"  journeys: {journey_count}")

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())