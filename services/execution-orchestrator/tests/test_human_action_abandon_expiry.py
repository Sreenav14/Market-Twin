"""Regression coverage for timeout cleanup of durable human handoffs."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from markettwin_database.models import BrowserSession, HumanActionRequest
from markettwin_execution_orchestrator.persistence.human_action_lifecycle_repository import (
    HumanActionLifecycleRepository,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expiry_offset", "expected_status"),
    [
        (timedelta(seconds=-1), "expired"),
        (timedelta(minutes=5), "cancelled"),
        (None, "cancelled"),
    ],
)
async def test_abandon_preserves_timeout_vs_cancellation(
    expiry_offset: timedelta | None, expected_status: str,
) -> None:
    request_id, execution_id, browser_id = uuid4(), uuid4(), uuid4()
    expires_at = datetime.now(UTC) + expiry_offset if expiry_offset is not None else None
    request = HumanActionRequest(
        id=request_id, execution_id=execution_id, browser_session_id=browser_id,
        request_type="login", idempotency_key="auth-preflight-v1",
        status="pending", expires_at=expires_at,
    )
    browser = BrowserSession(
        id=browser_id, execution_id=execution_id, state="open",
        control_mode="human_pending", control_generation=2,
    )
    pair = MagicMock()
    pair.one_or_none.return_value = (request, browser)
    session = MagicMock()
    session.execute = AsyncMock(side_effect=(pair, MagicMock()))
    session.scalars = AsyncMock(return_value=[])
    session.scalar = AsyncMock(return_value=None)
    session.flush = AsyncMock()

    await HumanActionLifecycleRepository(session).abandon(request_id=request_id)

    assert request.status == expected_status
    assert browser.control_generation == 3
    assert browser.control_mode == "none"
    session.flush.assert_awaited_once()
