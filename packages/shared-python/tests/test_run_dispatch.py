from datetime import UTC, datetime
from uuid import uuid4

from markettwin_shared.messaging import (
    COMMANDS_TOPIC,
    RUN_REQUESTED_EVENT_TYPE,
    RUN_REQUESTED_EVENT_VERSION,
    RunRequestedMessage,
)


def test_run_requested_message_builds_envelope() -> None:
    event_id = uuid4()
    test_run_id = uuid4()
    workspace_id = uuid4()

    message = RunRequestedMessage(
        event_id=event_id,
        test_run_id=test_run_id,
        workspace_id=workspace_id,
        occurred_at=datetime(
            2026,
            9,
            27,
            18,
            0,
            tzinfo=UTC,
        ),
    )

    envelope = message.to_envelope()

    assert COMMANDS_TOPIC == "markettwin.commands"

    assert envelope.event_id == event_id
    assert envelope.event_type == RUN_REQUESTED_EVENT_TYPE
    assert envelope.event_version == RUN_REQUESTED_EVENT_VERSION

    assert envelope.workspace_id == workspace_id
    assert envelope.producer == "markettwin-control-api"

    assert envelope.correlation_id == str(
        test_run_id
    )

    assert envelope.payload == {
        "test_run_id": str(test_run_id),
    }