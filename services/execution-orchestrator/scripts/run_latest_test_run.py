"""Execute the latest draft MarketTwin TestRun."""

import asyncio
import os
from typing import Literal, cast

from markettwin_database import (
    create_database_engine,
    create_session_factory,
)
from markettwin_database.models.testing import TestRun
from markettwin_execution_orchestrator.browser import AllowedOrigin
from markettwin_execution_orchestrator.workflow.run_executor import (
    MarketTwinRunRequest,
    execute_markettwin_run,
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
                .where(TestRun.status == "draft")
                .order_by(TestRun.created_at.desc())
                .limit(1)
            )

            test_run = await session.scalar(statement)

            if test_run is None:
                print("No draft TestRun found.")
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

            request = MarketTwinRunRequest(
                run_id=test_run.id,
                study_brief=study_brief,
                target_snapshot=target_snapshot,
                start_url=start_url,
                allowed_origins=allowed_origins,
                max_duration_seconds_per_journey=90,
            )

            print(f"Executing TestRun: {request.run_id}")
            print(f"Goal: {request.study_brief}")
            print(f"Target: {request.start_url}")

            result = await execute_markettwin_run(
                request,
                session=session,
            )

            print("\nMarketTwin execution finished.")
            print(f"Journeys: {len(result.journeys)}")
            print(f"Completed: {result.completed_count}")
            print(
                "Failed/non-completed: "
                f"{result.failed_count}"
            )

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())