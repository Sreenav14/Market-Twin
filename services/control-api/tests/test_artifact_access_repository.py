"""Artifact access repository security tests."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_control_api.persistence.repositories.artifact_access_repository import (
    ArtifactAccessRepository,
)
from sqlalchemy.dialects import postgresql


@pytest.mark.asyncio
async def test_artifact_lookup_is_scoped_to_test_run() -> None:
    """Artifact lookup must require both artifact ID and TestRun ID."""

    artifact_id = uuid4()
    test_run_id = uuid4()

    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)

    repository = ArtifactAccessRepository(session)

    result = await repository.get_for_test_run(
        artifact_id=artifact_id,
        test_run_id=test_run_id,
    )

    assert result is None

    statement = session.scalar.await_args.args[0]

    compiled = statement.compile(
        dialect=postgresql.dialect()
    )

    sql = str(compiled)

    assert "evidence.artifacts.id =" in sql
    assert "testing.persona_journeys.test_run_id =" in sql

    parameter_values = set(compiled.params.values())

    assert artifact_id in parameter_values
    assert test_run_id in parameter_values