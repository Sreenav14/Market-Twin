"""Verify that persisted artifacts physically exist in MinIO/S3."""

import asyncio
import os

from boto3.session import Session
from markettwin_database import (
    create_database_engine,
    create_session_factory,
)
from markettwin_database.models import (
    AgentExecution,
    Artifact,
    PersonaJourney,
    TestRun,
)
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
                print("No TestRun found.")
                return

            artifacts = (
                await session.scalars(
                    select(Artifact)
                    .join(
                        AgentExecution,
                        AgentExecution.id == Artifact.execution_id,
                    )
                    .join(
                        PersonaJourney,
                        PersonaJourney.id == AgentExecution.journey_id,
                    )
                    .where(
                        PersonaJourney.test_run_id == test_run.id,
                        Artifact.artifact_type.in_(
                            ["screenshot", "trace"]
                        ),
                    )
                    .order_by(Artifact.created_at)
                )
            ).all()

            # One screenshot + one trace is enough for this proof.
            selected = []
            seen_types = set()

            for artifact in artifacts:
                if artifact.artifact_type not in seen_types:
                    selected.append(artifact)
                    seen_types.add(artifact.artifact_type)

                if seen_types == {"screenshot", "trace"}:
                    break

            s3 = Session().client(
                "s3",
                region_name=os.environ.get(
                    "S3_REGION",
                    "us-east-1",
                ),
                endpoint_url=(
                    os.environ.get("S3_ENDPOINT_URL")
                    or None
                ),
            )

            print(f"TestRun: {test_run.id}")

            for artifact in selected:
                head = s3.head_object(
                    Bucket=artifact.bucket,
                    Key=artifact.object_key,
                )

                actual_size = head["ContentLength"]
                expected_size = artifact.size_bytes

                print()
                print(f"Type: {artifact.artifact_type}")
                print(f"Bucket: {artifact.bucket}")
                print(f"Key: {artifact.object_key}")
                print(f"DB size: {expected_size}")
                print(f"Object size: {actual_size}")
                print(
                    "MATCH"
                    if actual_size == expected_size
                    else "SIZE MISMATCH"
                )

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())