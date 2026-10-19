"""Browser metadata and form choices honor the same credential boundary as fills."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser.contracts import AllowedOrigin
from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.errors import (
    BrowserActionBlockedError,
    BrowserPolicyError,
)
from playwright.async_api import Error as PlaywrightError


@pytest.mark.parametrize("url,allowed", [
    ("https://example.test/login", True),
    ("https://www.google.com/recaptcha/api.js", False),
])
def test_popup_without_a_frame_still_requires_target_authority(url, allowed):
    class PopupRequest:
        def is_navigation_request(self):
            return True

        @property
        def frame(self):
            raise PlaywrightError("Frame for this navigation request is not available yet")

    request = PopupRequest()
    request.url = url
    session = SimpleNamespace(
        allowed_origins=(AllowedOrigin("https", "example.test"),), network_policy="public_only",
    )
    controller = BrowserController()
    if allowed:
        assert controller._validated_request_url(session, request).hostname == "example.test"
    else:
        with pytest.raises(BrowserPolicyError):
            controller._validated_request_url(session, request)


def test_failed_request_records_only_origin() -> None:
    buffer = SimpleNamespace(record_failed_request=Mock())
    session = SimpleNamespace(
        capture_enabled=True, control_mode="agent", authenticated_session=False,
        event_buffer=buffer,
    )
    request = SimpleNamespace(
        url="https://user:password@example.test/private-token?token=secret#credential",
        method="GET", resource_type="fetch", failure="error included private-token",
    )
    BrowserController._on_request_failed(session, request)
    record = buffer.record_failed_request.call_args.args[0]
    assert record.url == "https://example.test"
    assert record.error_text == "Network request failed"


@pytest.mark.parametrize("label,autocomplete", [
    ("Credit card", "cc-number"), ("Code", "one-time-code"),
])
async def test_sensitive_select_is_blocked_before_mutation(monkeypatch, label, autocomplete):
    locator = SimpleNamespace(
        count=AsyncMock(return_value=1), select_option=AsyncMock(),
        get_attribute=AsyncMock(side_effect=[None, autocomplete]),
    )
    session = SimpleNamespace(
        page=SimpleNamespace(get_by_label=Mock(return_value=locator)),
        next_action_number=Mock(),
    )
    controller = BrowserController()
    monkeypatch.setattr(controller, "_get_session", lambda **_: session)

    @asynccontextmanager
    async def control(_):
        yield

    monkeypatch.setattr(controller, "_agent_control_action", control)
    with pytest.raises(BrowserActionBlockedError):
        await controller.select(session_id=uuid4(), label=label, value="secret")
    locator.select_option.assert_not_awaited()
    session.next_action_number.assert_not_called()
