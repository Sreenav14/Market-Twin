"""Historical agent configuration and model usage endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import (
    get_authenticated_user_id,
)
from markettwin_control_api.persistence.repositories import (
    AgentObservabilityRepository,
    AgentSnapshotRecord,
    TestRunRepository,
    UsageSummaryRecord,
)

router = APIRouter(tags=["Agents"])


class UsageSummaryResponse(BaseModel):
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


class AgentSummaryResponse(BaseModel):
    id: UUID
    role: str
    name: str
    runtime: str
    model_provider: str | None
    model_name: str | None
    journey_id: UUID | None
    execution_id: UUID | None
    persona_name: str | None
    mission_name: str | None
    created_at: datetime
    usage: UsageSummaryResponse


class ModelInvocationResponse(BaseModel):
    id: UUID
    journey_id: UUID | None
    execution_id: UUID | None
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


class AgentDetailResponse(AgentSummaryResponse):
    agent_version: str
    snapshot_schema_version: int
    template_id: str | None
    template_version: str | None
    model_configuration: dict[str, object]
    base_instruction: str | None
    effective_instruction: str | None
    runtime_prompt: str | None
    persona: dict[str, object] | None
    mission: dict[str, object] | None
    success_criteria: list[str]
    tools: list[str]
    policy_references: dict[str, object]
    metadata: dict[str, object]
    snapshot_sha256: str
    yaml: str
    invocations: list[ModelInvocationResponse]


class TestRunUsageResponse(BaseModel):
    test_run_id: UUID
    usage: UsageSummaryResponse
    by_role: dict[str, UsageSummaryResponse]


def _usage_response(
    usage: UsageSummaryRecord,
) -> UsageSummaryResponse:
    return UsageSummaryResponse(
        attempts=usage.attempts,
        completed=usage.completed,
        failed=usage.failed,
        rate_limited=usage.rate_limited,
        unknown_usage_attempts=usage.unknown_usage_attempts,
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        output_tokens=usage.output_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        tool_input_tokens=usage.tool_input_tokens,
        provider_total_tokens=usage.provider_total_tokens,
        latency_ms=usage.latency_ms,
    )


def _optional_name(
    payload: dict[str, object] | None,
) -> str | None:
    if payload is None:
        return None
    value = payload.get("name")
    return value if isinstance(value, str) else None


def _yaml_payload(
    snapshot: AgentSnapshotRecord,
) -> dict[str, object]:
    return {
        "schema_version": snapshot.snapshot_schema_version,
        "agent": {
            "role": snapshot.agent_role,
            "name": snapshot.runtime_agent_name,
            "version": snapshot.agent_version,
            "runtime": snapshot.runtime_kind,
            "template_id": snapshot.template_id,
            "template_version": snapshot.template_version,
        },
        "model": {
            "provider": snapshot.model_provider,
            "name": snapshot.model_name,
            "configuration": snapshot.model_configuration,
        },
        "persona": snapshot.persona_snapshot,
        "mission": snapshot.mission_snapshot,
        "success_criteria": list(snapshot.success_criteria),
        "tools": list(snapshot.tools),
        "instructions": {
            "base": snapshot.base_instruction,
            "effective": snapshot.effective_instruction,
        },
        "runtime_prompt": snapshot.runtime_prompt,
        "policy_references": snapshot.policy_references,
        "metadata": snapshot.metadata,
        "snapshot_sha256": snapshot.snapshot_sha256,
    }


def _render_yaml(
    payload: dict[str, object],
) -> str:
    """Render snapshot data as deterministic human-readable YAML."""

    return "\n".join(
        _yaml_lines(
            payload,
            indent=0,
        )
    ) + "\n"


def _yaml_lines(
    value: object,
    *,
    indent: int,
) -> list[str]:
    prefix = " " * indent

    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        lines: list[str] = []
        for key, item in mapping.items():
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{prefix}{key}:")
                lines.extend(
                    _yaml_lines(
                        item,
                        indent=indent + 2,
                    )
                )
            else:
                lines.extend(
                    _yaml_scalar_field(
                        key=str(key),
                        value=item,
                        indent=indent,
                    )
                )
        return lines

    if isinstance(value, list):
        items = cast(list[object], value)
        lines = []
        for item in items:
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{prefix}-")
                lines.extend(
                    _yaml_lines(
                        item,
                        indent=indent + 2,
                    )
                )
            else:
                lines.append(
                    f"{prefix}- {_yaml_scalar(item)}"
                )
        return lines

    return [
        f"{prefix}{_yaml_scalar(value)}"
    ]


def _yaml_scalar_field(
    *,
    key: str,
    value: object,
    indent: int,
) -> list[str]:
    prefix = " " * indent

    if isinstance(value, str) and "\n" in value:
        return [
            f"{prefix}{key}: |",
            *[
                f"{prefix}  {line}"
                for line in value.splitlines()
            ],
        ]

    return [
        f"{prefix}{key}: {_yaml_scalar(value)}"
    ]


def _yaml_scalar(
    value: object,
) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = (
            value
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
        )
        return f'"{escaped}"'
    return f'"{str(value)}"'


def _invocation_response(
    item: ModelInvocationRecord,
) -> ModelInvocationResponse:
    return ModelInvocationResponse(
        id=item.invocation_id,
        journey_id=item.journey_id,
        execution_id=item.execution_id,
        status=item.status,
        usage_status=item.usage_status,
        invocation_sequence=item.invocation_sequence,
        attempt_number=item.attempt_number,
        model_provider=item.model_provider,
        model_name=item.model_name,
        model_version=item.model_version,
        input_tokens=item.input_tokens,
        cached_input_tokens=item.cached_input_tokens,
        output_tokens=item.output_tokens,
        reasoning_tokens=item.reasoning_tokens,
        tool_input_tokens=item.tool_input_tokens,
        provider_total_tokens=item.provider_total_tokens,
        latency_ms=item.latency_ms,
        started_at=item.started_at,
        completed_at=item.completed_at,
        error_code=item.error_code,
    )


@asynccontextmanager
async def _authorized_repository(
    *,
    test_run_id: UUID,
    request: Request,
) -> AsyncIterator[AgentObservabilityRepository]:
    """Yield an observability reader only after TestRun access is verified."""

    user_id = await get_authenticated_user_id(
        request=request
    )
    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        run_repository = TestRunRepository(
            database_session
        )
        run = await run_repository.get_for_user(
            test_run_id=test_run_id,
            user_id=user_id,
        )

        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test run not found.",
            )

        yield AgentObservabilityRepository(
            database_session
        )


@router.get(
    "/api/v1/test-runs/{test_run_id}/agents",
    response_model=list[AgentSummaryResponse],
)
async def list_test_run_agents(
    test_run_id: UUID,
    request: Request,
) -> list[AgentSummaryResponse]:
    async with _authorized_repository(
        test_run_id=test_run_id,
        request=request,
    ) as repository:
        snapshots = await repository.list_snapshots(
            test_run_id=test_run_id
        )
        responses: list[AgentSummaryResponse] = []

        for snapshot in snapshots:
            usage = await repository.usage_summary(
                test_run_id=test_run_id,
                snapshot_id=snapshot.snapshot_id,
            )
            responses.append(
                AgentSummaryResponse(
                    id=snapshot.snapshot_id,
                    role=snapshot.agent_role,
                    name=snapshot.runtime_agent_name,
                    runtime=snapshot.runtime_kind,
                    model_provider=snapshot.model_provider,
                    model_name=snapshot.model_name,
                    journey_id=snapshot.journey_id,
                    execution_id=snapshot.execution_id,
                    persona_name=_optional_name(
                        snapshot.persona_snapshot
                    ),
                    mission_name=_optional_name(
                        snapshot.mission_snapshot
                    ),
                    created_at=snapshot.created_at,
                    usage=_usage_response(usage),
                )
            )

        return responses


@router.get(
    "/api/v1/test-runs/{test_run_id}/agents/{snapshot_id}",
    response_model=AgentDetailResponse,
)
async def get_test_run_agent(
    test_run_id: UUID,
    snapshot_id: UUID,
    request: Request,
) -> AgentDetailResponse:
    async with _authorized_repository(
        test_run_id=test_run_id,
        request=request,
    ) as repository:
        snapshot = await repository.get_snapshot(
            test_run_id=test_run_id,
            snapshot_id=snapshot_id,
        )
        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent snapshot not found.",
            )

        usage = await repository.usage_summary(
            test_run_id=test_run_id,
            snapshot_id=snapshot_id,
        )
        invocations = await repository.list_invocations(
            test_run_id=test_run_id,
            snapshot_id=snapshot_id,
        )

        return AgentDetailResponse(
            id=snapshot.snapshot_id,
            role=snapshot.agent_role,
            name=snapshot.runtime_agent_name,
            runtime=snapshot.runtime_kind,
            model_provider=snapshot.model_provider,
            model_name=snapshot.model_name,
            journey_id=snapshot.journey_id,
            execution_id=snapshot.execution_id,
            persona_name=_optional_name(
                snapshot.persona_snapshot
            ),
            mission_name=_optional_name(
                snapshot.mission_snapshot
            ),
            created_at=snapshot.created_at,
            usage=_usage_response(usage),
            agent_version=snapshot.agent_version,
            snapshot_schema_version=(
                snapshot.snapshot_schema_version
            ),
            template_id=snapshot.template_id,
            template_version=snapshot.template_version,
            model_configuration=(
                snapshot.model_configuration
            ),
            base_instruction=snapshot.base_instruction,
            effective_instruction=(
                snapshot.effective_instruction
            ),
            runtime_prompt=snapshot.runtime_prompt,
            persona=snapshot.persona_snapshot,
            mission=snapshot.mission_snapshot,
            success_criteria=list(
                snapshot.success_criteria
            ),
            tools=list(snapshot.tools),
            policy_references=(
                snapshot.policy_references
            ),
            metadata=snapshot.metadata,
            snapshot_sha256=snapshot.snapshot_sha256,
            yaml=_render_yaml(
                _yaml_payload(snapshot)
            ),
            invocations=[
                _invocation_response(item)
                for item in invocations
            ],
        )


@router.get(
    "/api/v1/test-runs/{test_run_id}/usage",
    response_model=TestRunUsageResponse,
)
async def get_test_run_usage(
    test_run_id: UUID,
    request: Request,
) -> TestRunUsageResponse:
    async with _authorized_repository(
        test_run_id=test_run_id,
        request=request,
    ) as repository:
        snapshots = await repository.list_snapshots(
            test_run_id=test_run_id
        )
        # Role totals are derived from per-snapshot summaries so historical
        # agent roles remain the source of truth.
        by_role: dict[str, UsageSummaryResponse] = {}
        role_accumulator: dict[str, list[UsageSummaryRecord]] = {}

        for snapshot in snapshots:
            role_accumulator.setdefault(
                snapshot.agent_role,
                [],
            ).append(
                await repository.usage_summary(
                    test_run_id=test_run_id,
                    snapshot_id=snapshot.snapshot_id,
                )
            )

        for role, summaries in role_accumulator.items():
            by_role[role] = _usage_response(
                _merge_summaries(summaries)
            )

        return TestRunUsageResponse(
            test_run_id=test_run_id,
            usage=_usage_response(
                await repository.usage_summary(
                    test_run_id=test_run_id
                )
            ),
            by_role=by_role,
        )


def _merge_summaries(
    values: list[UsageSummaryRecord],
) -> UsageSummaryRecord:
    return UsageSummaryRecord(
        attempts=sum(item.attempts for item in values),
        completed=sum(item.completed for item in values),
        failed=sum(item.failed for item in values),
        rate_limited=sum(
            item.rate_limited for item in values
        ),
        unknown_usage_attempts=sum(
            item.unknown_usage_attempts
            for item in values
        ),
        input_tokens=sum(
            item.input_tokens for item in values
        ),
        cached_input_tokens=sum(
            item.cached_input_tokens
            for item in values
        ),
        output_tokens=sum(
            item.output_tokens for item in values
        ),
        reasoning_tokens=sum(
            item.reasoning_tokens for item in values
        ),
        tool_input_tokens=sum(
            item.tool_input_tokens for item in values
        ),
        provider_total_tokens=sum(
            item.provider_total_tokens
            for item in values
        ),
        latency_ms=sum(
            item.latency_ms for item in values
        ),
    )
