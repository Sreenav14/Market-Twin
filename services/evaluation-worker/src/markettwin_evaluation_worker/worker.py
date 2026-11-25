"""Evaluate completed tests independently of Kafka execution and browser lifetimes."""

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

from markettwin_database import create_database_engine, create_session_factory
from markettwin_database.models import Report, TestRun
from markettwin_database.worker_heartbeat import run_worker_heartbeat
from opentelemetry import trace
from sqlalchemy import or_, select, text, update
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from markettwin_evaluation_worker.errors import InvalidEvaluationInput

from markettwin_evaluation_worker.workflow import (
    EvaluationWorkflowResult,
    evaluate_and_generate_report,
)
from markettwin_evaluation_worker.graph_audit import (
    AUDIT_INTERVAL_SECONDS,
    run_scheduled_audit,
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
                    Report.status == "completed",
                ))
                if report_id is not None:
                    return None
                now = datetime.now(UTC)
                if run.evaluation_quarantined_at is not None or (
                    run.evaluation_next_attempt_at is not None
                    and run.evaluation_next_attempt_at > now
                ):
                    return None
                attempts = run.evaluation_attempts + 1
                budget = (getattr(run, "configuration_snapshot", None) or {}).get(
                    "slop_desktop_budget", {},
                )
                reserve = budget.get("finalization_reserve_seconds") if isinstance(budget, dict) else None
                timeout = reserve if isinstance(reserve, (int, float)) and reserve > 0 else None
                try:
                    async with asyncio.timeout(timeout):
                        result = await evaluate_and_generate_report(
                            test_run_id=test_run_id, session=session
                        )
                except Exception as error:
                    now = datetime.now(UTC)
                    if isinstance(error, InvalidEvaluationInput):
                        code = error.code
                    elif isinstance(error, TimeoutError):
                        code = "evaluation_timeout"
                    elif isinstance(error, OperationalError):
                        code = "evaluation_database_unavailable"
                    else:
                        code = "evaluation_failed"
                    quarantined = isinstance(error, InvalidEvaluationInput) or attempts >= 5
                    await session.rollback()
                    await session.execute(update(TestRun).where(TestRun.id == test_run_id).values(
                        evaluation_attempts=attempts,
                        evaluation_last_error=code,
                        evaluation_next_attempt_at=None if quarantined else now + timedelta(
                            seconds=min(3600, 30 * 2 ** min(attempts - 1, 7))
                        ),
                        evaluation_quarantined_at=now if quarantined else None,
                    ))
                    await session.commit()
                    raise
                await session.execute(update(TestRun).where(TestRun.id == test_run_id).values(
                    evaluation_attempts=0, evaluation_last_error=None,
                    evaluation_next_attempt_at=None, evaluation_quarantined_at=None,
                ))
                await session.commit()
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
    heartbeat = asyncio.create_task(run_worker_heartbeat(
        create_session_factory(engine), "evaluation", lambda: {"connected": True},
    ))
    try:
        await _run_worker(engine)
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)


async def _run_worker(engine: AsyncEngine) -> None:
    """Discover unfinished evaluation durably; retry failures without replaying executions."""
    concurrency = int(os.getenv("MARKETTWIN_EVALUATION_CONCURRENCY", "2"))
    if not 1 <= concurrency <= 4:
        raise ValueError("Evaluation concurrency must be between 1 and 4.")
    async def process_pending(test_run_id: UUID) -> None:
        try:
            if await process_run(engine, test_run_id) is None:
                # Another evaluator can hold the advisory lock. Avoid spinning
                # on the same oldest candidate while that evaluator finishes.
                await asyncio.sleep(1)
        except InvalidEvaluationInput as error:
            logger.warning("Evaluation input rejected for TestRun %s: %s", test_run_id, error.code)
        except Exception:
            logger.exception("Evaluation attempt failed for TestRun %s", test_run_id)

    active: dict[UUID, asyncio.Task[None]] = {}
    async with asyncio.TaskGroup() as group:
        group.create_task(_run_graph_audit_worker(engine))
        while True:
            active = {run_id: task for run_id, task in active.items() if not task.done()}
            available = concurrency - len(active)
            if available:
                try:
                    async with AsyncSession(engine) as session:
                        pending = (await session.scalars(select(TestRun.id).where(
                            TestRun.status == "completed",
                            TestRun.id.not_in(tuple(active)),
                            TestRun.evaluation_quarantined_at.is_(None),
                            or_(TestRun.evaluation_next_attempt_at.is_(None),
                                TestRun.evaluation_next_attempt_at <= datetime.now(UTC)),
                            ~select(Report.id).where(
                                Report.test_run_id == TestRun.id, Report.version == 1,
                                Report.status == "completed",
                            ).exists(),
                        ).order_by(TestRun.completed_at, TestRun.id).limit(available))).all()
                    for test_run_id in pending:
                        active[test_run_id] = group.create_task(process_pending(test_run_id))
                except Exception:
                    logger.exception("Could not discover completed tests for evaluation")
            if active:
                await asyncio.wait(active.values(), timeout=5, return_when=asyncio.FIRST_COMPLETED)
            else:
                await asyncio.sleep(5)


async def _run_graph_audit_worker(engine: AsyncEngine) -> None:
    session_factory = create_session_factory(engine)
    while True:
        try:
            await run_scheduled_audit(session_factory)
        except Exception:
            logger.exception("Graph audit failed; will retry next interval")
        await asyncio.sleep(AUDIT_INTERVAL_SECONDS)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    database_url = URL.create(
        "postgresql+asyncpg", username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"], host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]), database=os.environ["POSTGRES_DB"],
    ).render_as_string(hide_password=False)
    engine = create_database_engine(database_url)
    logger.info("Evaluation worker connected; waiting for completed tests")
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
