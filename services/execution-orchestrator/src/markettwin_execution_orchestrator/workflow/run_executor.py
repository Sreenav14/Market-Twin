"""Top-level persisted MarketTwin test-run orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from markettwin_shared.action_approval import SensitiveActionRule
from markettwin_shared.auth_verification import AuthVerificationPolicy
from markettwin_shared.deep_testing import CaseExecutionResult
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.browser import AllowedOrigin
from markettwin_execution_orchestrator.browser.contracts import (
    NetworkPolicy,
)
from markettwin_execution_orchestrator.browser.policy import (
    validate_target_url,
)
from markettwin_execution_orchestrator.observability import (
    initialize_adk_observability,
)
from markettwin_execution_orchestrator.workflow.testing_depth import TestingDepth


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
    knowledge_context: tuple[dict[str, object], ...] = ()
    testing_depth: TestingDepth = "high"
    # Unified run kind, resolved from the run_kind column / legacy mode
    # (U-P0-04/05); dispatch switches on it (U-P8).
    run_kind: Literal["explore_test", "persona", "slop"] = "explore_test"
    # True when the run was created unified-native: a run_kind column
    # value and NO legacy execution_mode in its snapshot (U-P1-06).
    unified_native: bool = False
    feature_plan: dict[str, object] | None = None
    fixture_truth: bool = False
    auth_verification: AuthVerificationPolicy | None = None
    auth_mode: Literal["required", "optional"] = "required"
    runtime_human_assistance: bool = False
    synthetic_fixture_approval_enabled: bool = False
    human_action_approvals_enabled: bool = False
    fixture_action_rules: tuple[SensitiveActionRule, ...] = ()
    created_by_user_id: UUID | None = None


async def execute_markettwin_run(
    request: MarketTwinRunRequest,
    *,
    session: AsyncSession,
) -> (
    tuple[CaseExecutionResult, ...] | None
):
    """Bind durable provider limits for every execution entry point."""
    from markettwin_database.model_budget import model_budget

    with model_budget(session, request.run_id):
        return await _execute_markettwin_run(request, session=session)


async def _execute_markettwin_run(
    request: MarketTwinRunRequest,
    *,
    session: AsyncSession,
) -> (
    tuple[CaseExecutionResult, ...] | None
):
    """Execute one unified run: exactly three kinds exist (U-P8).

    explore_test runs on the Board engine (the successor of the
    harness/discovery/deep modes); persona and slop run their native
    executors and only as unified-native runs — legacy runs of those
    kinds were retired with the legacy engines and refuse loudly
    instead of silently running a dead path.
    """

    initialize_adk_observability()

    study_brief = request.study_brief.strip()

    if not study_brief:
        raise ValueError("study_brief must not be empty.")

    if not request.allowed_origins:
        raise ValueError("At least one allowed origin is required.")

    if request.max_duration_seconds_per_journey <= 0:
        raise ValueError("max_duration_seconds_per_journey must be positive.")

    # Validation only: the engines navigate to request.start_url; the
    # normalized form's one consumer was the retired legacy persona
    # path. The call stays because it raises on a disallowed target.
    validate_target_url(
        request.start_url,
        request.allowed_origins,
        request.network_policy,
    )

    if request.run_kind == "persona":
        if not request.unified_native:
            raise ValueError(
                "Legacy persona runs were retired in the unified build; "
                "create a new Persona Test run instead."
            )
        from markettwin_execution_orchestrator.workflow.persona_run import (
            execute_persona_run,
        )

        return await execute_persona_run(request=request, session=session)
    if request.run_kind == "slop":
        if not request.unified_native:
            raise ValueError(
                "Slop runs have no legacy form; create the run with "
                "run_kind only."
            )
        from markettwin_execution_orchestrator.workflow.slop_run import (
            execute_slop_run,
        )

        return await execute_slop_run(request=request, session=session)
    from markettwin_execution_orchestrator.workflow.harness_run import (
        execute_harness_run,
    )

    return await execute_harness_run(request=request, session=session)
