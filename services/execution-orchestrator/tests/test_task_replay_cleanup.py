"""Partially established prerequisites still own cleanup and browser teardown."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from markettwin_execution_orchestrator.harvest.task_verify import TaskReplayExecutor


@pytest.mark.asyncio
async def test_cleanup_runs_after_prerequisite_failure():
    handle = SimpleNamespace(session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4())
    controller = SimpleNamespace(create_session=AsyncMock(return_value=handle), close_session=AsyncMock())
    executor = TaskReplayExecutor(
        controller, app_map=SimpleNamespace(base_url="https://example.com/"), profile={},
    )
    executor._establish_prerequisites = AsyncMock(return_value="prerequisite_unavailable")
    executor._run_cleanup = AsyncMock(return_value=True)
    outcome = await executor.run_once(definition={
        "case_id": "cleanup_case", "feature_key": "cleanup", "title": "Cleanup",
        "kind": "happy_path", "steps": [{"action": "navigate", "url": "https://example.com/"}],
        "expected": [{"assertion_id": "url", "oracle": "url", "expected_value": "https://example.com/"}],
        "task": {"inputs": []},
    })
    assert outcome.ok is False
    executor._run_cleanup.assert_awaited_once()
    controller.close_session.assert_awaited_once_with(session_id=handle.session_id)
