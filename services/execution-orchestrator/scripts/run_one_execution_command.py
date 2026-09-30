"""Consume and execute one MarketTwin run command."""

import asyncio
import logging
import os
from dataclasses import replace

from markettwin_database import (
    create_database_engine,
    create_session_factory,
)
from markettwin_execution_orchestrator.worker import (
    EXECUTION_MAX_POLL_INTERVAL_MS,
    process_command,
)
from markettwin_execution_orchestrator.workflow.run_request_handler import (
    EXECUTION_CONSUMER_NAME,
)
from markettwin_shared.messaging import (
    EXECUTION_COMMANDS_TOPIC,
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

    logging.basicConfig(level=logging.INFO)
    engine = create_database_engine(database_url())
    session_factory = create_session_factory(engine)

    settings = replace(
        load_kafka_consumer_settings(
            topic=EXECUTION_COMMANDS_TOPIC,
            group_id=EXECUTION_CONSUMER_NAME,
            client_id=EXECUTION_CONSUMER_NAME,
        ),
        max_poll_interval_ms=EXECUTION_MAX_POLL_INTERVAL_MS,
    )

    consumer = KafkaConsumer(settings)

    try:
        await consumer.start()

        print("Execution worker connected to Kafka.")
        print("Waiting for one execution command...")

        message = await consumer.receive()

        await process_command(message, session_factory)
        await consumer.commit()
        print("Kafka command processed and acknowledged.")

    finally:
        await consumer.stop()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
