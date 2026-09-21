"""Security tests for historical agent-observability reads."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_control_api.persistence.repositories.agent_observability_repository import (
    AgentObservabilityRepository,
)
from sqlalchemy.dialects import postgresql


@pytest.mark.asyncio
async def test_agent_snapshot_lookup_is_scoped_to_test_run() -> None:
    """A snapshot ID alone must never cross a TestRun boundary."""

    test_run_id = uuid4()
    snapshot_id = uuid4()

    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)

    repository = AgentObservabilityRepository(session)

    result = await repository.get_snapshot(
        test_run_id=test_run_id,
        snapshot_id=snapshot_id,
    )

    assert result is None

    statement = session.scalar.await_args.args[0]
    compiled = statement.compile(
        dialect=postgresql.dialect()
    )
    sql = str(compiled)

    assert "execution.agent_runtime_snapshots.id =" in sql
    assert "execution.agent_runtime_snapshots.test_run_id =" in sql

    values = set(compiled.params.values())
    assert snapshot_id in values
    assert test_run_id in values
