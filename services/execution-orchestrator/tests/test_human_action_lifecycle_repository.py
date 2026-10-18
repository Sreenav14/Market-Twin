"""Focused worker-side human handoff persistence state tests."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from markettwin_database.models import BrowserSession, ExecutionSuspension, HumanActionRequest
from markettwin_execution_orchestrator.persistence.human_action_lifecycle_repository import (
    HumanActionLifecycleRepository,
    HumanHandoffUnavailable,
)


def make_repository(*scalars: object) -> tuple[HumanActionLifecycleRepository, MagicMock]:
    session = MagicMock()
    session.scalar = AsyncMock(side_effect=scalars)
    session.flush = AsyncMock()
    session.add = MagicMock()
    return HumanActionLifecycleRepository(session), session


@pytest.mark.asyncio
@pytest.mark.parametrize("recovery", [False, True])
async def test_create_login_request_persists_pending_and_fences_database_browser(
    recovery: bool,
) -> None:
    execution_id, browser_id, run_id = uuid4(), uuid4(), uuid4()
    browser = BrowserSession(
        id=browser_id,
        execution_id=execution_id,
        state="open",
        control_mode="agent",
        control_generation=0,
    )
    repository, session = make_repository(SimpleNamespace(id=run_id), browser, None)

    request_id = await repository.create_login_request(
        test_run_id=run_id,
        execution_id=execution_id,
        browser_session_id=browser_id,
        expires_at=datetime.now(UTC) + timedelta(minutes=3),
        **({"assistance_reason": "absent_scope"} if recovery else {}),
    )

    request = session.add.call_args.args[0]
    assert isinstance(request, HumanActionRequest)
    assert request.id == request_id
    assert request.request_type == ("other" if recovery else "login")
    assert request.status == "pending"
    assert request.idempotency_key == ("case-recovery-v1:0" if recovery else "auth-preflight-v1")
    assert browser.control_mode == "human_pending"
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_login_request_fails_closed_when_frozen_authorization_is_missing() -> None:
    repository, session = make_repository(None, None)

    with pytest.raises(HumanHandoffUnavailable):
        await repository.create_login_request(
            test_run_id=uuid4(),
            execution_id=uuid4(),
            browser_session_id=uuid4(),
            expires_at=datetime.now(UTC) + timedelta(minutes=3),
        )

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_finish_verification_marks_request_and_checkpoint_ready_only_on_verified_role() -> None:
    request_id, browser_id = uuid4(), uuid4()
    request = HumanActionRequest(
        id=request_id,
        execution_id=uuid4(),
        browser_session_id=browser_id,
        request_type="login",
        idempotency_key="auth-preflight-v1",
        status="leased",
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    browser = BrowserSession(
        id=browser_id,
        execution_id=request.execution_id,
        state="open",
        control_mode="verifying",
        control_generation=3,
    )
    checkpoint = ExecutionSuspension(
        id=uuid4(),
        test_run_id=uuid4(),
        journey_id=uuid4(),
        execution_id=request.execution_id,
        browser_session_id=browser_id,
        pending_request_id=request_id,
        checkpoint_version=1,
        owner_generation=2,
        phase="auth_preflight",
        planned_step_index=0,
        active_deadline_remaining_ms=30_000,
        suspended_at=datetime.now(UTC),
        human_deadline=datetime.now(UTC) + timedelta(minutes=1),
        resume_count=0,
        status="waiting",
    )
    session = MagicMock()
    pair_result = MagicMock()
    pair_result.one_or_none.return_value = (request, browser)
    session.execute = AsyncMock(return_value=pair_result)
    session.scalar = AsyncMock(return_value=checkpoint)
    session.flush = AsyncMock()
    repository = HumanActionLifecycleRepository(session)

    await repository.finish_verification(
        request_id=request_id,
        expected_generation=3,
        verified=True,
    )

    assert request.status == "completed"
    assert request.completed_at is not None
    assert browser.control_mode == "agent"
    assert checkpoint.status == "ready"
    session.flush.assert_awaited_once()
