"""Opt-in PostgreSQL deletion check using isolated rows and an outer rollback."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from markettwin_control_api.api import lifecycle
from markettwin_control_api.config import get_settings
from markettwin_control_api.persistence.models import (
    Application,
    ApplicationTarget,
    User,
    Workspace,
    WorkspaceMember,
)
from markettwin_control_api.persistence.models import TestRun as RunModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_DATABASE") != "1",
    reason="Set MARKETTWIN_TEST_DATABASE=1 to verify against local PostgreSQL.",
)
async def test_database_delete_draft_then_parent_records(monkeypatch):
    """Delete only an untouched draft Test, then its target and application."""
    engine = create_async_engine(get_settings().database_url, connect_args={"timeout": 5})
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            try:
                factory = async_sessionmaker(
                    connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
                )
                user_id, workspace_id, app_id, target_id, run_id = (
                    uuid4() for _ in range(5)
                )
                email = f"lifecycle-test-{user_id}@example.invalid"
                async with factory() as session:
                    session.add(User(id=user_id, email=email, normalized_email=email))
                    await session.flush()
                    session.add(
                        Workspace(id=workspace_id, name="Deletion test", created_by_user_id=user_id)
                    )
                    await session.flush()
                    session.add(
                        WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="owner")
                    )
                    session.add(
                        Application(
                            id=app_id,
                            workspace_id=workspace_id,
                            created_by_user_id=user_id,
                            name="Deletion test",
                        )
                    )
                    await session.flush()
                    session.add(
                        ApplicationTarget(
                            id=target_id,
                            application_id=app_id,
                            name="Deletion test",
                            environment="test",
                            base_url="https://example.invalid",
                            requires_auth=False,
                        )
                    )
                    await session.flush()
                    session.add(
                        RunModel(
                            id=run_id,
                            workspace_id=workspace_id,
                            application_id=app_id,
                            target_id=target_id,
                            created_by_user_id=user_id,
                            status="draft",
                        )
                    )
                    await session.commit()
                monkeypatch.setattr(
                    lifecycle, "get_authenticated_user_id", AsyncMock(return_value=user_id)
                )
                monkeypatch.setattr(
                    lifecycle,
                    "get_database_runtime",
                    lambda request: SimpleNamespace(session_factory=factory),
                )
                request = Request({"type": "http", "method": "DELETE", "path": "/", "headers": []})
                with pytest.raises(HTTPException) as error:
                    await lifecycle.delete_target(target_id, request)
                assert error.value.status_code == 409
                assert (await lifecycle.delete_test_run(run_id, request)).status_code == 204
                assert (
                    await connection.scalar(select(RunModel.id).where(RunModel.id == run_id))
                    is None
                )
                assert (await lifecycle.delete_target(target_id, request)).status_code == 204
                assert (
                    await connection.scalar(
                        select(ApplicationTarget.id).where(ApplicationTarget.id == target_id)
                    )
                    is None
                )
                assert (await lifecycle.delete_application(app_id, request)).status_code == 204
                assert (
                    await connection.scalar(select(Application.id).where(Application.id == app_id))
                    is None
                )
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()
