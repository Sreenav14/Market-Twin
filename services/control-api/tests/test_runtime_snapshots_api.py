from datetime import UTC, datetime
from uuid import uuid4

from markettwin_control_api.api.runtime_snapshots import (
    build_runtime_snapshot_response,
)
from markettwin_control_api.persistence.repositories import (
    RuntimeSnapshotRecord,
)


def test_build_runtime_snapshot_response() -> None:
    snapshot_id = uuid4()
    test_run_id = uuid4()
    journey_id = uuid4()
    execution_id = uuid4()

    created_at = datetime.now(UTC)

    record = RuntimeSnapshotRecord(
        snapshot_id=snapshot_id,
        test_run_id=test_run_id,
        journey_id=journey_id,
        execution_id=execution_id,
        agent_role="persona",
        runtime_kind="google_adk",
        runtime_agent_name="markettwin_persona",
        agent_version=1,
        snapshot_schema_version=1,
        template_id=None,
        template_version=None,
        model_provider="openai",
        model_name="openai/gpt-4o-mini",
        model_configuration={
            "max_tokens": 512,
            "num_retries": 2,
        },
        base_instruction=None,
        effective_instruction=(
            "Act as the assigned persona."
        ),
        runtime_prompt=(
            "Execute the assigned journey."
        ),
        persona_snapshot={
            "name": "First-time user",
        },
        mission_snapshot={
            "objective": "Find pricing.",
        },
        success_criteria=(
            "Pricing is discoverable.",
        ),
        tools=(
            "browser_get_state",
            "browser_click",
        ),
        policy_references=(),
        metadata={
            "journey_key": "p1__m1",
        },
        observability_backend=None,
        trace_id=None,
        snapshot_sha256="a" * 64,
        created_at=created_at,
    )

    response = build_runtime_snapshot_response(
        record
    )

    assert response.id == snapshot_id
    assert response.test_run_id == test_run_id
    assert response.journey_id == journey_id
    assert response.execution_id == execution_id

    assert response.agent_role == "persona"

    assert response.model_name == (
        "openai/gpt-4o-mini"
    )

    assert response.success_criteria == [
        "Pricing is discoverable.",
    ]

    assert response.tools == [
        "browser_get_state",
        "browser_click",
    ]

    assert response.snapshot_sha256 == (
        "a" * 64
    )

    assert response.created_at == created_at