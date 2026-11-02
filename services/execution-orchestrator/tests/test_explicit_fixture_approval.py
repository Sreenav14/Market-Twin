"""Exact loopback fixture eligibility still requires a one-time approval receipt."""

from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserActionBlockedError
from markettwin_execution_orchestrator.browser.sensitive_action_policy import classify_click_action
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession
from markettwin_shared.action_approval import SensitiveActionRule
from playwright.async_api import async_playwright


@pytest.mark.parametrize(
    "name,kind", [("Continue to next step", None), ("Check contact address", "submit")],
)
def test_explicit_fixture_rule_only_makes_opaque_action_approvable(name, kind):
    with pytest.raises(BrowserActionBlockedError):
        classify_click_action(role="button", name=name, label=None, text=None, element_type=kind)
    intent = classify_click_action(role="button", name=name, label=None, text=None,
                                   element_type=kind, explicit_fixture_approval=True)
    assert intent is not None
    assert intent.category == "form_submit"


@pytest.mark.parametrize("name", ["Delete", "Send invitation", "Checkout", "Grant access"])
def test_fixture_eligibility_never_overrides_hard_denies(name):
    with pytest.raises(BrowserActionBlockedError):
        classify_click_action(role="button", name=name, label=None, text=None,
                              explicit_fixture_approval=True)


@pytest.mark.parametrize("scenario", ["exact", "no_rule", "public_policy", "public_origin",
                                      "wrong_scope", "different_target", "sensitive_form"])
async def test_controller_fixture_eligibility_is_exact_and_never_dispatches_without_approval(
    tmp_path, scenario,
):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context()
        page = await context.new_page()
        hostname = "example.test" if scenario == "public_origin" else "127.0.0.1"
        scheme = "https" if scenario == "public_origin" else "http"
        html = (
            '<form aria-label="Fixture">'
            + ('<input type="password" name="password">' if scenario == "sensitive_form" else '')
            + '<button type="button" onclick="document.title=\'clicked\'">Continue</button>'
            '<button type="button">Other control</button></form>'
        )
        await page.route("**/*", lambda route: route.fulfill(content_type="text/html", body=html))
        await page.goto(f"{scheme}://{hostname}/")
        rule = SensitiveActionRule(category="form_submit", role="button", name="Continue",
                                   scope_role="form" if scenario == "wrong_scope" else None,
                                   scope_name="Other" if scenario == "wrong_scope" else None,
                                   resource_reference="existing-fixture",
                                   test_data_reset_confirmed=True)
        session = JourneyBrowserSession(
            session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4(),
            allowed_origins=(AllowedOrigin(scheme, hostname),),
            network_policy="public_only" if scenario == "public_policy" else "local_development",
            timeout_ms=500, browser=browser, context=context, page=page,
            artifact_directory=tmp_path, state="open",
            fixture_action_rules=() if scenario == "no_rule" else (rule,),
        )
        controller = BrowserController(artifact_root=tmp_path)
        controller._sessions[session.session_id] = session
        locator = page.get_by_role("button", name="Other control" if scenario == "different_target"
                                   else "Continue", exact=True)
        arguments = dict(locator=locator, role="button", name="Continue", label=None, text=None,
                         scope_role=None, scope_name=None, session=session)
        if scenario == "exact":
            intent = await controller._click_intent(**arguments)
            assert intent is not None and intent.category == "form_submit"
            with pytest.raises(BrowserActionBlockedError, match="one-time approval"):
                await controller.click(
                    session_id=session.session_id, role="button", name="Continue",
                )
        else:
            with pytest.raises(BrowserActionBlockedError):
                await controller._click_intent(**arguments)
        assert await page.title() != "clicked"
        await browser.close()
