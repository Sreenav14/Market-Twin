"""Historical agent runtime snapshot endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    status,
)
from pydantic import BaseModel

from markettwin_control_api.api.auth import (
    get_database_runtime,
)
from markettwin_control_api.api.dependencies import (
    get_authenticated_user_id,
)
from markettwin_control_api.persistence.repositories import (
    RuntimeSnapshotRecord,
    RuntimeSnapshotRepository,
    TestRunRepository,
)

router = APIRouter(
    tags=["Agent Runtime Snapshots"],
)


class AgentRuntimeSnapshotResponse(BaseModel):
    """Historical configuration for one MarketTwin runtime."""

    id: UUID
    test_run_id: UUID
    journey_id: UUID | None
    execution_id: UUID | None

    agent_role: str
    runtime_kind: str
    runtime_agent_name: str | None

    agent_version: int
    snapshot_schema_version: int

    template_id: str | None
    template_version: str | None

    model_provider: str | None
    model_name: str | None
    model_configuration: dict[str, object]

    base_instruction: str | None
    effective_instruction: str | None
    runtime_prompt: str | None

    persona_snapshot: dict[str, object] | None
    mission_snapshot: dict[str, object] | None

    success_criteria: list[str]
    tools: list[str]
    policy_references: list[str]

    metadata: dict[str, object]

    observability_backend: str | None
    trace_id: str | None

    snapshot_sha256: str
    created_at: datetime


class TestRunRuntimeSnapshotsResponse(BaseModel):
    """All runtime snapshots belonging to one TestRun."""

    test_run_id: UUID
    snapshots: list[
        AgentRuntimeSnapshotResponse
    ]


def build_runtime_snapshot_response(
    record: RuntimeSnapshotRecord,
) -> AgentRuntimeSnapshotResponse:
    """Convert persistence record into API response."""

    return AgentRuntimeSnapshotResponse(
        id=record.snapshot_id,
        test_run_id=record.test_run_id,
        journey_id=record.journey_id,
        execution_id=record.execution_id,
        agent_role=record.agent_role,
        runtime_kind=record.runtime_kind,
        runtime_agent_name=(
            record.runtime_agent_name
        ),
        agent_version=record.agent_version,
        snapshot_schema_version=(
            record.snapshot_schema_version
        ),
        template_id=record.template_id,
        template_version=record.template_version,
        model_provider=record.model_provider,
        model_name=record.model_name,
        model_configuration=(
            record.model_configuration
        ),
        base_instruction=record.base_instruction,
        effective_instruction=(
            record.effective_instruction
        ),
        runtime_prompt=record.runtime_prompt,
        persona_snapshot=record.persona_snapshot,
        mission_snapshot=record.mission_snapshot,
        success_criteria=list(
            record.success_criteria
        ),
        tools=list(
            record.tools
        ),
        policy_references=list(
            record.policy_references
        ),
        metadata=record.metadata,
        observability_backend=(
            record.observability_backend
        ),
        trace_id=record.trace_id,
        snapshot_sha256=record.snapshot_sha256,
        created_at=record.created_at,
    )


@router.get(
    "/api/v1/test-runs/{test_run_id}/runtime-snapshots",
    response_model=TestRunRuntimeSnapshotsResponse,
)
async def get_test_run_runtime_snapshots(
    test_run_id: UUID,
    request: Request,
) -> TestRunRuntimeSnapshotsResponse:
    """Return historical runtime snapshots for one authorized TestRun."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with (
        database.session_factory()
        as database_session
    ):
        test_run_repository = TestRunRepository(
            database_session
        )

        test_run = (
            await test_run_repository.get_for_user(
                test_run_id=test_run_id,
                user_id=user_id,
            )
        )

        if test_run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test run not found.",
            )

        snapshot_repository = (
            RuntimeSnapshotRepository(
                database_session
            )
        )

        snapshots = (
            await snapshot_repository.list_for_run(
                test_run_id=test_run_id
            )
        )

    return TestRunRuntimeSnapshotsResponse(
        test_run_id=test_run_id,
        snapshots=[
            build_runtime_snapshot_response(
                snapshot
            )
            for snapshot in snapshots
        ],
    )