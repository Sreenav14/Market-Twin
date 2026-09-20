"""Inspect execution steps and evidence for the latest TestRun."""

import asyncio
import os

from markettwin_database import (
    create_database_engine,
    create_session_factory,
)
from markettwin_database.models.evidence import Artifact
from markettwin_database.models.execution import (
    AgentExecution,
    ExecutionStep,
)
from markettwin_database.models.testing import (
    PersonaJourney,
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

            execution_ids = (
                select(AgentExecution.id)
                .join(
                    PersonaJourney,
                    AgentExecution.journey_id == PersonaJourney.id,
                )
                .where(
                    PersonaJourney.test_run_id == test_run.id
                )
            )

            execution_count = await session.scalar(
                select(func.count())
                .select_from(AgentExecution)
                .where(AgentExecution.id.in_(execution_ids))
            )

            step_count = await session.scalar(
                select(func.count())
                .select_from(ExecutionStep)
                .where(ExecutionStep.execution_id.in_(execution_ids))
            )

            artifact_count = await session.scalar(
                select(func.count())
                .select_from(Artifact)
                .where(Artifact.execution_id.in_(execution_ids))
            )

            print(f"TestRun: {test_run.id}")
            print(f"Agent executions: {execution_count}")
            print(f"Execution steps: {step_count}")
            print(f"Artifacts: {artifact_count}")

            artifact_types = (
                await session.execute(
                    select(
                        Artifact.artifact_type,
                        func.count(Artifact.id),
                    )
                    .where(
                        Artifact.execution_id.in_(execution_ids)
                    )
                    .group_by(Artifact.artifact_type)
                    .order_by(Artifact.artifact_type)
                )
            ).all()

            print("\nArtifacts by type:")

            for artifact_type, count in artifact_types:
                print(f"  {artifact_type}: {count}")

            artifacts = (
                await session.scalars(
                    select(Artifact)
                    .where(
                        Artifact.execution_id.in_(execution_ids)
                    )
                    .order_by(Artifact.created_at)
                    .limit(10)
                )
            ).all()

            print("\nFirst artifacts:")

            for artifact in artifacts:
                print(
                    f"  {artifact.id} | "
                    f"  {artifact.artifact_type} | "
                    f"{artifact.storage_provider} | "
                    f"{artifact.bucket} | "
                    f"{artifact.size_bytes} bytes | "
                    f"sha256={artifact.sha256}"
                )

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())