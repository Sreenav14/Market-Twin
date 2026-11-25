"""Incomplete report rows must not prevent a later successful evaluation."""

from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_database.models import Report
from markettwin_database.models import TestRun as RunModel
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


async def test_readiness_checks_only_completed_report() -> None:
    session = AsyncMock(spec=AsyncSession)
    run_id = uuid4()
    session.get.return_value = RunModel(id=run_id, status="completed")
    session.scalar.return_value = None
    await ReportRepository(cast(AsyncSession, session)).validate_run_ready(test_run_id=run_id)
    statement = session.scalar.await_args.args[0]
    assert "completed" in statement.compile().params.values()


# -- Contract-report 409 guard (doc 24 section 5.1, W4-P5-08) --------


def _guard_session(*, report_id, execution_mode="discovery_contract_v1"):
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    run_id = uuid4()
    snapshot = {} if execution_mode is None else {
        "execution_mode": execution_mode,
    }
    run = SimpleNamespace(
        id=run_id, test_number=115, status="completed",
        configuration_snapshot=snapshot,
        target_url="https://app.example.test/",
        application_id=None, application_version_id=None,
        completed_at=datetime.now(UTC),
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=run)
    session.scalar = AsyncMock(return_value=report_id)
    session.add = MagicMock()
    return session, run_id


@pytest.mark.asyncio
async def test_existing_contract_report_is_preserved_not_rebuilt() -> None:
    """T-P5-E1: a discovery_contract_v1 run that already has a report
    is served that report — the rebuild never runs, nothing is
    written, and a second call returns the same answer."""
    from uuid import uuid4

    from markettwin_evaluation_worker.workflow import _evaluate_and_generate_report

    report_id = uuid4()
    session, run_id = _guard_session(report_id=report_id)
    result = await _evaluate_and_generate_report(test_run_id=run_id, session=session)
    assert result.report_id == report_id
    assert result.skip_reason == "contract_report_preserved"
    assert result.finding_ids == ()
    session.add.assert_not_called()
    again = await _evaluate_and_generate_report(test_run_id=run_id, session=session)
    assert again.report_id == report_id
    assert again.skip_reason == "contract_report_preserved"


@pytest.mark.asyncio
async def test_missing_contract_report_refuses_loudly() -> None:
    """T-P5-E2: no report + a contract-mode run is a loud refusal —
    an absent report is never fabricated to fill the gap."""
    from markettwin_evaluation_worker.workflow import (
        ContractReportNotRebuildableError,
        _evaluate_and_generate_report,
    )

    session, run_id = _guard_session(report_id=None)
    with pytest.raises(ContractReportNotRebuildableError):
        await _evaluate_and_generate_report(test_run_id=run_id, session=session)
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_guard_fires_only_for_contract_mode() -> None:
    """T-P5-E3: runs of every other shape pass the guard by — the
    generic path handles them exactly as before (here it runs into
    the mock session's limits, but never into the guard)."""
    from markettwin_evaluation_worker.workflow import (
        ContractReportNotRebuildableError,
        _evaluate_and_generate_report,
    )

    session, run_id = _guard_session(report_id=None, execution_mode=None)
    try:
        result = await _evaluate_and_generate_report(test_run_id=run_id, session=session)
    except ContractReportNotRebuildableError:
        raise AssertionError("guard fired for a non-contract run")
    except Exception:
        pass  # the generic path proceeded and met the mock's limits
    else:
        assert result.skip_reason is None
