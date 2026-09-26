"""Persistence for immutable MarketTwin agent runtime snapshots."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from markettwin_shared.runtime_snapshot import (
    AgentRuntimeSnapshotPayload,
)
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.persistence.models import (
    AgentRuntimeSnapshot,
)


class AgentRuntimeSnapshotRepository:
    """Persist immutable semantic agent runtime configuration."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        snapshot_id: UUID,
        test_run_id: UUID,
        payload: AgentRuntimeSnapshotPayload,
        journey_id: UUID | None = None,
        execution_id: UUID | None = None,
        observability_backend: str | None = None,
        trace_id: str | None = None,
    ) -> UUID:
        """Persist one immutable runtime snapshot."""

        semantic_payload = payload.semantic_payload()

        snapshot = AgentRuntimeSnapshot(
            id=snapshot_id,
            test_run_id=test_run_id,
            journey_id=journey_id,
            execution_id=execution_id,
            agent_role=payload.agent_role,
            runtime_kind=payload.runtime_kind,
            runtime_agent_name=payload.runtime_agent_name,
            agent_version=payload.agent_version,
            snapshot_schema_version=payload.snapshot_schema_version,
            template_id=payload.template_id,
            template_version=payload.template_version,
            model_provider=payload.model_provider,
            model_name=payload.model_name,
            model_configuration=_dict_value(
                semantic_payload["model_configuration"]
            ),
            base_instruction=payload.base_instruction,
            effective_instruction=payload.effective_instruction,
            runtime_prompt=payload.runtime_prompt,
            persona_snapshot=_optional_dict_value(
                semantic_payload["persona_snapshot"]
            ),
            mission_snapshot=_optional_dict_value(
                semantic_payload["mission_snapshot"]
            ),
            success_criteria=_string_list_value(
                semantic_payload["success_criteria"]
            ),
            tools=_string_list_value(
                semantic_payload["tools"]
            ),
            policy_references=_string_list_value(
                semantic_payload["policy_references"]
            ),
            metadata_json=_dict_value(
                semantic_payload["metadata"]
            ),
            observability_backend=observability_backend,
            trace_id=trace_id,
            snapshot_sha256=payload.sha256(),
        )

        self._session.add(snapshot)
        await self._session.flush()

        return snapshot.id


def _dict_value(value: object) -> dict[str, object]:
    """Return a validated dictionary from a sanitized snapshot value."""

    if not isinstance(value, dict):
        raise TypeError(
            "Expected runtime snapshot value to be a dictionary."
        )

    mapping = cast(dict[object, object], value)
    validated: dict[str, object] = {}

    for key, item in mapping.items():
        if not isinstance(key, str):
            raise TypeError(
                "Expected runtime snapshot dictionary keys to be strings."
            )

        validated[key] = item

    return validated


def _optional_dict_value(
    value: object,
) -> dict[str, object] | None:
    """Return an optional validated snapshot dictionary."""

    if value is None:
        return None

    return _dict_value(value)


def _string_list_value(value: object) -> list[str]:
    """Return a validated list of strings."""

    if not isinstance(value, list):
        raise TypeError(
            "Expected runtime snapshot value to be a list."
        )

    items = cast(list[object], value)
    validated: list[str] = []

    for item in items:
        if not isinstance(item, str):
            raise TypeError(
                "Expected runtime snapshot list to contain only strings."
            )

        validated.append(item)

    return validated