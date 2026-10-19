"""Poison messages must remain recoverable without blocking later deliveries."""

import os
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from markettwin_control_api.config import get_settings
from markettwin_database.models import OutboxEvent
from markettwin_database.repositories.outbox_repository import OutboxRepository
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.schema import CreateSchema


@pytest.mark.asyncio
async def test_retry_backoff_quarantine_and_operator_recovery() -> None:
    session = AsyncMock()
    repository = OutboxRepository(session)
    event = OutboxEvent(
        aggregate_type="run",
        aggregate_id=uuid4(),
        event_type="run.requested",
        topic="commands",
        payload={},
        attempts=0,
    )
    before = datetime.now(UTC)
    await repository.record_failure(event, error="TimeoutError")
    assert event.attempts == 1
    assert event.next_attempt_at is not None
    assert event.next_attempt_at > before
    assert event.published_at is None
    for _ in range(7):
        await repository.record_failure(event, error="TimeoutError")
    assert event.attempts == 8
    assert event.quarantined_at is not None
    assert event.published_at is None
    await repository.retry_quarantined(event)
    assert event.attempts == 0
    assert event.quarantined_at is None
    assert event.next_attempt_at is None
    await repository.mark_published(event)
    with pytest.raises(ValueError, match="Published"):
        await repository.retry_quarantined(event)


@pytest.mark.asyncio
async def test_claim_excludes_delayed_and_quarantined_events() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    await OutboxRepository(session).claim_next_pending()
    query = str(session.execute.await_args.args[0])
    assert "quarantined_at IS NULL" in query
    assert "next_attempt_at <=" in query
    assert "ORDER BY integration.outbox_events.id" in query
    assert "FOR UPDATE" in query


@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_DATABASE") != "1",
    reason="Set MARKETTWIN_TEST_DATABASE=1 to verify PostgreSQL outbox claims.",
)
async def test_postgresql_skips_poison_head_and_recovers_retained_message() -> None:
    engine = create_async_engine(get_settings().database_url, connect_args={"timeout": 5})
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            try:
                schema = f"outbox_retry_test_{uuid4().hex}"
                await connection.execute(CreateSchema(schema))
                connection = await connection.execution_options(
                    schema_translate_map={"integration": schema}
                )
                table = cast(Table, OutboxEvent.__table__)
                await connection.run_sync(lambda sync: table.create(sync))
                async with AsyncSession(
                    connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
                ) as session:
                    repository = OutboxRepository(session)
                    events = [
                        await repository.add(
                            aggregate_type="run",
                            aggregate_id=uuid4(),
                            event_type="run.requested",
                            topic="commands",
                            message_key=None,
                            payload={},
                        )
                        for _ in range(3)
                    ]
                    delayed, quarantined, healthy = events
                    delayed.next_attempt_at = datetime.now(UTC) + timedelta(hours=1)
                    quarantined.quarantined_at = datetime.now(UTC)
                    await session.flush()
                    assert await repository.claim_next_pending() is healthy
                    await repository.mark_published(healthy)
                    assert await repository.claim_next_pending() is None
                    await repository.retry_quarantined(quarantined)
                    assert await repository.claim_next_pending() is quarantined
                    assert delayed.published_at is None
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()
