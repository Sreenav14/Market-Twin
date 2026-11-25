from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from markettwin_execution_orchestrator.slop import visual_review
from markettwin_execution_orchestrator.browser.controller import BrowserController


@pytest.mark.asyncio
async def test_visual_boundary_and_preference_findings_are_excluded(monkeypatch, tmp_path):
    path = tmp_path / "frame.png"
    path.write_bytes(b"scripted image")
    monkeypatch.setattr(visual_review.ask, "_model_json", AsyncMock(return_value={"findings": [
        {"kind": "screenshot_boundary", "detail": "Table continues below screenshot"},
        {"kind": "preference", "detail": "Headline wraps across seven lines"},
        {"kind": "overlap", "detail": "Menu obscures button inside the card"},
        {"detail": "Untyped unsupported observation"}]}))
    findings = await visual_review.review_screenshots([
        {"viewport": "mobile320", "screenshot_path": str(path)}])
    assert [finding["detail"] for finding in findings] == ["Menu obscures button inside the card"]


@pytest.mark.asyncio
async def test_disclosure_uses_browser_accessibility_name():
    control = SimpleNamespace(is_visible=AsyncMock(return_value=True),
        is_enabled=AsyncMock(return_value=True),
        aria_snapshot=AsyncMock(return_value='- button "Open menu" [expanded=false]'))
    controls = SimpleNamespace(count=AsyncMock(return_value=1), nth=Mock(return_value=control))
    session = SimpleNamespace(timeout_ms=1000,
        page=SimpleNamespace(locator=Mock(return_value=controls)))
    controller = SimpleNamespace(_get_session=lambda **kw: session,
        _agent_control_action=lambda _: nullcontext())
    assert await BrowserController.ui_state_targets(controller, session_id=None) == [
        {"role": "button", "name": "Open menu"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
async def test_sitemap_uses_and_closes_a_separate_browser_context(failed):
    watched = SimpleNamespace(execution_id="execution", journey_id="journey")
    sitemap = SimpleNamespace(page=SimpleNamespace(
        evaluate=AsyncMock(return_value=["https://app.test/unlinked"]),
    ))
    controller = SimpleNamespace(
        _get_session=lambda *, session_id: watched if session_id == "watched" else sitemap,
        _create_sibling_session=AsyncMock(return_value=SimpleNamespace(session_id="discovery")),
        _agent_control_action=lambda _: nullcontext(),
        navigate=AsyncMock(side_effect=TimeoutError if failed else None),
        close_session=AsyncMock(),
    )
    url = "https://app.test/sitemap.xml"
    if failed:
        with pytest.raises(TimeoutError):
            await BrowserController.sitemap_locations(controller, session_id="watched", url=url)
    else:
        assert await BrowserController.sitemap_locations(controller, session_id="watched", url=url) == [
            "https://app.test/unlinked",
        ]
    controller.navigate.assert_awaited_once_with(session_id="discovery", url=url, observe=False)
    controller.close_session.assert_awaited_once_with(session_id="discovery")
