"""Persistence for evaluation-worker model observability."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from markettwin_database.models import (
    AgentRuntimeSnapshot,
    ModelInvocation,
    TestRun,
)
from markettwin_shared.observability import (
    AgentRuntimeSnapshotSpec,
    ModelTokenUsage,
)
from sqlalchemy.ext.asyncio import AsyncSession


class EvaluationObservabilityRepository:
    """Persist visual-verifier snapshots and model attempts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_agent_snapshot(
        self,
        *,
        snapshot_id: UUID,
        snapshot: AgentRuntimeSnapshotSpec,
    ) -> UUID:
        test_run_id = UUID(snapshot.test_run_id)

        if await self._session.get(TestRun, test_run_id) is None:
            raise ValueError(
                f'TestRun "{test_run_id}" does not exist.'
            )

        row = AgentRuntimeSnapshot(
            id=snapshot_id,
            test_run_id=test_run_id,
            journey_id=(
                UUID(snapshot.journey_id)
                if snapshot.journey_id
                else None
            ),
            execution_id=(
                UUID(snapshot.execution_id)
                if snapshot.execution_id
                else None
            ),
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

    async def start_invocation(
        self,
        *,
        invocation_id: UUID,
        test_run_id: UUID,
        agent_snapshot_id: UUID,
        attempt_number: int,
        model_provider: str | None,
        model_name: str | None,
        started_at: datetime,
        metadata: dict[str, object],
    ) -> None:
        snapshot = await self._session.get(
            AgentRuntimeSnapshot,
            agent_snapshot_id,
        )
        if (
            snapshot is None
            or snapshot.test_run_id != test_run_id
            or snapshot.agent_role != "visual_verifier"
        ):
            raise ValueError(
                "Visual model invocation snapshot is outside the TestRun scope."
            )

        self._session.add(
            ModelInvocation(
                id=invocation_id,
                test_run_id=test_run_id,
                agent_snapshot_id=agent_snapshot_id,
                agent_role="visual_verifier",
                runtime_agent_name="markettwin_visual_verifier",
                attempt_number=attempt_number,
                model_provider=model_provider,
                model_name=model_name,
                status="started",
                usage_status="unavailable",
                started_at=started_at,
                metadata_json=metadata,
            )
        )
        await self._session.flush()

    async def finish_invocation(
        self,
        *,
        invocation_id: UUID,
        status: str,
        completed_at: datetime,
        latency_ms: int,
        usage: ModelTokenUsage | None = None,
        model_version: str | None = None,
        error_code: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        row = await self._session.get(
            ModelInvocation,
            invocation_id,
        )
        if row is None:
            raise ValueError(
                f'ModelInvocation "{invocation_id}" does not exist.'
            )

        normalized = usage or ModelTokenUsage()

        row.status = status
        row.usage_status = normalized.status
        row.input_tokens = normalized.input_tokens
        row.cached_input_tokens = normalized.cached_input_tokens
        row.output_tokens = normalized.output_tokens
        row.reasoning_tokens = normalized.reasoning_tokens
        row.tool_input_tokens = normalized.tool_input_tokens
        row.provider_total_tokens = normalized.total_tokens
        row.model_version = model_version
        row.latency_ms = latency_ms
        row.completed_at = completed_at
        row.error_code = error_code
        row.error_summary = error_summary

        await self._session.flush()
