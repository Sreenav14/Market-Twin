"""Authenticated human-control request and lease endpoints."""

from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from markettwin_database.models.execution import (
    ActionApprovalRequest,
    AgentExecution,
    BrowserSession,
    HumanActionRequest,
    HumanControlLease,
)
from pydantic import BaseModel, Field
from sqlalchemy import select

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import get_authenticated_user_id
from markettwin_control_api.api.permissions import TARGET_AUTHORIZATION_ROLES
from markettwin_control_api.config import get_settings
from markettwin_control_api.persistence.models import (
    ApplicationTarget,
    PersonaJourney,
    TargetAuthorization,
    TestRun,
    Workspace,
    WorkspaceMember,
)
from markettwin_control_api.persistence.repositories import (
    HumanActionConflictError,
    HumanActionExpiredError,
    HumanActionNotAuthorizedError,
    HumanActionRepository,
    TestRunRepository,
)
from markettwin_control_api.persistence.repositories.action_approval_repository import (
    ActionApprovalRepository,
    ApprovalRejectedError,
)
from markettwin_control_api.services.hitl_worker_client import HitlWorkerClient, ViewerGrant

router = APIRouter(tags=["Human Control"])


class ClaimRequest(BaseModel):
    lease_seconds: int = Field(default=30, ge=5, le=60)


class LeaseRequest(BaseModel):
    lease_id: UUID
    lease_token: str = Field(min_length=32, max_length=128, repr=False)
    generation: int = Field(ge=1)


class HumanActionResponse(BaseModel):
    id: UUID
    test_run_id: UUID
    execution_id: UUID
    browser_session_id: UUID
    request_type: str
    status: str
    created_at: datetime
    expires_at: datetime | None
    control_generation: int
    lease_id: UUID | None = None
    lease_expires_at: datetime | None = None


class ApprovalDecision(BaseModel):
    approved: bool


class ClaimResponse(BaseModel):
    request_id: UUID
    browser_session_id: UUID
    lease_id: UUID
    lease_token: str = Field(repr=False)
    generation: int
    expires_at: datetime
    viewer_url: str
    viewer_ticket: str = Field(repr=False)


def _worker_client() -> HitlWorkerClient:
    settings = get_settings()
    if (
        settings.hitl_internal_secret is None
        or len(settings.hitl_internal_secret.get_secret_value().strip()) < 32
    ):
        raise HTTPException(503, "The supervised browser owner is unavailable.")
    worker_url = urlsplit(settings.hitl_worker_url)
    local_worker = worker_url.hostname in {"127.0.0.1", "localhost", "::1"}
    if (
        worker_url.scheme != "https" and not (worker_url.scheme == "http" and local_worker)
    ) or worker_url.username or worker_url.password or worker_url.query or worker_url.fragment:
        raise HTTPException(503, "The supervised browser owner is unavailable.")
    return HitlWorkerClient(
        base_url=settings.hitl_worker_url,
        secret=settings.hitl_internal_secret,
        timeout_seconds=settings.hitl_worker_timeout_seconds,
    )


def _validate_viewer_url(grant: ViewerGrant) -> str:
    settings = get_settings()
    parsed = urlsplit(str(grant.viewer_url))
    web = urlsplit(settings.web_origin)
    local = settings.app_env == "local" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    expected_websocket_port = web.port or (443 if web.scheme == "https" else 80)
    viewer_port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    if (
        parsed.scheme != "wss" and not (parsed.scheme == "ws" and local)
    ) or (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.hostname != web.hostname
        or viewer_port != expected_websocket_port
        or parsed.path != "/api/v1/hitl-viewer"
    ):
        raise HTTPException(503, "The supervised browser owner is unavailable.")
    return str(grant.viewer_url)


async def _get_lease_envelope(
    *, request: Request, request_id: UUID, lease_id: UUID, actor_id: UUID
) -> dict[str, object]:
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        row = (
            await session.execute(
                select(HumanControlLease, HumanActionRequest, AgentExecution)
                .join(HumanActionRequest, HumanActionRequest.id == HumanControlLease.request_id)
                .join(AgentExecution, AgentExecution.id == HumanActionRequest.execution_id)
                .where(
                    HumanControlLease.id == lease_id,
                    HumanControlLease.request_id == request_id,
                    HumanControlLease.user_id == actor_id,
                )
            )
        ).one_or_none()
    if row is None:
        raise HTTPException(409, "Human action request is unavailable.")
    lease, action, execution = row
    return {
        "actor_id": str(actor_id),
        "request_id": str(action.id),
        "browser_session_id": str(action.browser_session_id),
        "lease_id": str(lease.id),
        "generation": lease.generation,
        "expires_at": lease.expires_at.isoformat(),
        "execution_id": str(action.execution_id),
        "journey_id": str(execution.journey_id),
    }


async def _get_request_generation(*, request: Request, request_id: UUID) -> int:
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        generation = await session.scalar(
            select(BrowserSession.control_generation)
            .join(HumanActionRequest, HumanActionRequest.browser_session_id == BrowserSession.id)
            .where(HumanActionRequest.id == request_id)
        )
    if generation is None:
        raise HTTPException(404, "Human action request not found.")
    return generation


def _csrf(request: Request) -> None:
    settings = get_settings()
    origin = request.headers.get("origin")
    if request.headers.get("x-markettwin-request") != "1" or origin != settings.web_origin:
        raise HTTPException(403, "Request origin was rejected.")


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, HumanActionNotAuthorizedError):
        return HTTPException(404, "Human action request not found.")
    if isinstance(exc, HumanActionExpiredError):
        return HTTPException(410, "Human action request expired.")
    if isinstance(exc, HumanActionConflictError):
        return HTTPException(409, "Human action request is unavailable.")
    return HTTPException(409, "Human action request was rejected.")


@router.get("/api/v1/test-runs/{test_run_id}/human-actions")
async def list_human_actions(test_run_id: UUID, request: Request) -> list[HumanActionResponse]:
    actor_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        async with session.begin():
            if (
                await TestRunRepository(session).get_for_user(
                    test_run_id=test_run_id,
                    user_id=actor_id,
                )
                is None
            ):
                raise HTTPException(404, "Test run not found.")
            now = datetime.now(UTC)
            rows = (
                await session.execute(
                    select(HumanActionRequest, BrowserSession, HumanControlLease)
                    .join(
                        BrowserSession, BrowserSession.id == HumanActionRequest.browser_session_id
                    )
                    .join(AgentExecution, AgentExecution.id == HumanActionRequest.execution_id)
                    .join(PersonaJourney, PersonaJourney.id == AgentExecution.journey_id)
                    .join(TestRun, TestRun.id == PersonaJourney.test_run_id)
                    .join(Workspace, Workspace.id == TestRun.workspace_id)
                    .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
                    .join(ApplicationTarget, ApplicationTarget.id == TestRun.target_id)
                    .join(
                        TargetAuthorization, TargetAuthorization.target_id == ApplicationTarget.id
                    )
                    .outerjoin(
                        HumanControlLease, HumanControlLease.request_id == HumanActionRequest.id
                    )
                    .where(
                        TestRun.id == test_run_id,
                        Workspace.status == "active",
                        Workspace.deleted_at.is_(None),
                        WorkspaceMember.user_id == actor_id,
                        WorkspaceMember.role.in_(TARGET_AUTHORIZATION_ROLES),
                        ApplicationTarget.status == "active",
                        ApplicationTarget.deleted_at.is_(None),
                        TargetAuthorization.status == "authorized",
                        TargetAuthorization.revoked_at.is_(None),
                        (TargetAuthorization.expires_at.is_(None))
                        | (TargetAuthorization.expires_at > now),
                )
                .order_by(HumanActionRequest.created_at)
                .limit(50)
                )
            ).all()
            return [
                HumanActionResponse(
                    id=req.id,
                    test_run_id=test_run_id,
                    execution_id=req.execution_id,
                    browser_session_id=req.browser_session_id,
                    request_type=req.request_type,
                    status=req.status,
                    created_at=req.created_at,
                    expires_at=req.expires_at,
                    control_generation=browser.control_generation,
                    lease_id=lease.id if lease and lease.released_at is None else None,
                    lease_expires_at=lease.expires_at
                    if lease and lease.released_at is None
                    else None,
                )
                for req, browser, lease in rows
            ]


@router.post("/api/v1/human-actions/{request_id}/claim")
async def claim_human_action(
    request_id: UUID,
    payload: ClaimRequest,
    request: Request,
) -> ClaimResponse:
    _csrf(request)
    worker = _worker_client()
    actor_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    try:
        async with database.session_factory() as session:
            async with session.begin():
                grant = await HumanActionRepository(session).claim(
                    request_id=request_id,
                    actor_id=actor_id,
                    lease_duration=timedelta(seconds=payload.lease_seconds),
                )
        try:
            viewer = await worker.issue_viewer_grant(
                actor_id=actor_id,
                request_id=grant.request_id,
                browser_session_id=grant.browser_session_id,
                lease_id=grant.lease_id,
                lease_token=grant.lease_token,
                generation=grant.generation,
                expires_at=grant.expires_at.isoformat(),
                execution_id=grant.execution_id,
                journey_id=grant.journey_id,
            )
            viewer_url = _validate_viewer_url(viewer)
        except (RuntimeError, HTTPException) as exc:
            try:
                async with database.session_factory() as session:
                    async with session.begin():
                        generation = await HumanActionRepository(session).abort_claim(
                            lease_id=grant.lease_id,
                            actor_id=actor_id,
                            lease_token=grant.lease_token,
                            generation=grant.generation,
                            expected_request_id=grant.request_id,
                        )
                await worker.notify(
                    path="/internal/hitl/leases/revoke",
                    payload={
                        "request_id": str(grant.request_id),
                        "lease_id": str(grant.lease_id),
                        "browser_session_id": str(grant.browser_session_id),
                        "generation": generation,
                    },
                )
            except Exception:
                pass
            raise HTTPException(503, "The supervised browser owner is unavailable.") from exc
        return ClaimResponse(
            request_id=grant.request_id,
            browser_session_id=grant.browser_session_id,
            lease_id=grant.lease_id,
            lease_token=grant.lease_token,
            generation=grant.generation,
            expires_at=grant.expires_at,
            viewer_url=viewer_url,
            viewer_ticket=viewer.ticket,
        )
    except (
        HumanActionNotAuthorizedError,
        HumanActionConflictError,
        HumanActionExpiredError,
    ) as exc:
        raise _error(exc) from exc


@router.post("/api/v1/human-actions/{request_id}/renew")
async def renew_human_action(
    request_id: UUID,
    payload: LeaseRequest,
    request: Request,
) -> dict[str, str]:
    _csrf(request)
    actor_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    try:
        async with database.session_factory() as session:
            async with session.begin():
                expires_at = await HumanActionRepository(session).renew(
                    lease_id=payload.lease_id,
                    actor_id=actor_id,
                    lease_token=payload.lease_token,
                    generation=payload.generation,
                    expected_request_id=request_id,
                )
        lease_row = await _get_lease_envelope(
            request=request, request_id=request_id, lease_id=payload.lease_id, actor_id=actor_id
        )
        try:
            await _worker_client().notify(
                path="/internal/hitl/leases/renew",
                payload={**lease_row, "lease_token": payload.lease_token},
            )
        except RuntimeError as exc:
            raise HTTPException(503, "The supervised browser owner is unavailable.") from exc
        return {"expires_at": expires_at.isoformat()}
    except (
        HumanActionNotAuthorizedError,
        HumanActionConflictError,
        HumanActionExpiredError,
    ) as exc:
        raise _error(exc) from exc


@router.post("/api/v1/human-actions/{request_id}/cancel")
async def cancel_human_action(request_id: UUID, request: Request) -> dict[str, str]:
    _csrf(request)
    actor_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    try:
        async with database.session_factory() as session:
            async with session.begin():
                record = await HumanActionRepository(session).cancel(
                    request_id=request_id,
                    actor_id=actor_id,
                )
        generation = await _get_request_generation(request=request, request_id=request_id)
        try:
            await _worker_client().notify(
                path="/internal/hitl/leases/revoke",
                payload={"request_id": str(request_id), "generation": generation},
            )
        except HTTPException:
            pass
        except RuntimeError:
            pass
        return {"id": str(record.request_id), "status": record.status}
    except (
        HumanActionNotAuthorizedError,
        HumanActionConflictError,
        HumanActionExpiredError,
    ) as exc:
        raise _error(exc) from exc


@router.post("/api/v1/human-actions/{request_id}/release")
async def release_human_action(
    request_id: UUID,
    payload: LeaseRequest,
    request: Request,
) -> dict[str, int]:
    _csrf(request)
    actor_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    try:
        async with database.session_factory() as session:
            async with session.begin():
                generation = await HumanActionRepository(session).release_for_verification(
                    lease_id=payload.lease_id,
                    actor_id=actor_id,
                    lease_token=payload.lease_token,
                    generation=payload.generation,
                    expected_request_id=request_id,
                )
        lease_row = await _get_lease_envelope(
            request=request, request_id=request_id, lease_id=payload.lease_id, actor_id=actor_id
        )
        try:
            await _worker_client().notify(
                path="/internal/hitl/leases/revoke",
                payload={
                    "lease_id": str(payload.lease_id),
                    "browser_session_id": lease_row["browser_session_id"],
                    "generation": generation,
                },
            )
        except HTTPException:
            pass
        except RuntimeError:
            pass
        return {"generation": generation}
    except (
        HumanActionNotAuthorizedError,
        HumanActionConflictError,
        HumanActionExpiredError,
    ) as exc:
        raise _error(exc) from exc


@router.get("/api/v1/test-runs/{test_run_id}/action-approvals")
async def list_action_approvals(test_run_id: UUID, request: Request) -> list[dict[str, object]]:
    actor_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        async with session.begin():
            if (
                await TestRunRepository(session).get_for_user(
                    test_run_id=test_run_id,
                    user_id=actor_id,
                )
                is None
            ):
                raise HTTPException(404, "Test run not found.")
            now = datetime.now(UTC)
            rows = await session.execute(
                select(ActionApprovalRequest, AgentExecution.journey_id)
                .join(AgentExecution, AgentExecution.id == ActionApprovalRequest.execution_id)
                .join(TestRun, TestRun.id == ActionApprovalRequest.test_run_id)
                .join(Workspace, Workspace.id == TestRun.workspace_id)
                .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
                .join(ApplicationTarget, ApplicationTarget.id == TestRun.target_id)
                .join(TargetAuthorization, TargetAuthorization.target_id == ApplicationTarget.id)
                .where(
                    TestRun.id == test_run_id,
                    Workspace.status == "active",
                    Workspace.deleted_at.is_(None),
                    WorkspaceMember.user_id == actor_id,
                    WorkspaceMember.role.in_(TARGET_AUTHORIZATION_ROLES),
                    ApplicationTarget.status == "active",
                    ApplicationTarget.deleted_at.is_(None),
                    TargetAuthorization.status == "authorized",
                    TargetAuthorization.revoked_at.is_(None),
                    (TargetAuthorization.expires_at.is_(None))
                    | (TargetAuthorization.expires_at > now),
                    ActionApprovalRequest.status.in_(("pending", "approved")),
                )
            )
            return [
                {
                    "id": str(item.id),
                    "action_summary": item.action_summary,
                    "environment": item.environment,
                    "status": item.status,
                    "expires_at": item.expires_at.isoformat(),
                    "step_id": item.step_id,
                    "journey_id": str(journey_id),
                }
                for item, journey_id in rows.unique()
            ]


@router.post("/api/v1/action-approvals/{approval_id}/decision")
async def decide_action_approval(
    approval_id: UUID,
    payload: ApprovalDecision,
    request: Request,
) -> dict[str, str]:
    _csrf(request)
    actor_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    try:
        async with database.session_factory() as session:
            async with session.begin():
                result = await ActionApprovalRepository(session).decide(
                    approval_id=approval_id,
                    actor_id=actor_id,
                    approved=payload.approved,
                )
        return {"id": str(result.id), "status": result.status}
    except ApprovalRejectedError as exc:
        raise HTTPException(409, "Approval is no longer available.") from exc
