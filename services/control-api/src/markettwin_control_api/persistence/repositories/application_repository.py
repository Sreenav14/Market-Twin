"""Persistence operations for MarketTwin applications."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from markettwin_database.models import Report
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.persistence.models import (
    Application,
    TestRun,
    Workspace,
    WorkspaceMember,
)


@dataclass(frozen=True, slots=True)
class ApplicationRecord:
    """Application visible through the Control API."""

    application_id: UUID
    workspace_id: UUID
    created_by_user_id: UUID
    name: str
    description: str | None
    status: str


@dataclass(frozen=True, slots=True)
class LatestRunSummaryRecord:
    """An application's latest completed run that produced a report.

    The verdict is the report's own stored market verdict, read verbatim;
    it is never inferred from the run's status. It is None when the
    report carries no market verdict (legacy payloads). ``finished_at``
    is when the report was generated — the moment the verdict existed —
    falling back to the run's completion time when a report predates
    that field.
    """

    run_id: UUID
    run_status: str
    verdict: str | None
    finished_at: datetime | None


def report_verdict(
    report_payload: dict[str, object],
) -> str | None:
    """Return the market verdict stored in a report payload, if any."""

    market_verdict = report_payload.get("market_verdict")

    if not isinstance(market_verdict, dict):
        return None

    verdict = market_verdict.get("verdict")

    return verdict if isinstance(verdict, str) else None


def _to_record(
    application: Application,
) -> ApplicationRecord:
    """Convert a persisted application into an API-safe record."""

    return ApplicationRecord(
        application_id=application.id,
        workspace_id=application.workspace_id,
        created_by_user_id=application.created_by_user_id,
        name=application.name,
        description=application.description,
        status=application.status,
    )


class ApplicationRepository:
    """Database access for MarketTwin applications."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def create(
        self,
        *,
        workspace_id: UUID,
        created_by_user_id: UUID,
        name: str,
        description: str | None,
    ) -> ApplicationRecord:
        """Create an active application."""

        application = Application(
            workspace_id=workspace_id,
            created_by_user_id=created_by_user_id,
            name=name,
            description=description,
            status="active",
        )

        self._session.add(application)
        await self._session.flush()

        return _to_record(application)

    async def list_for_workspace(
        self,
        *,
        workspace_id: UUID,
    ) -> list[ApplicationRecord]:
        """List active applications in a workspace."""

        statement = (
            select(Application)
            .where(
                Application.workspace_id == workspace_id,
                Application.status == "active",
                Application.deleted_at.is_(None),
            )
            .order_by(Application.created_at)
        )

        result = await self._session.execute(statement)

        return [
            _to_record(application)
            for application in result.scalars().all()
        ]

    async def get_for_user(
        self,
        *,
        application_id: UUID,
        user_id: UUID,
    ) -> ApplicationRecord | None:
        """Return an application only when the user has workspace access."""

        statement = (
            select(Application)
            .join(
                Workspace,
                Workspace.id == Application.workspace_id,
            )
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id
                == Application.workspace_id,
            )
            .where(
                Application.id == application_id,
                WorkspaceMember.user_id == user_id,
                Application.status == "active",
                Application.deleted_at.is_(None),
                Workspace.status == "active",
                Workspace.deleted_at.is_(None),
            )
        )

        result = await self._session.execute(statement)

        application = result.scalar_one_or_none()

        if application is None:
            return None

        return _to_record(application)

    async def latest_run_summaries(
        self,
        *,
        workspace_id: UUID,
        application_ids: Sequence[UUID],
    ) -> dict[UUID, LatestRunSummaryRecord]:
        """Latest completed run with a completed report, per application.

        One query for the whole list: completed runs joined to their
        completed reports, ranked per application by finish time (then
        run number, then report version), keeping only the first row.
        Runs that never completed, and completed runs whose report is
        not finished, contribute nothing — a newer draft or queued run
        never erases the last real result. Applications without such a
        run are absent from the result.
        """

        if not application_ids:
            return {}

        rank = func.row_number().over(
            partition_by=TestRun.application_id,
            order_by=(
                func.coalesce(
                    TestRun.completed_at, TestRun.created_at
                ).desc(),
                TestRun.test_number.desc(),
                Report.version.desc(),
            ),
        )

        ranked = (
            select(
                TestRun.application_id.label("application_id"),
                TestRun.id.label("run_id"),
                TestRun.status.label("run_status"),
                TestRun.completed_at.label("run_completed_at"),
                Report.report_payload.label("report_payload"),
                Report.generated_at.label("report_generated_at"),
                rank.label("rank"),
            )
            .join(
                Report,
                Report.test_run_id == TestRun.id,
            )
            .where(
                TestRun.workspace_id == workspace_id,
                TestRun.application_id.in_(application_ids),
                TestRun.status == "completed",
                Report.status == "completed",
            )
            .subquery()
        )

        statement = select(
            ranked.c.application_id,
            ranked.c.run_id,
            ranked.c.run_status,
            ranked.c.run_completed_at,
            ranked.c.report_payload,
            ranked.c.report_generated_at,
        ).where(ranked.c.rank == 1)

        result = await self._session.execute(statement)

        summaries: dict[UUID, LatestRunSummaryRecord] = {}

        for row in result.all():
            summaries[row.application_id] = LatestRunSummaryRecord(
                run_id=row.run_id,
                run_status=row.run_status,
                verdict=report_verdict(row.report_payload),
                finished_at=(
                    row.report_generated_at or row.run_completed_at
                ),
            )

        return summaries