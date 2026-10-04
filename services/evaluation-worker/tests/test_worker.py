"""Completed tests are evaluated once; failures release ownership for a later retry."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from markettwin_evaluation_worker import worker
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession


@pytest.mark.parametrize("state", ["busy", "already_reported", "ready", "failed"])
async def test_evaluation_claim_retry_and_completion(
    monkeypatch: pytest.MonkeyPatch, state: str,
) -> None:
    run_id = uuid4()
    connection = AsyncMock(spec=AsyncConnection)
    connection.scalar.return_value = state != "busy"
    connection_context = AsyncMock()
    connection_context.__aenter__.return_value = connection
    engine = MagicMock(spec=AsyncEngine)
    engine.connect.return_value = connection_context
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = SimpleNamespace(status="completed")
    session.scalar.return_value = uuid4() if state == "already_reported" else None
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    def session_factory(*args: object, **kwargs: object) -> AsyncMock:
        return session_context

    monkeypatch.setattr(worker, "AsyncSession", session_factory)
    evaluate = AsyncMock(
        return_value=SimpleNamespace(report_id=uuid4()),
        side_effect=RuntimeError("provider unavailable") if state == "failed" else None,
    )
    monkeypatch.setattr(worker, "evaluate_and_generate_report", evaluate)
    if state == "failed":
        with pytest.raises(RuntimeError, match="provider unavailable"):
            await worker.process_run(cast(AsyncEngine, engine), run_id)
    else:
        result = await worker.process_run(cast(AsyncEngine, engine), run_id)
        assert (result is not None) == (state == "ready")
    if state in {"ready", "failed"}:
        evaluate.assert_awaited_once_with(test_run_id=run_id, session=session)
    else:
        evaluate.assert_not_awaited()
    if state != "busy":
        connection.rollback.assert_awaited_once()
        assert "pg_advisory_unlock" in str(connection.execute.await_args.args[0])
    else:
        connection.execute.assert_not_awaited()
