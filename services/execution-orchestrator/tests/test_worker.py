"""Persistent worker transport and execution behavior."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator import worker
from markettwin_shared.messaging import EventEnvelope, KafkaConsumer, KafkaMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SessionContext:
    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        pass


@pytest.mark.parametrize("body", [b"not json", b"\xff", b"{}", b"[]"])
async def test_invalid_command_records_receipt_without_execution(monkeypatch, body):
    session = SimpleNamespace(begin=lambda: SessionContext(None))
    record = AsyncMock(return_value=True)
    monkeypatch.setattr(worker, "ProcessedMessageRepository",
                        lambda _session: SimpleNamespace(mark_processed=record))
    execute = AsyncMock()
    monkeypatch.setattr(worker, "execute_markettwin_run", execute)
    message = KafkaMessage("commands", 2, 42, None, body)
    await worker.process_command(message, lambda: SessionContext(session))
    receipt = record.await_args.kwargs
    assert receipt["consumer_name"].endswith(":invalid")
    assert receipt["partition"] == 2 and receipt["kafka_offset"] == 42
    assert len(receipt["message_id"]) == 64
    execute.assert_not_awaited()


@pytest.mark.parametrize("version,payload", [(2, {"test_run_id": str(uuid4())}),
                                             (1, {}), (1, {"test_run_id": "bad"})])
async def test_unsupported_command_is_durably_rejected(monkeypatch, version, payload):
    session = SimpleNamespace(begin=lambda: SessionContext(None), rollback=AsyncMock())
    record = AsyncMock(return_value=True)
    monkeypatch.setattr(worker, "ProcessedMessageRepository",
                        lambda _session: SimpleNamespace(mark_processed=record))
    envelope = EventEnvelope(
        event_id=uuid4(), event_type="run.requested", event_version=version,
        occurred_at=datetime.now(UTC), producer="test", workspace_id=uuid4(),
        trace_id=None, correlation_id=None, causation_id=None, payload=payload,
    )
    await worker.process_command(
        KafkaMessage("commands", 0, 3, None, envelope.to_json().encode()),
        lambda: SessionContext(session),
    )
    record.assert_awaited_once()
    session.rollback.assert_awaited_once()


async def test_invalid_command_receipt_failure_remains_retryable(monkeypatch):
    session = SimpleNamespace(begin=lambda: SessionContext(None))
    monkeypatch.setattr(worker, "ProcessedMessageRepository", lambda _session:
                        SimpleNamespace(mark_processed=AsyncMock(side_effect=RuntimeError("db"))))
    with pytest.raises(RuntimeError, match="db"):
        await worker.process_command(KafkaMessage("commands", 0, 3, None, b"bad"),
                                     lambda: SessionContext(session))


async def test_concurrent_invalid_command_reaches_rejection_and_ack(monkeypatch):
    incoming = asyncio.Queue()
    message = KafkaMessage("commands", 0, 3, None, b"bad")
    incoming.put_nowait(message)
    rejected, acknowledged = asyncio.Event(), asyncio.Event()
    reject = AsyncMock(side_effect=lambda *_args: rejected.set())
    monkeypatch.setattr(worker, "_reject_invalid_command", reject)

    async def commit(messages):
        assert rejected.is_set()
        assert messages == (message,)
        acknowledged.set()

    consumer = SimpleNamespace(receive=incoming.get, commit_messages=commit)
    task = asyncio.create_task(worker._consume_concurrently(consumer, object(), 2))
    try:
        await asyncio.wait_for(acknowledged.wait(), 2)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    reject.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("checkpoint", [False, True])
async def test_interrupted_audit_redelivery_resumes_checkpoint(monkeypatch, checkpoint):
    run_id = uuid4()
    run = SimpleNamespace(id=run_id, status="running", run_kind="slop",
        configuration_snapshot={"slop_checkpoint": {"visited": [], "pending": []}}
                               if checkpoint else {})
    session = SimpleNamespace(get=AsyncMock(return_value=run), rollback=AsyncMock(),
        commit=AsyncMock(), execute=AsyncMock(), scalar=AsyncMock(return_value=None))
    envelope = SimpleNamespace(payload={"test_run_id": str(run_id)})
    monkeypatch.setattr(EventEnvelope, "from_json", Mock(return_value=envelope))
    monkeypatch.setattr(worker, "accept_run_requested", AsyncMock(return_value=None))
    cleanup = AsyncMock()
    monkeypatch.setattr(worker, "abandon_run_handoffs", cleanup)
    request = object()
    monkeypatch.setattr(worker, "build_run_request", Mock(return_value=request))
    execute = AsyncMock()
    monkeypatch.setattr(worker, "execute_markettwin_run", execute)
    await worker.process_command(KafkaMessage("commands", 0, 1, None, b"{}"),
        lambda: SessionContext(session))
    cleanup.assert_awaited_once_with(session, test_run_id=run_id)
    execute.assert_awaited_once_with(request, session=session)


async def test_slop_finalization_retry_records_stage_and_stops_after_three_failures(monkeypatch):
    from markettwin_execution_orchestrator.workflow.run_request_handler import AcceptedRunRequest
    from markettwin_execution_orchestrator.workflow.slop_run import SlopFinalizationError

    run_id = uuid4()
    checkpoint = {"visited": ["https://app.test/"], "pending": []}
    run = SimpleNamespace(id=run_id, status="running", run_kind="slop",
        configuration_snapshot={"slop_checkpoint": checkpoint})
    session = SimpleNamespace(get=AsyncMock(return_value=run), rollback=AsyncMock(),
        commit=AsyncMock(), execute=AsyncMock())
    envelope = SimpleNamespace(payload={"test_run_id": str(run_id)})
    monkeypatch.setattr(EventEnvelope, "from_json", Mock(return_value=envelope))
    monkeypatch.setattr(worker, "accept_run_requested", AsyncMock(
        return_value=AcceptedRunRequest(run_id),
    ))
    monkeypatch.setattr(worker, "abandon_run_handoffs", AsyncMock())
    monkeypatch.setattr(worker, "build_run_request", Mock())
    monkeypatch.setattr(worker, "execute_markettwin_run", AsyncMock(
        side_effect=SlopFinalizationError("publication"),
    ))
    emit = AsyncMock()
    fail = AsyncMock()
    monkeypatch.setattr(worker, "RunEventRepository", lambda _: SimpleNamespace(create=emit))
    monkeypatch.setattr(worker, "RunStateRepository", lambda _: SimpleNamespace(mark_failed=fail))
    message = KafkaMessage("commands", 0, 1, None, b"{}")
    for _ in range(2):
        with pytest.raises(SlopFinalizationError):
            await worker.process_command(message, lambda: SessionContext(session))
    fail.assert_not_awaited()
    await worker.process_command(message, lambda: SessionContext(session))
    fail.assert_awaited_once_with(test_run_id=run_id)
    stage_events = [call.kwargs["payload"] for call in emit.await_args_list
                    if call.kwargs["event_type"] == "slop.finalization.failed"]
    assert stage_events == [{"stage": "publication", "attempt": n} for n in range(1, 4)]
    assert emit.await_args.kwargs["payload"]["code"] == "slop_finalization"
    assert run.configuration_snapshot["slop_checkpoint"] == checkpoint


@pytest.mark.parametrize("second_partition", [0, 1])
async def test_concurrent_human_wait_preserves_partition_acknowledgements(
    monkeypatch: pytest.MonkeyPatch, second_partition: int,
) -> None:
    incoming: asyncio.Queue[KafkaMessage] = asyncio.Queue()
    messages = tuple(KafkaMessage("commands", partition, index, None, EventEnvelope(
        event_id=uuid4(), event_type="run.requested", event_version=1,
        occurred_at=datetime.now(UTC), producer="test", workspace_id=uuid4(),
        trace_id=None, correlation_id=None, causation_id=None,
        payload={"test_run_id": str(uuid4())},
    ).to_json().encode()) for index, partition in enumerate((0, second_partition)))
    for message in messages:
        incoming.put_nowait(message)
    human_waiting, other_completed, resume = asyncio.Event(), asyncio.Event(), asyncio.Event()
    acknowledged: list[KafkaMessage] = []
    committed = asyncio.Event()

    async def process(message: KafkaMessage, *_args: object) -> None:
        if message == messages[0]:
            human_waiting.set()
            await resume.wait()
        else:
            await human_waiting.wait()
            other_completed.set()

    async def commit(batch: tuple[KafkaMessage, ...]) -> None:
        acknowledged.extend(batch)
        committed.set()

    consumer = SimpleNamespace(receive=incoming.get, commit_messages=commit)
    monkeypatch.setattr(worker, "process_command", process)
    task = asyncio.create_task(worker._consume_concurrently(
        cast(KafkaConsumer, consumer), cast(async_sessionmaker[AsyncSession], object()), 2,
    ))
    try:
        await asyncio.wait_for(other_completed.wait(), 2)
        if second_partition == 1:
            await asyncio.wait_for(committed.wait(), 2)
            assert acknowledged == [messages[1]]
        else:
            # Let the scheduler observe the second completion.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert acknowledged == []
        committed.clear()
        resume.set()
        await asyncio.wait_for(committed.wait(), 2)
        assert acknowledged[-1] == messages[0 if second_partition == 1 else 1]
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_concurrent_intake_cancellation_drains_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incoming: asyncio.Queue[KafkaMessage] = asyncio.Queue()
    envelope = EventEnvelope(
        event_id=uuid4(), event_type="run.requested", event_version=1,
        occurred_at=datetime.now(UTC), producer="test", workspace_id=uuid4(),
        trace_id=None, correlation_id=None, causation_id=None,
        payload={"test_run_id": str(uuid4())},
    )
    incoming.put_nowait(KafkaMessage("commands", 0, 0, None, envelope.to_json().encode()))
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def process(*_args: object) -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    consumer = SimpleNamespace(receive=incoming.get, commit_messages=AsyncMock())
    monkeypatch.setattr(worker, "process_command", process)
    task = asyncio.create_task(worker._consume_concurrently(
        cast(KafkaConsumer, consumer), cast(async_sessionmaker[AsyncSession], object()), 2,
    ))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()
    consumer.commit_messages.assert_not_awaited()


async def test_human_wait_occupies_the_single_execution_consumer(monkeypatch) -> None:
    waiting, resume = asyncio.Event(), asyncio.Event()
    consumer = SimpleNamespace(
        start=AsyncMock(), receive=AsyncMock(side_effect=["run", asyncio.CancelledError()]),
        commit=AsyncMock(), stop=AsyncMock(),
    )

    async def process(*_args: object) -> None:
        waiting.set()
        await resume.wait()

    monkeypatch.setattr(worker, "process_command", process)
    task = asyncio.create_task(worker.run_worker(
        cast(KafkaConsumer, consumer), cast(async_sessionmaker[AsyncSession], object()),
    ))
    try:
        await asyncio.wait_for(waiting.wait(), timeout=1)
        assert consumer.receive.await_count == 1
        consumer.commit.assert_not_awaited()
        resume.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        consumer.commit.assert_awaited_once()
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
async def test_worker_reconnects_and_handles_multiple_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumer = SimpleNamespace(
        start=AsyncMock(side_effect=[OSError("DNS failed"), None]),
        receive=AsyncMock(side_effect=["first", "second", asyncio.CancelledError()]),
        commit=AsyncMock(),
        stop=AsyncMock(),
    )
    process = AsyncMock()
    monkeypatch.setattr(worker, "process_command", process)
    with pytest.raises(asyncio.CancelledError):
        await worker.run_worker(
            cast(KafkaConsumer, consumer),
            cast(async_sessionmaker[AsyncSession], object()),
            retry_delay_seconds=0,
        )
    assert consumer.start.await_count == 2
    assert process.await_count == 2
    assert consumer.commit.await_count == 2
    assert consumer.stop.await_count == 2


@pytest.mark.asyncio
async def test_worker_does_not_commit_failed_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumer = SimpleNamespace(
        start=AsyncMock(),
        receive=AsyncMock(side_effect=["command", asyncio.CancelledError()]),
        commit=AsyncMock(),
        stop=AsyncMock(),
    )
    monkeypatch.setattr(worker, "process_command", AsyncMock(side_effect=RuntimeError()))
    with pytest.raises(asyncio.CancelledError):
        await worker.run_worker(
            cast(KafkaConsumer, consumer),
            cast(async_sessionmaker[AsyncSession], object()),
            retry_delay_seconds=0,
        )
    consumer.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_commits_after_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def process(*args: object) -> None:
        calls.append("executed")

    async def commit() -> None:
        calls.append("committed")

    consumer = SimpleNamespace(
        start=AsyncMock(),
        receive=AsyncMock(side_effect=["command", asyncio.CancelledError()]),
        commit=commit,
        stop=AsyncMock(),
    )
    monkeypatch.setattr(worker, "process_command", process)
    with pytest.raises(asyncio.CancelledError):
        await worker.run_worker(
            cast(KafkaConsumer, consumer),
            cast(async_sessionmaker[AsyncSession], object()),
        )
    assert calls == ["executed", "committed"]


@pytest.mark.asyncio
async def test_terminal_duplicate_is_not_executed(monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = uuid4()
    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(status="completed")))

    def factory() -> SessionContext:
        return SessionContext(session)

    envelope = SimpleNamespace(payload={"test_run_id": str(run_id)})
    monkeypatch.setattr(EventEnvelope, "from_json", Mock(return_value=envelope))
    monkeypatch.setattr(worker, "accept_run_requested", AsyncMock(return_value=None))
    execute = AsyncMock()
    monkeypatch.setattr(worker, "execute_markettwin_run", execute)
    await worker.process_command(
        KafkaMessage("commands", 0, 1, None, b"{}"),
        cast(async_sessionmaker[AsyncSession], factory),
    )
    execute.assert_not_awaited()


async def test_completed_run_logging_does_not_read_expired_orm_identity(monkeypatch) -> None:
    run_id = uuid4()

    class ExpiringRun:
        expired = False

        @property
        def id(self):
            assert not self.expired, "A handoff rollback expired this ORM identity."
            return run_id

    run = ExpiringRun()
    session = SimpleNamespace(get=AsyncMock(return_value=run), rollback=AsyncMock())
    envelope = SimpleNamespace(payload={"test_run_id": str(run_id)})
    monkeypatch.setattr(EventEnvelope, "from_json", Mock(return_value=envelope))
    monkeypatch.setattr(
        worker, "accept_run_requested", AsyncMock(return_value=SimpleNamespace(test_run_id=run_id)),
    )
    monkeypatch.setattr(worker, "build_run_request", Mock(return_value=object()))
    note = Mock()
    monkeypatch.setattr(worker, "record_temp_note", note)

    async def execute(*args, **kwargs):
        run.expired = True

    monkeypatch.setattr(worker, "execute_markettwin_run", execute)
    await worker.process_command(
        KafkaMessage("commands", 0, 1, None, b"{}"),
        cast(async_sessionmaker[AsyncSession], lambda: SessionContext(session)),
    )
    session.rollback.assert_not_awaited()
    note.assert_called_with(stage="completed", detail=f"Completed TestRun {run_id}")


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate", [False, True])
async def test_failed_or_interrupted_run_is_finalized(
    monkeypatch: pytest.MonkeyPatch,
    duplicate: bool,
) -> None:
    run_id = uuid4()
    run = SimpleNamespace(id=run_id, status="planning")
    session = SimpleNamespace(
        get=AsyncMock(return_value=run), rollback=AsyncMock(), commit=AsyncMock(),
        execute=AsyncMock(),
    )

    def factory() -> SessionContext:
        return SessionContext(session)

    envelope = SimpleNamespace(payload={"test_run_id": str(run_id)})
    monkeypatch.setattr(EventEnvelope, "from_json", Mock(return_value=envelope))
    monkeypatch.setattr(
        worker,
        "accept_run_requested",
        AsyncMock(
            return_value=None if duplicate else SimpleNamespace(test_run_id=run_id),
        ),
    )
    monkeypatch.setattr(worker, "build_run_request", Mock(return_value=object()))
    execute = AsyncMock(side_effect=RuntimeError("Model unavailable"))
    monkeypatch.setattr(worker, "execute_markettwin_run", execute)
    repository = SimpleNamespace(mark_failed=AsyncMock())
    monkeypatch.setattr(worker, "RunStateRepository", Mock(return_value=repository))
    event_repository = SimpleNamespace(create=AsyncMock())
    monkeypatch.setattr(worker, "RunEventRepository", Mock(return_value=event_repository))
    await worker.process_command(
        KafkaMessage("commands", 0, 1, None, b"{}"),
        cast(async_sessionmaker[AsyncSession], factory),
    )
    repository.mark_failed.assert_awaited_once_with(test_run_id=run_id)
    session.commit.assert_awaited_once()
    assert execute.await_count == (0 if duplicate else 1)
    event = event_repository.create.await_args.kwargs
    assert event["event_type"] == "run.failed"
    assert "Model unavailable" not in str(event["payload"])
    assert event["payload"]["code"] == ("interrupted" if duplicate else "execution_failed")


@pytest.mark.asyncio
async def test_failed_run_logs_and_stores_a_reviewed_reason(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    run_id = uuid4()
    run = SimpleNamespace(id=run_id, status="planning")
    session = SimpleNamespace(
        get=AsyncMock(return_value=run), rollback=AsyncMock(), commit=AsyncMock(),
        execute=AsyncMock(),
    )

    def factory() -> SessionContext:
        return SessionContext(session)

    envelope = SimpleNamespace(payload={"test_run_id": str(run_id)})
    monkeypatch.setattr(EventEnvelope, "from_json", Mock(return_value=envelope))
    monkeypatch.setattr(
        worker, "accept_run_requested", AsyncMock(return_value=SimpleNamespace(test_run_id=run_id)),
    )
    monkeypatch.setattr(worker, "build_run_request", Mock(return_value=object()))
    monkeypatch.setattr(
        worker,
        "execute_markettwin_run",
        AsyncMock(side_effect=ValueError("Feature planner returned no schema-valid cases.")),
    )
    monkeypatch.setattr(
        worker, "RunStateRepository", Mock(return_value=SimpleNamespace(mark_failed=AsyncMock())),
    )
    event_repository = SimpleNamespace(create=AsyncMock())
    monkeypatch.setattr(worker, "RunEventRepository", Mock(return_value=event_repository))
    with caplog.at_level("ERROR", logger="markettwin_execution_orchestrator.worker"):
        await worker.process_command(
            KafkaMessage("commands", 0, 1, None, b"{}"),
            cast(async_sessionmaker[AsyncSession], factory),
        )
    payload = event_repository.create.await_args.kwargs["payload"]
    assert payload["code"] == "invalid_plan"
    assert payload["reason"] == "Feature planner returned no schema-valid cases."
    assert "Feature planner returned no schema-valid cases." in caplog.text


@pytest.mark.asyncio
async def test_failed_run_log_omits_unreviewed_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    run_id = uuid4()
    run = SimpleNamespace(id=run_id, status="planning")
    session = SimpleNamespace(
        get=AsyncMock(return_value=run), rollback=AsyncMock(), commit=AsyncMock(),
        execute=AsyncMock(),
    )

    def factory() -> SessionContext:
        return SessionContext(session)

    envelope = SimpleNamespace(payload={"test_run_id": str(run_id)})
    monkeypatch.setattr(EventEnvelope, "from_json", Mock(return_value=envelope))
    monkeypatch.setattr(
        worker, "accept_run_requested", AsyncMock(return_value=SimpleNamespace(test_run_id=run_id)),
    )
    monkeypatch.setattr(worker, "build_run_request", Mock(return_value=object()))
    monkeypatch.setattr(
        worker,
        "execute_markettwin_run",
        AsyncMock(side_effect=RuntimeError("SECRET_CANARY provider body")),
    )
    monkeypatch.setattr(
        worker, "RunStateRepository", Mock(return_value=SimpleNamespace(mark_failed=AsyncMock())),
    )
    monkeypatch.setattr(
        worker, "RunEventRepository", Mock(return_value=SimpleNamespace(create=AsyncMock())),
    )
    with caplog.at_level("ERROR", logger="markettwin_execution_orchestrator.worker"):
        await worker.process_command(
            KafkaMessage("commands", 0, 1, None, b"{}"),
            cast(async_sessionmaker[AsyncSession], factory),
        )
    assert "SECRET_CANARY" not in caplog.text
    assert "detail omitted" in caplog.text


@pytest.mark.asyncio
async def test_interrupted_explore_test_redelivery_resumes_from_frontier(monkeypatch):
    run_id = uuid4()
    run = SimpleNamespace(id=run_id, status="running", run_kind="explore_test",
        configuration_snapshot={"discovery_frontier": {
            "visited": ["https://app.test/"], "pending": ["https://app.test/two"]}})
    session = SimpleNamespace(get=AsyncMock(return_value=run), rollback=AsyncMock(),
        commit=AsyncMock(), execute=AsyncMock(), scalar=AsyncMock(return_value=uuid4()))
    envelope = SimpleNamespace(payload={"test_run_id": str(run_id)})
    monkeypatch.setattr(EventEnvelope, "from_json", Mock(return_value=envelope))
    monkeypatch.setattr(worker, "accept_run_requested", AsyncMock(return_value=None))
    cleanup = AsyncMock()
    monkeypatch.setattr(worker, "abandon_run_handoffs", cleanup)
    request = object()
    monkeypatch.setattr(worker, "build_run_request", Mock(return_value=request))
    execute = AsyncMock()
    monkeypatch.setattr(worker, "execute_markettwin_run", execute)
    await worker.process_command(KafkaMessage("commands", 0, 1, None, b"{}"),
        lambda: SessionContext(session))
    cleanup.assert_awaited_once_with(session, test_run_id=run_id)
    execute.assert_awaited_once_with(request, session=session)


@pytest.mark.asyncio
async def test_interrupted_explore_test_without_frontier_is_finalized(monkeypatch):
    run_id = uuid4()
    run = SimpleNamespace(id=run_id, status="running", run_kind="explore_test",
        configuration_snapshot={})
    session = SimpleNamespace(get=AsyncMock(return_value=run), rollback=AsyncMock(),
        commit=AsyncMock(), execute=AsyncMock(), scalar=AsyncMock(return_value=uuid4()))
    envelope = SimpleNamespace(payload={"test_run_id": str(run_id)})
    monkeypatch.setattr(EventEnvelope, "from_json", Mock(return_value=envelope))
    monkeypatch.setattr(worker, "accept_run_requested", AsyncMock(return_value=None))
    monkeypatch.setattr(worker, "build_run_request", Mock(return_value=object()))
    execute = AsyncMock()
    monkeypatch.setattr(worker, "execute_markettwin_run", execute)
    repository = SimpleNamespace(mark_failed=AsyncMock())
    monkeypatch.setattr(worker, "RunStateRepository", Mock(return_value=repository))
    event_repository = SimpleNamespace(create=AsyncMock())
    monkeypatch.setattr(worker, "RunEventRepository", Mock(return_value=event_repository))
    await worker.process_command(KafkaMessage("commands", 0, 1, None, b"{}"),
        lambda: SessionContext(session))
    execute.assert_not_awaited()
    repository.mark_failed.assert_awaited_once_with(test_run_id=run_id)
    event = event_repository.create.await_args.kwargs
    assert event["event_type"] == "run.failed"
    assert event["payload"]["code"] == "interrupted"


def _register_fake_execution(run_id, *, started_at=None):
    async def _never() -> None:
        await asyncio.Event().wait()
    task = asyncio.create_task(_never())
    worker._EXECUTION_WATCHES[run_id] = worker._ExecutionWatch(
        task=task, started_at=started_at or datetime.now(UTC))
    return task


@pytest.mark.asyncio
async def test_stall_watchdog_cancels_silent_running_execution():
    run_id = uuid4()
    run = SimpleNamespace(id=run_id, status="running")
    latest = datetime.now(UTC) - timedelta(seconds=worker.STALL_WATCHDOG_SECONDS + 60)
    session = SimpleNamespace(get=AsyncMock(return_value=run),
        scalar=AsyncMock(return_value=latest))
    task = _register_fake_execution(run_id, started_at=latest - timedelta(seconds=30))
    try:
        cancelled = await worker._cancel_stalled_executions(
            lambda: SessionContext(session), now=datetime.now(UTC))
        assert cancelled == (run_id,)
        await asyncio.sleep(0)
        assert task.cancelling() >= 1
    finally:
        worker._EXECUTION_WATCHES.pop(run_id, None)
        worker._WATCHDOG_CANCELLED.discard(run_id)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_stall_watchdog_never_touches_parked_run():
    # A login handoff is legitimately idle far past the bound by design.
    run_id = uuid4()
    run = SimpleNamespace(id=run_id, status="awaiting_human")
    latest = datetime.now(UTC) - timedelta(seconds=worker.STALL_WATCHDOG_SECONDS * 2)
    session = SimpleNamespace(get=AsyncMock(return_value=run),
        scalar=AsyncMock(return_value=latest))
    task = _register_fake_execution(run_id)
    try:
        cancelled = await worker._cancel_stalled_executions(
            lambda: SessionContext(session), now=datetime.now(UTC))
        assert cancelled == ()
        await asyncio.sleep(0)
        assert task.cancelling() == 0
    finally:
        worker._EXECUTION_WATCHES.pop(run_id, None)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(("age_seconds", "attempt_age"), [(30, 3600), (800, 900), (3600, 24)])
async def test_stall_watchdog_leaves_active_execution_alone(age_seconds, attempt_age):
    run_id = uuid4()
    run = SimpleNamespace(id=run_id, status="running")
    latest = datetime.now(UTC) - timedelta(seconds=age_seconds)
    session = SimpleNamespace(get=AsyncMock(return_value=run),
        scalar=AsyncMock(return_value=latest))
    task = _register_fake_execution(run_id, started_at=datetime.now(UTC) - timedelta(seconds=attempt_age))
    try:
        cancelled = await worker._cancel_stalled_executions(
            lambda: SessionContext(session), now=datetime.now(UTC))
        assert cancelled == ()
        await asyncio.sleep(0)
        assert task.cancelling() == 0
    finally:
        worker._EXECUTION_WATCHES.pop(run_id, None)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_stall_watchdog_closes_silent_run_failed_with_watchdog_site(monkeypatch):
    run_id = uuid4()
    run = SimpleNamespace(id=run_id, status="running", run_kind="slop",
        configuration_snapshot={})
    session = SimpleNamespace(get=AsyncMock(return_value=run), rollback=AsyncMock(),
        commit=AsyncMock(), execute=AsyncMock(), scalar=AsyncMock(return_value=None))
    envelope = SimpleNamespace(payload={"test_run_id": str(run_id)})
    monkeypatch.setattr(EventEnvelope, "from_json", Mock(return_value=envelope))
    monkeypatch.setattr(worker, "accept_run_requested",
        AsyncMock(return_value=SimpleNamespace(test_run_id=run_id)))
    monkeypatch.setattr(worker, "abandon_run_handoffs", AsyncMock())
    monkeypatch.setattr(worker, "build_run_request", Mock(return_value=object()))

    async def _hang(*_args, **_kwargs):
        await asyncio.Event().wait()
    monkeypatch.setattr(worker, "execute_markettwin_run", _hang)
    repository = SimpleNamespace(mark_failed=AsyncMock())
    monkeypatch.setattr(worker, "RunStateRepository", Mock(return_value=repository))
    event_repository = SimpleNamespace(create=AsyncMock())
    monkeypatch.setattr(worker, "RunEventRepository", Mock(return_value=event_repository))
    factory = lambda: SessionContext(session)  # noqa: E731
    task = asyncio.create_task(worker.process_command(
        KafkaMessage("commands", 0, 1, None, b"{}"), factory))
    try:
        for _ in range(100):
            if run_id in worker._EXECUTION_WATCHES:
                break
            await asyncio.sleep(0.01)
        assert run_id in worker._EXECUTION_WATCHES
        watchdog_session = SimpleNamespace(get=AsyncMock(return_value=run),
            scalar=AsyncMock(return_value=datetime.now(UTC)
                - timedelta(seconds=worker.STALL_WATCHDOG_SECONDS + 60)))
        cancelled = await worker._cancel_stalled_executions(
            lambda: SessionContext(watchdog_session),
            now=datetime.now(UTC) + timedelta(seconds=worker.STALL_WATCHDOG_SECONDS + 1))
        assert cancelled == (run_id,)
        await asyncio.wait_for(task, timeout=10)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        worker._EXECUTION_WATCHES.pop(run_id, None)
        worker._WATCHDOG_CANCELLED.discard(run_id)
    repository.mark_failed.assert_awaited_once_with(test_run_id=run_id)
    event = event_repository.create.await_args.kwargs
    assert event["event_type"] == "run.failed"
    assert event["payload"]["error_type"] == "StallWatchdogError"
    assert event["payload"]["code"] == "execution_stalled"
    assert event["payload"]["site"].startswith("worker.py:")
    assert run_id not in worker._EXECUTION_WATCHES
@pytest.mark.asyncio
async def test_a2_failed_run_terminalizes_running_child_executions(monkeypatch):
    """Astra A2 (worker): when the worker fails a run, its
    still-running child AgentExecutions must be terminalized too.
    Before the fix only the redelivery branch closed them, so a run
    whose executor died outside its own cleanup (e.g. persona
    browser creation) left children "running" forever."""
    run_id = uuid4()
    run = SimpleNamespace(id=run_id, status="planning")
    session = SimpleNamespace(
        get=AsyncMock(return_value=run), rollback=AsyncMock(), commit=AsyncMock(),
        execute=AsyncMock(),
    )

    def factory() -> SessionContext:
        return SessionContext(session)

    envelope = SimpleNamespace(payload={"test_run_id": str(run_id)})
    monkeypatch.setattr(EventEnvelope, "from_json", Mock(return_value=envelope))
    monkeypatch.setattr(
        worker, "accept_run_requested",
        AsyncMock(return_value=SimpleNamespace(test_run_id=run_id)),
    )
    monkeypatch.setattr(worker, "build_run_request", Mock(return_value=object()))
    monkeypatch.setattr(
        worker, "execute_markettwin_run",
        AsyncMock(side_effect=RuntimeError("walk died outside cleanup")),
    )
    repository = SimpleNamespace(mark_failed=AsyncMock())
    monkeypatch.setattr(worker, "RunStateRepository", Mock(return_value=repository))
    event_repository = SimpleNamespace(create=AsyncMock())
    monkeypatch.setattr(worker, "RunEventRepository", Mock(return_value=event_repository))
    await worker.process_command(
        KafkaMessage("commands", 0, 1, None, b"{}"),
        cast(async_sessionmaker[AsyncSession], factory),
    )
    repository.mark_failed.assert_awaited_once_with(test_run_id=run_id)
    compiled = []
    for call in session.execute.await_args_list:
        try:
            compiled.append(str(call.args[0].compile(
                compile_kwargs={"literal_binds": True})))
        except Exception:
            continue
    assert any("agent_executions" in sql and "interrupted" in sql
               for sql in compiled)
