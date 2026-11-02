"""Authorized run readiness checks shown before dispatch."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import get_authenticated_user_id
from markettwin_control_api.config import get_settings
from markettwin_control_api.persistence.repositories import TestRunRepository
from markettwin_control_api.services.run_readiness import RunPreflight, run_preflight

router = APIRouter(tags=["Test Runs"])


@router.get("/api/v1/test-runs/{test_run_id}/preflight", response_model=RunPreflight)
@router.get(
    "/api/v1/workspaces/{workspace_id}/test-runs/{test_run_id}/preflight",
    response_model=RunPreflight,
)
async def get_run_preflight(
    test_run_id: UUID, request: Request, workspace_id: UUID | None = None,
) -> RunPreflight:
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        run = await TestRunRepository(session).get_for_user(
            test_run_id=test_run_id, user_id=user_id,
        )
        if run is None or (workspace_id is not None and run.workspace_id != workspace_id):
            raise HTTPException(404, "Test run not found.")
        return await run_preflight(session, get_settings())
