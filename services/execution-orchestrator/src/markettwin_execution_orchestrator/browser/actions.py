"""Deterministic locator helpers for the safe MarketTwin browser surface."""

from typing import Any, cast

from playwright.async_api import Locator, Page

from markettwin_execution_orchestrator.browser.errors import BrowserActionError


def semantic_locator(
    page: Page,
    *,
    role: str | None = None,
    name: str | None = None,
    label: str | None = None,
    text: str | None = None,
) -> Locator:
    """Resolve one bounded semantic locator without arbitrary selectors."""

    supplied = sum(value is not None for value in (role, label, text))
    if supplied != 1:
        raise BrowserActionError(
            "Provide exactly one locator strategy: role, label, or text."
        )
    if role is not None:
        if not name:
            raise BrowserActionError("Role locators require an accessible name.")
        return page.get_by_role(cast(Any, role), name=name, exact=True)
    if label is not None:
        return page.get_by_label(label, exact=True)
    assert text is not None
    return page.get_by_text(text, exact=True)
