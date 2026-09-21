"""Tests for immutable MarketTwin agent runtime snapshots."""

from uuid import uuid4

from markettwin_execution_orchestrator.agents.runtime_snapshot import (
    build_persona_runtime_snapshot,
)
from markettwin_execution_orchestrator.agents.schemas.journey import (
    PersonaJourneySpec,
)
from markettwin_execution_orchestrator.agents.schemas.mission import (
    TestMissionSpec,
)
from markettwin_execution_orchestrator.agents.schemas.persona import (
    PersonaSpec,
)
from markettwin_execution_orchestrator.models.model_factory import (
    ModelRuntimeConfig,
)


def test_persona_snapshot_captures_effective_runtime_truth() -> None:
    journey = PersonaJourneySpec(
        journey_key="careful__pricing",
        persona=PersonaSpec(
            persona_id="careful",
            name="Careful User",
            perspective="A trust-sensitive first-time visitor.",
            behavior_traits=("careful", "methodical"),
            priorities=("clarity", "trust"),
        ),
        mission=TestMissionSpec(
            mission_id="pricing",
            name="Understand pricing",
            objective="Understand the pricing offer.",
            success_criteria=(
                "The plan price is visible.",
                "The billing condition is understandable.",
            ),
            priority="high",
        ),
    )

    def browser_get_state() -> None:
        return None

    snapshot = build_persona_runtime_snapshot(
        test_run_id=uuid4(),
        journey_id=uuid4(),
        execution_id=uuid4(),
        journey=journey,
        runtime_agent_name="markettwin_careful__pricing",
        model_config=ModelRuntimeConfig(
            provider="openai",
            model_name="openai/gpt-4o-mini",
            max_tokens=512,
            num_retries=2,
        ),
        effective_instruction="Exact effective persona instruction.",
        runtime_prompt="Exact initial Journey prompt.",
        tools=(browser_get_state,),
    )

    assert snapshot.agent_role == "persona"
    assert snapshot.runtime_kind == "google_adk"
    assert snapshot.persona_snapshot is not None
    assert snapshot.persona_snapshot["name"] == "Careful User"
    assert snapshot.mission_snapshot is not None
    assert snapshot.mission_snapshot["name"] == "Understand pricing"
    assert snapshot.success_criteria == (
        "The plan price is visible.",
        "The billing condition is understandable.",
    )
    assert snapshot.tools == ("browser_get_state",)
    assert snapshot.effective_instruction == (
        "Exact effective persona instruction."
    )
    assert snapshot.runtime_prompt == "Exact initial Journey prompt."
    assert "api_key" not in snapshot.model_configuration
