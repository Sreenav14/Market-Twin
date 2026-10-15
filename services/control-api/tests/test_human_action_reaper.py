"""Lifecycle tests for periodic HITL expiry."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from markettwin_control_api.services import human_action_reaper
from markettwin_control_api.services.human_action_reaper import run_human_action_reaper


@pytest.mark.asyncio
async def test_reaper_runs_bounded_transactional_batches_and_cancels_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = asyncio.Event()
    calls: list[int] = []
    approval_calls: list[int] = []
    exits = {"session": 0, "transaction": 0}

    class FakeSession:
        @asynccontextmanager
        async def begin(self) -> AsyncIterator[None]:
            try:
                yield
            finally:
                exits["transaction"] += 1

    @asynccontextmanager
    async def make_session() -> AsyncIterator[FakeSession]:
        try:
            yield FakeSession()
        finally:
            exits["session"] += 1

    class FakeRepository:
        def __init__(self, _: Any) -> None:
            pass

        async def expire_due(self, *, limit: int) -> int:
            calls.append(limit)
            called.set()
            return 0

    class FakeApprovalRepository:
        def __init__(self, _: Any) -> None:
            pass

        async def expire_due(self, *, limit: int) -> int:
            approval_calls.append(limit)
            return 0

    monkeypatch.setattr(human_action_reaper, "HumanActionRepository", FakeRepository)
    monkeypatch.setattr(
        human_action_reaper, "ActionApprovalRepository", FakeApprovalRepository
    )
    task = asyncio.create_task(
        run_human_action_reaper(make_session, interval_seconds=30, batch_size=17)
    )
    await asyncio.wait_for(called.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert calls == [17]
    assert approval_calls == [17]
    assert exits == {"session": 1, "transaction": 1}


@pytest.mark.parametrize(("interval", "batch"), [(0, 1), (-1, 1), (1, 0)])
@pytest.mark.asyncio
async def test_reaper_rejects_invalid_bounds(interval: float, batch: int) -> None:
    with pytest.raises(ValueError):
        await run_human_action_reaper(lambda: None, interval_seconds=interval, batch_size=batch)
