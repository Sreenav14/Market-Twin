"""Test Run HTTP endpoints."""

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

router = APIRouter(
    tags=["Test Runs"],
)


class CreateTestRunRequest(BaseModel):
    """Request for creating a MarketTwin test run."""

    target_id: UUID
    name: str | None = Field(default=None, min_length=1, max_length=80)
    testing_depth: Literal["low", "medium", "high"] = "medium"
    execution_mode: Literal["legacy_persona", "deep_feature_v1"] = "legacy_persona"
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
) -> TestRunResponse:
    """Convert repository data into an HTTP response."""

    return TestRunResponse(
        id=test_run.test_run_id,
        test_number=test_run.test_number,
        workspace_id=test_run.workspace_id,
        application_id=test_run.application_id,
        target_id=test_run.target_id,
        created_by_user_id=test_run.created_by_user_id,
        status=test_run.status,
        target_snapshot=test_run.target_snapshot,
        configuration_snapshot=(
            test_run.configuration_snapshot
        ),
        synthetic_fixture_approval_enabled=test_run.synthetic_fixture_approval_enabled,
        human_action_approvals_enabled=test_run.human_action_approvals_enabled,
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

            if payload.synthetic_fixture_approval:
                loopback_origins = _all_origins_loopback(target)
                if (
                    payload.execution_mode != "deep_feature_v1"
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
                payload.execution_mode != "deep_feature_v1"
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
            if payload.execution_mode == "deep_feature_v1":
                configuration_snapshot["execution_mode"] = payload.execution_mode
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

    return [
        test_run_response(test_run)
        for test_run in test_runs
    ]


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

    if test_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found.",
        )

    return test_run_response(test_run)


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
