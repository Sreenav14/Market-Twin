"""Authorized deletion of tests and unused target/application records."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from markettwin_database.models import AgentExecution, Artifact, PersonaJourney, Report
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import get_authenticated_user_id
from markettwin_control_api.persistence.models import (
    Application,
    ApplicationTarget,
    TestRun,
    Workspace,
    WorkspaceMember,
)

router = APIRouter(tags=["Lifecycle"])
DELETABLE_RUN_STATUSES = frozenset({"draft", "completed", "failed", "cancelled"})


async def check_dependencies(session: AsyncSession, entity: object) -> None:
    """Reject deletion while work, durable evidence, or parent dependencies exist."""
    if isinstance(entity, TestRun):
        if entity.status not in DELETABLE_RUN_STATUSES:
            raise HTTPException(
                409, "This test is active. Wait until it has finished before deleting it."
            )

        active_execution = await session.scalar(
            select(AgentExecution.id)
            .join(PersonaJourney, PersonaJourney.id == AgentExecution.journey_id)
            .where(
                PersonaJourney.test_run_id == entity.id,
                AgentExecution.status.in_(["pending", "queued", "running"]),
            )
            .limit(1)
        )
        if active_execution is not None:
            raise HTTPException(
                409, "This test still has active journeys. Try again after they finish."
            )

        stored_artifact = await session.scalar(
            select(Artifact.id)
            .join(AgentExecution, AgentExecution.id == Artifact.execution_id)
            .join(PersonaJourney, PersonaJourney.id == AgentExecution.journey_id)
            .where(PersonaJourney.test_run_id == entity.id)
            .limit(1)
        )
        if stored_artifact is not None:
            raise HTTPException(
                409,
                "This test has stored evidence and cannot be deleted until evidence retention cleanup is available.",
            )

        reports = list(
            (
                await session.scalars(select(Report.status).where(Report.test_run_id == entity.id))
            ).all()
        )
        if "generating" in reports or (entity.status == "completed" and not reports):
            raise HTTPException(
                409, "Evaluation is not finished yet. Wait before deleting this test."
            )

    elif isinstance(entity, ApplicationTarget):
        if await session.scalar(select(TestRun.id).where(TestRun.target_id == entity.id).limit(1)):
            raise HTTPException(409, "Delete this target's tests first, then delete the target.")

    elif isinstance(entity, Application):
        if await session.scalar(
            select(TestRun.id).where(TestRun.application_id == entity.id).limit(1)
        ):
            raise HTTPException(409, "Delete this application's tests first.")
        if await session.scalar(
            select(ApplicationTarget.id)
            .where(ApplicationTarget.application_id == entity.id)
            .limit(1)
        ):
            raise HTTPException(409, "Delete this application's targets first.")


async def delete_resource(
    request: Request,
    resource_id: UUID,
    model: type[Application] | type[ApplicationTarget] | type[TestRun],
) -> Response:
    """Authorize and delete in one transaction; foreign keys protect concurrent use."""
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    try:
        async with database.session_factory() as session:
            async with session.begin():
                statement = select(model, WorkspaceMember.role)
                if model is ApplicationTarget:
                    statement = statement.join(Application, Application.id == model.application_id)
                    workspace_id = Application.workspace_id
                else:
                    workspace_id = model.workspace_id
                statement = (
                    statement.join(Workspace, Workspace.id == workspace_id)
                    .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
                    .where(
                        model.id == resource_id,
                        WorkspaceMember.user_id == user_id,
                        Workspace.status == "active",
                        Workspace.deleted_at.is_(None),
                    )
                    .with_for_update(of=model)
                )
                row = (await session.execute(statement)).one_or_none()
                if row is None:
                    raise HTTPException(404, "Item not found.")
                entity, role = row
                if role not in {"owner", "admin"}:
                    raise HTTPException(
                        403, "Only workspace owners and administrators can delete items."
                    )
                await check_dependencies(session, entity)
                await session.delete(entity)
                await session.flush()
    except IntegrityError as error:
        raise HTTPException(
            409, "This item is still in use. Refresh and remove its dependencies first."
        ) from error
    return Response(status_code=204)


@router.delete("/api/v1/test-runs/{test_run_id}", status_code=204)
async def delete_test_run(test_run_id: UUID, request: Request) -> Response:
    """Delete a test only when no active work or durable evidence remains."""
    return await delete_resource(request, test_run_id, TestRun)


@router.delete("/api/v1/targets/{target_id}", status_code=204)
async def delete_target(target_id: UUID, request: Request) -> Response:
    """Delete a target after all its tests have been removed."""
    return await delete_resource(request, target_id, ApplicationTarget)


@router.delete("/api/v1/applications/{application_id}", status_code=204)
async def delete_application(application_id: UUID, request: Request) -> Response:
    """Delete an application after its tests and targets have been removed."""
    return await delete_resource(request, application_id, Application)
