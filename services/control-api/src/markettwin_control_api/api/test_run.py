"""Test Run HTTP endpoints."""

from uuid import UUID

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    status,
)
from pydantic import (
    BaseModel,
    Field,
    field_validator,
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
from markettwin_control_api.persistence.repositories import (
    ApplicationRepository,
    TargetAuthorizationRepository,
    TargetRecord,
    TargetRepository,
    TestRunRecord,
    TestRunRepository,
    WorkspaceRepository,
)

router = APIRouter(
    tags=["Test Runs"],
)


class CreateTestRunRequest(BaseModel):
    """Request for creating a MarketTwin test run."""

    target_id: UUID

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
    workspace_id: UUID
    application_id: UUID
    target_id: UUID
    created_by_user_id: UUID
    status: str
    target_snapshot: dict[str, object]
    configuration_snapshot: dict[str, object]


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
        workspace_id=test_run.workspace_id,
        application_id=test_run.application_id,
        target_id=test_run.target_id,
        created_by_user_id=test_run.created_by_user_id,
        status=test_run.status,
        target_snapshot=test_run.target_snapshot,
        configuration_snapshot=(
            test_run.configuration_snapshot
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

            configuration_snapshot: dict[str, object] = {
                "study_brief": payload.study_brief,
                "authorization_id_at_creation": str(
                    authorization.authorization_id
                ),
            }

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
            )

    return test_run_response(test_run)


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