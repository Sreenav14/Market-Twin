"""No-progress benchmark diagnostics contain only bounded stack metadata."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "run_contract_fixture_benchmark.py"
SPEC = importlib.util.spec_from_file_location("contract_fixture_benchmark", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


def test_event_silence_monitor_is_strictly_five_minutes_and_bounded():
    monitor = benchmark.EventSilenceMonitor(started_at=10.0)
    monitor.observe(42, 10.0)

    assert not monitor.due(310.0)
    assert monitor.due(310.1)
    assert not monitor.due(610.1)
    assert monitor.due(610.2)
    monitor.observe(43, 611.0)
    assert monitor.capture_count == 0
    assert not monitor.due(911.0)
    assert monitor.due(911.1)
    assert monitor.due(1211.2)
    assert monitor.due(1511.3)
    assert monitor.capture_count == 3
    assert not monitor.due(2000.0)


@pytest.mark.asyncio
async def test_task_stack_snapshot_contains_no_locals_or_source_text():
    gate = asyncio.Event()

    async def stalled_leaf():
        secret_local = "synthetic-sensitive-value"
        await gate.wait()
        return secret_local

    async def stalled_worker():
        return await stalled_leaf()

    task = asyncio.create_task(stalled_worker(), name="execution_worker")
    await asyncio.sleep(0)
    try:
        snapshots = benchmark.task_stack_metadata([task])
    finally:
        gate.set()
        await task

    assert snapshots[0]["task_name"] == "execution_worker"
    frames = snapshots[0]["frames"]
    assert any(frame["function"] == "stalled_worker" for frame in frames)
    assert any(frame["function"] == "stalled_leaf" for frame in frames)
    assert all(set(frame) == {"function", "file", "line"} for frame in frames)
    assert "synthetic-sensitive-value" not in json.dumps(snapshots)
