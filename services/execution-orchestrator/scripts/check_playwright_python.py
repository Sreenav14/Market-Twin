"""Verify that Playwright Python and its Chromium executable are available."""

import asyncio
from importlib.metadata import version

from playwright.async_api import async_playwright


async def main() -> None:
    """Launch and close Chromium to verify the Python browser dependency."""

    print(f"Playwright Python: {version('playwright')}")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            print(f"Chromium: {browser.version}")
            print("Playwright Python browser check OK")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
