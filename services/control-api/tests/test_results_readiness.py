"""Final results remain pending until a scoped completed report is available."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from markettwin_control_api.api import test_run_results


class SessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_):
        return False


def configure(monkeypatch, *, run, results):
    get_run = AsyncMock(return_value=run)
    get_results = AsyncMock(return_value=results)
    monkeypatch.setattr(
        test_run_results, "get_authenticated_user_id", AsyncMock(return_value=uuid4()),
    )
    monkeypatch.setattr(
        test_run_results, "get_database_runtime",
        lambda _: SimpleNamespace(session_factory=SessionContext),
    )
    monkeypatch.setattr(
        test_run_results, "TestRunRepository", lambda _: SimpleNamespace(get_for_user=get_run),
    )
    monkeypatch.setattr(
        test_run_results, "TestRunResultsRepository",
        lambda _: SimpleNamespace(get_completed_results=get_results),
    )
    return get_results


@pytest.mark.parametrize("run,code,detail", [
    (None, 404, "Test run not found."),
    (SimpleNamespace(status="running"), 409, "Test run has not completed yet."),
    (SimpleNamespace(status="completed"), 409,
     "Test run execution completed, but evaluation results are not available yet."),
])
async def test_results_pending_and_access_contract(monkeypatch, run, code, detail):
    get_results = configure(monkeypatch, run=run, results=None)
    with pytest.raises(HTTPException) as error:
        await test_run_results.get_test_run_results(uuid4(), object())
    assert error.value.status_code == code
    assert error.value.detail == detail
    assert get_results.await_count == (1 if run and run.status == "completed" else 0)


async def test_completed_report_is_returned_after_pending_evaluation(monkeypatch):
    run_id, report_id = uuid4(), uuid4()
    get_results = configure(monkeypatch, run=SimpleNamespace(status="completed"), results=None)
    get_results.side_effect = [None, SimpleNamespace(
        report=SimpleNamespace(
            report_id=report_id, version=1, status="completed",
            executive_summary="Synthetic report is ready.",
            report_payload={"generator": "deterministic_evaluation_v1"},
            generated_at=datetime.now(UTC),
        ), findings=(),
    )]
    with pytest.raises(HTTPException) as error:
        await test_run_results.get_test_run_results(run_id, object())
    assert error.value.status_code == 409
    response = await test_run_results.get_test_run_results(run_id, object())
    assert response.test_run_id == run_id
    assert response.report.id == report_id
    assert response.report.status == "completed"
    assert response.findings == []
