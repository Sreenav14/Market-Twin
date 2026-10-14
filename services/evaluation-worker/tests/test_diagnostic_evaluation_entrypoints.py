"""Diagnostic scripts use the same evaluation ownership path as the worker."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

SCRIPT_DIRECTORY = Path(__file__).resolve().parents[2] / "execution-orchestrator" / "scripts"


@pytest.mark.parametrize("name", ["run_evaluation", "run_latest_test_run"])
async def test_diagnostic_scripts_share_worker_claim(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    source = SCRIPT_DIRECTORY / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"diagnostic_{name}", source)
    assert spec is not None and spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    run_id = uuid4()
    engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr(script, "database_url", lambda: "not-used")
    monkeypatch.setattr(script, "create_database_engine", lambda _: engine)
    claim = AsyncMock(return_value=None)
    monkeypatch.setattr(script, "process_run", claim)
    if name == "run_evaluation":
        await script.main(run_id)
    else:
        session = AsyncMock()
        context = AsyncMock()
        context.__aenter__.return_value = session
        factory = MagicMock(return_value=context)
        monkeypatch.setattr(script, "create_session_factory", lambda _: factory)
        monkeypatch.setattr(
            script,
            "build_run_request",
            lambda _: SimpleNamespace(
                run_id=run_id,
                study_brief="Synthetic task",
                start_url="https://example.invalid",
            ),
        )
        monkeypatch.setattr(
            script,
            "execute_markettwin_run",
            AsyncMock(
                return_value=SimpleNamespace(
                    journeys=(),
                    completed_count=0,
                    failed_count=0,
                )
            ),
        )
        await script.main()
    claim.assert_awaited_once_with(engine, run_id)
    engine.dispose.assert_awaited_once()
