"""Stable messaging contracts for MarketTwin run dispatch."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Final, cast
from uuid import UUID

RUN_REQUEST_TOPIC: Final[str] = (
    "markettwin.run.requests.v1"
)

RUN_REQUEST_SCHEMA_VERSION: Final[int] = 1


@dataclass(frozen=True, slots=True)
class RunRequestedMessage:
    """Request execution of one persisted MarketTwin TestRun."""

    event_id: UUID
    test_run_id: UUID
    occurred_at: datetime
    schema_version: int = (
        RUN_REQUEST_SCHEMA_VERSION
    )

    def to_json(self) -> str:
        """Serialize the Kafka message deterministically."""

        payload = asdict(self)

        payload["event_id"] = str(
            self.event_id
        )
        payload["test_run_id"] = str(
            self.test_run_id
        )
        payload["occurred_at"] = (
            self.occurred_at
            .astimezone(UTC)
            .isoformat()
        )

        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(
        cls,
        value: str,
    ) -> RunRequestedMessage:
        """Deserialize and validate one run request."""

        raw_payload: object = json.loads(value)

        if not isinstance(raw_payload, dict):
            raise ValueError(
                "Run request must be a JSON object."
            )

        payload = cast(
            dict[str, object],
            raw_payload,
        )

        schema_version = payload.get(
            "schema_version"
        )

        if (
            not isinstance(schema_version, int)
            or schema_version
            != RUN_REQUEST_SCHEMA_VERSION
        ):
            raise ValueError(
                "Unsupported run request schema version."
            )

        return cls(
            event_id=UUID(
                str(payload["event_id"])
            ),
            test_run_id=UUID(
                str(payload["test_run_id"])
            ),
            occurred_at=datetime.fromisoformat(
                str(payload["occurred_at"])
            ),
            schema_version=schema_version,
        )