"""Background worker for durable outbox publication."""

import asyncio
import logging

from markettwin_shared.messaging import KafkaProducer

from markettwin_control_api.services.outbox_relay import (
    OutboxRelay,
)

logger = logging.getLogger(__name__)


async def run_outbox_relay(
    *,
    relay: OutboxRelay,
    producer: KafkaProducer,
    idle_delay_seconds: float = 1.0,
    retry_delay_seconds: float = 5.0,
) -> None:
    """Continuously publish pending outbox events."""

    try:
        while True:
            try:
                await producer.start()
                break
            except Exception:
                logger.exception(
                    "Unable to connect outbox relay to Kafka."
                )
                await asyncio.sleep(retry_delay_seconds)

        while True:
            try:
                published = await relay.publish_next()
            except Exception:
                logger.exception(
                    "Outbox relay iteration failed."
                )
                await asyncio.sleep(retry_delay_seconds)
                continue

            if not published:
                await asyncio.sleep(idle_delay_seconds)

    finally:
        await producer.stop()