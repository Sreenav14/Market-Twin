from uuid import uuid4

from markettwin_execution_orchestrator.agents.schemas.journey import (
    PersonaJourneySpec,
)
from markettwin_execution_orchestrator.agents.schemas.mission import (
    TestMissionSpec,
)
from markettwin_execution_orchestrator.agents.schemas.persona import (
    PersonaSpec,
)
from markettwin_execution_orchestrator.workflow.journey_executor import (
    PersonaJourneyExecutionRequest,
)


def test_persona_journey_execution_request_keeps_run_identity() -> None:
    test_run_id = uuid4()
    execution_id = uuid4()
    journey_id = uuid4()
    persona_id = uuid4()
    mission_id = uuid4()

    journey = PersonaJourneySpec(
        journey_key="persona_1__mission_1",
        persona=PersonaSpec(
            persona_id="persona_1",
            name="First-time user",
            perspective="A new user.",
            behavior_traits=(
                "careful",
            ),
            priorities=(
                "clarity",
            ),
        ),
        mission=TestMissionSpec(
            mission_id="mission_1",
            name="Find pricing",
            objective="Find pricing information.",
            success_criteria=(
                "Pricing is discoverable.",
            ),
            priority="high",
        ),
    )

    request = PersonaJourneyExecutionRequest(
        test_run_id=test_run_id,
        execution_id=execution_id,
        journey_id=journey_id,
        persona_id=persona_id,
        mission_id=mission_id,
        journey=journey,
        start_url="https://example.com/",
        allowed_origins=(),
    )

    assert request.test_run_id == test_run_id
    assert request.execution_id == execution_id
    assert request.journey_id == journey_id
    assert request.persona_id == persona_id
    assert request.mission_id == mission_id