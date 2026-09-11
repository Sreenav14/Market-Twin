"""Completed Test Run result endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    status,
)
from pydantic import BaseModel

from markettwin_control_api.api.auth import (
    get_database_runtime,
)
from markettwin_control_api.api.dependencies import (
    get_authenticated_user_id,
)
from markettwin_control_api.persistence.repositories import (
    FindingResultRecord,
    TestRunRepository,
    TestRunResultsRepository,
)

router = APIRouter(
    tags=["Test Run Results"],
)


class FindingEvidenceResponse(BaseModel):
    """Evidence references attached to one finding."""

    step_ids: list[int]
    artifact_ids: list[UUID]


class FindingResponse(BaseModel):
    """One evidence-backed MarketTwin finding."""

    id: UUID
    severity: str
    category: str
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


def build_finding_response(
    finding: FindingResultRecord,
) -> FindingResponse:
    return FindingResponse(
        id=finding.finding_id,
        severity=finding.severity,
        category=finding.category,
        title=finding.title,
        summary=finding.summary,
        recommendation=finding.recommendation,
        status=finding.status,
        journey_ids=list(
            finding.journey_ids
        ),
        evidence=FindingEvidenceResponse(
            step_ids=list(
                finding.step_ids
            ),
            artifact_ids=list(
                finding.artifact_ids
            ),
        ),
    )


@router.get(
    "/api/v1/test-runs/{test_run_id}/results",
    response_model=TestRunResultsResponse,
)
async def get_test_run_results(
    test_run_id: UUID,
    request: Request,
) -> TestRunResultsResponse:
    """Return the final report and findings for one run."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        test_run_repository = TestRunRepository(
            database_session
        )

        test_run = (
            await test_run_repository.get_for_user(
                test_run_id=test_run_id,
                user_id=user_id,
            )
        )

        if test_run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test run not found.",
            )

        if test_run.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Test run has not completed yet."
                ),
            )

        results_repository = (
            TestRunResultsRepository(
                database_session
            )
        )

        results = (
            await results_repository
            .get_completed_results(
                test_run_id=test_run_id
            )
        )

    if results is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Test run execution completed, but "
                "evaluation results are not available yet."
            ),
        )

    return TestRunResultsResponse(
        test_run_id=test_run_id,
        report=ReportResponse(
            id=results.report.report_id,
            version=results.report.version,
            status=results.report.status,
            executive_summary=(
                results.report.executive_summary
            ),
            payload=results.report.report_payload,
            generated_at=(
                results.report.generated_at
            ),
        ),
        findings=[
            build_finding_response(finding)
            for finding in results.findings
        ],
    )