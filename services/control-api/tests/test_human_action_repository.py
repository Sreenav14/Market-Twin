"""PostgreSQL coverage for human-control lease fencing and exclusivity."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from markettwin_control_api.config import get_settings
from markettwin_control_api.persistence.models import (
    Application,
    ApplicationTarget,
    PersonaJourney,
    RunMission,
    RunPersona,
    TargetAuthorization,
    User,
    Workspace,
    WorkspaceMember,
)
from markettwin_control_api.persistence.models import (
    TestRun as RunModel,
)
from markettwin_control_api.persistence.repositories.action_approval_repository import (
    ActionApprovalRepository,
    ApprovalRejectedError,
    action_fingerprint,
)
from markettwin_control_api.persistence.repositories.human_action_repository import (
    HumanActionConflictError,
    HumanActionNotAuthorizedError,
    HumanActionRepository,
    HumanLeaseGrant,
)
from markettwin_database import Base
from markettwin_database.models.execution import (
    ActionApprovalReceipt,
    ActionApprovalRequest,
    AgentExecution,
    BrowserSession,
    ExecutionStep,
    ExecutionSuspension,
    HumanActionRequest,
    HumanControlLease,
)
from markettwin_execution_orchestrator.persistence.fixture_action_approval import (
    FixtureActionApproval,
    FixtureApprovalRejected,
)
from sqlalchemy import Table, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema

TABLES = tuple(
    cast(Table, model.__table__)
    for model in (
        User,
        Workspace,
        WorkspaceMember,
        Application,
        ApplicationTarget,
        TargetAuthorization,
        RunModel,
        RunPersona,
        RunMission,
        PersonaJourney,
        AgentExecution,
        BrowserSession,
        ExecutionStep,
        HumanActionRequest,
        HumanControlLease,
        ExecutionSuspension,
        ActionApprovalRequest,
        ActionApprovalReceipt,
    )
)


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_DATABASE") != "1",
    reason="Set MARKETTWIN_TEST_DATABASE=1 to verify PostgreSQL lease constraints.",
)
async def test_claim_is_exclusive_and_generation_fences_stale_input() -> None:
    engine = create_async_engine(get_settings().database_url, connect_args={"timeout": 5})
    suffix = uuid4().hex[:12]
    schemas = {
        "core": f"hitl_core_{suffix}",
        "testing": f"hitl_testing_{suffix}",
        "execution": f"hitl_execution_{suffix}",
    }
    try:
        async with engine.begin() as connection:
            for schema in schemas.values():
                await connection.execute(CreateSchema(schema))
            translated = await connection.execution_options(schema_translate_map=schemas)
            await translated.run_sync(lambda sync: Base.metadata.create_all(sync, tables=TABLES))

        scoped_engine = engine.execution_options(schema_translate_map=schemas)
        factory = async_sessionmaker(scoped_engine, expire_on_commit=False)
        user_id = uuid4()
        member_id = uuid4()
        run_id = uuid4()
        journey_id = uuid4()
        execution_id = uuid4()
        browser_id = uuid4()
        now = datetime.now(UTC)
        async with factory.begin() as session:
            session.add_all(
                [
                    User(
                        id=user_id,
                        email=f"{suffix}@example.invalid",
                        normalized_email=f"{suffix}@example.invalid",
                    ),
                    Workspace(id=uuid4(), name="HITL lease test", created_by_user_id=user_id),
                ]
            )
            await session.flush()
            workspace = await session.scalar(
                select(Workspace).where(Workspace.created_by_user_id == user_id)
            )
            assert workspace is not None
            session.add_all(
                [
                    User(
                        id=member_id,
                        email=f"member-{suffix}@example.invalid",
                        normalized_email=f"member-{suffix}@example.invalid",
                    ),
                    WorkspaceMember(
                        workspace_id=workspace.id, user_id=member_id, role="member",
                    ),
                ]
            )
            application = Application(
                id=uuid4(), workspace_id=workspace.id, created_by_user_id=user_id,
                name="Synthetic protected app",
            )
            target = ApplicationTarget(
                id=uuid4(), application_id=application.id, name="Local fixture",
                environment="local", base_url="http://127.0.0.1", requires_auth=True,
            )
            session.add_all([application, target])
            await session.flush()
            session.add_all(
                [
                    WorkspaceMember(workspace_id=workspace.id, user_id=user_id, role="owner"),
                    TargetAuthorization(
                        id=uuid4(), target_id=target.id, created_by_user_id=user_id,
                        authorized_by_user_id=user_id, status="authorized",
                        authorization_basis="synthetic fixture test", authorized_at=now,
                        expires_at=now + timedelta(minutes=5),
                    ),
                    RunModel(
                        id=run_id, workspace_id=workspace.id, application_id=application.id,
                        target_id=target.id, created_by_user_id=user_id, status="running",
                        target_snapshot={}, configuration_snapshot={},
                        synthetic_fixture_approval_enabled=True,
                    ),
                ]
            )
            await session.flush()
            persona_id, mission_id = uuid4(), uuid4()
            session.add_all(
                [
                    RunPersona(
                        id=persona_id, test_run_id=run_id, ordinal=1,
                        name="Fixture operator", description="synthetic test identity",
                    ),
                    RunMission(
                        id=mission_id, test_run_id=run_id, ordinal=1,
                        title="Protected check", objective="Verify role access", priority="low",
                    ),
                ]
            )
            await session.flush()
            session.add(
                PersonaJourney(
                    id=journey_id, test_run_id=run_id, persona_id=persona_id,
                    mission_id=mission_id, ordinal=1,
                )
            )
            await session.flush()
            session.add(
                AgentExecution(
                    id=execution_id, journey_id=journey_id, attempt_number=1,
                    status="running", runtime_name="deterministic_test_case_v1",
                )
            )
            await session.flush()
            session.add(
                BrowserSession(
                    id=browser_id, execution_id=execution_id, state="open",
                    control_mode="agent", control_generation=0,
                )
            )
            await session.flush()
            approval_step = ExecutionStep(
                execution_id=execution_id,
                step_number=1,
                action_type="click",
                action_summary="Approve synthetic fixture operation.",
                status="completed",
            )
            session.add(approval_step)
            await session.flush()
            action: dict[str, object] = {
                "operation": "archive",
                "record": "fixture-row-1",
            }
            approval = await ActionApprovalRepository(session).create(
                test_run_id=run_id,
                execution_id=execution_id,
                step_id=approval_step.id,
                requested_by_user_id=user_id,
                action=action,
                resource={"target": str(target.id), "environment": "local"},
                environment="local",
                policy_version=1,
                action_summary="Archive synthetic fixture record",
                expires_at=now + timedelta(minutes=2),
            )
            request = await HumanActionRepository(session).create_request(
                execution_id=execution_id,
                browser_session_id=browser_id,
                request_type="login",
                idempotency_key="auth-preflight:case-1",
                expires_at=now + timedelta(minutes=2),
            )
            assert request.status == "pending"
            assert await HumanActionRepository(session).create_request(
                execution_id=execution_id,
                browser_session_id=browser_id,
                request_type="login",
                idempotency_key="auth-preflight:case-1",
                expires_at=now + timedelta(minutes=2),
            ) == request

        async with factory.begin() as session:
            with pytest.raises(ApprovalRejectedError):
                await ActionApprovalRepository(session).decide(
                    approval_id=approval.id, actor_id=member_id, approved=True,
                )
        async with factory.begin() as session:
            decision = await ActionApprovalRepository(session).decide(
                approval_id=approval.id, actor_id=user_id, approved=True,
            )
            assert decision.status == "approved"
        fingerprint = action_fingerprint(action)
        resource_fingerprint = action_fingerprint(
            {"target": str(target.id), "environment": "local"}
        )
        async with factory.begin() as session:
            with pytest.raises(ApprovalRejectedError):
                await ActionApprovalRepository(session).consume(
                    approval_id=approval.id,
                    expected_fingerprint=action_fingerprint({"operation": "different"}),
                    expected_resource_fingerprint=resource_fingerprint,
                    environment="local",
                    policy_version=1,
                )
        async with factory.begin() as session:
            receipt = await ActionApprovalRepository(session).consume(
                approval_id=approval.id, expected_fingerprint=fingerprint,
                expected_resource_fingerprint=resource_fingerprint,
                environment="local",
                policy_version=1,
            )
            assert receipt.dispatch_state == "claimed"
        async with factory.begin() as session:
            with pytest.raises(ApprovalRejectedError):
                await ActionApprovalRepository(session).consume(
                    approval_id=approval.id, expected_fingerprint=fingerprint,
                    expected_resource_fingerprint=resource_fingerprint,
                    environment="local",
                    policy_version=1,
                )
        async with factory.begin() as session:
            await ActionApprovalRepository(session).mark_completed(approval_id=approval.id)
            receipt = await session.get(ActionApprovalReceipt, approval.id)
            assert receipt is not None and receipt.dispatch_state == "completed"
            expired_approval = await ActionApprovalRepository(session).create(
                test_run_id=run_id,
                execution_id=execution_id,
                step_id=approval_step.id,
                requested_by_user_id=user_id,
                action={"operation": "archive", "record": "fixture-row-2"},
                resource={"target": str(target.id), "environment": "local"},
                environment="local",
                policy_version=1,
                action_summary="Archive another synthetic fixture record",
                expires_at=datetime.now(UTC) + timedelta(minutes=1),
            )
            expired_row = await session.get(ActionApprovalRequest, expired_approval.id)
            assert expired_row is not None
            expired_row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            assert await ActionApprovalRepository(session).expire_due(limit=1) == 1
            assert expired_row.status == "expired"
            approved_approval = await ActionApprovalRepository(session).create(
                test_run_id=run_id,
                execution_id=execution_id,
                step_id=approval_step.id,
                requested_by_user_id=user_id,
                action={"operation": "archive", "record": "fixture-row-3"},
                resource={"target": str(target.id), "environment": "local"},
                environment="local",
                policy_version=1,
                action_summary="Archive a third synthetic fixture record",
                expires_at=datetime.now(UTC) + timedelta(minutes=1),
            )
            await ActionApprovalRepository(session).decide(
                approval_id=approved_approval.id, actor_id=user_id, approved=True,
            )
            approved_row = await session.get(ActionApprovalRequest, approved_approval.id)
            assert approved_row is not None
            approved_row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            assert await ActionApprovalRepository(session).expire_due(limit=1) == 1
            assert approved_row.status == "expired"

        async with factory() as session:
            fixture_step = ExecutionStep(
                execution_id=execution_id,
                step_number=2,
                action_type="registration_submit",
                action_summary="Submit the synthetic local registration fixture.",
                status="completed",
            )
            session.add(fixture_step)
            await session.flush()
            fixture_approval_id = await FixtureActionApproval(session).create(
                run_id=run_id,
                execution_id=execution_id,
                step_id=fixture_step.id,
                owner_id=user_id,
                environment="local",
            )

        async with factory() as worker_session:
            approval_service = FixtureActionApproval(worker_session)
            wait_task = asyncio.create_task(
                approval_service.wait(approval_id=fixture_approval_id, timeout_seconds=3)
            )
            await asyncio.sleep(0.3)
            async with factory.begin() as api_session:
                await ActionApprovalRepository(api_session).decide(
                    approval_id=fixture_approval_id,
                    actor_id=user_id,
                    approved=True,
                )
            await wait_task
            await approval_service.consume(
                approval_id=fixture_approval_id,
                environment="local",
            )
            with pytest.raises(FixtureApprovalRejected):
                await approval_service.consume(
                    approval_id=fixture_approval_id,
                    environment="local",
                )
        async with factory() as session:
            fixture_receipt = await session.get(ActionApprovalReceipt, fixture_approval_id)
            assert fixture_receipt is not None
            assert fixture_receipt.dispatch_state == "claimed"

        # General approval dispatch uses the same session binding in a separate
        # worker transaction, while the owner decides in the API transaction.
        from markettwin_execution_orchestrator.browser.sensitive_action_policy import classify_click_action
        from markettwin_execution_orchestrator.persistence.sensitive_action_approval import (
            SensitiveActionApproval, SensitiveActionApprovalBlocked,
        )
        from markettwin_execution_orchestrator.worker import abandon_run_handoffs
        async with factory.begin() as session:
            general_run = await session.get(RunModel, run_id)
            assert general_run is not None
            general_run.human_action_approvals_enabled = True
            general_run.configuration_snapshot = {"sensitive_action_rules": [{
                "category": "save", "role": "button", "name": "Save",
                "resource_reference": "synthetic-record-v1", "test_data_reset_confirmed": True,
            }]}
            general_run.target_snapshot = {"allowed_origins": [
                {"scheme": "http", "hostname": "127.0.0.1", "port": None},
            ]}
            general_browser = await session.get(BrowserSession, browser_id)
            assert general_browser is not None
            general_browser.control_mode = "agent"
        intent = classify_click_action(role="button", name="Save", label=None, text=None,
                                       state_digest="synthetic-resource-v1")
        assert intent is not None

        async def origin() -> str:
            return "http://127.0.0.1"

        async def dispatch() -> object:
            async with factory() as session:
                return await SensitiveActionApproval(session, execution_id=execution_id).dispatch_authorized(
                    step_id=approval_step.id, intent=intent, current_origin=await origin(),
                    browser_session_id=browser_id, revalidate_origin=origin,
                )

        async def pending_general() -> UUID:
            async with asyncio.timeout(5):
                while True:
                    async with factory() as session:
                        row = await session.scalar(select(ActionApprovalRequest).where(
                            ActionApprovalRequest.execution_id == execution_id,
                            ActionApprovalRequest.policy_version == 2,
                            ActionApprovalRequest.status == "pending",
                        ))
                        if row is not None:
                            assert row.browser_session_id == browser_id
                            suspended_run = await session.get(RunModel, run_id)
                            assert suspended_run is not None and suspended_run.status == "awaiting_human"
                            return row.id
                    await asyncio.sleep(0.01)

        task = asyncio.create_task(dispatch())
        general_id = await pending_general()
        async with factory.begin() as session:
            await ActionApprovalRepository(session).decide(
                approval_id=general_id, actor_id=user_id, approved=True,
            )
        assert await asyncio.wait_for(task, 5) == general_id
        async with factory() as session:
            service = SensitiveActionApproval(session, execution_id=execution_id)
            await service.finish(approval_id=general_id, outcome="completed")
            generic = await session.get(ActionApprovalRequest, general_id)
            assert generic is not None and generic.status == "consumed"
            with pytest.raises(SensitiveActionApprovalBlocked):
                await service._consume(
                    approval_id=general_id, action_fingerprint=generic.action_fingerprint,
                    resource_fingerprint=generic.resource_fingerprint, environment="local",
                    authorization_id=uuid4(),
                )
            await session.rollback()

        task = asyncio.create_task(dispatch())
        stale_id = await pending_general()
        async with factory.begin() as session:
            await ActionApprovalRepository(session).decide(
                approval_id=stale_id, actor_id=user_id, approved=True,
            )
            general_browser = await session.get(BrowserSession, browser_id)
            assert general_browser is not None
            general_browser.control_generation += 1
        with pytest.raises(SensitiveActionApprovalBlocked):
            await asyncio.wait_for(task, 5)
        async with factory() as session:
            assert await session.get(ActionApprovalReceipt, stale_id) is None
            stale = await session.get(ActionApprovalRequest, stale_id)
            assert stale is not None and stale.status == "cancelled"

        task = asyncio.create_task(dispatch())
        interrupted_id = await pending_general()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with factory() as session:
            interrupted = await session.get(ActionApprovalRequest, interrupted_id)
            assert interrupted is not None and interrupted.status == "cancelled"
            resumed_run = await session.get(RunModel, run_id)
            assert resumed_run is not None and resumed_run.status == "running"
        # Restore generation to retain the original lease assertions below.
        async with factory.begin() as session:
            general_browser = await session.get(BrowserSession, browser_id)
            assert general_browser is not None
            general_browser.control_generation = 0

        async def claim() -> HumanLeaseGrant:
            async with factory.begin() as session:
                return await HumanActionRepository(session).claim(
                    request_id=request.request_id,
                    actor_id=user_id,
                )

        async with factory.begin() as session:
            with pytest.raises(HumanActionNotAuthorizedError):
                await HumanActionRepository(session).claim(
                    request_id=request.request_id,
                    actor_id=member_id,
                )
            with pytest.raises(HumanActionNotAuthorizedError):
                await HumanActionRepository(session).claim(
                    request_id=request.request_id, actor_id=uuid4(),
                )

        outcomes = await asyncio.gather(claim(), claim(), return_exceptions=True)
        grants = [outcome for outcome in outcomes if isinstance(outcome, HumanLeaseGrant)]
        rejected = [
            outcome for outcome in outcomes if isinstance(outcome, HumanActionConflictError)
        ]
        assert len(grants) == 1
        assert len(rejected) == 1
        grant = grants[0]
        assert grant.generation == 1

        async with factory.begin() as session:
            browser = await session.get(BrowserSession, browser_id)
            assert browser is not None
            browser.control_mode = "human"
            renewed_until = await HumanActionRepository(session).renew(
                lease_id=grant.lease_id,
                actor_id=user_id,
                lease_token=grant.lease_token,
                generation=grant.generation,
                lease_duration=timedelta(seconds=20),
            )
            assert request.expires_at is not None
            assert renewed_until <= request.expires_at
            assert await HumanActionRepository(session).validate_active_lease(
                lease_id=grant.lease_id, actor_id=user_id, generation=grant.generation,
            )
            assert not await HumanActionRepository(session).validate_active_lease(
                lease_id=grant.lease_id, actor_id=member_id, generation=grant.generation,
            )
            authorization = await session.scalar(select(TargetAuthorization))
            assert authorization is not None
            authorization.status = "revoked"
            authorization.revoked_at = datetime.now(UTC)
            await session.flush()
            assert not await HumanActionRepository(session).validate_active_lease(
                lease_id=grant.lease_id, actor_id=user_id, generation=grant.generation,
            )
            with pytest.raises(HumanActionNotAuthorizedError):
                await HumanActionRepository(session).renew(
                    lease_id=grant.lease_id, actor_id=user_id,
                    lease_token=grant.lease_token, generation=grant.generation,
                )
            authorization.status = "authorized"
            authorization.revoked_at = None
            await session.flush()

        async with factory.begin() as session:
            lease_count = await session.scalar(
                select(HumanControlLease.id).where(
                    HumanControlLease.browser_session_id == browser_id,
                    HumanControlLease.released_at.is_(None),
                )
            )
            assert lease_count == grant.lease_id
            lease = await session.get(HumanControlLease, grant.lease_id)
            assert lease is not None
            assert lease.lease_token_hash != grant.lease_token
            assert len(lease.lease_token_hash) == 64
            browser = await session.get(BrowserSession, browser_id)
            assert browser is not None
            assert browser.control_mode == "human"
            assert browser.control_generation == grant.generation
            with pytest.raises(HumanActionNotAuthorizedError):
                await HumanActionRepository(session).release_for_verification(
                    lease_id=grant.lease_id, actor_id=user_id,
                    lease_token=grant.lease_token, generation=grant.generation - 1,
                )

        async with factory.begin() as session:
            browser = await session.get(BrowserSession, browser_id)
            assert browser is not None
            browser.control_mode = "human"
            next_generation = await HumanActionRepository(session).release_for_verification(
                lease_id=grant.lease_id, actor_id=user_id,
                lease_token=grant.lease_token, generation=grant.generation,
            )
            assert next_generation == grant.generation + 1
            result = await HumanActionRepository(session).finish_verification(
                request_id=request.request_id, expected_generation=next_generation, verified=True,
            )
            assert result.status == "completed"
            assert not await HumanActionRepository(session).validate_active_lease(
                lease_id=grant.lease_id, actor_id=user_id, generation=grant.generation,
            )

        async with factory.begin() as session:
            failed_handoff = await HumanActionRepository(session).create_request(
                execution_id=execution_id,
                browser_session_id=browser_id,
                request_type="mfa",
                idempotency_key="auth-preflight:case-2",
                expires_at=datetime.now(UTC) + timedelta(minutes=2),
            )
            failed_grant = await HumanActionRepository(session).claim(
                request_id=failed_handoff.request_id, actor_id=user_id,
            )
            assert failed_grant.execution_id == execution_id
            assert failed_grant.journey_id == journey_id
            fence = await HumanActionRepository(session).abort_claim(
                lease_id=failed_grant.lease_id,
                actor_id=user_id,
                lease_token=failed_grant.lease_token,
                generation=failed_grant.generation,
                expected_request_id=failed_handoff.request_id,
            )
            assert fence == failed_grant.generation + 1
            restored = await session.get(BrowserSession, browser_id)
            assert restored is not None and restored.control_mode == "agent"
            restored_request = await session.get(HumanActionRequest, failed_handoff.request_id)
            assert restored_request is not None and restored_request.status == "pending"

        async with factory.begin() as session:
            repository = HumanActionRepository(session)
            cancel_request = await repository.create_request(
                execution_id=execution_id,
                browser_session_id=browser_id,
                request_type="password",
                idempotency_key="auth-preflight:case-2",
                expires_at=datetime.now(UTC) + timedelta(minutes=2),
            )
            cancelled = await repository.cancel(
                request_id=cancel_request.request_id,
                actor_id=user_id,
            )
            assert cancelled.status == "cancelled"
            expiring_request = await repository.create_request(
                execution_id=execution_id,
                browser_session_id=browser_id,
                request_type="mfa",
                idempotency_key="auth-preflight:case-3",
                expires_at=datetime.now(UTC) + timedelta(milliseconds=200),
            )

        await asyncio.sleep(0.25)
        async with factory.begin() as session:
            assert await HumanActionRepository(session).expire_due() == 1
        async with factory.begin() as session:
            expired = await session.get(HumanActionRequest, expiring_request.request_id)
            assert expired is not None
            assert expired.status == "expired"

        async with factory.begin() as session:
            await abandon_run_handoffs(session, test_run_id=run_id)
        async with factory() as session:
            fixture_receipt = await session.get(ActionApprovalReceipt, fixture_approval_id)
            assert fixture_receipt is not None and fixture_receipt.dispatch_state == "uncertain"
            lost_browser = await session.get(BrowserSession, browser_id)
            assert lost_browser is not None and lost_browser.control_mode == "none"

    finally:
        async with engine.begin() as connection:
            for schema in reversed(tuple(schemas.values())):
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
