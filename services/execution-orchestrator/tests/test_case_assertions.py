"""Deterministic assertions stay independent of any model summary."""

from urllib.parse import quote
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser.assertions import (
    evaluate_assertion,
    repeat_read_only_assertion,
)
from markettwin_shared.deep_testing import AssertionResult, CaseExecutionResult
from markettwin_shared.feature_plan import ExpectedAssertion, SemanticTarget
from playwright.async_api import Page, async_playwright
from pydantic import ValidationError


async def _open(page: Page, html: str) -> None:
    await page.goto("data:text/html," + quote(html))


def _text(assertion_id: str, expected: str) -> ExpectedAssertion:
    return ExpectedAssertion(
        assertion_id=assertion_id,
        oracle="visible_text",
        target=SemanticTarget(role="status", name="Validation"),
        expected_value=expected,
    )


@pytest.mark.asyncio
async def test_missing_expected_text_fails_and_repeats() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await _open(page, "<main><p>Saved</p></main>")
        first, second = await repeat_read_only_assertion(page, _text("error", "Email required"))
        await browser.close()
    assert first.status == second.status == "not_satisfied"
    assert first.observed_value == second.observed_value == "absent"


@pytest.mark.asyncio
async def test_delayed_expected_text_passes() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await _open(
            page,
            "<div role='status' aria-label='Validation'></div>"
            "<script>setTimeout(() => {"
            " document.querySelector('[role=status]').textContent = 'Email required';"
            "}, 300);</script>",
        )
        observation = await evaluate_assertion(
            page, _text("error", "Email required"), timeout_ms=2000
        )
        await browser.close()
    assert observation.status == "satisfied"
    assert observation.observed_value == "Email required"


@pytest.mark.asyncio
async def test_unloaded_and_ambiguous_states_stay_unverified() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        unloaded = await evaluate_assertion(page, _text("error", "Email required"))
        await _open(page, "<button>Save</button><button>Save</button>")
        ambiguous = await evaluate_assertion(
            page,
            ExpectedAssertion(
                assertion_id="save",
                oracle="visible",
                target=SemanticTarget(role="button", name="Save"),
                expected_value=True,
            ),
        )
        secret = await evaluate_assertion(
            page,
            ExpectedAssertion(
                assertion_id="secret",
                oracle="value",
                target=SemanticTarget(label="Password"),
                expected_value="hidden",
            ),
        )
        await browser.close()
    assert unloaded.reason == "page_not_loaded"
    assert ambiguous.reason == "ambiguous_target"
    assert secret.reason == "unsupported_safe_value_read"
    assert {unloaded.status, ambiguous.status, secret.status} == {"unverified"}


def test_invalid_assertion_contract_cannot_pass() -> None:
    execution_id = uuid4()
    with pytest.raises(ValidationError):
        AssertionResult(
            case_id="empty_email",
            assertion_id="error",
            oracle="visible_text",
            expected_value="Email required",
            observed_value="absent",
            status="satisfied",
            execution_id=execution_id,
            step_id=3,
            artifact_ids=(uuid4(),),
            origin="inferred",
            elapsed_ms=1,
        )
    assertion = AssertionResult(
        case_id="empty_email",
        assertion_id="error",
        oracle="visible_text",
        expected_value="Email required",
        observed_value="absent",
        status="not_satisfied",
        execution_id=execution_id,
        step_id=3,
        artifact_ids=(uuid4(),),
        origin="inferred",
        elapsed_ms=1,
    )
    with pytest.raises(ValidationError, match="foreign"):
        CaseExecutionResult(
            case_id="empty_email",
            execution_id=uuid4(),
            execution_status="completed",
            verdict="not_satisfied",
            action_step_ids=(1,),
            assertion_results=(assertion,),
            elapsed_ms=1,
        )
    with pytest.raises(ValidationError, match="Duplicate assertion"):
        CaseExecutionResult(
            case_id="empty_email",
            execution_id=execution_id,
            execution_status="completed",
            verdict="not_satisfied",
            action_step_ids=(1,),
            assertion_results=(assertion, assertion),
            elapsed_ms=1,
        )
