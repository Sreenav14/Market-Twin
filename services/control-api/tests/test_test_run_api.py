"""Regression tests for Test Run authorization gating."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Literal, cast
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Request
from markettwin_control_api.api import test_run as test_run_api
from markettwin_control_api.database import DatabaseRuntime
from markettwin_control_api.persistence.repositories import (
    AllowedOriginRecord,
    ApplicationRecord,
    TargetAuthorizationRecord,
    TargetRecord,
    TestRunRecord,
    WorkspaceAccess,
)
from markettwin_shared.auth_verification import AuthVerificationPolicy
from pydantic import ValidationError


@pytest.mark.parametrize("mode", ["required", "optional"])
def test_authentication_mode_requires_explicit_identity_policy(mode: str) -> None:
    with pytest.raises(ValidationError, match="approved identity verification policy"):
        test_run_api.CreateTestRunRequest.model_validate({
            "target_id": str(uuid4()), "study_brief": "Observe synthetic navigation",
            "auth_mode": mode,
        })


class AsyncContext:
    """Minimal async context manager used by the endpoint tests."""

    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> bool:
        return False


class FakeDatabaseSession:
    """Minimal database-session shape used by repository fakes."""

    def begin(self) -> AsyncContext:
        return AsyncContext(None)


class FakeApplicationRepository:
    def __init__(self, application: ApplicationRecord) -> None:
        self._application = application

    async def get_for_user(
        self,
        *,
        application_id: UUID,
        user_id: UUID,
    ) -> ApplicationRecord | None:
        return self._application


class FakeWorkspaceRepository:
    def __init__(self, workspace: WorkspaceAccess) -> None:
        self._workspace = workspace

    async def get_for_user(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
    ) -> WorkspaceAccess | None:
        return self._workspace


class FakeTargetRepository:
    def __init__(self, target: TargetRecord) -> None:
        self._target = target

    async def get_for_user(
        self,
        *,
        target_id: UUID,
        user_id: UUID,
    ) -> TargetRecord | None:
        return self._target


class FakeAuthorizationRepository:
    def __init__(
        self,
        authorization: TargetAuthorizationRecord | None,
    ) -> None:
        self._authorization = authorization

    async def get_active(
        self,
        *,
        target_id: UUID,
    ) -> TargetAuthorizationRecord | None:
        return self._authorization


class FakeTestRunRepository:
    def __init__(self, test_run: TestRunRecord) -> None:
        self._test_run = test_run
        self.create_arguments: dict[str, object] | None = None

    async def create(
        self,
        *,
        workspace_id: UUID,
        application_id: UUID,
        target_id: UUID,
        created_by_user_id: UUID,
        target_snapshot: dict[str, object],
        configuration_snapshot: dict[str, object],
        synthetic_fixture_approval_enabled: bool = False,
        human_action_approvals_enabled: bool = False,
    ) -> TestRunRecord:
        self.create_arguments = {
            "workspace_id": workspace_id,
            "application_id": application_id,
            "target_id": target_id,
            "created_by_user_id": created_by_user_id,
            "target_snapshot": target_snapshot,
            "configuration_snapshot": configuration_snapshot,
            "synthetic_fixture_approval_enabled": synthetic_fixture_approval_enabled,
            "human_action_approvals_enabled": human_action_approvals_enabled,
        }
        return self._test_run
    
    async def get_for_user(
    self,
    *,
    test_run_id: UUID,
    user_id: UUID,
    ) -> TestRunRecord | None:
        if self._test_run.test_run_id != test_run_id:
            return None

        return self._test_run


    async def queue_if_draft(
        self,
        *,
        test_run_id: UUID,
    ) -> TestRunRecord | None:
        if (
            self._test_run.test_run_id != test_run_id
            or self._test_run.status != "draft"
        ):
            return None

        self._test_run = replace(
            self._test_run,
            status="queued",
        )

        return self._test_run


def make_request() -> Request:
    """Create the minimal Starlette request required by the endpoint."""

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
        }
    )


def patch_common_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    user_id: UUID,
    application: ApplicationRecord,
    workspace: WorkspaceAccess,
    target: TargetRecord,
    authorization: TargetAuthorizationRecord | None,
    outbox_repository: FakeOutboxRepository | None = None,
    test_run_repository: FakeTestRunRepository | None = None,
) -> None:
    """Patch endpoint dependencies with deterministic repository fakes."""


    if outbox_repository is not None:
        def outbox_repository_factory(
            session: object,
        ) -> FakeOutboxRepository:
            return outbox_repository

        monkeypatch.setattr(
            test_run_api,
            "OutboxRepository",
            outbox_repository_factory,
        )

    def session_factory() -> AsyncContext:
        return AsyncContext(FakeDatabaseSession())

    database = SimpleNamespace(
        session_factory=session_factory,
    )

    async def authenticated_user_id(
        *,
        request: Request,
    ) -> UUID:
        return user_id

    def database_runtime(
        request: Request,
    ) -> DatabaseRuntime:
        return cast(DatabaseRuntime, database)

    def application_repository(
        session: object,
    ) -> FakeApplicationRepository:
        return FakeApplicationRepository(application)

    def workspace_repository(
        session: object,
    ) -> FakeWorkspaceRepository:
        return FakeWorkspaceRepository(workspace)

    def target_repository(
        session: object,
    ) -> FakeTargetRepository:
        return FakeTargetRepository(target)

    def authorization_repository(
        session: object,
    ) -> FakeAuthorizationRepository:
        return FakeAuthorizationRepository(authorization)

    monkeypatch.setattr(
        test_run_api,
        "get_authenticated_user_id",
        authenticated_user_id,
    )
    monkeypatch.setattr(
        test_run_api,
        "get_database_runtime",
        database_runtime,
    )
    monkeypatch.setattr(
        test_run_api,
        "ApplicationRepository",
        application_repository,
    )
    monkeypatch.setattr(
        test_run_api,
        "WorkspaceRepository",
        workspace_repository,
    )
    monkeypatch.setattr(
        test_run_api,
        "TargetRepository",
        target_repository,
    )
    monkeypatch.setattr(
        test_run_api,
        "TargetAuthorizationRepository",
        authorization_repository,
    )

    if test_run_repository is not None:
        def run_repository(
            session: object,
        ) -> FakeTestRunRepository:
            return test_run_repository

        monkeypatch.setattr(
            test_run_api,
            "TestRunRepository",
            run_repository,
        )


def make_records() -> tuple[
    UUID,
    ApplicationRecord,
    WorkspaceAccess,
    TargetRecord,
]:
    """Create a consistent workspace/application/target fixture."""

    user_id = uuid4()
    workspace_id = uuid4()
    application_id = uuid4()
    target_id = uuid4()

    application = ApplicationRecord(
        application_id=application_id,
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        name="Demo Store",
        description=None,
        status="active",
    )

    workspace = WorkspaceAccess(
        workspace_id=workspace_id,
        name="Demo Workspace",
        status="active",
        role="owner",
    )

    target = TargetRecord(
        target_id=target_id,
        application_id=application_id,
        name="Local Demo Store",
        environment="local",
        base_url="http://localhost:3000/",
        requires_auth=False,
        status="active",
        allowed_origins=(
            AllowedOriginRecord(
                scheme="http",
                hostname="localhost",
                port=3000,
                include_subdomains=False,
            ),
        ),
    )

    return user_id, application, workspace, target


@pytest.mark.asyncio
async def test_create_test_run_rejects_target_without_active_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An authorization record is mandatory before a Test Run is created."""

    user_id, application, workspace, target = make_records()

    patch_common_dependencies(
        monkeypatch,
        user_id=user_id,
        application=application,
        workspace=workspace,
        target=target,
        authorization=None,
    )

    payload = test_run_api.CreateTestRunRequest(
        target_id=target.target_id,
        study_brief=(
            "Evaluate the shopping and checkout experience."
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await test_run_api.create_test_run(
            application.application_id,
            payload,
            make_request(),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == (
        "Target is not currently authorized for testing."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("testing_depth", ["low", "medium", "high"])
@pytest.mark.parametrize("requires_auth", [False, True])
@pytest.mark.parametrize("mode", ["legacy_persona", "deep_feature_v1"])
async def test_create_test_run_snapshots_active_authorization(
    monkeypatch: pytest.MonkeyPatch,
    testing_depth: str,
    requires_auth: bool,
    mode: Literal["legacy_persona", "deep_feature_v1"],
) -> None:
    """Both modes start without upfront identity setup, including protected targets."""

    user_id, application, workspace, target = make_records()
    target = replace(target, requires_auth=requires_auth)
    now = datetime.now(UTC)
    authorization_id = uuid4()
    test_run_id = uuid4()

    authorization = TargetAuthorizationRecord(
        authorization_id=authorization_id,
        target_id=target.target_id,
        created_by_user_id=user_id,
        authorized_by_user_id=user_id,
        status="authorized",
        authorization_basis="Owned local application.",
        created_at=now,
        authorized_at=now,
        revoked_at=None,
        expires_at=None,
    )

    expected_configuration: dict[str, object] = {
        "runtime_human_assistance": True,
        "testing_depth": testing_depth,
        "study_brief": (
            "Evaluate the shopping and checkout experience."
        ),
        "authorization_id_at_creation": str(authorization_id),
    }
    if mode == "deep_feature_v1":
        expected_configuration["execution_mode"] = mode

    persisted_run = TestRunRecord(
        test_run_id=test_run_id,
        workspace_id=application.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        created_by_user_id=user_id,
        status="draft",
        target_snapshot=test_run_api.build_target_snapshot(target),
        configuration_snapshot=expected_configuration,
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )

    test_run_repository = FakeTestRunRepository(persisted_run)

    patch_common_dependencies(
        monkeypatch,
        user_id=user_id,
        application=application,
        workspace=workspace,
        target=target,
        authorization=authorization,
        test_run_repository=test_run_repository,
    )

    response = await test_run_api.create_test_run(
        application.application_id,
        test_run_api.CreateTestRunRequest(
            target_id=target.target_id,
            testing_depth=cast(Literal["low", "medium", "high"], testing_depth),
            execution_mode=mode,
            study_brief=(
                "Evaluate the shopping and checkout experience."
            ),
        ),
        make_request(),
    )

    assert response.status == "draft"
    assert response.configuration_snapshot == expected_configuration
    assert test_run_repository.create_arguments is not None
    assert (
        test_run_repository.create_arguments[
            "configuration_snapshot"
        ]
        == expected_configuration
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "requires_auth", "auth_mode"),
    [("deep_feature_v1", True, "required"), ("legacy_persona", True, "required"),
     ("deep_feature_v1", False, "optional"), ("legacy_persona", False, "optional")],
)
async def test_create_test_run_freezes_approved_auth_verification_policy(
    monkeypatch: pytest.MonkeyPatch,
    mode: str, requires_auth: bool, auth_mode: str,
) -> None:
    user_id, application, workspace, raw_target = make_records()
    target = replace(raw_target, requires_auth=requires_auth)
    now = datetime.now(UTC)
    authorization_id = uuid4()
    test_run_id = uuid4()
    authorization = TargetAuthorizationRecord(
        authorization_id=authorization_id,
        target_id=target.target_id,
        created_by_user_id=user_id,
        authorized_by_user_id=user_id,
        status="authorized",
        authorization_basis="Owned local authenticated application.",
        created_at=now,
        authorized_at=now,
        revoked_at=None,
        expires_at=None,
    )
    policy = AuthVerificationPolicy(
        origin="http://localhost:3000",
        marker_selector="[data-testid='signed-in-role']",
        expected_marker="member",
        role="member",
        account_reference="fixture-member-1",
    )
    config: dict[str, object] = {
        "runtime_human_assistance": True,
        "testing_depth": "medium",
        "study_brief": "Evaluate the shopping and checkout experience.",
        "authorization_id_at_creation": str(authorization_id),
        "auth_verification": policy.model_dump(mode="json"),
        "auth_mode": auth_mode,
    }
    if mode == "deep_feature_v1":
        config["execution_mode"] = mode
    persisted = TestRunRecord(
        test_run_id=test_run_id,
        workspace_id=application.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        created_by_user_id=user_id,
        status="draft",
        target_snapshot=test_run_api.build_target_snapshot(target),
        configuration_snapshot=config,
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )
    repository = FakeTestRunRepository(persisted)
    patch_common_dependencies(
        monkeypatch,
        user_id=user_id,
        application=application,
        workspace=workspace,
        target=target,
        authorization=authorization,
        test_run_repository=repository,
    )

    response = await test_run_api.create_test_run(
        application.application_id,
        test_run_api.CreateTestRunRequest(
            target_id=target.target_id,
            study_brief="Evaluate the shopping and checkout experience.",
            execution_mode=mode,
            auth_verification=policy,
            auth_mode=auth_mode,
        ),
        make_request(),
    )

    assert response.configuration_snapshot["auth_verification"] == policy.model_dump(
        mode="json"
    )
    assert repository.create_arguments is not None
    assert repository.create_arguments["configuration_snapshot"] == config


@pytest.mark.asyncio
async def test_create_test_run_rejects_auth_verification_outside_target_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, application, workspace, raw_target = make_records()
    target = replace(raw_target, requires_auth=True)
    now = datetime.now(UTC)
    authorization = TargetAuthorizationRecord(
        authorization_id=uuid4(),
        target_id=target.target_id,
        created_by_user_id=user_id,
        authorized_by_user_id=user_id,
        status="authorized",
        authorization_basis="Owned local authenticated application.",
        created_at=now,
        authorized_at=now,
        revoked_at=None,
        expires_at=None,
    )
    patch_common_dependencies(
        monkeypatch,
        user_id=user_id,
        application=application,
        workspace=workspace,
        target=target,
        authorization=authorization,
    )
    policy = AuthVerificationPolicy(
        origin="http://other.example.test",
        marker_selector="[data-testid='signed-in-role']",
        expected_marker="member",
        role="member",
        account_reference="fixture-member-1",
    )
    with pytest.raises(HTTPException) as error:
        await test_run_api.create_test_run(
            application.application_id,
            test_run_api.CreateTestRunRequest(
                target_id=target.target_id,
                study_brief="Evaluate the shopping and checkout experience.",
                execution_mode="deep_feature_v1",
                auth_verification=policy,
            ),
            make_request(),
        )
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_protected_target_cannot_downgrade_authentication_to_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, application, workspace, raw_target = make_records()
    target = replace(raw_target, requires_auth=True)
    now = datetime.now(UTC)
    authorization = TargetAuthorizationRecord(
        authorization_id=uuid4(),
        target_id=target.target_id,
        created_by_user_id=user_id,
        authorized_by_user_id=user_id,
        status="authorized",
        authorization_basis="Owned local authenticated application.",
        created_at=now,
        authorized_at=now,
        revoked_at=None,
        expires_at=None,
    )
    patch_common_dependencies(
        monkeypatch,
        user_id=user_id,
        application=application,
        workspace=workspace,
        target=target,
        authorization=authorization,
    )
    with pytest.raises(HTTPException) as error:
        await test_run_api.create_test_run(
            application.application_id,
            test_run_api.CreateTestRunRequest(
                target_id=target.target_id,
                study_brief="Evaluate the shopping and checkout experience.",
                auth_mode="optional",
                auth_verification=AuthVerificationPolicy(
                    origin="http://localhost:3000",
                    marker_selector="[data-testid='signed-in-role']",
                    expected_marker="member",
                    role="member",
                    account_reference="fixture-member-1",
                ),
            ),
            make_request(),
        )
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_legacy_opt_out_still_requires_protected_identity_policy(monkeypatch) -> None:
    user_id, application, workspace, raw_target = make_records()
    target = replace(raw_target, requires_auth=True)
    now = datetime.now(UTC)
    authorization = TargetAuthorizationRecord(
        authorization_id=uuid4(), target_id=target.target_id,
        created_by_user_id=user_id, authorized_by_user_id=user_id, status="authorized",
        authorization_basis="Owned synthetic application.", created_at=now,
        authorized_at=now, revoked_at=None, expires_at=None,
    )
    patch_common_dependencies(
        monkeypatch, user_id=user_id, application=application, workspace=workspace,
        target=target, authorization=authorization,
    )
    with pytest.raises(HTTPException) as error:
        await test_run_api.create_test_run(
            application.application_id,
            test_run_api.CreateTestRunRequest(
                target_id=target.target_id, study_brief="Check protected fixture.",
                runtime_human_assistance=False,
            ), make_request(),
        )
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_fixture_approval_opt_in_is_persisted_outside_config_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, application, workspace, target = make_records()
    now = datetime.now(UTC)
    authorization = TargetAuthorizationRecord(
        authorization_id=uuid4(),
        target_id=target.target_id,
        created_by_user_id=user_id,
        authorized_by_user_id=user_id,
        status="authorized",
        authorization_basis="Loopback synthetic test fixture.",
        created_at=now,
        authorized_at=now,
        revoked_at=None,
        expires_at=None,
    )
    persisted = TestRunRecord(
        test_run_id=uuid4(),
        workspace_id=workspace.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        created_by_user_id=user_id,
        status="draft",
        target_snapshot=test_run_api.build_target_snapshot(target),
        configuration_snapshot={"study_brief": "Test synthetic registration."},
        synthetic_fixture_approval_enabled=True,
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )
    repository = FakeTestRunRepository(persisted)
    patch_common_dependencies(
        monkeypatch,
        user_id=user_id,
        application=application,
        workspace=workspace,
        target=target,
        authorization=authorization,
        test_run_repository=repository,
    )
    response = await test_run_api.create_test_run(
        application.application_id,
        test_run_api.CreateTestRunRequest(
            target_id=target.target_id,
            study_brief="Test synthetic registration.",
            execution_mode="deep_feature_v1",
            synthetic_fixture_approval=True,
        ),
        make_request(),
    )
    assert repository.create_arguments is not None
    assert repository.create_arguments["synthetic_fixture_approval_enabled"] is True
    snapshot = repository.create_arguments["configuration_snapshot"]
    assert isinstance(snapshot, dict)
    assert "synthetic_fixture_approval" not in snapshot
    assert response.synthetic_fixture_approval_enabled is True


@pytest.mark.asyncio
async def test_general_action_approval_opt_in_is_persisted_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, application, workspace, target = make_records()
    now = datetime.now(UTC)
    authorization = TargetAuthorizationRecord(
        authorization_id=uuid4(),
        target_id=target.target_id,
        created_by_user_id=user_id,
        authorized_by_user_id=user_id,
        status="authorized",
        authorization_basis="Authorized synthetic test target.",
        created_at=now,
        authorized_at=now,
        revoked_at=None,
        expires_at=None,
    )
    persisted = TestRunRecord(
        test_run_id=uuid4(),
        workspace_id=workspace.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        created_by_user_id=user_id,
        status="draft",
        target_snapshot=test_run_api.build_target_snapshot(target),
        configuration_snapshot={"study_brief": "Test an authorized form."},
        human_action_approvals_enabled=True,
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )
    repository = FakeTestRunRepository(persisted)
    patch_common_dependencies(
        monkeypatch,
        user_id=user_id,
        application=application,
        workspace=workspace,
        target=target,
        authorization=authorization,
        test_run_repository=repository,
    )
    response = await test_run_api.create_test_run(
        application.application_id,
        test_run_api.CreateTestRunRequest(
            target_id=target.target_id,
            study_brief="Test an authorized form action.",
            execution_mode="deep_feature_v1",
            human_action_approvals=True,
        ),
        make_request(),
    )
    assert repository.create_arguments is not None
    assert repository.create_arguments["human_action_approvals_enabled"] is True
    assert repository.create_arguments["synthetic_fixture_approval_enabled"] is False
    assert response.human_action_approvals_enabled is True


@pytest.mark.asyncio
async def test_fixture_approval_rejects_remote_allowed_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, application, workspace, raw_target = make_records()
    target = replace(
        raw_target,
        allowed_origins=(
            AllowedOriginRecord(
                scheme="https",
                hostname="app.example.test",
                port=None,
                include_subdomains=False,
            ),
        ),
    )
    now = datetime.now(UTC)
    authorization = TargetAuthorizationRecord(
        authorization_id=uuid4(),
        target_id=target.target_id,
        created_by_user_id=user_id,
        authorized_by_user_id=user_id,
        status="authorized",
        authorization_basis="Authorized local target.",
        created_at=now,
        authorized_at=now,
        revoked_at=None,
        expires_at=None,
    )
    patch_common_dependencies(
        monkeypatch,
        user_id=user_id,
        application=application,
        workspace=workspace,
        target=target,
        authorization=authorization,
    )
    with pytest.raises(HTTPException) as error:
        await test_run_api.create_test_run(
            application.application_id,
            test_run_api.CreateTestRunRequest(
                target_id=target.target_id,
                study_brief="Test synthetic registration.",
                execution_mode="deep_feature_v1",
                synthetic_fixture_approval=True,
            ),
            make_request(),
        )
    assert error.value.status_code == 422
class FakeOutboxRepository:
    def __init__(self) -> None:
        self.messages: list[
            dict[str, object]
        ] = []

    async def add(
        self,
        *,
        aggregate_type: str,
        aggregate_id: UUID,
        event_type: str,
        topic: str,
        message_key: str | None,
        payload: dict[str, object],
        headers: dict[str, object] | None = None,
    ) -> object:
        self.messages.append(
            {
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "event_type": event_type,
                "topic": topic,
                "message_key": message_key,
                "payload": payload,
                "headers": headers,
            }
        )

        return object()
    
@pytest.mark.asyncio
async def test_start_test_run_dispatches_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Starting the same TestRun twice must create one dispatch only."""

    user_id, application, workspace, target = make_records()
    now = datetime.now(UTC)

    authorization = TargetAuthorizationRecord(
        authorization_id=uuid4(),
        target_id=target.target_id,
        created_by_user_id=user_id,
        authorized_by_user_id=user_id,
        status="authorized",
        authorization_basis="Owned local application.",
        created_at=now,
        authorized_at=now,
        revoked_at=None,
        expires_at=None,
    )

    persisted_run = TestRunRecord(
        test_run_id=uuid4(),
        workspace_id=application.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        created_by_user_id=user_id,
        status="draft",
        target_snapshot={},
        configuration_snapshot={
            "study_brief": "Evaluate the application.",
        },
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )

    run_repository = FakeTestRunRepository(
        persisted_run
    )
    outbox_repository = FakeOutboxRepository()

    patch_common_dependencies(
        monkeypatch,
        user_id=user_id,
        application=application,
        workspace=workspace,
        target=target,
        authorization=authorization,
        test_run_repository=run_repository,
        outbox_repository=outbox_repository,
    )

    first_response = await test_run_api.start_test_run(
        persisted_run.test_run_id,
        make_request(),
    )

    assert first_response.status == "queued"

    assert len(
        outbox_repository.messages
    ) == 1

    message = outbox_repository.messages[0]

    assert message["aggregate_type"] == "test_run"
    assert (
        message["aggregate_id"]
        == persisted_run.test_run_id
    )
    assert message["event_type"] == "run.requested"
    assert message["topic"] == "markettwin.execution.commands"
    assert (
        message["message_key"]
        == str(persisted_run.test_run_id)
    )

    with pytest.raises(HTTPException) as exc_info:
        await test_run_api.start_test_run(
            persisted_run.test_run_id,
            make_request(),
        )

    assert exc_info.value.status_code == 409

    assert len(
        outbox_repository.messages
    ) == 1
    
@pytest.mark.asyncio
async def test_start_test_run_rejects_revoked_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run cannot start after target authorization is lost."""

    user_id, application, workspace, target = make_records()
    now = datetime.now(UTC)

    persisted_run = TestRunRecord(
        test_run_id=uuid4(),
        workspace_id=application.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        created_by_user_id=user_id,
        status="draft",
        target_snapshot={},
        configuration_snapshot={
            "study_brief": "Evaluate the application.",
        },
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )

    run_repository = FakeTestRunRepository(
        persisted_run
    )
    outbox_repository = FakeOutboxRepository()

    patch_common_dependencies(
        monkeypatch,
        user_id=user_id,
        application=application,
        workspace=workspace,
        target=target,

        # get_active() returns None for revoked/expired auth.
        authorization=None,

        test_run_repository=run_repository,
        outbox_repository=outbox_repository,
    )

    with pytest.raises(HTTPException) as exc_info:
        await test_run_api.start_test_run(
            persisted_run.test_run_id,
            make_request(),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == (
        "Target is not currently authorized for testing."
    )

    assert len(
        outbox_repository.messages
    ) == 0
