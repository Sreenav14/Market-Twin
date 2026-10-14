"""Opt-in case execution through the existing persisted run lifecycle."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from markettwin_database.models import AgentExecution, ExecutionStep, PersonaJourney, TestRun
from markettwin_shared.deep_testing import CaseExecutionResult
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.agents.schemas.journey import PersonaJourneySpec
from markettwin_execution_orchestrator.agents.schemas.mission import TestMissionSpec
from markettwin_execution_orchestrator.agents.schemas.persona import PersonaSpec
from markettwin_execution_orchestrator.agents.schemas.test_case import (
    DeepFeaturePlan,
    FeatureScope,
    PlanBudget,
    Requirement,
    SafeTestValue,
    TestCaseSpec,
)
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.policy import validate_target_url
from markettwin_execution_orchestrator.persistence import ExecutionRepository, PlanRepository
from markettwin_execution_orchestrator.persistence.run_event_repository import RunEventRepository
from markettwin_execution_orchestrator.persistence.run_state_repository import RunStateRepository
from markettwin_execution_orchestrator.workflow.journey_executor import (
    PersonaJourneyExecutionRequest,
)
from markettwin_execution_orchestrator.workflow.test_case_planner import (
    DeepFeaturePlanningRequest,
    generate_feature_plan,
    persist_test_plan,
    validate_feature_plan,
)

if TYPE_CHECKING:
    from markettwin_execution_orchestrator.workflow.run_executor import MarketTwinRunRequest


@dataclass(frozen=True, slots=True)
class DeepFeatureRunResult:
    plan: DeepFeaturePlan
    cases: tuple[CaseExecutionResult, ...]
    coverage: dict[str, object]


def origin_url(origin: AllowedOrigin) -> str:
    host = f"[{origin.hostname}]" if ":" in origin.hostname else origin.hostname
    return f"{origin.scheme}://{host}" + (f":{origin.port}" if origin.port else "")


def default_scope(request: MarketTwinRunRequest) -> FeatureScope:
    return FeatureScope(
        feature_key="selected_feature",
        goal=request.study_brief[:1000],
        starting_url=request.start_url,
        allowed_origins=tuple(origin_url(origin) for origin in request.allowed_origins),
        safe_test_data=(
            SafeTestValue(key="valid_name", value="Visitor"),
            SafeTestValue(key="valid_email", value="fixture@example.test"),
            SafeTestValue(key="invalid_email", value="invalid"),
            SafeTestValue(key="empty", value=""),
        ),
        requirements=tuple(
            Requirement(
                requirement_id=f"knowledge_{index}",
                source="approved_knowledge",
                source_id=str(item["id"]),
                text=json.dumps(item.get("application_knowledge", item.get("name", "")))[:1000]
                or "Approved source",
            )
            for index, item in enumerate(request.knowledge_context)
            if "id" in item
        ),
        unknown_requirements=("Undocumented behavior has inferred expectations only.",),
        out_of_scope=("credentials", "payments", "uploads", "destructive actions"),
    )


def case_journey(case: TestCaseSpec) -> PersonaJourneySpec:
    persona = PersonaSpec(
        persona_id="feature_tester_v1",
        name="Feature tester",
        perspective="Bounded execution of approved feature cases.",
        behavior_traits=("methodical",),
        priorities=("observable assertions",),
    )
    mission = TestMissionSpec(
        mission_id=case.case_id,
        name=case.title[:100],
        objective=case.title[:500],
        success_criteria=tuple(
            f"{item.assertion_id}: {item.oracle} expected {item.expected_value}"
            for item in case.expected
        ),
        priority=case.priority,
    )
    return PersonaJourneySpec(
        journey_key=f"feature_tester_v1__{case.case_id}",
        persona=persona,
        mission=mission,
    )


def authorized_scope_snapshot(
    snapshot: dict[str, object],
    scope: FeatureScope,
) -> dict[str, object]:
    """Return the snapshot containing the exact scope the executor is allowed to run."""
    existing = snapshot.get("feature_scope")
    payload = scope.model_dump(mode="json")
    if existing is None:
        return {**snapshot, "feature_scope": payload}
    if FeatureScope.model_validate(existing) != scope:
        raise ValueError("Feature scope does not match the authorized snapshot.")
    return snapshot


async def freeze_authorized_scope(
    session: AsyncSession,
    test_run_id: UUID,
    scope: FeatureScope,
) -> None:
    run = await session.get(TestRun, test_run_id)
    if run is None:
        raise ValueError("Authorized test run is missing.")
    updated = authorized_scope_snapshot(dict(run.configuration_snapshot), scope)
    if updated != dict(run.configuration_snapshot):
        run.configuration_snapshot = updated
        await session.commit()


def skip_reason(
    *,
    remaining_seconds: float,
    remaining_steps: int,
    case: TestCaseSpec,
) -> str | None:
    """Return why a case cannot start; the model cannot extend this budget."""
    required_steps = len(case.steps) + len(case.expected) + 1
    if remaining_seconds < 1:
        return "time_budget"
    if remaining_steps < required_steps:
        return "step_budget"
    return None


def coverage_summary(
    plan: DeepFeaturePlan,
    results: tuple[CaseExecutionResult, ...],
) -> dict[str, object]:
    ids = {result.case_id for result in results}
    if len(ids) != len(results) or not ids.issubset({case.case_id for case in plan.cases}):
        raise ValueError("Case collection contains duplicate or foreign results.")
    return {
        "schema_version": 1,
        "planned": len(plan.cases) + len(plan.skipped),
        "executed": len(results),
        "covered": sum(bool(item.assertion_results) for item in results),
        "passed": sum(item.verdict == "satisfied" for item in results),
        "failed_assertions": sum(
            assertion.status == "not_satisfied"
            for item in results
            for assertion in item.assertion_results
        ),
        "blocked": sum(item.execution_status == "policy_blocked" for item in results),
        "inconclusive": sum(
            item.verdict == "unverified" and item.execution_status != "policy_blocked"
            for item in results
        ),
        "not_run": len(plan.skipped) + len(plan.cases) - len(results),
        "missing_case_ids": [case.case_id for case in plan.cases if case.case_id not in ids],
        "unknown_requirements": list(plan.scope.unknown_requirements),
        "coverage_gaps": list(plan.coverage_gaps),
    }


async def execute_deep_feature_run(
    *,
    request: MarketTwinRunRequest,
    session: AsyncSession,
) -> DeepFeatureRunResult:
    from markettwin_execution_orchestrator.workflow.case_execution import execute_test_case

    scope = (
        FeatureScope.model_validate(request.feature_scope)
        if request.feature_scope is not None
        else default_scope(request)
    )
    if scope.starting_url != request.start_url:
        raise ValueError("Feature scope cannot change the frozen starting URL.")
    for origin in scope.allowed_origins:
        validate_target_url(origin, request.allowed_origins, request.network_policy)
    if request.fixture_truth and request.network_policy != "local_development":
        raise ValueError("Fixture truth requires an explicit local development request.")
    await freeze_authorized_scope(session, request.run_id, scope)
    budget = PlanBudget.model_validate(request.feature_budget or {})
    planning = DeepFeaturePlanningRequest(
        test_run_id=request.run_id,
        scope=scope,
        budget=budget,
        approved_source_ids=frozenset(
            str(item["id"]) for item in request.knowledge_context if "id" in item
        ),
        allow_fixture_truth=request.fixture_truth,
        supported_actions=frozenset(
            {
                "navigate",
                "click",
                "fill",
                "select",
                "wait",
                "focus_next",
                "set_viewport",
                "check",
                "uncheck",
            }
        ),
    )
    states, events = RunStateRepository(session), RunEventRepository(session)
    executions = ExecutionRepository(session)
    await states.mark_planning(test_run_id=request.run_id)
    await session.commit()
    try:
        if request.feature_plan is not None:
            plan = DeepFeaturePlan.model_validate(request.feature_plan)
            validate_feature_plan(plan, planning)
            await persist_test_plan(session=session, request=planning, plan=plan)
        else:
            async with BrowserController() as discovery:
                handle = await discovery.create_session(
                    execution_id=uuid4(),
                    journey_id=uuid4(),
                    allowed_origins=request.allowed_origins,
                    network_policy=request.network_policy,
                )
                try:
                    state = await discovery.navigate(
                        session_id=handle.session_id,
                        url=scope.starting_url,
                    )
                    planning = replace(planning, page_context=state.observation.to_dict())
                finally:
                    await discovery.close_session(session_id=handle.session_id)
            plan = await generate_feature_plan(request=planning, session=session)
        persisted = await PlanRepository(session).create_from_feature_cases(
            test_run_id=request.run_id,
            plan=plan,
        )
        await states.mark_running(test_run_id=request.run_id)
        await session.commit()
        persona_id = persisted.personas[0].persona_id
        missions = {item.mission_key: item.mission_id for item in persisted.missions}
        journeys = {item.journey_key: item.journey_id for item in persisted.journeys}
        results: list[CaseExecutionResult] = []
        started = time.monotonic()
        async with BrowserController() as controller:
            for case in plan.cases:
                remaining = budget.max_total_seconds - (time.monotonic() - started)
                recorded_steps = await session.scalar(
                    select(func.count())
                    .select_from(ExecutionStep)
                    .join(AgentExecution, AgentExecution.id == ExecutionStep.execution_id)
                    .join(PersonaJourney, PersonaJourney.id == AgentExecution.journey_id)
                    .where(PersonaJourney.test_run_id == request.run_id)
                )
                remaining_steps = budget.max_steps - int(recorded_steps or 0)
                reason = skip_reason(
                    remaining_seconds=remaining,
                    remaining_steps=remaining_steps,
                    case=case,
                )
                if reason is not None:
                    await events.create(
                        test_run_id=request.run_id,
                        event_type="test_case.skipped",
                        journey_id=journeys[f"feature_tester_v1__{case.case_id}"],
                        execution_id=None,
                        payload={
                            "schema_version": 1,
                            "case_id": case.case_id,
                            "reason": reason,
                            "status": "not_run",
                        },
                    )
                    continue
                journey = case_journey(case)
                journey_id, execution_id = journeys[journey.journey_key], uuid4()
                await executions.create_agent_execution(
                    execution_id=execution_id,
                    journey_id=journey_id,
                    runtime_name="deterministic_case_steps_v1",
                )
                await session.commit()
                result = await execute_test_case(
                    request=PersonaJourneyExecutionRequest(
                        test_run_id=request.run_id,
                        execution_id=execution_id,
                        journey_id=journey_id,
                        persona_id=persona_id,
                        mission_id=missions[case.case_id],
                        journey=journey,
                        start_url=scope.starting_url,
                        allowed_origins=request.allowed_origins,
                        network_policy=request.network_policy,
                        max_duration_seconds=max(
                            1, min(int(remaining), request.max_duration_seconds_per_journey)
                        ),
                    ),
                    case=case,
                    scope=scope,
                    budget=budget.model_copy(update={"max_steps": remaining_steps}),
                    controller=controller,
                    session=session,
                )
                outcome = {
                    "satisfied": "passed",
                    "not_satisfied": "failed",
                    "unverified": "inconclusive",
                }[result.verdict]
                status = result.execution_status
                await executions.finish_agent_execution(
                    execution_id=execution_id,
                    status="timed_out" if status == "budget_exhausted" else status,
                    outcome=outcome if status == "completed" else None,
                    error_code=result.blocker,
                )
                payload = result.model_dump(mode="json")
                await events.create(
                    test_run_id=request.run_id,
                    event_type="journey.result",
                    journey_id=journey_id,
                    execution_id=execution_id,
                    payload={
                        **payload,
                        "mode": "deep_feature_v1",
                        "status": status,
                        "outcome": outcome if status == "completed" else None,
                        "journey_key": journey.journey_key,
                        "summary": f"Case {case.case_id}: {result.verdict}.",
                    },
                )
                await session.commit()
                results.append(result)
        coverage = coverage_summary(plan, tuple(results))
        for event_type in ("test_run.coverage", "run.collection"):
            await events.create(
                test_run_id=request.run_id,
                event_type=event_type,
                journey_id=None,
                execution_id=None,
                payload=coverage if event_type == "test_run.coverage" else {
                    **coverage, "mode": "deep_feature_v1", "journey_count": len(results),
                    "completed_count": sum(item.execution_status == "completed" for item in results),
                    "failed_count": sum(item.execution_status != "completed" for item in results),
                },
            )
        await states.mark_completed(test_run_id=request.run_id)
        await session.commit()
        return DeepFeatureRunResult(plan=plan, cases=tuple(results), coverage=coverage)
    except Exception:
        await session.rollback()
        await states.mark_failed(test_run_id=request.run_id)
        await session.commit()
        raise
