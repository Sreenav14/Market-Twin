"""Build immutable historical snapshots of effective MarketTwin agents."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from markettwin_shared.observability import AgentRuntimeSnapshotSpec

from markettwin_execution_orchestrator.agents.schemas.journey import (
    PersonaJourneySpec,
)
from markettwin_execution_orchestrator.models.model_factory import (
    ModelRuntimeConfig,
)

SNAPSHOT_SCHEMA_VERSION = 1
META_AGENT_VERSION = "1"
PERSONA_AGENT_VERSION = "1"
META_TEMPLATE_VERSION = "python-v1"
PERSONA_TEMPLATE_VERSION = "python-v1"


def build_meta_runtime_snapshot(
    *,
    test_run_id: UUID,
    runtime_agent_name: str,
    model_config: ModelRuntimeConfig,
    effective_instruction: str,
    runtime_prompt: str,
) -> AgentRuntimeSnapshotSpec:
    """Build the exact Meta Agent configuration used for one TestRun."""

    return AgentRuntimeSnapshotSpec(
        test_run_id=str(test_run_id),
        agent_role="meta",
        runtime_agent_name=runtime_agent_name,
        runtime_kind="google_adk",
        agent_version=META_AGENT_VERSION,
        snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
        template_id="meta_agent",
        template_version=META_TEMPLATE_VERSION,
        model_provider=model_config.provider,
        model_name=model_config.model_name,
        model_configuration=model_config.snapshot(),
        base_instruction=effective_instruction,
        effective_instruction=effective_instruction,
        runtime_prompt=runtime_prompt,
        tools=(),
        metadata={
            "output_contract": "MetaAgentPlan",
        },
    )


def build_persona_runtime_snapshot(
    *,
    test_run_id: UUID,
    journey_id: UUID,
    execution_id: UUID,
    journey: PersonaJourneySpec,
    runtime_agent_name: str,
    model_config: ModelRuntimeConfig,
    effective_instruction: str,
    runtime_prompt: str,
    tools: Sequence[object],
) -> AgentRuntimeSnapshotSpec:
    """Build the exact effective Persona Agent configuration for one Journey."""

    return AgentRuntimeSnapshotSpec(
        test_run_id=str(test_run_id),
        journey_id=str(journey_id),
        execution_id=str(execution_id),
        agent_role="persona",
        runtime_agent_name=runtime_agent_name,
        runtime_kind="google_adk",
        agent_version=PERSONA_AGENT_VERSION,
        snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
        template_id="persona_agent",
        template_version=PERSONA_TEMPLATE_VERSION,
        model_provider=model_config.provider,
        model_name=model_config.model_name,
        model_configuration=model_config.snapshot(),
        base_instruction=None,
        effective_instruction=effective_instruction,
        runtime_prompt=runtime_prompt,
        persona_snapshot={
            "persona_id": journey.persona.persona_id,
            "name": journey.persona.name,
            "perspective": journey.persona.perspective,
            "behavior_traits": list(
                journey.persona.behavior_traits
            ),
            "priorities": list(
                journey.persona.priorities
            ),
        },
        mission_snapshot={
            "mission_id": journey.mission.mission_id,
            "name": journey.mission.name,
            "objective": journey.mission.objective,
            "priority": journey.mission.priority,
        },
        success_criteria=tuple(
            journey.mission.success_criteria
        ),
        tools=tuple(
            _tool_name(tool)
            for tool in tools
        ),
        policy_references={
            "browser_authority": "BrowserController",
            "sensitive_input_policy": "human_assistance_required",
        },
        metadata={
            "journey_key": journey.journey_key,
        },
    )


def _tool_name(tool: object) -> str:
    name = getattr(
        tool,
        "name",
        None,
    )

    if isinstance(name, str) and name:
        return name

    callable_name = getattr(
        tool,
        "__name__",
        None,
    )

    if isinstance(callable_name, str) and callable_name:
        return callable_name

    return type(tool).__name__
