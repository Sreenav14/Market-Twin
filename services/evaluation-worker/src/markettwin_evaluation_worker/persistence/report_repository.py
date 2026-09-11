"""Persistence for MarketTwin evaluation reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from markettwin_database.models import (
    Finding,
    FindingJourney,
    Report,
    TestRun,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class ReportFindingRecord:
    """Finding data required to build a report."""

    finding_id: UUID
    severity: str
    category: str
    title: str
    summary: str
    recommendation: str | None
    journey_ids: tuple[UUID, ...]


class ReportRepository:
    """Read findings and persist generated reports."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def validate_run_ready(
        self,
        *,
        test_run_id: UUID,
    ) -> None:
        run = await self._session.get(
            TestRun,
            test_run_id,
        )

        if run is None:
            raise ValueError(
                f'TestRun "{test_run_id}" does not exist.'
            )

        if run.status != "completed":
            raise RuntimeError(
                "Only completed TestRuns can have reports. "
                f'Current status is "{run.status}".'
            )

        existing_report = await self._session.scalar(
            select(Report.id)
            .where(
                Report.test_run_id == test_run_id,
                Report.version == 1,
            )
            .limit(1)
        )

        if existing_report is not None:
            raise RuntimeError(
                "Report version 1 already exists for "
                f'TestRun "{test_run_id}".'
            )

    async def list_findings(
        self,
        *,
        test_run_id: UUID,
    ) -> tuple[ReportFindingRecord, ...]:
        findings = tuple(
            (
                await self._session.scalars(
                    select(Finding)
                    .where(
                        Finding.test_run_id
                        == test_run_id
                    )
                    .order_by(Finding.created_at)
                )
            ).all()
        )

        if not findings:
            return ()

        finding_ids = tuple(
            finding.id
            for finding in findings
        )

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

        journeys_by_finding: dict[
            UUID,
            list[UUID],
        ] = {}

        for link in journey_links:
            journeys_by_finding.setdefault(
                link.finding_id,
                [],
            ).append(link.journey_id)

        return tuple(
            ReportFindingRecord(
                finding_id=finding.id,
                severity=finding.severity,
                category=finding.category,
                title=finding.title,
                summary=finding.summary,
                recommendation=(
                    finding.recommendation
                ),
                journey_ids=tuple(
                    journeys_by_finding.get(
                        finding.id,
                        [],
                    )
                ),
            )
            for finding in findings
        )

    async def create_completed_report(
        self,
        *,
        test_run_id: UUID,
        executive_summary: str,
        report_payload: dict[str, object],
    ) -> UUID:
        report = Report(
            test_run_id=test_run_id,
            version=1,
            status="completed",
            executive_summary=executive_summary,
            report_payload=report_payload,
            generated_at=datetime.now(
                UTC
            ),
        )

        self._session.add(report)
        await self._session.flush()

        return report.id