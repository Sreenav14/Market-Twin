"""Publish durable Control API outbox events to Kafka."""

import json

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


class OutboxRelay:
    """Move persisted outbox events into Kafka."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        producer: KafkaProducer,
    ) -> None:
        self._session_factory = session_factory
        self._producer = producer

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

                    await self._producer.publish(
                        topic=event.topic,
                        key=key,
                        value=value,
                    )

                except Exception as error:
                    await repository.record_failure(
                        event,
                        error=(
                            f"{type(error).__name__}: "
                            f"{error}"
                        ),
                    )

                    return False

                await repository.mark_published(event)

                return True