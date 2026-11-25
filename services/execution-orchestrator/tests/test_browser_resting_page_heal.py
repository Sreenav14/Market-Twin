"""Controller-level tests for the resting-page self-heal (MT-000237 lane fix).

The pre-flight in BrowserController._agent_control_action validates the
page a session is resting on before every agent action. A lane whose page
came to rest on a browser error page (chrome-error://) used to fail every
later claim with policy_code "target_url", because the refusal also
blocked the navigation that would have rescued it. These tests pin the
heal: a resting page that is not a public URL at all is parked on
about:blank and the action proceeds, while a public off-origin resting
page still refuses exactly as before.

Fake pages are used throughout: the component under test is the
controller's own pre-flight logic, and the real validation functions
(validate_browsing_url / validate_target_url) run unpatched except where
a test counts their calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from markettwin_execution_orchestrator.browser import controller as controller_module
from markettwin_execution_orchestrator.browser.contracts import AllowedOrigin
from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.errors import (
    BrowserPolicyError,
    TargetUrlValidationError,
)
from markettwin_execution_orchestrator.browser.offsite import (
    OffsiteBrowsing,
    validate_browsing_url,
)
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession

ALLOWED = (AllowedOrigin("https", "www.target.test", None),)


class FakePage:
    """Minimal Playwright Page stand-in: a current URL and a goto that lands on it."""

    def __init__(self, url: str, *, goto_error: Exception | None = None) -> None:
        self.url = url
        self.goto_calls: list[str] = []
        self._goto_error = goto_error

    async def goto(self, url: str, **kwargs: object) -> None:
        self.goto_calls.append(url)
        if self._goto_error is not None:
            raise self._goto_error
        self.url = url


def _session(tmp_path: Path, page: FakePage) -> JourneyBrowserSession:
    async def _review(source: str, destination: str, goal: str) -> tuple[str, str]:
        return "continue", "unit test"

    async def _save(
        kind: str, payload: dict[str, object], journey_id: UUID, execution_id: UUID,
    ) -> None:
        return None

    return JourneyBrowserSession(
        session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4(),
        allowed_origins=ALLOWED,
        network_policy="public_only",
        timeout_ms=500,
        browser=cast(Any, None), context=cast(Any, None), page=cast(Any, page),
        artifact_directory=tmp_path, state="open",
        offsite=OffsiteBrowsing(goal="unit test", review=_review, save=_save),
    )


async def test_error_page_rest_heals_and_action_proceeds(tmp_path: Path) -> None:
    page = FakePage("chrome-error://chromewebdata/")
    session = _session(tmp_path, page)
    controller = BrowserController(artifact_root=tmp_path)

    ran = False
    async with controller._agent_control_action(session):
        ran = True
        # Destination validation is untouched by the heal: a non-public
        # destination still refuses inside the action itself.
        with pytest.raises(TargetUrlValidationError):
            validate_browsing_url(session, "chrome-error://chromewebdata/")

    assert ran
    assert page.goto_calls == ["about:blank"]
    assert page.url == "about:blank"


async def test_off_origin_public_rest_still_refuses_without_reset(tmp_path: Path) -> None:
    page = FakePage("https://other.test/page")
    session = _session(tmp_path, page)
    controller = BrowserController(artifact_root=tmp_path)

    with pytest.raises(BrowserPolicyError) as excinfo:
        async with controller._agent_control_action(session):
            pass

    # The plain policy_refused class, not the target_url class, and the
    # heal must not have been attempted.
    assert not isinstance(excinfo.value, TargetUrlValidationError)
    assert page.goto_calls == []
    assert page.url == "https://other.test/page"


async def test_about_blank_rest_skips_validation_and_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = FakePage("about:blank")
    session = _session(tmp_path, page)
    controller = BrowserController(artifact_root=tmp_path)

    calls: list[str] = []
    real_validate = controller_module.validate_browsing_url

    def counting_validate(sess: JourneyBrowserSession, url: str) -> Any:
        calls.append(url)
        return real_validate(sess, url)

    monkeypatch.setattr(controller_module, "validate_browsing_url", counting_validate)

    ran = False
    async with controller._agent_control_action(session):
        ran = True

    assert ran
    assert calls == []
    assert page.goto_calls == []


async def test_failed_reset_reraises_original_target_url_error(tmp_path: Path) -> None:
    page = FakePage(
        "chrome-error://chromewebdata/", goto_error=RuntimeError("page is gone"),
    )
    session = _session(tmp_path, page)
    controller = BrowserController(artifact_root=tmp_path)

    ran = False
    with pytest.raises(TargetUrlValidationError):
        async with controller._agent_control_action(session):
            ran = True

    assert not ran
    assert page.goto_calls == ["about:blank"]
    assert page.url == "chrome-error://chromewebdata/"
