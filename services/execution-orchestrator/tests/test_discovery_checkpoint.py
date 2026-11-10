"""Real DOM fixture signals; no external site or model calls."""

from types import SimpleNamespace

import pytest
from playwright.async_api import async_playwright

from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.discovery_checkpoint import is_discovery_checkpoint


@pytest.mark.parametrize("html, checkpoint", [
    ('<body>Please enable JS and disable any ad blocker<script type="application/json" '
     'src="https://ct.captcha-delivery.com/c.js"></script></body>', True),
    ('<body></body>', False),
    ('<body><h1>Catalog</h1><button>Search</button><input aria-label="Query"></body>', False),
    ('<body>Verify you are human<script type="application/json" '
     'src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script></body>', True),
    ('<body>Our documentation mentions DataDome and Cloudflare.<button>Search</button></body>', False),
    ('<body>Search<input aria-label="Query"><button>Search</button>'
     '<script type="application/json" src="https://challenges.cloudflare.com/turnstile/v0/api.js">'
     '</script></body>', False),
])
async def test_checkpoint_fixture_dom_signals(monkeypatch, html, checkpoint):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content(html)
            controller = BrowserController()
            monkeypatch.setattr(controller, "_get_session", lambda **_: SimpleNamespace(page=page))
            signals = await controller.discovery_page_signals(session_id=None)
            assert is_discovery_checkpoint(**signals) is checkpoint
        finally:
            await browser.close()
