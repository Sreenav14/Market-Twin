"""Job ownership must release its database lock, including on cancellation."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from markettwin_control_api.config import Settings
from markettwin_control_api.knowledge.processor import IngestionProcessor
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
