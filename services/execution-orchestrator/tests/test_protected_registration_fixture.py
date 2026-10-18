"""The composed local fixture requires synthetic login/MFA before registration."""

import asyncio
import importlib.util
from pathlib import Path
from threading import Thread
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.auth_session_broker import AuthSessionScope
from markettwin_shared.auth_verification import AuthVerificationPolicy
from playwright.async_api import async_playwright, expect


@pytest.mark.parametrize("variant", ["good", "bad"])
async def test_protected_registration_requires_mfa_and_counts_effects(variant: str) -> None:
    path = Path(__file__).parent / "fixtures/protected_registration_app/server.py"
    spec = importlib.util.spec_from_file_location("protected_registration_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    server = module.ProtectedRegistrationServer()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            context = await browser.new_context()
            await context.route("**/*", lambda route: route.continue_()
                                if route.request.url.startswith(origin + "/") else route.abort())
            page = await context.new_page()
            await page.goto(origin + "/registration.html?variant=" + variant)
            await expect(page.get_by_role(
                "heading", name="Sign in to the synthetic app",
            )).to_be_visible()
            await expect(page.get_by_role("form", name="Registration")).to_have_count(0)
            await page.get_by_label("Username").fill("fixture-user")
            await page.get_by_label("Password").fill("synthetic-password")
            await page.get_by_role("button", name="Continue").click()
            await page.get_by_label("One-time code").fill("000000")
            await page.get_by_role("button", name="Verify").click()
            await expect(page.get_by_role("alert")).to_have_text("Synthetic code expired.")
            await page.get_by_label("One-time code").fill("246810")
            await page.get_by_role("button", name="Verify").click()
            await expect(page.locator("#identity")).to_have_text("Signed in as user")
            assert "variant=" + variant in page.url
            await page.get_by_label("Team", exact=True).select_option("research")
            await expect(page.get_by_label("Role", exact=True)).to_be_enabled(
                enabled=variant == "good",
            )
            await page.get_by_label("Team", exact=True).select_option("")
            await page.get_by_role("button", name="Check address").click()
            await expect(page.locator("#address-status")).to_have_text(
                "Address unavailable." if variant == "bad" else "Address available.",
            )
            await page.get_by_label("Display name", exact=True).fill("Visitor")
            await page.get_by_label("Email", exact=True).fill("fixture@example.test")
            async with page.expect_response(origin + "/__fixture_effect") as effect:
                await page.get_by_role("form", name="Registration").get_by_role(
                    "button", name="Save", exact=True,
                ).click()
            assert (await effect.value).status == 200
            response = await context.request.get(origin + "/__fixture_effects")
            assert await response.json() == {"registration_submissions": 1}
            await page.get_by_role("link", name="Open registration guide").click()
            await expect(page.get_by_role(
                "heading", name="Account settings" if variant == "bad" else "Registration guide",
            )).to_be_visible()
            await expect(page.locator("#identity")).to_have_text("Signed in as user")
            await browser.close()
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=5)


async def test_controller_reuses_verified_session_storage_after_case_close(tmp_path) -> None:
    path = Path(__file__).parent / "fixtures/protected_registration_app/server.py"
    spec = importlib.util.spec_from_file_location("protected_registration_reuse", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    server = module.ProtectedRegistrationServer()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    policy = AuthVerificationPolicy(
        origin=origin, marker_selector="#identity", expected_marker="Signed in as user",
        role="user", account_reference="fixture-user",
    )
    scope = AuthSessionScope(uuid4(), uuid4(), "user", "fixture-user", origin)
    try:
        async with BrowserController(artifact_root=tmp_path) as controller:
            allowed = (AllowedOrigin("http", "127.0.0.1", server.server_port, False),)
            first = await controller.create_session(
                execution_id=uuid4(), journey_id=uuid4(), allowed_origins=allowed,
                network_policy="local_development", authenticated_session=True,
            )
            await controller.navigate(
                session_id=first.session_id, url=origin + "/registration.html",
            )
            await controller.begin_human_control(session_id=first.session_id)
            page = controller._sessions[first.session_id].page
            await page.get_by_label("Username").fill("fixture-user")
            await page.get_by_label("Password").fill("synthetic-password")
            await page.get_by_role("button", name="Continue").click()
            await page.get_by_label("One-time code").fill("246810")
            await page.get_by_role("button", name="Verify").click()
            await expect(page.locator("#identity")).to_have_text("Signed in as user")
            # This focused broker test models the trusted lease-release transition;
            # live HTTP/WS tests independently exercise its database authority.
            controller._sessions[first.session_id].control_mode = "verifying"
            principal = await controller.capture_verified_auth_session(
                handle=first, policy=policy, scope=scope,
            )
            assert principal is not None and principal.role == "user"
            await controller.end_human_control(
                session_id=first.session_id, verified=True, safe_to_capture=True,
            )
            await controller.close_session(session_id=first.session_id)
            snapshot = controller.take_auth_session_snapshot(scope=scope, case_id="empty")
            second = await controller.create_session(
                execution_id=uuid4(), journey_id=uuid4(), allowed_origins=allowed,
                network_policy="local_development", authenticated_session=True,
                auth_snapshot=snapshot,
            )
            await controller.navigate(
                session_id=second.session_id, url=origin + "/registration.html",
            )
            verified = await controller.verify_authenticated_role(handle=second, policy=policy)
            assert verified is not None and verified.role == "user"
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=5)
