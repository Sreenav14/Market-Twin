"""Read completed MarketTwin evaluation results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from markettwin_database.models import (
    Finding,
    FindingEvidence,
    FindingJourney,
    Report,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class FindingResultRecord:
    """One evidence-backed MarketTwin finding."""

    finding_id: UUID
    severity: str
    category: str
    title: str
    summary: str
    recommendation: str | None
    status: str

    journey_ids: tuple[UUID, ...]
    step_ids: tuple[int, ...]
    artifact_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ReportResultRecord:
    """One persisted MarketTwin report."""

    report_id: UUID
    test_run_id: UUID
    version: int
    status: str
    executive_summary: str | None
    report_payload: dict[str, object]
    generated_at: datetime | None


@dataclass(frozen=True, slots=True)
class TestRunResultsRecord:
    """Complete readable result for one TestRun."""

    report: ReportResultRecord
    findings: tuple[FindingResultRecord, ...]


class TestRunResultsRepository:
    """Read evaluation results for the Control API."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_completed_results(
        self,
        *,
        test_run_id: UUID,
    ) -> TestRunResultsRecord | None:
        report = await self._session.scalar(
            select(Report)
            .where(
                Report.test_run_id == test_run_id,
                Report.status == "completed",
            )
            .order_by(Report.version.desc())
            .limit(1)
        )

        if report is None:
            return None

        findings = tuple(
            (
                await self._session.scalars(
                    select(Finding)
                    .where(
                        Finding.test_run_id
                        == test_run_id
                    )
                    .order_by(
                        Finding.created_at,
                        Finding.id,
                    )
                )
            ).all()
        )

        finding_ids = tuple(
            finding.id
            for finding in findings
        )

        journeys_by_finding: dict[
            UUID,
            list[UUID],
        ] = {}

        steps_by_finding: dict[
            UUID,
            list[int],
        ] = {}

        artifacts_by_finding: dict[
            UUID,
            list[UUID],
        ] = {}

        if finding_ids:
            journey_links = tuple(
                (
                    await self._session.scalars(
                        select(FindingJourney)
                        .where(
                            FindingJourney.finding_id.in_(
                                finding_ids
                            )
                        )
                    )
                ).all()
            )

            for link in journey_links:
                journeys_by_finding.setdefault(
                    link.finding_id,
                    [],
                ).append(link.journey_id)

            evidence_links = tuple(
                (
                    await self._session.scalars(
                        select(FindingEvidence)
                        .where(
                            FindingEvidence.finding_id.in_(
                                finding_ids
                            )
                        )
                    )
                ).all()
            )

            for link in evidence_links:
                if link.step_id is not None:
                    steps_by_finding.setdefault(
                        link.finding_id,
                        [],
                    ).append(link.step_id)

                if link.artifact_id is not None:
                    artifacts_by_finding.setdefault(
                        link.finding_id,
                        [],
                    ).append(link.artifact_id)

        finding_records = tuple(
            FindingResultRecord(
                finding_id=finding.id,
                severity=finding.severity,
                category=finding.category,
                title=finding.title,
                summary=finding.summary,
                recommendation=(
                    finding.recommendation
                ),
                status=finding.status,
                journey_ids=tuple(
                    journeys_by_finding.get(
                        finding.id,
                        [],
                    )
                ),
                step_ids=tuple(
                    steps_by_finding.get(
                        finding.id,
                        [],
                    )
                ),
                artifact_ids=tuple(
                    artifacts_by_finding.get(
                        finding.id,
                        [],
                    )
                ),
            )
            for finding in findings
        )

        return TestRunResultsRecord(
            report=ReportResultRecord(
                report_id=report.id,
                test_run_id=report.test_run_id,
                version=report.version,
                status=report.status,
                executive_summary=(
                    report.executive_summary
                ),
                report_payload=(
                    report.report_payload
                ),
                generated_at=report.generated_at,
            ),
            findings=finding_records,
        )