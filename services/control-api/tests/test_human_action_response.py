"""The validated claim grant must expose the frontend's viewer capability flag."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from markettwin_control_api.api.human_actions import ClaimResponse


def test_validated_claim_serializes_viewer_capability_without_secret_repr() -> None:
    grant = ClaimResponse(
        request_id=uuid4(), browser_session_id=uuid4(), lease_id=uuid4(),
        lease_token="synthetic-lease-token-value-000000000000",
        generation=1, expires_at=datetime.now(UTC) + timedelta(minutes=2),
        viewer_url="ws://localhost:5173/api/v1/hitl-viewer",
        viewer_ticket="synthetic-one-use-viewer-ticket",
    )
    payload = grant.model_dump(mode="json")
    assert payload["viewer_available"] is True
    assert payload["viewer_url"] == grant.viewer_url
    assert payload["viewer_ticket"] == grant.viewer_ticket
    assert grant.lease_token not in repr(grant)
    assert grant.viewer_ticket not in repr(grant)
