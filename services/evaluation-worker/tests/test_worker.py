"""Completed tests are evaluated once; failures release ownership for a later retry."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from markettwin_evaluation_worker import worker
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession


@pytest.mark.parametrize(
    "state", [
        "busy", "already_reported", "ready", "failed", "timed_out",
        "quarantined", "delayed", "exhausted", "invalid_input",
    ],
)
async def test_evaluation_claim_retry_and_completion(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    run_id = uuid4()
    connection = AsyncMock(spec=AsyncConnection)
    connection.scalar.return_value = state != "busy"
    connection_context = AsyncMock()
    connection_context.__aenter__.return_value = connection
    engine = MagicMock(spec=AsyncEngine)
    engine.connect.return_value = connection_context
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = SimpleNamespace(
        status="completed",
        evaluation_attempts=0,
        evaluation_next_attempt_at=(datetime.now(UTC) + timedelta(hours=1))
        if state == "delayed"
        else None,
        evaluation_quarantined_at=datetime.now(UTC) if state == "quarantined" else None,
    )
    if state == "exhausted":
        session.get.return_value.evaluation_attempts = 4
    if state == "timed_out":
        session.get.return_value.configuration_snapshot = {
            "slop_desktop_budget": {"finalization_reserve_seconds": 0.01},
        }
    session.scalar.return_value = uuid4() if state == "already_reported" else None
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session

    def session_factory(*args: object, **kwargs: object) -> AsyncMock:
        return session_context

    monkeypatch.setattr(worker, "AsyncSession", session_factory)
    evaluate = AsyncMock(
        return_value=SimpleNamespace(report_id=uuid4()),
        side_effect=RuntimeError("provider unavailable")
        if state in {"failed", "exhausted"}
        else None,
    )
    if state == "timed_out":
        async def stalled_evaluation(**kwargs):
            await asyncio.Event().wait()

        evaluate.side_effect = stalled_evaluation
    if state == "invalid_input":
        evaluate.side_effect = worker.InvalidEvaluationInput("slop_states_missing", "Missing states")
    monkeypatch.setattr(worker, "evaluate_and_generate_report", evaluate)
    if state in {"failed", "exhausted"}:
        with pytest.raises(RuntimeError, match="provider unavailable"):
            await worker.process_run(cast(AsyncEngine, engine), run_id)
    elif state == "timed_out":
        with pytest.raises(TimeoutError):
            await worker.process_run(cast(AsyncEngine, engine), run_id)
    elif state == "invalid_input":
        with pytest.raises(worker.InvalidEvaluationInput):
            await worker.process_run(cast(AsyncEngine, engine), run_id)
    else:
        result = await worker.process_run(cast(AsyncEngine, engine), run_id)
        assert (result is not None) == (state == "ready")
    if state in {"ready", "failed", "timed_out", "exhausted", "invalid_input"}:
        evaluate.assert_awaited_once_with(test_run_id=run_id, session=session)
    else:
        evaluate.assert_not_awaited()
    if state != "busy":
        query = session.scalar.await_args.args[0]
        assert "completed" in query.compile().params.values()
        connection.rollback.assert_awaited_once()
        assert "pg_advisory_unlock" in str(connection.execute.await_args.args[0])
    else:
        connection.execute.assert_not_awaited()

    if state in {"failed", "timed_out", "exhausted", "invalid_input"}:
        values = session.execute.await_args.args[0].compile().params
        assert values["evaluation_attempts"] == (5 if state == "exhausted" else 1)
        expected_code = {
            "timed_out": "evaluation_timeout", "invalid_input": "slop_states_missing",
        }.get(state, "evaluation_failed")
        assert values["evaluation_last_error"] == expected_code
        terminal = state in {"exhausted", "invalid_input"}
        if terminal:
            assert values["evaluation_next_attempt_at"] is None
        else:
            assert values["evaluation_next_attempt_at"] > datetime.now(UTC)
        assert (values["evaluation_quarantined_at"] is not None) == terminal
        session.rollback.assert_awaited_once()
        session.commit.assert_awaited_once()
        if state == "timed_out":
            evaluate.side_effect = None
            session.get.return_value.evaluation_attempts = 1
            result = await worker.process_run(cast(AsyncEngine, engine), run_id)
            assert result is evaluate.return_value
            values = session.execute.await_args.args[0].compile().params
            assert values["evaluation_attempts"] == 0
            assert values["evaluation_last_error"] is None


async def test_free_slot_refills_while_a_slow_report_and_graph_audit_are_running(monkeypatch):
    slow, fast, next_run = uuid4(), uuid4(), uuid4()
    audit_started = asyncio.Event()
    slow_started = asyncio.Event()
    refilled = asyncio.Event()
    never_finishes = asyncio.Event()

    async def graph_audit(engine):
        audit_started.set()
        await never_finishes.wait()

    async def process(engine, run_id):
        if run_id == slow:
            slow_started.set()
            await never_finishes.wait()
        elif run_id == fast:
            await audit_started.wait()
            await slow_started.wait()
        else:
            refilled.set()
        return SimpleNamespace(report_id=uuid4())

    session = AsyncMock()
    session.scalars.side_effect = [
        MagicMock(all=lambda: [slow, fast]),
        MagicMock(all=lambda: [next_run]),
        MagicMock(all=lambda: []),
    ]
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    monkeypatch.setattr(worker, "AsyncSession", lambda engine: session_context)
    monkeypatch.setattr(worker, "_run_graph_audit_worker", graph_audit)
    monkeypatch.setattr(worker, "process_run", process)
    monkeypatch.setenv("MARKETTWIN_EVALUATION_CONCURRENCY", "2")
    task = asyncio.create_task(worker._run_worker(MagicMock(spec=AsyncEngine)))
    try:
        await asyncio.wait_for(refilled.wait(), timeout=2)
        second_poll = session.scalars.await_args_list[1].args[0].compile().params
        assert [slow] in second_poll.values()
        assert 1 in second_poll.values()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
