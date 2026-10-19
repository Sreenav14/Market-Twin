"""Focused no-policy runtime handoff, challenge and Skip regressions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.errors import HumanAssistanceSkipped
from markettwin_execution_orchestrator.browser.mcp_tools import connect_controlled_browser_tools
from markettwin_execution_orchestrator.persistence.human_action_lifecycle_repository import (
    HumanActionState,
)
from markettwin_execution_orchestrator.workflow import case_execution


@pytest.mark.parametrize(("markup", "challenge"), [
    ('<h1>Public</h1><a href="/login">Login</a>', False),
    ('<form><input type="email"><button>Subscribe</button></form>', False),
    ('<form><input type="email"><button>Continue</button></form>', True),
    ('<input autocomplete="username">', True),
    ('<input type="password">', True),
    ('<input autocomplete="one-time-code">', True),
    ('<div data-captcha>Challenge</div>', True),
    ('<h1>Sign in</h1><button>Continue with Google</button>', True),
    ('<h1>Product</h1><button>Continue with Google</button>', False),
])
async def test_challenge_is_observed_not_assumed_at_start(tmp_path, markup, challenge):
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(),
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", 5191),),
            network_policy="local_development", authenticated_session=True,
        )
        session = controller._sessions[handle.session_id]
        handler = AsyncMock()
        controller.bind_authentication_handler(handle, handler)
        handler.assert_not_awaited()
        await session.page.set_content(markup)
        assert await controller.has_authentication_challenge(handle) is challenge


async def test_durable_skip_is_acknowledged_not_abandoned(monkeypatch):
    lifecycle = MagicMock()
    lifecycle.create_login_request = AsyncMock(return_value=uuid4())
    lifecycle.state = AsyncMock(return_value=HumanActionState("skipped", "none", 1, None))
    lifecycle.acknowledge_skipped = AsyncMock()
    lifecycle.abandon = AsyncMock()
    monkeypatch.setattr(case_execution, "HumanActionLifecycleRepository", lambda _: lifecycle)
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    controller = MagicMock()
    for _ in range(2):  # a skipped journey cannot suppress another independent request
        with pytest.raises(HumanAssistanceSkipped):
            await case_execution.verify_or_request_login(
                request=SimpleNamespace(test_run_id=uuid4(), execution_id=uuid4()),
                controller=controller, handle=SimpleNamespace(session_id=uuid4()),
                policy=None, auth_scope=None, session=session, max_wait_seconds=1,
                continuation_verifier=AsyncMock(return_value=True),
            )
    assert lifecycle.create_login_request.await_count == 2
    assert lifecycle.acknowledge_skipped.await_count == 2
    lifecycle.abandon.assert_not_awaited()
    controller.verify_authenticated_role.assert_not_called()


async def test_skip_survives_actual_mcp_transport():
    async def browser_test_skip() -> dict[str, object]:
        """Synthetic skip endpoint for transport regression."""
        raise HumanAssistanceSkipped("Not tested—human assistance skipped.")

    async with connect_controlled_browser_tools([browser_test_skip]) as tools:
        with pytest.raises(HumanAssistanceSkipped):
            await tools[0].run_async(args={}, tool_context=None)


@pytest.mark.parametrize(
    "error", [RuntimeError("verification failed"), HumanAssistanceSkipped("skip")]
)
async def test_failed_runtime_handoff_revokes_any_provisional_session(monkeypatch, error):
    controller = MagicMock()
    monkeypatch.setattr(case_execution, "verify_or_request_login", AsyncMock(side_effect=error))
    with pytest.raises(type(error)):
        await case_execution.request_runtime_assistance(
            request=SimpleNamespace(test_run_id=uuid4(), runtime_target_id=uuid4()),
            controller=controller, handle=SimpleNamespace(session_id=uuid4()),
            session=MagicMock(),
        )
    assert controller.revoke_human_session_snapshots.call_count == 2
