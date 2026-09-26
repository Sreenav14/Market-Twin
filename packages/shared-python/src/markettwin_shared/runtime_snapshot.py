"""Canonical runtime snapshot contracts for MarketTwin agents."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, cast

AgentRole = Literal[
    "meta",
    "persona",
    "visual_verifier",
]

type SnapshotValue = (
    None | str | bool | int | float | list["SnapshotValue"] | dict[str, "SnapshotValue"]
)

_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "authorization_header",
        "cookie",
        "cookies",
        "password",
        "passwd",
        "secret",
        "client_secret",
        "access_token",
        "refresh_token",
        "session_token",
        "otp",
        "mfa",
        "captcha",
        "cvv",
        "card_number",
        "cc_number",
        "payment_token",
        "signed_url",
        "presigned_url",
        "private_takeover_input",
    }
)

_SENSITIVE_SUFFIXES = (
    "_api_key",
    "_password",
    "_secret",
    "_access_token",
    "_refresh_token",
    "_session_token",
    "_authorization",
    "_cookie",
    "_otp",
    "_captcha",
    "_cvv",
)


def _normalized_key(key: str) -> str:
    """Normalize mapping keys before sensitive-value checks."""

    return key.strip().casefold().replace("-", "_").replace(".", "_")


def _is_sensitive_key(key: str) -> bool:
    """Return whether a key identifies data that must not enter snapshots."""

    normalized = _normalized_key(key)

    return normalized in _SENSITIVE_KEYS or normalized.endswith(_SENSITIVE_SUFFIXES)


def sanitize_snapshot_value(value: object) -> SnapshotValue:
    """Return a JSON-safe copy with sensitive mapping entries removed.

    Runtime snapshots contain MarketTwin-owned configuration, not credentials
    or private runtime secrets. Unsupported non-JSON values are rejected so
    hashing cannot silently depend on unstable object representations.
    """

    if value is None or isinstance(value, (str, bool, int)):
        return value

    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("Runtime snapshot values cannot contain NaN or infinity.")
        return value

    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        sanitized: dict[str, SnapshotValue] = {}

        for key, item in mapping.items():
            if not isinstance(key, str):
                raise TypeError("Runtime snapshot mapping keys must be strings.")

            if _is_sensitive_key(key):
                continue

            sanitized[key] = sanitize_snapshot_value(item)

        return sanitized

    if isinstance(value, (list, tuple)):
        sequence = cast(list[object] | tuple[object, ...], value)
        return [sanitize_snapshot_value(item) for item in sequence]

    raise TypeError(
        f"Runtime snapshot values must be JSON-compatible; received {type(value).__name__}."
    )


@dataclass(frozen=True, slots=True)
class AgentRuntimeSnapshotPayload:
    """Immutable semantic configuration for one MarketTwin agent runtime.

    Database identifiers, timestamps, trace IDs, and other volatile runtime
    values intentionally do not belong in this payload. They will be stored
    alongside the payload by the persistence layer.
    """

    agent_role: AgentRole
    runtime_kind: str

    runtime_agent_name: str | None = None

    agent_version: int = 1
    snapshot_schema_version: int = 1

    template_id: str | None = None
    template_version: str | None = None

    model_provider: str | None = None
    model_name: str | None = None
    model_configuration: Mapping[str, object] = field(
        default_factory=dict[str, object],
    )

    base_instruction: str | None = None
    effective_instruction: str | None = None
    runtime_prompt: str | None = None

    persona_snapshot: Mapping[str, object] | None = None
    mission_snapshot: Mapping[str, object] | None = None

    success_criteria: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    policy_references: tuple[str, ...] = ()

    metadata: Mapping[str, object] = field(
        default_factory=dict[str, object],
    )

    def __post_init__(self) -> None:
        """Reject malformed snapshot identity/version values."""

        if not self.runtime_kind.strip():
            raise ValueError("runtime_kind must not be blank.")

        if self.runtime_agent_name is not None:
            if not self.runtime_agent_name.strip():
                raise ValueError("runtime_agent_name must not be blank when provided.")

        if self.agent_version < 1:
            raise ValueError("agent_version must be at least 1.")

        if self.snapshot_schema_version < 1:
            raise ValueError("snapshot_schema_version must be at least 1.")

    def semantic_payload(self) -> dict[str, SnapshotValue]:
        """Return the safe semantic payload used for persistence and hashing."""

        raw_payload: dict[str, object] = {
            "agent_role": self.agent_role,
            "runtime_kind": self.runtime_kind,
            "runtime_agent_name": self.runtime_agent_name,
            "agent_version": self.agent_version,
            "snapshot_schema_version": self.snapshot_schema_version,
            "template_id": self.template_id,
            "template_version": self.template_version,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "model_configuration": self.model_configuration,
            "base_instruction": self.base_instruction,
            "effective_instruction": self.effective_instruction,
            "runtime_prompt": self.runtime_prompt,
            "persona_snapshot": self.persona_snapshot,
            "mission_snapshot": self.mission_snapshot,
            "success_criteria": self.success_criteria,
            "tools": self.tools,
            "policy_references": self.policy_references,
            "metadata": self.metadata,
        }

        sanitized = sanitize_snapshot_value(raw_payload)

        if not isinstance(sanitized, dict):
            raise TypeError("Runtime snapshot semantic payload must be a mapping.")

        return sanitized

    def canonical_json(self) -> str:
        """Serialize the semantic payload deterministically."""

        return json.dumps(
            self.semantic_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

    def sha256(self) -> str:
        """Return the stable SHA-256 digest of semantic configuration."""

        canonical_bytes = self.canonical_json().encode("utf-8")
        return hashlib.sha256(canonical_bytes).hexdigest()
