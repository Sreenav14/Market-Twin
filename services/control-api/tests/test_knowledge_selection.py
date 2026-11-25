"""Attached approved workspace knowledge feeds the current grounding pipeline.

Per-run legacy knowledge selection is retired; the current consumer is grounding.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_database.models.knowledge import IngestionEntry
from markettwin_execution_orchestrator.expectations.expectations_repository import (
    GroundingRepository,
)


@pytest.mark.parametrize("status", ["approved", "draft", "rejected", None])
async def test_only_attached_approved_knowledge_reaches_grounding(status):
    application_id, entry_id, blueprint_id = uuid4(), uuid4(), uuid4()
    workspace_id = uuid4()
    entry = SimpleNamespace(id=entry_id, blueprint_id=blueprint_id, workspace_id=workspace_id)
    link = SimpleNamespace(ingestion_entry_id=entry_id)
    version = SimpleNamespace(status=status) if status is not None else None
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[
            SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [link])),
            SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: version)),
        ]), get=AsyncMock(return_value=entry),
    )

    class Context:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            pass

    repository = GroundingRepository(lambda: Context())
    selected = await repository.load_approved_entries(application_id)
    assert selected == ([entry] if status == "approved" else [])
    session.get.assert_awaited_once_with(IngestionEntry, entry_id)
    statement = session.execute.await_args_list[0].args[0]
    assert application_id in statement.compile().params.values()
    eligibility = session.execute.await_args_list[1].args[0]
    assert workspace_id in eligibility.compile().params.values()
    assert "active" in eligibility.compile().params.values()
