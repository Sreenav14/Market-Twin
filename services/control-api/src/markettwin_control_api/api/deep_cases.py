"""Authorized bounded feature cases; private plans stay internal."""

from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from markettwin_database.models import (
    AgentExecution,
    ExecutionStep,
    PersonaJourney,
    Report,
    RunEvent,
    TestRun,
)
from markettwin_shared.deep_testing import CaseExecutionResult
from markettwin_shared.feature_plan import DeepFeaturePlan
from markettwin_shared.run_failure import public_failure_details
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import get_authenticated_user_id
from markettwin_control_api.persistence.repositories import TestRunRepository

router = APIRouter(tags=["Feature Cases"])


async def case_view(session: AsyncSession, run_id: UUID) -> dict[str, object]:
    plan_event = await session.scalar(
        select(RunEvent)
        .where(
            RunEvent.test_run_id == run_id,
            RunEvent.event_type == "test_plan.created",
        )
        .order_by(RunEvent.id)
        .limit(1)
    )
    if plan_event is None:
        result: dict[str, object] = {
            "schema_version": 1, "available": False, "coverage": None, "cases": [],
        }
        run = await session.get(TestRun, run_id)
        if run is not None and run.status == "failed":
            event = await session.scalar(
                select(RunEvent).where(
                    RunEvent.test_run_id == run_id, RunEvent.event_type == "run.failed",
                ).order_by(RunEvent.id.desc()).limit(1)
            )
            result["failure"] = public_failure_details(None if event is None else event.payload)
        return result
    plan = DeepFeaturePlan.model_validate(plan_event.payload)
    report = await session.scalar(
        select(Report)
        .where(
            Report.test_run_id == run_id,
            Report.status == "completed",
        )
        .order_by(Report.version.desc())
        .limit(1)
    )
    evaluated = (
        cast(list[object], report.report_payload.get("cases", [])) if report is not None else []
    )
    evaluated_rows = [cast(dict[str, object], item) for item in evaluated if isinstance(item, dict)]
    completed = {
        item["case_id"]: item for item in evaluated_rows if isinstance(item.get("case_id"), str)
    }
    live_rows = (
        await session.execute(
            select(RunEvent, AgentExecution, PersonaJourney.ordinal)
            .join(AgentExecution, AgentExecution.id == RunEvent.execution_id)
            .join(PersonaJourney, PersonaJourney.id == AgentExecution.journey_id)
            .where(
                RunEvent.test_run_id == run_id,
                PersonaJourney.test_run_id == run_id,
                RunEvent.journey_id == PersonaJourney.id,
                RunEvent.event_type == "test_case.started",
            )
            .order_by(RunEvent.id)
            .limit(12)
        )
    ).all()
    live = {
        event.payload.get("case_id"): (event, execution, ordinal)
        for event, execution, ordinal in live_rows
    }
    recorded_rows = (
        await session.execute(
            select(RunEvent.payload, RunEvent.journey_id)
            .where(
                RunEvent.test_run_id == run_id,
                RunEvent.event_type == "test_case.completed",
            )
            .order_by(RunEvent.id)
            .limit(20)
        )
    ).all()
    recorded: dict[str, tuple[CaseExecutionResult, object]] = {}
    for row in recorded_rows:
        try:
            parsed = CaseExecutionResult.model_validate(row[0])
        except ValidationError:
            continue
        recorded[parsed.case_id] = (parsed, row[1])
    step_ids = [
        step_id
        for observed, _journey in recorded.values()
        for step_id in (
            *observed.action_step_ids,
            *(item.step_id for item in observed.assertion_results),
        )
    ]
    statuses: dict[int, str] = {}
    if step_ids:
        status_rows = (
            await session.execute(
                select(ExecutionStep.id, ExecutionStep.status)
                .join(AgentExecution, AgentExecution.id == ExecutionStep.execution_id)
                .join(PersonaJourney, PersonaJourney.id == AgentExecution.journey_id)
                .where(
                    PersonaJourney.test_run_id == run_id,
                    ExecutionStep.id.in_(step_ids),
                )
            )
        ).all()
        statuses = {int(row[0]): str(row[1]) for row in status_rows}
    rows: list[dict[str, object]] = []
    for ordinal, case in enumerate(plan.cases, start=1):
        final = completed.get(case.case_id, {})
        active = live.get(case.case_id)
        active = active if active is not None and active[2] == ordinal else None
        observed_row = recorded.get(case.case_id)
        observed = observed_row[0] if observed_row is not None else None
        observed_journey = observed_row[1] if observed_row is not None else None
        actions = ("navigate", *(item.action for item in case.steps))
        steps = (
            [
                *(
                    {
                        "step_id": step_id,
                        "action": actions[index] if index < len(actions) else "recorded",
                        "result": statuses.get(step_id, "unavailable"),
                    }
                    for index, step_id in enumerate(observed.action_step_ids)
                ),
                *(
                    {
                        "step_id": item.step_id,
                        "action": "assertion",
                        "result": item.status,
                    }
                    for item in observed.assertion_results
                ),
            ]
            if observed is not None
            else []
        )
        rows.append(
            {
                "case_id": case.case_id,
                "title": case.title,
                "kind": case.kind,
                "verdict": final.get(
                    "verdict",
                    "not_run" if observed is not None and observed.execution_status == "skipped"
                    else "awaiting_verification" if active or observed else "not_run",
                ),
                "reason": final.get("reason", observed.blocker if observed else None),
                "recorded_verdict": None if final else (observed.verdict if observed else None),
                "steps": steps,
                "execution_status": final.get(
                    "execution_status",
                    observed.execution_status
                    if observed is not None
                    else active[1].status
                    if active
                    else "not_started",
                ),
                "journey_id": final.get(
                    "journey_id",
                    str(active[0].journey_id)
                    if active
                    else str(observed_journey)
                    if observed_journey
                    else None,
                ),
                "execution_id": final.get(
                    "execution_id",
                    str(active[1].id)
                    if active
                    else str(observed.execution_id)
                    if observed is not None
                    else None,
                ),
                "assertions": final.get(
                    "assertions",
                    [
                        item.model_dump(mode="json")
                        for item in observed.assertion_results
                    ]
                    if observed is not None and not final
                    else [],
                ),
                "expected": [
                    {
                        "assertion_id": item.assertion_id,
                        "oracle": item.oracle,
                        "expected_value": item.expected_value,
                        "origin": item.origin,
                        "requirement_refs": list(item.requirement_refs),
                    }
                    for item in case.expected
                ],
            }
        )
    rows.extend(
        {
            "case_id": item.case.case_id,
            "title": item.case.title,
            "kind": item.case.kind,
            "verdict": "not_run",
            "reason": item.reason,
            "assertions": [],
            "expected": [],
            "journey_id": None,
            "execution_id": None,
            "execution_status": "not_started",
            "recorded_verdict": None,
            "steps": [],
        }
        for item in plan.skipped
    )
    return {
        "schema_version": 1,
        "available": True,
        "evaluation_pending": report is None,
        "cases": rows,
        "coverage": report.report_payload.get("coverage") if report else None,
        "unknown_requirements": list(plan.scope.unknown_requirements),
        "coverage_gaps": list(plan.coverage_gaps),
    }


async def authorized_cases(test_run_id: UUID, request: Request) -> dict[str, object]:
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        if (
            await TestRunRepository(session).get_for_user(
                test_run_id=test_run_id,
                user_id=user_id,
            )
            is None
        ):
            raise HTTPException(404, "Test run not found.")
        return await case_view(session, test_run_id)


def page_cases(result: dict[str, object], cursor: int, limit: int) -> dict[str, object]:
    if cursor < 0 or not 1 <= limit <= 20:
        raise HTTPException(422, "Invalid case page.")
    cases = cast(list[dict[str, object]], result["cases"])
    end = cursor + limit
    return {**result, "cases": cases[cursor:end], "next_cursor": end if end < len(cases) else None}


@router.get("/api/v1/test-runs/{test_run_id}/test-cases")
async def get_cases(
    test_run_id: UUID,
    request: Request,
    cursor: int = 0,
    limit: int = 20,
) -> dict[str, object]:
    return page_cases(await authorized_cases(test_run_id, request), cursor, limit)


@router.get("/api/v1/test-runs/{test_run_id}/test-cases/{case_id}")
async def get_case(test_run_id: UUID, case_id: str, request: Request) -> dict[str, object]:
    result = await authorized_cases(test_run_id, request)
    for case in cast(list[dict[str, object]], result["cases"]):
        if case["case_id"] == case_id:
            return case
    raise HTTPException(404, "Test case not found.")


@router.get("/api/v1/test-runs/{test_run_id}/test-cases/{case_id}/steps")
async def get_case_steps(
    test_run_id: UUID,
    case_id: str,
    request: Request,
    cursor: int = 0,
    limit: int = 20,
) -> dict[str, object]:
    case = await get_case(test_run_id, case_id, request)
    steps = cast(list[dict[str, object]], case.get("steps", []))
    if cursor < 0 or not 1 <= limit <= 20:
        raise HTTPException(422, "Invalid case page.")
    end = cursor + limit
    return {"steps": steps[cursor:end], "next_cursor": end if end < len(steps) else None}
