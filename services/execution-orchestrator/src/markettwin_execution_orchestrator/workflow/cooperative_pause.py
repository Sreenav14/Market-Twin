"""Cooperative operator pause at a completed, replay-safe browser boundary."""

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

from markettwin_database.models import (
    ActionApprovalReceipt,
    ActionApprovalRequest,
    AgentExecution,
    ApplicationTarget,
    BrowserSession,
    ExecutionPauseRequest,
    ExecutionStep,
    HumanActionRequest,
    HumanControlLease,
    PersonaJourney,
    TargetAllowedOrigin,
    TargetAuthorization,
    TestRun,
    User,
    Workspace,
    WorkspaceMember,
)
from markettwin_shared.auth_verification import AuthVerificationPolicy
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.errors import (
    BrowserPolicyError,
    HumanAssistanceSkipped,
)
from markettwin_execution_orchestrator.persistence.human_action_lifecycle_repository import (
    HumanActionLifecycleRepository,
)

if TYPE_CHECKING:
    from markettwin_execution_orchestrator.workflow.journey_executor import (
        PersonaJourneyExecutionRequest,
    )

ACTIVE_PAUSE_STATES = ("requested", "paused", "resume_requested")


async def finalize_browser_pauses(session: AsyncSession, handle: BrowserSessionHandle) -> None:
    """Close durable ownership before retiring pending intents, under the browser row lock."""
    browser = await session.scalar(
        select(BrowserSession)
        .where(
            BrowserSession.id == handle.session_id,
            BrowserSession.execution_id == handle.execution_id,
        )
        .with_for_update()
    )
    if browser is not None:
        browser.state = "closed" if browser.state != "failed" else "failed"
        browser.control_mode = "none"
    await session.execute(
        update(ExecutionPauseRequest)
        .where(
            ExecutionPauseRequest.browser_session_id == handle.session_id,
            ExecutionPauseRequest.execution_id == handle.execution_id,
            ExecutionPauseRequest.status.in_(ACTIVE_PAUSE_STATES),
        )
        .values(status="unavailable", completed_at=datetime.now(UTC))
    )
    await session.flush()


async def _authorized(
    session: AsyncSession,
    pause: ExecutionPauseRequest,
    actor_id: UUID | None = None,
) -> bool:
    now = datetime.now(UTC)
    statement = (
        select(TestRun.target_snapshot, TestRun.target_id)
        .join(PersonaJourney, PersonaJourney.test_run_id == TestRun.id)
        .join(AgentExecution, AgentExecution.journey_id == PersonaJourney.id)
        .join(Workspace, Workspace.id == TestRun.workspace_id)
        .join(ApplicationTarget, ApplicationTarget.id == TestRun.target_id)
        .join(TargetAuthorization, TargetAuthorization.target_id == ApplicationTarget.id)
        .where(
            TestRun.id == pause.test_run_id,
            PersonaJourney.id == pause.journey_id,
            AgentExecution.id == pause.execution_id,
            AgentExecution.status == "running",
            TestRun.status.in_(("running", "awaiting_human")),
            Workspace.status == "active",
            Workspace.deleted_at.is_(None),
            ApplicationTarget.status == "active",
            ApplicationTarget.deleted_at.is_(None),
            ApplicationTarget.application_id == TestRun.application_id,
            TargetAuthorization.status == "authorized",
            TargetAuthorization.revoked_at.is_(None),
            (TargetAuthorization.expires_at.is_(None)) | (TargetAuthorization.expires_at > now),
        )
        .limit(1)
    )
    if actor_id is not None:
        statement = (
            statement.join(
                WorkspaceMember,
                WorkspaceMember.workspace_id == Workspace.id,
            )
            .join(User, User.id == WorkspaceMember.user_id)
            .where(
                WorkspaceMember.user_id == actor_id,
                WorkspaceMember.role.in_(("owner", "admin")),
                User.status == "active",
                User.deleted_at.is_(None),
            )
        )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return False
    snapshot, target_id = row
    if snapshot.get("target_id") != str(target_id):
        return False
    frozen = snapshot.get("allowed_origins")
    if not isinstance(frozen, list) or not frozen:
        return False
    current = (
        await session.scalars(
            select(TargetAllowedOrigin).where(
                TargetAllowedOrigin.target_id == target_id,
            )
        )
    ).all()
    approved = {
        (item.scheme, item.hostname, item.port, item.include_subdomains) for item in current
    }
    for raw in cast(list[object], frozen):
        if not isinstance(raw, dict):
            return False
        origin = cast(dict[str, object], raw)
        if (
            not isinstance(origin.get("scheme"), str)
            or not isinstance(origin.get("hostname"), str)
            or (origin.get("port") is not None and type(origin.get("port")) is not int)
            or type(origin.get("include_subdomains")) is not bool
        ):
            return False
        if (
            origin.get("scheme"),
            origin.get("hostname"),
            origin.get("port"),
            origin.get("include_subdomains"),
        ) not in approved:
            return False
    return True


async def cooperative_pause_checkpoint(
    *,
    request: "PersonaJourneyExecutionRequest",
    controller: BrowserController,
    handle: BrowserSessionHandle,
    session: AsyncSession,
    policy: AuthVerificationPolicy | None = None,
) -> None:
    pause = await session.scalar(
        select(ExecutionPauseRequest)
        .where(
            ExecutionPauseRequest.test_run_id == request.test_run_id,
            ExecutionPauseRequest.journey_id == request.journey_id,
            ExecutionPauseRequest.execution_id == request.execution_id,
            ExecutionPauseRequest.browser_session_id == handle.session_id,
            ExecutionPauseRequest.status.in_(ACTIVE_PAUSE_STATES),
        )
        .execution_options(populate_existing=True)
    )
    if pause is None:
        return
    pause_id = pause.id
    lifecycle = HumanActionLifecycleRepository(session)
    try:
        if pause.status == "requested":
            if pause.expires_at <= datetime.now(UTC):
                pause.status, pause.completed_at = "expired", datetime.now(UTC)
                await session.commit()
                return
            # Never take over a reserved/dispatched action or a claimed/uncertain effect.
            busy_step = await session.scalar(
                select(ExecutionStep.id)
                .where(
                    ExecutionStep.execution_id == request.execution_id,
                    ExecutionStep.status == "running",
                )
                .limit(1)
            )
            receipt = await session.scalar(
                select(ActionApprovalReceipt.dispatch_state)
                .join(
                    ActionApprovalRequest,
                    ActionApprovalRequest.id == ActionApprovalReceipt.approval_id,
                )
                .where(
                    ActionApprovalRequest.execution_id == request.execution_id,
                    ActionApprovalReceipt.dispatch_state.in_(("claimed", "uncertain")),
                )
                .limit(1)
            )
            if receipt == "uncertain":
                raise BrowserPolicyError("An uncertain action requires review before pause.")
            if busy_step is not None or receipt == "claimed":
                return
            if not await controller.cooperative_pause_ready(handle):
                # The first navigation or an encountered auth handler must finish first.
                return
            browser = await session.scalar(
                select(BrowserSession)
                .where(
                    BrowserSession.id == handle.session_id,
                    BrowserSession.execution_id == request.execution_id,
                )
                .with_for_update()
            )
            await session.refresh(pause, with_for_update=True)
            if pause.status != "requested":
                return
            if (
                browser is None
                or browser.state != "open"
                or browser.control_mode != "agent"
                or browser.control_generation != pause.generation
                or pause.expires_at <= datetime.now(UTC)
                or not await _authorized(session, pause, pause.requested_by_user_id)
            ):
                raise BrowserPolicyError("The requested pause is no longer authorized.")
            last_step = await session.scalar(
                select(ExecutionStep.id)
                .where(
                    ExecutionStep.execution_id == request.execution_id,
                    ExecutionStep.status == "completed",
                )
                .order_by(ExecutionStep.step_number.desc())
                .limit(1)
            )
            human_request = HumanActionRequest(
                id=uuid4(),
                execution_id=request.execution_id,
                browser_session_id=handle.session_id,
                request_type="other",
                status="pending",
                idempotency_key=f"operator-pause:{pause.id}",
                expires_at=pause.expires_at,
                instructions=(
                    "Paused at a safe boundary. Resume, take control, or skip this work item."
                ),
            )
            session.add(human_request)
            await session.flush([human_request])
            pause.human_request_id = human_request.id
            pause.last_durable_step_id = last_step
            pause.status, pause.acknowledged_at = "paused", datetime.now(UTC)
            browser.control_mode = "human_pending"
            run = await session.get(TestRun, request.test_run_id, populate_existing=True)
            if run is None or run.status != "running":
                raise BrowserPolicyError("The run cannot acknowledge this pause.")
            run.status = "awaiting_human"
            await session.commit()

        while True:
            await session.refresh(pause)
            if pause.status not in ACTIVE_PAUSE_STATES:
                if pause.status == "resumed":
                    return
                if pause.status == "skipped":
                    raise HumanAssistanceSkipped("Not tested—human assistance skipped.")
                raise BrowserPolicyError("The cooperative pause ended without safe continuation.")
            if pause.expires_at <= datetime.now(UTC) or not await _authorized(session, pause):
                raise BrowserPolicyError("The bounded cooperative pause expired or was revoked.")
            if pause.human_request_id is None:
                raise BrowserPolicyError("The paused browser handoff is unavailable.")
            state = await lifecycle.state(request_id=pause.human_request_id)
            if state is None:
                raise BrowserPolicyError("The paused browser handoff is unavailable.")
            if state.request_status == "skipped":
                pause.status, pause.completed_at = "skipped", datetime.now(UTC)
                await lifecycle.acknowledge_skipped(request_id=pause.human_request_id)
                await session.commit()
                raise HumanAssistanceSkipped("Not tested—human assistance skipped.")
            if state.request_status in {"expired", "cancelled"}:
                raise BrowserPolicyError("Human control ended without safe continuation.")
            if pause.status == "resume_requested":
                if not await controller.cooperative_pause_ready(handle):
                    raise BrowserPolicyError("The paused page cannot safely resume.")
                browser = await session.scalar(
                    select(BrowserSession)
                    .where(
                        BrowserSession.id == handle.session_id,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                human = await session.scalar(
                    select(HumanActionRequest)
                    .where(
                        HumanActionRequest.id == pause.human_request_id,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                await session.refresh(pause, with_for_update=True)
                active_lease = await session.scalar(
                    select(HumanControlLease.id)
                    .where(
                        HumanControlLease.request_id == pause.human_request_id,
                        HumanControlLease.released_at.is_(None),
                    )
                    .limit(1)
                )
                if (
                    pause.status != "resume_requested"
                    or browser is None
                    or browser.state != "open"
                    or human is None
                    or human.status != "pending"
                    or active_lease is not None
                    or browser.control_mode != "human_pending"
                    or browser.control_generation != pause.generation
                    or pause.expires_at <= datetime.now(UTC)
                    or human.expires_at is None
                    or human.expires_at <= datetime.now(UTC)
                    or pause.resume_requested_by_user_id is None
                    or not await _authorized(
                        session,
                        pause,
                        pause.resume_requested_by_user_id,
                    )
                ):
                    raise BrowserPolicyError("Plain resume no longer owns the paused browser.")
                human.status, human.completed_at = "completed", datetime.now(UTC)
                browser.control_mode = "agent"
                pause.status, pause.completed_at = "resumed", datetime.now(UTC)
                run = await session.get(TestRun, request.test_run_id, populate_existing=True)
                if run is None or run.status != "awaiting_human":
                    raise BrowserPolicyError("The paused run cannot safely resume.")
                run.status = "running"
                await session.commit()
                return
            if state.request_status == "leased" and state.control_mode == "verifying":
                if await controller.human_continuation_ready(handle):
                    actor_id = await session.scalar(
                        select(HumanControlLease.user_id)
                        .where(
                            HumanControlLease.request_id == pause.human_request_id,
                            HumanControlLease.generation < state.control_generation,
                        )
                        .order_by(HumanControlLease.generation.desc())
                        .limit(1)
                    )
                    if actor_id is None or not await _authorized(session, pause, actor_id):
                        raise BrowserPolicyError(
                            "The controlling operator is no longer authorized."
                        )
                    if (
                        policy is not None
                        and await controller.verify_authenticated_role(
                            handle=handle,
                            policy=policy,
                        )
                        is None
                    ):
                        raise BrowserPolicyError("The configured identity could not be verified.")
                    if pause.expires_at <= datetime.now(UTC) or not await _authorized(
                        session, pause, actor_id
                    ):
                        raise BrowserPolicyError("The released pause is no longer authorized.")
                    await lifecycle.finish_verification(
                        request_id=pause.human_request_id,
                        expected_generation=state.control_generation,
                        verified=True,
                    )
                    pause.status, pause.completed_at = "resumed", datetime.now(UTC)
                    await session.commit()
                    await controller.end_human_control(
                        session_id=handle.session_id,
                        execution_id=handle.execution_id,
                        journey_id=handle.journey_id,
                        verified=True,
                        safe_to_capture=True,
                    )
                    return
            # Release read transactions while a human is deciding; no browser lock is held.
            await session.commit()
            await asyncio.sleep(0.1)
    except BaseException:
        await session.rollback()
        pause = await session.get(ExecutionPauseRequest, pause_id, populate_existing=True)
        if pause is not None and pause.status in ACTIVE_PAUSE_STATES:
            pause.status = "expired" if pause.expires_at <= datetime.now(UTC) else "cancelled"
            pause.completed_at = datetime.now(UTC)
            if pause.human_request_id is not None:
                await lifecycle.abandon(request_id=pause.human_request_id)
            await session.commit()
        raise
