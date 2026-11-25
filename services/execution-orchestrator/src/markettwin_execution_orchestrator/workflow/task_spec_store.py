"""Executed case specs live in scoped runtime snapshots, not trace events."""

import hashlib
import json
from copy import deepcopy
from typing import Any, cast
from uuid import UUID, uuid4

from markettwin_database.models.execution import AgentRuntimeSnapshot


def redact_task_spec(spec: dict[str, Any]) -> dict[str, Any]:
    redacted = deepcopy(spec)
    for assertion in cast(list[dict[str, Any]], redacted.get("expected") or []):
        assertion.pop("expected_value", None)
    return redacted


async def store_task_spec(session: Any, *, run_id: UUID, journey_id: UUID,
                          execution_id: UUID, spec: dict[str, Any]) -> UUID:
    snapshot_id = uuid4()
    session.add(AgentRuntimeSnapshot(
        id=snapshot_id, test_run_id=run_id, journey_id=journey_id,
        execution_id=execution_id, agent_role="persona", agent_version=1,
        runtime_kind="deterministic_task_spec", snapshot_schema_version=1,
        metadata_json={"case_spec": spec},
        snapshot_sha256=hashlib.sha256(
            json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    ))
    await session.flush()
    return snapshot_id


async def restore_task_trace(session: Any, *, payload: dict[str, Any],
                             run_id: UUID, execution_id: UUID | None) -> dict[str, Any]:
    """Refuse foreign/missing snapshots; historical traces keep their old shape."""
    reference = payload.get("spec_ref")
    if reference is None:
        return payload
    snapshot = await session.get(AgentRuntimeSnapshot, UUID(str(reference)))
    if (snapshot is None or snapshot.test_run_id != run_id
            or execution_id is None or snapshot.execution_id != execution_id
            or snapshot.runtime_kind != "deterministic_task_spec"):
        raise ValueError("task_spec_unavailable")
    raw_spec = snapshot.metadata_json.get("case_spec")
    if not isinstance(raw_spec, dict):
        raise ValueError("task_spec_mismatch")
    spec = cast(dict[str, Any], raw_spec)
    if (spec.get("case_id") != payload.get("case_id")
            or redact_task_spec(spec) != payload.get("spec")):
        raise ValueError("task_spec_mismatch")
    return {**payload, "spec": spec}
