"""Shared Kafka message envelope for MarketTwin."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Stable metadata surrounding one MarketTwin message."""

    event_id: UUID
    event_type: str
    event_version: int
    occurred_at: datetime

    producer: str
    workspace_id: UUID

    trace_id: str | None
    correlation_id: str | None
    causation_id: str | None

    payload: dict[str, object]

    def __post_init__(self) -> None:
        """Validate invariants shared by every message."""

        if not self.event_type.strip():
            raise ValueError(
                "event_type must not be empty."
            )

        if self.event_version < 1:
            raise ValueError(
                "event_version must be positive."
            )

        if self.occurred_at.tzinfo is None:
            raise ValueError(
                "occurred_at must be timezone-aware."
            )

        if not self.producer.strip():
            raise ValueError(
                "producer must not be empty."
            )

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-ready wire representation."""

        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "event_version": self.event_version,
            "occurred_at": (
                self.occurred_at
                .astimezone(UTC)
                .isoformat()
            ),
            "producer": self.producer,
            "workspace_id": str(
                self.workspace_id
            ),
            "trace_id": self.trace_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "payload": self.payload,
        }

    def to_json(self) -> str:
        """Serialize the envelope deterministically."""

        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(
        cls,
        value: str,
    ) -> EventEnvelope:
        """Deserialize one MarketTwin message envelope."""

        raw: object = json.loads(value)

        if not isinstance(raw, dict):
            raise ValueError(
                "Event envelope must be a JSON object."
            )

        data = cast(
            dict[str, object],
            raw,
        )

        payload = data.get("payload")

        if not isinstance(payload, dict):
            raise ValueError(
                "Event envelope payload must be an object."
            )

        event_version = data.get(
            "event_version"
        )

        if (
            not isinstance(event_version, int)
            or isinstance(event_version, bool)
        ):
            raise ValueError(
                "event_version must be an integer."
            )

        return cls(
            event_id=UUID(
                str(data["event_id"])
            ),
            event_type=str(
                data["event_type"]
            ),
            event_version=event_version,
            occurred_at=datetime.fromisoformat(
                str(data["occurred_at"])
            ),
            producer=str(
                data["producer"]
            ),
            workspace_id=UUID(
                str(data["workspace_id"])
            ),
            trace_id=_optional_string(
                data.get("trace_id")
            ),
            correlation_id=_optional_string(
                data.get("correlation_id")
            ),
            causation_id=_optional_string(
                data.get("causation_id")
            ),
            payload=cast(
                dict[str, object],
                payload,
            ),
        )


def _optional_string(
    value: object,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(
            "Optional envelope identifiers must be strings."
        )

    return value