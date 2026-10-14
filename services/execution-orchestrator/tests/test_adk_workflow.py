"""Exercise the real ADK runner and bounded workflow without models or browsers."""

import asyncio
from uuid import uuid4

import pytest
from google.adk.agents import SequentialAgent
from markettwin_execution_orchestrator.agents.schemas.journey import PersonaJourneySpec
from markettwin_execution_orchestrator.agents.schemas.plan import MetaAgentPlan
from markettwin_execution_orchestrator.workflow.adk_workflow import (
    WorkflowPlan,
    create_run_workflow,
    run_workflow,
)
from markettwin_execution_orchestrator.workflow.journey_planner import build_persona_journeys
from markettwin_execution_orchestrator.workflow.multi_persona_result import (
    MultiPersonaExecutionResult,
)
from markettwin_execution_orchestrator.workflow.persona_result import (
    JourneyExecutionStatus,
    PersonaJourneyResult,
)


def prepared_plan(mission_count: int) -> WorkflowPlan:
    plan = MetaAgentPlan.model_validate(
        {
            "mission_summary": "Review information discovery",
            "personas": [
                {
                    "persona_id": f"persona_{index}",
                    "name": f"User {index}",
                    "perspective": "A realistic application user",
                    "behavior_traits": ["careful"],
                    "priorities": ["clarity"],
                }
                for index in range(1, 4)
            ],
            "missions": [
                {
                    "mission_id": f"mission_{index}",
                    "name": f"Find information {index}",
                    "objective": "Find relevant application information",
                    "success_criteria": ["Information found"],
                    "priority": "medium",
                }
                for index in range(1, mission_count + 1)
            ],
        }
    )
    return WorkflowPlan(
        plan=plan,
        journey_ids_by_key={item.journey_key: uuid4() for item in build_persona_journeys(plan)},
        persona_ids_by_key={item.persona_id: uuid4() for item in plan.personas},
        mission_ids_by_key={item.mission_id: uuid4() for item in plan.missions},
    )


@pytest.mark.parametrize("mission_count", [1, 2, 4])
async def test_real_adk_sequence_executes_each_journey_once_and_supervisor_last(
    mission_count: int,
) -> None:
    prepared = prepared_plan(mission_count)
    expected = [item.journey_key for item in build_persona_journeys(prepared.plan)]
    seen: list[str] = []
    order: list[str] = []
    collected: list[MultiPersonaExecutionResult] = []
    active = 0

    async def prepare() -> WorkflowPlan:
        order.append("plan")
        return prepared

    async def execute(
        state_plan: WorkflowPlan, journey: PersonaJourneySpec
    ) -> PersonaJourneyResult:
        nonlocal active
        active += 1
        await asyncio.sleep(0)
        assert active == 1  # Another journey must not start while this one is awaiting.
        assert state_plan == prepared  # JSON state preserves the durable UUID mapping.
        assert journey.journey_key not in seen
        seen.append(journey.journey_key)
        order.append(journey.journey_key)
        active -= 1
        return PersonaJourneyResult(
            journey=journey,
            status=JourneyExecutionStatus.COMPLETED,
            observations=(f"Only {journey.journey_key}'s observation",),
        )

    async def collect(result: MultiPersonaExecutionResult) -> None:
        order.append("supervisor")
        assert seen == expected
        collected.append(result)

    workflow = create_run_workflow(
        prepare_plan=prepare, execute_journey=execute, collect_results=collect, max_journeys=12
    )
    assert isinstance(workflow, SequentialAgent)
    assert isinstance(workflow.sub_agents[1], SequentialAgent)
    dispatcher = workflow.sub_agents[1]
    assert dispatcher.sub_agents == []  # Nodes are constructed only after Meta planning.
    assert workflow.sub_agents[-1].name == "SupervisorAgent"
    result = await run_workflow(run_id=uuid4(), workflow=workflow)
    assert len(dispatcher.sub_agents) == len(expected)
    assert all(isinstance(node, SequentialAgent) for node in dispatcher.sub_agents)
    assert [node.name for node in dispatcher.sub_agents] == [
        f"JourneySequence_{index + 1}" for index in range(len(expected))
    ]
    assert all(node.parent_agent is dispatcher for node in dispatcher.sub_agents)
    assert all(
        key in node.description for key, node in zip(expected, dispatcher.sub_agents, strict=True)
    )
    def check_containers(node):
        if node.sub_agents:
            assert isinstance(node, SequentialAgent)
        for child in node.sub_agents:
            check_containers(child)

    check_containers(workflow)
    assert order == ["plan", *expected, "supervisor"]
    assert len(result.journeys) == 3 * mission_count
    assert result.completed_count == 3 * mission_count
    assert collected == [result]
    assert seen == expected  # No extra journey runs even when the plan limit is 12.


async def test_supervisor_preserves_failures_and_policy_results_without_replay() -> None:
    prepared = prepared_plan(1)
    statuses = [
        JourneyExecutionStatus.FAILED,
        JourneyExecutionStatus.TIMED_OUT,
        JourneyExecutionStatus.POLICY_BLOCKED,
    ]
    seen: list[str] = []

    async def prepare() -> WorkflowPlan:
        return prepared

    async def execute(_: WorkflowPlan, journey: PersonaJourneySpec) -> PersonaJourneyResult:
        status = statuses[len(seen)]
        seen.append(journey.journey_key)
        return PersonaJourneyResult(journey=journey, status=status, blockers=("Observed blocker",))

    async def collect(result: MultiPersonaExecutionResult) -> None:
        assert result.failed_count == 3

    result = await run_workflow(
        run_id=uuid4(),
        workflow=create_run_workflow(
            prepare_plan=prepare,
            execute_journey=execute,
            collect_results=collect,
            max_journeys=12,
        ),
    )
    assert [item.status for item in result.journeys] == statuses
    assert len(set(seen)) == 3


async def test_execution_exception_stops_before_supervisor_or_reexecution() -> None:
    prepared = prepared_plan(1)
    seen: list[str] = []

    async def prepare() -> WorkflowPlan:
        return prepared

    async def execute(_: WorkflowPlan, journey: PersonaJourneySpec) -> PersonaJourneyResult:
        seen.append(journey.journey_key)
        raise RuntimeError("Durable result commit failed")

    async def collect(_: MultiPersonaExecutionResult) -> None:
        pytest.fail("Supervisor must not collect an uncommitted execution.")

    with pytest.raises(RuntimeError, match="Durable result commit failed"):
        await run_workflow(
            run_id=uuid4(),
            workflow=create_run_workflow(
                prepare_plan=prepare,
                execute_journey=execute,
                collect_results=collect,
                max_journeys=12,
            ),
        )
    assert len(seen) == 1


async def test_wrong_journey_result_is_not_collected() -> None:
    prepared = prepared_plan(1)
    journeys = build_persona_journeys(prepared.plan)

    async def prepare() -> WorkflowPlan:
        return prepared

    async def execute(_: WorkflowPlan, __: PersonaJourneySpec) -> PersonaJourneyResult:
        return PersonaJourneyResult(journey=journeys[1], status=JourneyExecutionStatus.COMPLETED)

    async def collect(_: MultiPersonaExecutionResult) -> None:
        pytest.fail("Wrong journey must not reach the supervisor.")

    with pytest.raises(RuntimeError, match="does not match"):
        await run_workflow(
            run_id=uuid4(),
            workflow=create_run_workflow(
                prepare_plan=prepare,
                execute_journey=execute,
                collect_results=collect,
                max_journeys=12,
            ),
        )


async def test_duplicate_plan_assignment_cannot_execute_twice() -> None:
    prepared = prepared_plan(1)
    duplicate = prepared.plan.model_copy(
        update={
            "personas": (
                prepared.plan.personas[0],
                prepared.plan.personas[0],
                prepared.plan.personas[2],
            ),
        }
    )

    async def prepare() -> WorkflowPlan:
        return prepared.model_copy(update={"plan": duplicate})

    async def execute(_: WorkflowPlan, __: PersonaJourneySpec) -> PersonaJourneyResult:
        pytest.fail("Duplicate assignments must be rejected before browser execution.")

    async def collect(_: MultiPersonaExecutionResult) -> None:
        pytest.fail("Invalid plans must not reach the supervisor.")

    with pytest.raises(ValueError, match="unique journey assignments"):
        await run_workflow(
            run_id=uuid4(),
            workflow=create_run_workflow(
                prepare_plan=prepare,
                execute_journey=execute,
                collect_results=collect,
                max_journeys=12,
            ),
        )


async def test_plan_over_depth_limit_cannot_execute() -> None:
    async def prepare() -> WorkflowPlan:
        return prepared_plan(2)

    async def execute(_: WorkflowPlan, __: PersonaJourneySpec) -> PersonaJourneyResult:
        pytest.fail("An over-budget plan must not start browser execution.")

    async def collect(_: MultiPersonaExecutionResult) -> None:
        pytest.fail("An over-budget plan must not reach collection.")

    with pytest.raises(ValueError, match="exceeds the selected journey limit"):
        await run_workflow(
            run_id=uuid4(),
            workflow=create_run_workflow(
                prepare_plan=prepare,
                execute_journey=execute,
                collect_results=collect,
                max_journeys=3,
            ),
        )
