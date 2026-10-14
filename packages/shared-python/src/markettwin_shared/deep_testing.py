"""Versioned deep-case event contracts shared by producers and read-only consumers."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

AssertionStatus = Literal["satisfied", "not_satisfied", "unverified"]
AssertionReason = Literal[
    "page_not_loaded", "unsupported_safe_value_read", "ambiguous_target", "page_closed",
    "inspection_failed", "missing_evidence", "evidence_persistence_failed",
]
CaseExecutionStatus = Literal[
    "completed", "policy_blocked", "failed", "timed_out", "budget_exhausted", "cancelled",
]
CaseBlocker = Literal[
    "policy_blocked", "action_failed", "runtime_failed", "time_limit", "action_limit",
    "evidence_persistence_failed", "cancelled",
]


class AssertionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    case_id: str = Field(min_length=1, max_length=100)
    assertion_id: str = Field(min_length=1, max_length=100)
    oracle: Literal["visible_text", "visible", "enabled", "checked", "value", "url", "title", "count"]
    expected_value: StrictStr | StrictBool | StrictInt
    observed_value: StrictStr | StrictBool | StrictInt | None
    status: AssertionStatus
    execution_id: UUID
    step_id: StrictInt = Field(gt=0)
    artifact_ids: tuple[UUID, ...] = Field(default=(), max_length=64)
    origin: Literal["approved_requirement", "fixture_truth", "inferred"]
    requirement_refs: tuple[str, ...] = Field(default=(), max_length=8)
    elapsed_ms: StrictInt = Field(ge=0)
    reason: AssertionReason | None = None

    @model_validator(mode="after")
    def require_evidence(self) -> "AssertionResult":
        expected_type = (bool if self.oracle in {"visible", "enabled", "checked"}
                         else int if self.oracle == "count" else str)
        if type(self.expected_value) is not expected_type:
            raise ValueError("Oracle expectation has an invalid type.")
        if isinstance(self.expected_value, str) and len(self.expected_value) > 500:
            raise ValueError("Oracle expectation is too long.")
        if isinstance(self.observed_value, str) and len(self.observed_value) > 1000:
            raise ValueError("Oracle observation is too long.")
        if self.status != "unverified" and type(self.observed_value) is not expected_type:
            raise ValueError("A deterministic verdict requires a typed observation.")
        if self.status != "unverified" and not self.artifact_ids:
            raise ValueError("A deterministic verdict requires exact persisted evidence.")
        matches = (type(self.observed_value) is type(self.expected_value)
                   and self.observed_value == self.expected_value)
        if self.status == "satisfied" and not matches:
            raise ValueError("A satisfied assertion requires matching observations.")
        if self.status == "not_satisfied" and matches:
            raise ValueError("Contradictory assertion status and observation.")
        if len(set(self.artifact_ids)) != len(self.artifact_ids):
            raise ValueError("Duplicate assertion artifact IDs.")
        return self


class CaseExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    case_id: str = Field(min_length=1, max_length=100)
    execution_id: UUID
    execution_status: CaseExecutionStatus
    verdict: AssertionStatus
    action_step_ids: tuple[StrictInt, ...] = Field(default=(), max_length=96)
    assertion_results: tuple[AssertionResult, ...] = Field(default=(), max_length=8)
    elapsed_ms: StrictInt = Field(ge=0)
    blocker: CaseBlocker | None = None

    @model_validator(mode="after")
    def validate_provenance_and_verdict(self) -> "CaseExecutionResult":
        if any(step <= 0 for step in self.action_step_ids):
            raise ValueError("Action step IDs must be positive.")
        if len(set(self.action_step_ids)) != len(self.action_step_ids):
            raise ValueError("Duplicate action step IDs.")
        ids: set[str] = set()
        assertion_steps: set[int] = set()
        for assertion in self.assertion_results:
            if assertion.execution_id != self.execution_id or assertion.case_id != self.case_id:
                raise ValueError("Assertion belongs to a foreign case or execution.")
            if assertion.assertion_id in ids:
                raise ValueError("Duplicate assertion IDs.")
            ids.add(assertion.assertion_id)
            if assertion.step_id in assertion_steps or assertion.step_id in self.action_step_ids:
                raise ValueError("Assertion step must identify its own exact observation.")
            assertion_steps.add(assertion.step_id)
        if self.execution_status == "completed" and not self.action_step_ids:
            raise ValueError("A completed case requires real browser actions.")
        expected: AssertionStatus = "unverified"
        if (self.execution_status == "completed" and self.assertion_results
                and all(a.status != "unverified" for a in self.assertion_results)):
            expected = ("not_satisfied" if any(a.status == "not_satisfied"
                                              for a in self.assertion_results) else "satisfied")
        if self.verdict != expected:
            raise ValueError("Case verdict disagrees with authoritative assertion results.")
        return self
