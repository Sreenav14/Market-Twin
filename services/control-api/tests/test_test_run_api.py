"""Regression tests for Test Run authorization gating."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Literal, cast
from unittest.mock import AsyncMock, Mock
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
from markettwin_control_api.services import run_readiness
from markettwin_shared.auth_verification import AuthVerificationPolicy
from pydantic import ValidationError


def test_new_runs_default_to_explore_test() -> None:
    # U-P8: the default kind is explore_test; no legacy mode is set.
    request = test_run_api.CreateTestRunRequest(
        target_id=uuid4(), study_brief="Check the storefront.",
    )
    assert request.run_kind is None


@pytest.mark.parametrize(
    ("mode", "kind"),
    [
        ("legacy_persona", "persona"),
        ("deep_feature_v1", "explore_test"),
        ("discovery_contract_v1", "explore_test"),
        ("harness_v1", "explore_test"),
    ],
)
def test_legacy_modes_translate_to_unified_kinds(mode: str, kind: str) -> None:
    from markettwin_shared.run_kind import translate_execution_mode

    assert translate_execution_mode(mode) == kind


def test_create_request_accepts_an_explicit_run_kind() -> None:
    request = test_run_api.CreateTestRunRequest(
        target_id=uuid4(), study_brief="Check the look.", run_kind="slop",
    )
    assert request.run_kind == "slop"


@pytest.mark.parametrize("brief", [None, "", "   ", "Set up an account"])
def test_ui_audit_uses_fixed_scope_without_a_prompt(brief):
    from markettwin_shared.run_kind import UI_AUDIT_OBJECTIVE

    payload = {"target_id": uuid4(), "run_kind": "slop"}
    if brief is not None:
        payload["study_brief"] = brief
    assert test_run_api.CreateTestRunRequest.model_validate(payload).study_brief == UI_AUDIT_OBJECTIVE


@pytest.mark.parametrize("kind", [None, "explore_test", "persona"])
@pytest.mark.parametrize("brief", ["", "short", "          "])
def test_task_runs_still_require_a_meaningful_prompt(kind, brief):
    with pytest.raises(ValidationError, match="at least 10"):
        test_run_api.CreateTestRunRequest(target_id=uuid4(), run_kind=kind, study_brief=brief)


@pytest.mark.parametrize("mode", ["legacy_persona", "deep_feature_v1", "discovery_contract_v1"])
def test_create_rejects_the_retired_execution_mode_alias(
    mode: Literal["legacy_persona", "deep_feature_v1", "discovery_contract_v1"],
) -> None:
    """U-P8: sending execution_mode is a validation error (422)."""

    with pytest.raises(ValidationError, match="run_kind instead"):
        test_run_api.CreateTestRunRequest(
            target_id=uuid4(), study_brief="Check the storefront.", execution_mode=mode,
        )


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


class EmptyQueryResult:
    """Empty result for direct session queries the repository fakes ignore."""

    def scalars(self) -> "EmptyQueryResult":
        return self

    def first(self) -> None:
        return None

    def all(self) -> list:
        return []


class FakeDatabaseSession:
    """Minimal database-session shape used by repository fakes."""

    def begin(self) -> AsyncContext:
        return AsyncContext(None)

    async def execute(self, statement) -> EmptyQueryResult:
        return EmptyQueryResult()

    async def scalar(self, statement) -> None:
        return None

    async def scalars(self, statement) -> EmptyQueryResult:
        return EmptyQueryResult()


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
    def __init__(
        self, test_run: TestRunRecord,
    ) -> None:
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
        run_kind: str | None = None,
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
            "run_kind": run_kind,
        }
        return self._test_run
    
    async def get_for_user(
    self,
    *,
    test_run_id: UUID,
    user_id: UUID,
    ) -> TestRunRecord | None:
        if self._test_run.test_run_id == test_run_id:
            return self._test_run
        return None

    async def update_configuration_snapshot(
        self, *, test_run_id: UUID, configuration_snapshot: dict[str, object],
    ) -> None:
        if self._test_run.test_run_id == test_run_id:
            self._test_run = replace(
                self._test_run, configuration_snapshot=configuration_snapshot,
            )


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
async def test_create_test_run_snapshots_active_authorization(
    monkeypatch: pytest.MonkeyPatch,
    testing_depth: str,
    requires_auth: bool,
) -> None:
    """Runs start without upfront identity setup, including protected targets."""

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
        "allow_offsite_navigation": False,
        "testing_depth": testing_depth,
        "study_brief": (
            "Evaluate the shopping and checkout experience."
        ),
        "authorization_id_at_creation": str(authorization_id),
        "harness_run_mode": "read_only",
    }
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
            study_brief=(
                "Evaluate the shopping and checkout experience."
            ),
        ),
        make_request(),
    )

    assert response.status == "draft"
    assert response.configuration_snapshot == expected_configuration
    assert response.created_at == now
    assert test_run_repository.create_arguments is not None
    assert (
        test_run_repository.create_arguments[
            "configuration_snapshot"
        ]
        == expected_configuration
    )


@pytest.mark.asyncio
async def test_create_test_run_with_run_kind_only_is_unified_native(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U-P1-06: run_kind without an explicit legacy mode writes no
    execution_mode into the snapshot, and the kind goes to the column."""

    user_id, application, workspace, target = make_records()
    now = datetime.now(UTC)
    authorization_id = uuid4()
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
    persisted_run = TestRunRecord(
        test_run_id=uuid4(),
        workspace_id=application.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        created_by_user_id=user_id,
        status="draft",
        target_snapshot=test_run_api.build_target_snapshot(target),
        configuration_snapshot={},
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
        run_kind="explore_test",
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
            study_brief="Explore and test everything.",
            run_kind="explore_test",
        ),
        make_request(),
    )
    assert response.run_kind == "explore_test"
    assert test_run_repository.create_arguments is not None
    assert test_run_repository.create_arguments["run_kind"] == "explore_test"
    snapshot = test_run_repository.create_arguments["configuration_snapshot"]
    assert isinstance(snapshot, dict)
    assert "execution_mode" not in snapshot


@pytest.mark.asyncio
async def test_create_rejects_frozen_contract_replay() -> None:
    """U-P8: frozen-contract replay was retired with the legacy
    engines; asking for it is a validation error (422)."""

    with pytest.raises(ValidationError, match="replay was retired"):
        test_run_api.CreateTestRunRequest(
            target_id=uuid4(),
            frozen_contract_source_run_id=uuid4(),
            study_brief="Replay the previously approved fixture contract.",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requires_auth", "auth_mode"),
    [(True, "required"), (False, "optional")],
)
async def test_create_test_run_freezes_approved_auth_verification_policy(
    monkeypatch: pytest.MonkeyPatch,
    requires_auth: bool, auth_mode: str,
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
        "allow_offsite_navigation": False,
        "testing_depth": "medium",
        "study_brief": "Evaluate the shopping and checkout experience.",
        "authorization_id_at_creation": str(authorization_id),
        "auth_verification": policy.model_dump(mode="json"),
        "auth_mode": auth_mode,
        "harness_run_mode": "read_only",
    }
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
async def test_generic_start_rejects_frozen_contract_replay_without_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, application, workspace, target = make_records()
    now = datetime.now(UTC)
    persisted_run = TestRunRecord(
        test_run_id=uuid4(),
        workspace_id=workspace.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        created_by_user_id=user_id,
        status="draft",
        target_snapshot=test_run_api.build_target_snapshot(target),
        configuration_snapshot={
            "execution_mode": "discovery_contract_v1",
            "frozen_contract_source_run_id": str(uuid4()),
            "frozen_contract_source_hash": "a" * 64,
            "test_contract": {"status": "approved"},
        },
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )
    run_repository = FakeTestRunRepository(persisted_run)
    outbox = FakeOutboxRepository()
    ready = AsyncMock()
    monkeypatch.setattr(test_run_api, "require_run_ready", ready)
    patch_common_dependencies(
        monkeypatch,
        user_id=user_id,
        application=application,
        workspace=workspace,
        target=target,
        authorization=None,
        outbox_repository=outbox,
        test_run_repository=run_repository,
    )

    with pytest.raises(HTTPException, match="retired contract") as exc_info:
        await test_run_api.start_test_run(persisted_run.test_run_id, make_request())

    assert exc_info.value.status_code == 409
    assert outbox.messages == []
    ready.assert_not_awaited()
    
@pytest.mark.asyncio
@pytest.mark.parametrize("worker_available", [True, False])
async def test_start_test_run_dispatches_only_once(
    monkeypatch: pytest.MonkeyPatch,
    worker_available: bool,
) -> None:
    """Starting the same TestRun twice must create one dispatch only."""
    from unittest.mock import AsyncMock

    ready = AsyncMock(side_effect=None if worker_available else HTTPException(
        503, "The test runner is not running. Start the execution worker and try again.",
    ))
    monkeypatch.setattr(test_run_api, "require_run_ready", ready)

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

    if not worker_available:
        with pytest.raises(HTTPException) as error:
            await test_run_api.start_test_run(persisted_run.test_run_id, make_request())
        assert error.value.status_code == 503
        assert outbox_repository.messages == []
        return

    first_response = await test_run_api.start_test_run(
        persisted_run.test_run_id,
        make_request(),
    )
    ready.assert_awaited_once()

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
async def test_queued_run_read_model_updates_reason_when_runner_heartbeat_arrives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, application, _, target = make_records()
    run_id = uuid4()
    created_at = datetime.now(UTC) - timedelta(seconds=61)
    persisted_run = TestRunRecord(
        test_run_id=run_id,
        workspace_id=application.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        created_by_user_id=user_id,
        status="queued",
        target_snapshot={},
        configuration_snapshot={"study_brief": "Observe the local application."},
        created_at=created_at,
        updated_at=created_at,
        started_at=None,
        completed_at=None,
    )
    session = Mock(
        scalar=AsyncMock(return_value=None),
        begin=Mock(return_value=AsyncContext(None)),
    )
    database = SimpleNamespace(session_factory=lambda: AsyncContext(session))
    workers = AsyncMock(side_effect=[
        [
            run_readiness.WorkerStatus(service="execution", ready=False),
            run_readiness.WorkerStatus(service="evaluation", ready=True),
        ],
        [
            run_readiness.WorkerStatus(service="execution", ready=True),
            run_readiness.WorkerStatus(service="evaluation", ready=True),
        ],
    ])
    monkeypatch.setattr(
        test_run_api,
        "get_authenticated_user_id",
        AsyncMock(return_value=user_id),
    )
    monkeypatch.setattr(test_run_api, "get_database_runtime", lambda _: database)
    monkeypatch.setattr(
        test_run_api,
        "TestRunRepository",
        lambda _: FakeTestRunRepository(persisted_run),
    )
    monkeypatch.setattr(run_readiness, "worker_statuses", workers)

    waiting = await test_run_api.get_test_run(run_id, make_request())
    busy = await test_run_api.get_test_run(run_id, make_request())

    assert waiting.status == busy.status == "queued"
    assert waiting.status_reason == (
        "The test runner is offline. No test actions are running. Start or restart the execution worker."
    )
    assert busy.status_reason == "Runner is busy with another test"
    assert workers.await_count == 2
    
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


# ---------------------------------------------------------------------------
# Doc 17 (D3 writer): creation-time run mode + approved test data.
# Named tests T-D3-A1..A5 (doc 17 section 13).
# ---------------------------------------------------------------------------


def _d3_authorization(
    user_id: UUID, target: TargetRecord, now: datetime,
) -> TargetAuthorizationRecord:
    return TargetAuthorizationRecord(
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


def _d3_persisted_run(
    *,
    user_id: UUID,
    application: ApplicationRecord,
    workspace: WorkspaceAccess,
    target: TargetRecord,
    snapshot: dict[str, object],
    now: datetime,
) -> TestRunRecord:
    return TestRunRecord(
        test_run_id=uuid4(),
        workspace_id=workspace.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        created_by_user_id=user_id,
        status="draft",
        target_snapshot=test_run_api.build_target_snapshot(target),
        configuration_snapshot=snapshot,
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )


@pytest.mark.asyncio
async def test_d3_a1_create_without_mode_persists_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T-D3-A1: no mode in the request -> read_only in the snapshot (C1)."""

    user_id, application, workspace, target = make_records()
    now = datetime.now(UTC)
    authorization = _d3_authorization(user_id, target, now)
    expected_configuration: dict[str, object] = {
        "runtime_human_assistance": True,
        "allow_offsite_navigation": False,
        "testing_depth": "medium",
        "study_brief": "Evaluate the shopping and checkout experience.",
        "authorization_id_at_creation": str(authorization.authorization_id),
        "harness_run_mode": "read_only",
    }
    test_run_repository = FakeTestRunRepository(
        _d3_persisted_run(
            user_id=user_id,
            application=application,
            workspace=workspace,
            target=target,
            snapshot=expected_configuration,
            now=now,
        ),
    )
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
            testing_depth="medium",
            study_brief="Evaluate the shopping and checkout experience.",
        ),
        make_request(),
    )

    assert test_run_repository.create_arguments is not None
    snapshot = test_run_repository.create_arguments["configuration_snapshot"]
    assert snapshot == expected_configuration
    assert "approved_test_data" not in snapshot
    assert response.harness_run_mode == "read_only"


@pytest.mark.asyncio
async def test_d3_a2_standard_mode_and_approved_data_are_snapshotted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T-D3-A2: standard + declared data land in the snapshot exactly."""

    user_id, application, workspace, target = make_records()
    now = datetime.now(UTC)
    authorization = _d3_authorization(user_id, target, now)
    expected_configuration: dict[str, object] = {
        "runtime_human_assistance": True,
        "allow_offsite_navigation": False,
        "testing_depth": "medium",
        "study_brief": "Evaluate the shopping and checkout experience.",
        "authorization_id_at_creation": str(authorization.authorization_id),
        "harness_run_mode": "standard",
        "approved_test_data": [
            {"key": "valid_name", "value": "Gatekeeper Ada"},
            {"key": "company_name", "value": "Thread & Co. Test"},
        ],
    }
    test_run_repository = FakeTestRunRepository(
        _d3_persisted_run(
            user_id=user_id,
            application=application,
            workspace=workspace,
            target=target,
            snapshot=expected_configuration,
            now=now,
        ),
    )
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
            testing_depth="medium",
            study_brief="Evaluate the shopping and checkout experience.",
            harness_run_mode="standard",
            approved_test_data=[
                test_run_api.ApprovedTestValue(
                    key="valid_name", value="Gatekeeper Ada",
                ),
                test_run_api.ApprovedTestValue(
                    key="company_name", value="Thread & Co. Test",
                ),
            ],
        ),
        make_request(),
    )

    assert test_run_repository.create_arguments is not None
    snapshot = test_run_repository.create_arguments["configuration_snapshot"]
    assert snapshot == expected_configuration
    assert response.harness_run_mode == "standard"


@pytest.mark.parametrize("kind", ["persona", "slop"])
def test_d3_a3_standard_mode_rejected_for_non_explore_kinds(
    kind: str,
) -> None:
    """T-D3-A3: the mode belongs to explore_test runs only."""

    with pytest.raises(ValidationError, match="applies to explore_test runs"):
        test_run_api.CreateTestRunRequest(
            target_id=uuid4(),
            run_kind=kind,
            study_brief="Evaluate the shopping and checkout experience.",
            harness_run_mode="standard",
        )


def test_d3_a4_mode_and_data_validation_fails_loudly() -> None:
    """T-D3-A4: malformed mode/data combinations are loud 422s (C7)."""

    entry = test_run_api.ApprovedTestValue
    base: dict[str, object] = {
        "target_id": uuid4(),
        "study_brief": "Evaluate the shopping and checkout experience.",
    }
    # Approved data without the standard mode.
    with pytest.raises(ValidationError, match="requires the standard run mode"):
        test_run_api.CreateTestRunRequest(
            **base,
            approved_test_data=[entry(key="company_name", value="x")],
        )
    # Duplicate keys.
    with pytest.raises(ValidationError, match="must be unique"):
        test_run_api.CreateTestRunRequest(
            **base,
            harness_run_mode="standard",
            approved_test_data=[
                entry(key="company_name", value="x"),
                entry(key="company_name", value="y"),
            ],
        )
    # Key shape: capitals/spaces, leading digit, over 32 characters.
    for bad_key in ("Company Name", "1company", "a" * 33):
        with pytest.raises(ValidationError):
            entry(key=bad_key, value="x")
    # Match the worker's SafeTestValue boundary at creation time.
    assert len(entry(key="company_name", value="v" * 256).value) == 256
    with pytest.raises(ValidationError):
        entry(key="company_name", value="v" * 257)
    # More than 32 entries.
    with pytest.raises(ValidationError):
        test_run_api.CreateTestRunRequest(
            **base,
            harness_run_mode="standard",
            approved_test_data=[
                entry(key=f"key_{index}", value="x") for index in range(33)
            ],
        )
    # The same shapes are accepted with the standard mode.
    request = test_run_api.CreateTestRunRequest(
        **base,
        harness_run_mode="standard",
        approved_test_data=[
            entry(key="company_name", value="Thread & Co. Test"),
        ],
    )
    assert request.harness_run_mode == "standard"
    assert request.approved_test_data[0].key == "company_name"


def test_d3_a5_response_mode_is_fail_closed_for_legacy_snapshots() -> None:
    """T-D3-A5: a snapshot without the key reads back as read_only (C1)."""

    user_id, application, workspace, target = make_records()
    now = datetime.now(UTC)
    for snapshot, expected in (
        ({"study_brief": "Legacy run."}, "read_only"),
        ({"harness_run_mode": "STANDARD"}, "read_only"),
        ({"harness_run_mode": "standard"}, "standard"),
    ):
        record = _d3_persisted_run(
            user_id=user_id,
            application=application,
            workspace=workspace,
            target=target,
            snapshot=snapshot,
            now=now,
        )
        assert test_run_api.test_run_response(record).harness_run_mode == expected
