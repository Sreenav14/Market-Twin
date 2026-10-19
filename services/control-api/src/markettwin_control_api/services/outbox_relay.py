"""Publish durable Control API outbox events to Kafka."""

import asyncio
import json
import logging

from markettwin_database.repositories import (
    OutboxRepository,
)
from markettwin_shared.messaging import (
    KafkaProducer,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

logger = logging.getLogger(__name__)


class OutboxRelay:
    """Move persisted outbox events into Kafka."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        producer: KafkaProducer,
        publish_timeout_seconds: float = 30.0,
    ) -> None:
        self._session_factory = session_factory
        self._producer = producer
        self._publish_timeout_seconds = publish_timeout_seconds

    async def publish_next(self) -> bool:
        """Publish one pending event if one exists."""

        async with self._session_factory() as session:
            async with session.begin():
                repository = OutboxRepository(session)

                event = await repository.claim_next_pending()

                if event is None:
                    return False

                try:
                    value = json.dumps(
                        event.payload,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8")

                    key = (
                        event.message_key.encode("utf-8")
                        if event.message_key is not None
                        else None
                    )

                    # Keep the transaction until acknowledgement; a timeout is
                    # ambiguous and may produce a duplicate on retry, never loss.
                    async with asyncio.timeout(self._publish_timeout_seconds):
                        await self._producer.publish(
                            topic=event.topic,
                            key=key,
                            value=value,
                        )

                except Exception as error:
                    await repository.record_failure(
                        event,
                        error=type(error).__name__,
                    )

                    logger.warning(
                        "Outbox publication failed (%s); retry policy applied", type(error).__name__
                    )
                    return False

                await repository.mark_published(event)

                return True