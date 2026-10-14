"""Incomplete report rows must not prevent a later successful evaluation."""

from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_database.models import Report
from markettwin_evaluation_worker.persistence.report_repository import ReportRepository
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.parametrize("status", ["generating", "failed", "completed"])
async def test_reuses_incomplete_report_and_preserves_completed_report(status: str) -> None:
    report = Report(
        id=uuid4(),
        test_run_id=uuid4(),
        version=1,
        status=status,
        executive_summary="original",
        report_payload={"original": True},
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = report
    result = await ReportRepository(cast(AsyncSession, session)).create_completed_report(
        test_run_id=report.test_run_id,
        executive_summary="retried",
        report_payload={"retried": True},
    )
    assert result == report.id
    session.add.assert_not_called()
    if status == "completed":
        assert report.executive_summary == "original"
        session.flush.assert_not_awaited()
    else:
        assert report.status == "completed"
        assert report.report_payload == {"retried": True}
        assert report.generated_at is not None
        session.flush.assert_awaited_once()
