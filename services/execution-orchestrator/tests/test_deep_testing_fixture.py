"""Independent real-Chromium ground truth, without model/provider calls."""

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

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "tests/benchmarks/markettwin_deep/manifest.json"
FIXTURE = Path(__file__).parent / "fixtures/deep_testing_app"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def fixture_origin() -> Iterator[tuple[str, int]]:
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(FIXTURE)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("variant", ["good", "bad"])
@pytest.mark.parametrize("width", [320, 1280])
async def test_registration_ground_truth(
    fixture_origin: tuple[str, int], variant: str, width: int,
) -> None:
    origin, _ = fixture_origin
    bad = variant == "bad"
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": width, "height": 800})
            url = f"{origin}/index.html?variant={variant}"
            await page.goto(url)
            assert await page.get_by_role("button", name="Save", exact=True).count() == 2
            await expect(page.locator("#role")).to_be_disabled()
            assert await page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth"
            )

            # Empty -> corrected valid input, retaining the actual failed state first.
            save = page.get_by_role("form", name="Registration").get_by_role("button", name="Save")
            await save.click()
            if bad:
                await expect(page.locator("#error")).to_be_hidden()
                await expect(page.locator("#result")).to_have_text("Fixture profile registered.")
            else:
                await expect(page.locator("#error")).to_have_text("Display name is required.")
                await expect(page.locator("#result")).to_be_hidden()
            await page.get_by_label("Display name", exact=True).fill("Visitor")
            await page.get_by_label("Email", exact=True).fill("fixture@example.test")
            await save.click()
            await expect(page.locator("#result")).to_be_visible()
            await expect(page.locator("#error")).to_be_hidden()
            await expect(page.locator("#draft-result")).to_be_hidden()

            # Re-navigation resets each case, including previously saved state.
            await page.goto(url)
            await expect(page.locator("#result")).to_be_hidden()
            await page.locator("#name").fill("Visitor")
            await page.locator("#email").fill("invalid")
            await save.click()
            await expect(page.locator("#error")).to_have_text("" if bad else "Enter a valid email.")

            await page.goto(url)
            await page.locator("#name").fill("ABCDEFGHIJKL")
            await page.locator("#email").fill("fixture@example.test")
            await save.click()
            await expect(page.locator("#result")).to_have_text("Fixture profile registered.")
            await page.locator("#name").fill("ABCDEFGHIJKLM")
            await save.click()
            await expect(page.locator("#error")).to_have_text(
                "" if bad else "Display name must be at most 12 characters."
            )

            await page.goto(url)
            await page.locator("#team").select_option("research")
            if bad:
                await expect(page.locator("#role")).to_be_disabled()
            else:
                await expect(page.locator("#role")).to_be_enabled()
                await page.locator("#role").select_option("viewer")
                await page.locator("#team").select_option("")
                await expect(page.locator("#role")).to_be_disabled()
                await expect(page.locator("#role")).to_have_value("")
            await page.locator("#draft").click()
            await expect(page.locator("#draft-result")).to_be_visible()
            await expect(page.locator("#result")).to_be_hidden()
        finally:
            await browser.close()


@pytest.mark.parametrize("variant", ["good", "bad"])
async def test_slow_navigation_and_honesty_states(
    fixture_origin: tuple[str, int], variant: str,
) -> None:
    origin, _ = fixture_origin
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"{origin}/index.html?variant={variant}")
            await page.locator("#check").click()
            await expect(page.locator("#address-status")).to_have_text("Checking…")
            await expect(page.locator("#address-status")).to_have_attribute(
                "data-state", "complete", timeout=3000,
            )
            await expect(page.locator("#address-status")).to_have_text(
                "Address unavailable." if variant == "bad" else "Address available."
            )
            await expect(page.locator("#document")).to_have_attribute("type", "file")
            await expect(page.locator("#delivery")).to_have_text(
                "Delivery awaiting external confirmation. No final evidence is available."
            )
            await page.get_by_role("link", name="Open registration guide").click()
            await expect(page.get_by_role("heading", level=1)).to_have_text(
                "Account settings" if variant == "bad" else "Registration guide"
            )
        finally:
            await browser.close()


@pytest.mark.parametrize("policy", ["local_development", "public_only"])
async def test_fixture_policy_remains_scoped(
    fixture_origin: tuple[str, int], tmp_path: Path,
    policy: Literal["local_development", "public_only"],
) -> None:
    origin, port = fixture_origin
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy=policy,
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        url = f"{origin}/index.html?variant=good"
        if policy == "public_only":
            with pytest.raises(BrowserPolicyError):
                await controller.navigate(session_id=handle.session_id, url=url)
        else:
            await controller.navigate(session_id=handle.session_id, url=url)
            with pytest.raises(BrowserPolicyError):
                await controller.click(
                    session_id=handle.session_id, role="link", name="Open restricted destination",
                )
            state = await controller.get_state(session_id=handle.session_id)
            assert state.observation.url == url


def test_manifest_matches_independent_ground_truth() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert (ROOT / manifest["fixture_path"]).resolve() == (FIXTURE / "index.html").resolve()
    cases = {case["id"]: case for case in manifest["cases"]}
    assert len(cases) == len(manifest["cases"]) == 8
    assert set(cases) == {
        "valid", "empty", "invalid_email", "name_boundary", "dependent_role", "recovery",
        "async_address", "navigation",
    }
    for case_id, case in cases.items():
        assert case["expected_verdict"] == {
            "good": "satisfied",
            "bad": "satisfied" if case_id in {"valid", "recovery"} else "not_satisfied",
        }
    assert {probe["id"]: probe["expected_verdict"] for probe in manifest["diagnostic_probes"]} == {
        "policy_blocked": "blocked", "unsupported_upload": "unverified",
        "ambiguous_delivery": "unverified",
    }
