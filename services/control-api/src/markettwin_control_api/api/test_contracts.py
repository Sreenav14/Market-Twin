"""Historical test-contract reader (U-P8).

Contract generation, editing, approval and execution were retired
with the discovery_contract_v1 engine. What survives — permanently,
as history — is reading a contract that a past run already stored.
A run without a stored contract gets an honest 404; nothing is
generated on read any more."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from markettwin_shared.discovery_contract import TestContract

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import get_authenticated_user_id
from markettwin_control_api.persistence.repositories import (
    TestRunRecord,
    TestRunRepository,
    WorkspaceRepository,
)

router = APIRouter(tags=["Test Contracts"])


async def _get_authorized_run_and_workspace(
    *,
    workspace_id: UUID,
    run_id: UUID,
    user_id: UUID,
    session: Any,
) -> tuple[TestRunRecord, Any]:
    test_run_repo = TestRunRepository(session)
    run = await test_run_repo.get_for_user(test_run_id=run_id, user_id=user_id)
    if run is None or run.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found.",
        )

    workspace_repo = WorkspaceRepository(session)
    workspace = await workspace_repo.get_for_user(workspace_id=workspace_id, user_id=user_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        )

    return run, workspace


def _get_stored_contract(run: TestRunRecord) -> TestContract:
    """Read the contract a past run stored; never generate one."""

    snapshot = dict(run.configuration_snapshot)
    if "test_contract" in snapshot and snapshot["test_contract"] is not None:
        return TestContract.model_validate(snapshot["test_contract"])
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="This run has no stored test contract.",
    )


@router.get(
    "/api/v1/workspaces/{workspace_id}/test-runs/{run_id}/contract",
    response_model=TestContract,
)
async def get_test_contract(
    workspace_id: UUID,
    run_id: UUID,
    request: Request,
) -> TestContract:
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)

    async with database.session_factory() as session:
        async with session.begin():
            run, _ = await _get_authorized_run_and_workspace(
                workspace_id=workspace_id,
                run_id=run_id,
                user_id=user_id,
                session=session,
            )
            return _get_stored_contract(run)
