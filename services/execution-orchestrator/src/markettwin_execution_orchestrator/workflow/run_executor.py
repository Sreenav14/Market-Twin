"""Top-level persisted MarketTwin test-run orchestration."""

from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from markettwin_shared.auth_verification import AuthVerificationPolicy
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.agents.schemas.journey import PersonaJourneySpec
from markettwin_execution_orchestrator.agents.schemas.plan import MetaAgentPlan
from markettwin_execution_orchestrator.browser import (
    AllowedOrigin,
    BrowserController,
)
from markettwin_execution_orchestrator.browser.contracts import (
    NetworkPolicy,
)
from markettwin_execution_orchestrator.browser.policy import (
    validate_target_url,
)
from markettwin_execution_orchestrator.observability import (
    initialize_adk_observability,
)
from markettwin_execution_orchestrator.persistence import (
    PlanRepository,
    RunStateRepository,
)
from markettwin_execution_orchestrator.workflow.adk_workflow import (
    WorkflowPlan,
    create_run_workflow,
    run_workflow,
)
from markettwin_execution_orchestrator.workflow.multi_persona_executor import (
    MultiPersonaExecutionRequest,
    execute_one_planned_journey,
    persist_run_collection,
)
from markettwin_execution_orchestrator.workflow.multi_persona_result import (
    MultiPersonaExecutionResult,
)
from markettwin_execution_orchestrator.workflow.persona_result import PersonaJourneyResult
from markettwin_execution_orchestrator.workflow.planning import (
    MetaPlanningRequest,
    generate_meta_agent_plan,
)
from markettwin_execution_orchestrator.workflow.testing_depth import TestingDepth, mission_limit

if TYPE_CHECKING:
    from markettwin_execution_orchestrator.workflow.deep_run import DeepFeatureRunResult


@dataclass(frozen=True, slots=True)
class MarketTwinRunRequest:
    """Inputs required to execute one complete in-memory MarketTwin run."""

    run_id: UUID

    study_brief: str
    target_snapshot: dict[str, object]

    start_url: str
    allowed_origins: tuple[AllowedOrigin, ...]

    network_policy: NetworkPolicy = "public_only"
    max_duration_seconds_per_journey: int = 180
    knowledge_context: tuple[dict[str, object], ...] = ()
    testing_depth: TestingDepth = "high"
    agent_prompt_overrides: dict[str, dict[str, str]] = field(
        default_factory=dict[str, dict[str, str]]
    )
    replay_plan: dict[str, object] | None = None
    execution_mode: Literal["legacy_persona", "deep_feature_v1"] = "legacy_persona"
    feature_scope: dict[str, object] | None = None
    feature_budget: dict[str, object] | None = None
    feature_plan: dict[str, object] | None = None
    fixture_truth: bool = False
    auth_verification: AuthVerificationPolicy | None = None
    synthetic_fixture_approval_enabled: bool = False
    human_action_approvals_enabled: bool = False
    created_by_user_id: UUID | None = None


async def execute_markettwin_run(
    request: MarketTwinRunRequest,
    *,
    session: AsyncSession,
) -> MultiPersonaExecutionResult | DeepFeatureRunResult:
    """Plan and execute one complete MarketTwin test run."""

    initialize_adk_observability()

    study_brief = request.study_brief.strip()

    if not study_brief:
        raise ValueError("study_brief must not be empty.")

    if not request.allowed_origins:
        raise ValueError("At least one allowed origin is required.")

    if request.max_duration_seconds_per_journey <= 0:
        raise ValueError("max_duration_seconds_per_journey must be positive.")

    validated_start_url = validate_target_url(
        request.start_url,
        request.allowed_origins,
        request.network_policy,
    )

    if request.execution_mode == "deep_feature_v1":
        from markettwin_execution_orchestrator.workflow.deep_run import execute_deep_feature_run

        return await execute_deep_feature_run(request=request, session=session)
    if request.execution_mode != "legacy_persona":
        raise ValueError("Unsupported execution mode.")

    run_repository = RunStateRepository(session)
    plan_repository = PlanRepository(session)

    await run_repository.mark_planning(
        test_run_id=request.run_id,
    )
    await session.commit()

    async def prepare_plan() -> WorkflowPlan:
        if request.replay_plan is not None:
            plan = MetaAgentPlan.model_validate(request.replay_plan)
        else:
            plan = await generate_meta_agent_plan(
                request=MetaPlanningRequest(
                    test_run_id=request.run_id,
                    study_brief=study_brief,
                    target_snapshot=request.target_snapshot,
                    knowledge_context=request.knowledge_context,
                    testing_depth=request.testing_depth,
                    prompt_override=request.agent_prompt_overrides.get("meta"),
                ),
                session=session,
            )
        if len(plan.missions) > mission_limit(request.testing_depth):
            raise ValueError("The generated plan exceeds the selected testing depth.")

        persisted_plan = await plan_repository.create_from_plan(
            test_run_id=request.run_id,
            plan=plan,
        )

        await session.commit()

        await run_repository.mark_running(
            test_run_id=request.run_id,
        )

        await session.commit()

        return WorkflowPlan(
            plan=plan,
            journey_ids_by_key={
                item.journey_key: item.journey_id for item in persisted_plan.journeys
            },
            persona_ids_by_key={
                item.persona_key: item.persona_id for item in persisted_plan.personas
            },
            mission_ids_by_key={
                item.mission_key: item.mission_id for item in persisted_plan.missions
            },
        )

    async def collect_results(result: MultiPersonaExecutionResult) -> None:
        await persist_run_collection(run_id=request.run_id, result=result, session=session)

    try:
        async with AsyncExitStack() as resources:
            browser_controller: BrowserController | None = None

            async def execute_journey(
                prepared: WorkflowPlan, journey: PersonaJourneySpec
            ) -> PersonaJourneyResult:
                nonlocal browser_controller
                if browser_controller is None:
                    browser_controller = await resources.enter_async_context(BrowserController())
                return await execute_one_planned_journey(
                    request=MultiPersonaExecutionRequest(
                        run_id=request.run_id,
                        plan=prepared.plan,
                        journey_ids_by_key=prepared.journey_ids_by_key,
                        persona_ids_by_key=prepared.persona_ids_by_key,
                        mission_ids_by_key=prepared.mission_ids_by_key,
                        start_url=validated_start_url.href,
                        allowed_origins=request.allowed_origins,
                        network_policy=request.network_policy,
                        max_duration_seconds_per_journey=(request.max_duration_seconds_per_journey),
                        agent_prompt_overrides=request.agent_prompt_overrides,
                    ),
                    journey=journey,
                    browser_controller=browser_controller,
                    session=session,
                )

            result = await run_workflow(
                run_id=request.run_id,
                workflow=create_run_workflow(
                    prepare_plan=prepare_plan,
                    execute_journey=execute_journey,
                    collect_results=collect_results,
                    max_journeys=3 * mission_limit(request.testing_depth),
                ),
            )

        await run_repository.mark_completed(
            test_run_id=request.run_id,
        )

        await session.commit()

        return result

    except Exception:
        await session.rollback()

        try:
            await run_repository.mark_failed(
                test_run_id=request.run_id,
            )
            await session.commit()
        except Exception:
            await session.rollback()

        raise
