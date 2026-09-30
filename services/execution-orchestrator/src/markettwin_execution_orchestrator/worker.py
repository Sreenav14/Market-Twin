"""Continuously consume and execute durable run commands."""

import asyncio
import logging
import os
from dataclasses import replace
from uuid import UUID

from markettwin_database import create_database_engine, create_session_factory
from markettwin_database.models.testing import TestRun
from markettwin_shared.messaging import (
    EXECUTION_COMMANDS_TOPIC,
    EventEnvelope,
    KafkaConsumer,
    KafkaMessage,
    load_kafka_consumer_settings,
)
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from markettwin_execution_orchestrator.persistence import RunStateRepository
from markettwin_execution_orchestrator.workflow.run_executor import execute_markettwin_run
from markettwin_execution_orchestrator.workflow.run_request import build_run_request
from markettwin_execution_orchestrator.workflow.run_request_handler import (
    EXECUTION_CONSUMER_NAME,
    accept_run_requested,
)

logger = logging.getLogger(__name__)


async def process_command(
    message: KafkaMessage,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Execute an accepted run, or finalize an interrupted delivery as failed."""
    envelope = EventEnvelope.from_json(message.value.decode("utf-8"))
    async with session_factory() as session:
        accepted = await accept_run_requested(
            envelope=envelope,
            message=message,
            session=session,
        )
        if accepted is None:
            # A committed acceptance without a terminal state means the prior
            # worker stopped during execution. Do not replay browser actions.
            run = await session.get(TestRun, UUID(str(envelope.payload["test_run_id"])))
            if run is not None and run.status in {"planning", "running"}:
                await RunStateRepository(session).mark_failed(test_run_id=run.id)
                await session.commit()
                logger.warning("Interrupted run %s marked failed", run.id)
            return

        run = await session.get(TestRun, accepted.test_run_id)
        if run is None:
            raise RuntimeError("Accepted TestRun disappeared.")
        try:
            request = build_run_request(run)
            logger.info("Executing TestRun %s", run.id)
            await execute_markettwin_run(request, session=session)
            logger.info("Completed TestRun %s", run.id)
        except Exception:
            await session.rollback()
            run = await session.get(TestRun, accepted.test_run_id)
            if run is not None and run.status in {"planning", "queued", "running"}:
                await RunStateRepository(session).mark_failed(test_run_id=run.id)
                await session.commit()
            logger.exception("Execution failed for TestRun %s", accepted.test_run_id)


async def run_worker(
    consumer: KafkaConsumer,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    retry_delay_seconds: float = 5.0,
) -> None:
    """Retry transport failures; commit only after a run reaches a terminal state."""
    try:
        while True:
            try:
                await consumer.start()
                logger.info("Execution worker connected; waiting for commands")
                while True:
                    message = await consumer.receive()
                    await process_command(message, session_factory)
                    await consumer.commit()
            except Exception:
                logger.exception("Execution worker iteration failed; reconnecting")
                await consumer.stop()
                await asyncio.sleep(retry_delay_seconds)
    finally:
        await consumer.stop()


async def main() -> None:
    """Run the worker until stopped by its process supervisor."""
    logging.basicConfig(level=logging.INFO)
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
        max_poll_interval_ms=86_400_000,
    )
    try:
        await run_worker(KafkaConsumer(settings), create_session_factory(engine))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
