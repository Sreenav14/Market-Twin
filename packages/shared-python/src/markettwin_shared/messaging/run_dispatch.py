"""Stable messaging contracts for MarketTwin run dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from markettwin_shared.messaging.envelope import EventEnvelope

RUN_REQUEST_TOPIC: Final[str] = (
    "markettwin.execution.commands"
)
RUN_REQUESTED_EVENT_TYPE: Final[str] = (
    "run.requested"
)
RUN_REQUESTED_EVENT_VERSION: Final[int] = 1

RUN_REQUEST_SCHEMA_VERSION: Final[int] = 1

COMMANDS_TOPIC: Final[str] = (
    "markettwin.commands"
)

@dataclass(frozen=True, slots=True)
class RunRequestedMessage:
    """Request execution of one persisted MarketTwin TestRun."""

    event_id: UUID
    test_run_id: UUID
    workspace_id: UUID
    occurred_at: datetime
    
    trace_id: str | None = None
    causation_id: str | None = None
    
    def to_envelope(self) -> EventEnvelope:
        """Build the shared kafka envelope for this command."""
        
        if self.occurred_at.tzinfo is None:
            raise ValueError(
                "Occured_at must be timezone-aware."
            )
            
        return EventEnvelope(
            event_id=self.event_id,
            event_type=RUN_REQUESTED_EVENT_TYPE,
            event_version=RUN_REQUESTED_EVENT_VERSION,
            occurred_at=self.occurred_at,
            producer="markettwin-control-api",
            workspace_id=self.workspace_id,
            trace_id=self.trace_id,
            correlation_id=str(self.test_run_id),
            causation_id=self.causation_id,
            payload={
                "test_run_id": str(self.test_run_id),
            },
        )
        