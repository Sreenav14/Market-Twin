"""Real migrated PostgreSQL scope-revision API regression (disposable database only)."""

import asyncio
import os
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from markettwin_control_api.api import target_authorizations, targets
from markettwin_control_api.api.test_run import build_target_snapshot
from markettwin_control_api.config import get_settings
from markettwin_control_api.database import DatabaseRuntime
from markettwin_control_api.persistence.repositories import (
    TargetAuthorizationRepository,
    TargetRepository,
)
from markettwin_database.models import User, Workspace, WorkspaceMember
from markettwin_database.models.testing import Application
from markettwin_database.models.testing import TestRun as RunModel
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_SCOPE_TEST_DATABASE") != "1",
    reason="Requires generated disposable local database.",
)
async def test_pending_approved_revoked_scope_is_separate_from_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    assert settings.postgres_host in {"127.0.0.1", "localhost", "::1"}
    assert settings.postgres_db.startswith("mt_scope_")
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner, member, outsider, workspace_id, app_id = (uuid4() for _ in range(5))
    try:
        async with factory.begin() as session:
            for user_id in (owner, member, outsider):
                email = f"scope-{user_id}@example.invalid"
                session.add(User(id=user_id, email=email, normalized_email=email))
            await session.flush()
            session.add(
                Workspace(id=workspace_id, name="Synthetic scope", created_by_user_id=owner)
            )
            await session.flush()
            for user_id, role in ((owner, "owner"), (member, "member")):
                session.add(WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role))
            session.add(
                Application(
                    id=app_id,
                    workspace_id=workspace_id,
                    created_by_user_id=owner,
                    name="Synthetic scope",
                )
            )
            await session.flush()
            parent = await TargetRepository(session).create(
                application_id=app_id,
                name="Original",
                environment="test",
                base_url="http://127.0.0.1:8765/",
                requires_auth=False,
                scheme="http",
                hostname="127.0.0.1",
                port=8765,
            )
            frozen_run = RunModel(
                workspace_id=workspace_id,
                application_id=app_id,
                target_id=parent.target_id,
                created_by_user_id=owner,
                status="draft",
                target_snapshot=build_target_snapshot(parent),
                configuration_snapshot={"study_brief": "Synthetic frozen scope test"},
            )
            session.add(frozen_run)
            await session.flush()
            old_snapshot = dict(frozen_run.target_snapshot)
            await TargetAuthorizationRepository(session).authorize(
                target_id=parent.target_id,
                user_id=owner,
                authorization_basis="Owned synthetic local fixture.",
            )
        runtime = cast(DatabaseRuntime, SimpleNamespace(session_factory=factory))
        def get_runtime(request: Request) -> DatabaseRuntime:
            return runtime

        for module in (targets, target_authorizations):
            monkeypatch.setattr(module, "get_database_runtime", get_runtime)
            monkeypatch.setattr(module, "get_authenticated_user_id", AsyncMock(return_value=owner))
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
        payload = targets.RequestScopeRevision(
            name="Console scope",
            origins=["http://127.0.0.1:8765", "http://127.0.0.1:8766"],
            request_basis="Owned synthetic fixture console.",
        )
        revision = await targets.request_scope_revision(parent.target_id, payload, request)
        assert revision.id != parent.target_id and revision.scope_parent_id == parent.target_id
        assert len(revision.allowed_origins) == 2
        async with factory() as session:
            authorizations = TargetAuthorizationRepository(session)
            assert await authorizations.get_active(target_id=revision.id) is None
            pending = await authorizations.get_latest(target_id=revision.id)
            assert pending is not None and pending.status == "pending"
            original = await TargetRepository(session).get_for_user(
                target_id=parent.target_id, user_id=owner
            )
            assert original is not None and original.allowed_origins == parent.allowed_origins
        frozen_original = [
            origin.__dict__
            if hasattr(origin, "__dict__")
            else (origin.scheme, origin.hostname, origin.port, origin.include_subdomains)
            for origin in parent.allowed_origins
        ]
        monkeypatch.setattr(targets, "get_authenticated_user_id", AsyncMock(return_value=member))
        with pytest.raises(HTTPException) as error:
            await targets.request_scope_revision(parent.target_id, payload, request)
        assert error.value.status_code == 403
        monkeypatch.setattr(
            target_authorizations, "get_authenticated_user_id", AsyncMock(return_value=member)
        )
        with pytest.raises(HTTPException) as error:
            await target_authorizations.authorize_target(
                revision.id,
                target_authorizations.AuthorizeTargetRequest(
                    confirm_authorized=True, authorization_basis="Owned local synthetic fixture."
                ),
                request,
            )
        assert error.value.status_code == 403
        monkeypatch.setattr(targets, "get_authenticated_user_id", AsyncMock(return_value=outsider))
        with pytest.raises(HTTPException) as error:
            await targets.list_scope_revisions(parent.target_id, request)
        assert error.value.status_code == 404
        monkeypatch.setattr(
            target_authorizations, "get_authenticated_user_id", AsyncMock(return_value=owner)
        )
        approval = target_authorizations.AuthorizeTargetRequest(
            confirm_authorized=True,
            authorization_basis="Every listed loopback origin is owned by this fixture.",
        )
        concurrent = await asyncio.gather(
            target_authorizations.authorize_target(revision.id, approval, request),
            target_authorizations.authorize_target(revision.id, approval, request),
            return_exceptions=True,
        )
        accepted = [value for value in concurrent if not isinstance(value, BaseException)]
        denied = [value for value in concurrent if isinstance(value, HTTPException)]
        assert len(accepted) == 1
        assert len(denied) == 1 and denied[0].status_code == 409
        approved = accepted[0]
        assert approved.status == "authorized"
        with pytest.raises(HTTPException) as error:
            await target_authorizations.authorize_target(
                revision.id,
                target_authorizations.AuthorizeTargetRequest(
                    confirm_authorized=True, authorization_basis="Duplicate approval must fail."
                ),
                request,
            )
        assert error.value.status_code == 409
        revoked = await target_authorizations.revoke_target_authorization(revision.id, request)
        assert revoked.status == "revoked"
        async with factory() as session:
            assert (
                await TargetAuthorizationRepository(session).get_active(target_id=revision.id)
                is None
            )
            assert (
                await TargetAuthorizationRepository(session).get_active(target_id=parent.target_id)
                is not None
            )
            original = await TargetRepository(session).get_for_user(
                target_id=parent.target_id, user_id=owner
            )
            assert original is not None and original.allowed_origins == parent.allowed_origins
            saved_run = await session.get(RunModel, frozen_run.id)
            assert saved_run is not None and saved_run.target_snapshot == old_snapshot
            saved_origins = saved_run.target_snapshot["allowed_origins"]
            assert isinstance(saved_origins, list) and len(saved_origins) == 1
            approved_revision = await TargetRepository(session).get_for_user(
                target_id=revision.id,
                user_id=owner,
            )
            assert approved_revision is not None
            revised_origins = build_target_snapshot(approved_revision)["allowed_origins"]
            assert isinstance(revised_origins, list) and len(revised_origins) == 2
            assert frozen_original == [
                (origin.scheme, origin.hostname, origin.port, origin.include_subdomains)
                for origin in original.allowed_origins
            ]
    finally:
        await engine.dispose()
