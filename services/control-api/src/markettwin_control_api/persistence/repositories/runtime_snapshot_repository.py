"""Read MarketTwin agent runtime snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from markettwin_database.models import (
    AgentRuntimeSnapshot,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class RuntimeSnapshotRecord:
    """One historical agent runtime snapshot."""

    snapshot_id: UUID
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

    success_criteria: tuple[str, ...]
    tools: tuple[str, ...]
    policy_references: tuple[str, ...]

    metadata: dict[str, object]

    observability_backend: str | None
    trace_id: str | None

    snapshot_sha256: str
    created_at: datetime


class RuntimeSnapshotRepository:
    """Read historical runtime configuration for one TestRun."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def list_for_run(
        self,
        *,
        test_run_id: UUID,
    ) -> tuple[RuntimeSnapshotRecord, ...]:
        """Return runtime snapshots belonging to one TestRun."""

        snapshots = tuple(
            (
                await self._session.scalars(
                    select(AgentRuntimeSnapshot)
                    .where(
                        AgentRuntimeSnapshot.test_run_id
                        == test_run_id
                    )
                    .order_by(
                        AgentRuntimeSnapshot.created_at,
                        AgentRuntimeSnapshot.id,
                    )
                )
            ).all()
        )

        return tuple(
            RuntimeSnapshotRecord(
                snapshot_id=snapshot.id,
                test_run_id=snapshot.test_run_id,
                journey_id=snapshot.journey_id,
                execution_id=snapshot.execution_id,
                agent_role=snapshot.agent_role,
                runtime_kind=snapshot.runtime_kind,
                runtime_agent_name=(
                    snapshot.runtime_agent_name
                ),
                agent_version=snapshot.agent_version,
                snapshot_schema_version=(
                    snapshot.snapshot_schema_version
                ),
                template_id=snapshot.template_id,
                template_version=snapshot.template_version,
                model_provider=snapshot.model_provider,
                model_name=snapshot.model_name,
                model_configuration=(
                    snapshot.model_configuration
                ),
                base_instruction=snapshot.base_instruction,
                effective_instruction=(
                    snapshot.effective_instruction
                ),
                runtime_prompt=snapshot.runtime_prompt,
                persona_snapshot=snapshot.persona_snapshot,
                mission_snapshot=snapshot.mission_snapshot,
                success_criteria=tuple(
                    snapshot.success_criteria
                ),
                tools=tuple(
                    snapshot.tools
                ),
                policy_references=tuple(
                    snapshot.policy_references
                ),
                metadata=snapshot.metadata_json,
                observability_backend=(
                    snapshot.observability_backend
                ),
                trace_id=snapshot.trace_id,
                snapshot_sha256=(
                    snapshot.snapshot_sha256
                ),
                created_at=snapshot.created_at,
            )
            for snapshot in snapshots
        )