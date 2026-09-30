"""Verify that MarketTwin can connect to Kafka."""

import asyncio

from markettwin_shared.messaging import (
    KafkaProducer,
    load_kafka_producer_settings,
)


async def main() -> None:
    """Connect to Kafka and close cleanly."""

    settings = load_kafka_producer_settings()

    producer = KafkaProducer(settings)

    try:
        await producer.start()
        print("Kafka connection successful.")
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())