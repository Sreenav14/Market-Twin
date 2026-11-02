"""Execute frozen journeys and one clean confirmation attempt using the case engine."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from uuid import uuid4

from markettwin_database.models import (
    ExecutionStep,
    PersonaJourney,
    RunMission,
    RunPersona,
    TestRun,
)
from markettwin_shared.contract_execution import contract_case
from markettwin_shared.deep_testing import CaseExecutionResult
from markettwin_shared.discovery_contract import TestContract
from markettwin_shared.feature_plan import FeatureScope, PlanBudget, TestCaseSpec
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserActionBlockedError
from markettwin_execution_orchestrator.persistence import ExecutionRepository
from markettwin_execution_orchestrator.persistence.run_event_repository import RunEventRepository
from markettwin_execution_orchestrator.persistence.run_state_repository import RunStateRepository
from markettwin_execution_orchestrator.workflow.case_execution import execute_test_case
from markettwin_execution_orchestrator.workflow.deep_run import (
    case_journey,
    default_scope,
    origin_url,
)
from markettwin_execution_orchestrator.workflow.journey_executor import (
    PersonaJourneyExecutionRequest,
)
from markettwin_execution_orchestrator.workflow.testing_depth import feature_case_limit

if TYPE_CHECKING:
    from markettwin_execution_orchestrator.workflow.run_executor import MarketTwinRunRequest


async def execute_contract_run(
    *, request: MarketTwinRunRequest, session: AsyncSession,
) -> tuple[CaseExecutionResult, ...]:
    run = await session.get(TestRun, request.run_id)
    if run is None:
        raise ValueError("Contract run does not exist.")
    contract = TestContract.model_validate(run.configuration_snapshot.get("frozen_contract"))
    if (contract.status != "frozen" or contract.test_run_id != request.run_id
            or contract.approved_by_user_id is None or contract.approved_at is None
            or run.configuration_snapshot.get("frozen_contract_hash") != contract.content_hash()):
        raise ValueError("Approved frozen contract identity or hash does not match this run.")
    states, events = RunStateRepository(session), RunEventRepository(session)
    executions = ExecutionRepository(session)
    await states.mark_running(test_run_id=request.run_id)
    await session.commit()
    start = urlsplit(request.start_url)
    origin = f"{start.scheme}://{start.netloc}"
    selected = [j for j in contract.journeys if not j.excluded
                and any(not a.excluded for a in j.assertions)]
    cases: list[TestCaseSpec] = []
    for index, journey in enumerate(selected):
        reason = None
        if index >= feature_case_limit(request.testing_depth):
            reason = "testing_depth_budget"
        else:
            try:
                cases.append(contract_case(journey, origin))
            except (ValueError, ValidationError):
                reason = "unsupported_case_bounds_or_check"
        if reason:
            await events.create(test_run_id=request.run_id, event_type="contract.journey.skipped",
                                journey_id=None, execution_id=None,
                                payload={"journey_key": journey.journey_key, "reason": reason})
    identity = {"contract_id": str(contract.contract_id), "contract_version": contract.version,
                "contract_hash": contract.content_hash()}
    await events.create(test_run_id=request.run_id, event_type="contract.execution_plan",
                        journey_id=None, execution_id=None, payload={
                            **identity, "cases": [c.model_dump(mode="json") for c in cases],
                        })
    results: list[CaseExecutionResult] = []
    missions = {case.case_id: uuid4() for case in cases}
    for ordinal, case in enumerate(cases, start=1):
        session.add(RunMission(
            id=missions[case.case_id], test_run_id=request.run_id, ordinal=ordinal,
            title=case.title[:100], objective=case.title,
            success_criteria=[a.assertion_id for a in case.expected], priority=case.priority,
        ))
    await session.flush()
    async with BrowserController() as controller:
        for persona_index, name in enumerate(
            ("First-time user", "Experienced user", "Mobile user"),
        ):
            persona_id = uuid4()
            session.add(RunPersona(
                id=persona_id, test_run_id=request.run_id, ordinal=persona_index + 1,
                name=name, description=f"Frozen journey perspective: {name}",
                attributes={"executor_role": True, "contract_persona": persona_index,
                            "viewport": "mobile320" if persona_index == 2 else "desktop1280"},
            ))
            await session.flush()
            for case_index, case in enumerate(cases):
                mission_id, journey_id = missions[case.case_id], uuid4()
                ordinal = persona_index * len(cases) + case_index + 1
                session.add(PersonaJourney(id=journey_id, test_run_id=request.run_id,
                                          persona_id=persona_id, mission_id=mission_id,
                                          ordinal=ordinal))
                await session.commit()
                base_scope = default_scope(request)
                scope = FeatureScope(
                    feature_key=case.feature_key, goal=request.study_brief[:1000],
                    starting_url=request.start_url,
                    allowed_origins=tuple(origin_url(o) for o in request.allowed_origins),
                    safe_test_data=tuple(v.model_copy(update={"value": (
                        f"Visitor{persona_index + 1}" if v.key == "valid_name" else
                        f"visitor{persona_index + 1}@example.test" if v.key == "valid_email"
                        else v.value
                    )}) for v in base_scope.safe_test_data),
                )
                original = None
                for attempt in (1, 2):
                    execution_id = uuid4()
                    await executions.create_agent_execution(
                        execution_id=execution_id, journey_id=journey_id, attempt_number=attempt,
                        runtime_name="discovery_contract_v1",
                    )
                    if original is not None:
                        await events.create(
                            test_run_id=request.run_id, journey_id=journey_id,
                            execution_id=execution_id, event_type="test_case.replay",
                            payload={**identity,
                                     "replay_of_execution_id": str(original.execution_id)},
                        )
                    await session.commit()
                    result = await execute_test_case(
                        request=PersonaJourneyExecutionRequest(
                            test_run_id=request.run_id, execution_id=execution_id,
                            journey_id=journey_id, persona_id=persona_id, mission_id=mission_id,
                            journey=case_journey(case), start_url=request.start_url,
                            allowed_origins=request.allowed_origins,
                            network_policy=request.network_policy, max_duration_seconds=240,
                            viewport_preset="mobile320" if persona_index == 2 else "desktop1280",
                            fixture_action_rules=request.fixture_action_rules,
                        ), case=case, scope=scope, budget=PlanBudget(max_steps=96),
                        controller=controller, session=session,
                    )
                    completed_steps = await session.scalar(
                        select(func.count(ExecutionStep.id)).where(
                            ExecutionStep.execution_id == execution_id,
                            ExecutionStep.id.in_(result.action_step_ids),
                            ExecutionStep.status == "completed",
                            ExecutionStep.action_type != "assertion",
                        )
                    ) or 0
                    await executions.finish_agent_execution(
                        execution_id=execution_id,
                        status="timed_out" if result.execution_status == "budget_exhausted"
                        else result.execution_status,
                        outcome={"satisfied": "passed", "not_satisfied": "failed",
                                 "unverified": "inconclusive"}[result.verdict]
                        if result.execution_status == "completed" else None,
                    )
                    await events.create(
                        test_run_id=request.run_id, journey_id=journey_id,
                        execution_id=execution_id, event_type="contract.case.completed",
                        payload={**identity, "persona_index": persona_index, "attempt": attempt,
                                 "planned_steps": len(case.steps) + 1,
                                 "completed_steps": completed_steps,
                                 "result": result.model_dump(mode="json")},
                    )
                    await session.commit()
                    results.append(result)
                    if result.blocker == "human_takeover_required":
                        raise BrowserActionBlockedError(
                            "An opaque confirmation requires human browser takeover."
                        )
                    if attempt == 2 or not any(a.status == "not_satisfied"
                                               for a in result.assertion_results):
                        break
                    original = result
    await states.mark_completed(test_run_id=request.run_id)
    run = await session.get(TestRun, request.run_id, populate_existing=True)
    assert run is not None
    run.configuration_snapshot = {**run.configuration_snapshot, "discovery_stage": "evaluating"}
    await session.commit()
    return tuple(results)
