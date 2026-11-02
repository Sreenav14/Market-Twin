from uuid import uuid4

import pytest
from markettwin_evaluation_worker.contract_replay import replay_decision
from markettwin_shared.deep_testing import AssertionResult, CaseExecutionResult


def execution(passed: bool) -> CaseExecutionResult:
    execution_id = uuid4()
    assertion = AssertionResult(
        case_id="journey",
        assertion_id="check",
        oracle="title",
        expected_value="Welcome",
        observed_value="Welcome" if passed else "Wrong",
        status="satisfied" if passed else "not_satisfied",
        execution_id=execution_id,
        step_id=2,
        artifact_ids=(uuid4(),),
        origin="user_approved",
        elapsed_ms=1,
    )
    return CaseExecutionResult(
        case_id="journey",
        execution_id=execution_id,
        execution_status="completed",
        verdict=assertion.status,
        action_step_ids=(1,),
        assertion_results=(assertion,),
        elapsed_ms=1,
    )


def precondition_execution(*, passed: bool, blocked: bool = True) -> CaseExecutionResult:
    execution_id = uuid4()
    assertion = AssertionResult(
        case_id="journey",
        assertion_id="check",
        oracle="enabled",
        expected_value=True,
        observed_value=passed,
        status="satisfied" if passed else "not_satisfied",
        execution_id=execution_id,
        step_id=2,
        artifact_ids=(uuid4(),),
        origin="user_approved",
        elapsed_ms=1,
    )
    return CaseExecutionResult(
        case_id="journey",
        execution_id=execution_id,
        execution_status="completed",
        verdict=assertion.status,
        action_step_ids=(1,),
        assertion_results=(assertion,),
        elapsed_ms=1,
        blocker="assertion_precondition_failed" if blocked and not passed else None,
    )


@pytest.mark.parametrize(
    "passes,valid,same,expected",
    [
        (False, True, True, "reproduced"),
        (True, True, True, "did_not_reproduce"),
        (False, False, True, "replay_unavailable"),
        (False, True, False, "replay_unavailable"),
    ],
)
def test_replay_requires_matching_frozen_contract_and_valid_independent_evidence(
    passes,
    valid,
    same,
    expected,
):
    assert (
        replay_decision(
            assertion_id="check",
            original=execution(False),
            replay=execution(passes),
            original_evidence_valid=True,
            replay_evidence_valid=valid,
            same_frozen_contract=same,
        )
        == expected
    )


def test_same_execution_never_counts_as_confirmation():
    original = execution(False)
    assert (
        replay_decision(
            assertion_id="check",
            original=original,
            replay=original,
            original_evidence_valid=True,
            replay_evidence_valid=True,
            same_frozen_contract=True,
        )
        == "replay_unavailable"
    )


def test_precondition_failure_confirms_only_when_both_fresh_executions_fail_it():
    original = precondition_execution(passed=False)
    replay = precondition_execution(passed=False)
    assert (
        replay_decision(
            assertion_id="check",
            original=original,
            replay=replay,
            original_evidence_valid=True,
            replay_evidence_valid=True,
            same_frozen_contract=True,
        )
        == "reproduced"
    )

    passed = precondition_execution(passed=True, blocked=False)
    assert (
        replay_decision(
            assertion_id="check",
            original=original,
            replay=passed,
            original_evidence_valid=True,
            replay_evidence_valid=True,
            same_frozen_contract=True,
        )
        == "did_not_reproduce"
    )

    failed_without_precondition = execution(False)
    assert (
        replay_decision(
            assertion_id="check",
            original=original,
            replay=failed_without_precondition,
            original_evidence_valid=True,
            replay_evidence_valid=True,
            same_frozen_contract=True,
        )
        == "replay_unavailable"
    )
