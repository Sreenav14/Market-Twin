"""One bounded deterministic case, using existing owned browser/step persistence.

The plan is model-generated separately. This executor is a deterministic fallback,
not an LLM persona, and never retries a submit or silently changes a case oracle.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from markettwin_database.models import ExecutionSuspension
from markettwin_shared.auth_verification import AuthVerificationPolicy
from markettwin_shared.deep_testing import (
    AssertionResult,
    AssertionStatus,
    CaseBlocker,
    CaseExecutionResult,
    CaseExecutionStatus,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.agents.schemas.test_case import (
    CaseAction,
    FeatureScope,
    PlanBudget,
    TestCaseSpec,
    ensure_scope_url,
)
from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.browser.assertions import safe_url
from markettwin_execution_orchestrator.browser.auth_session_broker import (
    AuthSessionScope,
    AuthSessionSnapshot,
)
from markettwin_execution_orchestrator.browser.contracts import (
    BrowserActionResult,
    BrowserSessionHandle,
)
from markettwin_execution_orchestrator.browser.errors import BrowserActionError, BrowserPolicyError
from markettwin_execution_orchestrator.browser.sensitive_action_policy import (
    SensitiveActionIntent,
)
from markettwin_execution_orchestrator.persistence import (
    ExecutionRepository,
    ExecutionStepRecorder,
    ExecutionSuspensionRepository,
    HumanActionLifecycleRepository,
    S3ArtifactStorage,
    SessionArtifactRecorder,
)
from markettwin_execution_orchestrator.persistence.models import Artifact
from markettwin_execution_orchestrator.persistence.run_event_repository import RunEventRepository
from markettwin_execution_orchestrator.workflow.journey_executor import (
    PersonaJourneyExecutionRequest,
)


class CaseActionLimitError(RuntimeError):
    """No browser action was attempted after exhausting the deterministic cap."""


class AuthenticationVerificationBlocked(BrowserPolicyError):
    """Authentication was not verified before the case could continue."""


class SensitiveActionApprovalBlocked(BrowserPolicyError):
    """A policy-eligible browser action did not receive a valid approval."""


MAX_HUMAN_LOGIN_WAIT_SECONDS = 10 * 60


@asynccontextmanager
async def _pause_case_deadline(
    case_timer: asyncio.Timeout, *, allowance_seconds: float
) -> AsyncGenerator[None, None]:
    """Exclude bounded human wait from the deterministic case action budget."""
    deadline = case_timer.when()
    if deadline is None or allowance_seconds <= 0:
        raise ValueError("A live case deadline and positive wait allowance are required.")
    started = time.monotonic()
    # Keep a small margin so our own bounded wait expires before the outer timeout.
    case_timer.reschedule(deadline + allowance_seconds + 1)
    try:
        yield
    finally:
        case_timer.reschedule(deadline + time.monotonic() - started)


async def verify_or_request_login(
    *,
    request: PersonaJourneyExecutionRequest,
    controller: BrowserController,
    handle: BrowserSessionHandle,
    policy: AuthVerificationPolicy,
    auth_scope: AuthSessionScope,
    session: AsyncSession,
    max_wait_seconds: float,
) -> None:
    principal = await controller.verify_authenticated_role(handle=handle, policy=policy)
    if principal is not None:
        captured = await controller.capture_verified_auth_session(
            handle=handle, policy=policy, scope=auth_scope,
        )
        if captured is None:
            raise AuthenticationVerificationBlocked(
                "Authenticated identity could not be safely captured."
            )
        return

    expires_at = datetime.now(UTC) + timedelta(seconds=max_wait_seconds)
    lifecycle = HumanActionLifecycleRepository(session)
    try:
        request_id = await lifecycle.create_login_request(
            test_run_id=request.test_run_id,
            execution_id=request.execution_id,
            browser_session_id=handle.session_id,
            expires_at=expires_at,
        )
        await session.commit()
    except Exception as error:
        await session.rollback()
        raise AuthenticationVerificationBlocked(
            "A secure login handoff could not be created."
        ) from error

    deadline = min(expires_at, datetime.now(UTC) + timedelta(seconds=max_wait_seconds))
    checkpoint_created = False
    try:
        from markettwin_execution_orchestrator.browser.owner_service import (
            wait_for_human_action_resume,
        )

        while True:
            remaining = (deadline - datetime.now(UTC)).total_seconds()
            if remaining <= 0:
                raise TimeoutError
            state = await lifecycle.state(request_id=request_id)
            if state is None or state.request_status in {"cancelled", "expired"}:
                raise AuthenticationVerificationBlocked(
                    "The human login handoff ended before verification."
                )
            if state.control_mode == "verifying":
                if state.request_status == "leased" and not checkpoint_created:
                    remaining = max(0.001, (deadline - datetime.now(UTC)).total_seconds())
                    await ExecutionSuspensionRepository(session).create_waiting(
                        test_run_id=request.test_run_id,
                        journey_id=request.journey_id,
                        execution_id=request.execution_id,
                        browser_session_id=handle.session_id,
                        request_id=request_id,
                        last_durable_step_id=None,
                        owner_generation=state.control_generation,
                        phase="auth_preflight",
                        planned_step_index=0,
                        remaining=timedelta(seconds=remaining),
                        human_deadline=expires_at,
                    )
                    await session.commit()
                    checkpoint_created = True
                break
            if state.request_status == "completed":
                # Completed is valid only after our verifier commits it below.
                raise AuthenticationVerificationBlocked(
                    "The login handoff has an unexpected completed state."
                )
            if state.request_status == "leased" and state.control_mode in {
                "human_pending", "human",
            }:
                suspension = ExecutionSuspensionRepository(session)
                try:
                    await suspension.create_waiting(
                        test_run_id=request.test_run_id,
                        journey_id=request.journey_id,
                        execution_id=request.execution_id,
                        browser_session_id=handle.session_id,
                        request_id=request_id,
                        last_durable_step_id=None,
                        owner_generation=state.control_generation,
                        phase="auth_preflight",
                        planned_step_index=0,
                        remaining=timedelta(seconds=remaining),
                        human_deadline=expires_at,
                    )
                    await session.commit()
                    checkpoint_created = True
                except Exception as error:
                    await session.rollback()
                    raise AuthenticationVerificationBlocked(
                        "The human login checkpoint could not be persisted."
                    ) from error
                try:
                    await wait_for_human_action_resume(
                        request_id=request_id,
                        timeout_seconds=remaining,
                    )
                except TimeoutError:
                    raise
                except Exception as error:
                    raise AuthenticationVerificationBlocked(
                        "The human login handoff was interrupted."
                    ) from error
                continue
            await asyncio.sleep(min(0.25, remaining))

        state = await lifecycle.state(request_id=request_id)
        if state is None or state.request_status != "leased":
            raise AuthenticationVerificationBlocked(
                "The human login handoff is no longer active."
            )
        principal = await controller.verify_authenticated_role(handle=handle, policy=policy)
        if principal is not None:
            principal = await controller.capture_verified_auth_session(
                handle=handle, policy=policy, scope=auth_scope,
            )
        if principal is None:
            try:
                await controller.end_human_control(
                    session_id=handle.session_id,
                    execution_id=handle.execution_id,
                    journey_id=handle.journey_id,
                    verified=False,
                )
            except Exception:
                pass
            await lifecycle.finish_verification(
                request_id=request_id,
                expected_generation=state.control_generation,
                verified=False,
            )
            await session.commit()
            raise AuthenticationVerificationBlocked(
                "The signed-in identity did not match the approved role."
            )

        await lifecycle.finish_verification(
            request_id=request_id,
            expected_generation=state.control_generation,
            verified=True,
        )
        await session.commit()
        suspension_id = await session.scalar(
            select(ExecutionSuspension.id).where(
                ExecutionSuspension.pending_request_id == request_id,
                ExecutionSuspension.status == "ready",
            )
        )
        if suspension_id is None:
            raise AuthenticationVerificationBlocked(
                "The verified login continuation is unavailable."
            )
        await ExecutionSuspensionRepository(session).claim_ready(
            suspension_id=suspension_id
        )
        await session.commit()
        await controller.end_human_control(
            session_id=handle.session_id,
            execution_id=handle.execution_id,
            journey_id=handle.journey_id,
            verified=True,
            safe_to_capture=True,
        )
    except TimeoutError as error:
        await session.rollback()
        await lifecycle.abandon(request_id=request_id)
        await session.commit()
        raise AuthenticationVerificationBlocked(
            "The approved human login window expired."
        ) from error
    except asyncio.CancelledError:
        await session.rollback()
        await lifecycle.abandon(request_id=request_id)
        await session.commit()
        raise
    except AuthenticationVerificationBlocked:
        await session.rollback()
        await lifecycle.abandon(request_id=request_id)
        await session.commit()
        raise
    except Exception as error:
        await session.rollback()
        await lifecycle.abandon(request_id=request_id)
        await session.commit()
        raise AuthenticationVerificationBlocked(
            "The human login continuation failed closed."
        ) from error


async def perform_case_action(
    controller: BrowserController,
    handle: BrowserSessionHandle,
    action: CaseAction,
    scope: FeatureScope,
    approval_fingerprint: str | None = None,
) -> BrowserActionResult:
    owned: dict[str, Any] = {
        "session_id": handle.session_id,
        "execution_id": handle.execution_id,
        "journey_id": handle.journey_id,
    }
    target = action.target
    if action.action == "navigate":
        assert action.url is not None
        ensure_scope_url(action.url, scope)
        return await controller.navigate(**owned, url=action.url)
    if action.action == "set_viewport":
        assert action.preset is not None
        return await controller.set_viewport(**owned, preset=action.preset)
    if action.action == "focus_next":
        return await controller.focus_next(**owned)
    if action.action == "wait":
        assert action.milliseconds is not None
        return await controller.wait(**owned, milliseconds=action.milliseconds)
    assert target is not None
    scoped: dict[str, Any] = {
        **owned,
        "scope_role": target.scope_role,
        "scope_name": target.scope_name,
    }
    if action.action == "click":
        return await controller.click(
            **scoped,
            role=target.role,
            name=target.name,
            label=target.label,
            text=target.text,
            approval_fingerprint=approval_fingerprint,
        )
    assert target.label is not None
    if action.action in {"check", "uncheck"}:
        return await controller.set_checked(
            **scoped,
            label=target.label,
            checked=action.action == "check",
        )
    values = {item.key: item.value for item in scope.safe_test_data}
    assert action.test_value_key is not None
    value = values[action.test_value_key]
    if action.action == "fill":
        return await controller.fill(**scoped, label=target.label, value=value)
    return await controller.select(**scoped, label=target.label, value=value)


async def _approved_case_action(
    *,
    step_id: int,
    intent: SensitiveActionIntent,
    controller: BrowserController,
    handle: BrowserSessionHandle,
    recorder: ExecutionStepRecorder,
    case_timeout: asyncio.Timeout,
    request: PersonaJourneyExecutionRequest,
    action: CaseAction,
    scope: FeatureScope,
    planned_step_index: int,
) -> BrowserActionResult:
    origin = await controller.current_origin(
        session_id=handle.session_id,
        execution_id=handle.execution_id,
        journey_id=handle.journey_id,
    )
    try:
        async with _pause_case_deadline(
            case_timeout, allowance_seconds=MAX_HUMAN_LOGIN_WAIT_SECONDS
        ):
            deadline = case_timeout.when()
            remaining_ms = max(
                0,
                int(
                    (
                        deadline - asyncio.get_running_loop().time()
                        if deadline is not None
                        else 0
                    )
                    * 1000
                ),
            )
            approval_id = await recorder.begin_sensitive_action(
                step_id=step_id,
                intent=intent,
                current_origin=origin,
                browser_session_id=handle.session_id,
                planned_step_index=planned_step_index,
                remaining_ms=remaining_ms,
                revalidate_origin=lambda: controller.current_origin(
                    session_id=handle.session_id,
                    execution_id=handle.execution_id,
                    journey_id=handle.journey_id,
                ),
            )
        try:
            result = await perform_case_action(
                controller,
                handle,
                action,
                scope,
                approval_fingerprint=intent.fingerprint,
            )
        except BaseException:
            await asyncio.shield(
                recorder.finish_sensitive_action(
                    approval_id=approval_id,
                    outcome="uncertain",
                )
            )
            raise
        await recorder.finish_sensitive_action(
            approval_id=approval_id,
            outcome="completed",
        )
        return result
    except BrowserPolicyError:
        raise
    except Exception as error:
        raise SensitiveActionApprovalBlocked(
            "The exact sensitive action did not receive a usable approval."
        ) from error


async def execute_test_case(
    *,
    request: PersonaJourneyExecutionRequest,
    case: TestCaseSpec,
    scope: FeatureScope,
    budget: PlanBudget,
    controller: BrowserController,
    session: AsyncSession,
    auth_verification: AuthVerificationPolicy | None = None,
    auth_session_scope: AuthSessionScope | None = None,
    reuse_auth_session: bool = False,
) -> CaseExecutionResult:
    """Caller persists AgentExecution first and consumes result for legacy readiness."""
    browser_controller = controller
    if case.feature_key != scope.feature_key:
        raise ValueError("Case must belong to the caller-owned feature.")
    ensure_scope_url(request.start_url, scope)
    started = time.monotonic()
    events = RunEventRepository(session)
    repository = ExecutionRepository(session)
    action_steps: list[int] = []
    assertions: list[AssertionResult] = []
    status: CaseExecutionStatus = "completed"
    blocker: CaseBlocker | None = None
    handle: BrowserSessionHandle | None = None
    persisted_browser = False
    storage: S3ArtifactStorage | None = None
    recorder: ExecutionStepRecorder | None = None
    attempted_steps = 0
    stage = "browser_start"
    case_timer: asyncio.Timeout | None = None
    initial_deadline: float | None = None
    max_seconds = min(
        request.max_duration_seconds, case.estimated_seconds, budget.max_total_seconds
    )

    def human_wait_ms() -> int:
        deadline = case_timer.when() if case_timer is not None else None
        if deadline is None or initial_deadline is None:
            return 0
        return max(0, int((deadline - initial_deadline) * 1000))

    async def event(event_type: str, payload: dict[str, object]) -> None:
        await events.create(
            test_run_id=request.test_run_id,
            journey_id=request.journey_id,
            execution_id=request.execution_id,
            event_type=event_type,
            payload=payload,
        )
        await session.commit()

    def reserve_step() -> None:
        nonlocal attempted_steps
        if attempted_steps >= budget.max_steps:
            raise CaseActionLimitError
        attempted_steps += 1

    async def record_action(
        action_type: str,
        operation: Callable[[], Awaitable[BrowserActionResult]],
        approved_operation: Callable[[int], Awaitable[BrowserActionResult]] | None = None,
    ) -> None:
        assert recorder is not None and handle is not None
        reserve_step()
        step_id = await recorder.start_step(
            action_type=action_type,
            action_summary=f"Deep case {case.case_id}: {action_type}.",
        )
        action_steps.append(step_id)
        try:
            observed = (
                await approved_operation(step_id)
                if approved_operation is not None
                else await operation()
            )
        except BaseException as error:
            await recorder.finish_step(
                step_id=step_id,
                status="policy_blocked" if isinstance(error, BrowserPolicyError) else "failed",
                observation_summary=type(error).__name__,
            )
            if isinstance(error, BrowserActionError):
                try:
                    async with asyncio.timeout(3):
                        state = await browser_controller.get_state(
                            session_id=handle.session_id,
                            execution_id=request.execution_id,
                            journey_id=request.journey_id,
                        )
                        await recorder.record_failure_evidence(step_id=step_id, result=state)
                except Exception:
                    pass
            raise
        try:
            await recorder.record_evidence(step_id=step_id, result=observed)
            await recorder.finish_step(step_id=step_id, status="completed")
        except BaseException:
            await session.rollback()
            await recorder.finish_step(
                step_id=step_id,
                status="failed",
                observation_summary="Evidence persistence failed.",
            )
            raise

    await event(
        "test_case.started",
        {
            "schema_version": 1,
            "case_id": case.case_id,
            "execution_id": str(request.execution_id),
            "executor_mode": "deterministic_case_steps",
            "max_seconds": max_seconds,
            "max_steps": budget.max_steps,
        },
    )
    try:
        async with asyncio.timeout(max_seconds) as case_timeout:
            case_timer = case_timeout
            initial_deadline = case_timeout.when()
            auth_snapshot: AuthSessionSnapshot | None = None
            if auth_verification is not None and auth_session_scope is not None:
                if reuse_auth_session:
                    try:
                        auth_snapshot = browser_controller.take_auth_session_snapshot(
                            scope=auth_session_scope,
                            case_id=case.case_id,
                        )
                    except Exception:
                        # Missing/expired transferable state falls back to secure login.
                        auth_snapshot = None
            handle = await browser_controller.create_session(
                execution_id=request.execution_id,
                journey_id=request.journey_id,
                allowed_origins=request.allowed_origins,
                network_policy=request.network_policy,
                auth_snapshot=auth_snapshot,
                auth_only_origins=auth_verification.auth_only_origins if auth_verification else (),
                authenticated_session=auth_verification is not None,
            )
            stage = "browser_persistence"
            await repository.create_browser_session(
                browser_session_id=handle.session_id,
                execution_id=request.execution_id,
            )
            await session.commit()
            persisted_browser = True
            stage = "storage_setup"
            storage = await asyncio.to_thread(S3ArtifactStorage.from_environment)
            recorder = ExecutionStepRecorder(session, request.execution_id, storage)
            stage = "actions"
            await record_action(
                "navigate",
                lambda: browser_controller.navigate(
                    session_id=handle.session_id,
                    execution_id=request.execution_id,
                    journey_id=request.journey_id,
                    url=request.start_url,
                ),
            )
            if auth_verification is not None:
                if auth_session_scope is None:
                    raise AuthenticationVerificationBlocked(
                        "The approved authentication scope is unavailable."
                    )
                verified = await browser_controller.verify_authenticated_role(
                    handle=handle, policy=auth_verification,
                )
                if auth_snapshot is not None and verified is None:
                    browser_controller.revoke_auth_session_snapshot(scope=auth_session_scope)
                if verified is None:
                    async with _pause_case_deadline(
                        case_timeout, allowance_seconds=MAX_HUMAN_LOGIN_WAIT_SECONDS,
                    ):
                        await verify_or_request_login(
                            request=request, controller=browser_controller, handle=handle,
                            policy=auth_verification, auth_scope=auth_session_scope,
                            session=session, max_wait_seconds=MAX_HUMAN_LOGIN_WAIT_SECONDS,
                        )
                await event("test_case.authenticated", {
                    "schema_version": 1, "case_id": case.case_id,
                    "role": auth_verification.role, "origin": auth_verification.origin,
                    "auth_source": "reused_session" if auth_snapshot is not None and verified
                        else "human_or_existing_session",
                    "executor_mode": "deterministic_case_steps",
                    "feature_key": scope.feature_key,
                    "inventory_source": "frozen_feature_scope",
                    "requirements": [item.requirement_id for item in scope.requirements],
                    "full_application_coverage": False,
                })
            for action_index, action in enumerate(case.steps):
                if auth_verification is not None and auth_session_scope is not None:
                    verified = await browser_controller.verify_authenticated_role(
                        handle=handle, policy=auth_verification,
                    )
                    if verified is None:
                        browser_controller.revoke_auth_session_snapshot(scope=auth_session_scope)
                        async with _pause_case_deadline(
                            case_timeout, allowance_seconds=MAX_HUMAN_LOGIN_WAIT_SECONDS,
                        ):
                            await verify_or_request_login(
                                request=request, controller=browser_controller, handle=handle,
                                policy=auth_verification, auth_scope=auth_session_scope,
                                session=session, max_wait_seconds=MAX_HUMAN_LOGIN_WAIT_SECONDS,
                            )
                async def execute_case_action(
                    step_id: int,
                    action: CaseAction = action,
                    action_index: int = action_index,
                ) -> BrowserActionResult:
                    if action.action == "click":
                        assert action.target is not None
                        target = action.target
                        intent = await browser_controller.inspect_click_approval(
                            session_id=handle.session_id,
                            execution_id=request.execution_id,
                            journey_id=request.journey_id,
                            role=target.role,
                            name=target.name,
                            label=target.label,
                            text=target.text,
                            scope_role=target.scope_role,
                            scope_name=target.scope_name,
                        )
                        if intent is not None:
                            return await _approved_case_action(
                                step_id=step_id,
                                intent=intent,
                                controller=browser_controller,
                                handle=handle,
                                recorder=recorder,
                                case_timeout=case_timeout,
                                request=request,
                                action=action,
                                scope=scope,
                                planned_step_index=action_index,
                            )
                    return await perform_case_action(
                        browser_controller,
                        handle,
                        action,
                        scope,
                    )

                await record_action(
                    action.action_id or action.action,
                    lambda action=action: perform_case_action(
                        browser_controller, handle, action, scope
                    ),
                    approved_operation=execute_case_action,
                )
            for expected in case.expected:
                stage = "assertions"
                reserve_step()
                step_id = await recorder.start_step(
                    action_type="assertion",
                    action_summary=f"Assert {expected.assertion_id}.",
                )
                try:
                    browser_result, observation = await browser_controller.read_assertion(
                        session_id=handle.session_id,
                        execution_id=request.execution_id,
                        journey_id=request.journey_id,
                        assertion=expected,
                    )
                    await recorder.record_evidence(step_id=step_id, result=browser_result)
                    artifact_ids = tuple(
                        await session.scalars(
                            select(Artifact.id).where(
                                Artifact.execution_id == request.execution_id,
                                Artifact.step_id == step_id,
                            )
                        )
                    )
                    assertion = AssertionResult(
                        case_id=case.case_id,
                        assertion_id=expected.assertion_id,
                        oracle=expected.oracle,
                        expected_value=(
                            safe_url(str(expected.expected_value))
                            if expected.oracle == "url"
                            else expected.expected_value
                        ),
                        observed_value=observation.observed_value,
                        status=observation.status if artifact_ids else "unverified",
                        execution_id=request.execution_id,
                        step_id=step_id,
                        artifact_ids=artifact_ids,
                        origin=expected.origin,
                        requirement_refs=expected.requirement_refs,
                        elapsed_ms=observation.elapsed_ms,
                        reason=observation.reason if artifact_ids else "missing_evidence",
                    )
                    await recorder.finish_step(
                        step_id=step_id,
                        status="completed",
                        observation_summary=json.dumps(assertion.model_dump(mode="json")),
                    )
                except BaseException:
                    await session.rollback()
                    await recorder.finish_step(
                        step_id=step_id,
                        status="failed",
                        observation_summary="Assertion unavailable.",
                    )
                    raise
                assertions.append(assertion)
                await event("test_case.assertion", assertion.model_dump(mode="json"))
    except BrowserPolicyError:
        status, blocker = "policy_blocked", "policy_blocked"
    except BrowserActionError as error:
        status, blocker = "failed", "action_failed"
        await event("test_case.diagnostic", {"schema_version": 1, "case_id": case.case_id,
                    "stage": stage, "error_type": type(error).__name__,
                    "reason_code": error.reason_code})
    except CaseActionLimitError:
        status, blocker = "budget_exhausted", "action_limit"
    except TimeoutError:
        status, blocker = "timed_out", "time_limit"
    except asyncio.CancelledError:
        status, blocker = "cancelled", "cancelled"
        await session.rollback()
        cancelled = CaseExecutionResult(
            case_id=case.case_id,
            execution_id=request.execution_id,
            execution_status=status,
            verdict="unverified",
            action_step_ids=tuple(action_steps),
            assertion_results=tuple(assertions),
            elapsed_ms=int((time.monotonic() - started) * 1000),
            human_wait_ms=human_wait_ms(),
            blocker=blocker,
        )
        await event("test_case.completed", cancelled.model_dump(mode="json"))
        raise
    except Exception as error:
        await session.rollback()
        status, blocker = "failed", "runtime_failed"
        await event(
            "test_case.diagnostic",
            {
                "schema_version": 1,
                "case_id": case.case_id,
                "stage": stage,
                "error_type": type(error).__name__,
            },
        )
    finally:
        if handle is not None:
            try:
                async with asyncio.timeout(10):
                    artifacts = await browser_controller.close_session(session_id=handle.session_id)
                    if storage is not None:
                        await SessionArtifactRecorder(
                            session, request.execution_id, storage
                        ).record(
                            artifacts,
                        )
                    if persisted_browser:
                        await repository.mark_browser_session_closed(
                            browser_session_id=handle.session_id
                        )
                        await session.commit()
            except Exception as error:
                await session.rollback()
                if status == "completed":
                    status, blocker = "failed", "runtime_failed"
                await event(
                    "test_case.diagnostic",
                    {
                        "schema_version": 1,
                        "case_id": case.case_id,
                        "stage": "cleanup",
                        "error_type": type(error).__name__,
                    },
                )
    verdict: AssertionStatus = "unverified"
    if (
        status == "completed"
        and len(assertions) == len(case.expected)
        and all(item.status != "unverified" for item in assertions)
    ):
        verdict = (
            "not_satisfied"
            if any(item.status == "not_satisfied" for item in assertions)
            else "satisfied"
        )
    result = CaseExecutionResult(
        case_id=case.case_id,
        execution_id=request.execution_id,
        execution_status=status,
        verdict=verdict,
        action_step_ids=tuple(action_steps),
        assertion_results=tuple(assertions),
        elapsed_ms=int((time.monotonic() - started) * 1000),
        human_wait_ms=human_wait_ms(),
        blocker=blocker,
    )
    await event("test_case.completed", result.model_dump(mode="json"))
    return result
