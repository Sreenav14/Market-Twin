"""Bounded ADK workflow with explicit session-state handoffs between stages."""

# The requested SequentialAgent API is supported but deprecated in ADK 2.5.
# Keep that compatibility decision local; migration is documented alongside this workflow.
# pyright: reportDeprecated=false

from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import cast
from uuid import UUID, uuid4

from google.adk.agents import BaseAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from markettwin_execution_orchestrator.agents.schemas.journey import PersonaJourneySpec
from markettwin_execution_orchestrator.agents.schemas.plan import MetaAgentPlan
from markettwin_execution_orchestrator.workflow.journey_planner import build_persona_journeys
from markettwin_execution_orchestrator.workflow.multi_persona_result import (
    MultiPersonaExecutionResult,
)
from markettwin_execution_orchestrator.workflow.persona_result import PersonaJourneyResult

WORKFLOW_APP_NAME = "markettwin_run_workflow"
PLAN_KEY = "markettwin_plan"
INDEX_KEY = "journey_index"
PENDING_KEY = "pending_journey_result"
RESULTS_KEY = "journey_results"
COLLECTION_KEY = "run_collection"


class WorkflowPlan(BaseModel):
    """JSON-safe planning handoff; PostgreSQL owns all durable identities."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    plan: MetaAgentPlan
    journey_ids_by_key: dict[str, UUID]
    persona_ids_by_key: dict[str, UUID]
    mission_ids_by_key: dict[str, UUID]


class WorkflowStage(BaseAgent):
    """A deterministic ADK agent whose stage emits explicit state delta events."""

    operation: Callable[[InvocationContext], Awaitable[EventActions]] = Field(exclude=True)

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        actions = await self.operation(ctx)
        yield Event(author=self.name, invocation_id=ctx.invocation_id, actions=actions)


def create_run_workflow(
    *,
    prepare_plan: Callable[[], Awaitable[WorkflowPlan]],
    execute_journey: Callable[[WorkflowPlan, PersonaJourneySpec], Awaitable[PersonaJourneyResult]],
    collect_results: Callable[[MultiPersonaExecutionResult], Awaitable[None]],
    max_journeys: int,
) -> SequentialAgent:
    """Create Plan → Loop[Execute → Record] → Collect, once per planned journey."""
    if max_journeys <= 0:
        raise ValueError("max_journeys must be positive.")
    journey_group = SequentialAgent(name="Agent_Journeys_1", sub_agents=[])

    async def plan_stage(_: InvocationContext) -> EventActions:
        prepared = await prepare_plan()
        journeys = build_persona_journeys(prepared.plan)
        if len({journey.journey_key for journey in journeys}) != len(journeys):
            raise ValueError("The plan must contain unique journey assignments.")
        if len(journeys) > max_journeys:
            raise ValueError("The plan exceeds the selected journey limit.")
        # Construct the actual agent tree from the committed plan, not a static
        # reusable node whose label only changes in the UI.
        for index, journey in enumerate(journeys):
            sequence = create_journey_sequence(index, journey)
            sequence.parent_agent = journey_group
            journey_group.sub_agents.append(sequence)
        return EventActions(
            state_delta={
                PLAN_KEY: prepared.model_dump(mode="json"),
                INDEX_KEY: 0,
                RESULTS_KEY: [],
                PENDING_KEY: None,
            }
        )

    async def execute_stage(ctx: InvocationContext, assigned_index: int) -> EventActions:
        prepared = WorkflowPlan.model_validate(ctx.session.state[PLAN_KEY])
        journeys = build_persona_journeys(prepared.plan)
        index = cast(int, ctx.session.state[INDEX_KEY])
        if (
            index != assigned_index
            or index >= len(journeys)
            or len(ctx.session.state[RESULTS_KEY]) != index
        ):
            raise RuntimeError("Journey workflow state would repeat or skip an execution.")
        # Each persona has its own controlled browser and inner ADK conversation.
        result = await execute_journey(prepared, journeys[index])
        if result.journey.journey_key != journeys[index].journey_key:
            raise RuntimeError("Journey result does not match the assigned journey.")
        return EventActions(state_delta={PENDING_KEY: result.model_dump(mode="json")})

    async def record_stage(ctx: InvocationContext, assigned_index: int) -> EventActions:
        pending = PersonaJourneyResult.model_validate(ctx.session.state[PENDING_KEY])
        if ctx.session.state[INDEX_KEY] != assigned_index:
            raise RuntimeError("Journey recording does not match the assigned sequence.")
        results = [
            *cast(list[dict[str, object]], ctx.session.state[RESULTS_KEY]),
            pending.model_dump(mode="json"),
        ]
        index = cast(int, ctx.session.state[INDEX_KEY]) + 1
        return EventActions(
            state_delta={
                RESULTS_KEY: results,
                INDEX_KEY: index,
                PENDING_KEY: None,
            },
        )

    def create_journey_sequence(index: int, journey: PersonaJourneySpec) -> SequentialAgent:
        async def execute(ctx: InvocationContext) -> EventActions:
            return await execute_stage(ctx, index)

        async def record(ctx: InvocationContext) -> EventActions:
            return await record_stage(ctx, index)

        return SequentialAgent(
            name=f"JourneySequence_{index + 1}",
            description=f"{journey.persona.name}: {journey.mission.name} ({journey.journey_key})",
            sub_agents=[
                WorkflowStage(name=f"ExecuteJourneyAgent_{index + 1}", operation=execute),
                WorkflowStage(name=f"RecordJourneyResultAgent_{index + 1}", operation=record),
            ],
        )

    async def collector_stage(ctx: InvocationContext) -> EventActions:
        prepared = WorkflowPlan.model_validate(ctx.session.state[PLAN_KEY])
        result = MultiPersonaExecutionResult.model_validate(
            {
                "plan": prepared.plan.model_dump(mode="json"),
                "journeys": ctx.session.state[RESULTS_KEY],
            }
        )
        expected = [item.journey_key for item in build_persona_journeys(prepared.plan)]
        if [item.journey.journey_key for item in result.journeys] != expected:
            raise RuntimeError("Collector requires exactly one result for every planned journey.")
        # The collector runs only after all execution/result commits have succeeded.
        await collect_results(result)
        return EventActions(state_delta={COLLECTION_KEY: result.model_dump(mode="json")})

    return SequentialAgent(
        name="markettwin_run",
        sub_agents=[
            WorkflowStage(name="PlanAgent", operation=plan_stage),
            journey_group,
            WorkflowStage(name="SupervisorAgent", operation=collector_stage),
        ],
    )


async def run_workflow(
    *,
    run_id: UUID,
    workflow: SequentialAgent,
) -> MultiPersonaExecutionResult:
    """Run the actual ADK event loop, then read the collector's saved state."""
    runner = InMemoryRunner(agent=workflow, app_name=WORKFLOW_APP_NAME)
    user_id = f"run_{run_id.hex}"
    session_id = f"workflow_{run_id.hex}_{uuid4().hex}"
    try:
        await runner.session_service.create_session(
            app_name=WORKFLOW_APP_NAME, user_id=user_id, session_id=session_id
        )
        async for _ in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(
                role="user", parts=[types.Part(text="Execute this authorized MarketTwin test run.")]
            ),
        ):
            pass
        saved = await runner.session_service.get_session(
            app_name=WORKFLOW_APP_NAME, user_id=user_id, session_id=session_id
        )
        if saved is None or COLLECTION_KEY not in saved.state:
            raise RuntimeError("ADK workflow completed without collecting its results.")
        return MultiPersonaExecutionResult.model_validate(saved.state[COLLECTION_KEY])
    finally:
        await runner.close()
