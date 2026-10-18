"""Completed Test Run result endpoints."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import cast
from uuid import UUID

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    status,
)
from markettwin_database.models.evaluation import Report
from markettwin_database.models.execution import RunEvent
from markettwin_shared.finding_classification import classify_finding
from pydantic import BaseModel
from sqlalchemy import select

from markettwin_control_api.api.auth import (
    get_database_runtime,
)
from markettwin_control_api.api.dependencies import (
    get_authenticated_user_id,
)
from markettwin_control_api.api.runtime_snapshots import (
    AgentRuntimeSnapshotResponse,
    build_runtime_snapshot_response,
)
from markettwin_control_api.persistence.repositories import (
    FindingResultRecord,
    RuntimeSnapshotRepository,
    TestRunRepository,
    TestRunResultsRepository,
)

router = APIRouter(
    tags=["Test Run Results"],
)


@router.get(
    "/api/v1/test-runs/{test_run_id}/evaluation-agents",
    response_model=list[AgentRuntimeSnapshotResponse],
)
async def get_evaluation_agents(
    test_run_id: UUID,
    request: Request,
) -> list[AgentRuntimeSnapshotResponse]:
    """Keep evidence verifiers and assessment agents separate from test personas."""
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        run = await TestRunRepository(session).get_for_user(
            test_run_id=test_run_id,
            user_id=user_id,
        )
        if run is None:
            raise HTTPException(404, "Test run not found.")
        snapshots = await RuntimeSnapshotRepository(session).list_for_run(test_run_id=test_run_id)
    return [
        build_runtime_snapshot_response(item)
        for item in snapshots
        if item.agent_role in {"visual_verifier", "evaluator"}
    ]


@router.get("/api/v1/test-runs/{test_run_id}/collection")
async def get_test_run_collection(test_run_id: UUID, request: Request) -> dict[str, object]:
    """Expose the supervisor's durable collection without inferring it from run status."""
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        run = await TestRunRepository(session).get_for_user(
            test_run_id=test_run_id,
            user_id=user_id,
        )
        if run is None:
            raise HTTPException(404, "Test run not found.")
        event = await session.scalar(
            select(RunEvent)
            .where(
                RunEvent.test_run_id == test_run_id,
                RunEvent.event_type == "run.collection",
            )
            .order_by(RunEvent.id.desc())
            .limit(1)
        )
    return {
        "collection": event.payload if event is not None else None,
        "collected_at": event.occurred_at.isoformat() if event is not None else None,
    }


class FindingEvidenceResponse(BaseModel):
    """Evidence references attached to one finding."""

    step_ids: list[int]
    artifact_ids: list[UUID]


class FindingResponse(BaseModel):
    """A classified finding; evidence linkage alone does not verify agent claims."""

    id: UUID
    severity: str
    category: str
    finding_kind: str
    verification_status: str
    title: str
    summary: str
    recommendation: str | None
    status: str
    journey_ids: list[UUID]
    evidence: FindingEvidenceResponse


class ReportResponse(BaseModel):
    """Final MarketTwin evaluation report."""

    id: UUID
    version: int
    status: str
    executive_summary: str | None
    payload: dict[str, object]
    generated_at: datetime | None


class TestRunResultsResponse(BaseModel):
    """Final evaluation results for one TestRun."""

    test_run_id: UUID
    report: ReportResponse
    findings: list[FindingResponse]


class JourneyResponse(BaseModel):
    """Persisted journey execution; absence is distinct from success."""

    id: UUID
    ordinal: int
    persona_name: str
    persona_perspective: str
    mission_title: str
    mission_objective: str
    step_count: int
    artifact_count: int
    evidence_available: bool
    summary: str | None
    success_criteria: list[str]
    execution_id: UUID | None
    attempt_number: int | None
    execution_status: str | None
    runtime_name: str | None = None
    outcome: str | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    result: dict[str, object] | None


class JourneyStepResponse(BaseModel):
    id: int
    step_number: int
    action_type: str
    action_summary: str
    observation_summary: str | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None


class JourneyArtifactResponse(BaseModel):
    id: UUID
    step_id: int | None
    artifact_type: str
    content_type: str
    size_bytes: int | None
    created_at: datetime
    kind: str | None


class JourneyDetailResponse(BaseModel):
    journey: JourneyResponse
    steps: list[JourneyStepResponse]
    artifacts: list[JourneyArtifactResponse]
    findings: list[FindingResponse]
    next_after_step: int | None
    artifacts_truncated: bool


def build_run_flow(
    *,
    run_status: str,
    journeys: list[dict[str, object]],
    collected: bool,
    report_status: str | None,
    execution_mode: str = "legacy_persona",
    plan_recorded: bool | None = None,
) -> dict[str, object]:
    """Build a read-only map from saved planning, execution and evaluation records."""
    discovery = [journey for journey in journeys if (
        journey.get("runtime_name") in {"human_auth_bootstrap_v1", "browser_discovery_v1"}
        or journey.get("ordinal") == 10_000
    )]
    cases = [journey for journey in journeys if journey not in discovery]
    has_plan = bool(cases) if plan_recorded is None else plan_recorded
    nodes = [{
        "id": f"discovery:{journey['id']}", "kind": "discovery", "label": "Browser discovery",
        "status": "awaiting_human"
        if run_status == "awaiting_human" and journey["execution_status"] == "running"
        else str(journey["execution_status"] or "not_started"),
    } for journey in discovery]
    nodes.extend([
        {
            "id": "meta",
            "kind": "meta",
            "label": "Feature plan" if execution_mode == "deep_feature_v1" else "Meta Agent",
            "status": "completed"
            if has_plan
            else "running"
            if run_status == "planning"
            else "failed"
            if run_status == "failed" and not discovery
            else "not_started",
        }
    ])
    nodes.extend(
        {
            "id": f"journey:{journey['id']}",
            "kind": "journey",
            "label": f"{journey['persona_name']} · {journey['mission_title']}",
            "status": str(journey["execution_status"] or "not_started"),
        }
        for journey in cases
    )
    nodes.extend(
        [
            {
                "id": "collector",
                "kind": "collector",
                "label": "Collector",
                "status": "completed"
                if collected
                else "not_recorded"
                if run_status == "completed"
                else "not_started",
            },
            {
                "id": "evaluation",
                "kind": "evaluation",
                "label": "Evaluation",
                "status": "completed"
                if report_status == "completed"
                else "failed"
                if report_status == "failed"
                else "awaiting_report"
                if run_status == "completed"
                else "not_started",
            },
            {
                "id": "report",
                "kind": "report",
                "label": "Report",
                "status": report_status or "not_started",
            },
        ]
    )
    edges = [
        {"source": left["id"], "target": right["id"]}
        for left, right in zip(nodes, nodes[1:], strict=False)
    ]
    revision = hashlib.sha256(json.dumps(nodes, sort_keys=True).encode()).hexdigest()[:16]
    return {
        "nodes": nodes,
        "edges": edges,
        "execution_policy": "once_per_journey",
        "revision": revision,
    }


@router.get("/api/v1/test-runs/{test_run_id}/flow")
async def get_test_run_flow(test_run_id: UUID, request: Request) -> dict[str, object]:
    """Return the authorized run's real plan and recorded stage states."""
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        run = await TestRunRepository(session).get_for_user(
            test_run_id=test_run_id,
            user_id=user_id,
        )
        if run is None:
            raise HTTPException(404, "Test run not found.")
        journeys = await TestRunResultsRepository(session).list_journeys(test_run_id=test_run_id)
        collected = await session.scalar(
            select(RunEvent.id)
            .where(
                RunEvent.test_run_id == test_run_id,
                RunEvent.event_type == "run.collection",
            )
            .limit(1)
        )
        plan_recorded = await session.scalar(
            select(RunEvent.id).where(
                RunEvent.test_run_id == test_run_id,
                RunEvent.event_type == "test_plan.created",
            ).limit(1)
        )
        report_status = await session.scalar(
            select(Report.status)
            .where(
                Report.test_run_id == test_run_id,
            )
            .order_by(Report.version.desc())
            .limit(1)
        )
    return build_run_flow(
        run_status=run.status,
        journeys=journeys,
        collected=collected is not None,
        report_status=report_status,
        execution_mode=str(run.configuration_snapshot.get("execution_mode", "legacy_persona")),
        plan_recorded=(plan_recorded is not None)
        if run.configuration_snapshot.get("execution_mode") == "deep_feature_v1" else None,
    )


@router.get("/api/v1/test-runs/{test_run_id}/journeys", response_model=list[JourneyResponse])
async def get_test_run_journeys(test_run_id: UUID, request: Request) -> list[JourneyResponse]:
    """Return scoped journey results while execution or evaluation is still running."""
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        run = await TestRunRepository(session).get_for_user(
            test_run_id=test_run_id, user_id=user_id
        )
        if run is None:
            raise HTTPException(status_code=404, detail="Test run not found.")
        rows = await TestRunResultsRepository(session).list_journeys(test_run_id=test_run_id)
    return [JourneyResponse.model_validate(row) for row in rows]


def build_finding_response(
    finding: FindingResultRecord,
) -> FindingResponse:
    return FindingResponse(
        id=finding.finding_id,
        severity="info" if finding.category == "cross_persona_pattern" else finding.severity,
        category=finding.category,
        finding_kind=classify_finding(
            finding.category, has_visual_evidence=finding.has_visual_evidence,
        )[0],
        verification_status=classify_finding(
            finding.category, has_visual_evidence=finding.has_visual_evidence,
        )[1],
        title=finding.title,
        summary=finding.summary,
        recommendation=finding.recommendation,
        status=finding.status,
        journey_ids=list(finding.journey_ids),
        evidence=FindingEvidenceResponse(
            step_ids=list(finding.step_ids),
            artifact_ids=list(finding.artifact_ids),
        ),
    )


@router.get(
    "/api/v1/test-runs/{test_run_id}/journeys/{journey_id}",
    response_model=JourneyDetailResponse,
)
async def get_test_run_journey(
    test_run_id: UUID, journey_id: UUID, request: Request,
    after_step: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=200),
) -> JourneyDetailResponse:
    """Authorize the run first; another run's journey is indistinguishable from missing."""
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        run = await TestRunRepository(session).get_for_user(
            test_run_id=test_run_id, user_id=user_id,
        )
        if run is None:
            raise HTTPException(404, "Test run not found.")
        detail = await TestRunResultsRepository(session).get_journey(
            test_run_id=test_run_id, journey_id=journey_id, after_step=after_step, limit=limit,
        )
        if detail is None:
            raise HTTPException(404, "Journey not found.")
    detail["findings"] = [build_finding_response(item) for item in
                          cast(tuple[FindingResultRecord, ...], detail["findings"])]
    return JourneyDetailResponse.model_validate(detail)


@router.get(
    "/api/v1/test-runs/{test_run_id}/results",
    response_model=TestRunResultsResponse,
)
async def get_test_run_results(
    test_run_id: UUID,
    request: Request,
) -> TestRunResultsResponse:
    """Return the final report and findings for one run."""

    user_id = await get_authenticated_user_id(request=request)

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        test_run_repository = TestRunRepository(database_session)

        test_run = await test_run_repository.get_for_user(
            test_run_id=test_run_id,
            user_id=user_id,
        )

        if test_run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test run not found.",
            )

        if test_run.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("Test run has not completed yet."),
            )

        results_repository = TestRunResultsRepository(database_session)

        results = await results_repository.get_completed_results(test_run_id=test_run_id)

    if results is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Test run execution completed, but evaluation results are not available yet."),
        )

    return TestRunResultsResponse(
        test_run_id=test_run_id,
        report=ReportResponse(
            id=results.report.report_id,
            version=results.report.version,
            status=results.report.status,
            executive_summary=(results.report.executive_summary),
            payload=results.report.report_payload,
            generated_at=(results.report.generated_at),
        ),
        findings=[build_finding_response(finding) for finding in results.findings],
    )
