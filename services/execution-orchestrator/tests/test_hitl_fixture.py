"""Independent real-browser ground truth for the synthetic HITL fixture."""

import json
import threading
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserPolicyError
from playwright.async_api import async_playwright, expect

FIXTURE = Path(__file__).parent / "fixtures/hitl_app"
TRUTH = FIXTURE / "ground_truth.json"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def fixture_origin() -> Iterator[tuple[str, int]]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(FIXTURE)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("variant", ["good", "bad"])
async def test_synthetic_login_mfa_and_role_truth(
    fixture_origin: tuple[str, int], variant: Literal["good", "bad"],
) -> None:
    origin, _ = fixture_origin
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(f"{origin}/index.html?view=login&variant={variant}")
            await page.get_by_label("Username").fill("fixture-user")
            await page.get_by_label("Password").fill("wrong")
            await page.get_by_role("button", name="Continue").click()
            await expect(page.get_by_role("alert")).to_have_text(
                truth["expected"]["wrong_password"]
            )

            await page.get_by_label("Password").fill(truth["credentials"]["user"]["password"])
            await page.get_by_role("button", name="Continue").click()
            await expect(page.get_by_role("heading", name="Verify synthetic MFA")).to_be_visible()
            await page.get_by_label("One-time code").fill("111111")
            await page.get_by_role("button", name="Verify").click()
            await expect(page.get_by_role("alert")).to_have_text(truth["expected"]["wrong_otp"])
            await page.get_by_label("One-time code").fill("000000")
            await page.get_by_role("button", name="Verify").click()
            await expect(page.get_by_role("alert")).to_have_text(truth["expected"]["expired_otp"])

            await page.get_by_label("One-time code").fill(truth["credentials"]["user"]["otp"])
            await page.get_by_role("button", name="Verify").click()
            await expect(
                page.get_by_text(truth["expected"]["user_dashboard"], exact=True)
            ).to_be_visible()
            admin_link = page.get_by_role("link", name="Admin console")
            if variant == "good":
                await expect(admin_link).to_have_count(0)
            else:
                await expect(admin_link).to_be_visible()
            await page.goto(f"{origin}/index.html?view=admin&variant={variant}")
            user_admin_result = (
                truth["expected"]["user_admin_access"]
                if variant == "good"
                else truth["seeded_bad_variant"]["user_admin_access"]
            )
            await expect(page.get_by_role("heading", name=user_admin_result)).to_be_visible()

            await page.goto(f"{origin}/index.html?view=login&variant={variant}")
            await page.get_by_label("Username").fill("fixture-admin")
            await page.get_by_label("Password").fill(truth["credentials"]["admin"]["password"])
            await page.get_by_role("button", name="Continue").click()
            await page.get_by_label("One-time code").fill(truth["credentials"]["admin"]["otp"])
            await page.get_by_role("button", name="Verify").click()
            await expect(
                page.get_by_text(truth["expected"]["admin_dashboard"], exact=True)
            ).to_be_visible()
        finally:
            await browser.close()


async def test_fixture_is_network_scoped_and_browser_canary_is_detectable(
    fixture_origin: tuple[str, int], tmp_path: Path,
) -> None:
    origin, port = fixture_origin
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        result = await controller.navigate(
            session_id=handle.session_id,
            url=f"{origin}/index.html?view=login&inject_canary=1",
        )
        assert truth["canary"] in " ".join(result.observation.console_errors_since_last_action)
        assert truth["prompt_injection"] in result.observation.aria_snapshot
        with pytest.raises(BrowserPolicyError):
            await controller.navigate(session_id=handle.session_id, url="https://example.com/")
