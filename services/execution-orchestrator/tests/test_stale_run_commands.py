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


@pytest.mark.asyncio
async def test_workspace_mismatch_is_not_misclassified_as_missing_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid4()
    message = _message(run_id, offset=30)
    run = SimpleNamespace(
        id=run_id,
        workspace_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        status="queued",
    )
    session = SimpleNamespace(
        begin=Mock(side_effect=lambda: _BeginContext()),
        get=AsyncMock(return_value=run),
    )
    _install_acceptance_repositories(monkeypatch)
    consumer = _consumer([message])

    with pytest.raises(asyncio.CancelledError):
        await worker.run_worker(
            cast(KafkaConsumer, consumer),
            cast(async_sessionmaker[AsyncSession], lambda: _SessionContext(session)),
            retry_delay_seconds=0,
        )

    assert consumer.commit.await_count == 0
    session.get.assert_awaited_once_with(RunRecord, run_id)
