"""Regression tests for Test Run authorization gating."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
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
    ) -> TestRunRecord:
        self.create_arguments = {
            "workspace_id": workspace_id,
            "application_id": application_id,
            "target_id": target_id,
            "created_by_user_id": created_by_user_id,
            "target_snapshot": target_snapshot,
            "configuration_snapshot": configuration_snapshot,
        }
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
    test_run_repository: FakeTestRunRepository | None = None,
) -> None:
    """Patch endpoint dependencies with deterministic repository fakes."""

    database = SimpleNamespace(
        session_factory=lambda: AsyncContext(FakeDatabaseSession())
    )

    async def authenticated_user_id(
        *,
        request: Request,
    ) -> UUID:
        return user_id

    monkeypatch.setattr(
        test_run_api,
        "get_authenticated_user_id",
        authenticated_user_id,
    )
    monkeypatch.setattr(
        test_run_api,
        "get_database_runtime",
        lambda request: cast(DatabaseRuntime, database),
    )
    monkeypatch.setattr(
        test_run_api,
        "ApplicationRepository",
        lambda session: FakeApplicationRepository(application),
    )
    monkeypatch.setattr(
        test_run_api,
        "WorkspaceRepository",
        lambda session: FakeWorkspaceRepository(workspace),
    )
    monkeypatch.setattr(
        test_run_api,
        "TargetRepository",
        lambda session: FakeTargetRepository(target),
    )
    monkeypatch.setattr(
        test_run_api,
        "TargetAuthorizationRepository",
        lambda session: FakeAuthorizationRepository(authorization),
    )

    if test_run_repository is not None:
        monkeypatch.setattr(
            test_run_api,
            "TestRunRepository",
            lambda session: test_run_repository,
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
async def test_create_test_run_snapshots_active_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful Test Run records the authorization active at creation."""

    user_id, application, workspace, target = make_records()
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

    expected_configuration = {
        "study_brief": (
            "Evaluate the shopping and checkout experience."
        ),
        "authorization_id_at_creation": str(authorization_id),
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
