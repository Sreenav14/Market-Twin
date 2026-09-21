"""Read historical agent snapshots and model usage for the Control API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from markettwin_database.models import (
    AgentRuntimeSnapshot,
    ModelInvocation,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class UsageSummaryRecord:
    """Known model usage plus completeness information."""

    attempts: int
    completed: int
    failed: int
    rate_limited: int
    unknown_usage_attempts: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    tool_input_tokens: int
    provider_total_tokens: int
    latency_ms: int


@dataclass(frozen=True, slots=True)
class ModelInvocationRecord:
    """One historical model invocation attempt."""

    invocation_id: UUID
    status: str
    usage_status: str
    invocation_sequence: int | None
    attempt_number: int
    model_provider: str | None
    model_name: str | None
    model_version: str | None
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    tool_input_tokens: int | None
    provider_total_tokens: int | None
    latency_ms: int | None
    started_at: datetime
    completed_at: datetime | None
    error_code: str | None


@dataclass(frozen=True, slots=True)
class AgentSnapshotRecord:
    """One immutable historical runtime snapshot."""

    snapshot_id: UUID
    test_run_id: UUID
    journey_id: UUID | None
    execution_id: UUID | None
    agent_role: str
    runtime_agent_name: str
    runtime_kind: str
    agent_version: str
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
    policy_references: dict[str, object]
    metadata: dict[str, object]
    snapshot_sha256: str
    created_at: datetime


class AgentObservabilityRepository:
    """Read model-backed agent history for one TestRun."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_snapshots(
        self,
        *,
        test_run_id: UUID,
    ) -> tuple[AgentSnapshotRecord, ...]:
        rows = tuple(
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
            _snapshot_record(row)
            for row in rows
        )

    async def get_snapshot(
        self,
        *,
        test_run_id: UUID,
        snapshot_id: UUID,
    ) -> AgentSnapshotRecord | None:
        row = await self._session.scalar(
            select(AgentRuntimeSnapshot)
            .where(
                AgentRuntimeSnapshot.id == snapshot_id,
                AgentRuntimeSnapshot.test_run_id == test_run_id,
            )
        )

        return (
            _snapshot_record(row)
            if row is not None
            else None
        )

    async def list_invocations(
        self,
        *,
        test_run_id: UUID,
        snapshot_id: UUID | None = None,
    ) -> tuple[ModelInvocationRecord, ...]:
        statement = (
            select(ModelInvocation)
            .where(
                ModelInvocation.test_run_id
                == test_run_id
            )
            .order_by(
                ModelInvocation.started_at,
                ModelInvocation.id,
            )
        )

        if snapshot_id is not None:
            statement = statement.where(
                ModelInvocation.agent_snapshot_id
                == snapshot_id
            )

        rows = tuple(
            (
                await self._session.scalars(
                    statement
                )
            ).all()
        )

        return tuple(
            _invocation_record(row)
            for row in rows
        )

    async def usage_summary(
        self,
        *,
        test_run_id: UUID,
        snapshot_id: UUID | None = None,
    ) -> UsageSummaryRecord:
        invocations = await self.list_invocations(
            test_run_id=test_run_id,
            snapshot_id=snapshot_id,
        )

        return summarize_usage(invocations)


def summarize_usage(
    invocations: tuple[ModelInvocationRecord, ...],
) -> UsageSummaryRecord:
    """Aggregate known usage without pretending missing fields are zero-cost."""

    return UsageSummaryRecord(
        attempts=len(invocations),
        completed=sum(
            item.status == "completed"
            for item in invocations
        ),
        failed=sum(
            item.status == "failed"
            for item in invocations
        ),
        rate_limited=sum(
            item.status == "rate_limited"
            for item in invocations
        ),
        unknown_usage_attempts=sum(
            item.usage_status == "unavailable"
            for item in invocations
        ),
        input_tokens=_sum_known(
            item.input_tokens
            for item in invocations
        ),
        cached_input_tokens=_sum_known(
            item.cached_input_tokens
            for item in invocations
        ),
        output_tokens=_sum_known(
            item.output_tokens
            for item in invocations
        ),
        reasoning_tokens=_sum_known(
            item.reasoning_tokens
            for item in invocations
        ),
        tool_input_tokens=_sum_known(
            item.tool_input_tokens
            for item in invocations
        ),
        provider_total_tokens=_sum_known(
            item.provider_total_tokens
            for item in invocations
        ),
        latency_ms=_sum_known(
            item.latency_ms
            for item in invocations
        ),
    )


def _sum_known(
    values: object,
) -> int:
    return sum(
        value
        for value in values
        if isinstance(value, int)
    )


def _snapshot_record(
    row: AgentRuntimeSnapshot,
) -> AgentSnapshotRecord:
    return AgentSnapshotRecord(
        snapshot_id=row.id,
        test_run_id=row.test_run_id,
        journey_id=row.journey_id,
        execution_id=row.execution_id,
        agent_role=row.agent_role,
        runtime_agent_name=row.runtime_agent_name,
        runtime_kind=row.runtime_kind,
        agent_version=row.agent_version,
        snapshot_schema_version=row.snapshot_schema_version,
        template_id=row.template_id,
        template_version=row.template_version,
        model_provider=row.model_provider,
        model_name=row.model_name,
        model_configuration=row.model_configuration,
        base_instruction=row.base_instruction,
        effective_instruction=row.effective_instruction,
        runtime_prompt=row.runtime_prompt,
        persona_snapshot=row.persona_snapshot,
        mission_snapshot=row.mission_snapshot,
        success_criteria=tuple(row.success_criteria),
        tools=tuple(row.tools),
        policy_references=row.policy_references,
        metadata=row.metadata_json,
        snapshot_sha256=row.snapshot_sha256,
        created_at=row.created_at,
    )


def _invocation_record(
    row: ModelInvocation,
) -> ModelInvocationRecord:
    return ModelInvocationRecord(
        invocation_id=row.id,
        status=row.status,
        usage_status=row.usage_status,
        invocation_sequence=row.invocation_sequence,
        attempt_number=row.attempt_number,
        model_provider=row.model_provider,
        model_name=row.model_name,
        model_version=row.model_version,
        input_tokens=row.input_tokens,
        cached_input_tokens=row.cached_input_tokens,
        output_tokens=row.output_tokens,
        reasoning_tokens=row.reasoning_tokens,
        tool_input_tokens=row.tool_input_tokens,
        provider_total_tokens=row.provider_total_tokens,
        latency_ms=row.latency_ms,
        started_at=row.started_at,
        completed_at=row.completed_at,
        error_code=row.error_code,
    )
