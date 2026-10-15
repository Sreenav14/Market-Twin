"""Focused verification of the same-context auth handoff workflow boundary."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser.auth_session_broker import AuthSessionScope
from markettwin_execution_orchestrator.browser.auth_verifier import VerifiedPrincipal
from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.persistence.human_action_lifecycle_repository import (
    HumanActionState,
)
from markettwin_execution_orchestrator.workflow import case_execution
from markettwin_execution_orchestrator.workflow.journey_executor import (
    PersonaJourneyExecutionRequest,
)
from markettwin_shared.auth_verification import AuthVerificationPolicy


@pytest.mark.asyncio
async def test_login_handoff_waits_for_signed_release_then_verifies_same_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = uuid4()
    suspension_id = uuid4()
    handle = BrowserSessionHandle(uuid4(), uuid4(), uuid4())
    run_id, target_id = uuid4(), uuid4()
    policy = AuthVerificationPolicy(
        origin="https://example.invalid",
        marker_selector="[data-testid='signed-in-role']",
        expected_marker="member",
        role="member",
        account_reference="fixture-member-1",
    )
    auth_scope = AuthSessionScope(
        run_id=run_id,
        target_id=target_id,
        role="member",
        account_reference="fixture-member-1",
        origin="https://example.invalid",
    )
    principal = VerifiedPrincipal("member", "fixture-member-1", policy.origin)
    states = iter(
        [
            HumanActionState(
                "leased", "human_pending", 2, datetime.now(UTC) + timedelta(minutes=2)
            ),
            HumanActionState("leased", "verifying", 3, datetime.now(UTC) + timedelta(minutes=2)),
            HumanActionState("leased", "verifying", 3, datetime.now(UTC) + timedelta(minutes=2)),
        ]
    )
    lifecycle = MagicMock()
    lifecycle.create_login_request = AsyncMock(return_value=request_id)
    async def next_state(**_kwargs: Any) -> HumanActionState:
        return next(states)

    lifecycle.state = AsyncMock(side_effect=next_state)
    lifecycle.finish_verification = AsyncMock()
    lifecycle.abandon = AsyncMock()
    def make_lifecycle(_session: object) -> Any:
        return lifecycle

    monkeypatch.setattr(case_execution, "HumanActionLifecycleRepository", make_lifecycle)

    suspension = MagicMock()
    suspension.create_waiting = AsyncMock()
    suspension.claim_ready = AsyncMock()
    def make_suspension(_session: object) -> Any:
        return suspension

    monkeypatch.setattr(case_execution, "ExecutionSuspensionRepository", make_suspension)
    from markettwin_execution_orchestrator.browser import owner_service

    wait = AsyncMock()
    monkeypatch.setattr(owner_service, "wait_for_human_action_resume", wait)

    controller = MagicMock()
    controller.verify_authenticated_role = AsyncMock(side_effect=[None, principal])
    controller.capture_verified_auth_session = AsyncMock(return_value=principal)
    controller.end_human_control = AsyncMock()
    db_session = MagicMock()
    db_session.commit = AsyncMock()
    db_session.rollback = AsyncMock()
    db_session.scalar = AsyncMock(return_value=suspension_id)
    request = cast(
        PersonaJourneyExecutionRequest,
        SimpleNamespace(
            test_run_id=run_id,
            execution_id=handle.execution_id,
            journey_id=handle.journey_id,
        ),
    )

    await case_execution.verify_or_request_login(  # pyright: ignore[reportPrivateUsage]
        request=request,
        controller=controller,
        handle=handle,
        policy=policy,
        auth_scope=auth_scope,
        session=db_session,
        max_wait_seconds=30,
    )

    lifecycle.create_login_request.assert_awaited_once()
    suspension.create_waiting.assert_awaited_once()
    wait.assert_awaited_once()
    assert wait.await_args is not None
    wait_kwargs = wait.await_args.kwargs
    assert wait_kwargs["request_id"] == request_id
    assert 0 < wait_kwargs["timeout_seconds"] <= 30
    controller.verify_authenticated_role.assert_has_awaits(
        [
            call(handle=handle, policy=policy),
            call(handle=handle, policy=policy),
        ]
    )
    controller.capture_verified_auth_session.assert_awaited_once_with(
        handle=handle,
        policy=policy,
        scope=auth_scope,
    )
    lifecycle.finish_verification.assert_awaited_once_with(
        request_id=request_id,
        expected_generation=3,
        verified=True,
    )
    suspension.claim_ready.assert_awaited_once_with(suspension_id=suspension_id)
    controller.end_human_control.assert_awaited_once_with(
        session_id=handle.session_id,
        execution_id=handle.execution_id,
        journey_id=handle.journey_id,
        verified=True,
        safe_to_capture=True,
    )


@pytest.mark.asyncio
async def test_human_wait_is_excluded_from_case_action_deadline() -> None:
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.04) as case_timeout:
            async with case_execution._pause_case_deadline(  # pyright: ignore[reportPrivateUsage]
                case_timeout,
                allowance_seconds=0.2,
            ):
                await asyncio.sleep(0.08)
            # The initial 40 ms action allowance remains after the human wait.
            await asyncio.sleep(0.06)
    assert time.monotonic() - started >= 0.1
