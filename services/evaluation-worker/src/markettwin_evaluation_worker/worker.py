"""Evaluate completed tests independently of Kafka execution and browser lifetimes."""

import asyncio
import logging
import os
from uuid import UUID

from markettwin_database import create_database_engine
from markettwin_database.models import Report, TestRun
from opentelemetry import trace
from sqlalchemy import select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from markettwin_evaluation_worker.workflow import (
    EvaluationWorkflowResult,
    evaluate_and_generate_report,
)

logger = logging.getLogger(__name__)


async def process_run(engine: AsyncEngine, test_run_id: UUID) -> EvaluationWorkflowResult | None:
    """Claim one run; a completed report is the durable completion marker."""
    async with engine.connect() as connection:
        key = {"key": f"markettwin-evaluation:{test_run_id}"}
        locked = await connection.scalar(
            text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"), key
        )
        await connection.commit()
        if not locked:
            return None
        try:
            async with AsyncSession(connection, expire_on_commit=False) as session:
                run = await session.get(TestRun, test_run_id)
                if run is None or run.status != "completed":
                    return None
                report_id = await session.scalar(select(Report.id).where(
                    Report.test_run_id == test_run_id, Report.version == 1,
                ))
                if report_id is not None:
                    return None
                result = await evaluate_and_generate_report(
                    test_run_id=test_run_id, session=session
                )
                logger.info("Evaluated TestRun %s; report %s", test_run_id, result.report_id)
                return result
        finally:
            try:
                await connection.rollback()
                await connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"), key
                )
                await connection.commit()
            except BaseException:
                await connection.invalidate()
                raise


async def run_worker(engine: AsyncEngine) -> None:
    """Discover unfinished evaluation durably; retry failures without replaying executions."""
    while True:
        try:
            async with AsyncSession(engine) as session:
                pending = (await session.scalars(select(TestRun.id).where(
                    TestRun.status == "completed",
                    ~select(Report.id).where(
                        Report.test_run_id == TestRun.id, Report.version == 1,
                    ).exists(),
                ).order_by(TestRun.completed_at).limit(20))).all()
            for test_run_id in pending:
                try:
                    await process_run(engine, test_run_id)
                except Exception:
                    logger.exception("Evaluation failed for TestRun %s; will retry", test_run_id)
        except Exception:
            logger.exception("Could not discover completed tests for evaluation")
        await asyncio.sleep(5)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    database_url = URL.create(
        "postgresql+asyncpg", username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"], host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]), database=os.environ["POSTGRES_DB"],
    ).render_as_string(hide_password=False)
    engine = create_database_engine(database_url)
    try:
        await run_worker(engine)
    finally:
        await engine.dispose()
        flush = getattr(trace.get_tracer_provider(), "force_flush", None)
        if flush is not None:
            await asyncio.to_thread(flush, timeout_millis=5000)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
