"""Durable handling of run.requested commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
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
EXECUTION_REJECTION_CONSUMER_NAME = f"{EXECUTION_CONSUMER_NAME}:rejected"


class MissingRunRequestError(ValueError):
    """A successfully read command refers to a run that no longer exists."""

    def __init__(self, test_run_id: UUID) -> None:
        self.test_run_id = test_run_id
        super().__init__(f'TestRun "{test_run_id}" not found.')


@dataclass(frozen=True, slots=True)
class AcceptedRunRequest:
    """A run durably accepted for execution."""

    test_run_id: UUID


@dataclass(frozen=True, slots=True)
class RejectedRunRequest:
    """A permanently rejected command with a committed handling receipt."""

    test_run_id: UUID
    reason: Literal["workspace_mismatch", "terminal_run", "already_rejected"]


async def accept_run_requested(
    *,
    envelope: EventEnvelope,
    message: KafkaMessage,
    session: AsyncSession,
) -> AcceptedRunRequest | RejectedRunRequest | None:
    """Atomically accept one run.requested command.

    Returns None for a previously accepted delivery. Permanent rejections use
    separate receipts and return a typed result only after their transaction commits.

    Receipt identity currently binds consumer/event ID, not the aggregate payload.
    Tenant checks reject altered cross-workspace replays; binding an accepted event
    to one specific run within a workspace requires additional durable metadata.
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

    rejection: RejectedRunRequest | None = None
    async with session.begin():
        # A rejected replay must never enter accepted-run interruption recovery.
        if await processed_repository.is_processed(
            consumer_name=EXECUTION_REJECTION_CONSUMER_NAME,
            message_id=str(envelope.event_id),
        ):
            return RejectedRunRequest(test_run_id, "already_rejected")

        already_processed = (
            await processed_repository.is_processed(
                consumer_name=EXECUTION_CONSUMER_NAME,
                message_id=str(envelope.event_id),
            )
        )

        test_run = await session.get(
            TestRun,
            test_run_id,
        )

        if test_run is None:
            raise MissingRunRequestError(test_run_id)

        if test_run.workspace_id != envelope.workspace_id:
            rejection = RejectedRunRequest(test_run_id, "workspace_mismatch")
        elif already_processed:
            # Validate persisted tenant ownership even on an accepted receipt:
            # an altered replay must never enter interruption recovery.
            return None
        else:
            claimed = await run_repository.claim_queued_for_planning(test_run_id=test_run_id)
            if not claimed:
                # Refresh after the CAS: an identity-map value may predate a
                # concurrent cancellation/completion. Queued/active failures
                # remain retryable; never replay or finalize another owner here.
                current_run = await session.get(TestRun, test_run_id, populate_existing=True)
                if current_run is not None and current_run.status in {
                    "completed", "failed", "cancelled",
                }:
                    rejection = RejectedRunRequest(test_run_id, "terminal_run")
                else:
                    raise RuntimeError(
                        f'TestRun "{test_run_id}" could not be claimed from queued status.'
                    )

        recorded = (
            await processed_repository.mark_processed(
                consumer_name=(EXECUTION_REJECTION_CONSUMER_NAME if rejection is not None
                               else EXECUTION_CONSUMER_NAME),
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

    if rejection is not None:
        return rejection
    return AcceptedRunRequest(
        test_run_id=test_run_id,
    )
