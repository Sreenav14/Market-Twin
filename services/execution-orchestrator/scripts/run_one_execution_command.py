"""Consume and execute one MarketTwin run command."""

import asyncio
import os

from markettwin_database import (
    create_database_engine,
    create_session_factory,
)
from markettwin_database.models.testing import TestRun
from markettwin_execution_orchestrator.workflow.run_executor import (
    execute_markettwin_run,
)
from markettwin_execution_orchestrator.workflow.run_request import (
    build_run_request,
)
from markettwin_execution_orchestrator.workflow.run_request_handler import (
    EXECUTION_CONSUMER_NAME,
    accept_run_requested,
)
from markettwin_shared.messaging import (
    EXECUTION_COMMANDS_TOPIC,
    EventEnvelope,
    KafkaConsumer,
    load_kafka_consumer_settings,
)


def database_url() -> str:
    """Build the async PostgreSQL URL."""

    return (
        "postgresql+asyncpg://"
        f"{os.environ['POSTGRES_USER']}:"
        f"{os.environ['POSTGRES_PASSWORD']}@"
        f"{os.environ['POSTGRES_HOST']}:"
        f"{os.environ['POSTGRES_PORT']}/"
        f"{os.environ['POSTGRES_DB']}"
    )


async def main() -> None:
    """Consume and execute one command."""

    engine = create_database_engine(database_url())
    session_factory = create_session_factory(engine)

    settings = load_kafka_consumer_settings(
        topic=EXECUTION_COMMANDS_TOPIC,
        group_id=EXECUTION_CONSUMER_NAME,
        client_id="markettwin-execution-worker",
    )

    consumer = KafkaConsumer(settings)

    try:
        await consumer.start()

        print("Execution worker connected to Kafka.")
        print("Waiting for one execution command...")

        message = await consumer.receive()

        envelope = EventEnvelope.from_json(
            message.value.decode("utf-8")
        )

        async with session_factory() as session:
            accepted = await accept_run_requested(
                envelope=envelope,
                message=message,
                session=session,
            )

            if accepted is None:
                print(
                    f"Event {envelope.event_id} "
                    "was already accepted."
                )
                await consumer.commit()
                return

            print(
                f"Accepted TestRun: "
                f"{accepted.test_run_id}"
            )

            # The Kafka command is now durably represented by:
            #
            # TestRun.status == "planning"
            # + ProcessedMessage row
            #
            # so acknowledge the transport command.
            
            await consumer.commit()
            
            await consumer.stop()
            
            print("Kafka command acknowledged.")

            test_run = await session.get(
                TestRun,
                accepted.test_run_id,
            )

            if test_run is None:
                raise RuntimeError(
                    "Accepted TestRun disappeared."
                )

            request = build_run_request(test_run)

            print(
                f"Executing TestRun: {request.run_id}"
            )

            result = await execute_markettwin_run(
                request,
                session=session,
            )

            print("MarketTwin execution finished.")
            print(
                f"Journeys: {len(result.journeys)}"
            )
            print(
                f"Completed: {result.completed_count}"
            )
            print(
                "Failed/non-completed: "
                f"{result.failed_count}"
            )

    finally:
        await consumer.stop()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())