"""Persistence for durable transactional-outbox messages."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
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
    
    
    async def claim_next_pending(
    self,
    ) -> OutboxEvent | None:
        """Lock the next unpublished event for this transaction."""

        statement = (
            select(OutboxEvent)
            .where(
                OutboxEvent.published_at.is_(None),
                OutboxEvent.quarantined_at.is_(None),
                or_(OutboxEvent.next_attempt_at.is_(None),
                    OutboxEvent.next_attempt_at <= datetime.now(UTC)),
            )
            .order_by(OutboxEvent.id)
            .with_for_update(
                skip_locked=True
            )
            .limit(1)
        )

        result = await self._session.execute(
            statement
        )

        return result.scalar_one_or_none()


    async def mark_published(
        self,
        event: OutboxEvent,
    ) -> None:
        """Record successful publication."""

        event.published_at = datetime.now(UTC)
        event.last_error = None

        await self._session.flush()


    async def record_failure(
        self,
        event: OutboxEvent,
        *,
        error: str,
    ) -> None:
        """Record one failed publication attempt."""

        event.attempts += 1
        # Store a safe classification, never transport exception payloads/credentials.
        event.last_error = error
        now = datetime.now(UTC)
        event.next_attempt_at = now + timedelta(
            seconds=min(3600, 5 * 2 ** min(event.attempts - 1, 10))
        )
        if event.attempts >= 8:
            event.quarantined_at = now

        await self._session.flush()

    async def retry_quarantined(self, event: OutboxEvent) -> None:
        """Operator recovery after diagnosing a retained, unpublished event.

        Caller must hold the row lock and commit this change. Publication can be
        duplicated after ambiguous broker timeouts, so consumers must deduplicate.
        """
        if event.published_at is not None:
            raise ValueError("Published events cannot be retried.")
        event.attempts = 0
        event.next_attempt_at = None
        event.quarantined_at = None
        event.last_error = None
        await self._session.flush()
