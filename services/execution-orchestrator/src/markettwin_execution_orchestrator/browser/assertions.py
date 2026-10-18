"""Bounded semantic, read-only assertions on a controller-owned Playwright page."""

import re
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from markettwin_shared.deep_testing import AssertionReason, AssertionStatus
from markettwin_shared.feature_plan import URL_PATH_MISMATCH, normalized_visible_text
from playwright.async_api import Locator, Page, expect

from markettwin_execution_orchestrator.agents.schemas.test_case import ExpectedAssertion
from markettwin_execution_orchestrator.browser.actions import assertion_locator, scoped_root


@dataclass(frozen=True, slots=True)
class AssertionObservation:
    status: AssertionStatus
    observed_value: str | bool | int | None
    elapsed_ms: int
    reason: AssertionReason | None = None


def safe_url(url: str) -> str:
    parsed = urlsplit(url)
    # Userinfo is never a public route component.
    return urlunsplit((parsed.scheme, parsed.netloc.rsplit("@", 1)[-1], parsed.path, "", ""))


async def repeat_read_only_assertion(
    page: Page,
    assertion: ExpectedAssertion,
    timeout_ms: int = 1500,
) -> tuple[AssertionObservation, AssertionObservation]:
    """Read the same oracle twice without repeating the action that produced it."""
    return (
        await evaluate_assertion(page, assertion, timeout_ms),
        await evaluate_assertion(page, assertion, timeout_ms),
    )


async def evaluate_assertion(
    page: Page,
    assertion: ExpectedAssertion,
    timeout_ms: int = 1500,
) -> AssertionObservation:
    """Wait only for read-only expected state; never retry a user action."""
    if not 1 <= timeout_ms <= 5000:
        raise ValueError("Assertion timeout must be between 1 and 5000ms.")
    started = time.monotonic()

    def result(
        status: AssertionStatus,
        observed: str | bool | int | None,
        reason: AssertionReason | None = None,
    ) -> AssertionObservation:
        return AssertionObservation(
            status, observed, int((time.monotonic() - started) * 1000), reason
        )

    try:
        await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        if page.url == "about:blank":
            return result("unverified", None, "page_not_loaded")
        expected = assertion.expected_value
        oracle = assertion.oracle
        locator: Locator | None = None
        if assertion.target is not None:
            target = assertion.target
            root = await scoped_root(
                page,
                scope_role=target.scope_role,
                scope_name=target.scope_name,
            )
            locator = await assertion_locator(
                root,
                role=target.role,
                name=target.name,
                label=target.label,
                text=target.text,
                timeout_ms=timeout_ms,
            )
        # Values from arbitrary text fields can contain credentials or personal data.
        # Selected-option/value assertions need a separately approved safe read contract.
        if oracle == "value":
            return result("unverified", None, "unsupported_safe_value_read")
        try:
            if oracle == "title":
                assert isinstance(expected, str)
                await expect(page).to_have_title(expected, timeout=timeout_ms)
            elif oracle == "url":
                assert isinstance(expected, str)
                await expect(page).to_have_url(expected, timeout=timeout_ms)
            elif oracle == "url_path_v1":
                assert isinstance(expected, str)
                # Exact public origin/path; query and fragment are intentionally
                # outside this versioned oracle, not redacted full-URL equality.
                await expect(page).to_have_url(
                    re.compile("^" + re.escape(expected) + r"(?:[?#].*)?$"), timeout=timeout_ms
                )
            else:
                assert locator is not None
                if oracle == "visible_text":
                    assert isinstance(expected, str)
                    await expect(locator).to_have_text(
                        expected, use_inner_text=True, timeout=timeout_ms
                    )
                    await expect(locator).to_be_visible(timeout=timeout_ms)
                elif oracle == "visible":
                    await expect(locator).to_be_visible(visible=bool(expected), timeout=timeout_ms)
                elif oracle == "enabled":
                    await expect(locator).to_be_enabled(enabled=bool(expected), timeout=timeout_ms)
                elif oracle == "checked":
                    await expect(locator).to_be_checked(checked=bool(expected), timeout=timeout_ms)
                elif oracle == "count":
                    assert isinstance(expected, int) and not isinstance(expected, bool)
                    await expect(locator).to_have_count(expected, timeout=timeout_ms)
        except AssertionError:
            pass
        if oracle == "title":
            observed: str | bool | int = (await page.title())[:1000]
        elif oracle in {"url", "url_path_v1"}:
            actual_url = page.url
            observed = safe_url(actual_url)
            # Query and fragment values cannot enter persisted observations. Their
            # redacted equality cannot establish the full URL oracle either.
            if oracle == "url" and (
                observed != actual_url or safe_url(str(expected)) != expected
            ):
                return result("unverified", observed, "unsupported_safe_url_read")
            if oracle == "url_path_v1" and (
                urlsplit(actual_url).scheme not in {"http", "https"}
                or urlsplit(actual_url).username or urlsplit(actual_url).password
            ):
                return result("unverified", None, "unsupported_safe_url_read")
            if oracle == "url_path_v1":
                # Unexpected routes may embed reset tokens or personal identifiers.
                # Persist only the frozen route on a match, or a fixed mismatch marker.
                observed = str(expected) if observed == expected else URL_PATH_MISMATCH
        else:
            assert locator is not None
            count = await locator.count()
            if oracle == "count":
                observed = count
            elif count > 1:
                return result("unverified", None, "ambiguous_target")
            elif count == 0:
                if oracle in {"enabled", "checked"}:
                    return result("unverified", None, "inspection_failed")
                observed = False if oracle == "visible" else "absent"
            elif oracle == "visible_text":
                observed = (
                    (await locator.inner_text(timeout=timeout_ms)).strip()[:1000]
                    if await locator.is_visible()
                    else "not_visible"
                )
            elif oracle == "visible":
                observed = await locator.is_visible()
            elif oracle == "enabled":
                observed = await locator.is_enabled(timeout=timeout_ms)
            else:
                observed = await locator.is_checked(timeout=timeout_ms)
        if page.is_closed():
            return result("unverified", None, "page_closed")
        matches = observed == expected
        if oracle == "visible_text" and isinstance(observed, str) and isinstance(expected, str):
            matches = normalized_visible_text(observed) == normalized_visible_text(expected)
        return result("satisfied" if matches else "not_satisfied", observed)
    except Exception:
        return result("unverified", None, "inspection_failed")
