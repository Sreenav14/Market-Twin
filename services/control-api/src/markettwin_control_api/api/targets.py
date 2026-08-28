"""Application target HTTP endpoints."""

from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    status,
)
from pydantic import (
    AnyHttpUrl,
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
    TargetRecord,
    TargetRepository,
    WorkspaceRepository,
)

router = APIRouter(
    tags=["Targets"],
)


@dataclass(frozen=True, slots=True)
class ParsedOrigin:
    """Normalized origin derived from a target URL."""

    scheme: str
    hostname: str
    port: int | None


class CreateTargetRequest(BaseModel):
    """Request for creating an application target."""

    name: str = Field(
        min_length=1,
        max_length=200,
    )

    environment: str = Field(
        min_length=1,
        max_length=64,
    )

    base_url: AnyHttpUrl

    requires_auth: bool = False

    @field_validator(
        "name",
        "environment",
    )
    @classmethod
    def clean_required_text(
        cls,
        value: str,
    ) -> str:
        """Reject whitespace-only values."""

        cleaned = value.strip()

        if not cleaned:
            raise ValueError(
                "Value cannot be empty."
            )

        return cleaned


class AllowedOriginResponse(BaseModel):
    """Origin that the target may access."""

    scheme: str
    hostname: str
    port: int | None
    include_subdomains: bool


class TargetResponse(BaseModel):
    """Application target returned by the API."""

    id: UUID
    application_id: UUID
    name: str
    environment: str
    base_url: str
    requires_auth: bool
    status: str
    allowed_origins: list[AllowedOriginResponse]


def parse_origin(
    base_url: str,
) -> ParsedOrigin:
    """Derive and normalize a browser origin."""

    parsed = urlsplit(base_url)

    if parsed.username is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Target URLs cannot contain "
                "embedded credentials."
            ),
        )

    if parsed.password is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Target URLs cannot contain "
                "embedded credentials."
            ),
        )

    hostname = parsed.hostname

    if hostname is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Target URL requires a hostname.",
        )

    try:
        port = parsed.port
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Target URL contains an invalid port.",
        ) from error

    scheme = parsed.scheme.lower()
    hostname = hostname.rstrip(".").lower()

    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Target URL requires a hostname.",
        )

    # Normalize default HTTP/S ports.
    if (
        scheme == "http"
        and port == 80
    ) or (
        scheme == "https"
        and port == 443
    ):
        port = None

    return ParsedOrigin(
        scheme=scheme,
        hostname=hostname,
        port=port,
    )


def target_response(
    target: TargetRecord,
) -> TargetResponse:
    """Convert repository target data to HTTP data."""

    return TargetResponse(
        id=target.target_id,
        application_id=target.application_id,
        name=target.name,
        environment=target.environment,
        base_url=target.base_url,
        requires_auth=target.requires_auth,
        status=target.status,
        allowed_origins=[
            AllowedOriginResponse(
                scheme=origin.scheme,
                hostname=origin.hostname,
                port=origin.port,
                include_subdomains=(
                    origin.include_subdomains
                ),
            )
            for origin in target.allowed_origins
        ],
    )


@router.post(
    "/api/v1/applications/{application_id}/targets",
    response_model=TargetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_target(
    application_id: UUID,
    payload: CreateTargetRequest,
    request: Request,
) -> TargetResponse:
    """Create a target for an accessible application."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    normalized_base_url = str(
        payload.base_url
    )

    origin = parse_origin(
        normalized_base_url
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            application_repository = (
                ApplicationRepository(
                    database_session
                )
            )

            application = (
                await application_repository.get_for_user(
                    application_id=application_id,
                    user_id=user_id,
                )
            )

            if application is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Application not found.",
                )

            workspace_repository = (
                WorkspaceRepository(
                    database_session
                )
            )

            workspace = (
                await workspace_repository.get_for_user(
                    workspace_id=application.workspace_id,
                    user_id=user_id,
                )
            )

            if workspace is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Application not found.",
                )

            if (
                workspace.role
                not in WORKSPACE_WRITE_ROLES
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Your workspace role cannot "
                        "create targets."
                    ),
                )

            target_repository = TargetRepository(
                database_session
            )

            target = await target_repository.create(
                application_id=application_id,
                name=payload.name,
                environment=payload.environment,
                base_url=normalized_base_url,
                requires_auth=payload.requires_auth,
                scheme=origin.scheme,
                hostname=origin.hostname,
                port=origin.port,
            )

    return target_response(target)


@router.get(
    "/api/v1/applications/{application_id}/targets",
    response_model=list[TargetResponse],
)
async def list_targets(
    application_id: UUID,
    request: Request,
) -> list[TargetResponse]:
    """List targets belonging to an accessible application."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            application_repository = (
                ApplicationRepository(
                    database_session
                )
            )

            application = (
                await application_repository.get_for_user(
                    application_id=application_id,
                    user_id=user_id,
                )
            )

            if application is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Application not found.",
                )

            target_repository = TargetRepository(
                database_session
            )

            targets = (
                await target_repository.list_for_application(
                    application_id=application_id
                )
            )

    return [
        target_response(target)
        for target in targets
    ]


@router.get(
    "/api/v1/targets/{target_id}",
    response_model=TargetResponse,
)
async def get_target(
    target_id: UUID,
    request: Request,
) -> TargetResponse:
    """Return one target available to the current user."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            repository = TargetRepository(
                database_session
            )

            target = await repository.get_for_user(
                target_id=target_id,
                user_id=user_id,
            )

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target not found.",
        )

    return target_response(target)