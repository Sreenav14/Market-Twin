"""Persistent worker transport and execution behavior."""

import asyncio
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


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate", [False, True])
async def test_failed_or_interrupted_run_is_finalized(
    monkeypatch: pytest.MonkeyPatch,
    duplicate: bool,
) -> None:
    run_id = uuid4()
    run = SimpleNamespace(id=run_id, status="planning")
    session = SimpleNamespace(
        get=AsyncMock(return_value=run), rollback=AsyncMock(), commit=AsyncMock()
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
    await worker.process_command(
        KafkaMessage("commands", 0, 1, None, b"{}"),
        cast(async_sessionmaker[AsyncSession], factory),
    )
    repository.mark_failed.assert_awaited_once_with(test_run_id=run_id)
    session.commit.assert_awaited_once()
    assert execute.await_count == (0 if duplicate else 1)
