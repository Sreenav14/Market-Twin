"""Probe clicks stay in the recorded form and recheck effective submit method."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserActionBlockedError


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get", "post"])
async def test_probe_uses_form_scope_and_checks_button_override(monkeypatch, method):
    target = SimpleNamespace(count=AsyncMock(return_value=1), click=AsyncMock(),
                             get_attribute=AsyncMock(return_value=None),
                             evaluate=AsyncMock(return_value={"method": method, "action": "https://example.test/search"}))
    form = SimpleNamespace(count=AsyncMock(return_value=1), get_by_role=Mock(return_value=target))
    forms = SimpleNamespace(nth=Mock(return_value=form))
    session = SimpleNamespace(page=SimpleNamespace(locator=Mock(return_value=forms)),
                               next_action_number=Mock(), keyboard_only=False, timeout_ms=1000)
    controller = BrowserController()
    monkeypatch.setattr(controller, "_get_session", lambda **kwargs: session)
    @asynccontextmanager
    async def control(_session):
        yield
    monkeypatch.setattr(controller, "_agent_control_action", control)
    for name in ("_click_intent", "_require_keyboard_focus", "_track_pointer", "_authentication_checkpoint", "_navigation_url"):
        monkeypatch.setattr(controller, name, AsyncMock(return_value=None))
    if method == "get":
        await controller.click(session_id=uuid4(), role="button", name="Search", form_index=1, observe=False)
        target.click.assert_awaited_once()
    else:
        with pytest.raises(BrowserActionBlockedError, match="requires GET"):
            await controller.click(session_id=uuid4(), role="button", name="Search", form_index=1, observe=False)
        target.click.assert_not_awaited()
    forms.nth.assert_called_once_with(1)
    form.get_by_role.assert_any_call("button", name="Search", exact=True)
