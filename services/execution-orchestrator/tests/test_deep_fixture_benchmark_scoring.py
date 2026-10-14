"""Benchmark scores must preserve missing cases and uncertainty."""

import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest


def load_script() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts/run_deep_fixture_benchmark.py"
    spec = spec_from_file_location("deep_fixture_benchmark", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_failed_tool_and_missing_case_do_not_improve_execution_or_agreement() -> None:
    script = load_script()
    cases = [{"id": name, "expected_verdict": {"bad": "not_satisfied"}}
             for name in ("observed", "timeout", "missing")]
    metrics = script.score([
        {"case_id": "observed", "execution_status": "completed", "verdict": "not_satisfied"},
        {"case_id": "timeout", "execution_status": "failed", "verdict": "unverified"},
    ], cases, "bad")
    assert metrics["scenario_execution_rate"] == {"numerator": 1, "denominator": 3}
    assert metrics["oracle_coverage"] == {"numerator": 1, "denominator": 1}
    assert metrics["ground_truth_agreement"] == {"numerator": 1, "denominator": 3}
    assert metrics["missing_results"] == ["missing"]
    assert metrics["autonomous_metrics"]["verified_finding_precision"] is None
    assert metrics["autonomous_metrics"]["seeded_defect_recall"] is None


def test_zero_browser_execution_has_zero_denominator_without_fabricated_percentage() -> None:
    metrics = load_script().score([], [{"id": "pending",
                                      "expected_verdict": {"good": "satisfied"}}], "good")
    assert metrics["oracle_coverage"] == {"numerator": 0, "denominator": 0}
    assert metrics["ground_truth_agreement"] == {"numerator": 0, "denominator": 1}


@pytest.mark.parametrize("ids", [("known", "known"), ("foreign",)])
def test_duplicate_or_foreign_results_are_rejected(ids: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="Duplicate or foreign"):
        load_script().score([
            {"case_id": name, "execution_status": "completed", "verdict": "satisfied"}
            for name in ids
        ], [{"id": "known", "expected_verdict": {"good": "satisfied"}}], "good")


def test_claimed_defect_on_tool_failure_cannot_count_as_ground_truth_agreement() -> None:
    metrics = load_script().score([
        {"case_id": "known", "execution_status": "failed", "verdict": "not_satisfied"},
    ], [{"id": "known", "expected_verdict": {"bad": "not_satisfied"}}], "bad")
    assert metrics["ground_truth_agreement"]["numerator"] == 0


def test_cli_requires_explicit_local_authorization_before_creating_output(tmp_path: Path) -> None:
    script = Path(__file__).parents[1] / "scripts/run_deep_fixture_benchmark.py"
    output = tmp_path / "unauthorized-output"
    result = subprocess.run(
        [sys.executable, str(script), "--variant", "good", "--output-dir", str(output)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 2
    assert "--local-development" in result.stderr
    assert not output.exists()
