"""Request cooperative pause/resume; input remains under the existing human lease."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from markettwin_database.models import ExecutionPauseRequest
from pydantic import BaseModel, ConfigDict, Field

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import get_authenticated_user_id
from markettwin_control_api.api.observation_common import ObservationRoute
from markettwin_control_api.config import get_settings
from markettwin_control_api.persistence.repositories.execution_pause_repository import (
    ExecutionPauseRepository,
    PauseRejected,
)

router = APIRouter(tags=["Live Execution"], route_class=ObservationRoute)


class PauseIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    browser_session_id: UUID
    generation: int = Field(ge=0)


class PauseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    execution_id: UUID
    journey_id: UUID
    browser_session_id: UUID
    generation: int
    human_request_id: UUID | None
    created_at: datetime
    expires_at: datetime
    acknowledged_at: datetime | None
    completed_at: datetime | None


def require_same_origin(request: Request) -> None:
    if (request.headers.get("x-markettwin-request") != "1"
            or request.headers.get("origin") != get_settings().web_origin):
        raise HTTPException(403, "Request origin was rejected.")


def pause_response(pause: ExecutionPauseRequest) -> PauseResponse:
    return PauseResponse.model_validate(pause)


@router.post("/api/v1/test-runs/{run_id}/live-browser/pause", status_code=202,
             response_model=PauseResponse)
async def request_execution_pause(run_id: UUID, payload: PauseIntent,
                                  request: Request) -> PauseResponse:
    require_same_origin(request)
    actor_id = await get_authenticated_user_id(request=request)
    try:
        async with get_database_runtime(request).session_factory() as session:
            async with session.begin():
                pause = await ExecutionPauseRepository(session).request(
                    run_id=run_id, actor_id=actor_id, browser_session_id=payload.browser_session_id,
                    generation=payload.generation,
                )
                response = pause_response(pause)
        return response
    except PauseRejected as error:
        raise HTTPException(error.status_code, "Execution pause is unavailable.") from None


@router.post("/api/v1/test-runs/{run_id}/live-browser/pause/{pause_id}/resume", status_code=202,
             response_model=PauseResponse)
async def request_execution_resume(run_id: UUID, pause_id: UUID,
                                   request: Request) -> PauseResponse:
    require_same_origin(request)
    actor_id = await get_authenticated_user_id(request=request)
    try:
        async with get_database_runtime(request).session_factory() as session:
            async with session.begin():
                pause = await ExecutionPauseRepository(session).resume(
                    run_id=run_id, pause_id=pause_id, actor_id=actor_id,
                )
                response = pause_response(pause)
        return response
    except PauseRejected as error:
        raise HTTPException(error.status_code, "Execution pause is unavailable.") from None
