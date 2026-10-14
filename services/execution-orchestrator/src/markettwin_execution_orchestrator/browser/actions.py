"""Deterministic locator helpers for the safe MarketTwin browser surface."""

from typing import Any, cast

from playwright.async_api import Locator, Page

from markettwin_execution_orchestrator.browser.contracts import ScopeRole
from markettwin_execution_orchestrator.browser.errors import BrowserActionError


async def scoped_root(
    page: Page, *, scope_role: ScopeRole | None = None, scope_name: str | None = None,
) -> Page | Locator:
    if scope_role is None and scope_name is None:
        return page
    if scope_role not in {"form", "region", "dialog", "listitem", "navigation"} or not scope_name:
        raise BrowserActionError("Provide an allowed scope role and exact accessible scope name.")
    scope = page.get_by_role(scope_role, name=scope_name, exact=True)
    await require_unique(scope, "Scope")
    return scope


async def require_unique(locator: Locator, description: str = "Target") -> None:
    count = await locator.count()
    if count != 1:
        kind = "scope" if description == "Scope" else "target"
        reason = f"absent_{kind}" if count == 0 else f"ambiguous_{kind}"
        raise BrowserActionError(
            f"{description} requires exactly one match; observed {count}.", reason_code=reason,
        )


def semantic_locator(
    page: Page | Locator,
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
