from markettwin_execution_orchestrator.agents.schemas.mission import (
    TestMissionSpec,
)
from markettwin_execution_orchestrator.agents.schemas.persona import (
    PersonaSpec,
)
from markettwin_execution_orchestrator.agents.schemas.plan import (
    MetaAgentPlan,
)
from markettwin_execution_orchestrator.workflow.journey_planner import (
    build_persona_journeys,
)


def make_persona(
    persona_id: str,
) -> PersonaSpec:
    return PersonaSpec(
        persona_id=persona_id,
        name=persona_id,
        perspective="A realistic user perspective.",
        behavior_traits=("careful",),
        priorities=("clarity",),
    )


def make_mission(
    mission_id: str,
) -> TestMissionSpec:
    return TestMissionSpec(
        mission_id=mission_id,
        name=mission_id,
        objective="Complete the bounded task.",
        success_criteria=("Task completed",),
    )


def test_build_persona_journeys_creates_cross_product() -> None:
    plan = MetaAgentPlan(
        mission_summary="Test important product flows.",
        personas=(
            make_persona("persona_a"),
            make_persona("persona_b"),
            make_persona("persona_c"),
        ),
        missions=(
            make_mission("mission_one"),
            make_mission("mission_two"),
        ),
    )

    journeys = build_persona_journeys(plan)

    assert len(journeys) == 6

    assert {
        journey.journey_key
        for journey in journeys
    } == {
        "persona_a__mission_one",
        "persona_a__mission_two",
        "persona_b__mission_one",
        "persona_b__mission_two",
        "persona_c__mission_one",
        "persona_c__mission_two",
    }