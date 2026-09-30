"""Persistence for idempotent Kafka message processing."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_database.models import ProcessedMessage


class ProcessedMessageRepository:
    """Track messages successfully handled by a consumer."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def is_processed(
        self,
        *,
        consumer_name: str,
        message_id: str,
    ) -> bool:
        """Return whether this consumer already handled the message."""

        statement = (
            select(ProcessedMessage.message_id)
            .where(
                ProcessedMessage.consumer_name
                == consumer_name,
                ProcessedMessage.message_id
                == message_id,
            )
            .limit(1)
        )

        result = await self._session.execute(
            statement
        )

        return result.scalar_one_or_none() is not None

    async def mark_processed(
        self,
        *,
        consumer_name: str,
        message_id: str,
        topic: str,
        partition: int | None,
        kafka_offset: int | None,
    ) -> bool:
        """Record successful handling unless already recorded."""

        statement = (
            insert(ProcessedMessage)
            .values(
                consumer_name=consumer_name,
                message_id=message_id,
                topic=topic,
                partition=partition,
                kafka_offset=kafka_offset,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    ProcessedMessage.consumer_name,
                    ProcessedMessage.message_id,
                ]
            )
            .returning(
                ProcessedMessage.message_id
            )
        )

        result = await self._session.execute(
            statement
        )

        return result.scalar_one_or_none() is not None