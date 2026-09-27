from datetime import UTC, datetime
from uuid import uuid4

import pytest
from markettwin_shared.messaging import (
    RUN_REQUEST_TOPIC,
    RunRequestedMessage,
)


def test_run_request_round_trip() -> None:
    event_id = uuid4()
    test_run_id = uuid4()

    message = RunRequestedMessage(
        event_id=event_id,
        test_run_id=test_run_id,
        occurred_at=datetime(
            2026,
            9,
            27,
            12,
            30,
            tzinfo=UTC,
        ),
    )

    restored = RunRequestedMessage.from_json(
        message.to_json()
    )

    assert restored == message

    assert (
        RUN_REQUEST_TOPIC
        == "markettwin.run.requests.v1"
    )


def test_run_request_rejects_unknown_version() -> None:
    with pytest.raises(
        ValueError,
        match="Unsupported",
    ):
        RunRequestedMessage.from_json(
            """
            {
              "event_id":
                "00000000-0000-0000-0000-000000000001",
              "test_run_id":
                "00000000-0000-0000-0000-000000000002",
              "occurred_at":
                "2026-09-27T12:30:00+00:00",
              "schema_version": 999
            }
            """
        )