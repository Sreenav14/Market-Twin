"""Durable observer authorization rejects terminal runs and executions."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from markettwin_control_api.config import get_settings
from markettwin_database.models import (
    ActionApprovalReceipt,
    ActionApprovalRequest,
    AgentExecution,
    Application,
    ApplicationTarget,
    BrowserSession,
    ExecutionStep,
    ExecutionSuspension,
    PersonaJourney,
    RunMission,
    RunPersona,
    TargetAuthorization,
    User,
    Workspace,
    WorkspaceMember,
)
from markettwin_database.models import TestRun as RunModel
from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.owner_registry import BrowserOwnerRegistry
from markettwin_execution_orchestrator.browser.viewer_authority import DatabaseViewerAuthority
from markettwin_execution_orchestrator.persistence.sensitive_action_approval import (
    SensitiveActionApproval,
    SensitiveActionApprovalBlocked,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_SCOPE_TEST_DATABASE") != "1",
    reason="Requires an explicitly generated disposable local database migrated to head.",
)
async def test_observer_requires_active_run_execution_and_current_entitlement():
    settings = get_settings()
    assert settings.postgres_host in {"127.0.0.1", "localhost", "::1"}
    assert settings.postgres_db.startswith("mt_scope_")
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id, workspace_id, app_id, target_id, run_id = (uuid4() for _ in range(5))
    persona_id, mission_id, journey_id, execution_id, browser_id = (uuid4() for _ in range(5))
    authorization_id = uuid4()
    try:
        async with factory.begin() as session:
            email = f"observer-{user_id}@example.invalid"
            session.add(User(id=user_id, email=email, normalized_email=email))
            await session.flush()
            session.add(Workspace(
                id=workspace_id, name="Observer fixture", created_by_user_id=user_id,
            ))
            await session.flush()
            session.add_all([
                WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="owner"),
                Application(id=app_id, workspace_id=workspace_id,
                            created_by_user_id=user_id, name="Synthetic observer"),
            ])
            await session.flush()
            session.add(ApplicationTarget(
                id=target_id, application_id=app_id, name="Local", environment="test",
                base_url="http://127.0.0.1:8765/", requires_auth=False,
            ))
            await session.flush()
            session.add_all([
                TargetAuthorization(
                    id=authorization_id, target_id=target_id, created_by_user_id=user_id,
                    authorized_by_user_id=user_id, status="authorized",
                    authorization_basis="Owned synthetic local fixture.",
                    authorized_at=datetime.now(UTC),
                ),
                RunModel(id=run_id, workspace_id=workspace_id, application_id=app_id,
                         target_id=target_id, created_by_user_id=user_id, status="running",
                         target_snapshot={}, configuration_snapshot={}),
            ])
            await session.flush()
            session.add_all([
                RunPersona(id=persona_id, test_run_id=run_id, ordinal=1,
                           name="Fixture", description="Synthetic fixture"),
                RunMission(id=mission_id, test_run_id=run_id, ordinal=1,
                           title="Check fixture", objective="Check fixture", priority="low"),
            ])
            await session.flush()
            session.add(PersonaJourney(
                id=journey_id, test_run_id=run_id, persona_id=persona_id,
                mission_id=mission_id, ordinal=1,
            ))
            await session.flush()
            session.add(AgentExecution(
                id=execution_id, journey_id=journey_id, attempt_number=1, status="running",
            ))
            await session.flush()
            session.add(BrowserSession(
                id=browser_id, execution_id=execution_id, state="open",
                control_mode="agent", control_generation=2,
            ))
        authority = DatabaseViewerAuthority(factory, BrowserOwnerRegistry())
        handle = BrowserSessionHandle(browser_id, execution_id, journey_id)
        for run_status, execution_status, permitted in (
            ("planning", "running", True), ("running", "running", True),
            ("awaiting_human", "running", True), ("completed", "running", False),
            ("failed", "running", False), ("cancelled", "running", False),
            ("running", "completed", False), ("running", "failed", False),
            ("running", "skipped", False), ("running", "queued", False),
        ):
            async with factory.begin() as session:
                await session.execute(update(RunModel).where(RunModel.id == run_id).values(
                    status=run_status,
                ))
                await session.execute(update(AgentExecution).where(
                    AgentExecution.id == execution_id,
                ).values(status=execution_status))
            assert await authority.observer_permitted(user_id, handle, 2) is permitted
        async with factory.begin() as session:
            await session.execute(update(AgentExecution).where(
                AgentExecution.id == execution_id,
            ).values(status="running"))
            await session.execute(update(TargetAuthorization).where(
                TargetAuthorization.id == authorization_id,
            ).values(status="revoked", revoked_at=datetime.now(UTC)))
        assert not await authority.observer_permitted(user_id, handle, 2)
        # The approver must remain active at consumption, not only at decision time.
        async with factory.begin() as session:
            await session.execute(update(TargetAuthorization).where(
                TargetAuthorization.id == authorization_id,
            ).values(status="authorized", revoked_at=None))
            await session.execute(update(RunModel).where(RunModel.id == run_id).values(
                status="awaiting_human", human_action_approvals_enabled=True,
            ))
        for index, actor_state in enumerate(("disabled", "deleted", "active"), start=100):
            approval_id = uuid4()
            async with factory.begin() as session:
                await session.execute(update(User).where(User.id == user_id).values(
                    status="disabled" if actor_state == "disabled" else "active",
                    deleted_at=datetime.now(UTC) if actor_state == "deleted" else None,
                ))
                step = ExecutionStep(
                    execution_id=execution_id, step_number=index, action_type="click",
                    action_summary="Synthetic approved action", status="running",
                )
                session.add(step)
                await session.flush()
                session.add(ActionApprovalRequest(
                    id=approval_id, test_run_id=run_id, execution_id=execution_id,
                    browser_session_id=browser_id, step_id=step.id,
                    requested_by_user_id=user_id, decision_by_user_id=user_id,
                    action_fingerprint="a" * 64, resource_fingerprint="b" * 64,
                    environment="test", policy_version=2, control_generation=2,
                    action_summary="Synthetic approved action", status="approved",
                    expires_at=datetime.now(UTC) + timedelta(minutes=2),
                ))
                await session.flush()
                session.add(ExecutionSuspension(
                    test_run_id=run_id, journey_id=journey_id, execution_id=execution_id,
                    browser_session_id=browser_id, pending_approval_id=approval_id,
                    checkpoint_version=index, owner_generation=2, phase="case_action",
                    planned_step_index=0, active_deadline_remaining_ms=1000,
                    suspended_at=datetime.now(UTC),
                    human_deadline=datetime.now(UTC) + timedelta(minutes=2), status="waiting",
                ))
            async with factory() as session:
                consumer = SensitiveActionApproval(session, execution_id=execution_id)
                consume = consumer._consume(
                    approval_id=approval_id, action_fingerprint="a" * 64,
                    resource_fingerprint="b" * 64, environment="test",
                    authorization_id=authorization_id,
                )
                if actor_state == "active":
                    assert await consume == approval_id
                else:
                    with pytest.raises(SensitiveActionApprovalBlocked):
                        await consume
                    assert await session.get(ActionApprovalReceipt, approval_id) is None
                    await session.rollback()
            async with factory.begin() as session:
                await session.execute(update(ExecutionSuspension).where(
                    ExecutionSuspension.pending_approval_id == approval_id,
                ).values(status="abandoned"))
                if actor_state != "active":
                    assert await session.scalar(select(ActionApprovalRequest.status).where(
                        ActionApprovalRequest.id == approval_id,
                    )) == "approved"
    finally:
        await engine.dispose()
