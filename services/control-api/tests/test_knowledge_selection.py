"""Only approved workspace knowledge reaches the frozen test configuration."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from markettwin_control_api.api import test_run as api
from markettwin_control_api.persistence.repositories import TargetAuthorizationRecord, TestRunRecord
from pydantic import ValidationError

from .test_test_run_api import (
    FakeTestRunRepository,
    make_records,
    make_request,
    patch_common_dependencies,
)


def test_knowledge_selection_rejects_duplicate_ids():
    entry_id = uuid4()
    with pytest.raises(ValidationError):
        api.CreateTestRunRequest(
            target_id=uuid4(),
            study_brief="A valid testing goal",
            knowledge_entry_ids=[entry_id, entry_id],
        )


@pytest.mark.parametrize(
    "knowledge_status,expected_error", [("draft", 409), (None, 404), ("approved", None)]
)
async def test_only_approved_knowledge_is_snapshotted(
    monkeypatch, knowledge_status, expected_error
):
    user_id, application, workspace, target = make_records()
    now, entry_id = datetime.now(UTC), uuid4()
    authorization = TargetAuthorizationRecord(
        authorization_id=uuid4(),
        target_id=target.target_id,
        created_by_user_id=user_id,
        authorized_by_user_id=user_id,
        status="authorized",
        authorization_basis="Owned target",
        created_at=now,
        authorized_at=now,
        revoked_at=None,
        expires_at=None,
    )
    run_repository = FakeTestRunRepository(
        TestRunRecord(
            test_run_id=uuid4(),
            workspace_id=workspace.workspace_id,
            application_id=application.application_id,
            target_id=target.target_id,
            created_by_user_id=user_id,
            status="draft",
            target_snapshot={},
            configuration_snapshot={},
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
        )
    )
    patch_common_dependencies(
        monkeypatch,
        user_id=user_id,
        application=application,
        workspace=workspace,
        target=target,
        authorization=authorization,
        test_run_repository=run_repository,
    )
    record = (
        None
        if knowledge_status is None
        else SimpleNamespace(
            entry=SimpleNamespace(
                id=entry_id,
                preview={
                    "application_knowledge": [{"content": "Approved facts"}],
                    "artifacts": [],
                    "skills": [],
                },
            ),
            version=SimpleNamespace(status=knowledge_status),
            blueprint=SimpleNamespace(name="Source context"),
            asset=SimpleNamespace(original_filename="source.txt"),
            pin=SimpleNamespace(roles=["product_knowledge"]),
        )
    )
    get = AsyncMock(return_value=record)
    monkeypatch.setattr(api, "IngestionRepository", lambda _: SimpleNamespace(get=get))
    payload = api.CreateTestRunRequest(
        target_id=target.target_id,
        study_brief="Evaluate documented behavior",
        knowledge_entry_ids=[entry_id],
    )
    if expected_error:
        with pytest.raises(HTTPException) as failure:
            await api.create_test_run(application.application_id, payload, make_request())
        assert failure.value.status_code == expected_error
        assert run_repository.create_arguments is None
    else:
        await api.create_test_run(application.application_id, payload, make_request())
        snapshot = run_repository.create_arguments["configuration_snapshot"]
        assert snapshot["knowledge"][0]["id"] == str(entry_id)
        assert snapshot["knowledge"][0]["application_knowledge"] == [{"content": "Approved facts"}]
    get.assert_awaited_once_with(
        application.workspace_id, entry_id, application_id=application.application_id
    )
