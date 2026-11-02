"""Case deadlines remain active for empty pause probes and bound real pauses."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.workflow.cooperative_pause import (
    cooperative_pause_case_deadline,
    cooperative_pause_checkpoint,
)


@pytest.mark.asyncio
async def test_blocked_no_pause_probe_does_not_extend_case_deadline() -> None:
    probe_started = asyncio.Event()

    async def blocked_probe(*_args: object, **_kwargs: object) -> None:
        probe_started.set()
        await asyncio.Event().wait()

    session = SimpleNamespace(scalar=AsyncMock(side_effect=blocked_probe))
    request = SimpleNamespace(
        test_run_id=uuid4(), journey_id=uuid4(), execution_id=uuid4(),
    )
    handle = BrowserSessionHandle(uuid4(), request.execution_id, request.journey_id)
    started = time.monotonic()

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05) as case_timeout:
            original_deadline = case_timeout.when()
            await cooperative_pause_checkpoint(
                request=request,
                controller=MagicMock(),
                handle=handle,
                session=session,
                case_timeout=case_timeout,
            )

    assert probe_started.is_set()
    assert session.scalar.await_count == 1
    assert case_timeout.when() == original_deadline
    assert time.monotonic() - started < 2


@pytest.mark.asyncio
async def test_confirmed_pause_allowance_is_bounded() -> None:
    started = time.monotonic()

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(2) as case_timeout:
            async with cooperative_pause_case_deadline(case_timeout, allowance_seconds=0.05):
                await asyncio.Event().wait()

    assert time.monotonic() - started < 2
