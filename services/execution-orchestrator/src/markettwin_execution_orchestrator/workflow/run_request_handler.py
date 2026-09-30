"""Durable handling of run.requested commands."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from markettwin_database.models.testing import TestRun
from markettwin_database.repositories import (
    ProcessedMessageRepository,
)
from markettwin_shared.messaging import (
    RUN_REQUESTED_EVENT_TYPE,
    RUN_REQUESTED_EVENT_VERSION,
    EventEnvelope,
    KafkaMessage,
)
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.persistence import (
    RunStateRepository,
)

EXECUTION_CONSUMER_NAME = "markettwin-execution-worker"


@dataclass(frozen=True, slots=True)
class AcceptedRunRequest:
    """A run durably accepted for execution."""

    test_run_id: UUID


async def accept_run_requested(
    *,
    envelope: EventEnvelope,
    message: KafkaMessage,
    session: AsyncSession,
) -> AcceptedRunRequest | None:
    """Atomically accept one run.requested command.

    Returns None when this consumer already handled the event.
    """

    if envelope.event_type != RUN_REQUESTED_EVENT_TYPE:
        raise ValueError(
            f'Unsupported event type "{envelope.event_type}".'
        )

    if envelope.event_version != RUN_REQUESTED_EVENT_VERSION:
        raise ValueError(
            "Unsupported run.requested event version."
        )

    raw_test_run_id = envelope.payload.get(
        "test_run_id"
    )

    if not isinstance(raw_test_run_id, str):
        raise ValueError(
            "run.requested payload must contain "
            "a string test_run_id."
        )

    try:
        test_run_id = UUID(raw_test_run_id)
    except ValueError as error:
        raise ValueError(
            "run.requested test_run_id must be a UUID."
        ) from error

    processed_repository = (
        ProcessedMessageRepository(session)
    )
    run_repository = RunStateRepository(session)

    async with session.begin():
        already_processed = (
            await processed_repository.is_processed(
                consumer_name=EXECUTION_CONSUMER_NAME,
                message_id=str(envelope.event_id),
            )
        )

        if already_processed:
            return None

        test_run = await session.get(
            TestRun,
            test_run_id,
        )

        if test_run is None:
            raise ValueError(
                f'TestRun "{test_run_id}" not found.'
            )

        if test_run.workspace_id != envelope.workspace_id:
            raise ValueError(
                "run.requested workspace does not match "
                "the persisted TestRun."
            )

        claimed = (
            await run_repository.claim_queued_for_planning(
                test_run_id=test_run_id,
            )
        )

        if not claimed:
            raise RuntimeError(
                f'TestRun "{test_run_id}" could not be '
                "claimed from queued status."
            )

        recorded = (
            await processed_repository.mark_processed(
                consumer_name=EXECUTION_CONSUMER_NAME,
                message_id=str(envelope.event_id),
                topic=message.topic,
                partition=message.partition,
                kafka_offset=message.offset,
            )
        )

        if not recorded:
            raise RuntimeError(
                "Processed message record could not "
                "be created."
            )

    return AcceptedRunRequest(
        test_run_id=test_run_id,
    )