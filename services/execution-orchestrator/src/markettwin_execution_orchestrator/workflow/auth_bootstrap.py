"""Authenticated discovery uses the same durable human handoff as feature cases."""

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.agents.schemas.journey import PersonaJourneySpec
from markettwin_execution_orchestrator.agents.schemas.mission import TestMissionSpec
from markettwin_execution_orchestrator.agents.schemas.persona import PersonaSpec
from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.browser.auth_session_broker import AuthSessionScope
from markettwin_execution_orchestrator.persistence import ExecutionRepository, PlanRepository
from markettwin_execution_orchestrator.persistence.run_state_repository import RunStateRepository
from markettwin_execution_orchestrator.workflow.case_execution import (
    MAX_HUMAN_LOGIN_WAIT_SECONDS,
    verify_or_request_login,
)
from markettwin_execution_orchestrator.workflow.journey_executor import (
    PersonaJourneyExecutionRequest,
)

if TYPE_CHECKING:
    from markettwin_execution_orchestrator.workflow.run_executor import MarketTwinRunRequest


async def authenticated_discovery(
    *, request: "MarketTwinRunRequest", controller: BrowserController,
    session: AsyncSession, auth_scope: AuthSessionScope,
) -> dict[str, object]:
    """Verify the role before any protected page context reaches the planner."""
    assert request.auth_verification is not None
    record = await PlanRepository(session).create_auth_bootstrap(test_run_id=request.run_id)
    execution_id = uuid4()
    executions = ExecutionRepository(session)
    await executions.create_agent_execution(
        execution_id=execution_id, journey_id=record.journey_id,
        runtime_name="human_auth_bootstrap_v1",
    )
    await RunStateRepository(session).mark_running(test_run_id=request.run_id)
    await session.commit()
    handle = await controller.create_session(
        execution_id=execution_id, journey_id=record.journey_id,
        allowed_origins=request.allowed_origins, network_policy=request.network_policy,
        auth_only_origins=request.auth_verification.auth_only_origins,
        authenticated_session=True,
    )
    success = False
    try:
        await executions.create_browser_session(
            browser_session_id=handle.session_id, execution_id=execution_id,
        )
        await session.commit()
        await controller.navigate(session_id=handle.session_id, url=request.start_url)
        journey = PersonaJourneySpec(
            journey_key=record.journey_key,
            persona=PersonaSpec(persona_id="human_auth", name="Human authentication",
                                perspective="Manual test-account prerequisite",
                                behavior_traits=("manual",),
                                priorities=("secure authentication",)),
            mission=TestMissionSpec(mission_id="auth_bootstrap", name="Verify test identity",
                                    objective="Verify the approved identity before discovery.",
                                    success_criteria=("Approved identity verified",),
                                    priority="low"),
        )
        await verify_or_request_login(
            request=PersonaJourneyExecutionRequest(
                test_run_id=request.run_id, execution_id=execution_id,
                journey_id=record.journey_id, persona_id=record.persona_id,
                mission_id=record.mission_id, journey=journey, start_url=request.start_url,
                allowed_origins=request.allowed_origins, network_policy=request.network_policy,
            ),
            controller=controller, handle=handle, policy=request.auth_verification,
            auth_scope=auth_scope, session=session,
            max_wait_seconds=MAX_HUMAN_LOGIN_WAIT_SECONDS,
        )
        observed = await controller.get_state(
            session_id=handle.session_id, execution_id=execution_id, journey_id=record.journey_id,
        )
        success = True
        return observed.observation.to_dict()
    finally:
        await session.rollback()
        await controller.close_session(session_id=handle.session_id)
        await executions.mark_browser_session_closed(browser_session_id=handle.session_id)
        await executions.finish_agent_execution(
            execution_id=execution_id, status="completed" if success else "policy_blocked",
            outcome=None,
        )
        await session.commit()
