"""Persistence for durable transactional-outbox messages."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_database.models import OutboxEvent


class OutboxRepository:
    """Persist messages that must later be published."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def add(
        self,
        *,
        aggregate_type: str,
        aggregate_id: UUID,
        event_type: str,
        topic: str,
        message_key: str | None,
        payload: dict[str, object],
        headers: dict[str, object] | None = None,
    ) -> OutboxEvent:
        """Add one unpublished message to the current transaction."""

        event = OutboxEvent(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            topic=topic,
            message_key=message_key,
            payload=payload,
            headers={} if headers is None else headers,
        )

        self._session.add(event)

        await self._session.flush()

        return event