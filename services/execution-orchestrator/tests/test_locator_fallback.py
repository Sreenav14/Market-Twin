"""Fallback never turns ambiguity into a guessed browser mutation."""

import pytest
from markettwin_execution_orchestrator.browser.actions import resolve_action_locator
from markettwin_execution_orchestrator.browser.errors import BrowserActionError
from playwright.async_api import async_playwright


async def test_supplied_label_and_normalized_name_fallbacks() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.set_content('<button aria-label="Continue">Next</button>')
        locator, strategy = await resolve_action_locator(
            page, role="button", name="Stale name", label="Continue",
        )
        assert strategy == "label_exact"
        assert await locator.count() == 1
        locator, strategy = await resolve_action_locator(page, role="button", name="  CONTINUE  ")
        assert strategy == "role_normalized"
        await locator.click()
        await browser.close()


async def test_ambiguous_exact_target_never_falls_through_or_clicks() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.set_content(
            '<button onclick="document.title=\'clicked\'">Next</button>'
            '<button>Next</button><button aria-label="Unique">Continue</button>'
        )
        with pytest.raises(BrowserActionError) as error:
            await resolve_action_locator(page, role="button", name="Next", label="Unique")
        assert error.value.reason_code == "ambiguous_target"
        assert await page.title() == ""
        await browser.close()
