"""Trace events cannot carry literals or borrow another execution's spec."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.workflow.task_spec_store import (
    restore_task_trace,
    store_task_spec,
)
from markettwin_execution_orchestrator.workflow.task_trace import TaskTraceRecorder
from markettwin_shared.feature_plan import TestCaseSpec


def case():
    return TestCaseSpec.model_validate({
        "case_id": "input_case", "feature_key": "input", "title": "Check input",
        "kind": "happy_path", "steps": [{"action": "navigate", "url": "https://example.com/"}],
        "expected": [{"assertion_id": "value", "oracle": "value", "target": {"label": "Name"},
                      "expected_value": "private-expected-value"}],
    })


@pytest.mark.asyncio
async def test_trace_redaction_and_scoped_recovery():
    spec = case()
    trace = TaskTraceRecorder(case=spec, start_url="https://example.com/").payload(case_status="failed")
    assert "private-expected-value" not in json.dumps(trace)
    rows = []
    session = SimpleNamespace(add=rows.append, flush=AsyncMock())
    run_id, journey_id, execution_id = uuid4(), uuid4(), uuid4()
    reference = await store_task_spec(
        session, run_id=run_id, journey_id=journey_id, execution_id=execution_id,
        spec=spec.model_dump(mode="json"),
    )
    trace["spec_ref"] = str(reference)
    session.get = AsyncMock(return_value=rows[0])
    restored = await restore_task_trace(session, payload=trace, run_id=run_id, execution_id=execution_id)
    assert restored["spec"] == spec.model_dump(mode="json")
    assert "expected_value" not in trace["spec"]["expected"][0]
    for foreign_run, foreign_execution in ((uuid4(), execution_id), (run_id, uuid4())):
        with pytest.raises(ValueError, match="task_spec_unavailable"):
            await restore_task_trace(
                session, payload=trace, run_id=foreign_run, execution_id=foreign_execution,
            )
    trace["spec"]["title"] = "Changed"
    with pytest.raises(ValueError, match="task_spec_mismatch"):
        await restore_task_trace(session, payload=trace, run_id=run_id, execution_id=execution_id)
