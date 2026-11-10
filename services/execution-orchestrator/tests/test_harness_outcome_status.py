"""Successful interaction coverage requires evidence beyond target readiness."""

from uuid import uuid4

import pytest
from markettwin_shared.deep_testing import AssertionResult, CaseExecutionResult

from markettwin_execution_orchestrator.workflow.harness_run import _result_status


@pytest.mark.parametrize("oracle, expected", [
    ("visible", "could_not_check"),
    ("enabled", "could_not_check"),
    ("checked", "worked"),
])
def test_readiness_alone_does_not_prove_an_interaction_worked(oracle, expected):
    execution = uuid4()
    result = CaseExecutionResult(
        case_id="inert_menu", execution_id=execution,
        execution_status="completed", verdict="satisfied",
        action_step_ids=(1,), elapsed_ms=1,
        assertion_results=(AssertionResult(
            case_id="inert_menu", assertion_id="observed", oracle=oracle,
            expected_value=True, observed_value=True, status="satisfied",
            execution_id=execution, step_id=2, artifact_ids=(uuid4(),),
            origin="inferred", elapsed_ms=1,
        ),),
    )
    assert _result_status(result) == expected
