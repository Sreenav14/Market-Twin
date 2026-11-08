"""Test Run HTTP endpoints."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    status,
)
from markettwin_database.repositories import (
    OutboxRepository,
)
from markettwin_shared.action_approval import SensitiveActionRule
from markettwin_shared.auth_verification import AuthVerificationPolicy
from markettwin_shared.run_kind import resolve_run_kind
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from markettwin_control_api.api.auth import (
    get_database_runtime,
)
from markettwin_control_api.api.dependencies import (
    get_authenticated_user_id,
)
from markettwin_control_api.api.permissions import (
    WORKSPACE_WRITE_ROLES,
)
from markettwin_control_api.config import get_settings
from markettwin_control_api.knowledge.repository import IngestionRepository
from markettwin_control_api.persistence.repositories import (
    ApplicationRepository,
    TargetAuthorizationRepository,
    TargetRecord,
    TargetRepository,
    TestRunRecord,
    TestRunRepository,
    WorkspaceRepository,
)
from markettwin_control_api.services import (
    RunDispatchService,
    RunNotQueueableError,
)
from markettwin_control_api.services.run_readiness import require_run_ready, stalled_run_reason

router = APIRouter(
    tags=["Test Runs"],
)


class CreateTestRunRequest(BaseModel):
    """Request for creating a MarketTwin test run."""

    target_id: UUID
    name: str | None = Field(default=None, min_length=1, max_length=80)
    testing_depth: Literal["low", "medium", "high"] = "medium"
    execution_mode: Literal[
        "legacy_persona", "deep_feature_v1", "discovery_contract_v1", "harness_v1",
    ] = "discovery_contract_v1"
    # Unified run kind (U-P0-05): the only way to choose what a new
    # run does. The execution_mode field above survives only as a
    # rejection sentinel — sending it is a 422 (validator below, U-P8).
    run_kind: Literal["explore_test", "persona", "slop"] | None = None
    frozen_contract_source_run_id: UUID | None = None
    knowledge_entry_ids: list[UUID] = Field(default_factory=list[UUID], max_length=10)
    auth_verification: AuthVerificationPolicy | None = None
    auth_mode: Literal["required", "optional"] | None = None
    runtime_human_assistance: bool = True
    synthetic_fixture_approval: bool = False
    human_action_approvals: bool = False
    sensitive_action_rules: list[SensitiveActionRule] = Field(
        default_factory=list[SensitiveActionRule], max_length=16,
    )

    @model_validator(mode="after")
    def retired_fields_are_rejected(self) -> "CreateTestRunRequest":
        # U-P8: the execution_mode alias and frozen-contract replay
        # were retired with the legacy engines. Sending either is a
        # 422 — new runs are created with run_kind only.
        if "execution_mode" in self.model_fields_set:
            raise ValueError(
                "execution_mode was retired; create runs with run_kind instead."
            )
        if self.frozen_contract_source_run_id is not None:
            raise ValueError(
                "Frozen contract replay was retired with the legacy engines."
            )
        return self

    @model_validator(mode="after")
    def authentication_mode_requires_policy(self) -> "CreateTestRunRequest":
        if self.auth_mode is not None and self.auth_verification is None:
            raise ValueError(
                "Authentication mode requires an approved identity verification policy."
            )
        return self

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Test name cannot be blank.")
        return value

    @field_validator("knowledge_entry_ids")
    @classmethod
    def unique_knowledge_entries(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("Select each knowledge set once.")
        return value

    study_brief: str = Field(
        min_length=10,
        max_length=4000,
    )

    @field_validator("study_brief")
    @classmethod
    def clean_study_brief(
        cls,
        value: str,
    ) -> str:
        """Normalize the study brief."""

        cleaned = value.strip()

        if not cleaned:
            raise ValueError(
                "Study brief is required."
            )

        return cleaned


class TestRunResponse(BaseModel):
    """Test run returned by the Control API."""

    id: UUID
    created_at: datetime
    test_number: int | None
    workspace_id: UUID
    application_id: UUID
    target_id: UUID
    created_by_user_id: UUID
    status: str
    target_snapshot: dict[str, object]
    configuration_snapshot: dict[str, object]
    synthetic_fixture_approval_enabled: bool = False
    human_action_approvals_enabled: bool = False
    status_reason: str | None = None
    # The run's unified kind, always resolved (column first, legacy
    # snapshot translation as fallback) so clients never guess.
    run_kind: str = "explore_test"


def build_target_snapshot(
    target: TargetRecord,
) -> dict[str, object]:
    """Freeze the target configuration used by this run."""

    return {
        "target_id": str(target.target_id),
        "application_id": str(target.application_id),
        "name": target.name,
        "environment": target.environment,
        "base_url": target.base_url,
        "requires_auth": target.requires_auth,
        "allowed_origins": [
            {
                "scheme": origin.scheme,
                "hostname": origin.hostname,
                "port": origin.port,
                "include_subdomains": (
                    origin.include_subdomains
                ),
            }
            for origin in target.allowed_origins
        ],
    }


def test_run_response(
    test_run: TestRunRecord,
    status_reason: str | None = None,
) -> TestRunResponse:
    """Convert repository data into an HTTP response."""

    return TestRunResponse(
        id=test_run.test_run_id,
        created_at=test_run.created_at,
        test_number=test_run.test_number,
        workspace_id=test_run.workspace_id,
        application_id=test_run.application_id,
        target_id=test_run.target_id,
        created_by_user_id=test_run.created_by_user_id,
        status=test_run.status,
        status_reason=status_reason,
        target_snapshot=test_run.target_snapshot,
        configuration_snapshot=(
            test_run.configuration_snapshot
        ),
        synthetic_fixture_approval_enabled=test_run.synthetic_fixture_approval_enabled,
        human_action_approvals_enabled=test_run.human_action_approvals_enabled,
        run_kind=resolve_run_kind(
            run_kind_column=test_run.run_kind,
            configuration_snapshot=test_run.configuration_snapshot,
        ),
    )


@router.post(
    "/api/v1/applications/{application_id}/test-runs",
    response_model=TestRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_test_run(
    application_id: UUID,
    payload: CreateTestRunRequest,
    request: Request,
) -> TestRunResponse:
    """Create a draft run against an authorized target."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            application_repository = ApplicationRepository(
                database_session
            )

            application = await application_repository.get_for_user(
                application_id=application_id,
                user_id=user_id,
            )

            if application is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Application not found.",
                )

            workspace_repository = WorkspaceRepository(
                database_session
            )

            workspace = await workspace_repository.get_for_user(
                workspace_id=application.workspace_id,
                user_id=user_id,
            )

            if workspace is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Application not found.",
                )

            if workspace.role not in WORKSPACE_WRITE_ROLES:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Your workspace role cannot "
                        "create test runs."
                    ),
                )

            target_repository = TargetRepository(
                database_session
            )

            target = await target_repository.get_for_user(
                target_id=payload.target_id,
                user_id=user_id,
            )

            if (
                target is None
                or target.application_id != application_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Target not found for application.",
                )

            authorization_repository = (
                TargetAuthorizationRepository(
                    database_session
                )
            )

            authorization = (
                await authorization_repository.get_active(
                    target_id=target.target_id
                )
            )

            if authorization is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Target is not currently authorized "
                        "for testing."
                    ),
                )

            target_snapshot = build_target_snapshot(
                target
            )

            if (
                target.requires_auth and payload.auth_verification is None
                and not payload.runtime_human_assistance
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Authenticated targets require an approved identity verification policy."
                    ),
                )

            if payload.auth_verification is not None:
                if target.requires_auth and payload.auth_mode == "optional":
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Protected targets require authentication before execution.",
                    )
                if not all(_auth_origin_is_allowed(origin, target) for origin in (
                    payload.auth_verification.origin, *payload.auth_verification.auth_only_origins,
                )):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=(
                            "Authentication and SSO origins must be authorized "
                            "for this target."
                        ),
                    )

            # The unified kind for this run (U-P8: run_kind only; the
            # legacy alias is rejected at validation above).
            effective_run_kind = payload.run_kind or "explore_test"

            if payload.synthetic_fixture_approval:
                loopback_origins = _all_origins_loopback(target)
                if (
                    effective_run_kind != "explore_test"
                    or target.environment not in {"local", "test"}
                    or not loopback_origins
                ):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=(
                            "Synthetic fixture approval requires a deep run on an all-loopback "
                            "local/test target."
                        ),
                    )

            if payload.human_action_approvals and (
                effective_run_kind not in {"explore_test", "persona"}
                or target.environment not in {"local", "development", "test", "staging"}
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Sensitive action approvals require an authorized local, test, "
                        "development, or staging target and deep feature execution."
                    ),
                )

            configuration_snapshot: dict[str, object] = {
                "runtime_human_assistance": payload.runtime_human_assistance,
                "study_brief": payload.study_brief,
                "testing_depth": payload.testing_depth,
                "authorization_id_at_creation": str(
                    authorization.authorization_id
                ),
            }
            if payload.name is not None:
                configuration_snapshot["test_name"] = payload.name
            if payload.auth_verification is not None:
                configuration_snapshot["auth_mode"] = payload.auth_mode or "required"
                configuration_snapshot["auth_verification"] = payload.auth_verification.model_dump(
                    mode="json"
                )
            if payload.sensitive_action_rules:
                configuration_snapshot["sensitive_action_rules"] = [
                    rule.model_dump(mode="json") for rule in payload.sensitive_action_rules
                ]
            if payload.knowledge_entry_ids:
                knowledge_repository = IngestionRepository(database_session)
                selected_knowledge: list[dict[str, object]] = []
                for entry_id in payload.knowledge_entry_ids:
                    record = await knowledge_repository.get(
                        application.workspace_id, entry_id,
                        application_id=application.application_id,
                    )
                    if record is None:
                        raise HTTPException(
                            status_code=404,
                            detail="Selected knowledge is not attached to this application.",
                        )
                    if record.version.status != "approved":
                        raise HTTPException(
                            status_code=409,
                            detail="Selected knowledge must be approved before testing.",
                        )
                    preview = record.entry.preview
                    selected_knowledge.append(
                        {
                            "id": str(record.entry.id),
                            "name": record.blueprint.name,
                            "source_name": record.asset.original_filename,
                            "roles": record.pin.roles,
                            "application_knowledge": preview["application_knowledge"],
                            "artifacts": preview["artifacts"],
                            "skills": preview["skills"],
                        }
                    )
                configuration_snapshot["knowledge"] = selected_knowledge

            repository = TestRunRepository(
                database_session
            )

            test_run = await repository.create(
                workspace_id=application.workspace_id,
                application_id=application_id,
                target_id=target.target_id,
                created_by_user_id=user_id,
                target_snapshot=target_snapshot,
                configuration_snapshot=(
                    configuration_snapshot
                ),
                synthetic_fixture_approval_enabled=payload.synthetic_fixture_approval,
                human_action_approvals_enabled=(
                    payload.human_action_approvals or payload.synthetic_fixture_approval
                ),
                run_kind=effective_run_kind,
            )
    return test_run_response(test_run)


def _auth_origin_is_allowed(origin: str, target: TargetRecord) -> bool:
    """Require exact origin membership, honoring only explicit subdomain grants."""
    from urllib.parse import urlsplit

    parsed = urlsplit(origin)
    try:
        port = parsed.port
    except ValueError:
        return False
    for allowed in target.allowed_origins:
        if parsed.scheme != allowed.scheme or port != allowed.port:
            continue
        if parsed.hostname == allowed.hostname:
            return True
        if (
            allowed.include_subdomains
            and parsed.hostname is not None
            and parsed.hostname.endswith("." + allowed.hostname)
        ):
            return True
    return False


def _all_origins_loopback(target: TargetRecord) -> bool:
    if not target.allowed_origins:
        return False
    try:
        base_host = urlsplit(target.base_url).hostname
        if base_host != "localhost" and not ip_address(base_host or "").is_loopback:
            return False
    except ValueError:
        return False
    for origin in target.allowed_origins:
        if origin.scheme != "http" or origin.include_subdomains:
            return False
        if origin.hostname == "localhost":
            continue
        try:
            if ip_address(origin.hostname).is_loopback:
                continue
        except ValueError:
            pass
        return False
    return True


@router.get(
    "/api/v1/applications/{application_id}/test-runs",
    response_model=list[TestRunResponse],
)
async def list_test_runs(
    application_id: UUID,
    request: Request,
) -> list[TestRunResponse]:
    """List runs belonging to an accessible application."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            application_repository = ApplicationRepository(
                database_session
            )

            application = await application_repository.get_for_user(
                application_id=application_id,
                user_id=user_id,
            )

            if application is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Application not found.",
                )

            repository = TestRunRepository(
                database_session
            )

            test_runs = await repository.list_for_application(
                application_id=application_id
            )
            responses = [test_run_response(run, await stalled_run_reason(
                database_session, run_id=run.test_run_id, status=run.status,
                created_at=run.created_at,
            )) for run in test_runs]

    return responses


@router.get(
    "/api/v1/test-runs/{test_run_id}",
    response_model=TestRunResponse,
)
async def get_test_run(
    test_run_id: UUID,
    request: Request,
) -> TestRunResponse:
    """Return a test run available to the current user."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            repository = TestRunRepository(
                database_session
            )

            test_run = await repository.get_for_user(
                test_run_id=test_run_id,
                user_id=user_id,
            )
            reason = await stalled_run_reason(
                database_session, run_id=test_run.test_run_id, status=test_run.status,
                created_at=test_run.created_at,
            ) if test_run is not None else None

    if test_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found.",
        )

    return test_run_response(test_run, reason)


class BoardItemResponse(BaseModel):
    """One item on a run's Board (U-P1-07)."""

    item_id: str
    state_id: str
    case_id: str
    role: str
    name: str
    status: str
    blocker: str | None = None
    attempts: int = 0
    page_url: str = ""


class BoardResponse(BaseModel):
    """A run's Board: counts plus every item, in Board order."""

    run_id: UUID
    run_status: str
    run_kind: str
    total: int
    counts: dict[str, int]
    items: list[BoardItemResponse]


def _board_response(test_run: TestRunRecord) -> BoardResponse:
    board = test_run.configuration_snapshot.get("harness_state")
    if not isinstance(board, dict):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This run has no board.",
        )
    states = board.get("states")
    state_urls: dict[str, str] = {}
    if isinstance(states, dict):
        for state_id, state_doc in states.items():
            if isinstance(state_doc, dict):
                state_urls[str(state_id)] = str(state_doc.get("url", ""))
    raw_items = board.get("items")
    item_docs: list[dict[str, object]] = []
    if isinstance(raw_items, dict):
        item_docs = [v for v in raw_items.values() if isinstance(v, dict)]
    elif isinstance(raw_items, list):
        item_docs = [v for v in raw_items if isinstance(v, dict)]
    counts: dict[str, int] = {}
    items: list[BoardItemResponse] = []
    for doc in item_docs:
        item_status = str(doc.get("status", "pending"))
        counts[item_status] = counts.get(item_status, 0) + 1
        items.append(BoardItemResponse(
            item_id=str(doc.get("item_id", "")),
            state_id=str(doc.get("state_id", "")),
            case_id=str(doc.get("case_id", "")),
            role=str(doc.get("role", "")),
            name=str(doc.get("name", "")),
            status=item_status,
            blocker=(str(doc["blocker"]) if doc.get("blocker") else None),
            attempts=int(doc.get("attempts", 0) or 0),
            page_url=state_urls.get(str(doc.get("state_id", "")), ""),
        ))
    return BoardResponse(
        run_id=test_run.test_run_id,
        run_status=test_run.status,
        run_kind=resolve_run_kind(
            run_kind_column=test_run.run_kind,
            configuration_snapshot=test_run.configuration_snapshot,
        ),
        total=len(items),
        counts=counts,
        items=items,
    )


async def _get_run_for_board(test_run_id: UUID, request: Request) -> TestRunRecord:
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as database_session:
        async with database_session.begin():
            repository = TestRunRepository(database_session)
            test_run = await repository.get_for_user(
                test_run_id=test_run_id, user_id=user_id,
            )
    if test_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found.",
        )
    return test_run


@router.get(
    "/api/v1/test-runs/{test_run_id}/board",
    response_model=BoardResponse,
)
async def get_test_run_board(
    test_run_id: UUID,
    request: Request,
) -> BoardResponse:
    """Return the run's Board (the live work list of the unified engine)."""

    test_run = await _get_run_for_board(test_run_id, request)
    return _board_response(test_run)


@router.post(
    "/api/v1/test-runs/{test_run_id}/board/items/{item_id}/disable",
    response_model=BoardResponse,
)
async def disable_board_item(
    test_run_id: UUID,
    item_id: str,
    request: Request,
) -> BoardResponse:
    """Turn off one pending Board item (owner_disabled).

    Only while the run is not testing: the engine owns Board writes
    during a run, and a mid-run edit here would be overwritten by the
    engine's next Board persist.
    """

    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as database_session:
        async with database_session.begin():
            repository = TestRunRepository(database_session)
            test_run = await repository.get_for_user(
                test_run_id=test_run_id, user_id=user_id,
            )
            if test_run is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Test run not found.",
                )
            if test_run.status == "running":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Items can be turned off only while the run "
                        "is not testing."
                    ),
                )
            snapshot = test_run.configuration_snapshot
            board = snapshot.get("harness_state")
            if not isinstance(board, dict):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="This run has no board.",
                )
            # The GET path serves both stored shapes (dict keyed by
            # item id, or a plain list); disabling must accept the
            # same shapes and write back in the shape it found.
            raw_items = board.get("items")
            list_shaped = isinstance(raw_items, list)
            if isinstance(raw_items, dict):
                items = dict(raw_items)
            elif list_shaped:
                items = {
                    str(doc.get("item_id", "")): doc
                    for doc in raw_items
                    if isinstance(doc, dict)
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="This run has no board.",
                )
            item_doc = items.get(item_id)
            if not isinstance(item_doc, dict):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Board item not found.",
                )
            if item_doc.get("status") != "pending":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Only a pending item can be turned off.",
                )
            updated_item = {**item_doc, "status": "owner_disabled"}
            if list_shaped:
                new_items: object = [
                    updated_item
                    if isinstance(doc, dict)
                    and str(doc.get("item_id", "")) == item_id
                    else doc
                    for doc in raw_items
                ]
            else:
                items[item_id] = updated_item
                new_items = items
            updated_snapshot = {
                **snapshot, "harness_state": {**board, "items": new_items},
            }
            await repository.update_configuration_snapshot(
                test_run_id=test_run_id,
                configuration_snapshot=updated_snapshot,
            )
            test_run = replace(
                test_run, configuration_snapshot=updated_snapshot,
            )
    return _board_response(test_run)


class ParkResponse(BaseModel):
    """A parked run's live-park window (U-P4)."""

    parked_at: str
    deadline_at: str


@router.post(
    "/api/v1/test-runs/{test_run_id}/park/extend",
    response_model=ParkResponse,
)
async def extend_park(
    test_run_id: UUID,
    request: Request,
) -> ParkResponse:
    """Extend a parked run's deadline, up to 30 minutes from the park.

    The window is owner time, not agent time: extending never resumes
    the run and never changes any item — it only moves the deadline
    the countdown shows.
    """

    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as database_session:
        async with database_session.begin():
            repository = TestRunRepository(database_session)
            test_run = await repository.get_for_user(
                test_run_id=test_run_id, user_id=user_id,
            )
            if test_run is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Test run not found.",
                )
            park = test_run.configuration_snapshot.get("harness_park")
            if test_run.status != "awaiting_human" or not isinstance(park, dict):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This run is not parked.",
                )
            try:
                parked_at = datetime.fromisoformat(str(park["parked_at"]))
            except (KeyError, ValueError):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This run is not parked.",
                ) from None
            cap = parked_at + timedelta(minutes=30)
            now = datetime.now(UTC)
            if now >= cap:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The park window is exhausted; resume or end the run.",
                )
            new_deadline = min(now + timedelta(minutes=15), cap)
            updated_park = {**park, "deadline_at": new_deadline.isoformat()}
            updated_snapshot = {
                **test_run.configuration_snapshot, "harness_park": updated_park,
            }
            await repository.update_configuration_snapshot(
                test_run_id=test_run_id,
                configuration_snapshot=updated_snapshot,
            )
    return ParkResponse(
        parked_at=str(park["parked_at"]), deadline_at=new_deadline.isoformat(),
    )


@router.post(
    "/api/v1/test-runs/{test_run_id}/start",
    response_model=TestRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_test_run(
      test_run_id: UUID,
    request: Request,
) -> TestRunResponse:
    """Queue one authorized draft TestRun for execution."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            test_run_repository = TestRunRepository(
                database_session
            )

            test_run = await test_run_repository.get_for_user(
                test_run_id=test_run_id,
                user_id=user_id,
            )

            if test_run is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Test run not found.",
                )

            if test_run.status != "draft":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Test run has already been started.",
                )

            if test_run.configuration_snapshot.get("frozen_contract_source_run_id"):
                # The contract start endpoint this check once pointed
                # to was retired with the legacy engines (U-P8); the
                # honest answer now is that such a run can never be
                # started, not a direction to a missing endpoint.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "This run was created by the retired contract "
                        "replay flow and can no longer be started. "
                        "Create a new run instead."
                    ),
                )

            workspace_repository = WorkspaceRepository(
                database_session
            )

            workspace = await workspace_repository.get_for_user(
                workspace_id=test_run.workspace_id,
                user_id=user_id,
            )

            if workspace is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Test run not found.",
                )

            if workspace.role not in WORKSPACE_WRITE_ROLES:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Your workspace role cannot "
                        "start test runs."
                    ),
                )

            target_repository = TargetRepository(
                database_session
            )

            target = await target_repository.get_for_user(
                target_id=test_run.target_id,
                user_id=user_id,
            )

            if target is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Target is not currently "
                        "available for testing."
                    ),
                )

            authorization_repository = (
                TargetAuthorizationRepository(
                    database_session
                )
            )

            authorization = (
                await authorization_repository.get_active(
                    target_id=target.target_id
                )
            )

            if authorization is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Target is not currently authorized "
                        "for testing."
                    ),
                )

            await require_run_ready(database_session, get_settings())
            dispatch_service = RunDispatchService(
                test_run_repository=test_run_repository,
                outbox_repository=OutboxRepository(
                    database_session
                ),
            )

            try:
                queued_run = await dispatch_service.queue(
                    test_run_id=test_run_id
                )
            except RunNotQueueableError as error:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Test run has already been started."
                    ),
                ) from error

    return test_run_response(queued_run)
