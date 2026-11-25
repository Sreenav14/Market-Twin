"""Verified-resume re-entry (ORC2-03): a worker that picks the pause
up again when the lease is already verifying must complete the
handoff. Before the fix the verified branch wrote run.status with
``run`` never bound on this path - NameError, and the verified
handoff was rolled back instead of completed."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.workflow import cooperative_pause
from markettwin_execution_orchestrator.workflow.cooperative_pause import (
    _continue_cooperative_pause,
)


class _FakeLifecycle:
    instance = None

    def __init__(self, session):
        self.finished = []
        self.abandoned = []
        _FakeLifecycle.instance = self

    async def state(self, *, request_id):
        return SimpleNamespace(
            request_status="leased", control_mode="verifying",
            control_generation=3,
        )

    async def finish_verification(self, *, request_id, expected_generation, verified):
        self.finished.append((request_id, expected_generation, verified))

    async def abandon(self, *, request_id):
        self.abandoned.append(request_id)


class _FakeSession:
    def __init__(self, *, pause, run, actor_id):
        self._pause = pause
        self._run = run
        self._actor_id = actor_id
        self.commits = 0
        self.rollbacks = 0

    async def refresh(self, obj, **kwargs):
        return None

    async def scalar(self, statement, *args, **kwargs):
        return self._actor_id

    async def get(self, model, key, **kwargs):
        if getattr(model, "__name__", "") == "TestRun":
            return self._run
        return self._pause

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _FakeController:
    def __init__(self):
        self.ended = []

    async def human_continuation_ready(self, handle):
        return True

    async def end_human_control(self, **kwargs):
        self.ended.append(kwargs)


@pytest.mark.asyncio
async def test_verified_resume_completes_on_reentry(monkeypatch):
    async def authorized(session, pause, user_id=None):
        return True

    monkeypatch.setattr(cooperative_pause, "_authorized", authorized)
    monkeypatch.setattr(
        cooperative_pause, "HumanActionLifecycleRepository", _FakeLifecycle
    )
    run = SimpleNamespace(status="awaiting_human")
    pause = SimpleNamespace(
        id=uuid4(), status="paused",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        human_request_id=uuid4(), generation=1,
        requested_by_user_id=uuid4(), resume_requested_by_user_id=None,
    )
    session = _FakeSession(pause=pause, run=run, actor_id=uuid4())
    controller = _FakeController()
    request = SimpleNamespace(
        test_run_id=uuid4(), execution_id=uuid4(), journey_id=uuid4(),
    )
    handle = BrowserSessionHandle(uuid4(), request.execution_id, request.journey_id)
    await _continue_cooperative_pause(
        pause=pause, request=request, controller=controller, handle=handle,
        session=session, policy=None,
    )
    assert _FakeLifecycle.instance.finished == [
        (pause.human_request_id, 3, True)
    ]
    assert run.status == "running"
    assert pause.status == "resumed"
    assert len(controller.ended) == 1
    assert controller.ended[0]["verified"] is True
