"""One bounded deterministic case, using existing owned browser/step persistence.

The plan is model-generated separately. This executor is a deterministic fallback,
not an LLM persona, and never retries a submit or silently changes a case oracle.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

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
from markettwin_execution_orchestrator.browser.contracts import (
    BrowserActionResult,
    BrowserSessionHandle,
)
from markettwin_execution_orchestrator.browser.errors import BrowserActionError, BrowserPolicyError
from markettwin_execution_orchestrator.persistence import (
    ExecutionRepository,
    ExecutionStepRecorder,
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


async def perform_case_action(
    controller: BrowserController,
    handle: BrowserSessionHandle,
    action: CaseAction,
    scope: FeatureScope,
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


async def execute_test_case(
    *,
    request: PersonaJourneyExecutionRequest,
    case: TestCaseSpec,
    scope: FeatureScope,
    budget: PlanBudget,
    controller: BrowserController,
    session: AsyncSession,
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
    max_seconds = min(
        request.max_duration_seconds, case.estimated_seconds, budget.max_total_seconds
    )

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
    ) -> None:
        assert recorder is not None and handle is not None
        reserve_step()
        step_id = await recorder.start_step(
            action_type=action_type,
            action_summary=f"Deep case {case.case_id}: {action_type}.",
        )
        action_steps.append(step_id)
        try:
            observed = await operation()
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
        async with asyncio.timeout(max_seconds):
            handle = await browser_controller.create_session(
                execution_id=request.execution_id,
                journey_id=request.journey_id,
                allowed_origins=request.allowed_origins,
                network_policy=request.network_policy,
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
            for action in case.steps:
                await record_action(
                    action.action,
                    lambda action=action: perform_case_action(
                        browser_controller,
                        handle,
                        action,
                        scope,
                    ),
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
        blocker=blocker,
    )
    await event("test_case.completed", result.model_dump(mode="json"))
    return result
