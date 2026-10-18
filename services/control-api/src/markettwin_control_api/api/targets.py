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
    ValidationError,
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
    scope_parent_id: UUID | None = None


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
        scope_parent_id=target.scope_parent_id,
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

class RequestScopeRevision(BaseModel):
    """A requested exact-origin scope, requiring separate authorization."""

    name: str = Field(min_length=1, max_length=200)
    origins: list[str] = Field(min_length=1, max_length=32)
    request_basis: str = Field(min_length=10, max_length=2000)

    @field_validator("name", "request_basis")
    @classmethod
    def clean_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank.")
        return value

    @field_validator("request_basis")
    @classmethod
    def sufficient_basis(cls, value: str) -> str:
        if len(value) < 10:
            raise ValueError("Explain the requested scope in at least 10 characters.")
        return value


def exact_scope_origins(payload: RequestScopeRevision, base_url: str):
    """Reject wildcard, credential, path, query and fragment scope ambiguity."""
    from markettwin_control_api.persistence.repositories.target_repository import (
        AllowedOriginRecord,
    )

    origins: list[AllowedOriginRecord] = []
    for value in payload.origins:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"} or not parsed.hostname
            or "*" in value or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment or parsed.username or parsed.password
            or value != value.strip() or "\\" in value
            or any(ord(character) <= 32 for character in value)
        ):
            raise HTTPException(422, "Use exact HTTP(S) origins without paths or credentials.")
        try:
            normalized = str(AnyHttpUrl(value))
        except ValidationError as error:
            raise HTTPException(422, "Invalid exact HTTP(S) origin.") from error
        origin = parse_origin(normalized)
        if origin.port == 0:
            raise HTTPException(422, "Origin port must be between 1 and 65535.")
        record = AllowedOriginRecord(origin.scheme, origin.hostname, origin.port, False)
        if record in origins:
            raise HTTPException(422, "Each normalized origin must appear only once.")
        origins.append(record)
    base = parse_origin(base_url)
    if AllowedOriginRecord(base.scheme, base.hostname, base.port, False) not in origins:
        raise HTTPException(422, "The target base origin must remain in the requested scope.")
    return tuple(origins)


@router.post(
    "/api/v1/targets/{target_id}/scope-revisions",
    response_model=TargetResponse, status_code=status.HTTP_201_CREATED,
)
async def request_scope_revision(
    target_id: UUID, payload: RequestScopeRevision, request: Request,
) -> TargetResponse:
    """Create a new pending scope without changing this target or existing runs."""
    from markettwin_control_api.api.target_authorizations import (
        require_authorization_role,
        require_target_access,
    )

    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        async with session.begin():
            parent = await require_target_access(
                database_session=session, target_id=target_id, user_id=user_id,
            )
            await require_authorization_role(
                database_session=session, target=parent, user_id=user_id,
            )
            origins = exact_scope_origins(payload, parent.base_url)
            revision = await TargetRepository(session).create_scope_revision(
                parent=parent, name=payload.name, origins=origins,
            )
            await TargetAuthorizationRepository(session).request_scope_authorization(
                target_id=revision.target_id, user_id=user_id,
                request_basis=payload.request_basis,
            )
    return target_response(revision)


@router.get(
    "/api/v1/targets/{target_id}/scope-revisions", response_model=list[TargetResponse],
)
async def list_scope_revisions(target_id: UUID, request: Request) -> list[TargetResponse]:
    """List pending or approved revisions visible to this workspace member."""
    from markettwin_control_api.api.target_authorizations import require_target_access

    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        async with session.begin():
            parent = await require_target_access(
                database_session=session, target_id=target_id, user_id=user_id,
            )
            targets = await TargetRepository(session).list_for_application(
                application_id=parent.application_id,
            )
    return [target_response(target) for target in targets if target.scope_parent_id == target_id]
