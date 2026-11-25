"""D16 value channel (doc 24 section 6.1, W4-P5-11): a value oracle
compares the live field value against an APPROVED expected value
inside the page and reports only the boolean. The actual content is
never read back, logged, or placed in an observation.
"""

from urllib.parse import quote

import pytest
from playwright.async_api import async_playwright

from markettwin_execution_orchestrator.agents.schemas.test_case import (
    ExpectedAssertion,
    SemanticTarget,
)
from markettwin_execution_orchestrator.browser.assertions import (
    evaluate_assertion,
)

_SECRET = "s3cret-token-value"

_PAGE = f"""<!doctype html><html><body>
<label>API key <input id="key" value="{_SECRET}"></label>
</body></html>"""


def _assertion(expected: str) -> ExpectedAssertion:
    return ExpectedAssertion(
        assertion_id="api_key_value",
        oracle="value",
        target=SemanticTarget(label="API key"),
        expected_value=expected,
        origin="inferred",
    )


async def _field_page(playwright):
    browser = await playwright.chromium.launch()
    page = await browser.new_page()
    # A data: URL gives the page a real (non-blank) URL, which
    # evaluate_assertion requires before it reads anything.
    await page.goto("data:text/html," + quote(_PAGE, safe=""))
    return browser, page


@pytest.mark.asyncio
async def test_approved_value_compares_without_disclosing() -> None:
    """T-P5-H1: an approved expected value is compared in-page; the
    observation carries the boolean outcome and never the content —
    for both the matching and the mismatching approved value."""
    async with async_playwright() as playwright:
        browser, page = await _field_page(playwright)
        matched = await evaluate_assertion(
            page, _assertion(_SECRET),
            approved_values=(_SECRET,), run_mode="standard",
        )
        missed = await evaluate_assertion(
            page, _assertion("a-different-approved-value"),
            approved_values=(_SECRET, "a-different-approved-value"),
            run_mode="standard",
        )
        await browser.close()
    assert matched.status == "satisfied"
    assert matched.observed_value is True
    assert missed.status == "not_satisfied"
    assert missed.observed_value is False
    for outcome in (matched, missed):
        assert outcome.reason is None
        assert _SECRET not in str(outcome)


@pytest.mark.asyncio
async def test_unapproved_value_keeps_the_privacy_block() -> None:
    """T-P5-H2: a value oracle whose expected value is NOT on the
    approved list is byte-identical to today — unverified with the
    standing reason, and nothing is read."""
    async with async_playwright() as playwright:
        browser, page = await _field_page(playwright)
        outcome = await evaluate_assertion(
            page, _assertion(_SECRET),
            approved_values=(), run_mode="standard",
        )
        await browser.close()
    assert outcome.status == "unverified"
    assert outcome.reason == "unsupported_safe_value_read"


@pytest.mark.asyncio
async def test_read_only_mode_never_exercises_the_value() -> None:
    """T-P5-H1: in a read-only run the value oracle is accounted
    not_exercised_read_only even when the value is approved."""
    async with async_playwright() as playwright:
        browser, page = await _field_page(playwright)
        outcome = await evaluate_assertion(
            page, _assertion(_SECRET),
            approved_values=(_SECRET,), run_mode="read_only",
        )
        await browser.close()
    assert outcome.status == "unverified"
    assert outcome.reason == "not_exercised_read_only"
