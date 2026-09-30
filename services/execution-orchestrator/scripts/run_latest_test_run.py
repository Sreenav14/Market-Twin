"""Execute the latest draft MarketTwin TestRun."""

import asyncio
import os

from markettwin_database import (
    create_database_engine,
    create_session_factory,
)
from markettwin_database.models.testing import TestRun
from markettwin_evaluation_worker.workflow import (
    evaluate_and_generate_report,
)
from markettwin_execution_orchestrator.workflow.run_executor import (
    execute_markettwin_run,
)
from markettwin_execution_orchestrator.workflow.run_request import (
    build_run_request,
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

            request = build_run_request(test_run)

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

            print("\nGenerating evaluation findings and report...")
            evaluation = await evaluate_and_generate_report(
                test_run_id=request.run_id,
                session=session,
            )

            print("MarketTwin evaluation finished.")
            print(f"Findings: {len(evaluation.finding_ids)}")
            print(
                "Visual checks: "
                f"{evaluation.visual_evaluation_count}"
            )
            print(f"Report: {evaluation.report_id}")

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())