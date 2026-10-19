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
    HumanActionExpiredError,
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
    ExecutionPauseRequest,
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
        ExecutionPauseRequest,
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
async def test_claim_is_exclusive_and_generation_fences_stale_input(monkeypatch, tmp_path) -> None:
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
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from markettwin_control_api.api import human_actions
        from markettwin_execution_orchestrator.browser.sensitive_action_policy import (
            classify_click_action,
        )
        from markettwin_execution_orchestrator.persistence.sensitive_action_approval import (
            SensitiveActionApproval,
            SensitiveActionApprovalBlocked,
        )
        from markettwin_execution_orchestrator.worker import abandon_run_handoffs
        from starlette.requests import Request as StarletteRequest
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
                return await SensitiveActionApproval(
                    session, execution_id=execution_id
                ).dispatch_authorized(
                    step_id=approval_step.id,
                    intent=intent,
                    current_origin=await origin(),
                    browser_session_id=browser_id,
                    revalidate_origin=origin,
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
                            assert (
                                suspended_run is not None
                                and suspended_run.status == "awaiting_human"
                            )
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

        rejected_dispatches: list[UUID] = []

        async def dispatch_with_spy() -> UUID:
            approved_id = await dispatch()
            # This is the dispatch boundary: the spy is called only when the
            # worker has committed an exact approval receipt.
            rejected_dispatches.append(approved_id)
            return approved_id

        rejected_task = asyncio.create_task(dispatch_with_spy())
        rejected_id = await pending_general()
        async with factory.begin() as session:
            rejected_decision = await ActionApprovalRepository(session).decide(
                approval_id=rejected_id, actor_id=user_id, approved=False,
            )
            assert rejected_decision.status == "rejected"
        with pytest.raises(SensitiveActionApprovalBlocked):
            await asyncio.wait_for(rejected_task, 5)
        async with factory() as session:
            rejected_row = await session.get(ActionApprovalRequest, rejected_id)
            assert rejected_row is not None and rejected_row.status == "rejected"
            assert await session.get(ActionApprovalReceipt, rejected_id) is None
            rejected_suspension = await session.scalar(select(ExecutionSuspension).where(
                ExecutionSuspension.pending_approval_id == rejected_id,
            ))
            assert rejected_suspension is not None
            assert rejected_suspension.status == "abandoned"
            rejected_run = await session.get(RunModel, run_id)
            assert rejected_run is not None and rejected_run.status == "running"
        assert rejected_dispatches == []

        concurrent_task = asyncio.create_task(dispatch())
        concurrent_id = await pending_general()
        async with factory.begin() as session:
            await ActionApprovalRepository(session).decide(
                approval_id=concurrent_id, actor_id=user_id, approved=True,
            )
        assert await asyncio.wait_for(concurrent_task, 5) == concurrent_id
        # Put the committed request back at the exact approved checkpoint to
        # race two independent workers at the receipt-consumption boundary.
        async with factory.begin() as session:
            concurrent_row = await session.get(ActionApprovalRequest, concurrent_id)
            assert concurrent_row is not None
            concurrent_row.status = "approved"
            receipt = await session.get(ActionApprovalReceipt, concurrent_id)
            assert receipt is not None
            await session.delete(receipt)
            suspension = await session.scalar(select(ExecutionSuspension).where(
                ExecutionSuspension.pending_approval_id == concurrent_id,
            ))
            assert suspension is not None
            suspension.status = "waiting"
            suspended_run = await session.get(RunModel, run_id)
            assert suspended_run is not None
            suspended_run.status = "awaiting_human"
        async with factory() as session:
            concurrent_row = await session.get(ActionApprovalRequest, concurrent_id)
            assert concurrent_row is not None
            expected_action = concurrent_row.action_fingerprint
            expected_resource = concurrent_row.resource_fingerprint
            expected_environment = concurrent_row.environment
            authorization = await session.scalar(
                select(TargetAuthorization).where(TargetAuthorization.target_id == target.id)
            )
            assert authorization is not None
            expected_authorization = authorization.id
        rejected_dispatches.clear()

        async def exact_consume() -> UUID:
            async with factory() as session:
                consumed_id = await SensitiveActionApproval(
                    session, execution_id=execution_id,
                )._consume(
                    approval_id=concurrent_id,
                    action_fingerprint=expected_action,
                    resource_fingerprint=expected_resource,
                    environment=expected_environment,
                    authorization_id=expected_authorization,
                )
                # Model the protected dispatch callback after the receipt has
                # been acquired by this exact-consumption path.
                rejected_dispatches.append(consumed_id)
                return consumed_id

        concurrent_results = await asyncio.wait_for(asyncio.gather(
            exact_consume(), exact_consume(), return_exceptions=True,
        ), 5)
        assert sum(result == concurrent_id for result in concurrent_results) == 1
        assert sum(isinstance(result, SensitiveActionApprovalBlocked)
                   for result in concurrent_results) == 1
        assert rejected_dispatches == [concurrent_id]
        async with factory() as session:
            concurrent_receipt = await session.get(ActionApprovalReceipt, concurrent_id)
            assert concurrent_receipt is not None
            assert concurrent_receipt.dispatch_state == "claimed"
            concurrent_row = await session.get(ActionApprovalRequest, concurrent_id)
            assert concurrent_row is not None and concurrent_row.status == "consumed"
            await session.rollback()

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
            reclaimed_grant = await HumanActionRepository(session).claim(
                request_id=failed_handoff.request_id, actor_id=user_id,
            )
        monkeypatch.setattr(
            human_actions, "get_authenticated_user_id", AsyncMock(return_value=user_id),
        )
        monkeypatch.setattr(
            human_actions, "get_database_runtime",
            lambda _: SimpleNamespace(session_factory=factory),
        )
        list_request = StarletteRequest({"type": "http", "headers": []})
        listed_actions = await human_actions.list_human_actions(
            test_run_id=run_id, request=list_request,
        )
        reclaimed_rows = [
            item for item in listed_actions if item.id == failed_handoff.request_id
        ]
        assert len(reclaimed_rows) == 1
        assert reclaimed_rows[0].lease_id == reclaimed_grant.lease_id
        assert reclaimed_rows[0].journey_id is not None
        assert reclaimed_rows[0].journey_title
        assert reclaimed_rows[0].requesting_agent
        assert reclaimed_rows[0].browser_state == "open"
        assert reclaimed_grant.lease_token not in reclaimed_rows[0].model_dump_json()
        async with factory.begin() as session:
            await HumanActionRepository(session).abort_claim(
                lease_id=reclaimed_grant.lease_id,
                actor_id=user_id,
                lease_token=reclaimed_grant.lease_token,
                generation=reclaimed_grant.generation,
                expected_request_id=failed_handoff.request_id,
            )

        # Skip is durable and exclusive, fences control once, and is not cancellation.
        for leased in (False, True):
            async with factory.begin() as session:
                repository = HumanActionRepository(session)
                current_browser = await session.get(BrowserSession, browser_id)
                assert current_browser is not None
                # Each independent work item publishes a fresh waiting browser state.
                current_browser.control_mode = "human_pending"
                skipped_request = await repository.create_request(
                    execution_id=execution_id, browser_session_id=browser_id,
                    request_type="login", idempotency_key=f"skip:{leased}",
                    expires_at=datetime.now(UTC) + timedelta(minutes=2),
                )
                if leased:
                    skip_grant = await repository.claim(
                        request_id=skipped_request.request_id, actor_id=user_id,
                    )
                initial_generation = current_browser.control_generation
                suspension_id = uuid4()
                session.add(ExecutionSuspension(
                    id=suspension_id, test_run_id=run_id, journey_id=journey_id,
                    execution_id=execution_id, browser_session_id=browser_id,
                    pending_request_id=skipped_request.request_id,
                    checkpoint_version=100 + int(leased),
                    owner_generation=initial_generation, phase="case_action",
                    planned_step_index=0, active_deadline_remaining_ms=1000,
                    suspended_at=datetime.now(UTC),
                    human_deadline=datetime.now(UTC) + timedelta(minutes=2), status="waiting",
                ))
                await session.flush()
                with pytest.raises(HumanActionNotAuthorizedError):
                    await repository.skip(
                        request_id=skipped_request.request_id, actor_id=member_id,
                    )
                skipped = await repository.skip(
                    request_id=skipped_request.request_id, actor_id=user_id,
                )
                assert skipped.status == "skipped"
                assert current_browser.control_mode == "none"
                assert current_browser.control_generation == initial_generation + 1
                again = await repository.skip(
                    request_id=skipped_request.request_id, actor_id=user_id,
                )
                assert again.status == "skipped"
                assert current_browser.control_generation == initial_generation + 1
                assert again.terminal_generation == initial_generation + 1
                # A delayed duplicate must retain the old fence, never adopt a later
                # independent work item's browser generation for its notification.
                current_browser.control_generation += 3
                await session.flush()
                delayed = await repository.skip(
                    request_id=skipped_request.request_id, actor_id=user_id,
                )
                assert delayed.terminal_generation == initial_generation + 1
                assert current_browser.control_generation == initial_generation + 4
                with pytest.raises(HumanActionConflictError):
                    await repository.claim(
                        request_id=skipped_request.request_id, actor_id=user_id,
                    )
                if leased:
                    old_lease = await session.get(HumanControlLease, skip_grant.lease_id)
                    assert old_lease is not None and old_lease.released_at is not None
            async with factory() as session:
                persisted = await session.get(HumanActionRequest, skipped_request.request_id)
                assert persisted is not None and persisted.status == "skipped"
                enclosing_run = await session.get(RunModel, run_id)
                assert enclosing_run is not None and enclosing_run.status != "cancelled"
                persisted_suspension = await session.get(ExecutionSuspension, suspension_id)
                assert persisted_suspension is not None
                assert persisted_suspension.status == "abandoned"

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
            with pytest.raises(HumanActionExpiredError):
                await HumanActionRepository(session).skip(
                    request_id=expiring_request.request_id, actor_id=user_id,
                )
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

        await _exercise_viewer_release_lifecycle(
            factory, user_id, run_id, execution_id, monkeypatch, tmp_path,
        )

    finally:
        async with engine.begin() as connection:
            for schema in reversed(tuple(schemas.values())):
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()


async def _exercise_viewer_release_lifecycle(
    factory, user_id, run_id, execution_id, monkeypatch, tmp_path
):
    """Real PG + signed API/worker + live Playwright + local WebSocket regressions."""
    import json
    import socket
    import threading
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import httpx
    from fastapi import HTTPException
    from markettwin_control_api.api import human_actions
    from markettwin_control_api.config import Settings
    from markettwin_control_api.services.hitl_worker_client import HitlWorkerClient
    from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
    from markettwin_execution_orchestrator.browser.owner import OwnerLease
    from markettwin_execution_orchestrator.browser.owner_registry import BrowserOwnerRegistry
    from markettwin_execution_orchestrator.browser.owner_service import HITLWorkerService
    from markettwin_shared.auth_verification import AuthVerificationPolicy
    from pydantic import SecretStr
    from starlette.requests import Request
    from websockets.asyncio.client import connect

    fixture = Path(__file__).parents[2] / "execution-orchestrator/tests/fixtures/hitl_app"
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(fixture))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    registry = BrowserOwnerRegistry()
    detached_events: dict[UUID, asyncio.Event] = {}
    original_detach = registry.detach

    async def record_detach(lease: OwnerLease) -> None:
        await original_detach(lease)
        detached_events[lease.handle.session_id].set()

    monkeypatch.setattr(registry, "detach", record_detach)
    secret = "synthetic-integration-secret-for-local-hitl-only-012345"
    service = HITLWorkerService(session_factory=factory, registry=registry, internal_secret=secret,
        allowed_origins=frozenset({"http://localhost:5173"}),
        viewer_url="ws://localhost:5173/api/v1/hitl-viewer", allow_local_ws=True)
    # The request identity is synthetic; all lease/role/target/generation checks use PG.
    async def actor(cookie):
        return user_id if cookie == "synthetic-session" else None
    monkeypatch.setattr(service._authority, "actor", actor)
    bridge = HitlWorkerClient(base_url="http://worker", secret=SecretStr(secret),
        transport=httpx.ASGITransport(app=service.app))
    monkeypatch.setattr(human_actions, "_worker_client", lambda: bridge)
    monkeypatch.setattr(human_actions, "get_authenticated_user_id", AsyncMock(return_value=user_id))
    monkeypatch.setattr(
        human_actions, "get_database_runtime", lambda _: SimpleNamespace(session_factory=factory)
    )
    monkeypatch.setattr(human_actions, "get_settings", lambda: Settings(app_env="local", web_origin="http://localhost:5173"))
    request = Request(
        {
            "type": "http",
            "headers": [(b"origin", b"http://localhost:5173"), (b"x-markettwin-request", b"1")],
        }
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    await service.start(host="127.0.0.1", port=port, cert_file=None, key_file=None)
    url = f"ws://127.0.0.1:{port}/api/v1/hitl-viewer"
    try:
        async with BrowserController(artifact_root=tmp_path / "integration") as controller:
            for ordinal, scenario in enumerate(
                ("disconnect", "active", "reconnect", "expired", "delivery_retry"), start=10
            ):
                journey_id = await _journey(factory, execution_id)
                scenario_execution_id = uuid4()
                async with factory.begin() as session:
                    session.add(
                        AgentExecution(
                            id=scenario_execution_id,
                            journey_id=journey_id,
                            attempt_number=ordinal,
                            status="running",
                            runtime_name="hitl-integration-regression",
                        )
                    )
                handle = await controller.create_session(
                    execution_id=scenario_execution_id,
                    journey_id=journey_id,
                    allowed_origins=(AllowedOrigin("http", "127.0.0.1", server.server_port),),
                    network_policy="local_development",
                    authenticated_session=True,
                )
                detached_events[handle.session_id] = asyncio.Event()
                registry.register(controller, handle)
                await controller.navigate(
                    session_id=handle.session_id, url=origin + "/index.html?view=login"
                )
                live = controller._get_session(session_id=handle.session_id)
                context = live.context
                async with factory.begin() as session:
                    session.add(
                        BrowserSession(
                            id=handle.session_id,
                            execution_id=scenario_execution_id,
                            state="open",
                            control_mode="agent",
                            control_generation=0,
                        )
                    )
                    await session.flush()
                    action = await HumanActionRepository(session).create_request(
                        execution_id=scenario_execution_id,
                        browser_session_id=handle.session_id,
                        request_type="login",
                        idempotency_key=f"race-{scenario}",
                        expires_at=datetime.now(UTC) + timedelta(minutes=2),
                    )
                claim = await human_actions.claim_human_action(
                    action.request_id, human_actions.ClaimRequest(), request
                )
                lease_body = human_actions.LeaseRequest(
                    lease_id=claim.lease_id,
                    lease_token=claim.lease_token,
                    generation=claim.generation,
                )
                websocket = await connect(
                    url,
                    origin="http://localhost:5173",
                    additional_headers={"Cookie": "markettwin_session=synthetic-session"},
                )
                await websocket.send(json.dumps({"ticket": claim.viewer_ticket}))
                assert isinstance(await websocket.recv(), bytes), scenario
                assert live.control_generation == claim.generation
                await live.page.evaluate("sessionStorage.setItem('fixture-role','user')")
                await live.page.goto(origin + "/index.html?view=dashboard")
                waiter = asyncio.create_task(service.wait_for_revoke(action.request_id, 5))
                if scenario != "active":
                    await websocket.close()
                    await asyncio.wait_for(detached_events[handle.session_id].wait(), 2)
                    assert handle.session_id not in service._gateway._connected
                    assert live.control_generation == claim.generation, scenario
                    assert live.control_mode == "human"
                if scenario == "reconnect":
                    refresh = await human_actions.reconnect_human_action(
                        action.request_id, lease_body, request
                    )
                    assert refresh.viewer_ticket != claim.viewer_ticket
                    websocket = await connect(
                        url,
                        origin="http://localhost:5173",
                        additional_headers={"Cookie": "markettwin_session=synthetic-session"},
                    )
                    await websocket.send(json.dumps({"ticket": refresh.viewer_ticket}))
                    assert isinstance(await websocket.recv(), bytes)
                    await websocket.send(json.dumps({"sequence": 1, "event": "key", "key": "Tab"}))
                    while isinstance(response := await websocket.recv(), bytes):
                        pass
                    assert json.loads(response)["accepted_sequence"] == 1
                    assert live.context is context and live.control_generation == claim.generation
                if scenario == "expired":
                    async with factory.begin() as session:
                        expired = await session.get(HumanControlLease, claim.lease_id)
                        expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                    with pytest.raises(HTTPException):
                        await human_actions.reconnect_human_action(
                            action.request_id, lease_body, request
                        )
                    with pytest.raises(HTTPException):
                        await human_actions.release_human_action(
                            action.request_id, lease_body, request
                        )
                    assert not waiter.done()
                    async with factory.begin() as session:
                        await HumanActionRepository(session).expire_due()
                    claim = await human_actions.claim_human_action(
                        action.request_id, human_actions.ClaimRequest(), request
                    )
                    lease_body = human_actions.LeaseRequest(
                        lease_id=claim.lease_id,
                        lease_token=claim.lease_token,
                        generation=claim.generation,
                    )
                    assert claim.generation == 3
                notification = {
                    "request_id": str(action.request_id),
                    "lease_id": str(claim.lease_id),
                    "browser_session_id": str(handle.session_id),
                    "generation": claim.generation + 1,
                }
                with pytest.raises(RuntimeError):
                    await bridge.notify(path="/internal/hitl/leases/revoke", payload=notification)
                assert not waiter.done()  # uncommitted/forged generation cannot wake verification
                if scenario == "delivery_retry":
                    notify = bridge.notify
                    monkeypatch.setattr(
                        bridge, "notify", AsyncMock(side_effect=RuntimeError("unavailable"))
                    )
                    with pytest.raises(HTTPException) as error:
                        await human_actions.release_human_action(
                            action.request_id, lease_body, request
                        )
                    assert error.value.status_code == 503
                    assert not waiter.done()
                    monkeypatch.setattr(bridge, "notify", notify)
                result = await human_actions.release_human_action(
                    action.request_id, lease_body, request
                )
                await waiter
                assert result["generation"] == claim.generation + 1
                assert (
                    live.control_generation == result["generation"]
                    and live.control_mode == "verifying"
                )
                await bridge.notify(path="/internal/hitl/leases/revoke", payload=notification)
                assert not live.capture_enabled and not live.tracing_active
                policy = AuthVerificationPolicy(
                    origin=origin,
                    marker_selector="#identity",
                    expected_marker="Signed in as user",
                    role="user",
                    account_reference="fixture-user",
                )
                assert (
                    await controller.verify_authenticated_role(handle=handle, policy=policy)
                    is not None
                )
                async with factory.begin() as session:
                    await HumanActionRepository(session).finish_verification(
                        request_id=action.request_id,
                        expected_generation=result["generation"],
                        verified=True,
                    )
                await controller.end_human_control(
                    session_id=handle.session_id, verified=True, safe_to_capture=True
                )
                await bridge.notify(path="/internal/hitl/leases/revoke", payload=notification)
                assert (
                    live.control_mode == "agent"
                )  # late duplicate cannot re-fence a verified browser
                await websocket.close()
                registry.unregister(handle)
                await controller.close_session(session_id=handle.session_id)
    finally:
        await service.stop()
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=2)


async def _journey(factory, execution_id):
    async with factory() as session:
        return await session.scalar(
            select(AgentExecution.journey_id).where(AgentExecution.id == execution_id)
        )
