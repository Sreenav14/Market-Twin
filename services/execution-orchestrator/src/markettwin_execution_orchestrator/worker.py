"""Continuously consume and execute durable run commands."""

import asyncio
import logging
import os
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from markettwin_database import create_database_engine, create_session_factory
from markettwin_database.models.execution import (
    ActionApprovalReceipt,
    ActionApprovalRequest,
    AgentExecution,
    BrowserSession,
    ExecutionPauseRequest,
    ExecutionSuspension,
    HumanActionRequest,
    HumanControlLease,
)
from markettwin_database.models.testing import PersonaJourney, TestRun
from markettwin_shared.messaging import (
    EXECUTION_COMMANDS_TOPIC,
    EventEnvelope,
    KafkaConsumer,
    KafkaMessage,
    load_kafka_consumer_settings,
)
from markettwin_shared.run_failure import failure_details, failure_event_payload, failure_site
from sqlalchemy import select, update
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from markettwin_execution_orchestrator.browser.owner_registry import browser_owner_registry
from markettwin_execution_orchestrator.browser.owner_service import HITLWorkerService
from markettwin_execution_orchestrator.persistence import RunStateRepository
from markettwin_execution_orchestrator.persistence.run_event_repository import RunEventRepository
from markettwin_execution_orchestrator.temp_failure_log import (
    bind_temp_run,
    install_temp_log_handler,
    record_temp_failure,
    record_temp_note,
    reset_temp_run,
    temp_log_path,
)
from markettwin_execution_orchestrator.workflow.run_executor import execute_markettwin_run
from markettwin_execution_orchestrator.workflow.run_request import build_run_request
from markettwin_execution_orchestrator.workflow.run_request_handler import (
    EXECUTION_CONSUMER_NAME,
    MissingRunRequestError,
    accept_run_requested,
)

logger = logging.getLogger(__name__)
EXECUTION_MAX_POLL_INTERVAL_MS = 86_400_000


async def abandon_run_handoffs(session: AsyncSession, *, test_run_id: UUID) -> None:
    """Fence lost live contexts and preserve uncertain effects; never replay them."""
    executions = select(AgentExecution.id).join(
        PersonaJourney, PersonaJourney.id == AgentExecution.journey_id
    ).where(PersonaJourney.test_run_id == test_run_id)
    requests = select(HumanActionRequest.id).where(
        HumanActionRequest.execution_id.in_(executions)
    )
    approvals = select(ActionApprovalRequest.id).where(
        ActionApprovalRequest.test_run_id == test_run_id
    )
    await session.execute(update(ActionApprovalReceipt).where(
        ActionApprovalReceipt.approval_id.in_(approvals),
        ActionApprovalReceipt.dispatch_state == "claimed",
    ).values(dispatch_state="uncertain"))
    await session.execute(update(ActionApprovalRequest).where(
        ActionApprovalRequest.test_run_id == test_run_id,
        ActionApprovalRequest.status.in_(("pending", "approved")),
    ).values(status="cancelled"))
    await session.execute(update(HumanControlLease).where(
        HumanControlLease.request_id.in_(requests),
        HumanControlLease.released_at.is_(None),
    ).values(released_at=datetime.now(UTC)))
    await session.execute(update(HumanActionRequest).where(
        HumanActionRequest.execution_id.in_(executions),
        HumanActionRequest.status.in_(("pending", "leased")),
    ).values(status="cancelled"))
    await session.execute(update(ExecutionSuspension).where(
        ExecutionSuspension.test_run_id == test_run_id,
        ExecutionSuspension.status.in_(("waiting", "ready")),
    ).values(status="abandoned"))
    await session.execute(update(ExecutionPauseRequest).where(
        ExecutionPauseRequest.test_run_id == test_run_id,
        ExecutionPauseRequest.status.in_(("requested", "paused", "resume_requested")),
    ).values(status="unavailable", completed_at=datetime.now(UTC)))
    await session.execute(update(BrowserSession).where(
        BrowserSession.execution_id.in_(executions),
        BrowserSession.state == "open",
    ).values(state="failed", control_mode="none",
             control_generation=BrowserSession.control_generation + 1))


async def process_command(
    message: KafkaMessage,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Execute an accepted run, or finalize an interrupted delivery as failed."""
    envelope = EventEnvelope.from_json(message.value.decode("utf-8"))
    async with session_factory() as session:
        try:
            accepted = await accept_run_requested(
                envelope=envelope,
                message=message,
                session=session,
            )
        except MissingRunRequestError as error:
            # A deleted run cannot be executed. Acknowledge only this delivery;
            # database/transport failures still escape and remain retryable.
            logger.warning(
                "Discarding stale run.requested event %s for missing TestRun %s",
                envelope.event_id, error.test_run_id,
            )
            return
        if accepted is None:
            # In V1 only one worker owns execution. Without leases, this branch
            # must not be used to recover deliveries across concurrent workers.
            # Do not replay potentially state-changing browser actions.
            run = await session.get(TestRun, UUID(str(envelope.payload["test_run_id"])))
            if run is not None and run.status in {"planning", "running", "awaiting_human"}:
                await abandon_run_handoffs(session, test_run_id=run.id)
                await RunStateRepository(session).mark_failed(test_run_id=run.id)
                await RunEventRepository(session).create(
                    test_run_id=run.id, event_type="run.failed",
                    payload={**failure_details("interrupted")}, journey_id=None, execution_id=None,
                )
                await session.commit()
                logger.warning("Interrupted run %s marked failed", run.id)
            return

        run = await session.get(TestRun, accepted.test_run_id)
        if run is None:
            raise RuntimeError("Accepted TestRun disappeared.")
        run_id = accepted.test_run_id
        run_token = bind_temp_run(run_id)
        try:
            request = build_run_request(run)
            logger.info("Executing TestRun %s", run_id)
            record_temp_note(stage="start", detail=f"Executing TestRun {run_id}")
            await execute_markettwin_run(request, session=session)
            logger.info("Completed TestRun %s", run_id)
            record_temp_note(stage="completed", detail=f"Completed TestRun {run_id}")
        except (Exception, asyncio.CancelledError) as error:
            record_temp_failure(stage="run", error=error)
            await session.rollback()
            run = await session.get(TestRun, accepted.test_run_id)
            if run is not None:
                await abandon_run_handoffs(session, test_run_id=run.id)
            if run is not None and run.status in {
                "planning", "queued", "running", "awaiting_human",
            }:
                await RunStateRepository(session).mark_failed(test_run_id=run.id)
            if run is not None:
                payload: dict[str, object] = {**failure_event_payload(error)}
                await RunEventRepository(session).create(
                    test_run_id=run.id, event_type="run.failed",
                    payload=payload,
                    journey_id=None, execution_id=None,
                )
                await session.commit()
            else:
                payload = {**failure_event_payload(error)}
            logger.error(
                "Execution failed for TestRun %s (%s) at %s: %s",
                accepted.test_run_id,
                type(error).__name__,
                failure_site(error),
                payload.get("reason", "detail omitted"),
            )
            if isinstance(error, asyncio.CancelledError):
                raise
        finally:
            reset_temp_run(run_token)


async def run_worker(
    consumer: KafkaConsumer,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    retry_delay_seconds: float = 5.0,
    hitl_service: HITLWorkerService | None = None,
) -> None:
    """Retry transport failures; commit only after a run reaches a terminal state.

    Human waits remain inside process_command: this single consumer cannot receive
    another run until the current run resumes or terminates. The viewer listener
    remains responsive on the same event loop. Do not add parallel consumers as a
    workaround without execution-owner leases and coordinated recovery.
    """
    try:
        if hitl_service is not None:
            await hitl_service.start(
                host=os.environ.get("MARKETTWIN_HITL_VIEWER_BIND_HOST", "127.0.0.1"),
                port=int(os.environ.get("MARKETTWIN_HITL_VIEWER_BIND_PORT", "8020")),
                cert_file=os.environ.get("MARKETTWIN_HITL_VIEWER_TLS_CERT"),
                key_file=os.environ.get("MARKETTWIN_HITL_VIEWER_TLS_KEY"),
            )
        while True:
            try:
                await consumer.start()
                logger.info("Execution worker connected; waiting for commands")
                while True:
                    message = await consumer.receive()
                    await process_command(message, session_factory)
                    await consumer.commit()
            except Exception as error:
                record_temp_failure(stage="worker-iteration", error=error)
                logger.exception("Execution worker iteration failed; reconnecting")
                await consumer.stop()
                await asyncio.sleep(retry_delay_seconds)
    finally:
        await consumer.stop()
        if hitl_service is not None:
            await hitl_service.stop()


def build_hitl_worker_service(
    session_factory: async_sessionmaker[AsyncSession],
) -> HITLWorkerService | None:
    """Enable worker takeover only with a complete internal and viewer config."""

    names = (
        "MARKETTWIN_HITL_INTERNAL_SECRET",
        "MARKETTWIN_HITL_VIEWER_ORIGINS",
        "MARKETTWIN_HITL_VIEWER_URL",
    )
    present = [bool(os.environ.get(name)) for name in names]
    if not any(present):
        return None
    if not all(present):
        raise RuntimeError("HITL worker configuration is incomplete.")
    viewer_url = os.environ["MARKETTWIN_HITL_VIEWER_URL"]
    allow_local_ws = (
        viewer_url.startswith("ws://")
        and os.environ.get("MARKETTWIN_ENV", os.environ.get("APP_ENV", "")).casefold()
        in {"development", "local"}
        and os.environ.get("MARKETTWIN_HITL_VIEWER_BIND_HOST", "127.0.0.1")
        in {"127.0.0.1", "localhost", "::1"}
    )
    origins = frozenset(
        origin.strip()
        for origin in os.environ["MARKETTWIN_HITL_VIEWER_ORIGINS"].split(",")
        if origin.strip()
    )
    return HITLWorkerService(
        session_factory=session_factory,
        registry=browser_owner_registry,
        internal_secret=os.environ["MARKETTWIN_HITL_INTERNAL_SECRET"],
        allowed_origins=origins,
        viewer_url=viewer_url,
        allow_local_ws=allow_local_ws,
    )


async def main() -> None:
    """Run the worker until stopped by its process supervisor."""
    logging.basicConfig(level=logging.INFO)
    install_temp_log_handler()
    logger.info("Temporary execution log: %s", temp_log_path())
    engine = create_database_engine(
        URL.create(
            "postgresql+asyncpg",
            username=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            host=os.environ["POSTGRES_HOST"],
            port=int(os.environ["POSTGRES_PORT"]),
            database=os.environ["POSTGRES_DB"],
        ).render_as_string(hide_password=False)
    )
    settings = replace(
        load_kafka_consumer_settings(
            topic=EXECUTION_COMMANDS_TOPIC,
            group_id=EXECUTION_CONSUMER_NAME,
            client_id=EXECUTION_CONSUMER_NAME,
        ),
        max_poll_interval_ms=EXECUTION_MAX_POLL_INTERVAL_MS,
    )
    try:
        session_factory = create_session_factory(engine)
        hitl_service = build_hitl_worker_service(session_factory)
        await run_worker(
            KafkaConsumer(settings),
            session_factory,
            hitl_service=hitl_service,
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
