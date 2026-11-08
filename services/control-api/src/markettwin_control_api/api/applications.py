"""Application HTTP endpoints."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from markettwin_shared.persona_definitions import (
    dump_definition_yaml,
    parse_definition_yaml,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import (
    get_authenticated_user_id,
)
from markettwin_control_api.api.permissions import (
    WORKSPACE_WRITE_ROLES,
)
from markettwin_control_api.persistence.repositories import (
    ApplicationRecord,
    ApplicationRepository,
    LatestRunSummaryRecord,
    PersonaDefinitionRepository,
    WorkspaceAccess,
    WorkspaceRepository,
)

router = APIRouter(
    tags=["Applications"],
)


class CreateApplicationRequest(BaseModel):
    """Request for creating a MarketTwin application."""

    name: str = Field(
        min_length=1,
        max_length=200,
    )

    description: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(
        cls,
        value: str,
    ) -> str:
        """Reject empty or whitespace-only names."""

        cleaned = value.strip()

        if not cleaned:
            raise ValueError(
                "Application name is required."
            )

        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(
        cls,
        value: str | None,
    ) -> str | None:
        """Normalize an optional description."""

        if value is None:
            return None

        cleaned = value.strip()

        return cleaned or None


class LatestRunSummaryResponse(BaseModel):
    """The application's latest completed run that produced a report.

    The verdict is the report's stored market verdict, passed through
    verbatim; it is never inferred from the run's status. Null when the
    report carries no market verdict.
    """

    latest_run_id: UUID
    latest_run_status: str
    verdict: str | None
    finished_at: datetime | None


class ApplicationResponse(BaseModel):
    """Application returned to the frontend."""

    id: UUID
    workspace_id: UUID
    created_by_user_id: UUID
    name: str
    description: str | None
    status: str
    latest_run_summary: LatestRunSummaryResponse | None = None


def application_response(
    application: ApplicationRecord,
    latest_run_summary: LatestRunSummaryRecord | None = None,
) -> ApplicationResponse:
    """Convert repository data into an HTTP response."""

    return ApplicationResponse(
        id=application.application_id,
        workspace_id=application.workspace_id,
        created_by_user_id=application.created_by_user_id,
        name=application.name,
        description=application.description,
        status=application.status,
        latest_run_summary=(
            LatestRunSummaryResponse(
                latest_run_id=latest_run_summary.run_id,
                latest_run_status=latest_run_summary.run_status,
                verdict=latest_run_summary.verdict,
                finished_at=latest_run_summary.finished_at,
            )
            if latest_run_summary is not None
            else None
        ),
    )


async def require_workspace_access(
    *,
    database_session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
) -> WorkspaceAccess:
    """Require membership in an active workspace."""

    repository = WorkspaceRepository(
        database_session
    )

    workspace = await repository.get_for_user(
        workspace_id=workspace_id,
        user_id=user_id,
    )

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace access denied.",
        )

    return workspace


@router.post(
    "/api/v1/workspaces/{workspace_id}/applications",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application(
    workspace_id: UUID,
    payload: CreateApplicationRequest,
    request: Request,
) -> ApplicationResponse:
    """Create an application inside an accessible workspace."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            workspace = await require_workspace_access(
                database_session=database_session,
                workspace_id=workspace_id,
                user_id=user_id,
            )

            if workspace.role not in WORKSPACE_WRITE_ROLES:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Your workspace role cannot "
                        "create applications."
                    ),
                )

            repository = ApplicationRepository(
                database_session
            )

            application = await repository.create(
                workspace_id=workspace_id,
                created_by_user_id=user_id,
                name=payload.name,
                description=payload.description,
            )

    return application_response(application)


@router.get(
    "/api/v1/workspaces/{workspace_id}/applications",
    response_model=list[ApplicationResponse],
)
async def list_applications(
    workspace_id: UUID,
    request: Request,
) -> list[ApplicationResponse]:
    """List applications in an accessible workspace."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            await require_workspace_access(
                database_session=database_session,
                workspace_id=workspace_id,
                user_id=user_id,
            )

            repository = ApplicationRepository(
                database_session
            )

            applications = await repository.list_for_workspace(
                workspace_id=workspace_id
            )

            summaries = await repository.latest_run_summaries(
                workspace_id=workspace_id,
                application_ids=[
                    application.application_id
                    for application in applications
                ],
            )

    return [
        application_response(
            application,
            summaries.get(application.application_id),
        )
        for application in applications
    ]


@router.get(
    "/api/v1/applications/{application_id}",
    response_model=ApplicationResponse,
)
async def get_application(
    application_id: UUID,
    request: Request,
) -> ApplicationResponse:
    """Return an application available to the current user."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            repository = ApplicationRepository(
                database_session
            )

            application = await repository.get_for_user(
                application_id=application_id,
                user_id=user_id,
            )

    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    return application_response(application)

# --- Persona definitions (U-P5-03) -------------------------------------
# Owners view and edit the application's persona definitions. Every
# write is validated by the shared contract: canonical conditions are
# enforced by the type, score-like keys are rejected, and unknown keys
# fail — the API returns the validator's message as a 422 so the
# editor can show exactly what is wrong.


class PersonaDefinitionResponse(BaseModel):
    persona_id: str
    persona_type: str
    name: str
    enabled: bool
    yaml: str


class UpdatePersonaDefinitionRequest(BaseModel):
    yaml: str = Field(min_length=1, max_length=20000)


@router.get(
    "/api/v1/applications/{application_id}/personas",
    response_model=list[PersonaDefinitionResponse],
)
async def list_personas(
    application_id: UUID, request: Request,
) -> list[PersonaDefinitionResponse]:
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as database_session:
        async with database_session.begin():
            application = await ApplicationRepository(
                database_session
            ).get_for_user(application_id=application_id, user_id=user_id)
            if application is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Application not found.",
                )
            rows = await PersonaDefinitionRepository(
                database_session
            ).list_for_application(application_id=application_id)
    return [
        PersonaDefinitionResponse(
            persona_id=row.persona_id, persona_type=row.persona_type,
            name=row.name, enabled=row.enabled, yaml=row.definition_yaml,
        )
        for row in rows
    ]


@router.put(
    "/api/v1/applications/{application_id}/personas/{persona_id}",
    response_model=PersonaDefinitionResponse,
)
async def update_persona(
    application_id: UUID, persona_id: str,
    payload: UpdatePersonaDefinitionRequest, request: Request,
) -> PersonaDefinitionResponse:
    # Authenticate first, like every other endpoint in this module:
    # an unauthenticated request gets a 401 even when its YAML is
    # also invalid, never a 422 that leaks validation behaviour.
    user_id = await get_authenticated_user_id(request=request)
    try:
        definition = parse_definition_yaml(payload.yaml)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid persona definition: {error}",
        ) from error
    if definition.persona_id != persona_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The definition's persona_id does not match the URL.",
        )
    database = get_database_runtime(request)
    async with database.session_factory() as database_session:
        async with database_session.begin():
            application = await ApplicationRepository(
                database_session
            ).get_for_user(application_id=application_id, user_id=user_id)
            if application is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Application not found.",
                )
            repository = PersonaDefinitionRepository(database_session)
            rendered = dump_definition_yaml(definition)
            await repository.upsert(
                application_id=application_id,
                definition=definition, definition_yaml=rendered,
            )
    return PersonaDefinitionResponse(
        persona_id=definition.persona_id, persona_type=definition.type,
        name=definition.name, enabled=definition.enabled, yaml=rendered,
    )
