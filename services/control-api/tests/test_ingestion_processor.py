"""Job ownership must release its database lock, including on cancellation."""

import asyncio
from io import BytesIO
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from markettwin_control_api.config import Settings
from markettwin_control_api.knowledge import processor as processor_module
from markettwin_control_api.knowledge.client import KnowledgeWorkerError
from markettwin_control_api.knowledge.processor import IngestionProcessor
from markettwin_shared.knowledge_preview import KnowledgePreviewResponse
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine


@pytest.mark.parametrize("cancelled", [False, True])
async def test_dispatch_releases_ownership_on_completion_or_cancellation(
    monkeypatch: pytest.MonkeyPatch, cancelled: bool,
) -> None:
    connection = AsyncMock(spec=AsyncConnection)
    connection.scalar.return_value = True
    context = AsyncMock()
    context.__aenter__.return_value = connection
    engine = MagicMock(spec=AsyncEngine)
    engine.connect.return_value = context
    processor = IngestionProcessor(cast(AsyncEngine, engine), Settings())
    process = AsyncMock(side_effect=asyncio.CancelledError() if cancelled else None)
    monkeypatch.setattr(processor, "_process", process)
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            await processor.process_entry(uuid4(), uuid4())
    else:
        assert await processor.process_entry(uuid4(), uuid4())
    connection.rollback.assert_awaited_once()
    assert "pg_advisory_unlock" in str(connection.execute.await_args.args[0])
    assert connection.commit.await_count == 2


async def test_another_owner_prevents_duplicate_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = AsyncMock(spec=AsyncConnection)
    connection.scalar.return_value = False
    context = AsyncMock()
    context.__aenter__.return_value = connection
    engine = MagicMock(spec=AsyncEngine)
    engine.connect.return_value = context
    processor = IngestionProcessor(cast(AsyncEngine, engine), Settings())
    process = AsyncMock()
    monkeypatch.setattr(processor, "_process", process)
    assert not await processor.process_entry(uuid4(), uuid4())
    process.assert_not_awaited()
    connection.execute.assert_not_awaited()


@pytest.mark.parametrize("status", [502, 503, 504])
async def test_transient_failure_recovers_automatically(
    monkeypatch: pytest.MonkeyPatch, status: int,
) -> None:
    result = MagicMock(spec=KnowledgePreviewResponse)
    payloads: list[bytes] = []

    async def preview(**kwargs: object) -> KnowledgePreviewResponse:
        stream = cast(BytesIO, kwargs["stream"])
        payloads.append(stream.read())
        if len(payloads) == 1:
            raise KnowledgeWorkerError(status, "Temporarily unavailable")
        return cast(KnowledgePreviewResponse, result)

    client = MagicMock()
    client.preview = AsyncMock(side_effect=preview)
    def client_factory(settings: Settings) -> MagicMock:
        return client

    monkeypatch.setattr(processor_module, "KnowledgeWorkerClient", client_factory)
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    response = await processor._preview_with_retry(  # pyright: ignore[reportPrivateUsage]
        filename="source.txt", content_type="text/plain", stream=BytesIO(b"original source"),
    )
    assert response is result
    assert payloads == [b"original source", b"original source"]
    sleep.assert_awaited_once_with(2)


@pytest.mark.parametrize("status,message,attempts", [
    (415, "Unsupported source format.", 1),
    (422, "The source could not be read.", 1),
    (502, "Knowledge generation reached its output limit.", 1),
    (503, "Temporarily unavailable", 3),
    (504, "Timed out", 3),
    (502, "Model temporarily failed", 3),
])
async def test_terminal_errors_and_retry_exhaustion(
    monkeypatch: pytest.MonkeyPatch, status: int, message: str, attempts: int,
) -> None:
    client = MagicMock()
    client.preview = AsyncMock(side_effect=KnowledgeWorkerError(status, message))
    def client_factory(settings: Settings) -> MagicMock:
        return client

    monkeypatch.setattr(processor_module, "KnowledgeWorkerClient", client_factory)
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    with pytest.raises(KnowledgeWorkerError, match=message):
        await processor._preview_with_retry(  # pyright: ignore[reportPrivateUsage]
            filename="source.txt", content_type="text/plain", stream=BytesIO(b"source"),
        )
    assert client.preview.await_count == attempts
    assert [call.args[0] for call in sleep.await_args_list] == ([2, 4] if attempts == 3 else [])
