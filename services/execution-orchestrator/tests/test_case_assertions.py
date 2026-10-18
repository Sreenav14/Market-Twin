"""Deterministic assertions stay independent of any model summary."""

from dataclasses import asdict
from urllib.parse import quote
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser.assertions import (
    evaluate_assertion,
    repeat_read_only_assertion,
    safe_url,
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("actual_path", "expected_path", "status"),
    [
        ("/guide", "/guide", "satisfied"),
        ("/settings", "/guide", "not_satisfied"),
        ("/?page=settings", "/?page=guide", "unverified"),
        ("/#settings", "/#guide", "unverified"),
        ("/?page=guide", "/?page=guide", "unverified"),
        ("/#guide", "/#guide", "unverified"),
        ("/guide?token=synthetic-secret-canary", "/guide", "unverified"),
        ("/guide", "/guide#synthetic-secret-canary", "unverified"),
    ],
)
async def test_url_redaction_cannot_create_a_passing_oracle(
    actual_path: str, expected_path: str, status: str,
) -> None:
    origin = "http://url-oracle.test"
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        # Serve the complete synthetic page in-process without a network request.
        await page.route("**/*", lambda route: route.fulfill(body="<main>Guide</main>"))
        await page.goto(origin + actual_path)
        assertion = ExpectedAssertion(
            assertion_id="destination", oracle="url", expected_value=origin + expected_path,
        )
        observation = await evaluate_assertion(page, assertion, timeout_ms=50)
        await browser.close()
    assert observation.status == status
    assert observation.observed_value == safe_url(origin + actual_path)
    assert observation.reason == ("unsupported_safe_url_read" if status == "unverified" else None)
    # Match the production recorder's redacted expected value and require that
    # the shared persisted-result contract also accepts the fail-closed result.
    persisted = AssertionResult(
        case_id="navigation", assertion_id=assertion.assertion_id, oracle="url",
        expected_value=safe_url(str(assertion.expected_value)),
        observed_value=observation.observed_value, status=observation.status,
        execution_id=uuid4(), step_id=1, artifact_ids=(uuid4(),), origin="inferred",
        elapsed_ms=observation.elapsed_ms, reason=observation.reason,
    )
    assert "synthetic-secret-canary" not in str(asdict(observation))
    assert "synthetic-secret-canary" not in persisted.model_dump_json()


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


@pytest.mark.asyncio
@pytest.mark.parametrize("broken", [False, True])
async def test_rendered_heading_and_frozen_text_across_breaks(broken: bool) -> None:
    expected = "Memory never forgets. The agent remembers."
    actual = "Memory never forgets.<br>The agent " + ("loses." if broken else "remembers.")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await _open(page, "<h1>" + actual + "</h1>")
        targets = (SemanticTarget(role="heading", name=expected), SemanticTarget(text=expected))
        for target in targets:
            assertion = ExpectedAssertion(
                assertion_id="heading", oracle="visible_text", target=target,
                expected_value=expected,
            )
            observation = await evaluate_assertion(page, assertion, timeout_ms=50)
            assert observation.status == ("not_satisfied" if broken else "satisfied")
            if not broken:
                persisted = AssertionResult(
                    case_id="heading", assertion_id="heading", oracle="visible_text",
                    expected_value=expected, observed_value=observation.observed_value,
                    status=observation.status, execution_id=uuid4(), step_id=1,
                    artifact_ids=(uuid4(),), origin="inferred", elapsed_ms=0,
                )
                assert persisted.expected_value == expected
        await browser.close()


@pytest.mark.asyncio
async def test_rendered_duplicate_text_requires_scope() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await _open(page, "<nav><a>Memory guide</a></nav><h1>Memory guide</h1>")
        ambiguous = await evaluate_assertion(page, ExpectedAssertion(
            assertion_id="heading", oracle="visible_text",
            target=SemanticTarget(text="Memory guide"), expected_value="Memory guide",
        ), timeout_ms=50)
        unique = await evaluate_assertion(page, ExpectedAssertion(
            assertion_id="heading", oracle="visible_text",
            target=SemanticTarget(role="heading", name="Memory guide"),
            expected_value="Memory guide",
        ), timeout_ms=50)
        await browser.close()
    assert ambiguous.reason == "ambiguous_target"
    assert unique.status == "satisfied"


@pytest.mark.asyncio
async def test_delayed_rendered_text_target_waits_without_repeating_action() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await _open(page, "<main></main><script>setTimeout(() => {"
                    "document.querySelector('main').innerHTML='<h1>Ready<br>now</h1>';"
                    "}, 100)</script>")
        observation = await evaluate_assertion(page, ExpectedAssertion(
            assertion_id="heading", oracle="visible_text",
            target=SemanticTarget(text="Ready now"), expected_value="Ready now",
        ), timeout_ms=500)
        await browser.close()
    assert observation.status == "satisfied"


@pytest.mark.asyncio
@pytest.mark.parametrize(("actual", "status"), [
    ("/guide?token=secret-canary#private", "satisfied"),
    ("/wrong?token=secret-canary", "not_satisfied"),
    ("/reset/private-path-canary?token=secret-canary", "not_satisfied"),
])
async def test_declared_public_path_oracle_good_and_seeded_bug(actual: str, status: str) -> None:
    origin = "http://path-oracle.test"
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.route("**/*", lambda route: route.fulfill(body="<main>Route</main>"))
        await page.goto(origin + actual)
        observation = await evaluate_assertion(page, ExpectedAssertion(
            assertion_id="route", oracle="url_path_v1", expected_value=origin + "/guide",
        ), timeout_ms=50)
        await browser.close()
    assert observation.status == status
    assert "secret-canary" not in str(asdict(observation))
    assert "private-path-canary" not in str(asdict(observation))
    persisted = AssertionResult(
        case_id="route", assertion_id="route", oracle="url_path_v1",
        expected_value=origin + "/guide", observed_value=observation.observed_value,
        status=observation.status, execution_id=uuid4(), step_id=1,
        artifact_ids=(uuid4(),), origin="inferred", elapsed_ms=observation.elapsed_ms,
    )
    assert "private-path-canary" not in persisted.model_dump_json()
    assert persisted.observed_value == (
        origin + "/guide" if status == "satisfied" else "different origin/path"
    )


@pytest.mark.parametrize("expected", [
    "https://user:secret@example.test/guide", "https://example.test/?token=secret",
    "https://example.test/#secret", "/relative", "javascript:alert(1)",
])
def test_public_path_oracle_rejects_private_or_nonabsolute_expected(expected: str) -> None:
    with pytest.raises(ValidationError):
        ExpectedAssertion(assertion_id="route", oracle="url_path_v1", expected_value=expected)


def test_safe_url_never_retains_userinfo() -> None:
    assert safe_url("https://user:secret@example.test/guide?token=secret#private") == (
        "https://example.test/guide"
    )
