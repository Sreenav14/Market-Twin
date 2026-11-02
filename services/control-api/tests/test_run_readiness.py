"""Readiness rejects unavailable infrastructure without sending a provider request."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from markettwin_control_api.api import run_readiness as api
from markettwin_control_api.config import Settings
from markettwin_control_api.services import run_readiness as readiness
from markettwin_database.models import WorkerHeartbeat
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError


@pytest.mark.parametrize("age,connected,expected", [
    (1, True, True), (31, True, False), (1, False, False), (-5, True, False),
])
async def test_heartbeat_freshness_and_connection_are_both_required(age, connected, expected):
    session = Mock(begin_nested=Mock(return_value=AsyncMock()))
    row = WorkerHeartbeat(service="execution",
                          last_seen_at=datetime.now(UTC) - timedelta(seconds=age),
                          detail={"connected": connected, "secret": "must-not-appear"})
    session.scalars = AsyncMock(return_value=Mock(all=Mock(return_value=[row])))
    statuses = await readiness.worker_statuses(session)
    assert statuses[0].ready is expected
    assert statuses[1].ready is False
    assert "must-not-appear" not in str(statuses)


async def test_missing_heartbeat_migration_fails_readiness_without_aborting_authorization():
    session = Mock(begin_nested=Mock(return_value=AsyncMock()))
    session.scalars = AsyncMock(side_effect=SQLAlchemyError("private database detail"))
    statuses = await readiness.worker_statuses(session)
    assert all(not item.ready for item in statuses)
    session.begin_nested.assert_called_once()


@pytest.mark.parametrize("failed_check", ["dispatch", "kafka", "execution", "evaluation", "model"])
async def test_preflight_rejects_each_unavailable_dependency(monkeypatch, failed_check):
    monkeypatch.setattr(readiness, "worker_statuses", AsyncMock(return_value=[
        readiness.WorkerStatus(service=service, ready=service != failed_check)
        for service in ("execution", "evaluation")
    ]))
    monkeypatch.setattr(readiness, "kafka_reachable", AsyncMock(
        return_value=failed_check != "kafka",
    ))
    monkeypatch.setattr(readiness, "provider_configured", lambda _: failed_check != "model")
    settings = Settings.model_construct(outbox_relay_enabled=failed_check != "dispatch")
    with pytest.raises(HTTPException) as error:
        await readiness.require_run_ready(Mock(), settings)
    assert error.value.status_code == 503
    detail = error.value.detail
    assert detail["code"] == "run_preflight_failed"
    assert next(c for c in detail["checks"] if c["name"] == failed_check)["ready"] is False


@pytest.mark.parametrize("runner_ready,expected", [
    (False, "Waiting for the test runner"), (True, "Runner is busy with another test"),
])
async def test_queued_stall_reason_tracks_worker_start(monkeypatch, runner_ready, expected):
    session = Mock(scalar=AsyncMock(return_value=None))
    monkeypatch.setattr(readiness, "worker_statuses", AsyncMock(return_value=[
        readiness.WorkerStatus(service="execution", ready=runner_ready),
        readiness.WorkerStatus(service="evaluation", ready=True),
    ]))
    reason = await readiness.stalled_run_reason(
        session, run_id=uuid4(), status="queued",
        created_at=datetime.now(UTC) - timedelta(seconds=61),
    )
    assert reason == expected


async def test_recent_progress_has_no_stall_reason(monkeypatch):
    session = Mock(scalar=AsyncMock(return_value=datetime.now(UTC)))
    workers = AsyncMock()
    monkeypatch.setattr(readiness, "worker_statuses", workers)
    assert await readiness.stalled_run_reason(
        session, run_id=uuid4(), status="running",
        created_at=datetime.now(UTC) - timedelta(minutes=3),
    ) is None
    workers.assert_not_awaited()


async def test_foreign_workspace_preflight_does_not_probe_infrastructure(monkeypatch):
    user_id, run_id = uuid4(), uuid4()
    context = AsyncMock()
    session = Mock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(api, "get_authenticated_user_id", AsyncMock(return_value=user_id))
    monkeypatch.setattr(api, "get_database_runtime", lambda _: SimpleNamespace(
        session_factory=Mock(return_value=context),
    ))
    monkeypatch.setattr(api, "TestRunRepository", lambda _: SimpleNamespace(
        get_for_user=AsyncMock(return_value=SimpleNamespace(workspace_id=uuid4())),
    ))
    probe = AsyncMock()
    monkeypatch.setattr(api, "run_preflight", probe)
    with pytest.raises(HTTPException) as error:
        await api.get_run_preflight(run_id, object(), workspace_id=uuid4())
    assert error.value.status_code == 404
    probe.assert_not_awaited()


def test_provider_presence_reads_settings_without_provider_request():
    settings = Settings.model_construct(model_api_key=SecretStr("synthetic-provider-key"))
    assert readiness.provider_configured(settings)
    assert "synthetic-provider-key" not in repr(settings)
    assert not readiness.provider_configured(Settings.model_construct())
    assert readiness.provider_configured(Settings.model_construct(
        model_provider="ollama", ollama_model_name="local-model",
    ))


async def test_interrupted_reason_uses_fixed_user_message():
    session = Mock(scalar=AsyncMock(return_value=SimpleNamespace(
        payload={"code": "interrupted", "message": "private exception payload"},
    )))
    reason = await readiness.stalled_run_reason(
        session, run_id=uuid4(), status="failed", created_at=datetime.now(UTC),
    )
    assert reason == (
        "This run was interrupted (the runner restarted) and was not resumed. Start a new run."
    )


async def test_completed_report_removes_waiting_reason():
    session = Mock(scalar=AsyncMock(return_value=uuid4()))
    assert await readiness.stalled_run_reason(
        session, run_id=uuid4(), status="completed",
        created_at=datetime.now(UTC) - timedelta(hours=1),
    ) is None
    session.scalar.assert_awaited_once()
