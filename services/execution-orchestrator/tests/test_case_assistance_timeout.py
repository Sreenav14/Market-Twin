"""A timed-out non-login assistance request blocks one case, not the run.

T-1B-C1: the click-preflight recovery wait expires unanswered and the
case finishes ``policy_blocked`` with the blocker naming the timeout.
T-1B-C2: the answered-in-time recovery path is unchanged at case level.
Doubles mirror ``test_case_assertions.py``; the lifecycle/suspension
doubles mirror ``test_workflow_auth_handoff.py``.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.agents.schemas.test_case import (
    FeatureScope,
    PlanBudget,
    TestCaseSpec,
)
from markettwin_execution_orchestrator.browser.contracts import (
    AllowedOrigin,
    BrowserActionResult,
    BrowserObservation,
    BrowserSessionArtifacts,
    BrowserSessionHandle,
)
from markettwin_execution_orchestrator.browser.assertions import AssertionObservation
from markettwin_execution_orchestrator.browser.errors import BrowserActionError
from markettwin_execution_orchestrator.persistence.human_action_lifecycle_repository import (
    HumanActionState,
)
from markettwin_execution_orchestrator.workflow import case_execution
from markettwin_execution_orchestrator.workflow.case_execution import (
    PersonaJourneyExecutionRequest,
)
from markettwin_execution_orchestrator.workflow.feature_scope import case_journey
from markettwin_shared.feature_plan import CaseAction, ExpectedAssertion, SemanticTarget


def _browser_action_result(action: str) -> BrowserActionResult:
    return BrowserActionResult(
        action=action,
        observation=BrowserObservation(
            url="https://example.test/checkout", title="Checkout", aria_snapshot="",
            viewport_width=1280, viewport_height=720, scroll_y=0, document_height=720,
        ),
    )


def _future_state(request_status: str, control_mode: str, generation: int) -> HumanActionState:
    return HumanActionState(
        request_status, control_mode, generation,
        datetime.now(UTC) + timedelta(minutes=2),
    )


class _EmptyArtifacts:
    async def record(self, _artifacts: BrowserSessionArtifacts) -> None:
        pass


class _FakeSession:
    def __init__(self, suspension_id: object) -> None:
        self.latest_artifact: object = None
        self._suspension_id = suspension_id

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def scalar(self, _query: object) -> object:
        return self._suspension_id

    async def scalars(self, _query: object) -> list[object]:
        return [self.latest_artifact] if self.latest_artifact else []


class _FakeEvents:
    def __init__(self, _session: object) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def create(
        self, *, event_type: str, payload: dict[str, Any], **_kwargs: object
    ) -> None:
        self.events.append((event_type, payload))


class _FakeExecutionRepository:
    def __init__(self, _session: object) -> None:
        pass

    async def create_browser_session(self, **_kwargs: object) -> None:
        pass

    async def mark_browser_session_closed(self, **_kwargs: object) -> None:
        pass


class _FakeRecorder:
    def __init__(self, session: _FakeSession, _execution_id: object, _storage: object) -> None:
        self.session = session
        self.next_step_id = 0
        self.steps: list[tuple[int, str, str | None]] = []
        self.evidence: dict[int, object] = {}

    async def start_step(self, *, action_type: str, action_summary: str) -> int:
        self.next_step_id += 1
        self.steps.append((self.next_step_id, action_type, None))
        return self.next_step_id

    async def record_evidence(self, *, step_id: int, result: BrowserActionResult) -> None:
        artifact_id = uuid4()
        self.evidence[step_id] = artifact_id
        self.session.latest_artifact = artifact_id

    async def record_failure_evidence(self, *, step_id: int, result: object) -> None:
        pass

    async def finish_step(
        self, *, step_id: int, status: str, observation_summary: str | None = None,
    ) -> None:
        self.steps = [
            (item_id, action, observation_summary if item_id == step_id else summary)
            for item_id, action, summary in self.steps
        ]


class _FakeLifecycle:
    """States are consumed in order; the last one repeats."""

    def __init__(self, request_id: object, states: list[HumanActionState]) -> None:
        self.request_id = request_id
        self._states = list(states)
        self.abandoned: list[object] = []
        self.finished: list[dict[str, Any]] = []

    async def create_login_request(self, **_kwargs: object) -> object:
        return self.request_id

    async def state(self, *, request_id: object) -> HumanActionState:
        if len(self._states) > 1:
            return self._states.pop(0)
        return self._states[0]

    async def abandon(self, *, request_id: object) -> None:
        self.abandoned.append(request_id)

    async def finish_verification(self, **kwargs: Any) -> None:
        self.finished.append(kwargs)


class _FakeSuspensionRepository:
    def __init__(self, _session: object) -> None:
        self.created: list[dict[str, Any]] = []
        self.claimed: list[object] = []

    async def create_waiting(self, **kwargs: Any) -> None:
        self.created.append(kwargs)

    async def claim_ready(self, *, suspension_id: object) -> None:
        self.claimed.append(suspension_id)


class _RecoveryController:
    """The click preflight raises ``absent_target`` until the human helps."""

    def __init__(self, execution_id: object, journey_id: object, *, answered: bool) -> None:
        self.handle = BrowserSessionHandle(execution_id, journey_id, uuid4())  # type: ignore[arg-type]
        self.answered = answered
        self.inspect_calls = 0
        self.click_calls = 0

    async def __aenter__(self) -> "_RecoveryController":
        return self

    async def __aexit__(self, *_args: object) -> None:
        pass

    async def create_session(self, **_kwargs: object) -> BrowserSessionHandle:
        return self.handle

    def bind_cooperative_pause_handler(self, *_args: object) -> None:
        pass

    def bind_authentication_handler(self, *_args: object) -> None:
        pass

    async def cooperative_checkpoint(self, _handle: BrowserSessionHandle) -> None:
        pass

    async def navigate(self, **_kwargs: object) -> BrowserActionResult:
        return _browser_action_result("navigate")

    async def inspect_click_approval(self, **_kwargs: object) -> None:
        self.inspect_calls += 1
        if self.inspect_calls == 1 or not self.answered:
            raise BrowserActionError(
                "The planned target is absent.", reason_code="absent_target",
            )
        return None

    async def verify_recovery_target(self, **_kwargs: object) -> bool:
        return True

    async def read_assertion(
        self, *, assertion: ExpectedAssertion, **_kwargs: object
    ) -> tuple[BrowserActionResult, AssertionObservation]:
        return _browser_action_result("assertion"), AssertionObservation(
            "satisfied", True, 1,
        )

    async def click(self, **_kwargs: object) -> BrowserActionResult:
        self.click_calls += 1
        return _browser_action_result("click")

    async def end_human_control(self, **_kwargs: object) -> None:
        pass

    async def close_session(self, **_kwargs: object) -> BrowserSessionArtifacts:
        return BrowserSessionArtifacts()


async def _run_case(
    monkeypatch: pytest.MonkeyPatch,
    *,
    answered: bool,
    lifecycle_states: list[HumanActionState],
    wait_seconds: float,
) -> tuple[Any, _FakeEvents, _RecoveryController, _FakeLifecycle]:
    execution_id, journey_id, run_id = uuid4(), uuid4(), uuid4()
    request_id, suspension_id = uuid4(), uuid4()
    target = SemanticTarget(role="link", name="Privacy Policy")
    case = TestCaseSpec(
        case_id="privacy_policy_link", feature_key="checkout",
        title="Privacy Policy link", kind="happy_path",
        steps=(CaseAction(action="click", target=target),),
        expected=(
            ExpectedAssertion(
                assertion_id="privacy_policy_enabled", oracle="enabled",
                target=target, expected_value=True,
                after_step_ordinal=1,
            ),
        ),
    )
    scope = FeatureScope(
        feature_key="checkout", goal="Check the privacy policy link",
        starting_url="https://example.test/checkout",
        allowed_origins=("https://example.test",),
    )
    request = PersonaJourneyExecutionRequest(
        test_run_id=run_id, execution_id=execution_id, journey_id=journey_id,
        persona_id=uuid4(), mission_id=uuid4(), journey=case_journey(case),
        start_url=scope.starting_url,
        allowed_origins=(AllowedOrigin(scheme="https", hostname="example.test"),),
        max_duration_seconds=30,
    )
    session = _FakeSession(suspension_id)
    events = _FakeEvents(session)
    recorder = _FakeRecorder(session, execution_id, object())
    lifecycle = _FakeLifecycle(request_id, lifecycle_states)
    suspension_repo = _FakeSuspensionRepository(session)
    browser = _RecoveryController(execution_id, journey_id, answered=answered)
    monkeypatch.setattr(case_execution, "RunEventRepository", lambda _session: events)
    monkeypatch.setattr(case_execution, "ExecutionRepository", _FakeExecutionRepository)
    monkeypatch.setattr(case_execution, "ExecutionStepRecorder", lambda *_args: recorder)
    monkeypatch.setattr(
        case_execution, "SessionArtifactRecorder", lambda *_args: _EmptyArtifacts(),
    )
    monkeypatch.setattr(
        case_execution.S3ArtifactStorage, "from_environment",
        classmethod(lambda _cls: object()),
    )
    monkeypatch.setattr(case_execution, "BrowserController", lambda: browser)
    monkeypatch.setattr(
        case_execution, "HumanActionLifecycleRepository", lambda _session: lifecycle,
    )
    monkeypatch.setattr(
        case_execution, "ExecutionSuspensionRepository", lambda _session: suspension_repo,
    )
    monkeypatch.setattr(case_execution, "MAX_HUMAN_LOGIN_WAIT_SECONDS", wait_seconds)
    from markettwin_execution_orchestrator.workflow import cooperative_pause

    async def no_pause_finalization(
        _session: object, _handle: BrowserSessionHandle,
    ) -> None:
        pass

    monkeypatch.setattr(cooperative_pause, "finalize_browser_pauses", no_pause_finalization)
    if answered:
        from markettwin_execution_orchestrator.browser import owner_service

        monkeypatch.setattr(owner_service, "wait_for_human_action_resume", AsyncMock())
    result = await case_execution.execute_test_case(
        request=request, case=case, scope=scope, budget=PlanBudget(max_steps=8),
        controller=browser, session=session,
    )
    return result, events, browser, lifecycle


@pytest.mark.asyncio
async def test_case_blocked_with_named_reason_when_recovery_assistance_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, events, browser, lifecycle = await _run_case(
        monkeypatch,
        answered=False,
        lifecycle_states=[_future_state("pending", "agent", 1)],
        wait_seconds=0.2,
    )
    assert result.execution_status == "policy_blocked"
    assert result.blocker == "human_assistance_timeout"
    assert result.verdict == "unverified"
    assert result.human_wait_ms > 0
    kinds = [kind for kind, _payload in events.events]
    requested = next(
        payload for kind, payload in events.events
        if kind == "test_case.assistance_requested"
    )
    assert requested["reason_code"] == "absent_target"
    diagnostic = next(
        payload for kind, payload in events.events if kind == "test_case.diagnostic"
    )
    assert diagnostic["reason_code"] == "human_assistance_timeout"
    assert kinds.index("test_case.assistance_requested") < kinds.index(
        "test_case.diagnostic"
    )
    # The request was abandoned by the wait; verification never ran and
    # the preflight was never retried.
    assert lifecycle.abandoned == [lifecycle.request_id]
    assert lifecycle.finished == []
    assert browser.inspect_calls == 1
    assert browser.click_calls == 0


@pytest.mark.asyncio
async def test_case_recovery_answered_in_time_retries_preflight_and_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, events, browser, lifecycle = await _run_case(
        monkeypatch,
        answered=True,
        lifecycle_states=[
            _future_state("leased", "human_pending", 2),
            _future_state("leased", "verifying", 3),
        ],
        wait_seconds=30,
    )
    assert result.execution_status == "completed"
    assert result.blocker is None
    kinds = [kind for kind, _payload in events.events]
    assert "test_case.assistance_requested" in kinds
    assert "test_case.assistance_resumed" in kinds
    assert kinds.index("test_case.assistance_requested") < kinds.index(
        "test_case.assistance_resumed"
    )
    diagnostics = [
        payload for kind, payload in events.events if kind == "test_case.diagnostic"
    ]
    assert all(
        payload.get("reason_code") != "human_assistance_timeout"
        for payload in diagnostics
    )
    # Only the read-only preflight was retried; the click then ran once.
    assert browser.inspect_calls == 2
    assert browser.click_calls == 1
    assert lifecycle.abandoned == []
    assert lifecycle.finished == [
        {
            "request_id": lifecycle.request_id,
            "expected_generation": 3,
            "verified": True,
        }
    ]
