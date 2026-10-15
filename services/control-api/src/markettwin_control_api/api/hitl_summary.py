"""Secret-free authenticated coverage and human contribution read model."""

from collections import Counter
from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from markettwin_database.models import (
    ActionApprovalRequest,
    AgentExecution,
    HumanActionRequest,
    PersonaJourney,
    RunEvent,
)
from markettwin_shared.deep_testing import CaseExecutionResult
from markettwin_shared.feature_plan import DeepFeaturePlan
from sqlalchemy import select

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import get_authenticated_user_id
from markettwin_control_api.persistence.repositories import TestRunRepository

router = APIRouter(tags=["Human Actions"])


def summarize_authenticated_coverage(
    events: list[tuple[str, dict[str, object]]],
) -> dict[str, object]:
    """Reconcile the frozen feature inventory against actual case evidence.

    Authentication alone never counts as an executed or passed feature check.
    Only approved scope identifiers and counts leave this boundary.
    """
    plans = [payload for kind, payload in events if kind == "test_plan.created"]
    plan = DeepFeaturePlan.model_validate(plans[0]) if plans else None
    planned_ids: set[str] = {case.case_id for case in plan.cases} if plan else set()
    results = {
        parsed.case_id: parsed
        for kind, payload in events if kind == "test_case.completed"
        for parsed in [CaseExecutionResult.model_validate(payload)]
        if parsed.case_id in planned_ids
    }
    roles: dict[str, set[str]] = {}
    reused: set[str] = set()
    for kind, payload in events:
        if kind != "test_case.authenticated":
            continue
        role, case_id = payload.get("role"), payload.get("case_id")
        if not isinstance(role, str) or not isinstance(case_id, str) or case_id not in planned_ids:
            continue
        roles.setdefault(role, set()).add(case_id)
        if payload.get("auth_source") == "reused_session":
            reused.add(case_id)
    matrix: list[dict[str, object]] = []
    for role, ids in sorted(roles.items()):
        completed = [results[case_id] for case_id in ids if case_id in results]
        matrix.append({
            "role": role,
            "planned": len(planned_ids),
            "authenticated": len(ids),
            "executed": len(completed),
            "passed": sum(item.verdict == "satisfied" for item in completed),
            "failed_assertions": sum(
                assertion.status == "not_satisfied"
                for item in completed for assertion in item.assertion_results
            ),
            "blocked": sum(item.execution_status == "policy_blocked" for item in completed),
            "inconclusive": sum(
                item.verdict == "unverified" and item.execution_status != "policy_blocked"
                for item in completed
            ),
            "not_run": len(planned_ids - set(results)),
        })
    return {
        "schema_version": 1,
        "executor_mode": "deterministic_case_steps" if plan else "agent_journey",
        "full_application_coverage": False,
        "inventory_source": "frozen_feature_scope",
        "inventory": [{
            "feature_key": plan.scope.feature_key,
            "requirements": len(plan.scope.requirements),
            "unknown_requirements": len(plan.scope.unknown_requirements),
            "roles_verified": sorted(roles),
            "asserted_cases": sum(bool(item.assertion_results) for item in results.values()),
            "not_explored": len(plan.skipped) + len(planned_ids - set(results)),
        }] if plan else [],
        "role_coverage": matrix,
        "reused_auth_cases": len(reused),
        "human_login_steps_count_as_agent_steps": False,
        "server_data_isolation": "Requires a dedicated account, dataset and reset contract",
    }


@router.get("/api/v1/test-runs/{test_run_id}/hitl-summary")
async def get_hitl_summary(test_run_id: UUID, request: Request) -> dict[str, object]:
    actor_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        if await TestRunRepository(session).get_for_user(
            test_run_id=test_run_id, user_id=actor_id,
        ) is None:
            raise HTTPException(404, "Test run not found.")
        rows = (await session.execute(
            select(RunEvent.event_type, RunEvent.payload).where(
                RunEvent.test_run_id == test_run_id,
                RunEvent.event_type.in_((
                    "test_plan.created", "test_case.authenticated", "test_case.completed",
                )),
            ).order_by(RunEvent.id).limit(200)
        )).all()
        summary = summarize_authenticated_coverage([
            (kind, cast(dict[str, object], payload)) for kind, payload in rows
        ])
        human_states = list(await session.scalars(
            select(HumanActionRequest.status)
            .join(AgentExecution, AgentExecution.id == HumanActionRequest.execution_id)
            .join(PersonaJourney, PersonaJourney.id == AgentExecution.journey_id)
            .where(PersonaJourney.test_run_id == test_run_id)
        ))
        approval_states = list(await session.scalars(
            select(ActionApprovalRequest.status)
            .where(ActionApprovalRequest.test_run_id == test_run_id)
        ))
        return {**summary, "human_requests": dict(Counter(human_states)),
                "action_approvals": dict(Counter(approval_states))}
