"""Persistence for Evaluation Worker runtime snapshots."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from markettwin_database.models import (
    AgentRuntimeSnapshot,
)
from markettwin_shared.runtime_snapshot import (
    AgentRuntimeSnapshotPayload,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class EvaluationRuntimeSnapshotRepository:
    """Persist stable Evaluation Worker runtime configuration."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def ensure_run_level_snapshot(
        self,
        *,
        snapshot_id: UUID,
        test_run_id: UUID,
        payload: AgentRuntimeSnapshotPayload,
    ) -> UUID:
        """Ensure this stable run-level snapshot exists once."""

        snapshot_hash = payload.sha256()

        existing_id = await self._session.scalar(
            select(
                AgentRuntimeSnapshot.id
            )
            .where(
                AgentRuntimeSnapshot.test_run_id
                == test_run_id,
                AgentRuntimeSnapshot.agent_role
                == payload.agent_role,
                AgentRuntimeSnapshot.snapshot_sha256
                == snapshot_hash,
                AgentRuntimeSnapshot.journey_id.is_(
                    None
                ),
                AgentRuntimeSnapshot.execution_id.is_(
                    None
                ),
            )
            .limit(1)
        )

        if existing_id is not None:
            return existing_id

        semantic_payload = (
            payload.semantic_payload()
        )

        snapshot = AgentRuntimeSnapshot(
            id=snapshot_id,
            test_run_id=test_run_id,
            journey_id=None,
            execution_id=None,
            agent_role=payload.agent_role,
            runtime_kind=payload.runtime_kind,
            runtime_agent_name=(
                payload.runtime_agent_name
            ),
            agent_version=payload.agent_version,
            snapshot_schema_version=(
                payload.snapshot_schema_version
            ),
            template_id=payload.template_id,
            template_version=(
                payload.template_version
            ),
            model_provider=payload.model_provider,
            model_name=payload.model_name,
            model_configuration=_dict_value(
                semantic_payload[
                    "model_configuration"
                ]
            ),
            base_instruction=(
                payload.base_instruction
            ),
            effective_instruction=(
                payload.effective_instruction
            ),
            runtime_prompt=payload.runtime_prompt,
            persona_snapshot=None,
            mission_snapshot=None,
            success_criteria=[],
            tools=[],
            policy_references=[],
            metadata_json=_dict_value(
                semantic_payload["metadata"]
            ),
            observability_backend=None,
            trace_id=None,
            snapshot_sha256=snapshot_hash,
        )

        self._session.add(snapshot)
        await self._session.flush()

        return snapshot.id


def _dict_value(
    value: object,
) -> dict[str, object]:
    """Return a validated sanitized dictionary."""

    if not isinstance(value, dict):
        raise TypeError(
            "Expected runtime snapshot value "
            "to be a dictionary."
        )

    mapping = cast(dict[object, object], value)
    validated: dict[str, object] = {}

    for key, item in mapping.items():
        if not isinstance(key, str):
            raise TypeError(
                "Expected runtime snapshot dictionary "
                "keys to be strings."
            )

        validated[key] = item

    return validated