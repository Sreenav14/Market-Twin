"""Transactional dispatch of MarketTwin TestRuns."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from markettwin_database.repositories import (
    OutboxRepository,
)
from markettwin_shared.messaging import (
    COMMANDS_TOPIC,
    RunRequestedMessage,
)

from markettwin_control_api.persistence.repositories import (
    TestRunRecord,
    TestRunRepository,
)


class RunNotQueueableError(RuntimeError):
    """The TestRun could not transition from draft to queued."""


class RunDispatchService:
    """Create the durable intent to execute one TestRun."""

    def __init__(
        self,
        *,
        test_run_repository: TestRunRepository,
        outbox_repository: OutboxRepository,
    ) -> None:
        self._test_runs = test_run_repository
        self._outbox = outbox_repository

    async def queue(
        self,
        *,
        test_run_id: UUID,
    ) -> TestRunRecord:
        """Queue one draft run and create its outbox message."""

        queued_run = (
            await self._test_runs.queue_if_draft(
                test_run_id=test_run_id,
            )
        )

        if queued_run is None:
            raise RunNotQueueableError(
                "TestRun is not in draft state."
            )

        message = RunRequestedMessage(
            event_id=uuid4(),
            test_run_id=queued_run.test_run_id,
            workspace_id=queued_run.workspace_id,
            occurred_at=datetime.now(UTC),
        )

        envelope = message.to_envelope()

        await self._outbox.add(
            aggregate_type="test_run",
            aggregate_id=queued_run.test_run_id,
            event_type=envelope.event_type,
            topic=COMMANDS_TOPIC,
            message_key=str(
                queued_run.test_run_id
            ),
            payload=envelope.to_dict(),
        )

        return queued_run