"""Tests for durable outbox publication."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from markettwin_control_api.services import (
    outbox_relay as relay_module,
)
from markettwin_control_api.services.outbox_relay import (
    OutboxRelay,
)
from markettwin_shared.messaging import KafkaProducer
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)


class AsyncContext:
    """Minimal async context manager."""

    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> bool:
        return False


class FakeSession:
    """Minimal session required by OutboxRelay."""

    def begin(self) -> AsyncContext:
        return AsyncContext(None)


class FakeSessionFactory:
    """Return one fake database session."""

    def __call__(self) -> AsyncContext:
        return AsyncContext(FakeSession())


class FakeOutboxRepository:
    """Track relay persistence operations."""

    def __init__(
        self,
        event: object,
    ) -> None:
        self.event = event
        self.published: list[object] = []
        self.failures: list[tuple[object, str]] = []

    async def claim_next_pending(
        self,
    ) -> object:
        return self.event

    async def mark_published(
        self,
        event: object,
    ) -> None:
        self.published.append(event)

    async def record_failure(
        self,
        event: object,
        *,
        error: str,
    ) -> None:
        self.failures.append(
            (event, error)
        )


@pytest.mark.asyncio
async def test_outbox_relay_publishes_and_marks_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful Kafka publication marks the event published."""

    event = SimpleNamespace(
        topic="markettwin.execution.commands",
        message_key="run-123",
        payload={
            "event_type": "run.requested",
            "payload": {
                "test_run_id": "run-123",
            },
        },
    )

    repository = FakeOutboxRepository(event)

    def repository_factory(
        session: object,
    ) -> FakeOutboxRepository:
        return repository

    monkeypatch.setattr(
        relay_module,
        "OutboxRepository",
        repository_factory,
    )

    producer_mock = AsyncMock()

    relay = OutboxRelay(
        session_factory=cast(
            async_sessionmaker[AsyncSession],
            FakeSessionFactory(),
        ),
        producer=cast(
            KafkaProducer,
            producer_mock,
        ),
    )

    result = await relay.publish_next()

    assert result is True

    producer_mock.publish.assert_awaited_once_with(
        topic="markettwin.execution.commands",
        key=b"run-123",
        value=(
            b'{"event_type":"run.requested",'
            b'"payload":{"test_run_id":"run-123"}}'
        ),
    )

    assert repository.published == [event]
    assert repository.failures == []


@pytest.mark.asyncio
async def test_outbox_relay_records_kafka_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kafka failure leaves the outbox event retryable."""

    event = SimpleNamespace(
        topic="markettwin.execution.commands",
        message_key="run-123",
        payload={
            "event_type": "run.requested",
        },
    )

    repository = FakeOutboxRepository(event)

    def repository_factory(
        session: object,
    ) -> FakeOutboxRepository:
        return repository

    monkeypatch.setattr(
        relay_module,
        "OutboxRepository",
        repository_factory,
    )

    producer_mock = AsyncMock()
    producer_mock.publish.side_effect = RuntimeError(
        "Kafka unavailable"
    )

    relay = OutboxRelay(
        session_factory=cast(
            async_sessionmaker[AsyncSession],
            FakeSessionFactory(),
        ),
        producer=cast(
            KafkaProducer,
            producer_mock,
        ),
    )

    result = await relay.publish_next()

    assert result is False

    assert repository.published == []

    assert repository.failures == [
        (
            event,
            "RuntimeError: Kafka unavailable",
        )
    ]