"""Independent evidence checks shared by report creation and the read API."""

import json
from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

from markettwin_shared.deep_testing import CaseExecutionResult
from markettwin_shared.discovery_contract import TestContract
from markettwin_shared.feature_plan import TestCaseSpec


class StepEvidence(Protocol):
    @property
    def id(self) -> int: ...
    @property
    def execution_id(self) -> UUID: ...
    @property
    def status(self) -> str: ...
    @property
    def action_type(self) -> str: ...
    @property
    def step_number(self) -> int: ...
    @property
    def observation_summary(self) -> str | None: ...


class ArtifactEvidence(Protocol):
    @property
    def execution_id(self) -> UUID: ...
    @property
    def step_id(self) -> int | None: ...
    @property
    def artifact_type(self) -> str: ...
    @property
    def metadata_json(self) -> Mapping[str, object]: ...


def valid_case_evidence(
    case: TestCaseSpec,
    result: CaseExecutionResult,
    steps: Mapping[int, StepEvidence],
    artifacts: Mapping[UUID, ArtifactEvidence],
    frozen_contract: TestContract | None = None,
    expected_contract_hash: str | None = None,
) -> bool:
    """Ownership, causal order and observed-state checks precede any defect claim."""
    if frozen_contract is not None and expected_contract_hash is not None:
        if frozen_contract.content_hash() != expected_contract_hash:
            return False
    if result.case_id != case.case_id or result.execution_status != "completed":
        return False
    precondition_failed = result.blocker == "assertion_precondition_failed"
    if precondition_failed:
        if (
            result.verdict != "not_satisfied"
            or len(result.action_step_ids) < 1
            or len(result.action_step_ids) > len(case.steps)
        ):
            return False
        completed_case_actions = len(result.action_step_ids) - 1
        if completed_case_actions >= len(case.steps):
            return False
        expected = {
            item.assertion_id: item
            for item in case.expected
            if item.after_step_ordinal is not None
            and item.after_step_ordinal <= completed_case_actions
        }
        next_target = case.steps[completed_case_actions].target
    else:
        if len(result.action_step_ids) != len(case.steps) + 1:
            return False
        expected = {item.assertion_id: item for item in case.expected}
        next_target = None
    expected_actions = ("navigate", *(action.action_id or action.action for action in case.steps))
    if precondition_failed:
        expected_actions = expected_actions[: len(result.action_step_ids)]
    for step_id, action in zip(result.action_step_ids, expected_actions, strict=True):
        step = steps.get(step_id)
        if (
            step is None
            or step.execution_id != result.execution_id
            or step.status != "completed"
            or step.action_type != action
        ):
            return False
    if {item.assertion_id for item in result.assertion_results} != set(expected):
        return False
    failed_precondition_found = False
    for observed in result.assertion_results:
        oracle = expected[observed.assertion_id]
        if (
            observed.oracle,
            observed.expected_value,
            observed.origin,
            observed.requirement_refs,
        ) != (
            oracle.oracle,
            oracle.expected_value,
            oracle.origin,
            oracle.requirement_refs,
        ):
            return False
        is_next_action_check = (
            precondition_failed
            and oracle.after_step_ordinal == len(result.action_step_ids) - 1
            and observed.status == "not_satisfied"
        )
        if is_next_action_check:
            if (
                oracle.origin != "user_approved"
                or oracle.oracle not in {"visible", "enabled"}
                or oracle.target is None
                or oracle.target != next_target
            ):
                return False
            failed_precondition_found = True
        step = steps.get(observed.step_id)
        if (
            step is None
            or step.execution_id != result.execution_id
            or step.action_type != "assertion"
            or step.status != "completed"
        ):
            return False
        required_actions = (
            result.action_step_ids
            if oracle.after_step_ordinal is None
            else (result.action_step_ids[: oracle.after_step_ordinal + 1])
        )
        if any(steps[step_id].step_number >= step.step_number for step_id in required_actions):
            return False
        if (
            oracle.after_step_ordinal is not None
            and oracle.after_step_ordinal + 1 < len(result.action_step_ids)
            and step.step_number
            >= steps[result.action_step_ids[oracle.after_step_ordinal + 1]].step_number
        ):
            return False
        try:
            if json.loads(step.observation_summary or "null") != observed.model_dump(mode="json"):
                return False
        except (TypeError, ValueError):
            return False
        for artifact_id in observed.artifact_ids:
            artifact = artifacts.get(artifact_id)
            if (
                artifact is None
                or artifact.execution_id != result.execution_id
                or artifact.step_id != step.id
                or artifact.artifact_type != "screenshot"
            ):
                # The recorder also saves ARIA evidence; require at least one exact image below.
                if (
                    artifact is None
                    or artifact.execution_id != result.execution_id
                    or artifact.step_id != step.id
                    or artifact.metadata_json.get("kind") != "accessibility_snapshot"
                ):
                    return False
        if observed.status != "unverified" and not any(
            artifacts[item].artifact_type == "screenshot" for item in observed.artifact_ids
        ):
            return False
    return not precondition_failed or failed_precondition_found
