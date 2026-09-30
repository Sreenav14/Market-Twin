"""Verify that MarketTwin can consume from Kafka."""

import asyncio

from markettwin_shared.messaging import (
    EXECUTION_COMMANDS_TOPIC,
    EventEnvelope,
    KafkaConsumer,
    load_kafka_consumer_settings,
)


async def main() -> None:
    """Connect to Kafka and read one execution command."""

    settings = load_kafka_consumer_settings(
        topic=EXECUTION_COMMANDS_TOPIC,

        # Diagnostic group only.
        # Do not use the future production worker group here.
        group_id="markettwin-execution-consumer-check",

        client_id="markettwin-consumer-check",
    )

    consumer = KafkaConsumer(settings)

    try:
        await consumer.start()

        print("Kafka consumer connected.")

        try:
            message = await asyncio.wait_for(
                consumer.receive(),
                timeout=15.0,
            )
        except TimeoutError:
            print("No Kafka message received within 15 seconds.")
            return

        envelope = EventEnvelope.from_json(
            message.value.decode("utf-8")
        )

        print(f"Topic: {message.topic}")
        print(f"Partition: {message.partition}")
        print(f"Offset: {message.offset}")
        print(f"Event ID: {envelope.event_id}")
        print(f"Event type: {envelope.event_type}")
        print(
            "TestRun ID: "
            f"{envelope.payload.get('test_run_id')}"
        )

        # Intentionally do NOT commit.
        # This is only a diagnostic consumer.

    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(main())