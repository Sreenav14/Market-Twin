"""Authenticated discovery uses the same durable human handoff as feature cases."""

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.agents.schemas.journey import PersonaJourneySpec
from markettwin_execution_orchestrator.agents.schemas.mission import TestMissionSpec
from markettwin_execution_orchestrator.agents.schemas.persona import PersonaSpec
from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.browser.auth_session_broker import AuthSessionScope
from markettwin_execution_orchestrator.browser.errors import HumanAssistanceSkipped
from markettwin_execution_orchestrator.persistence import ExecutionRepository, PlanRepository
from markettwin_execution_orchestrator.persistence.run_state_repository import RunStateRepository
from markettwin_execution_orchestrator.workflow.case_execution import (
    MAX_HUMAN_LOGIN_WAIT_SECONDS,
    request_runtime_assistance,
    verify_or_request_login,
)
from markettwin_execution_orchestrator.workflow.journey_executor import (
    PersonaJourneyExecutionRequest,
)

if TYPE_CHECKING:
    from markettwin_execution_orchestrator.workflow.run_executor import MarketTwinRunRequest


async def authenticated_discovery(
    *, request: "MarketTwinRunRequest", controller: BrowserController,
    session: AsyncSession, auth_scope: AuthSessionScope | None,
) -> dict[str, object]:
    """Discover normally; encountered challenges pause before page data reaches planning."""
    identity_verification = request.auth_verification is not None
    record = await PlanRepository(session).create_auth_bootstrap(
        test_run_id=request.run_id, requires_identity_verification=identity_verification,
    )
    execution_id = uuid4()
    executions = ExecutionRepository(session)
    await executions.create_agent_execution(
        execution_id=execution_id, journey_id=record.journey_id,
        runtime_name="human_auth_bootstrap_v1" if identity_verification else "browser_discovery_v1",
    )
    await RunStateRepository(session).mark_running(test_run_id=request.run_id)
    await session.commit()
    handle = await controller.create_session(
        execution_id=execution_id, journey_id=record.journey_id,
        allowed_origins=request.allowed_origins, network_policy=request.network_policy,
        auth_only_origins=request.auth_verification.auth_only_origins
            if request.auth_verification else (),
        authenticated_session=True,
    )
    success = False
    skipped = False
    try:
        await executions.create_browser_session(
            browser_session_id=handle.session_id, execution_id=execution_id,
        )
        await session.commit()
        journey = PersonaJourneySpec(
            journey_key=record.journey_key,
            persona=PersonaSpec(
                persona_id="human_auth" if identity_verification else "browser_discovery",
                name="Human authentication" if identity_verification else "Browser discovery",
                perspective="Manual test-account prerequisite" if identity_verification
                    else "Observe the approved starting page",
                behavior_traits=("manual",) if identity_verification else ("observational",),
                priorities=("secure authentication",) if identity_verification
                    else ("observe approved page",),
            ),
            mission=TestMissionSpec(
                mission_id="auth_bootstrap" if identity_verification else "observe_starting_page",
                name="Verify test identity" if identity_verification
                    else "Observe approved starting page",
                objective="Verify the approved identity before discovery." if identity_verification
                    else "Observe the approved starting page and request help only if blocked.",
                success_criteria=("Approved identity verified",) if identity_verification
                    else ("Approved starting page observed",), priority="low",
            ),
        )
        journey_request = PersonaJourneyExecutionRequest(
                test_run_id=request.run_id, execution_id=execution_id,
                journey_id=record.journey_id, persona_id=record.persona_id,
                mission_id=record.mission_id, journey=journey, start_url=request.start_url,
                allowed_origins=request.allowed_origins, network_policy=request.network_policy,
                runtime_human_assistance=request.runtime_human_assistance,
                runtime_target_id=UUID(str(request.target_snapshot["target_id"]))
                    if request.runtime_human_assistance else None,
            )
        from markettwin_execution_orchestrator.workflow.cooperative_pause import (
            cooperative_pause_checkpoint,
        )

        async def request_pause() -> None:
            await cooperative_pause_checkpoint(
                request=journey_request, controller=controller, handle=handle,
                session=session, policy=request.auth_verification,
            )

        controller.bind_cooperative_pause_handler(handle, request_pause)
        async def request_login() -> None:
            if request.auth_verification is None:
                await request_runtime_assistance(
                    request=journey_request, controller=controller, handle=handle, session=session,
                )
            else:
                await verify_or_request_login(
                    request=journey_request, controller=controller, handle=handle,
                    policy=request.auth_verification, auth_scope=auth_scope, session=session,
                    max_wait_seconds=MAX_HUMAN_LOGIN_WAIT_SECONDS,
                )
        controller.bind_authentication_handler(handle, request_login)
        await controller.navigate(session_id=handle.session_id, url=request.start_url)
        if request.auth_mode == "required" and not request.runtime_human_assistance:
            await request_login()
        observed = await controller.get_state(
            session_id=handle.session_id, execution_id=execution_id, journey_id=record.journey_id,
        )
        success = True
        return observed.observation.to_dict()
    except HumanAssistanceSkipped:
        skipped = True
        return {"human_assistance_skipped": True}
    finally:
        await session.rollback()
        await controller.close_session(session_id=handle.session_id)
        from markettwin_execution_orchestrator.workflow.cooperative_pause import (
            finalize_browser_pauses,
        )
        await finalize_browser_pauses(session, handle)
        await executions.mark_browser_session_closed(browser_session_id=handle.session_id)
        await executions.finish_agent_execution(
            execution_id=execution_id,
            status="skipped" if skipped else "completed" if success else "policy_blocked",
            outcome=None,
        )
        await session.commit()
