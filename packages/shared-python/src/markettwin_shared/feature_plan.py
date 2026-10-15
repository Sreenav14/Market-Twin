"""Versioned, bounded feature cases; caller-owned scope grants no new authority."""

from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")]
CaseKind = Literal[
    "happy_path",
    "negative",
    "boundary",
    "state_transition",
    "recovery",
    "keyboard",
    "responsive",
    "exploratory",
    "business_rule",
]
Oracle = Literal["visible_text", "visible", "enabled", "checked", "value", "url", "title", "count"]


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticTarget(FrozenContract):
    role: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    label: str | None = Field(default=None, min_length=1, max_length=160)
    text: str | None = Field(default=None, min_length=1, max_length=160)
    scope_role: Literal["form", "region", "dialog", "listitem", "navigation"] | None = None
    scope_name: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def one_semantic_target(self) -> Self:
        if (self.role is None) != (self.name is None):
            raise ValueError("Role and name must be supplied together.")
        if sum((self.role is not None, self.label is not None, self.text is not None)) != 1:
            raise ValueError("Supply exactly one role/name, label or text target.")
        if (self.scope_role is None) != (self.scope_name is None):
            raise ValueError("Scope role and name must be supplied together.")
        return self


class CaseAction(FrozenContract):
    action: Literal[
        "navigate",
        "click",
        "fill",
        "select",
        "check",
        "uncheck",
        "focus_next",
        "set_viewport",
        "wait",
    ]
    target: SemanticTarget | None = None
    test_value_key: Identifier | None = None
    url: str | None = Field(default=None, max_length=2048)
    preset: Literal["mobile320", "desktop1280"] | None = None
    milliseconds: int | None = Field(default=None, ge=0, le=2000, strict=True)
    action_id: Literal["registration_submit"] | None = None

    @model_validator(mode="after")
    def action_arguments(self) -> Self:
        expected: set[str] = {
            "navigate": {"url"},
            "click": {"target"},
            "fill": {"target", "test_value_key"},
            "select": {"target", "test_value_key"},
            "check": {"target"},
            "uncheck": {"target"},
            "focus_next": set[str](),
            "set_viewport": {"preset"},
            "wait": {"milliseconds"},
        }[self.action]
        actual = {
            field
            for field in ("target", "test_value_key", "url", "preset", "milliseconds")
            if getattr(self, field) is not None
        }
        if actual != expected:
            raise ValueError("Arguments do not match the permitted action.")
        if self.action_id is not None and not (
            self.action == "click"
            and self.target is not None
            and self.target.role == "button"
            and self.target.name == "Save"
            and self.target.scope_role == "form"
            and self.target.scope_name == "Registration"
        ):
            raise ValueError("The fixture action identity is valid only for Registration Save.")
        if self.action in {"fill", "select", "check", "uncheck"} and self.target is not None:
            if self.target.label is None:
                raise ValueError("Form actions require a labeled field.")
        return self


class ExpectedAssertion(FrozenContract):
    assertion_id: Identifier
    oracle: Oracle
    target: SemanticTarget | None = None
    expected_value: StrictStr | StrictBool | StrictInt
    requirement_refs: tuple[Identifier, ...] = Field(default=(), max_length=8)
    origin: Literal["approved_requirement", "fixture_truth", "inferred"] = "inferred"

    @model_validator(mode="after")
    def observable_oracle(self) -> Self:
        if (self.oracle in {"url", "title"}) != (self.target is None):
            raise ValueError("Element oracles require a target; page oracles do not.")
        if self.oracle in {"visible", "enabled", "checked"}:
            if type(self.expected_value) is not bool:
                raise ValueError("State expectations must be booleans.")
        elif self.oracle == "count":
            if type(self.expected_value) is not int or self.expected_value < 0:
                raise ValueError("Count expectations must be nonnegative integers.")
        elif not isinstance(self.expected_value, str) or len(self.expected_value) > 500:
            raise ValueError("Text expectations must be bounded strings.")
        if self.origin != "inferred" and not self.requirement_refs:
            raise ValueError("Grounded assertions require source references.")
        return self


class Requirement(FrozenContract):
    requirement_id: Identifier
    source: Literal["approved_knowledge", "user_brief", "fixture"]
    source_id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=1000)
    assertions: tuple[ExpectedAssertion, ...] = Field(default=(), max_length=8)
    defect_key: Identifier | None = None


class SafeTestValue(FrozenContract):
    key: Identifier
    value: str = Field(max_length=256)


class FeatureScope(FrozenContract):
    feature_key: Identifier
    goal: str = Field(min_length=1, max_length=1000)
    starting_url: str = Field(min_length=1, max_length=2048)
    allowed_origins: tuple[str, ...] = Field(min_length=1, max_length=8)
    requirements: tuple[Requirement, ...] = Field(default=(), max_length=32)
    safe_test_data: tuple[SafeTestValue, ...] = Field(default=(), max_length=32)
    unknown_requirements: tuple[str, ...] = Field(default=(), max_length=16)
    out_of_scope: tuple[str, ...] = Field(default=(), max_length=16)
    safety_class: Literal["read_only_or_low_risk"] = "read_only_or_low_risk"

    @model_validator(mode="after")
    def unique_owned_inputs(self) -> Self:
        for values in (
            [item.requirement_id for item in self.requirements],
            [item.key for item in self.safe_test_data],
            list(self.allowed_origins),
        ):
            if len(set(values)) != len(values):
                raise ValueError("Scope IDs and origins must be unique.")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("Origins must be HTTP(S).")
            if parsed.username or parsed.password or parsed.path not in {"", "/"}:
                raise ValueError("Origins cannot contain credentials or paths.")
            if parsed.query or parsed.fragment:
                raise ValueError("Origins cannot contain query or fragment.")
        ensure_scope_url(self.starting_url, self)
        return self


def ensure_scope_url(url: str, scope: FeatureScope) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Navigation must use an authorized HTTP(S) URL without credentials.")

    def origin_key(value: str) -> tuple[str, str | None, int | None]:
        item = urlsplit(value)
        return item.scheme, item.hostname, item.port or (443 if item.scheme == "https" else 80)

    if origin_key(url) not in {origin_key(origin) for origin in scope.allowed_origins}:
        raise ValueError("Navigation is outside the caller-owned feature scope.")


class TestCaseSpec(FrozenContract):
    __test__ = False
    case_id: Identifier
    feature_key: Identifier
    title: str = Field(min_length=1, max_length=160)
    kind: CaseKind
    priority: Literal["low", "medium", "high"] = "medium"
    requirement_refs: tuple[Identifier, ...] = Field(default=(), max_length=8)
    preconditions: tuple[str, ...] = Field(default=(), max_length=8)
    steps: tuple[CaseAction, ...] = Field(min_length=1, max_length=24)
    expected: tuple[ExpectedAssertion, ...] = Field(min_length=1, max_length=8)
    safety: Literal["non_destructive"] = "non_destructive"
    estimated_seconds: int = Field(default=30, ge=1, le=180, strict=True)
    estimated_cost_usd: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def unique_assertions(self) -> Self:
        ids = [item.assertion_id for item in self.expected]
        if len(set(ids)) != len(ids):
            raise ValueError("Assertion IDs must be unique within each case.")
        return self


class PlanBudget(FrozenContract):
    max_cases: int = Field(default=8, ge=1, le=12, strict=True)
    max_steps: int = Field(default=96, ge=1, le=288, strict=True)
    max_total_seconds: int = Field(default=300, ge=1, le=1200, strict=True)
    max_model_cost_usd: float = Field(default=0.25, ge=0, le=5, allow_inf_nan=False)


class SkippedCase(FrozenContract):
    case: TestCaseSpec
    reason: Literal[
        "duplicate_semantics", "case_budget", "step_budget", "time_budget", "cost_budget"
    ]


class FeatureCaseCandidates(FrozenContract):
    cases: tuple[TestCaseSpec, ...] = Field(min_length=1, max_length=64)
    coverage_gaps: tuple[str, ...] = Field(default=(), max_length=16)


class DeepFeaturePlan(FrozenContract):
    schema_version: Literal[1] = 1
    mode: Literal["deep_feature_v1"] = "deep_feature_v1"
    scope: FeatureScope
    budget: PlanBudget
    cases: tuple[TestCaseSpec, ...] = Field(min_length=1, max_length=12)
    skipped: tuple[SkippedCase, ...] = Field(default=(), max_length=64)
    coverage_gaps: tuple[str, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def final_plan_bounds(self) -> Self:
        all_cases = (*self.cases, *(item.case for item in self.skipped))
        if len({item.case_id for item in all_cases}) != len(all_cases):
            raise ValueError("Case IDs must be unique throughout the frozen plan.")
        if any(item.feature_key != self.scope.feature_key for item in all_cases):
            raise ValueError("Every case must belong to the feature.")
        if len(self.cases) > self.budget.max_cases:
            raise ValueError("Case budget exceeded.")
        if sum(len(item.steps) + len(item.expected) for item in self.cases) > self.budget.max_steps:
            raise ValueError("Step and assertion budget exceeded.")
        if sum(item.estimated_seconds for item in self.cases) > self.budget.max_total_seconds:
            raise ValueError("Time budget exceeded.")
        if (
            sum(item.estimated_cost_usd for item in self.cases)
            > self.budget.max_model_cost_usd + 1e-9
        ):
            raise ValueError("Estimated cost budget exceeded.")
        return self
