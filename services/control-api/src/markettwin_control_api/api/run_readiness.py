"""Authorized run readiness checks shown before dispatch."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import get_authenticated_user_id
from markettwin_control_api.config import get_settings
from markettwin_control_api.persistence.repositories import TestRunRepository
from markettwin_control_api.services.run_readiness import RunPreflight, draft_map_readiness, run_preflight

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
        settings = get_settings()
        result = await run_preflight(session, settings)
        _, map_check = await draft_map_readiness(session, run, settings)
        if map_check is not None:
            result.checks.append(map_check)
            result.ready = result.ready and map_check.ready
        return result
