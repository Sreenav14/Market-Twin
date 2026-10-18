"""Authenticated observation, separate from lease-bound browser input."""

import asyncio
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import get_authenticated_user_id
from markettwin_control_api.api.execution_pause import PauseResponse, pause_response
from markettwin_control_api.api.observation_common import NO_STORE, ObservationRoute
from markettwin_control_api.config import get_settings
from markettwin_control_api.persistence.repositories.execution_pause_repository import (
    ExecutionPauseRepository,
)
from markettwin_control_api.persistence.repositories.live_browser_repository import (
    LiveBrowserRepository,
)
from markettwin_control_api.services.hitl_worker_client import (
    BrowserObservationUnavailable,
    HitlWorkerClient,
)

_frame_slots = asyncio.Semaphore(4)


router = APIRouter(tags=["Live Execution"], route_class=ObservationRoute)


class BrowserSelection(BaseModel):
    browser_session_id: UUID
    execution_id: UUID
    journey_id: UUID
    generation: int
    control_state: Literal["agent", "human_pending", "human", "verifying", "none"]
    viewer_state: Literal["available", "suppressed"]
    journey_title: str
    requesting_agent: str


class ActivityItem(BaseModel):
    id: str
    run_id: UUID
    journey_id: UUID | None
    execution_id: UUID | None
    step_id: int | None
    source: str
    kind: str
    status: str
    occurred_at: datetime
    title: str


class ActivityPage(BaseModel):
    items: list[ActivityItem]
    next_cursor: str | None


class LiveBrowserResponse(BaseModel):
    run_id: UUID
    run_status: str
    server_observed_at: datetime
    browser: BrowserSelection | None
    activity: ActivityPage
    pause: PauseResponse | None = None


def worker_client() -> HitlWorkerClient:
    settings = get_settings()
    if settings.hitl_internal_secret is None:
        raise HTTPException(503, "The supervised browser owner is unavailable.")
    try:
        parsed = urlsplit(settings.hitl_worker_url)
        _ = parsed.port
    except ValueError:
        raise HTTPException(503, "The supervised browser owner is unavailable.") from None
    local = settings.app_env == "local" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if (parsed.scheme != "https" and not (parsed.scheme == "http" and local)
            or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise HTTPException(503, "The supervised browser owner is unavailable.")
    return HitlWorkerClient(base_url=settings.hitl_worker_url, secret=settings.hitl_internal_secret,
                            timeout_seconds=settings.hitl_worker_timeout_seconds)


@router.get("/api/v1/test-runs/{run_id}/live-browser", response_model=LiveBrowserResponse)
async def get_live_browser(
    run_id: UUID, request: Request, browser_session_id: UUID | None = None,
    cursor: str | None = Query(default=None, max_length=300),
    limit: int = Query(default=50, ge=1, le=50),
) -> LiveBrowserResponse:
    actor_id = await get_authenticated_user_id(request=request)
    async with get_database_runtime(request).session_factory() as session:
        repository = LiveBrowserRepository(session)
        run = await repository.authorized_run(run_id=run_id, actor_id=actor_id)
        if run is None:
            raise HTTPException(404, "Test run not found.")
        browser = await repository.selected_browser(run=run, browser_session_id=browser_session_id)
        try:
            activity = await repository.activity(run_id=run_id, cursor=cursor, limit=limit)
        except ValueError:
            raise HTTPException(422, "Invalid activity cursor.") from None
        pause = None
        if browser is not None:
            recorded_pause = await ExecutionPauseRepository(session).latest(
                run_id=run_id, browser_session_id=browser_session_id
                if browser_session_id is not None else UUID(str(browser["browser_session_id"])),
            )
            pause = pause_response(recorded_pause) if recorded_pause is not None else None
        return LiveBrowserResponse(
            run_id=run_id, run_status=run.status, server_observed_at=datetime.now(UTC),
            browser=BrowserSelection.model_validate(browser) if browser else None,
            activity=ActivityPage.model_validate(activity), pause=pause,
        )


@router.get("/api/v1/test-runs/{run_id}/live-browser/frame")
async def get_live_frame(
    run_id: UUID, request: Request, browser_session_id: UUID,
    generation: int = Query(ge=0),
) -> Response:
    actor_id = await get_authenticated_user_id(request=request)
    if _frame_slots.locked():
        raise HTTPException(429, "Browser observation is busy. Try again.")
    async with _frame_slots:
        async with get_database_runtime(request).session_factory() as session:
            repository = LiveBrowserRepository(session)

            async def exact_selection() -> BrowserSelection:
                run = await repository.authorized_run(run_id=run_id, actor_id=actor_id)
                if run is None:
                    raise HTTPException(404, "Test run not found.")
                selection = await repository.selected_browser(
                    run=run, browser_session_id=browser_session_id,
                )
                if (not selection or selection["browser_session_id"] != browser_session_id
                        or selection["generation"] != generation
                        or selection["viewer_state"] != "available"):
                    raise HTTPException(409, "Browser observation unavailable.")
                return BrowserSelection.model_validate(selection)

            selected = await exact_selection()
            try:
                image = await worker_client().observe_frame(
                    actor_id=actor_id, browser_session_id=browser_session_id,
                    execution_id=selected.execution_id, journey_id=selected.journey_id,
                    generation=generation,
                )
            except BrowserObservationUnavailable:
                raise HTTPException(409, "Browser observation unavailable.") from None
            except RuntimeError:
                raise HTTPException(503, "The supervised browser owner is unavailable.") from None
            # Session revocation, membership, target approval and durable generation
            # can change during the asynchronous worker capture. Recheck before bytes.
            if await get_authenticated_user_id(request=request) != actor_id:
                raise HTTPException(401, "Authentication required.")
            current = await exact_selection()
            if current != selected:
                raise HTTPException(409, "Browser observation unavailable.")
            return Response(content=image, media_type="image/jpeg", headers=NO_STORE)
