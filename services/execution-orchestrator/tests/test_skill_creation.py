"""Creation records share the draft's transaction and lifecycle authority."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.persistence import skill_creation


async def test_draft_creation_records_real_lifecycle_edge():
    rows = []
    session = SimpleNamespace(add=rows.append, flush=AsyncMock())
    version = SimpleNamespace(id=uuid4(), workspace_id=uuid4(), skill_id=uuid4(),
                              app_map_id=uuid4(), lifecycle_status="draft")
    await skill_creation.create_draft_version(session, version, source="task-compile")
    assert rows[0] is version
    event = rows[1]
    assert event.skill_version_id == version.id
    assert event.from_status is None and event.to_status == "draft"
    assert event.payload == {"creation_record": {"source": "task-compile"}}


async def test_creation_refuses_before_writing_when_authority_refuses(monkeypatch):
    rows = []
    monkeypatch.setattr(skill_creation, "check_skill_transition", lambda *_args: False)
    session = SimpleNamespace(add=rows.append, flush=AsyncMock())
    with pytest.raises(ValueError, match="skill_transition_refused"):
        await skill_creation.create_draft_version(
            session, SimpleNamespace(lifecycle_status="draft"), source="test",
        )
    assert rows == []
    session.flush.assert_not_awaited()
