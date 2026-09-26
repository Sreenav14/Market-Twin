from google.adk.agents import LlmAgent
from markettwin_execution_orchestrator.agents.persona_agents import (
    build_persona_runtime_snapshot_payload,
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
from pytest import MonkeyPatch


async def browser_get_state() -> dict[str, object]:
    return {}


def test_build_persona_runtime_snapshot_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MODEL_PROVIDER",
        "openai",
    )
    monkeypatch.setenv(
        "MODEL_NAME",
        "gpt-4o-mini",
    )
    monkeypatch.setenv(
        "MODEL_API_KEY",
        "must-not-appear",
    )

    journey = PersonaJourneySpec(
        journey_key="persona_1__mission_1",
        persona=PersonaSpec(
            persona_id="persona_1",
            name="First-time user",
            perspective=(
                "A new user evaluating the product."
            ),
            behavior_traits=(
                "careful",
                "curious",
            ),
            priorities=(
                "clarity",
                "pricing",
            ),
        ),
        mission=TestMissionSpec(
            mission_id="mission_1",
            name="Find pricing",
            objective=(
                "Determine whether pricing is easy to find."
            ),
            success_criteria=(
                "Pricing information is discoverable.",
            ),
            priority="high",
        ),
    )

    agent = LlmAgent(
        name="markettwin_persona_1__mission_1",
        model="openai/gpt-4o-mini",
        instruction="Act as the assigned persona.",
    )

    payload = build_persona_runtime_snapshot_payload(
        journey=journey,
        agent=agent,
        browser_tools=(
            browser_get_state,
        ),
        runtime_prompt=(
            "Execute your assigned MarketTwin Journey."
        ),
    )

    assert payload.agent_role == "persona"
    assert payload.runtime_kind == "google_adk"

    assert (
        payload.runtime_agent_name
        == "markettwin_persona_1__mission_1"
    )

    assert payload.model_provider == "openai"
    assert payload.model_name == "openai/gpt-4o-mini"

    assert payload.model_configuration == {
        "max_tokens": 512,
        "num_retries": 2,
    }

    assert payload.effective_instruction == (
        "Act as the assigned persona."
    )

    assert payload.runtime_prompt == (
        "Execute your assigned MarketTwin Journey."
    )

    assert payload.success_criteria == (
        "Pricing information is discoverable.",
    )

    assert payload.tools == (
        "browser_get_state",
    )

    assert payload.metadata == {
        "journey_key": "persona_1__mission_1",
    }

    assert "must-not-appear" not in (
        payload.canonical_json()
    )