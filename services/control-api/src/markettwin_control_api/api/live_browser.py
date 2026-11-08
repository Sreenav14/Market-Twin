"""Authenticated observation, separate from lease-bound browser input."""

from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import get_authenticated_user_id
from markettwin_control_api.api.execution_pause import PauseResponse, pause_response
from markettwin_control_api.api.observation_common import ObservationRoute
from markettwin_control_api.config import get_settings
from markettwin_control_api.persistence.repositories.execution_pause_repository import (
    ExecutionPauseRepository,
)
from markettwin_control_api.persistence.repositories.live_browser_repository import (
    LiveBrowserRepository,
)
from markettwin_control_api.services.hitl_worker_client import HitlWorkerClient


router = APIRouter(tags=["Live Execution"], route_class=ObservationRoute)


class BoardItemBanner(BaseModel):
    """Now-line for the Watch page: 'Item 23 of 112 — Save (button)'."""

    index: int
    total: int
    label: str


class BrowserSelection(BaseModel):
    browser_session_id: UUID
    execution_id: UUID
    journey_id: UUID
    generation: int
    control_state: Literal["agent", "human_pending", "human", "verifying", "none"]
    viewer_state: Literal["available", "suppressed"]
    journey_title: str
    requesting_agent: str
    board_item: BoardItemBanner | None = None


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
    if (settings.hitl_internal_secret is None
            or len(settings.hitl_internal_secret.get_secret_value().strip()) < 32):
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


class LiveGrantResponse(BaseModel):
    ticket: str
    viewer_url: str
    browser: BrowserSelection


@router.post(
    "/api/v1/test-runs/{run_id}/live-grant", response_model=LiveGrantResponse,
)
async def create_live_grant(
    run_id: UUID, request: Request, browser_session_id: UUID | None = None,
) -> LiveGrantResponse:
    """Issue a single-use observer ticket for the run's live browser.

    This is the first production caller of the worker's observer-grant
    route (U-P3-01): the Watch page exchanges this grant for the
    screencast WebSocket. 503 when the HITL worker service is not
    configured (worker_client), 409 when no browser can be observed.
    """

    actor_id = await get_authenticated_user_id(request=request)
    async with get_database_runtime(request).session_factory() as session:
        repository = LiveBrowserRepository(session)
        run = await repository.authorized_run(run_id=run_id, actor_id=actor_id)
        if run is None:
            raise HTTPException(404, "Test run not found.")
        selection = await repository.selected_browser(
            run=run, browser_session_id=browser_session_id,
        )
        if not selection or selection["viewer_state"] != "available":
            raise HTTPException(409, "Browser observation unavailable.")
        browser = BrowserSelection.model_validate(selection)
    try:
        grant = await worker_client().issue_observer_grant(
            actor_id=actor_id,
            browser_session_id=browser.browser_session_id,
            execution_id=browser.execution_id,
            journey_id=browser.journey_id,
            generation=browser.generation,
        )
    except RuntimeError:
        raise HTTPException(
            503, "The supervised browser owner is unavailable.",
        ) from None
    return LiveGrantResponse(
        ticket=grant.ticket, viewer_url=str(grant.viewer_url), browser=browser,
    )
