"""Fail-closed acknowledgement of run commands for deleted runs."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from markettwin_database.models.testing import TestRun as RunRecord
from markettwin_execution_orchestrator import worker
from markettwin_execution_orchestrator.workflow import run_request_handler
from markettwin_shared.messaging import (
    RUN_REQUESTED_EVENT_TYPE,
    RUN_REQUESTED_EVENT_VERSION,
    EventEnvelope,
    KafkaConsumer,
    KafkaMessage,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class _BeginContext:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> None:
        return None


class _SessionContext:
    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, *_args: object) -> None:
        return None


def _message(test_run_id: UUID, *, offset: int) -> KafkaMessage:
    envelope = EventEnvelope(
        event_id=uuid4(),
        event_type=RUN_REQUESTED_EVENT_TYPE,
        event_version=RUN_REQUESTED_EVENT_VERSION,
        occurred_at=datetime.now(UTC),
        producer="synthetic-stale-run-test",
        workspace_id=UUID("99999999-9999-4999-8999-999999999999"),
        trace_id=None,
        correlation_id=None,
        causation_id=None,
        payload={"test_run_id": str(test_run_id)},
    )
    return KafkaMessage(
        topic="markettwin.execution.commands",
        partition=0,
        offset=offset,
        key=None,
        value=envelope.to_json().encode("utf-8"),
    )


def _install_acceptance_repositories(
    monkeypatch: pytest.MonkeyPatch,
    *,
    is_processed: AsyncMock | None = None,
    mark_processed: AsyncMock | None = None,
    claim: AsyncMock | None = None,
) -> None:
    processed = SimpleNamespace(
        is_processed=is_processed or AsyncMock(return_value=False),
        mark_processed=mark_processed or AsyncMock(return_value=True),
    )
    state = SimpleNamespace(
        claim_queued_for_planning=claim or AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        run_request_handler,
        "ProcessedMessageRepository",
        Mock(return_value=processed),
    )
    monkeypatch.setattr(
        run_request_handler,
        "RunStateRepository",
        Mock(return_value=state),
    )


def _consumer(messages: list[KafkaMessage]) -> SimpleNamespace:
    return SimpleNamespace(
        start=AsyncMock(),
        receive=AsyncMock(side_effect=[*messages, asyncio.CancelledError()]),
        commit=AsyncMock(),
        stop=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_missing_run_is_committed_and_next_valid_command_executes(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    missing_id, valid_id = uuid4(), uuid4()
    workspace_id = UUID("99999999-9999-4999-8999-999999999999")
    missing, valid = _message(missing_id, offset=10), _message(valid_id, offset=11)
    run = SimpleNamespace(id=valid_id, workspace_id=workspace_id, status="planning")

    async def get_run(_model: type[RunRecord], test_run_id: UUID) -> object | None:
        return None if test_run_id == missing_id else run

    session = SimpleNamespace(
        begin=Mock(side_effect=lambda: _BeginContext()),
        get=AsyncMock(side_effect=get_run),
    )
    _install_acceptance_repositories(monkeypatch)
    monkeypatch.setattr(worker, "build_run_request", Mock(return_value=object()))
    execute = AsyncMock()
    monkeypatch.setattr(worker, "execute_markettwin_run", execute)
    consumer = _consumer([missing, valid])

    assert run_request_handler.EXECUTION_CONSUMER_NAME == "markettwin-execution-worker"
    caplog.set_level(logging.WARNING, logger=worker.__name__)
    with pytest.raises(asyncio.CancelledError):
        await worker.run_worker(
            cast(KafkaConsumer, consumer),
            cast(async_sessionmaker[AsyncSession], lambda: _SessionContext(session)),
            retry_delay_seconds=0,
        )

    assert consumer.commit.await_count == 2
    execute.assert_awaited_once()
    stale_event_id = EventEnvelope.from_json(missing.value.decode("utf-8")).event_id
    assert str(stale_event_id) in caplog.text
    assert str(missing_id) in caplog.text
    assert str(valid_id) not in caplog.text
    assert "synthetic-stale-run-test" not in caplog.text


@pytest.mark.asyncio
async def test_transient_database_lookup_failure_retries_without_committing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid4()
    message = _message(run_id, offset=20)
    workspace_id = UUID("99999999-9999-4999-8999-999999999999")
    run = SimpleNamespace(id=run_id, workspace_id=workspace_id, status="planning")

    async def get_run(_model: type[RunRecord], _test_run_id: UUID) -> object:
        if session.get.await_count == 1:
            raise OperationalError("SELECT", {}, RuntimeError("temporary database outage"))
        return run

    session = SimpleNamespace(
        begin=Mock(side_effect=lambda: _BeginContext()),
        get=AsyncMock(side_effect=get_run),
    )
    _install_acceptance_repositories(monkeypatch)
    monkeypatch.setattr(worker, "build_run_request", Mock(return_value=object()))
    execute = AsyncMock()
    monkeypatch.setattr(worker, "execute_markettwin_run", execute)
    consumer = _consumer([message, message])

    with pytest.raises(asyncio.CancelledError):
        await worker.run_worker(
            cast(KafkaConsumer, consumer),
            cast(async_sessionmaker[AsyncSession], lambda: _SessionContext(session)),
            retry_delay_seconds=0,
        )

    assert session.get.await_count == 3
    assert consumer.start.await_count == 2
    consumer.commit.assert_awaited_once()
    execute.assert_awaited_once()


class _TrackedBeginContext(_BeginContext):
    def __init__(self, events: list[str], *, fail_commit: bool = False) -> None:
        self.events = events
        self.fail_commit = fail_commit

    async def __aexit__(self, *args: object) -> None:
        if args[0] is not None:
            self.events.append("database_rollback")
        elif self.fail_commit:
            raise OperationalError("COMMIT", {}, RuntimeError("database unavailable"))
        else:
            self.events.append("database_commit")


@pytest.mark.asyncio
async def test_workspace_poison_and_replay_are_receipted_before_ack_then_valid_command_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    poison_id, valid_id = uuid4(), uuid4()
    poison, valid = _message(poison_id, offset=30), _message(valid_id, offset=31)
    events: list[str] = []
    poison_run = SimpleNamespace(id=poison_id, workspace_id=uuid4(), status="running")
    valid_run = SimpleNamespace(
        id=valid_id, workspace_id=UUID("99999999-9999-4999-8999-999999999999"), status="planning"
    )
    receipt_names: set[tuple[str, str]] = set()

    async def is_processed(**values: object) -> bool:
        return (str(values["consumer_name"]), str(values["message_id"])) in receipt_names

    async def record_receipt(**values: object) -> bool:
        receipt_names.add((str(values["consumer_name"]), str(values["message_id"])))
        events.append("receipt")
        return True

    async def get_run(_model: type[RunRecord], run_id: UUID) -> object:
        return poison_run if run_id == poison_id else valid_run

    session = SimpleNamespace(
        begin=Mock(side_effect=lambda: _TrackedBeginContext(events)),
        get=AsyncMock(side_effect=get_run),
    )
    claim, record = AsyncMock(return_value=True), AsyncMock(side_effect=record_receipt)
    _install_acceptance_repositories(
        monkeypatch,
        is_processed=AsyncMock(side_effect=is_processed),
        mark_processed=record,
        claim=claim,
    )
    monkeypatch.setattr(worker, "build_run_request", Mock(return_value=object()))
    execute = AsyncMock()
    monkeypatch.setattr(worker, "execute_markettwin_run", execute)
    consumer = _consumer([poison, poison, valid])
    consumer.commit.side_effect = lambda: events.append("kafka_ack")
    with pytest.raises(asyncio.CancelledError):
        await worker.run_worker(
            cast(KafkaConsumer, consumer),
            cast(async_sessionmaker[AsyncSession], lambda: _SessionContext(session)),
            retry_delay_seconds=0,
        )
    assert events[:5] == ["receipt", "database_commit", "kafka_ack", "database_commit", "kafka_ack"]
    assert consumer.commit.await_count == 3
    assert record.await_count == 2
    assert record.await_args_list[0].kwargs["consumer_name"] == (
        run_request_handler.EXECUTION_REJECTION_CONSUMER_NAME
    )
    assert (
        record.await_args_list[1].kwargs["consumer_name"]
        == run_request_handler.EXECUTION_CONSUMER_NAME
    )
    claim.assert_awaited_once_with(test_run_id=valid_id)
    execute.assert_awaited_once()
    assert session.get.await_args_list.count(((RunRecord, poison_id), {})) == 1
    assert poison_run.status == "running"


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_status", ["completed", "failed", "cancelled"])
async def test_terminal_cas_failure_is_refreshed_and_receipted_then_next_command_runs(
    monkeypatch: pytest.MonkeyPatch,
    terminal_status: str,
) -> None:
    terminal_id, valid_id = uuid4(), uuid4()
    workspace_id = UUID("99999999-9999-4999-8999-999999999999")
    original = SimpleNamespace(id=terminal_id, workspace_id=workspace_id, status="queued")
    current = SimpleNamespace(id=terminal_id, workspace_id=workspace_id, status=terminal_status)
    valid_run = SimpleNamespace(id=valid_id, workspace_id=workspace_id, status="planning")

    async def get_run(_model: type[RunRecord], run_id: UUID, **kwargs: object) -> object:
        if run_id == valid_id:
            return valid_run
        return current if kwargs.get("populate_existing") else original

    session = SimpleNamespace(
        begin=Mock(side_effect=lambda: _BeginContext()), get=AsyncMock(side_effect=get_run)
    )
    record, claim = AsyncMock(return_value=True), AsyncMock(side_effect=[False, True])
    _install_acceptance_repositories(monkeypatch, mark_processed=record, claim=claim)
    monkeypatch.setattr(worker, "build_run_request", Mock(return_value=object()))
    execute = AsyncMock()
    monkeypatch.setattr(worker, "execute_markettwin_run", execute)
    consumer = _consumer([_message(terminal_id, offset=40), _message(valid_id, offset=41)])
    with pytest.raises(asyncio.CancelledError):
        await worker.run_worker(
            cast(KafkaConsumer, consumer),
            cast(async_sessionmaker[AsyncSession], lambda: _SessionContext(session)),
            retry_delay_seconds=0,
        )
    session.get.assert_any_await(RunRecord, terminal_id, populate_existing=True)
    assert record.await_args_list[0].kwargs["consumer_name"] == (
        run_request_handler.EXECUTION_REJECTION_CONSUMER_NAME
    )
    assert consumer.commit.await_count == 2
    execute.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["queued", "planning", "running", "awaiting_human"])
async def test_nonterminal_claim_failure_stays_retryable_without_replay(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    run_id = uuid4()
    run = SimpleNamespace(
        id=run_id, workspace_id=UUID("99999999-9999-4999-8999-999999999999"), status=status
    )
    session = SimpleNamespace(
        begin=Mock(side_effect=lambda: _BeginContext()), get=AsyncMock(return_value=run)
    )
    record = AsyncMock(return_value=True)
    _install_acceptance_repositories(
        monkeypatch, mark_processed=record, claim=AsyncMock(return_value=False)
    )
    execute = AsyncMock()
    monkeypatch.setattr(worker, "execute_markettwin_run", execute)
    consumer = _consumer([_message(run_id, offset=50)])
    with pytest.raises(asyncio.CancelledError):
        await worker.run_worker(
            cast(KafkaConsumer, consumer),
            cast(async_sessionmaker[AsyncSession], lambda: _SessionContext(session)),
            retry_delay_seconds=0,
        )
    consumer.commit.assert_not_awaited()
    record.assert_not_awaited()
    execute.assert_not_awaited()
    assert run.status == status


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["receipt", "commit"])
async def test_rejection_database_failure_cannot_acknowledge_command(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    run_id = uuid4()
    events: list[str] = []
    session = SimpleNamespace(
        begin=Mock(
            side_effect=lambda: _TrackedBeginContext(events, fail_commit=failure == "commit")
        ),
        get=AsyncMock(
            return_value=SimpleNamespace(id=run_id, workspace_id=uuid4(), status="queued")
        ),
    )
    record = AsyncMock(
        return_value=True,
        side_effect=OperationalError("INSERT", {}, RuntimeError("unavailable"))
        if failure == "receipt"
        else None,
    )
    claim = AsyncMock(return_value=True)
    _install_acceptance_repositories(monkeypatch, mark_processed=record, claim=claim)
    execute = AsyncMock()
    monkeypatch.setattr(worker, "execute_markettwin_run", execute)
    consumer = _consumer([_message(run_id, offset=60)])
    with pytest.raises(asyncio.CancelledError):
        await worker.run_worker(
            cast(KafkaConsumer, consumer),
            cast(async_sessionmaker[AsyncSession], lambda: _SessionContext(session)),
            retry_delay_seconds=0,
        )
    consumer.commit.assert_not_awaited()
    claim.assert_not_awaited()
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_accepted_receipt_with_mismatched_workspace_cannot_fail_active_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid4()
    run = SimpleNamespace(id=run_id, workspace_id=uuid4(), status="running")
    session = SimpleNamespace(
        begin=Mock(side_effect=lambda: _BeginContext()),
        get=AsyncMock(return_value=run),
        commit=AsyncMock(),
    )

    async def is_processed(*, consumer_name: str, message_id: str) -> bool:
        return consumer_name == run_request_handler.EXECUTION_CONSUMER_NAME

    record, claim = AsyncMock(return_value=True), AsyncMock(return_value=True)
    _install_acceptance_repositories(
        monkeypatch,
        is_processed=AsyncMock(side_effect=is_processed),
        mark_processed=record,
        claim=claim,
    )
    abandon, fail, execute = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(worker, "abandon_run_handoffs", abandon)
    monkeypatch.setattr(
        worker, "RunStateRepository", Mock(return_value=SimpleNamespace(mark_failed=fail))
    )
    monkeypatch.setattr(
        worker, "RunEventRepository", Mock(return_value=SimpleNamespace(create=AsyncMock()))
    )
    monkeypatch.setattr(worker, "execute_markettwin_run", execute)
    consumer = _consumer([_message(run_id, offset=70)])
    with pytest.raises(asyncio.CancelledError):
        await worker.run_worker(
            cast(KafkaConsumer, consumer),
            cast(async_sessionmaker[AsyncSession], lambda: _SessionContext(session)),
            retry_delay_seconds=0,
        )
    consumer.commit.assert_awaited_once()
    assert record.await_args is not None
    assert record.await_args.kwargs["consumer_name"] == (
        run_request_handler.EXECUTION_REJECTION_CONSUMER_NAME
    )
    claim.assert_not_awaited()
    abandon.assert_not_awaited()
    fail.assert_not_awaited()
    execute.assert_not_awaited()
    assert run.status == "running"
