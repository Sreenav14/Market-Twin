"""Continuously consume and execute durable run commands."""

import asyncio
import logging
import os
import sys
import tempfile
from hashlib import sha256
from collections import deque
from dataclasses import dataclass, replace
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
from markettwin_database.repositories import ProcessedMessageRepository
from markettwin_database.worker_heartbeat import run_worker_heartbeat
from markettwin_shared.messaging import (
    EXECUTION_COMMANDS_TOPIC,
    EventEnvelope,
    KafkaConsumer,
    KafkaMessage,
    load_kafka_consumer_settings,
)
from markettwin_shared.run_failure import failure_details, failure_event_payload, failure_site
from sqlalchemy import select, text, update
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from markettwin_execution_orchestrator.browser.owner_registry import browser_owner_registry
from markettwin_execution_orchestrator.browser.owner_service import HITLWorkerService
from markettwin_execution_orchestrator.persistence import (
    ExecutionRepository,
    RunStateRepository,
)
from markettwin_execution_orchestrator.persistence.models import RunEvent
from markettwin_execution_orchestrator.persistence.run_event_repository import RunEventRepository
from markettwin_execution_orchestrator.temp_failure_log import (
    bind_temp_run,
    record_temp_failure,
    record_temp_note,
    reset_temp_run,
)
from markettwin_execution_orchestrator.workflow.run_executor import execute_markettwin_run
from markettwin_execution_orchestrator.workflow.run_request import build_run_request
from markettwin_execution_orchestrator.workflow.run_request_handler import (
    EXECUTION_CONSUMER_NAME,
    InvalidRunRequestError,
    MissingRunRequestError,
    RejectedRunRequest,
    accept_run_requested,
)

logger = logging.getLogger(__name__)
EXECUTION_MAX_POLL_INTERVAL_MS = 86_400_000

# Stall watchdog: a healthy crawl records run events at least once per
# traversal budget (180 s per page) plus Lead review time, so 900 s without
# a single recorded event is unreachable by a healthy actively-running
# execution. Only actively-running states are eligible: parked runs
# (awaiting_human - a login handoff is legitimately idle 15-30 min by
# design), queued runs, and terminal runs are never touched.
STALL_WATCHDOG_SECONDS = 900
STALL_WATCHDOG_CHECK_SECONDS = 30
_ACTIVELY_RUNNING_STATUSES = frozenset({"planning", "running"})


class StallWatchdogError(RuntimeError):
    """An actively-running execution recorded no activity past the stall bound."""


@dataclass
class _ExecutionWatch:
    task: "asyncio.Task[None]"
    started_at: datetime
    triggered: bool = False


_EXECUTION_WATCHES: dict[UUID, _ExecutionWatch] = {}
_WATCHDOG_CANCELLED: set[UUID] = set()


def _register_execution(run_id: UUID) -> None:
    task = asyncio.current_task()
    if task is not None:
        _EXECUTION_WATCHES[run_id] = _ExecutionWatch(
            task=task, started_at=datetime.now(UTC))


def _unregister_execution(run_id: UUID) -> None:
    _EXECUTION_WATCHES.pop(run_id, None)
    _WATCHDOG_CANCELLED.discard(run_id)


async def _cancel_stalled_executions(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    stall_seconds: int = STALL_WATCHDOG_SECONDS,
) -> tuple[UUID, ...]:
    """Cancel each actively-running execution silent past the stall bound.

    Cancellation is delivered once per execution; process_command converts
    it into a StallWatchdogError so the run closes failed through the
    shared failure payload with the watchdog as the recorded site. The
    activity source is execution.run_events (occurred_at), the same record
    the worker itself writes; a run with no events yet is measured from
    its execution start.
    """
    cancelled: list[UUID] = []
    for run_id, watch in tuple(_EXECUTION_WATCHES.items()):
        if watch.triggered or watch.task.done():
            continue
        async with session_factory() as session:
            run = await session.get(TestRun, run_id)
            if run is None or run.status not in _ACTIVELY_RUNNING_STATUSES:
                continue
            latest = await session.scalar(
                select(RunEvent.occurred_at)
                .where(RunEvent.test_run_id == run_id)
                .order_by(RunEvent.occurred_at.desc())
                .limit(1)
            )
        last_activity = max(watch.started_at, latest) if latest is not None else watch.started_at
        if (now - last_activity).total_seconds() > stall_seconds:
            watch.triggered = True
            _WATCHDOG_CANCELLED.add(run_id)
            watch.task.cancel()
            cancelled.append(run_id)
            logger.error(
                "Stall watchdog cancelling TestRun %s: no recorded activity since %s",
                run_id, last_activity,
            )
    return tuple(cancelled)


async def _stall_watchdog(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    check_seconds: float = STALL_WATCHDOG_CHECK_SECONDS,
    stall_seconds: int = STALL_WATCHDOG_SECONDS,
) -> None:
    """Periodically cancel silently stalled executions; survives its own errors."""
    while True:
        await asyncio.sleep(check_seconds)
        try:
            await _cancel_stalled_executions(
                session_factory, now=datetime.now(UTC), stall_seconds=stall_seconds,
            )
        except Exception:
            logger.exception("Stall watchdog check failed; continuing")


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


async def _fail_running_agent_executions(session: AsyncSession, *, test_run_id: UUID) -> None:
    """Terminalize a dead run's still-running child executions.

    A run that is failed or abandoned without this leaves its
    AgentExecution rows "running" forever: the persona executor's own
    cleanup is the only other closer, and it cannot run when the
    failure happened outside a walk (browser creation, worker-level
    error, interruption before any browser row existed)."""
    await session.execute(update(AgentExecution).where(
        AgentExecution.journey_id.in_(select(PersonaJourney.id).where(
            PersonaJourney.test_run_id == test_run_id)),
        AgentExecution.status == "running",
    ).values(status="failed", completed_at=datetime.now(UTC), error_code="interrupted"))


async def _reject_invalid_command(
    message: KafkaMessage,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Invalid bytes need not contain an event ID. Bind the receipt to the durable
    # delivery position; never persist an unvalidated command body or credentials.
    position = f"{message.topic}:{message.partition}:{message.offset}"
    async with session_factory() as session:
        async with session.begin():
            await ProcessedMessageRepository(session).mark_processed(
                consumer_name=f"{EXECUTION_CONSUMER_NAME}:invalid",
                message_id=sha256(position.encode()).hexdigest(),
                topic=message.topic, partition=message.partition,
                kafka_offset=message.offset,
            )
    logger.warning("Rejected invalid execution command at %s", position)


async def process_command(
    message: KafkaMessage,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Execute an accepted run, or finalize an interrupted delivery as failed."""
    try:
        envelope = EventEnvelope.from_json(message.value.decode("utf-8"))
    except Exception:
        # Parsing is pure (bytes to envelope, no I/O), so any failure
        # - bad JSON, a tombstone's missing body, pathological
        # nesting - means this delivery can never become a command.
        # Dead-letter it: raising would redeliver it forever and
        # wedge every command queued behind it (DAT-5).
        await _reject_invalid_command(message, session_factory)
        return
    async with session_factory() as session:
        try:
            accepted = await accept_run_requested(
                envelope=envelope,
                message=message,
                session=session,
            )
        except InvalidRunRequestError:
            await session.rollback()
            await _reject_invalid_command(message, session_factory)
            return
        except MissingRunRequestError as error:
            # A deleted run cannot be executed. Acknowledge only this delivery;
            # database/transport failures still escape and remain retryable.
            logger.warning(
                "Discarding stale run.requested event %s for missing TestRun %s",
                envelope.event_id, error.test_run_id,
            )
            return
        if isinstance(accepted, RejectedRunRequest):
            logger.warning(
                "Rejected run.requested event %s for TestRun %s (%s)",
                envelope.event_id, accepted.test_run_id, accepted.reason,
            )
            return
        if accepted is None:
            # In V1 only one worker owns execution. Without leases, this branch
            # must not be used to recover deliveries across concurrent workers.
            # Do not replay potentially state-changing browser actions.
            run = await session.get(TestRun, UUID(str(envelope.payload["test_run_id"])))
            recoverable = (run is not None and getattr(run, "run_kind", None) == "slop"
                and run.status in {"running", "planning"}
                and bool((run.configuration_snapshot or {}).get("slop_checkpoint")))
            if (not recoverable and run is not None
                    and run.status in {"running", "planning"}):
                run_kind = getattr(run, "run_kind", None)
                snapshot = getattr(run, "configuration_snapshot", None) or {}
                if run_kind == "explore_test" and snapshot.get("discovery_frontier"):
                    # The Board and the discovery frontier are persisted;
                    # re-dispatch resumes from them (harness resume path).
                    recoverable = True
                elif run_kind in {"slop", "explore_test", "persona"}:
                    # Before a browser row exists, no page action has been dispatched.
                    browser_exists = await session.scalar(select(BrowserSession.id).where(
                        BrowserSession.test_run_id == run.id).limit(1))
                    recoverable = browser_exists is None
            if recoverable:
                from markettwin_execution_orchestrator.workflow.run_request_handler import AcceptedRunRequest
                await abandon_run_handoffs(session, test_run_id=run.id)
                await _fail_running_agent_executions(session, test_run_id=run.id)
                await session.commit()
                accepted = AcceptedRunRequest(run.id)
            elif run is not None and run.status in {"planning", "running", "awaiting_human"}:
                await abandon_run_handoffs(session, test_run_id=run.id)
                await _fail_running_agent_executions(session, test_run_id=run.id)
                await RunStateRepository(session).mark_failed(test_run_id=run.id)
                await RunEventRepository(session).create(
                    test_run_id=run.id, event_type="run.failed",
                    payload={**failure_details("interrupted")}, journey_id=None, execution_id=None,
                )
                await session.commit()
                logger.warning("Interrupted run %s marked failed", run.id)
            if not recoverable:
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
            _register_execution(run_id)
            await execute_markettwin_run(request, session=session)
            logger.info("Completed TestRun %s", run_id)
            record_temp_note(stage="completed", detail=f"Completed TestRun {run_id}")
        except (Exception, asyncio.CancelledError) as error:
            if isinstance(error, asyncio.CancelledError) and run_id in _WATCHDOG_CANCELLED:
                # The stall watchdog cancelled this execution: close it with a
                # dedicated error so the recorded failure site names this
                # watchdog raise point, not the interrupted crawl frame.
                _WATCHDOG_CANCELLED.discard(run_id)
                try:
                    raise StallWatchdogError(
                        "Execution recorded no activity within the stall watchdog bound."
                    )
                except StallWatchdogError as watchdog_error:
                    error = watchdog_error
            record_temp_failure(stage="run", error=error)
            await session.rollback()
            run = await session.get(TestRun, accepted.test_run_id)
            from markettwin_execution_orchestrator.workflow.slop_run import SlopFinalizationError

            if isinstance(error, SlopFinalizationError) and run is not None and run.status == "running":
                snapshot = run.configuration_snapshot or {}
                attempts = int(snapshot.get("slop_finalization_failures", 0)) + 1
                run.configuration_snapshot = {**snapshot, "slop_finalization_failures": attempts}
                await RunEventRepository(session).create(
                    test_run_id=run.id, event_type="slop.finalization.failed",
                    payload={"stage": error.stage, "attempt": attempts},
                    journey_id=None, execution_id=None,
                )
                if attempts < 3 and snapshot.get("slop_checkpoint"):
                    await session.commit()
                    raise
            if run is not None:
                await abandon_run_handoffs(session, test_run_id=run.id)
                await _fail_running_agent_executions(session, test_run_id=run.id)
            if run is not None and run.status in {
                "planning", "queued", "running", "awaiting_human",
            }:
                await RunStateRepository(session).mark_failed(test_run_id=run.id)
            if run is not None:
                payload: dict[str, object] = {**failure_event_payload(error)}
                if isinstance(error, SlopFinalizationError):
                    payload["stage"] = error.stage
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
            _unregister_execution(run_id)


async def run_worker(
    consumer: KafkaConsumer,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    retry_delay_seconds: float = 5.0,
    hitl_service: HITLWorkerService | None = None,
    max_concurrent_runs: int = 1,
) -> None:
    """Run isolated commands concurrently; acknowledge terminal partition prefixes."""
    if not 1 <= max_concurrent_runs <= 4:
        raise ValueError("Execution concurrency must be between 1 and 4.")
    connected = False
    heartbeat = asyncio.create_task(run_worker_heartbeat(
        session_factory, "execution", lambda: {"connected": connected,
                                               "capacity": max_concurrent_runs},
    ))
    watchdog = asyncio.create_task(_stall_watchdog(session_factory))
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
                connected = True
                logger.info("Execution worker connected; waiting for commands")
                if max_concurrent_runs == 1:
                    while True:
                        message = await consumer.receive()
                        await process_command(message, session_factory)
                        await consumer.commit()
                else:
                    await _consume_concurrently(consumer, session_factory, max_concurrent_runs)
            except Exception as error:
                connected = False
                record_temp_failure(stage="worker-iteration", error=error)
                logger.exception("Execution worker iteration failed; reconnecting")
                await consumer.stop()
                await asyncio.sleep(retry_delay_seconds)
    finally:
        heartbeat.cancel()
        watchdog.cancel()
        await asyncio.gather(heartbeat, watchdog, return_exceptions=True)
        await consumer.stop()
        if hitl_service is not None:
            await hitl_service.stop()


async def _consume_concurrently(
    consumer: KafkaConsumer,
    session_factory: async_sessionmaker[AsyncSession],
    limit: int,
) -> None:
    """Keep sessions/contexts isolated and drain all work before transport recovery."""
    pending: dict[tuple[str, int], deque[tuple[KafkaMessage, asyncio.Task[None]]]] = {}
    active: set[asyncio.Task[None]] = set()
    run_locks: dict[str, asyncio.Lock] = {}
    run_users: dict[str, int] = {}
    receiving: asyncio.Task[KafkaMessage] | None = None

    async def process(message: KafkaMessage) -> None:
        try:
            envelope = EventEnvelope.from_json(message.value.decode("utf-8"))
        except Exception:
            # Undecodable in any way: process_command dead-letters it.
            await process_command(message, session_factory)
            return
        run_id = str(envelope.payload.get("test_run_id"))
        lock = run_locks.setdefault(run_id, asyncio.Lock())
        run_users[run_id] = run_users.get(run_id, 0) + 1
        try:
            async with lock:
                await process_command(message, session_factory)
        finally:
            run_users[run_id] -= 1
            if run_users[run_id] == 0:
                run_users.pop(run_id)
                run_locks.pop(run_id)

    try:
        while True:
            # Inspect every completion, including failures behind an unfinished
            # prefix. Never acknowledge a later offset past an active command.
            for task in tuple(active):
                if task.done():
                    task.result()
                    active.remove(task)
            completed: list[KafkaMessage] = []
            for partition, queue in tuple(pending.items()):
                latest: KafkaMessage | None = None
                while queue and queue[0][1].done():
                    message, task = queue.popleft()
                    task.result()
                    latest = message
                if latest is not None:
                    completed.append(latest)
                if not queue:
                    pending.pop(partition)
            if completed:
                await consumer.commit_messages(tuple(completed))
            # Bound both running tasks and unacknowledged completed work. A human
            # wait cannot create an unbounded backlog behind its partition prefix.
            buffered = sum(len(queue) for queue in pending.values())
            if receiving is None and len(active) < limit and buffered < limit * 8:
                receiving = asyncio.create_task(consumer.receive())
            waiting: set[asyncio.Task[object]] = set(active)
            if receiving is not None:
                waiting.add(receiving)
            await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
            if receiving is not None and receiving.done():
                message = receiving.result()
                receiving = None
                task = asyncio.create_task(process(message))
                active.add(task)
                pending.setdefault((message.topic, message.partition), deque()).append(
                    (message, task)
                )
    finally:
        tasks: list[asyncio.Task[object]] = list(active)
        if receiving is not None:
            tasks.append(receiving)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _watch_execution_owner(connection: AsyncConnection) -> None:
    """A lost ownership connection stops all executions before restarting intake."""
    while True:
        await asyncio.sleep(2)
        async with asyncio.timeout(5):
            await connection.execute(text("SELECT 1"))
            await connection.commit()


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


_WORKER_LOCK_HANDLE = None


def acquire_worker_lock():
    """Take the single-instance lock for this worker chain.

    The lock is an OS file lock on a file in the temp directory, held by
    the supervisor process for the chain's whole life; the OS releases it
    automatically when that process dies, crash included. Returns the open
    handle - also kept referenced at module level so the lock stays held -
    or None, after printing the running worker's PID to stderr, when
    another chain already holds it. The worker child spawned by the
    supervisor never calls this: its parent holds the lock.
    """
    global _WORKER_LOCK_HANDLE
    path = os.environ.get("MARKETTWIN_WORKER_LOCK_FILE") or os.path.join(
        tempfile.gettempdir(), "markettwin-execution-worker.lock")
    try:
        handle = open(path, "r+b")
    except FileNotFoundError:
        handle = open(path, "w+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b" ")
        handle.flush()
    # The PID sits after the locked first byte: Windows byte-range
    # locks are mandatory, so a refused contender could not read a
    # PID stored inside the locked range.
    handle.seek(1)
    holder = handle.read().decode("utf-8", "replace").strip()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        print(
            "MarketTwin execution worker already running "
            f"(PID {holder or 'unknown'}); exiting.",
            file=sys.stderr,
        )
        return None
    handle.seek(1)
    handle.truncate()
    handle.write(str(os.getpid()).encode("utf-8"))
    handle.flush()
    _WORKER_LOCK_HANDLE = handle
    return handle


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
        max_poll_interval_ms=EXECUTION_MAX_POLL_INTERVAL_MS,
    )
    try:
        session_factory = create_session_factory(engine)
        hitl_service = build_hitl_worker_service(session_factory)
        # One process owns the configured viewer endpoint/registry. Concurrency
        # stays inside that owner; another process cannot recover its live runs.
        async with engine.connect() as ownership:
            key = {"key": "markettwin-execution-owner"}
            locked = await ownership.scalar(text(
                "SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"
            ), key)
            await ownership.commit()
            if not locked:
                raise RuntimeError("Another execution worker owns the live browser registry.")
            # Reaper (U-P2-04): this process now owns the registry and
            # no browser exists yet, so every still-open browser row is
            # an orphan from a crashed predecessor.
            async with session_factory() as reap_session:
                async with reap_session.begin():
                    reaped = await ExecutionRepository(
                        reap_session
                    ).reap_open_browser_sessions()
            if reaped:
                logging.getLogger(__name__).info(
                    "Closed %d orphaned browser session row(s) at startup.",
                    reaped,
                )
            try:
                # Phase 1b: the harvest poller shares this process and
                # its session factory. The import is deferred to here:
                # harvest_job imports this module's watchdog constant,
                # so importing it at module load would be a cycle.
                from markettwin_execution_orchestrator.harvest.harvest_job import (
                    run_harvest_poller,
                )
                from markettwin_execution_orchestrator.expectations.grounding_job import (
                    run_grounding_poller,
                )
                from markettwin_execution_orchestrator.harvest.skill_reverify import (
                    run_skill_reverify_poller,
                )
                from markettwin_execution_orchestrator.freshness.freshness_job import (
                    run_preflight_poller,
                )

                async with asyncio.TaskGroup() as group:
                    group.create_task(_watch_execution_owner(ownership))
                    group.create_task(run_harvest_poller(session_factory))
                    group.create_task(run_grounding_poller(session_factory))
                    group.create_task(run_skill_reverify_poller(session_factory))
                    group.create_task(run_preflight_poller(session_factory))
                    group.create_task(run_worker(
                        KafkaConsumer(settings), session_factory, hitl_service=hitl_service,
                        max_concurrent_runs=int(os.getenv("MARKETTWIN_EXECUTION_CONCURRENCY", "2")),
                    ))
            finally:
                try:
                    await ownership.rollback()
                    await ownership.execute(text(
                        "SELECT pg_advisory_unlock(hashtextextended(:key, 0))"
                    ), key)
                    await ownership.commit()
                except BaseException:
                    await ownership.invalidate()
                    raise
    finally:
        from markettwin_execution_orchestrator.browser.auth_session_broker import task_verification_sessions

        task_verification_sessions.clear()
        await engine.dispose()


if __name__ == "__main__":
    from markettwin_execution_orchestrator.supervisor import CHILD_ENV, supervise
    if os.environ.get(CHILD_ENV) != "1":
        # One chain per machine: the supervisor holds the single-instance
        # lock for the chain's whole life, so a duplicate launch exits
        # here - before it can supervise, consume commands, reap browser
        # sessions, or take over the viewer endpoint.
        if acquire_worker_lock() is None:
            raise SystemExit(3)
        supervise()
    else:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            pass
