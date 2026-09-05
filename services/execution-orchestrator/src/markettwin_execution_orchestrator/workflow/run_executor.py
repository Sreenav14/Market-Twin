"""Top-level in-memory MarketTwin test-run orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

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
from markettwin_execution_orchestrator.workflow.multi_persona_executor import (
    MultiPersonaExecutionRequest,
    execute_multi_persona_plan,
)
from markettwin_execution_orchestrator.workflow.multi_persona_result import (
    MultiPersonaExecutionResult,
)
from markettwin_execution_orchestrator.workflow.planning import (
    MetaPlanningRequest,
    generate_meta_agent_plan,
)


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


async def execute_markettwin_run(
    request: MarketTwinRunRequest,
) -> MultiPersonaExecutionResult:
    """Plan and execute one complete MarketTwin test run."""

    study_brief = request.study_brief.strip()

    if not study_brief:
        raise ValueError("study_brief must not be empty.")

    if not request.allowed_origins:
        raise ValueError("At least one allowed origin is required.")

    if request.max_duration_seconds_per_journey <= 0:
        raise ValueError(
            "max_duration_seconds_per_journey must be positive."
        )

    validated_start_url = validate_target_url(
        request.start_url,
        request.allowed_origins,
        request.network_policy,
    )

    plan = await generate_meta_agent_plan(
        MetaPlanningRequest(
            test_run_id=request.run_id,
            study_brief=study_brief,
            target_snapshot=request.target_snapshot,
        )
    )

    async with BrowserController() as browser_controller:
        return await execute_multi_persona_plan(
            request=MultiPersonaExecutionRequest(
                run_id=request.run_id,
                plan=plan,
                start_url=validated_start_url.href,
                allowed_origins=request.allowed_origins,
                network_policy=request.network_policy,
                max_duration_seconds_per_journey=(
                    request.max_duration_seconds_per_journey
                ),
            ),
            browser_controller=browser_controller,
        )