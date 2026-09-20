"""Tests for MarketTwin Persona Agent construction."""

import pytest
from markettwin_execution_orchestrator.agents import persona_agents
from markettwin_execution_orchestrator.agents.schemas.journey import (
    PersonaJourneySpec,
)
from markettwin_execution_orchestrator.agents.schemas.mission import (
    TestMissionSpec,
)
from markettwin_execution_orchestrator.agents.schemas.persona import (
    PersonaSpec,
)


def test_persona_agent_builds_json_response_instruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Persona Agent instruction must contain literal JSON braces."""

    monkeypatch.setattr(
        persona_agents,
        "create_model",
        lambda: "openai/gpt-4o-mini",
    )

    journey = PersonaJourneySpec(
        journey_key="user1__mission1",
        persona=PersonaSpec(
            persona_id="user1",
            name="Test User",
            perspective="A careful user.",
            behavior_traits=("careful",),
            priorities=("clarity",),
        ),
        mission=TestMissionSpec(
            mission_id="mission1",
            name="Verify page",
            objective="Verify that the page is accessible.",
            success_criteria=("Page is accessible.",),
            priority="high",
        ),
    )

    agent = persona_agents.create_persona_agent(
        journey=journey,
        browser_tools=(),
    )

    instruction = agent.instruction

    assert isinstance(instruction, str)
    assert '"outcome": "passed | failed | partial | inconclusive"' in (
        instruction
    )
    assert '"final_url": "final browser URL or null"' in (
        instruction
    )

    assert (
        "Do not mark a success criterion as unsatisfied merely because"
        in instruction
    )

    assert (
        'Treat "not observed" and "observed to be false" as different things.'
        in instruction
    )

    assert (
        "Only place a criterion in unsatisfied_criteria when browser evidence"
        in instruction
    )
    assert (
        "Treat visible_elements as the primary representation"
        in instruction
    )

    assert (
        "Treat aria_snapshot as supplementary semantic context"
        in instruction
    )

    assert (
        "screenshot_path means screenshot evidence was captured"
        in instruction
    )

    assert (
        "Do not infer properties such as visual legibility"
        in instruction
    )
    assert '"criterion_evidence": [' in instruction

    assert (
        '"status": "satisfied | unsatisfied | unverified"'
        in instruction
    )

    assert (
        "evidence_step_ids must contain only browser step IDs"
        in instruction
    )

    assert (
        "Do not invent step IDs."
        in instruction
    )

    assert (
        "Use browser_capture_element when a success criterion"
        in instruction
    )

    assert (
        "Use browser_take_screenshot when a visual criterion"
        in instruction
    )
