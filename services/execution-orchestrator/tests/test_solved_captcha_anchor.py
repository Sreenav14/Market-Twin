"""Synthetic intercepted widget UI; no request reaches a CAPTCHA provider."""

from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.browser.auth_verifier import (
    AuthVerificationPolicy,
    has_active_sensitive_challenge,
    verify_authenticated_role,
)
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession
from playwright.async_api import Locator, Route, async_playwright


@pytest.mark.parametrize(("widget", "extra", "marker", "challenge", "verified"), [
    ('<div role="checkbox" aria-checked="true">Verified</div>', "", "Signed in as user",
     False, True),
    ('<div role="checkbox" aria-checked="false">Verify</div>', "", "Signed in as user",
     True, False),
    ('<div role="checkbox" aria-checked="true">Verified</div>', '<input type="password">',
     "Signed in as user", True, False),
    ('<div role="checkbox" aria-checked="true">Verified</div>', "", "Sign in required",
     False, False),
    ('<div role="checkbox" aria-checked="true">Verified</div>',
     '<iframe title="reCAPTCHA challenge" src="https://www.google.com/recaptcha/api2/bframe"></iframe>',
     "Signed in as user", True, False),
])
async def test_persistent_anchor_requires_checked_ui_and_site_identity(
    widget: str, extra: str, marker: str, challenge: bool, verified: bool,
) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context(service_workers="block")
            requests: list[str] = []

            async def respond(route: Route) -> None:
                # Entire context is intercepted; provider hosts never reach DNS or sockets.
                requests.append(route.request.resource_type)
                if route.request.url.startswith("https://target.invalid/"):
                    body = (
                        f'<p id="identity">{marker}</p>{extra}'
                        '<iframe title="reCAPTCHA" '
                        'src="https://www.google.com/recaptcha/api2/anchor?secret=PRIVATE"></iframe>'
                    )
                else:
                    body = widget
                await route.fulfill(content_type="text/html", body=body)

            await context.route("**/*", respond)
            page = await context.new_page()
            page.set_default_timeout(1500)
            await page.goto("https://target.invalid/dashboard")
            assert "document" in requests
            assert await has_active_sensitive_challenge(page) is challenge
            policy = AuthVerificationPolicy(
                origin="https://target.invalid", marker_selector="#identity",
                expected_marker="Signed in as user", role="user", account_reference="fixture-user",
            )
            principal = await verify_authenticated_role(
                page=page, policy=policy, allowed_origins=frozenset({"https://target.invalid"}),
            )
            assert (principal is not None) is verified
            controller = BrowserController()
            session = cast(JourneyBrowserSession, SimpleNamespace(
                page=page, session_id=uuid4(), is_auth_only_url=lambda _: False,
            ))
            assert await controller._has_authentication_challenge(session) is challenge
        finally:
            await browser.close()


@pytest.mark.parametrize("transition", ["redirect", "navigate_during_check", "replace_document"])
async def test_stale_anchor_attribute_cannot_clear_a_changed_frame(
    transition: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context(service_workers="block")
            anchor = "https://www.google.com/recaptcha/api2/anchor"
            challenge = "https://www.google.com/recaptcha/api2/bframe"

            async def respond(route: Route) -> None:
                if route.request.url.startswith("https://target.invalid/"):
                    body = f'<iframe title="reCAPTCHA" src="{anchor}"></iframe>'
                elif transition == "redirect" and route.request.url == anchor:
                    await route.fulfill(status=302, headers={"location": challenge})
                    return
                else:
                    body = '<div role="checkbox" aria-checked="true">Checked</div>'
                await route.fulfill(content_type="text/html", body=body)

            await context.route("**/*", respond)
            page = await context.new_page()
            page.set_default_timeout(1500)
            await page.goto("https://target.invalid/")
            if transition != "redirect":
                original = Locator.get_attribute
                changed = False

                async def change_during_read(
                    locator: Locator, name: str, **options: float | None,
                ) -> str | None:
                    nonlocal changed
                    if name == "aria-checked" and not changed:
                        changed = True
                        frame = page.frames[1]
                        if transition == "replace_document":
                            # Same anchor URL, but a different document than the one verified.
                            await frame.goto(anchor)
                        else:
                            await frame.goto(challenge)
                    return await original(locator, name, timeout=options.get("timeout"))

                monkeypatch.setattr(Locator, "get_attribute", change_during_read)
            assert await page.locator("iframe").get_attribute("src") == anchor
            assert await has_active_sensitive_challenge(page)
        finally:
            await browser.close()


async def test_identity_origin_is_rechecked_after_marker_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context(service_workers="block")

            async def respond(route: Route) -> None:
                await route.fulfill(
                    content_type="text/html", body='<p id="identity">Signed in as user</p>',
                )

            await context.route("**/*", respond)
            page = await context.new_page()
            await page.goto("https://target.invalid/")
            original = Locator.inner_text

            async def navigate_after_read(
                locator: Locator, **options: float | None,
            ) -> str:
                marker = await original(locator, timeout=options.get("timeout"))
                await page.goto("https://other.invalid/")
                return marker

            monkeypatch.setattr(Locator, "inner_text", navigate_after_read)
            policy = AuthVerificationPolicy(
                origin="https://target.invalid", marker_selector="#identity",
                expected_marker="Signed in as user", role="user", account_reference="fixture-user",
            )
            assert await verify_authenticated_role(
                page=page, policy=policy, allowed_origins=frozenset({"https://target.invalid"}),
            ) is None
        finally:
            await browser.close()
