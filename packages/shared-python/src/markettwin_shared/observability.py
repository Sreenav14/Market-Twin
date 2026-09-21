"""Shared observability contracts for MarketTwin model-backed runtimes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, cast


UsageStatus = Literal["reported", "partial", "unavailable"]


@dataclass(frozen=True, slots=True)
class ModelTokenUsage:
    """Provider-neutral token usage for one model invocation."""

    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    tool_input_tokens: int | None = None
    total_tokens: int | None = None

    @property
    def status(self) -> UsageStatus:
        """Describe how complete the normalized usage metadata is."""

        values = (
            self.input_tokens,
            self.cached_input_tokens,
            self.output_tokens,
            self.reasoning_tokens,
            self.tool_input_tokens,
            self.total_tokens,
        )

        if all(value is None for value in values):
            return "unavailable"

        if (
            self.input_tokens is not None
            and self.output_tokens is not None
            and self.total_tokens is not None
        ):
            return "reported"

        return "partial"


@dataclass(frozen=True, slots=True)
class AgentRuntimeSnapshotSpec:
    """Immutable effective configuration for one historical model-backed role."""

    test_run_id: str
    agent_role: str
    runtime_agent_name: str
    runtime_kind: str
    agent_version: str
    snapshot_schema_version: int

    model_provider: str | None
    model_name: str | None
    model_configuration: dict[str, object]

    base_instruction: str | None
    effective_instruction: str | None
    runtime_prompt: str | None

    journey_id: str | None = None
    execution_id: str | None = None
    template_id: str | None = None
    template_version: str | None = None

    persona_snapshot: dict[str, object] | None = None
    mission_snapshot: dict[str, object] | None = None
    success_criteria: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    policy_references: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)

    def canonical_payload(self) -> dict[str, object]:
        """Return the stable semantic payload used for storage and hashing."""

        return {
            "snapshot_schema_version": self.snapshot_schema_version,
            "agent_role": self.agent_role,
            "runtime_agent_name": self.runtime_agent_name,
            "runtime_kind": self.runtime_kind,
            "agent_version": self.agent_version,
            "template_id": self.template_id,
            "template_version": self.template_version,
            "model": {
                "provider": self.model_provider,
                "name": self.model_name,
                "configuration": self.model_configuration,
            },
            "base_instruction": self.base_instruction,
            "effective_instruction": self.effective_instruction,
            "runtime_prompt": self.runtime_prompt,
            "persona": self.persona_snapshot,
            "mission": self.mission_snapshot,
            "success_criteria": list(self.success_criteria),
            "tools": list(self.tools),
            "policy_references": self.policy_references,
            "metadata": self.metadata,
        }

    @property
    def snapshot_sha256(self) -> str:
        """Hash the canonical semantic payload without volatile row metadata."""

        serialized = json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return hashlib.sha256(serialized).hexdigest()


def model_token_usage_from_adk(
    usage_metadata: object | None,
) -> ModelTokenUsage | None:
    """Normalize Google ADK/GenAI usage metadata without SDK coupling."""

    if usage_metadata is None:
        return None

    return ModelTokenUsage(
        input_tokens=_optional_int_field(
            usage_metadata,
            "prompt_token_count",
        ),
        cached_input_tokens=_optional_int_field(
            usage_metadata,
            "cached_content_token_count",
        ),
        output_tokens=_optional_int_field(
            usage_metadata,
            "candidates_token_count",
        ),
        reasoning_tokens=_optional_int_field(
            usage_metadata,
            "thoughts_token_count",
        ),
        tool_input_tokens=_optional_int_field(
            usage_metadata,
            "tool_use_prompt_token_count",
        ),
        total_tokens=_optional_int_field(
            usage_metadata,
            "total_token_count",
        ),
    )


def model_token_usage_from_litellm(
    response: object | None,
) -> ModelTokenUsage | None:
    """Normalize LiteLLM ModelResponse usage using public response fields."""

    if response is None:
        return None

    usage = _field(response, "usage")

    if usage is None:
        return None

    prompt_details = _field(
        usage,
        "prompt_tokens_details",
    )
    completion_details = _field(
        usage,
        "completion_tokens_details",
    )

    return ModelTokenUsage(
        input_tokens=_optional_int_field(
            usage,
            "prompt_tokens",
        ),
        cached_input_tokens=(
            _optional_int_field(
                prompt_details,
                "cached_tokens",
            )
            if prompt_details is not None
            else None
        ),
        output_tokens=_optional_int_field(
            usage,
            "completion_tokens",
        ),
        reasoning_tokens=(
            _optional_int_field(
                completion_details,
                "reasoning_tokens",
            )
            if completion_details is not None
            else None
        ),
        total_tokens=_optional_int_field(
            usage,
            "total_tokens",
        ),
    )


def _field(
    value: object,
    name: str,
) -> object | None:
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return mapping.get(name)

    return getattr(
        value,
        name,
        None,
    )


def _optional_int_field(
    value: object,
    name: str,
) -> int | None:
    raw_value = _field(
        value,
        name,
    )

    if type(raw_value) is not int or raw_value < 0:
        return None

    return raw_value
