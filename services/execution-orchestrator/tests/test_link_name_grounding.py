"""Native accessible link names ground planning without changing frozen checks."""

from types import SimpleNamespace
from typing import cast

import pytest
from markettwin_execution_orchestrator.browser.assertions import evaluate_assertion
from markettwin_execution_orchestrator.browser.observations import build_observation
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession
from markettwin_shared.feature_plan import ExpectedAssertion, SemanticTarget
from playwright.async_api import async_playwright


@pytest.mark.parametrize("authenticated", [False, True])
async def test_native_names_match_exact_locators_and_leave_negative_assertions_unchanged(
    tmp_path, authenticated: bool,
) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        html = (
            '<meta charset="utf-8"><style>.external::after {content:" \\2197"}</style>'
            '<a class="external" href="https://fixture.test/docs?token=SYNTHETIC_CANARY">Docs</a>'
            '<a href="https://fixture.test/console">Console <span>↗</span></a>'
            '<a href="https://fixture.test/help">Help <span aria-hidden="true">↗</span></a>'
            '<a href="https://fixture.test/quoted">Docs: "API"</a>'
        )
        await page.route("**/*", lambda route: route.fulfill(content_type="text/html", body=html))
        await page.goto("https://fixture.test/")
        session = cast(JourneyBrowserSession, SimpleNamespace(
            page=page, timeout_ms=1000, authenticated_session=authenticated,
            capture_enabled=True, control_mode="agent", action_number=1,
            artifact_directory=tmp_path, context=SimpleNamespace(pages=[page]),
            event_buffer=SimpleNamespace(console_errors=[], page_errors=[], failed_requests=[]),
        ))
        observation = await build_observation(session)
        names = [item.name for item in observation.visible_elements if item.role == "link"]
        assert names == ["Docs ↗", "Console ↗", "Help", 'Docs: "API"']
        for name in names:
            assert await page.get_by_role("link", name=name, exact=True).count() == 1
        positive = ExpectedAssertion(
            assertion_id="docs_present", oracle="visible",
            target=SemanticTarget(role="link", name=names[0]), expected_value=True,
        )
        absent = ExpectedAssertion(
            assertion_id="absent_link", oracle="visible",
            target=SemanticTarget(role="link", name="Intentionally absent"), expected_value=False,
        )
        frozen_positive, frozen_absent = positive.model_dump_json(), absent.model_dump_json()
        assert (await evaluate_assertion(page, positive, timeout_ms=50)).status == "satisfied"
        assert (await evaluate_assertion(page, absent, timeout_ms=50)).status == "satisfied"
        # Existing shortened expectations are never silently changed at execution.
        shortened = positive.model_copy(update={"target": SemanticTarget(role="link", name="Docs")})
        assert (await evaluate_assertion(page, shortened, timeout_ms=50)).status == "not_satisfied"
        await page.locator("a").first.evaluate("element => element.remove()")
        assert (await evaluate_assertion(page, positive, timeout_ms=50)).status == "not_satisfied"
        assert positive.model_dump_json() == frozen_positive
        assert absent.model_dump_json() == frozen_absent
        if authenticated:
            assert observation.aria_snapshot == ""
            assert observation.accessibility_snapshot_path is None
            assert "SYNTHETIC_CANARY" not in str(observation.to_dict())
            assert not list(tmp_path.iterdir())
        await browser.close()
