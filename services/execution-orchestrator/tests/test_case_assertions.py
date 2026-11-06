"""Deterministic assertions stay independent of any model summary."""

import asyncio
import json
from dataclasses import asdict
from urllib.parse import quote
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.agents.schemas.test_case import (
    FeatureScope,
    PlanBudget,
    TestCaseSpec,
)
from markettwin_execution_orchestrator.browser.assertions import (
    AssertionObservation,
    evaluate_assertion,
    repeat_read_only_assertion,
    safe_url,
)
from markettwin_execution_orchestrator.browser.contracts import (
    AllowedOrigin,
    BrowserActionResult,
    BrowserObservation,
    BrowserSessionArtifacts,
    BrowserSessionHandle,
)
from markettwin_execution_orchestrator.workflow import case_execution
from markettwin_execution_orchestrator.workflow.case_execution import (
    _is_failed_action_precondition,
)
from markettwin_execution_orchestrator.workflow.deep_run import case_journey
from markettwin_execution_orchestrator.workflow.journey_executor import (
    PersonaJourneyExecutionRequest,
)
from markettwin_shared.deep_testing import AssertionResult, CaseExecutionResult
from markettwin_shared.feature_plan import CaseAction, ExpectedAssertion, SemanticTarget
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


def test_only_owner_approved_failed_visibility_on_the_next_exact_target_blocks_action():
    target = SemanticTarget(role="button", name="Continue")
    action = CaseAction(action="click", target=target)
    expected = ExpectedAssertion(
        assertion_id="continue_enabled",
        oracle="enabled",
        target=target,
        expected_value=True,
        after_step_ordinal=0,
        origin="user_approved",
    )
    observed = AssertionResult(
        case_id="journey",
        assertion_id="continue_enabled",
        oracle="enabled",
        expected_value=True,
        observed_value=False,
        status="not_satisfied",
        execution_id=uuid4(),
        step_id=2,
        artifact_ids=(uuid4(),),
        origin="user_approved",
        elapsed_ms=1,
    )

    assert _is_failed_action_precondition(expected, observed, action)
    assert not _is_failed_action_precondition(
        expected,
        observed,
        CaseAction(
            action="click",
            target=SemanticTarget(
                role="button",
                name="Different",
            ),
        ),
    )
    assert not _is_failed_action_precondition(expected, observed, None)
    assert not _is_failed_action_precondition(
        expected.model_copy(update={"origin": "inferred"}),
        observed,
        action,
    )
    assert not _is_failed_action_precondition(
        expected,
        observed.model_copy(update={"status": "unverified"}),
        action,
    )


def test_failed_precondition_matches_scoped_action_when_check_is_unscoped():
    # Contract checks are translated from ContractAssertion, which carries
    # role/name only, while the replayed click target keeps the scope that
    # discovery recorded. The failed check must still guard that action.
    scoped_action = CaseAction(
        action="click",
        target=SemanticTarget(
            role="button", name="Continue", scope_role="form", scope_name="Checkout",
        ),
    )
    expected = ExpectedAssertion(
        assertion_id="continue_enabled",
        oracle="enabled",
        target=SemanticTarget(role="button", name="Continue"),
        expected_value=True,
        after_step_ordinal=0,
        origin="user_approved",
    )
    observed = AssertionResult(
        case_id="journey",
        assertion_id="continue_enabled",
        oracle="enabled",
        expected_value=True,
        observed_value=False,
        status="not_satisfied",
        execution_id=uuid4(),
        step_id=2,
        artifact_ids=(uuid4(),),
        origin="user_approved",
        elapsed_ms=1,
    )

    assert _is_failed_action_precondition(expected, observed, scoped_action)
    # A check that names a different scope must not guard the action.
    other_scope = expected.model_copy(
        update={
            "target": SemanticTarget(
                role="button", name="Continue",
                scope_role="form", scope_name="Registration",
            ),
        },
    )
    assert not _is_failed_action_precondition(other_scope, observed, scoped_action)
    # A check scoped exactly like the action still matches.
    same_scope = expected.model_copy(
        update={
            "target": SemanticTarget(
                role="button", name="Continue",
                scope_role="form", scope_name="Checkout",
            ),
        },
    )
    assert _is_failed_action_precondition(same_scope, observed, scoped_action)


@pytest.mark.asyncio
@pytest.mark.parametrize("opaque_takeover", [False, True])
async def test_executor_persists_failed_pre_action_evidence_and_skips_action_and_later_checks(
    monkeypatch: pytest.MonkeyPatch,
    opaque_takeover: bool,
) -> None:
    execution_id, journey_id, run_id = uuid4(), uuid4(), uuid4()
    expected_target = SemanticTarget(role="button", name="Continue")
    case = TestCaseSpec(
        case_id="continue_checkout",
        feature_key="checkout",
        title="Continue checkout",
        kind="happy_path",
        steps=(CaseAction(action="click", target=expected_target),),
        expected=(
            ExpectedAssertion(
                assertion_id="continue_enabled", oracle="enabled", target=expected_target,
                expected_value=True, origin="user_approved",
                after_step_ordinal=1 if opaque_takeover else 0,
            ),
            ExpectedAssertion(
                assertion_id="checkout_saved", oracle="visible_text",
                target=SemanticTarget(role="status", name="Checkout status"),
                expected_value="Saved", origin="user_approved", after_step_ordinal=1,
            ),
        ),
    )
    scope = FeatureScope(
        feature_key="checkout", goal="Continue checkout safely",
        starting_url="https://example.test/checkout",
        allowed_origins=("https://example.test",),
    )
    request = PersonaJourneyExecutionRequest(
        test_run_id=run_id, execution_id=execution_id, journey_id=journey_id,
        persona_id=uuid4(), mission_id=uuid4(), journey=case_journey(case),
        start_url=scope.starting_url,
        allowed_origins=(AllowedOrigin(scheme="https", hostname="example.test"),),
        max_duration_seconds=10,
    )
    order: list[str] = []

    class FakeSession:
        latest_artifact = None

        async def commit(self) -> None:
            pass

        async def rollback(self) -> None:
            pass

        async def scalars(self, _query: object):
            return [self.latest_artifact] if self.latest_artifact else []

    session = FakeSession()

    class FakeEvents:
        def __init__(self, _session: object) -> None:
            self.events: list[tuple[str, dict[str, object]]] = []

        async def create(self, *, event_type: str, payload: dict[str, object], **_kwargs: object):
            self.events.append((event_type, payload))
            order.append(event_type)

    class FakeExecutionRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def create_browser_session(self, **_kwargs: object) -> None:
            pass

        async def mark_browser_session_closed(self, **_kwargs: object) -> None:
            pass

    class FakeRecorder:
        def __init__(self, _session: object, _execution_id: object, _storage: object) -> None:
            self.next_step_id = 0
            self.steps: list[tuple[int, str, str | None]] = []
            self.evidence: dict[int, object] = {}

        async def start_step(self, *, action_type: str, action_summary: str) -> int:
            self.next_step_id += 1
            self.steps.append((self.next_step_id, action_type, None))
            order.append(f"step:{action_type}")
            return self.next_step_id

        async def record_evidence(self, *, step_id: int, result: BrowserActionResult) -> None:
            artifact_id = uuid4()
            self.evidence[step_id] = artifact_id
            session.latest_artifact = artifact_id
            order.append(f"evidence:{step_id}")

        async def finish_step(
            self, *, step_id: int, status: str, observation_summary: str | None = None,
        ) -> None:
            self.steps = [
                (item_id, action, observation_summary if item_id == step_id else summary)
                for item_id, action, summary in self.steps
            ]
            order.append(f"finish:{step_id}:{status}")

    class FakeBrowserController:
        def __init__(self) -> None:
            self.handle = BrowserSessionHandle(execution_id, journey_id, uuid4())
            self.assertion_ids: list[str] = []
            self.click_calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: object) -> None:
            pass

        async def create_session(self, **_kwargs: object) -> BrowserSessionHandle:
            return self.handle

        def bind_cooperative_pause_handler(self, *_args: object) -> None:
            pass

        async def cooperative_checkpoint(self, _handle: BrowserSessionHandle) -> None:
            pass

        async def inspect_click_approval(self, **_kwargs: object) -> None:
            return None

        async def navigate(self, **_kwargs: object) -> BrowserActionResult:
            order.append("navigate")
            return _browser_action_result("navigate")

        async def read_assertion(self, *, assertion: ExpectedAssertion, **_kwargs: object):
            self.assertion_ids.append(assertion.assertion_id)
            order.append(f"read:{assertion.assertion_id}")
            return (
                _browser_action_result("assertion"),
                AssertionObservation(
                    "satisfied" if opaque_takeover else "not_satisfied",
                    True if opaque_takeover else False, 1,
                ),
            )

        async def click(self, **_kwargs: object) -> BrowserActionResult:
            self.click_calls += 1
            order.append("click")
            if opaque_takeover:
                from markettwin_execution_orchestrator.browser.errors import (
                    BrowserActionBlockedError,
                )

                raise BrowserActionBlockedError(
                    "An opaque confirmation requires human browser takeover."
                )
            return _browser_action_result("click")

        async def close_session(self, **_kwargs: object) -> BrowserSessionArtifacts:
            return BrowserSessionArtifacts()

    browser = FakeBrowserController()
    events = FakeEvents(session)
    recorder = FakeRecorder(session, execution_id, object())
    monkeypatch.setattr(case_execution, "RunEventRepository", lambda _session: events)
    monkeypatch.setattr(case_execution, "ExecutionRepository", FakeExecutionRepository)
    monkeypatch.setattr(case_execution, "ExecutionStepRecorder", lambda *_args: recorder)
    monkeypatch.setattr(case_execution, "SessionArtifactRecorder", lambda *_args: _EmptyArtifacts())
    monkeypatch.setattr(
        case_execution.S3ArtifactStorage, "from_environment", classmethod(lambda _cls: object()),
    )
    monkeypatch.setattr(case_execution, "BrowserController", lambda: browser)
    from markettwin_execution_orchestrator.workflow import cooperative_pause

    async def no_pause_finalization(_session: object, _handle: BrowserSessionHandle) -> None:
        pass

    monkeypatch.setattr(cooperative_pause, "finalize_browser_pauses", no_pause_finalization)

    result = await case_execution.execute_test_case(
        request=request, case=case, scope=scope, budget=PlanBudget(max_steps=8),
        controller=browser, session=session,
    )

    if opaque_takeover:
        assert result.execution_status == "policy_blocked", [
            payload for kind, payload in events.events if kind == "test_case.diagnostic"
        ]
        assert result.verdict == "unverified"
        assert result.blocker == "human_takeover_required"
        assert browser.click_calls == 1
        assert browser.assertion_ids == []
        action_step = next(step for step in recorder.steps if step[1] == "click")
        persisted = json.loads(action_step[2])
        assert persisted["reason_code"] == "human_takeover_required"
        assert persisted["reason"] == (
            "An opaque confirmation requires human browser takeover."
        )
        assert persisted["action"] == {
            "action": "click", "target": {"role": "button", "name": "Continue"},
        }
        diagnostic = next(payload for kind, payload in events.events
                          if kind == "test_case.diagnostic")
        assert diagnostic["reason"] == persisted["reason"]
        assert diagnostic["action"] == persisted["action"]
        assert "read:checkout_saved" not in order
    else:
        assert result.verdict == "not_satisfied", (
            result.execution_status, result.blocker,
            [payload for kind, payload in events.events if kind == "test_case.diagnostic"],
            order,
        )
        assert result.blocker == "assertion_precondition_failed"
        assert browser.assertion_ids == ["continue_enabled"]
        assert browser.click_calls == 0
        assertion_step = recorder.steps[1]
        assert assertion_step[1] == "assertion"
        assert result.assertion_results[0].step_id == assertion_step[0]
        assert result.assertion_results[0].artifact_ids == (recorder.evidence[assertion_step[0]],)
        assert [kind for kind, _payload in events.events].count("test_case.assertion") == 1
        assert order.index("read:continue_enabled") < order.index("evidence:2")
        assert "read:checkout_saved" not in order
        assert "click" not in order


@pytest.mark.asyncio
async def test_executor_timeout_persists_partial_progress_and_closes_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_id, journey_id, run_id = uuid4(), uuid4(), uuid4()
    target = SemanticTarget(role="button", name="Continue")
    case = TestCaseSpec(
        case_id="slow_navigation", feature_key="checkout", title="Slow navigation",
        kind="happy_path",
        steps=(CaseAction(action="click", target=target),),
        expected=(ExpectedAssertion(
            assertion_id="saved", oracle="visible_text",
            target=SemanticTarget(role="status", name="Status"),
            expected_value="Saved", after_step_ordinal=1,
        ),),
    )
    scope = FeatureScope(
        feature_key="checkout", goal="Check a slow checkout page",
        starting_url="https://example.test/checkout",
        allowed_origins=("https://example.test",),
    )
    request = PersonaJourneyExecutionRequest(
        test_run_id=run_id, execution_id=execution_id, journey_id=journey_id,
        persona_id=uuid4(), mission_id=uuid4(), journey=case_journey(case),
        start_url=scope.starting_url,
        allowed_origins=(AllowedOrigin(scheme="https", hostname="example.test"),),
        max_duration_seconds=5,
    )

    class FakeSession:
        async def commit(self) -> None:
            pass

        async def rollback(self) -> None:
            pass

    session = FakeSession()

    class FakeEvents:
        def __init__(self, _session: object) -> None:
            self.events: list[tuple[str, dict[str, object]]] = []

        async def create(self, *, event_type: str, payload: dict[str, object], **_kwargs: object):
            self.events.append((event_type, payload))

    class FakeExecutionRepository:
        def __init__(self, _session: object) -> None:
            self.closed_session_ids: list[object] = []

        async def create_browser_session(self, **_kwargs: object) -> None:
            pass

        async def mark_browser_session_closed(self, *, browser_session_id: object) -> None:
            self.closed_session_ids.append(browser_session_id)

    class FakeRecorder:
        def __init__(self, _session: object, _execution_id: object, _storage: object) -> None:
            self.steps: list[tuple[int, str, str | None]] = []

        async def start_step(self, *, action_type: str, action_summary: str) -> int:
            self.steps.append((1, action_type, None))
            return 1

        async def finish_step(
            self, *, step_id: int, status: str, observation_summary: str | None = None,
        ) -> None:
            self.steps = [(step_id, action_type, status) for _, action_type, _ in self.steps]

        async def record_evidence(self, **_kwargs: object) -> None:
            raise AssertionError("A cancelled browser operation has no success evidence.")

    class FakeBrowserController:
        def __init__(self) -> None:
            self.handle = BrowserSessionHandle(execution_id, journey_id, uuid4())
            self.navigation_started = asyncio.Event()
            self.closed = False

        async def create_session(self, **_kwargs: object) -> BrowserSessionHandle:
            return self.handle

        def bind_cooperative_pause_handler(self, *_args: object) -> None:
            pass

        async def cooperative_checkpoint(self, _handle: BrowserSessionHandle) -> None:
            pass

        async def navigate(self, **_kwargs: object) -> BrowserActionResult:
            self.navigation_started.set()
            await asyncio.Event().wait()
            raise AssertionError("The timed-out operation should never complete.")

        async def close_session(self, **_kwargs: object) -> BrowserSessionArtifacts:
            self.closed = True
            return BrowserSessionArtifacts()

    events = FakeEvents(session)
    repository = FakeExecutionRepository(session)
    recorder = FakeRecorder(session, execution_id, object())
    browser = FakeBrowserController()
    monkeypatch.setattr(case_execution, "RunEventRepository", lambda _session: events)
    monkeypatch.setattr(case_execution, "ExecutionRepository", lambda _session: repository)
    monkeypatch.setattr(case_execution, "ExecutionStepRecorder", lambda *_args: recorder)
    monkeypatch.setattr(case_execution, "SessionArtifactRecorder", lambda *_args: _EmptyArtifacts())
    monkeypatch.setattr(
        case_execution.S3ArtifactStorage, "from_environment", classmethod(lambda _cls: object()),
    )
    monkeypatch.setattr(case_execution, "BrowserController", lambda: browser)
    from markettwin_execution_orchestrator.workflow import cooperative_pause

    async def no_pause_finalization(_session: object, _handle: BrowserSessionHandle) -> None:
        pass

    monkeypatch.setattr(cooperative_pause, "finalize_browser_pauses", no_pause_finalization)

    result = await case_execution.execute_test_case(
        request=request, case=case, scope=scope,
        budget=PlanBudget(max_steps=8, max_total_seconds=1),
        controller=browser, session=session,
    )

    assert browser.navigation_started.is_set()
    assert result.execution_status == "timed_out"
    assert result.verdict == "unverified"
    assert result.blocker == "time_limit"
    assert len(result.action_step_ids) == 1
    assert result.assertion_results == ()
    assert recorder.steps == [(1, "navigate", "failed")]
    completed = next(payload for kind, payload in events.events if kind == "test_case.completed")
    assert completed["execution_status"] == "timed_out"
    assert completed["verdict"] == "unverified"
    assert completed["blocker"] == "time_limit"
    assert completed["action_step_ids"] == list(result.action_step_ids)
    assert completed["assertion_results"] == []
    assert browser.closed
    assert repository.closed_session_ids == [browser.handle.session_id]


def _browser_action_result(action: str) -> BrowserActionResult:
    return BrowserActionResult(
        action=action,
        observation=BrowserObservation(
            url="https://example.test/checkout", title="Checkout", aria_snapshot="",
            viewport_width=1280, viewport_height=720, scroll_y=0, document_height=720,
        ),
    )


class _EmptyArtifacts:
    async def record(self, _artifacts: BrowserSessionArtifacts) -> None:
        pass


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
    actual_path: str,
    expected_path: str,
    status: str,
) -> None:
    origin = "http://url-oracle.test"
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        # Serve the complete synthetic page in-process without a network request.
        await page.route("**/*", lambda route: route.fulfill(body="<main>Guide</main>"))
        await page.goto(origin + actual_path)
        assertion = ExpectedAssertion(
            assertion_id="destination",
            oracle="url",
            expected_value=origin + expected_path,
        )
        observation = await evaluate_assertion(page, assertion, timeout_ms=50)
        await browser.close()
    assert observation.status == status
    assert observation.observed_value == safe_url(origin + actual_path)
    assert observation.reason == ("unsupported_safe_url_read" if status == "unverified" else None)
    # Match the production recorder's redacted expected value and require that
    # the shared persisted-result contract also accepts the fail-closed result.
    persisted = AssertionResult(
        case_id="navigation",
        assertion_id=assertion.assertion_id,
        oracle="url",
        expected_value=safe_url(str(assertion.expected_value)),
        observed_value=observation.observed_value,
        status=observation.status,
        execution_id=uuid4(),
        step_id=1,
        artifact_ids=(uuid4(),),
        origin="inferred",
        elapsed_ms=observation.elapsed_ms,
        reason=observation.reason,
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
                assertion_id="heading",
                oracle="visible_text",
                target=target,
                expected_value=expected,
            )
            observation = await evaluate_assertion(page, assertion, timeout_ms=50)
            assert observation.status == ("not_satisfied" if broken else "satisfied")
            if not broken:
                persisted = AssertionResult(
                    case_id="heading",
                    assertion_id="heading",
                    oracle="visible_text",
                    expected_value=expected,
                    observed_value=observation.observed_value,
                    status=observation.status,
                    execution_id=uuid4(),
                    step_id=1,
                    artifact_ids=(uuid4(),),
                    origin="inferred",
                    elapsed_ms=0,
                )
                assert persisted.expected_value == expected
        await browser.close()


@pytest.mark.asyncio
async def test_rendered_duplicate_text_requires_scope() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await _open(page, "<nav><a>Memory guide</a></nav><h1>Memory guide</h1>")
        ambiguous = await evaluate_assertion(
            page,
            ExpectedAssertion(
                assertion_id="heading",
                oracle="visible_text",
                target=SemanticTarget(text="Memory guide"),
                expected_value="Memory guide",
            ),
            timeout_ms=50,
        )
        unique = await evaluate_assertion(
            page,
            ExpectedAssertion(
                assertion_id="heading",
                oracle="visible_text",
                target=SemanticTarget(role="heading", name="Memory guide"),
                expected_value="Memory guide",
            ),
            timeout_ms=50,
        )
        await browser.close()
    assert ambiguous.reason == "ambiguous_target"
    assert unique.status == "satisfied"


@pytest.mark.asyncio
async def test_delayed_rendered_text_target_waits_without_repeating_action() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await _open(
            page,
            "<main></main><script>setTimeout(() => {"
            "document.querySelector('main').innerHTML='<h1>Ready<br>now</h1>';"
            "}, 100)</script>",
        )
        observation = await evaluate_assertion(
            page,
            ExpectedAssertion(
                assertion_id="heading",
                oracle="visible_text",
                target=SemanticTarget(text="Ready now"),
                expected_value="Ready now",
            ),
            timeout_ms=500,
        )
        await browser.close()
    assert observation.status == "satisfied"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("actual", "status"),
    [
        ("/guide?token=secret-canary#private", "satisfied"),
        ("/wrong?token=secret-canary", "not_satisfied"),
        ("/reset/private-path-canary?token=secret-canary", "not_satisfied"),
    ],
)
async def test_declared_public_path_oracle_good_and_seeded_bug(actual: str, status: str) -> None:
    origin = "http://path-oracle.test"
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.route("**/*", lambda route: route.fulfill(body="<main>Route</main>"))
        await page.goto(origin + actual)
        observation = await evaluate_assertion(
            page,
            ExpectedAssertion(
                assertion_id="route",
                oracle="url_path_v1",
                expected_value=origin + "/guide",
            ),
            timeout_ms=50,
        )
        await browser.close()
    assert observation.status == status
    assert "secret-canary" not in str(asdict(observation))
    assert "private-path-canary" not in str(asdict(observation))
    persisted = AssertionResult(
        case_id="route",
        assertion_id="route",
        oracle="url_path_v1",
        expected_value=origin + "/guide",
        observed_value=observation.observed_value,
        status=observation.status,
        execution_id=uuid4(),
        step_id=1,
        artifact_ids=(uuid4(),),
        origin="inferred",
        elapsed_ms=observation.elapsed_ms,
    )
    assert "private-path-canary" not in persisted.model_dump_json()
    assert persisted.observed_value == (
        origin + "/guide" if status == "satisfied" else "different origin/path"
    )


@pytest.mark.parametrize(
    "expected",
    [
        "https://user:secret@example.test/guide",
        "https://example.test/?token=secret",
        "https://example.test/#secret",
        "/relative",
        "javascript:alert(1)",
    ],
)
def test_public_path_oracle_rejects_private_or_nonabsolute_expected(expected: str) -> None:
    with pytest.raises(ValidationError):
        ExpectedAssertion(assertion_id="route", oracle="url_path_v1", expected_value=expected)


def test_safe_url_never_retains_userinfo() -> None:
    assert safe_url("https://user:secret@example.test/guide?token=secret#private") == (
        "https://example.test/guide"
    )
