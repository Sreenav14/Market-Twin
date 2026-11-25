"""A dead lifespan loop is observable before shutdown."""

import asyncio
import logging

import pytest
from markettwin_control_api.main import report_background_task_exit


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_unexpected_background_exit_is_reported_immediately(caplog, fails):
    async def loop():
        if fails:
            raise RuntimeError("loop failed")
    with caplog.at_level(logging.ERROR):
        task = asyncio.create_task(loop(), name="test-census")
        task.add_done_callback(report_background_task_exit)
        await asyncio.gather(task, return_exceptions=True)
    assert "Background task test-census exited unexpectedly" in caplog.text


@pytest.mark.asyncio
async def test_shutdown_cancellation_is_not_an_unexpected_failure(caplog):
    task = asyncio.create_task(asyncio.sleep(10), name="test-census")
    task.add_done_callback(report_background_task_exit)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert "exited unexpectedly" not in caplog.text
