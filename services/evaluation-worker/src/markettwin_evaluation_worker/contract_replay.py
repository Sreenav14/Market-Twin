"""Replay decisions require two independently validated executions of one contract."""

from typing import Literal

from markettwin_shared.deep_testing import CaseExecutionResult

ReplayDecision = Literal["reproduced", "did_not_reproduce", "replay_unavailable"]


def replay_decision(
    *,
    assertion_id: str,
    original: CaseExecutionResult,
    replay: CaseExecutionResult | None,
    original_evidence_valid: bool,
    replay_evidence_valid: bool,
    same_frozen_contract: bool,
) -> ReplayDecision:
    """This decision alone never creates a finding or establishes oracle grounding."""
    if (
        not original_evidence_valid
        or not replay_evidence_valid
        or not same_frozen_contract
        or replay is None
        or original.execution_id == replay.execution_id
        or original.case_id != replay.case_id
        or original.execution_status != "completed"
        or replay.execution_status != "completed"
    ):
        return "replay_unavailable"
    precondition_blocked = "assertion_precondition_failed"
    original_precondition = original.blocker == precondition_blocked
    replay_precondition = replay.blocker == precondition_blocked
    first = next((a for a in original.assertion_results if a.assertion_id == assertion_id), None)
    second = next((a for a in replay.assertion_results if a.assertion_id == assertion_id), None)
    if (
        first is None
        or second is None
        or first.status != "not_satisfied"
        or (
            first.oracle,
            type(first.expected_value),
            first.expected_value,
            first.origin,
            first.requirement_refs,
        )
        != (
            second.oracle,
            type(second.expected_value),
            second.expected_value,
            second.origin,
            second.requirement_refs,
        )
    ):
        return "replay_unavailable"
    if original_precondition != replay_precondition:
        if original_precondition and second.status == "satisfied":
            return "did_not_reproduce"
        return "replay_unavailable"
    if second.status == "not_satisfied":
        return "reproduced"
    if second.status == "satisfied":
        return "did_not_reproduce"
    return "replay_unavailable"
