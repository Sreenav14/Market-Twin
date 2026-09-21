"""Persistence for historical agent snapshots and model-call telemetry."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from markettwin_database.models import (
    AgentExecution,
    AgentRuntimeSnapshot,
    ModelInvocation,
    PersonaJourney,
    TestRun,
)
from markettwin_shared.observability import (
    AgentRuntimeSnapshotSpec,
    ModelTokenUsage,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class ObservabilityRepository:
    """Persist immutable runtime snapshots and model invocation attempts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_agent_snapshot(
        self,
        *,
        snapshot_id: UUID,
        snapshot: AgentRuntimeSnapshotSpec,
    ) -> UUID:
        test_run_id = UUID(snapshot.test_run_id)
        journey_id = UUID(snapshot.journey_id) if snapshot.journey_id else None
        execution_id = (
            UUID(snapshot.execution_id)
            if snapshot.execution_id
            else None
        )

        await self._validate_scope(
            test_run_id=test_run_id,
            journey_id=journey_id,
            execution_id=execution_id,
        )

        row = AgentRuntimeSnapshot(
            id=snapshot_id,
            test_run_id=test_run_id,
            journey_id=journey_id,
            execution_id=execution_id,
            agent_role=snapshot.agent_role,
            runtime_agent_name=snapshot.runtime_agent_name,
            runtime_kind=snapshot.runtime_kind,
            agent_version=snapshot.agent_version,
            snapshot_schema_version=snapshot.snapshot_schema_version,
            template_id=snapshot.template_id,
            template_version=snapshot.template_version,
            model_provider=snapshot.model_provider,
            model_name=snapshot.model_name,
            model_configuration=snapshot.model_configuration,
            base_instruction=snapshot.base_instruction,
            effective_instruction=snapshot.effective_instruction,
            runtime_prompt=snapshot.runtime_prompt,
            persona_snapshot=snapshot.persona_snapshot,
            mission_snapshot=snapshot.mission_snapshot,
            success_criteria=list(snapshot.success_criteria),
            tools=list(snapshot.tools),
            policy_references=snapshot.policy_references,
            metadata_json=snapshot.metadata,
            snapshot_sha256=snapshot.snapshot_sha256,
        )

        self._session.add(row)
        await self._session.flush()

        return row.id

    async def _validate_snapshot_scope(
        self,
        *,
        snapshot_id: UUID,
        test_run_id: UUID,
        journey_id: UUID | None,
        execution_id: UUID | None,
    ) -> None:
        snapshot = await self._session.get(
            AgentRuntimeSnapshot,
            snapshot_id,
        )

        if snapshot is None:
            raise ValueError(
                f'AgentRuntimeSnapshot "{snapshot_id}" does not exist.'
            )

        if snapshot.test_run_id != test_run_id:
            raise ValueError(
                "Model invocation snapshot does not belong to the TestRun."
            )

        if snapshot.journey_id != journey_id:
            raise ValueError(
                "Model invocation Journey scope does not match its snapshot."
            )

        if snapshot.execution_id != execution_id:
            raise ValueError(
                "Model invocation execution scope does not match its snapshot."
            )

    async def start_model_invocation(
        self,
        *,
        invocation_id: UUID,
        test_run_id: UUID,
        agent_snapshot_id: UUID | None,
        agent_role: str,
        runtime_agent_name: str | None,
        runtime_invocation_id: str | None,
        invocation_sequence: int | None,
        attempt_number: int,
        model_provider: str | None,
        model_name: str | None,
        journey_id: UUID | None = None,
        execution_id: UUID | None = None,
        started_at: datetime,
        metadata: dict[str, object] | None = None,
    ) -> UUID:
        if agent_snapshot_id is not None:
            await self._validate_snapshot_scope(
                snapshot_id=agent_snapshot_id,
                test_run_id=test_run_id,
                journey_id=journey_id,
                execution_id=execution_id,
            )

        row = ModelInvocation(
            id=invocation_id,
            test_run_id=test_run_id,
            journey_id=journey_id,
            execution_id=execution_id,
            agent_snapshot_id=agent_snapshot_id,
            agent_role=agent_role,
            runtime_agent_name=runtime_agent_name,
            runtime_invocation_id=runtime_invocation_id,
            invocation_sequence=invocation_sequence,
            attempt_number=attempt_number,
            model_provider=model_provider,
            model_name=model_name,
            status="started",
            usage_status="unavailable",
            started_at=started_at,
            metadata_json=metadata or {},
        )

        self._session.add(row)
        await self._session.flush()

        return row.id

    async def finish_model_invocation(
        self,
        *,
        invocation_id: UUID,
        status: str,
        completed_at: datetime,
        latency_ms: int,
        usage: ModelTokenUsage | None = None,
        model_version: str | None = None,
        provider_request_id: str | None = None,
        error_code: str | None = None,
        error_summary: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        row = await self._session.get(
            ModelInvocation,
            invocation_id,
        )

        if row is None:
            raise ValueError(
                f'ModelInvocation "{invocation_id}" does not exist.'
            )

        normalized_usage = usage or ModelTokenUsage()

        row.status = status
        row.usage_status = normalized_usage.status
        row.input_tokens = normalized_usage.input_tokens
        row.cached_input_tokens = normalized_usage.cached_input_tokens
        row.output_tokens = normalized_usage.output_tokens
        row.reasoning_tokens = normalized_usage.reasoning_tokens
        row.tool_input_tokens = normalized_usage.tool_input_tokens
        row.provider_total_tokens = normalized_usage.total_tokens
        row.model_version = model_version
        row.provider_request_id = provider_request_id
        row.latency_ms = latency_ms
        row.completed_at = completed_at
        row.error_code = error_code
        row.error_summary = error_summary

        if metadata:
            row.metadata_json = {
                **row.metadata_json,
                **metadata,
            }

        await self._session.flush()

    async def _validate_scope(
        self,
        *,
        test_run_id: UUID,
        journey_id: UUID | None,
        execution_id: UUID | None,
    ) -> None:
        if await self._session.get(TestRun, test_run_id) is None:
            raise ValueError(
                f'TestRun "{test_run_id}" does not exist.'
            )

        if journey_id is not None:
            journey = await self._session.scalar(
                select(PersonaJourney)
                .where(
                    PersonaJourney.id == journey_id,
                    PersonaJourney.test_run_id == test_run_id,
                )
            )
            if journey is None:
                raise ValueError(
                    "Agent snapshot Journey does not belong to the TestRun."
                )

        if execution_id is not None:
            execution = await self._session.get(
                AgentExecution,
                execution_id,
            )
            if execution is None:
                raise ValueError(
                    f'AgentExecution "{execution_id}" does not exist.'
                )
            if (
                journey_id is not None
                and execution.journey_id != journey_id
            ):
                raise ValueError(
                    "Agent snapshot execution does not belong to the Journey."
                )
