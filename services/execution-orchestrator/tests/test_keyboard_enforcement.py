from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import Mock
from contextlib import nullcontext

import pytest

from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserActionError


@pytest.mark.asyncio
async def test_keyboard_persona_requires_real_focus_and_never_moves_mouse():
    session = SimpleNamespace(keyboard_only=True)
    locator = SimpleNamespace(evaluate=AsyncMock(return_value=False))
    with pytest.raises(BrowserActionError, match="Use Tab"):
        await BrowserController._require_keyboard_focus(session, locator)
    locator.evaluate.return_value = True
    await BrowserController._require_keyboard_focus(session, locator)
    # No page/mouse exists: the keyboard path must return before touching either.
    await BrowserController._track_pointer(session, locator)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["fill", "select", "set_checked"])
async def test_keyboard_operations_do_not_dispatch_mouse_or_dom_shortcuts(monkeypatch, action):
    from markettwin_execution_orchestrator.browser import controller as module
    locator = SimpleNamespace(get_attribute=AsyncMock(
        side_effect=lambda key: "checkbox" if key == "type" and action == "set_checked" else None),
        evaluate=AsyncMock(side_effect=lambda script, *args: 0 if "findIndex" in script else True),
        fill=AsyncMock(), select_option=AsyncMock(), set_checked=AsyncMock(),
        input_value=AsyncMock(return_value="demo"), is_checked=AsyncMock(return_value=False))
    root = SimpleNamespace(get_by_label=Mock(return_value=locator))
    session = SimpleNamespace(keyboard_only=True, allowed_origins=(), network_policy="public_only",
        timeout_ms=1000, next_action_number=Mock(),
        page=SimpleNamespace(url="https://app.test/", keyboard=SimpleNamespace(
            press=AsyncMock(), insert_text=AsyncMock())))
    controller = SimpleNamespace(_get_session=lambda **kw: session,
        _agent_control_action=lambda _: nullcontext(),
        _require_keyboard_focus=BrowserController._require_keyboard_focus,
        _track_pointer=BrowserController._track_pointer)
    monkeypatch.setattr(module, "validate_target_url", Mock())
    monkeypatch.setattr(module, "scoped_root", AsyncMock(return_value=root))
    monkeypatch.setattr(module, "require_unique", AsyncMock())
    monkeypatch.setattr(module, "capture_screenshot", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "build_observation", AsyncMock(return_value=object()))
    kwargs = {"session_id": None, "label": "Show details"}
    kwargs.update(checked=True) if action == "set_checked" else kwargs.update(value="demo")
    await getattr(BrowserController, action)(controller, **kwargs)
    locator.fill.assert_not_awaited()
    locator.select_option.assert_not_awaited()
    locator.set_checked.assert_not_awaited()
    assert session.page.keyboard.press.await_count >= 1
