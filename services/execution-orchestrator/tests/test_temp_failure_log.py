"""Temporary failure log keeps the exception reason and redacts credentials."""

from markettwin_execution_orchestrator.temp_failure_log import (
    bind_temp_run,
    record_temp_failure,
    reset_temp_run,
)


def test_failure_file_contains_the_reason_and_redacts_secrets(monkeypatch, tmp_path) -> None:
    path = tmp_path / "temp-execution.log"
    monkeypatch.setenv("MARKETTWIN_TEMP_FAILURE_LOG", str(path))
    monkeypatch.setenv("MARKETTWIN_TEMP_FAILURE_LOG_ENABLED", "true")
    token = bind_temp_run("da2c121b-21ec-4710-8fdf-59322142dd0c")
    try:
        try:
            raise ValueError("Feature planner returned no schema-valid cases. sk-secretvalue")
        except ValueError as error:
            record_temp_failure(stage="run", error=error)
    finally:
        reset_temp_run(token)
    text = path.read_text(encoding="utf-8")
    assert "stage=run" in text
    assert "da2c121b-21ec-4710-8fdf-59322142dd0c" in text
    assert "error_type=ValueError" in text
    assert "no schema-valid cases" in text
    assert "sk-secretvalue" not in text
    assert "[redacted]" in text
    assert "test_temp_failure_log.py" in text


def test_temporary_diagnostics_are_disabled_by_default(monkeypatch, tmp_path) -> None:
    path = tmp_path / "disabled.log"
    monkeypatch.setenv("MARKETTWIN_TEMP_FAILURE_LOG", str(path))
    monkeypatch.delenv("MARKETTWIN_TEMP_FAILURE_LOG_ENABLED", raising=False)
    record_temp_failure(stage="run", error=ValueError("private application text"))
    assert not path.exists()
