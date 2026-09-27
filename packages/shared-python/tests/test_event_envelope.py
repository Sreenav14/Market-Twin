from datetime import UTC, datetime
from uuid import uuid4

import pytest
from markettwin_shared.messaging import (
    EventEnvelope,
)


def test_event_envelope_round_trip() -> None:
    event_id = uuid4()
    workspace_id = uuid4()
    test_run_id = uuid4()

    envelope = EventEnvelope(
        event_id=event_id,
        event_type="run.requested",
        event_version=1,
        occurred_at=datetime(
            2026,
            9,
            27,
            17,
            30,
            tzinfo=UTC,
        ),
        producer="markettwin-control-api",
        workspace_id=workspace_id,
        trace_id=None,
        correlation_id=str(test_run_id),
        causation_id=None,
        payload={
            "test_run_id": str(test_run_id),
        },
    )

    restored = EventEnvelope.from_json(
        envelope.to_json()
    )

    assert restored == envelope


def test_event_envelope_rejects_naive_time() -> None:
    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        EventEnvelope(
            event_id=uuid4(),
            event_type="run.requested",
            event_version=1,
            occurred_at=datetime(
                2026,
                9,
                27,
                17,
                30,
            ),
            producer="markettwin-control-api",
            workspace_id=uuid4(),
            trace_id=None,
            correlation_id=None,
            causation_id=None,
            payload={},
        )