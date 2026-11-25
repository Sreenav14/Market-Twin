"""Speed S0 (doc 18 section 7.2): the observation-tax contract.

observe=False performs the action under the same agent-control lock and
checkpoints but returns a bare result — no screenshot capture, no
observation build, no artifacts. capture_evidence_screenshot returns the
image path alone. Default behaviour (observe=True) is unchanged.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import controller as controller_module
from markettwin_execution_orchestrator.browser.controller import BrowserController


def _fake_session():
    page = MagicMock()
    page.url = "about:blank"
    page.wait_for_timeout = AsyncMock()
    return SimpleNamespace(
        session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4(),
        page=page, lock=asyncio.Lock(), control_mode="agent", state="open",
        offsite=None, keyboard_only=False,
        is_auth_only_url=lambda url: False,
        next_action_number=lambda: 1,
    )


def _controller_with(monkeypatch, tmp_path):
    controller = BrowserController()
    session = _fake_session()
    controller._sessions[session.session_id] = session
    capture = AsyncMock(return_value=tmp_path / "shot.png")
    build = AsyncMock(return_value=SimpleNamespace(screenshot_path=None))
    monkeypatch.setattr(controller_module, "capture_screenshot", capture)
    monkeypatch.setattr(controller_module, "build_observation", build)
    return controller, session, capture, build


@pytest.mark.asyncio
async def test_wait_observe_false_skips_capture_and_observation(monkeypatch, tmp_path):
    """T-O1: observe=True captures + builds exactly as before; observe=False
    still performs the wait under the lock but captures and builds nothing
    and returns a result with observation=None."""
    controller, session, capture, build = _controller_with(monkeypatch, tmp_path)

    observed = await controller.wait(session_id=session.session_id, milliseconds=1)
    assert observed.observation is not None
    assert capture.await_count == 1 and build.await_count == 1

    bare = await controller.wait(
        session_id=session.session_id, milliseconds=1, observe=False)
    assert bare.action == "wait"
    assert bare.observation is None
    assert capture.await_count == 1 and build.await_count == 1
    assert session.page.wait_for_timeout.await_count == 2


@pytest.mark.asyncio
async def test_capture_evidence_screenshot_returns_path_without_observation(
        monkeypatch, tmp_path):
    """T-O2: the capture-only method returns the screenshot path inside the
    session's evidence flow with build_observation provably uncalled, and
    an empty string when capture is disabled."""
    controller, session, capture, build = _controller_with(monkeypatch, tmp_path)

    path = await controller.capture_evidence_screenshot(session_id=session.session_id)
    assert path == str(tmp_path / "shot.png")
    assert capture.await_count == 1
    build.assert_not_awaited()

    capture.return_value = None
    assert await controller.capture_evidence_screenshot(
        session_id=session.session_id) == ""
