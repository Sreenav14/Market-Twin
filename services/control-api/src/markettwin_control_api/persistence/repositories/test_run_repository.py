"""Persistence operations for MarketTwin test runs."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.persistence.models import (
    TestRun,
    Workspace,
    WorkspaceMember,
)


@dataclass(frozen=True, slots=True)
class TestRunRecord:
    """A MarketTwin test run."""

    test_run_id: UUID
    workspace_id: UUID
    application_id: UUID
    target_id: UUID
    created_by_user_id: UUID
    status: str
    target_snapshot: dict[str, object]
    configuration_snapshot: dict[str, object]
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


def _to_record(
    test_run: TestRun,
) -> TestRunRecord:
    """Convert a persisted test run into repository data."""

    return TestRunRecord(
        test_run_id=test_run.id,
        workspace_id=test_run.workspace_id,
        application_id=test_run.application_id,
        target_id=test_run.target_id,
        created_by_user_id=test_run.created_by_user_id,
        status=test_run.status,
        target_snapshot=test_run.target_snapshot,
        configuration_snapshot=test_run.configuration_snapshot,
        created_at=test_run.created_at,
        updated_at=test_run.updated_at,
        started_at=test_run.started_at,
        completed_at=test_run.completed_at,
    )


class TestRunRepository:
    """Database access for MarketTwin test runs."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def create(
        self,
        *,
        workspace_id: UUID,
        application_id: UUID,
        target_id: UUID,
        created_by_user_id: UUID,
        target_snapshot: dict[str, object],
        configuration_snapshot: dict[str, object],
    ) -> TestRunRecord:
        """Create a draft test run."""

        test_run = TestRun(
            workspace_id=workspace_id,
            application_id=application_id,
            target_id=target_id,
            created_by_user_id=created_by_user_id,
            status="draft",
            target_snapshot=target_snapshot,
            configuration_snapshot=configuration_snapshot,
        )

        self._session.add(test_run)
        await self._session.flush()

        return _to_record(test_run)

    async def list_for_application(
        self,
        *,
        application_id: UUID,
    ) -> list[TestRunRecord]:
        """List test runs for an application."""

        statement = (
            select(TestRun)
            .where(
                TestRun.application_id == application_id
            )
            .order_by(
                TestRun.created_at.desc()
            )
        )

        result = await self._session.execute(statement)

        return [
            _to_record(test_run)
            for test_run in result.scalars().all()
        ]

    async def get_for_user(
        self,
        *,
        test_run_id: UUID,
        user_id: UUID,
    ) -> TestRunRecord | None:
        """Return a run only when the user has workspace access."""

        statement = (
            select(TestRun)
            .join(
                Workspace,
                Workspace.id == TestRun.workspace_id,
            )
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id
                == TestRun.workspace_id,
            )
            .where(
                TestRun.id == test_run_id,
                WorkspaceMember.user_id == user_id,
                Workspace.status == "active",
                Workspace.deleted_at.is_(None),
            )
        )

        result = await self._session.execute(statement)

        test_run = result.scalar_one_or_none()

        if test_run is None:
            return None

        return _to_record(test_run)