from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.persistence import (
    AgentRuntimeSnapshotRepository,
)
from markettwin_execution_orchestrator.persistence.models import (
    AgentRuntimeSnapshot,
)
from markettwin_shared.runtime_snapshot import (
    AgentRuntimeSnapshotPayload,
)
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_create_persists_safe_runtime_snapshot() -> None:
    session = MagicMock(spec=AsyncSession)
    session.flush = AsyncMock()

    repository = AgentRuntimeSnapshotRepository(session)

    snapshot_id = uuid4()
    test_run_id = uuid4()
    journey_id = uuid4()
    execution_id = uuid4()

    payload = AgentRuntimeSnapshotPayload(
        agent_role="persona",
        runtime_kind="google_adk",
        runtime_agent_name="persona_agent",
        model_provider="openai",
        model_name="openai/gpt-4o-mini",
        model_configuration={
            "max_tokens": 512,
            "api_key": "must-not-be-stored",
        },
        effective_instruction="Test the assigned mission.",
        persona_snapshot={
            "persona_id": "persona_1",
        },
        mission_snapshot={
            "mission_id": "mission_1",
        },
        success_criteria=(
            "Main heading is visible.",
        ),
        tools=(
            "browser_get_state",
            "browser_click",
        ),
        policy_references=(
            "browser_policy_v1",
        ),
        metadata={
            "safe_key": "safe-value",
            "access_token": "must-not-be-stored",
        },
    )

    result = await repository.create(
        snapshot_id=snapshot_id,
        test_run_id=test_run_id,
        journey_id=journey_id,
        execution_id=execution_id,
        payload=payload,
        observability_backend="aws",
    )

    assert result == snapshot_id

    session.add.assert_called_once()
    session.flush.assert_awaited_once()

    persisted = session.add.call_args.args[0]

    assert isinstance(
        persisted,
        AgentRuntimeSnapshot,
    )

    assert persisted.id == snapshot_id
    assert persisted.test_run_id == test_run_id
    assert persisted.journey_id == journey_id
    assert persisted.execution_id == execution_id

    assert persisted.agent_role == "persona"
    assert persisted.runtime_kind == "google_adk"

    assert persisted.model_configuration == {
        "max_tokens": 512,
    }

    assert persisted.metadata_json == {
        "safe_key": "safe-value",
    }

    assert persisted.success_criteria == [
        "Main heading is visible.",
    ]

    assert persisted.tools == [
        "browser_get_state",
        "browser_click",
    ]

    assert persisted.snapshot_sha256 == payload.sha256()

    assert len(persisted.snapshot_sha256) == 64


@pytest.mark.asyncio
async def test_create_supports_run_level_meta_snapshot() -> None:
    session = MagicMock(spec=AsyncSession)
    session.flush = AsyncMock()

    repository = AgentRuntimeSnapshotRepository(session)

    snapshot_id = uuid4()
    test_run_id = uuid4()

    payload = AgentRuntimeSnapshotPayload(
        agent_role="meta",
        runtime_kind="google_adk",
        runtime_agent_name="meta_agent",
        model_provider="openai",
        model_name="openai/gpt-4o-mini",
        effective_instruction="Create the MarketTwin plan.",
    )

    await repository.create(
        snapshot_id=snapshot_id,
        test_run_id=test_run_id,
        payload=payload,
    )

    persisted = session.add.call_args.args[0]

    assert persisted.test_run_id == test_run_id
    assert persisted.journey_id is None
    assert persisted.execution_id is None
    assert persisted.agent_role == "meta"


@pytest.mark.asyncio
async def test_create_does_not_commit_transaction() -> None:
    session = MagicMock(spec=AsyncSession)
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    repository = AgentRuntimeSnapshotRepository(session)

    await repository.create(
        snapshot_id=uuid4(),
        test_run_id=uuid4(),
        payload=AgentRuntimeSnapshotPayload(
            agent_role="meta",
            runtime_kind="google_adk",
        ),
    )

    session.flush.assert_awaited_once()
    session.commit.assert_not_awaited()