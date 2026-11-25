"""One bounded deterministic case, using existing owned browser/step persistence.

The plan is model-generated separately. This executor is a deterministic fallback,
not an LLM persona, and never retries a submit or silently changes a case oracle.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

from markettwin_database.models import ExecutionSuspension, RunEvent, TestRun
from markettwin_shared.auth_verification import AuthVerificationPolicy
from markettwin_shared.deep_testing import (
    AssertionResult,
    AssertionStatus,
    CaseBlocker,
    CaseExecutionResult,
    CaseExecutionStatus,
)
from markettwin_shared.action_approval import SensitiveActionRule
from markettwin_shared.feature_plan import ExpectedAssertion
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.agents.schemas.journey import PersonaJourneySpec
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
    AuthSessionReuseRejected,
    AuthSessionScope,
    AuthSessionSnapshot,
)
from markettwin_execution_orchestrator.browser.contracts import (
    AllowedOrigin,
    BrowserActionResult,
    BrowserSessionHandle,
    NetworkPolicy,
)
from markettwin_execution_orchestrator.browser.errors import (
    BrowserActionBlockedError,
    BrowserActionError,
    BrowserPolicyError,
    HumanAssistanceSkipped,
)
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
from markettwin_execution_orchestrator.expectations import login_skill
from markettwin_execution_orchestrator.workflow.harness_items import run_safety_mode


@dataclass(frozen=True, slots=True)
class PersonaJourneyExecutionRequest:
    """Everything required to execute one already-planned Journey."""

    test_run_id: UUID
    execution_id: UUID
    journey_id: UUID
    persona_id: UUID
    mission_id: UUID

    journey: PersonaJourneySpec

    start_url: str
    allowed_origins: tuple[AllowedOrigin, ...]

    auth_verification: AuthVerificationPolicy | None = None
    auth_session_scope: AuthSessionScope | None = None
    auth_mode: Literal["required", "optional"] = "required"
    runtime_human_assistance: bool = False
    runtime_target_id: UUID | None = None
    network_policy: NetworkPolicy = "public_only"
    max_duration_seconds: int = 180
    viewport_preset: Literal["mobile320", "desktop1280"] = "desktop1280"
    fixture_action_rules: tuple[SensitiveActionRule, ...] = ()


@dataclass(frozen=True, slots=True)
class BrowserHandoffExecution:
    test_run_id: UUID
    execution_id: UUID
    journey_id: UUID
    allowed_origins: tuple[AllowedOrigin, ...]


class CaseActionLimitError(RuntimeError):
    """No browser action was attempted after exhausting the deterministic cap."""


class AuthenticationVerificationBlocked(BrowserPolicyError):
    """Authentication was not verified before the case could continue."""


class AuthenticationChallengeBlocked(AuthenticationVerificationBlocked):
    """Released login control without establishing the approved signed-in state."""


class HumanAssistanceTimeoutError(AuthenticationVerificationBlocked):
    """A non-login human assistance window expired unanswered."""


class SensitiveActionApprovalBlocked(BrowserPolicyError):
    """A policy-eligible browser action did not receive a valid approval."""


MAX_HUMAN_LOGIN_WAIT_SECONDS = 10 * 60
# Unified park (U-P4): the spec's live-park default — 15 minutes for
# the human to log in while the Room stays open, in the same context.
HARNESS_PARK_WAIT_SECONDS = 15 * 60
OPAQUE_CONFIRMATION_REASON = "An opaque confirmation requires human browser takeover."


def _precondition_target_matches(expected: ExpectedAssertion, next_action: CaseAction) -> bool:
    """Whether a point-of-use check guards the action that follows it.

    Approved contract checks are translated from ContractAssertion, which
    carries role/name only, while the replayed action target also keeps the
    scope recorded at discovery. Strict target equality therefore never
    matched for a control inside a named form or region, and its failed
    visible/enabled check was not recognised as a failed precondition.
    A scope recorded on the check itself must still match exactly; an
    unscoped check matches the same role/name (or label/text) in any scope.
    """
    expected_target = expected.target
    action_target = next_action.target
    if expected_target is None or action_target is None:
        return False
    if (expected_target.role, expected_target.name, expected_target.label,
            expected_target.text) != (action_target.role, action_target.name,
                                      action_target.label, action_target.text):
        return False
    if expected_target.scope_role is None:
        return True
    return (expected_target.scope_role, expected_target.scope_name) == (
        action_target.scope_role, action_target.scope_name,
    )


def _is_failed_action_precondition(
    expected: ExpectedAssertion,
    observed: AssertionResult,
    next_action: CaseAction | None,
) -> bool:
    return (
        next_action is not None
        and expected.origin == "user_approved"
        and expected.oracle in {"visible", "enabled"}
        and _precondition_target_matches(expected, next_action)
        and observed.status == "not_satisfied"
    )


@asynccontextmanager
async def pause_case_deadline(
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
        if not case_timer.expired():
            case_timer.reschedule(deadline + time.monotonic() - started)


async def _run_event(
    session: AsyncSession,
    request: PersonaJourneyExecutionRequest | BrowserHandoffExecution,
    event_type: str,
    payload: dict[str, object],
) -> None:
    await RunEventRepository(session).create(
        test_run_id=request.test_run_id,
        event_type=event_type,
        payload=payload,
        journey_id=request.journey_id,
        execution_id=request.execution_id,
    )
    await session.commit()


async def _attempt_login_skill(
    *,
    request: PersonaJourneyExecutionRequest | BrowserHandoffExecution,
    controller: BrowserController,
    handle: BrowserSessionHandle,
    policy: AuthVerificationPolicy | None,
    auth_scope: AuthSessionScope | None,
    session: AsyncSession,
) -> bool:
    """Doc 21 section 13.3: replay the compiled login skill, if any.

    Returns True only when the replay authenticated the session. Every
    other outcome falls back to the human handoff verbatim; an
    unresolvable credential key is named in a login_skill_refused event.
    """
    try:
        run = await session.get(TestRun, request.test_run_id)
        snapshot = run.configuration_snapshot if run is not None else {}
        block = snapshot.get("app_map") if isinstance(snapshot, dict) else None
        map_id = block.get("map_id") if isinstance(block, dict) else None
        if not isinstance(map_id, str):
            return False
        app_map_id = UUID(map_id)
        version = await login_skill.select_login_version(
            session, app_map_id=app_map_id
        )
        if version is None:
            return False
        from markettwin_execution_orchestrator.workflow.run_request import (
            _parse_approved_test_data,
        )

        values = {
            entry.key: entry.value
            for entry in _parse_approved_test_data(snapshot)
        }
        allowed, refusal_key = login_skill.login_mode_allowed(
            run_mode=run_safety_mode(snapshot),
            is_persona_run=(run.run_kind == "persona" if run else False),
            approved_keys=set(values),
        )
        if refusal_key is not None:
            await _run_event(
                session,
                request,
                "login_skill_refused",
                {
                    "reason": "NOT_EXERCISED_UNAPPROVED_DATA",
                    "key": refusal_key,
                },
            )
            return False
        if not allowed:
            return False
        definition = version.definition_json or {}
        origins = tuple(
            f"{origin.scheme}://{origin.hostname}"
            + (f":{origin.port}" if origin.port else "")
            for origin in request.allowed_origins
        )
        succeeded, failure_step, failure_site = (
            await login_skill.replay_login_definition(
                controller,
                handle,
                definition=definition,
                values=values,
                allowed_origins=origins,
                policy=policy,
            )
        )
        await login_skill.record_login_replay(
            session,
            version=version,
            app_map_id=app_map_id,
            result="passed" if succeeded else "failed",
            failure_step=failure_step,
            failure_site=failure_site,
        )
        await session.commit()
        if not succeeded:
            return False
        if policy is not None and auth_scope is not None:
            captured = await controller.capture_verified_auth_session(
                handle=handle, policy=policy, scope=auth_scope
            )
            if captured is None:
                return False
        return True
    except Exception as error:  # noqa: BLE001 - the handoff is the fallback
        await session.rollback()
        await _run_event(
            session, request, "login_skill_failed", {"error_type": type(error).__name__},
        )
        await session.commit()
        return False


async def _compile_login_skill_after_handoff(
    *,
    request: PersonaJourneyExecutionRequest | BrowserHandoffExecution,
    controller: BrowserController,
    handle: BrowserSessionHandle,
    session: AsyncSession,
) -> None:
    """Doc 21 sections 13.2-13.3: compile the login skill from the graph
    after a successful handoff. Failures are recorded, never raised."""
    try:
        run = await session.get(TestRun, request.test_run_id)
        snapshot = run.configuration_snapshot if run is not None else {}
        block = snapshot.get("app_map") if isinstance(snapshot, dict) else None
        map_id = block.get("map_id") if isinstance(block, dict) else None
        if not isinstance(map_id, str):
            return
        from markettwin_database.models.knowledge import AppMap

        app_map = await session.get(AppMap, UUID(map_id))
        if app_map is None:
            return
        result = await controller.get_page_index(
            session_id=handle.session_id,
            execution_id=handle.execution_id,
            journey_id=handle.journey_id,
            cursor=0,
        )
        signature = hashlib.sha256(
            " ".join(result.observation.aria_snapshot.split()).encode()
        ).hexdigest()
        version = await login_skill.compile_login_skill(
            session,
            app_map=app_map,
            landing_url=result.observation.url,
            landing_signature=signature,
        )
        await session.commit()
        if version is not None:
            await _run_event(
                session,
                request,
                "login_skill_compiled",
                {"skill_version_id": str(version.id)},
            )
    except Exception as error:  # noqa: BLE001 - recorded, never raised
        await session.rollback()
        try:
            await _run_event(
                session,
                request,
                "login_skill_compile_failed",
                {"error": f"{type(error).__name__}: {error}"},
            )
        except Exception:  # noqa: BLE001
            await session.rollback()


async def execute_skill_replay(
    *,
    request: PersonaJourneyExecutionRequest,
    controller: BrowserController,
    handle: BrowserSessionHandle,
    session: AsyncSession,
    skill_entry: dict[str, object],
    board_item_ref: str,
    requesting_case: TestCaseSpec | None = None,
) -> dict[str, object]:
    """Doc 22 section 8.4: replay one served skill inside the run's
    own browser session and record the consumption replay
    (skill_replays, context 'run', zero model calls — a replay never
    calls a model).

    Outcomes: 'passed' (the terminal assertion held), 'failed' (a
    step failed to execute — a locator-shaped divergence: the
    active version demotes to suspect, section 8.4.3), 'diverged'
    (the steps completed but the terminal assertion did not hold —
    an assertion-shaped divergence: the active version is
    quarantined in the same step, section 8.4.2, and no heal is
    attempted), 'mode_filtered' (the execution-time mode re-check
    of section 8.3 refused: nothing replays, nothing is
    recorded)."""
    from markettwin_database.models.knowledge import (
        SkillReplay,
        SkillUsageEvent,
        SkillVersion,
    )
    from markettwin_shared.app_map_common import (
        canonical_url,
        check_skill_transition,
    )
    from markettwin_shared.feature_plan import FeatureScope, TestCaseSpec

    from markettwin_execution_orchestrator.harvest.harvest_capture import (
        capture_state,
    )
    from markettwin_execution_orchestrator.harvest.harvest_inventory import (
        distil_elements,
        distil_forms,
        identity_for,
    )
    from markettwin_execution_orchestrator.workflow.run_request import (
        _parse_approved_test_data,
    )
    from markettwin_execution_orchestrator.workflow.skill_filter import (
        skill_selectability,
        task_case_mismatch,
    )

    run = await session.get(TestRun, request.test_run_id)
    snapshot = run.configuration_snapshot if run is not None else {}
    if not isinstance(snapshot, dict):
        snapshot = {}
    approved = _parse_approved_test_data(snapshot)
    definition = skill_entry.get("definition")
    reason = skill_selectability(
        definition,
        mode=run_safety_mode(snapshot),
        approved_keys={entry.key for entry in approved},
    )
    if reason is not None:
        return {"status": "mode_filtered", "reason": reason}
    assert isinstance(definition, dict)
    if requesting_case is not None and isinstance(definition.get("task"), dict):
        # Skill-replay selection (doc 29 section 7 as amended): a
        # task skill handed to this executor FOR a specific case
        # must be that case's contract -- steps, targets and the
        # case's own expected outcomes, with value-bound outcomes
        # asserting this run's approved values. The digest half of
        # the check lives in the matcher (the definition here may
        # already be rebound, and the digest covers stored
        # values), so equivalence is what is re-verified, before
        # any browser action and before anything is recorded.
        mismatch = task_case_mismatch(
            definition,
            requesting_case,
            approved_values={entry.key: entry.value for entry in approved},
            start_url=getattr(request, "start_url", None),
            check_digest=False,
        )
        if mismatch is not None:
            return {"status": "refused", "reason": mismatch}
    block = snapshot.get("app_map")
    if not isinstance(block, dict):
        block = {}
    map_id = block.get("map_id")
    try:
        version_id = UUID(str(skill_entry.get("skill_version_id")))
    except ValueError:
        return {"status": "refused", "reason": "invalid_skill_version_id"}
    try:
        app_map_id = UUID(map_id) if isinstance(map_id, str) else None
    except ValueError:
        return {"status": "refused", "reason": "invalid_app_map_id"}
    native = {
        key: definition[key]
        for key in (
            "case_id",
            "feature_key",
            "title",
            "kind",
            "steps",
            "expected",
        )
        if key in definition
    }
    native.setdefault("safety", "non_destructive")
    native.setdefault("estimated_seconds", 60)
    spec = TestCaseSpec.model_validate(native)
    from markettwin_execution_orchestrator.workflow.feature_scope import origin_url

    origins = tuple(origin_url(origin) for origin in request.allowed_origins)
    first_url = next(
        (step.url for step in spec.steps if step.action == "navigate" and step.url),
        f"{origins[0]}/" if origins else "",
    )
    scope = FeatureScope(
        feature_key=spec.feature_key,
        goal="Replay a library skill for this run.",
        starting_url=first_url,
        allowed_origins=origins,
        safe_test_data=approved,
    )
    started = datetime.now(UTC)
    failure_step: int | None = None
    failure_site: str | None = None
    diverged = False
    terminal_state_match: bool | None = None
    per_step: list[dict[str, object]] = []
    from markettwin_execution_orchestrator.workflow.skill_assertions import check_skill_assertions

    async def check_skill_checkpoint(checkpoint: int | None) -> str | None:
        return await check_skill_assertions(
            controller, handle, spec, checkpoint=checkpoint,
            approved_values=tuple(value.value for value in approved),
            run_mode=run_safety_mode(snapshot),
        )

    for index, action in enumerate(spec.steps):
        try:
            failed_assertion = await check_skill_checkpoint(index)
            if failed_assertion:
                diverged = True
                failure_site = f"skill_assertion:{failed_assertion}"
                break
            await perform_case_action(controller, handle, action, scope)
        except Exception as exc:  # noqa: BLE001 - recorded as the failure
            failure_step = index
            failure_site = f"case_execution:{type(exc).__name__}"
            per_step.append({"order": index, "result": "failed"})
            break
        per_step.append({"order": index, "result": "passed"})
    if failure_step is None and not diverged:
        try:
            failed_assertion = (
                await check_skill_checkpoint(len(spec.steps))
                or await check_skill_checkpoint(None)
            )
            capture = await capture_state(
                controller,
                handle,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
            )
            elements = distil_elements(capture)
            forms = distil_forms(capture)
            live_state_id, _, _ = identity_for(capture.url, elements, forms)
            assertion = definition.get("success_assertion") or {}
            url_ok = canonical_url(capture.url) == canonical_url(
                str(assertion.get("url") or "")
            )
            state_ok = live_state_id == assertion.get("state_id")
            if not state_ok and assertion.get("signature_superset_fallback"):
                harvested = set(assertion.get("element_signature") or [])
                live = {
                    f"{element['role']}|{element['name']}"
                    for element in elements
                }
                state_ok = bool(harvested) and harvested <= live
            terminal_state_match = url_ok and state_ok and failed_assertion is None
            if failed_assertion:
                failure_site = f"skill_assertion:{failed_assertion}"
            diverged = not terminal_state_match
        except Exception as exc:  # noqa: BLE001 - a failed replay, not a crash
            failure_step = len(spec.steps)
            failure_site = f"skill_replay:{type(exc).__name__}"
    finished = datetime.now(UTC)
    result = "failed" if failure_step is not None or diverged else "passed"
    replay = SkillReplay(
        id=uuid4(),
        skill_version_id=version_id,
        app_map_id=app_map_id,
        result=result,
        failure_step=failure_step,
        failure_site=failure_site,
        heal_cycle=False,
        context_kind="run",
        model_calls=0,
        started_at=started,
        finished_at=finished,
        run_id=request.test_run_id,
        board_item_ref=board_item_ref,
    )
    session.add(replay)
    version = await session.get(SkillVersion, version_id)
    if version is not None:
        version.last_replay_result = result
        version.last_replay_at = finished
        version.replay_count = (version.replay_count or 0) + 1
        # Section 8.3: every consumption replay writes its run_replay
        # usage event (zero model calls — a replay never calls one).
        session.add(
            SkillUsageEvent(
                id=uuid4(),
                workspace_id=version.workspace_id,
                skill_id=version.skill_id,
                skill_version_id=version.id,
                app_map_id=version.app_map_id,
                run_id=request.test_run_id,
                kind="run_replay",
                from_status=version.lifecycle_status,
                to_status=version.lifecycle_status,
                result=result,
                payload={
                    "board_item_ref": board_item_ref,
                    "outcome": (
                        "satisfied_by_replay"
                        if result == "passed"
                        else "diverged"
                    ),
                    "terminal_state_match": terminal_state_match,
                },
            )
        )
        if diverged and version.lifecycle_status == "active":
            # Section 8.4.2 (assertion-shaped): quarantine at once —
            # defect-shaped signals are never healed around.
            evidence: dict[str, object] = {
                "assertion_divergence": {
                    "replay_id": str(replay.id),
                    "kind": "assertion_divergence",
                }
            }
            if check_skill_transition("active", "quarantined", evidence):
                version.lifecycle_status = "quarantined"
                session.add(
                    SkillUsageEvent(
                        id=uuid4(),
                        workspace_id=version.workspace_id,
                        skill_id=version.skill_id,
                        skill_version_id=version.id,
                        app_map_id=version.app_map_id,
                        run_id=request.test_run_id,
                        kind="quarantine",
                        from_status="active",
                        to_status="quarantined",
                        result="failed",
                        payload={
                            "replay_id": str(replay.id),
                            "kind": "assertion_divergence",
                            "board_item_ref": board_item_ref,
                        },
                    )
                )
        elif failure_step is not None and version.lifecycle_status == "active":
            # Section 8.4.3 (locator-shaped): demote to suspect; the
            # re-verification queue takes it from there.
            evidence = {
                "demotion": {
                    "replay_id": str(replay.id),
                    "kind": "locator_failure",
                    "failure_step": failure_step,
                    "failure_site": failure_site,
                }
            }
            if check_skill_transition("active", "suspect", evidence):
                version.lifecycle_status = "suspect"
                session.add(
                    SkillUsageEvent(
                        id=uuid4(),
                        workspace_id=version.workspace_id,
                        skill_id=version.skill_id,
                        skill_version_id=version.id,
                        app_map_id=version.app_map_id,
                        run_id=request.test_run_id,
                        kind="demotion",
                        from_status="active",
                        to_status="suspect",
                        result="failed",
                        payload={
                            "replay_id": str(replay.id),
                            "kind": "locator_failure",
                            "failure_step": failure_step,
                            "failure_site": failure_site,
                            "board_item_ref": board_item_ref,
                        },
                    )
                )
    await session.flush()
    record: dict[str, object] = {
        "replay_id": str(replay.id),
        "per_step": per_step,
        "terminal_state_match": terminal_state_match,
    }
    if diverged:
        return {"status": "diverged", **record}
    if failure_step is not None:
        return {
            "status": "failed",
            "failure_step": failure_step,
            "failure_site": failure_site,
            **record,
        }
    return {"status": "passed", **record}


async def verify_or_request_login(
    *,
    request: PersonaJourneyExecutionRequest | BrowserHandoffExecution,
    controller: BrowserController,
    handle: BrowserSessionHandle,
    policy: AuthVerificationPolicy | None,
    auth_scope: AuthSessionScope | None,
    session: AsyncSession,
    max_wait_seconds: float,
    assistance_reason: Literal[
        "absent_scope", "ambiguous_scope", "absent_target", "ambiguous_target"
    ]
    | None = None,
    continuation_verifier: Callable[[], Awaitable[bool]] | None = None,
    planned_step_index: int = 0,
    encountered_challenge: bool = False,
) -> None:
    principal = (
        await controller.verify_authenticated_role(handle=handle, policy=policy)
        if not encountered_challenge and assistance_reason is None and policy is not None
        else None
    )
    if principal is not None:
        assert policy is not None and auth_scope is not None
        captured = await controller.capture_verified_auth_session(
            handle=handle,
            policy=policy,
            scope=auth_scope,
        )
        if captured is None:
            raise AuthenticationVerificationBlocked(
                "Authenticated identity could not be safely captured."
            )
        await _run_event(
            session, request, "login_via", {"via": "already_authenticated"}
        )
        return

    if not encountered_challenge and assistance_reason is None and await _attempt_login_skill(
        request=request,
        controller=controller,
        handle=handle,
        policy=policy,
        auth_scope=auth_scope,
        session=session,
    ):
        await _run_event(session, request, "login_via", {"via": "skill_replay"})
        return

    expires_at = datetime.now(UTC) + timedelta(seconds=max_wait_seconds)
    lifecycle = HumanActionLifecycleRepository(session)
    try:
        handoff_options: dict[str, Any] = {}
        if assistance_reason is not None:
            if continuation_verifier is None:
                raise ValueError("A recovery verifier is required.")
            handoff_options["assistance_reason"] = assistance_reason
        if encountered_challenge:
            handoff_options["encountered_challenge"] = True
        request_id = await lifecycle.create_login_request(
            test_run_id=request.test_run_id,
            execution_id=request.execution_id,
            browser_session_id=handle.session_id,
            expires_at=expires_at,
            **handoff_options,
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
            if state is not None and state.request_status == "skipped":
                raise HumanAssistanceSkipped("Not tested—human assistance skipped.")
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
                        phase="case_action" if assistance_reason else "auth_preflight",
                        planned_step_index=planned_step_index,
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
                "human_pending",
                "human",
            }:
                if not checkpoint_created:
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
                            phase="case_action" if assistance_reason else "auth_preflight",
                            planned_step_index=planned_step_index,
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
            await session.commit()
            await asyncio.sleep(min(0.25, remaining))

        state = await lifecycle.state(request_id=request_id)
        if state is None or state.request_status != "leased":
            raise AuthenticationVerificationBlocked("The human login handoff is no longer active.")
        principal = (
            await controller.verify_authenticated_role(handle=handle, policy=policy)
            if assistance_reason is None and policy is not None
            else None
        )
        if principal is not None and assistance_reason is None:
            assert policy is not None and auth_scope is not None
            principal = await controller.capture_verified_auth_session(
                handle=handle,
                policy=policy,
                scope=auth_scope,
            )
        if continuation_verifier is not None and (
            assistance_reason is not None or policy is None or encountered_challenge
        ):
            continuation_verified = (
                (policy is None or assistance_reason is not None or principal is not None)
                and await continuation_verifier()
            )
        else:
            continuation_verified = principal is not None
        if not continuation_verified:
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
            if assistance_reason:
                raise AuthenticationVerificationBlocked(
                    "The original target is still unavailable or unsafe; recovery was not verified."
                )
            raise AuthenticationChallengeBlocked(
                "Login or identity was not verified. Complete sign-in and any challenge or MFA "
                "before starting a new attempt. This does not establish an application defect."
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
        await ExecutionSuspensionRepository(session).claim_ready(suspension_id=suspension_id)
        await session.commit()
        await controller.end_human_control(
            session_id=handle.session_id,
            execution_id=handle.execution_id,
            journey_id=handle.journey_id,
            verified=True,
            safe_to_capture=True,
        )
        await _run_event(session, request, "login_via", {"via": "handoff"})
        if not encountered_challenge:
            await _compile_login_skill_after_handoff(
                request=request, controller=controller, handle=handle, session=session
            )
    except TimeoutError as error:
        await session.rollback()
        await lifecycle.abandon(request_id=request_id)
        await session.commit()
        if assistance_reason is not None:
            raise HumanAssistanceTimeoutError(
                "The bounded human assistance window expired."
            ) from error
        raise AuthenticationVerificationBlocked(
            "The bounded human assistance window expired."
        ) from error
    except asyncio.CancelledError:
        await session.rollback()
        await lifecycle.abandon(request_id=request_id)
        await session.commit()
        raise
    except HumanAssistanceSkipped:
        await session.rollback()
        await lifecycle.acknowledge_skipped(request_id=request_id)
        await session.commit()
        raise
    except AuthenticationVerificationBlocked:
        await session.rollback()
        await lifecycle.abandon(request_id=request_id)
        await session.commit()
        raise
    except Exception as error:
        await session.rollback()
        latest = await lifecycle.state(request_id=request_id)
        if latest is not None and latest.request_status == "skipped":
            await lifecycle.acknowledge_skipped(request_id=request_id)
            await session.commit()
            raise HumanAssistanceSkipped("Not tested—human assistance skipped.") from error
        await lifecycle.abandon(request_id=request_id)
        await session.commit()
        raise AuthenticationVerificationBlocked("The human continuation failed closed.") from error


async def request_browser_handoff(
    *,
    request: BrowserHandoffExecution,
    controller: BrowserController,
    handle: BrowserSessionHandle,
    session: AsyncSession,
    expected_url: str | None = None,
    policy: AuthVerificationPolicy | None = None,
    auth_scope: AuthSessionScope | None = None,
) -> None:
    """Continue the exact browser after the gate is verified clear."""
    async def continuation_ready() -> bool:
        if expected_url is not None:
            return await controller.verify_handoff_destination(handle, expected_url=expected_url)
        return await controller.human_continuation_ready(handle)

    await verify_or_request_login(
        request=request,
        controller=controller,
        handle=handle,
        policy=policy,
        auth_scope=auth_scope,
        session=session,
        max_wait_seconds=MAX_HUMAN_LOGIN_WAIT_SECONDS,
        continuation_verifier=continuation_ready,
        encountered_challenge=True,
    )


async def request_runtime_assistance(
    *,
    request: PersonaJourneyExecutionRequest,
    controller: BrowserController,
    handle: BrowserSessionHandle,
    session: AsyncSession,
) -> None:
    """Encounter-driven assistance, without an upfront identity or role policy."""
    target_id = request.runtime_target_id
    if target_id is None:
        raise AuthenticationVerificationBlocked("The frozen assistance target is unavailable.")
    controller.revoke_human_session_snapshots(run_id=request.test_run_id, target_id=target_id)

    async def continuation_ready() -> bool:
        return await controller.capture_human_session(
            handle,
            run_id=request.test_run_id,
            target_id=target_id,
        )

    try:
        await verify_or_request_login(
            request=request,
            controller=controller,
            handle=handle,
            policy=None,
            auth_scope=None,
            session=session,
            max_wait_seconds=MAX_HUMAN_LOGIN_WAIT_SECONDS,
            continuation_verifier=continuation_ready,
        )
    except BaseException:
        controller.revoke_human_session_snapshots(run_id=request.test_run_id, target_id=target_id)
        raise


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
        async with pause_case_deadline(
            case_timeout, allowance_seconds=MAX_HUMAN_LOGIN_WAIT_SECONDS
        ):
            deadline = case_timeout.when()
            remaining_ms = max(
                0,
                int(
                    (deadline - asyncio.get_running_loop().time() if deadline is not None else 0)
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
    auth_mode: Literal["required", "optional"] = "required",
    auth_session_scope: AuthSessionScope | None = None,
    reuse_auth_session: bool = False,
    session_handle: BrowserSessionHandle | None = None,
) -> CaseExecutionResult:
    """Caller persists AgentExecution first and consumes result for legacy readiness.

    With session_handle (the unified Room, U-P2-03), the case borrows
    the caller's live session: no browser is launched, no snapshot is
    installed, no browser-session row is persisted, and the session is
    NOT closed at the end — the Room's owner closes it. Trace/event
    logs stay Room-level (written when the Room closes); step evidence
    is recorded per item exactly as in the owned path.
    """
    # Unified Room executions park for the spec's 15 minutes (U-P4);
    # owned legacy sessions keep the historical 10-minute wait.
    login_wait_seconds = (
        HARNESS_PARK_WAIT_SECONDS if session_handle is not None
        else MAX_HUMAN_LOGIN_WAIT_SECONDS
    )
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
    opaque_takeover_detected = False
    handle: BrowserSessionHandle | None = None
    persisted_browser = False
    storage: S3ArtifactStorage | None = None
    recorder: ExecutionStepRecorder | None = None
    trace_recorder: TaskTraceRecorder | None = None
    attempted_steps = 0
    recovery_attempted = False
    stage = "browser_start"
    case_timer: asyncio.Timeout | None = None
    initial_deadline: float | None = None
    max_seconds = min(
        request.max_duration_seconds,
        240 if any(a.origin == "user_approved" for a in case.expected) else case.estimated_seconds,
        budget.max_total_seconds,
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

    async def persist_task_trace(case_status: str) -> None:
        """Doc 29 section 4: persist the case's task trace as one
        test_case.task_trace event beside test_case.completed.
        Segments are derived from the run's own persisted events
        (the login handoff and in-flow assistance). Observational:
        a failure here never changes the case's outcome."""
        if trace_recorder is None:
            return
        try:
            rows = await session.scalars(
                select(RunEvent).where(
                    RunEvent.execution_id == request.execution_id,
                    RunEvent.event_type.in_(
                        ["login_via", "test_case.assistance_requested"]
                    ),
                )
            )
            for row in rows:
                payload_in = row.payload if isinstance(row.payload, dict) else {}
                if (
                    row.event_type == "login_via"
                    and payload_in.get("via") == "handoff"
                ):
                    trace_recorder.note_segment(
                        kind="assisted_login", from_step=None, to_step=None
                    )
                elif row.event_type == "test_case.assistance_requested":
                    index = payload_in.get("planned_step_index")
                    trace_recorder.note_segment(
                        kind="assisted_other",
                        from_step=index if isinstance(index, int) else None,
                        to_step=index if isinstance(index, int) else None,
                        reason_code=(
                            payload_in.get("reason_code")
                            if isinstance(payload_in.get("reason_code"), str)
                            else None
                        ),
                    )
        except Exception:
            await session.rollback()
        try:
            from markettwin_execution_orchestrator.workflow.task_spec_store import store_task_spec

            spec_ref = await store_task_spec(
                session, run_id=request.test_run_id, journey_id=request.journey_id,
                execution_id=request.execution_id, spec=case.model_dump(mode="json"),
            )
            await event(
                "test_case.task_trace",
                {
                    "schema_version": 1,
                    "spec_ref": str(spec_ref),
                    **trace_recorder.payload(case_status=case_status),
                },
            )
        except Exception:
            await session.rollback()

    def reserve_step() -> None:
        nonlocal attempted_steps
        if attempted_steps >= budget.max_steps:
            raise CaseActionLimitError
        attempted_steps += 1

    async def record_action(
        action_type: str,
        operation: Callable[[], Awaitable[BrowserActionResult]],
        approved_operation: Callable[[int], Awaitable[BrowserActionResult]] | None = None,
        case_action: CaseAction | None = None,
    ) -> None:
        nonlocal blocker, opaque_takeover_detected
        assert recorder is not None and handle is not None
        await browser_controller.cooperative_checkpoint(handle)
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
            action_details: dict[str, object] = {}
            opaque_takeover = (
                isinstance(error, BrowserActionBlockedError)
                and str(error) == OPAQUE_CONFIRMATION_REASON
                and case_action is not None
            )
            if opaque_takeover:
                opaque_takeover_detected = True
                blocker = "human_takeover_required"
                if case_action is not None:
                    action_details = {"action": case_action.action}
                if case_action is not None and case_action.target is not None:
                    action_details["target"] = case_action.target.model_dump(
                        mode="json", exclude_none=True
                    )
                await event("test_case.diagnostic", {
                    "schema_version": 1,
                    "case_id": case.case_id,
                    "stage": "actions",
                    "reason_code": "human_takeover_required",
                    "reason": OPAQUE_CONFIRMATION_REASON,
                    "action": action_details,
                })
            if trace_recorder is not None:
                try:
                    trace_recorder.record_step(
                        action_type=action_type,
                        case_action=case_action,
                        locator_strategy=None,
                        outcome="failed",
                    )
                except Exception:
                    pass
            await recorder.finish_step(
                step_id=step_id,
                status="policy_blocked" if isinstance(error, BrowserPolicyError) else "failed",
                observation_summary=(
                    '{"reason_code":"authentication_challenge_blocked"}'
                    if isinstance(error, AuthenticationChallengeBlocked)
                    else json.dumps({
                        "reason_code": "human_takeover_required",
                        "reason": OPAQUE_CONFIRMATION_REASON,
                        "action": action_details,
                    }, sort_keys=True)
                    if opaque_takeover
                    else type(error).__name__
                ),
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
        if trace_recorder is not None:
            try:
                trace_recorder.record_step(
                    action_type=action_type,
                    case_action=case_action,
                    locator_strategy=observed.locator_strategy,
                    outcome="completed",
                )
                trace_recorder.observe_url(
                    observed.observation.url if observed.observation else None
                )
            except Exception:
                pass

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
            if session_handle is not None:
                handle = session_handle
                stage = "actions"
            elif auth_verification is not None and auth_session_scope is not None:
                if reuse_auth_session:
                    try:
                        auth_snapshot = browser_controller.take_auth_session_snapshot(
                            scope=auth_session_scope,
                            case_id=case.case_id,
                        )
                    except Exception:
                        # Missing/expired transferable state falls back to secure login.
                        auth_snapshot = None
            elif request.runtime_human_assistance and request.runtime_target_id is not None:
                try:
                    auth_snapshot = browser_controller.take_human_session_snapshot(
                        run_id=request.test_run_id,
                        target_id=request.runtime_target_id,
                        case_id=case.case_id,
                    )
                except AuthSessionReuseRejected:
                    pass
            if session_handle is None:
                handle = await browser_controller.create_session(
                    execution_id=request.execution_id,
                    journey_id=request.journey_id,
                    allowed_origins=request.allowed_origins,
                    network_policy=request.network_policy,
                    auth_snapshot=auth_snapshot,
                    viewport_preset=request.viewport_preset,
                    fixture_action_rules=request.fixture_action_rules,
                    auth_only_origins=auth_verification.auth_only_origins if auth_verification else (),
                    authenticated_session=(
                        auth_verification is not None or request.runtime_human_assistance
                    ),
                )
                stage = "browser_persistence"
                await repository.create_browser_session(
                    browser_session_id=handle.session_id,
                    execution_id=request.execution_id,
                )
                await session.commit()
                persisted_browser = True
            from markettwin_execution_orchestrator.workflow.cooperative_pause import (
                cooperative_pause_checkpoint,
            )

            async def request_cooperative_pause() -> None:
                await cooperative_pause_checkpoint(
                    request=request,
                    controller=browser_controller,
                    handle=handle,
                    session=session,
                    policy=auth_verification,
                    case_timeout=case_timeout,
                )

            browser_controller.bind_cooperative_pause_handler(handle, request_cooperative_pause)
            stage = "storage_setup"
            storage = await asyncio.to_thread(S3ArtifactStorage.from_environment)
            recorder = ExecutionStepRecorder(session, request.execution_id, storage)
            try:
                run_row = await session.get(TestRun, request.test_run_id)
            except AttributeError:
                run_row = None
            run_kind = getattr(run_row, "run_kind", None)
            if not isinstance(run_kind, str) or run_kind == "explore_test":
                from markettwin_execution_orchestrator.workflow.task_trace import (
                    TaskTraceRecorder,
                )

                trace_recorder = TaskTraceRecorder(
                    case=case, start_url=request.start_url
                )
            if auth_verification is not None:

                async def request_login() -> None:
                    async with pause_case_deadline(
                        case_timeout,
                        allowance_seconds=login_wait_seconds,
                    ):
                        await verify_or_request_login(
                            request=request,
                            controller=browser_controller,
                            handle=handle,
                            policy=auth_verification,
                            auth_scope=auth_session_scope,
                            session=session,
                            max_wait_seconds=login_wait_seconds,
                        )

                browser_controller.bind_authentication_handler(handle, request_login)
            elif request.runtime_human_assistance:

                async def request_encountered_help() -> None:
                    async with pause_case_deadline(
                        case_timeout,
                        allowance_seconds=login_wait_seconds,
                    ):
                        await request_runtime_assistance(
                            request=request,
                            controller=browser_controller,
                            handle=handle,
                            session=session,
                        )

                browser_controller.bind_authentication_handler(handle, request_encountered_help)
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
            if auth_verification is not None and (
                auth_mode == "required" or auth_snapshot is not None
            ):
                if auth_session_scope is None:
                    raise AuthenticationVerificationBlocked(
                        "The approved authentication scope is unavailable."
                    )
                verified = await browser_controller.verify_authenticated_role(
                    handle=handle,
                    policy=auth_verification,
                )
                if auth_snapshot is not None and verified is None:
                    browser_controller.revoke_auth_session_snapshot(scope=auth_session_scope)
                if verified is None:
                    async with pause_case_deadline(
                        case_timeout,
                        allowance_seconds=login_wait_seconds,
                    ):
                        await verify_or_request_login(
                            request=request,
                            controller=browser_controller,
                            handle=handle,
                            policy=auth_verification,
                            auth_scope=auth_session_scope,
                            session=session,
                            max_wait_seconds=login_wait_seconds,
                        )
                await event(
                    "test_case.authenticated",
                    {
                        "schema_version": 1,
                        "case_id": case.case_id,
                        "role": auth_verification.role,
                        "origin": auth_verification.origin,
                        "auth_source": "reused_session"
                        if auth_snapshot is not None and verified
                        else "human_or_existing_session",
                        "executor_mode": "deterministic_case_steps",
                        "feature_key": scope.feature_key,
                        "inventory_source": "frozen_feature_scope",
                        "requirements": [item.requirement_id for item in scope.requirements],
                        "full_application_coverage": False,
                    },
                )

            async def check_assertions(checkpoint: int | None) -> bool:
                nonlocal stage
                assert handle is not None
                approved_values = tuple(
                    item.value for item in scope.safe_test_data
                )
                try:
                    run = await session.get(TestRun, request.test_run_id)
                except AttributeError:
                    # A session that cannot load rows (the unit
                    # fakes) leaves the channel closed, exactly as
                    # an unloadable row does.
                    run = None
                run_mode = (
                    run_safety_mode(run.configuration_snapshot)
                    if run is not None
                    else None
                )
                failed_precondition = False
                for expected in case.expected:
                    if expected.after_step_ordinal != checkpoint:
                        continue
                    await browser_controller.cooperative_checkpoint(handle)
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
                            approved_values=approved_values,
                            run_mode=run_mode,
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
                    if trace_recorder is not None:
                        try:
                            trace_recorder.record_assertion(
                                assertion_id=assertion.assertion_id,
                                oracle=assertion.oracle,
                                status=assertion.status,
                            )
                        except Exception:
                            pass
                    await event("test_case.assertion", assertion.model_dump(mode="json"))
                    next_action = (
                        case.steps[checkpoint]
                        if checkpoint is not None and checkpoint < len(case.steps)
                        else None
                    )
                    failed_precondition = failed_precondition or _is_failed_action_precondition(
                        expected, assertion, next_action
                    )
                return failed_precondition

            if await check_assertions(0):
                status, blocker = "completed", "assertion_precondition_failed"
            for action_index, action in enumerate(case.steps):
                if blocker == "assertion_precondition_failed":
                    break
                if (
                    auth_mode == "required"
                    and auth_verification is not None
                    and auth_session_scope is not None
                ):
                    verified = await browser_controller.verify_authenticated_role(
                        handle=handle,
                        policy=auth_verification,
                    )
                    if verified is None:
                        browser_controller.revoke_auth_session_snapshot(scope=auth_session_scope)
                        async with pause_case_deadline(
                            case_timeout,
                            allowance_seconds=login_wait_seconds,
                        ):
                            await verify_or_request_login(
                                request=request,
                                controller=browser_controller,
                                handle=handle,
                                policy=auth_verification,
                                auth_scope=auth_session_scope,
                                session=session,
                                max_wait_seconds=login_wait_seconds,
                            )

                async def execute_case_action(
                    step_id: int,
                    action: CaseAction = action,
                    action_index: int = action_index,
                ) -> BrowserActionResult:
                    nonlocal recovery_attempted
                    if action.action == "click":
                        assert action.target is not None
                        target = action.target

                        async def inspect_intent() -> SensitiveActionIntent | None:
                            return await browser_controller.inspect_click_approval(
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

                        try:
                            intent = await inspect_intent()
                        except BrowserActionError as error:
                            reason = error.reason_code
                            if (
                                reason
                                not in {
                                    "absent_scope",
                                    "ambiguous_scope",
                                    "absent_target",
                                    "ambiguous_target",
                                }
                                or recovery_attempted
                            ):
                                raise
                            recovery_attempted = True
                            await event(
                                "test_case.assistance_requested",
                                {
                                    "case_id": case.case_id,
                                    "stage": "action_preflight",
                                    "reason_code": reason,
                                    "planned_step_index": action_index,
                                },
                            )

                            async def verify_continuation() -> bool:
                                if not await browser_controller.verify_recovery_target(
                                    handle=handle,
                                    target=target,
                                ):
                                    return False
                                return (
                                    auth_verification is None
                                    or (
                                        await browser_controller.verify_authenticated_role(
                                            handle=handle,
                                            policy=auth_verification,
                                        )
                                    )
                                    is not None
                                )

                            async with pause_case_deadline(
                                case_timeout,
                                allowance_seconds=login_wait_seconds,
                            ):
                                await verify_or_request_login(
                                    request=request,
                                    controller=browser_controller,
                                    handle=handle,
                                    policy=auth_verification,
                                    auth_scope=auth_session_scope,
                                    session=session,
                                    max_wait_seconds=login_wait_seconds,
                                    assistance_reason=reason,  # type: ignore[arg-type]
                                    continuation_verifier=verify_continuation,
                                    planned_step_index=action_index,
                                )
                            # Only the read-only preflight is retried. No click was
                            # dispatched before the pause; approval policy runs again.
                            intent = await inspect_intent()
                            await event(
                                "test_case.assistance_resumed",
                                {
                                    "case_id": case.case_id,
                                    "planned_step_index": action_index,
                                },
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
                    case_action=action,
                )
                if await check_assertions(action_index + 1) and action_index + 1 < len(case.steps):
                    status, blocker = "completed", "assertion_precondition_failed"
                    break
            if blocker != "assertion_precondition_failed":
                await check_assertions(None)
        if trace_recorder is not None and handle is not None:
            try:
                from markettwin_execution_orchestrator.harvest.harvest_capture import (
                    capture_state,
                )
                from markettwin_execution_orchestrator.harvest.harvest_inventory import (
                    distil_elements,
                    distil_forms,
                    identity_for,
                )

                async with asyncio.timeout(3):
                    capture = await capture_state(
                        browser_controller,
                        handle,
                        execution_id=handle.execution_id,
                        journey_id=handle.journey_id,
                    )
                elements = distil_elements(capture)
                forms = distil_forms(capture)
                state_id, _, _ = identity_for(capture.url, elements, forms)
                trace_recorder.set_terminal(
                    {
                        "url": capture.url,
                        "state_id": state_id,
                        "element_signature": [
                            f"{element['role']}|{element['name']}"
                            for element in elements
                        ],
                    }
                )
            except Exception:
                pass
    except HumanAssistanceSkipped:
        status, blocker = "skipped", "human_assistance_skipped"
        assertions.clear()
    except HumanAssistanceTimeoutError:
        status, blocker = "policy_blocked", "human_assistance_timeout"
        await event(
            "test_case.diagnostic",
            {
                "schema_version": 1,
                "case_id": case.case_id,
                "stage": stage,
                "reason_code": "human_assistance_timeout",
            },
        )
    except AuthenticationVerificationBlocked as error:
        status = "policy_blocked"
        blocker = (
            "authentication_challenge_blocked"
            if isinstance(error, AuthenticationChallengeBlocked)
            else "policy_blocked"
        )
        await event(
            "test_case.diagnostic",
            {
                "schema_version": 1,
                "case_id": case.case_id,
                "stage": stage,
                "reason_code": (
                    "authentication_challenge_blocked"
                    if isinstance(error, AuthenticationChallengeBlocked)
                    else "human_assistance_unverified"
                ),
            },
        )
    except BrowserPolicyError:
        status = "policy_blocked"
        if not opaque_takeover_detected:
            blocker = "policy_blocked"
    except BrowserActionError as error:
        status, blocker = "failed", "action_failed"
        await event(
            "test_case.diagnostic",
            {
                "schema_version": 1,
                "case_id": case.case_id,
                "stage": stage,
                "error_type": type(error).__name__,
                "reason_code": error.reason_code,
            },
        )
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
        await persist_task_trace(status)
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
        if handle is not None and session_handle is None:
            try:
                async with asyncio.timeout(10):
                    artifacts = await browser_controller.close_session(session_id=handle.session_id)
                    if persisted_browser:
                        from markettwin_execution_orchestrator.workflow.cooperative_pause import (
                            finalize_browser_pauses,
                        )

                        await finalize_browser_pauses(session, handle)
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
    if blocker == "assertion_precondition_failed" and any(
        item.status == "not_satisfied" for item in assertions
    ):
        verdict = "not_satisfied"
    elif (
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
    await persist_task_trace(status)
    await event("test_case.completed", result.model_dump(mode="json"))
    return result
