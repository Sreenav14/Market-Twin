"""Observed journeys and owner-approved checks; observations grant no authority."""

import hashlib
import json
from datetime import datetime
from typing import Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from markettwin_shared.feature_plan import CaseAction, FrozenContract, Identifier

BlockedReason = Literal[
    "authentication_required", "policy_blocked", "target_not_found", "ambiguous_target",
    "observation_loop", "time_budget", "step_budget", "provider_error", "unknown",
]
DiscoveryAction = Literal["navigate", "click", "fill", "select", "check", "uncheck", "go_back"]


class DiscoveredStep(FrozenContract):
    ordinal: StrictInt = Field(ge=1, le=60)
    action: DiscoveryAction
    target_role: str | None = Field(default=None, max_length=80)
    target_name: str | None = Field(default=None, max_length=160)
    target_label: str | None = Field(default=None, max_length=160)
    target_text: str | None = Field(default=None, max_length=160)
    scope_role: str | None = None
    scope_name: str | None = Field(default=None, max_length=160)
    locator_strategy: str | None = None
    input_key: Identifier | None = None
    navigation_url_path: str | None = Field(default=None, max_length=2048)
    resulting_url_path: str | None = Field(default=None, max_length=2048)
    resulting_page_title: str | None = Field(default=None, max_length=500)
    observed_text_markers: tuple[str, ...] = Field(default=(), max_length=8)
    # ExecutionStep uses a bigint key; do not manufacture UUID aliases.
    execution_step_id: StrictInt = Field(gt=0)
    name_source: Literal["playwright", "approximate", "unavailable"] = "unavailable"

    @model_validator(mode="after")
    def safe_paths_and_inputs(self) -> Self:
        for path in (self.resulting_url_path, self.navigation_url_path):
            if path is not None:
                parsed = urlsplit(path)
                if not path.startswith("/") or parsed.netloc or parsed.query or parsed.fragment:
                    raise ValueError("Discovery paths contain no origin, query or fragment.")
        if any(len(marker) > 160 for marker in self.observed_text_markers):
            raise ValueError("Observed text markers must be short.")
        if self.action in {"fill", "select"} and self.input_key is None:
            raise ValueError("Form inputs require a safe data key.")
        if (self.action == "click" and self.target_role and self.name_source != "playwright"
                and not (self.target_label or self.target_text)):
            raise ValueError("Approximate names need a recorded secondary locator.")
        return self


class DiscoveredJourney(FrozenContract):
    journey_key: Identifier
    title: str = Field(min_length=1, max_length=200)
    feature_key: Identifier
    completed: bool
    blocked_reason: BlockedReason | None = None
    steps: tuple[DiscoveredStep, ...] = Field(default=(), max_length=60)

    @model_validator(mode="after")
    def consistent_completion(self) -> Self:
        if self.completed and (self.blocked_reason or not any(
            step.action in {"click", "fill", "select", "check", "uncheck"} for step in self.steps
        )):
            raise ValueError("Completed discovery requires an actual interaction and no blocker.")
        if not self.completed and self.blocked_reason is None:
            raise ValueError("Incomplete discovery requires a blocker.")
        if [s.ordinal for s in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("Journey steps must have consecutive ordinals.")
        if len({s.execution_step_id for s in self.steps}) != len(self.steps):
            raise ValueError("A journey cannot duplicate evidence steps.")
        return self


class DiscoveredFeature(FrozenContract):
    feature_key: Identifier
    title: str = Field(min_length=1, max_length=200)
    entry_url_path: str
    journey_keys: tuple[Identifier, ...]


class DiscoveryMap(FrozenContract):
    schema_version: Literal[1] = 1
    target_origin: str
    features: tuple[DiscoveredFeature, ...] = Field(default=(), max_length=60)
    journeys: tuple[DiscoveredJourney, ...] = Field(default=(), max_length=60)
    coverage_notes: tuple[str, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def consistent_references(self) -> Self:
        origin = urlsplit(self.target_origin)
        if (origin.scheme not in {"http", "https"} or not origin.hostname
                or origin.username or origin.password or origin.path not in {"", "/"}
                or origin.query or origin.fragment):
            raise ValueError("Discovery requires a plain HTTP(S) origin.")
        journeys = {j.journey_key: j for j in self.journeys}
        features = {f.feature_key: f for f in self.features}
        if len(journeys) != len(self.journeys) or len(features) != len(self.features):
            raise ValueError("Discovery keys must be unique.")
        for feature in self.features:
            if any(key not in journeys or journeys[key].feature_key != feature.feature_key
                   for key in feature.journey_keys):
                raise ValueError("Feature references an unrelated journey.")
        if any(j.feature_key not in features for j in self.journeys):
            raise ValueError("Journey references an unknown feature.")
        return self


class ContractAssertion(FrozenContract):
    assertion_id: Identifier
    oracle: Literal[
        "visible_text", "visible", "enabled", "url_path_v1", "title", "count", "checked"
    ]
    target_role: str | None = Field(default=None, max_length=80)
    target_name: str | None = Field(default=None, max_length=160)
    expected_value: StrictStr | StrictBool | StrictInt | None = None
    plain_language: str = Field(min_length=1, max_length=500)
    origin: Literal["user_approved"] | None = None
    source_step_ordinal: StrictInt = Field(ge=1, le=60)
    excluded: bool = False

    @model_validator(mode="after")
    def validate_assertion(self) -> Self:
        if self.oracle in {"url_path_v1", "title"}:
            if self.target_role is not None or self.target_name is not None:
                raise ValueError("Page oracles do not use element targets.")
        return self


class FrozenJourneyContract(FrozenContract):
    journey_key: Identifier
    title: str = Field(min_length=1, max_length=200)
    feature_key: Identifier
    steps: tuple[CaseAction, ...] = Field(default=(), max_length=60)
    assertions: tuple[ContractAssertion, ...] = Field(default=(), max_length=60)
    safe_test_data_keys: tuple[str, ...] = Field(default=(), max_length=32)
    excluded: bool = False


class TestContract(FrozenContract):
    __test__ = False
    schema_version: Literal[1] = 1
    contract_id: UUID
    test_run_id: UUID
    version: StrictInt = Field(default=1, ge=1)
    status: Literal["draft", "approved", "frozen", "superseded"] = "draft"
    journeys: tuple[FrozenJourneyContract, ...] = Field(default=(), max_length=60)
    approved_by_user_id: UUID | None = None
    approved_at: datetime | None = None

    def content_hash(self) -> str:
        payload = [
            {
                "journey_key": j.journey_key,
                "title": j.title,
                "feature_key": j.feature_key,
                "excluded": j.excluded,
                "safe_test_data_keys": list(j.safe_test_data_keys),
                "steps": [s.model_dump(mode="json") for s in j.steps],
                "assertions": [
                    {
                        "assertion_id": a.assertion_id,
                        "oracle": a.oracle,
                        "target_role": a.target_role,
                        "target_name": a.target_name,
                        "expected_value": a.expected_value,
                        "source_step_ordinal": a.source_step_ordinal,
                        "excluded": a.excluded,
                    }
                    for a in j.assertions
                ],
            }
            for j in self.journeys
        ]
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
