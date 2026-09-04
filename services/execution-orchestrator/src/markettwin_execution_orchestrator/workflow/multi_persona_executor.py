"""Execute every Persona Journey in one MarketTwin Meta Agent plan."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

from markettwin_execution_orchestrator.agents.meta_agent_factory import (
    MetaAgentFactory,
)
from markettwin_execution_orchestrator.agents.schemas.plan import (
    MetaAgentPlan,
)
from markettwin_execution_orchestrator.browser import (
    AllowedOrigin,
    BrowserController,
)
from markettwin_execution_orchestrator.browser.contracts import (
    NetworkPolicy,
)
from markettwin_execution_orchestrator.workflow.journey_executor import (
    PersonaJourneyExecutionRequest,
    execute_persona_journey,
)
from markettwin_execution_orchestrator.workflow.journey_planner import (
    build_persona_journeys,
)
from markettwin_execution_orchestrator.workflow.multi_persona_result import (
    MultiPersonaExecutionResult,
)
from markettwin_execution_orchestrator.workflow.persona_result import (
    PersonaJourneyResult,
)


@dataclass(frozen=True, slots=True)
class MultiPersonaExecutionRequest:
    """Inputs required to execute one already-generated MarketTwin plan."""

    run_id: UUID
    plan: MetaAgentPlan

    start_url: str
    allowed_origins: tuple[AllowedOrigin, ...]

    network_policy: NetworkPolicy = "public_only"
    max_duration_seconds_per_journey: int = 180


async def execute_multi_persona_plan(
    *,
    request: MultiPersonaExecutionRequest,
    browser_controller: BrowserController,
    factory: MetaAgentFactory | None = None,
) -> MultiPersonaExecutionResult:
    """Execute every Persona × Mission Journey sequentially."""

    if not request.allowed_origins:
        raise ValueError("At least one allowed origin is required.")

    if request.max_duration_seconds_per_journey <= 0:
        raise ValueError(
            "max_duration_seconds_per_journey must be positive."
        )

    journeys = build_persona_journeys(request.plan)

    runtime_factory = factory or MetaAgentFactory()

    results: list[PersonaJourneyResult] = []

    for journey in journeys:
        execution_id = uuid4()
        journey_id = uuid4()

        result = await execute_persona_journey(
            request=PersonaJourneyExecutionRequest(
                execution_id=execution_id,
                journey_id=journey_id,
                journey=journey,
                start_url=request.start_url,
                allowed_origins=request.allowed_origins,
                network_policy=request.network_policy,
                max_duration_seconds=(
                    request.max_duration_seconds_per_journey
                ),
            ),
            browser_controller=browser_controller,
            factory=runtime_factory,
        )

        results.append(result)

    return MultiPersonaExecutionResult(
        plan=request.plan,
        journeys=tuple(results),
    )
    
JourneyExecutor = Callable[
    ...,
    Awaitable[PersonaJourneyResult],
]