"""Doc 33 section 3.6: run creation validates and pins source
knowledge attachments — entry approved, file approved, same
workspace — into configuration_snapshot["source_knowledge"], by
hash, with the collection's manifest pinned at its versioned
location (arbitration A-2).

The endpoint fakes are inlined (copied from test_test_run_api.py):
this suite's convention is self-contained test modules."""

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from markettwin_control_api.api import test_run as test_run_api
from markettwin_control_api.database import DatabaseRuntime
from markettwin_control_api.knowledge.files import (
    KnowledgeFileRecord,
    KnowledgeFileRepository,
)
from markettwin_control_api.persistence.repositories import (
    AllowedOriginRecord,
    ApplicationRecord,
    TargetAuthorizationRecord,
    TargetRecord,
    TestRunRecord,
    WorkspaceAccess,
)
from pydantic import ValidationError

ENTRY_ID = uuid4()
COLLECTION_ID = uuid4()
FILE_ID = uuid4()


# --- endpoint fakes (copied from test_test_run_api.py) --------------------


class AsyncContext:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *_args):
        return False


class EmptyQueryResult:
    def scalars(self):
        return self

    def first(self):
        return None

    def all(self):
        return []


class FakeDatabaseSession:
    def begin(self):
        return AsyncContext(None)

    async def execute(self, statement):
        return EmptyQueryResult()

    async def scalar(self, statement):
        return None

    async def scalars(self, statement):
        return EmptyQueryResult()


class FakeApplicationRepository:
    def __init__(self, application):
        self._application = application

    async def get_for_user(self, *, application_id, user_id):
        return self._application


class FakeWorkspaceRepository:
    def __init__(self, workspace):
        self._workspace = workspace

    async def get_for_user(self, *, workspace_id, user_id):
        return self._workspace


class FakeTargetRepository:
    def __init__(self, target):
        self._target = target

    async def get_for_user(self, *, target_id, user_id):
        return self._target


class FakeAuthorizationRepository:
    def __init__(self, authorization):
        self._authorization = authorization

    async def get_active(self, *, target_id):
        return self._authorization


class FakeTestRunRepository:
    def __init__(self, test_run):
        self._test_run = test_run
        self.create_arguments = None

    async def create(
        self, *, workspace_id, application_id, target_id,
        created_by_user_id, target_snapshot, configuration_snapshot,
        synthetic_fixture_approval_enabled=False,
        human_action_approvals_enabled=False, run_kind=None,
    ):
        self.create_arguments = {
            "workspace_id": workspace_id,
            "application_id": application_id,
            "target_id": target_id,
            "created_by_user_id": created_by_user_id,
            "target_snapshot": target_snapshot,
            "configuration_snapshot": configuration_snapshot,
            "synthetic_fixture_approval_enabled": (
                synthetic_fixture_approval_enabled
            ),
            "human_action_approvals_enabled": human_action_approvals_enabled,
            "run_kind": run_kind,
        }
        return self._test_run

    async def get_for_user(self, *, test_run_id, user_id):
        if self._test_run.test_run_id == test_run_id:
            return self._test_run
        return None

    async def update_configuration_snapshot(
        self, *, test_run_id, configuration_snapshot,
    ):
        if self._test_run.test_run_id == test_run_id:
            self._test_run = replace(
                self._test_run, configuration_snapshot=configuration_snapshot,
            )


def make_request() -> Request:
    return Request(
        {"type": "http", "method": "POST", "path": "/", "headers": []}
    )


def make_records():
    user_id = uuid4()
    workspace_id = uuid4()
    application_id = uuid4()
    target_id = uuid4()
    application = ApplicationRecord(
        application_id=application_id, workspace_id=workspace_id,
        created_by_user_id=user_id, name="Demo Store", description=None,
        status="active",
    )
    workspace = WorkspaceAccess(
        workspace_id=workspace_id, name="Demo Workspace", status="active",
        role="owner",
    )
    target = TargetRecord(
        target_id=target_id, application_id=application_id,
        name="Local Demo Store", environment="local",
        base_url="http://localhost:3000/", requires_auth=False,
        status="active",
        allowed_origins=(
            AllowedOriginRecord(
                scheme="http", hostname="localhost", port=3000,
                include_subdomains=False,
            ),
        ),
    )
    return user_id, application, workspace, target


def patch_common_dependencies(
    monkeypatch, *, user_id, application, workspace, target,
    authorization, test_run_repository,
):
    def session_factory():
        return AsyncContext(FakeDatabaseSession())

    database = SimpleNamespace(session_factory=session_factory)

    async def authenticated_user_id(*, request):
        return user_id

    def database_runtime(request):
        return cast(DatabaseRuntime, database)

    monkeypatch.setattr(
        test_run_api, "get_authenticated_user_id", authenticated_user_id,
    )
    monkeypatch.setattr(
        test_run_api, "get_database_runtime", database_runtime,
    )
    monkeypatch.setattr(
        test_run_api, "ApplicationRepository",
        lambda session: FakeApplicationRepository(application),
    )
    monkeypatch.setattr(
        test_run_api, "WorkspaceRepository",
        lambda session: FakeWorkspaceRepository(workspace),
    )
    monkeypatch.setattr(
        test_run_api, "TargetRepository",
        lambda session: FakeTargetRepository(target),
    )
    monkeypatch.setattr(
        test_run_api, "TargetAuthorizationRepository",
        lambda session: FakeAuthorizationRepository(authorization),
    )
    monkeypatch.setattr(
        test_run_api, "TestRunRepository",
        lambda session: test_run_repository,
    )


# --- knowledge fakes -------------------------------------------------------


class FakeIngestionRepository:
    """Entry-id -> approval status (None = no such entry here)."""

    def __init__(self, statuses):
        self._statuses = statuses

    async def get(self, workspace_id, entry_id, *, lock=False, application_id=None):
        status = self._statuses.get(entry_id)
        if status is None:
            return None
        return SimpleNamespace(version=SimpleNamespace(status=status))


class FakeKnowledgeFileRepository:
    def __init__(self, *, files=None, versions=None):
        self._files = files or {}
        self._versions = versions or {}

    async def get_approved_file(self, *, workspace_id, entry_id, slug):
        return self._files.get((entry_id, slug))

    async def latest_approved_version(self, *, workspace_id, entry_id):
        return self._versions.get(entry_id)


def file_row(workspace_id, *, slug="pricing", version=2):
    return KnowledgeFileRecord(
        id=FILE_ID, workspace_id=workspace_id, ingestion_entry_id=ENTRY_ID,
        slug=slug, title="Pricing", description="Plan prices.",
        object_key=f"knowledge/{workspace_id}/{ENTRY_ID}/files/v{version}/{slug}.md",
        sha256="a" * 64, token_count=120, version=version, status="approved",
    )


def setup_creation(monkeypatch, *, ingestion, file_repository):
    user_id, application, workspace, target = make_records()
    now = datetime.now(UTC)
    authorization = TargetAuthorizationRecord(
        authorization_id=uuid4(), target_id=target.target_id,
        created_by_user_id=user_id, authorized_by_user_id=user_id,
        status="authorized", authorization_basis="Owned local application.",
        created_at=now, authorized_at=now, revoked_at=None, expires_at=None,
    )
    persisted_run = TestRunRecord(
        test_run_id=uuid4(), workspace_id=application.workspace_id,
        application_id=application.application_id, target_id=target.target_id,
        created_by_user_id=user_id, status="draft",
        target_snapshot=test_run_api.build_target_snapshot(target),
        configuration_snapshot={}, created_at=now, updated_at=now,
        started_at=None, completed_at=None,
    )
    repository = FakeTestRunRepository(persisted_run)
    patch_common_dependencies(
        monkeypatch, user_id=user_id, application=application,
        workspace=workspace, target=target, authorization=authorization,
        test_run_repository=repository,
    )
    monkeypatch.setattr(
        test_run_api, "IngestionRepository", lambda session: ingestion,
    )
    monkeypatch.setattr(
        test_run_api, "KnowledgeFileRepository", lambda session: file_repository,
    )
    return application, target, repository


def payload(target, **overrides):
    body = {
        "target_id": target.target_id,
        "study_brief": "Evaluate the shopping and checkout experience.",
    }
    body.update(overrides)
    return test_run_api.CreateTestRunRequest(**body)


# --- pinning behaviour -------------------------------------------------------


@pytest.mark.asyncio
async def test_create_pins_files_and_collections_by_hash(monkeypatch):
    ingestion = FakeIngestionRepository(
        {ENTRY_ID: "approved", COLLECTION_ID: "approved"}
    )
    files = FakeKnowledgeFileRepository(versions={COLLECTION_ID: 3})
    application, target, repository = setup_creation(
        monkeypatch, ingestion=ingestion, file_repository=files,
    )
    files._files[(ENTRY_ID, "pricing")] = file_row(application.workspace_id)

    await test_run_api.create_test_run(
        application.application_id,
        payload(
            target,
            knowledge_files=[{"entry_id": ENTRY_ID, "slug": "pricing"}],
            knowledge_collections=[COLLECTION_ID],
        ),
        make_request(),
    )
    assert repository.create_arguments is not None
    snapshot = repository.create_arguments["configuration_snapshot"]
    assert snapshot["source_knowledge"] == {
        "files": [{
            "file_id": str(FILE_ID), "entry_id": str(ENTRY_ID),
            "slug": "pricing", "title": "Pricing",
            "object_key": (
                f"knowledge/{application.workspace_id}/{ENTRY_ID}"
                "/files/v2/pricing.md"
            ),
            "sha256": "a" * 64,
        }],
        "collections": [{
            "entry_id": str(COLLECTION_ID),
            "manifest_object_key": (
                f"knowledge/{application.workspace_id}/{COLLECTION_ID}"
                "/files/v3/manifest.json"
            ),
            "version": 3,
        }],
    }


@pytest.mark.asyncio
async def test_create_rejects_an_unapproved_entry(monkeypatch):
    ingestion = FakeIngestionRepository({ENTRY_ID: "draft"})
    files = FakeKnowledgeFileRepository()
    application, target, _ = setup_creation(
        monkeypatch, ingestion=ingestion, file_repository=files,
    )
    with pytest.raises(HTTPException) as exc_info:
        await test_run_api.create_test_run(
            application.application_id,
            payload(
                target,
                knowledge_files=[{"entry_id": ENTRY_ID, "slug": "pricing"}],
            ),
            make_request(),
        )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_a_file_that_is_not_approved(monkeypatch):
    ingestion = FakeIngestionRepository({ENTRY_ID: "approved"})
    files = FakeKnowledgeFileRepository(files={})
    application, target, _ = setup_creation(
        monkeypatch, ingestion=ingestion, file_repository=files,
    )
    with pytest.raises(HTTPException) as exc_info:
        await test_run_api.create_test_run(
            application.application_id,
            payload(
                target,
                knowledge_files=[{"entry_id": ENTRY_ID, "slug": "pricing"}],
            ),
            make_request(),
        )
    assert exc_info.value.status_code == 422
    assert "pricing" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_create_rejects_a_collection_without_approved_files(monkeypatch):
    ingestion = FakeIngestionRepository({COLLECTION_ID: "approved"})
    files = FakeKnowledgeFileRepository(versions={})
    application, target, _ = setup_creation(
        monkeypatch, ingestion=ingestion, file_repository=files,
    )
    with pytest.raises(HTTPException) as exc_info:
        await test_run_api.create_test_run(
            application.application_id,
            payload(target, knowledge_collections=[COLLECTION_ID]),
            make_request(),
        )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_create_without_attachments_pins_no_block(monkeypatch):
    ingestion = FakeIngestionRepository({})
    files = FakeKnowledgeFileRepository()
    application, target, repository = setup_creation(
        monkeypatch, ingestion=ingestion, file_repository=files,
    )
    await test_run_api.create_test_run(
        application.application_id, payload(target), make_request(),
    )
    assert repository.create_arguments is not None
    snapshot = repository.create_arguments["configuration_snapshot"]
    assert "source_knowledge" not in snapshot


def test_attachment_slug_follows_the_contract_alphabet():
    with pytest.raises(ValidationError):
        test_run_api.CreateTestRunRequest(
            target_id=uuid4(), study_brief="Evaluate the storefront.",
            knowledge_files=[{"entry_id": ENTRY_ID, "slug": "Pricing Guide"}],
        )


# --- the file-index repository's own logic -------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return SimpleNamespace(all=lambda: self._rows)


class _Session:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, statement):
        return _Result(self._rows)


def _row(slug, version, *, status="approved"):
    return {
        "id": uuid4(), "workspace_id": uuid4(),
        "ingestion_entry_id": ENTRY_ID, "slug": slug,
        "title": slug.title(), "description": "d",
        "object_key": f"k/{slug}.md", "sha256": "b" * 64,
        "token_count": 10, "version": version, "status": status,
    }


@pytest.mark.asyncio
async def test_list_files_keeps_the_latest_approved_version_per_slug():
    rows = [_row("pricing", 2), _row("pricing", 1), _row("refunds", 1)]
    repository = KnowledgeFileRepository(_Session(rows))
    files = await repository.list_files(
        workspace_id=uuid4(), entry_id=ENTRY_ID,
    )
    assert [(f.slug, f.version) for f in files] == [
        ("pricing", 2), ("refunds", 1),
    ]


@pytest.mark.asyncio
async def test_get_approved_file_returns_the_first_row_or_none():
    repository = KnowledgeFileRepository(_Session([_row("pricing", 3)]))
    found = await repository.get_approved_file(
        workspace_id=uuid4(), entry_id=ENTRY_ID, slug="pricing",
    )
    assert found is not None and found.version == 3
    empty = KnowledgeFileRepository(_Session([]))
    assert await empty.get_approved_file(
        workspace_id=uuid4(), entry_id=ENTRY_ID, slug="pricing",
    ) is None
