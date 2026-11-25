"""FIX-2 (dynamic wiring pass, 2026-11-18): skill_library_lines
carries task_source_kind from the latest version's
definition_json.task.source.kind — the field the web skills
panel's "Source knowledge — not yet a skill" group classifies
candidates by (doc 29 sections 3.4 / 8.2). A document-sourced
candidate reports "document"; a run-learned task skill reports
"run_execution"; a skill with no task block reports None; the
LATEST version wins when several exist.

Fake sessions follow the Phase 2/3 pattern: queued execute
results in the repository's pinned call order (skills, versions,
diagnosis sums, demotion/quarantine reason events).
"""

from collections import deque
from types import SimpleNamespace
from uuid import uuid4

import pytest
from markettwin_control_api.api.app_maps import AppMapSkillOut
from markettwin_control_api.knowledge.map_repository import MapRepository
from markettwin_database.models.knowledge import Skill, SkillVersion

WORKSPACE_ID = uuid4()
APPLICATION_ID = uuid4()
TARGET_ID = uuid4()


def _result(rows):
    rows = list(rows)
    return SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: list(rows)),
        all=lambda: list(rows),
    )


class _Context:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


class _FakeSession:
    def __init__(self, *, execute_results=()):
        self._execute_results = deque(execute_results)

    async def execute(self, statement):
        rows = self._execute_results.popleft() if self._execute_results else []
        return _result(rows)


def _repo(session) -> MapRepository:
    return MapRepository(session_factory=lambda: _Context(session))


def _skill(*, kind, name):
    return Skill(
        id=uuid4(),
        workspace_id=WORKSPACE_ID,
        application_id=APPLICATION_ID,
        target_id=TARGET_ID,
        name=name,
        skill_kind=kind,
    )


def _version(skill, *, number, definition):
    return SkillVersion(
        id=uuid4(),
        workspace_id=WORKSPACE_ID,
        skill_id=skill.id,
        version_number=number,
        status="draft",
        definition_json=definition,
        generation_metadata={},
        lifecycle_status="active",
        package={},
        heal_count=0,
        replay_count=0,
        last_replay_result=None,
        last_replay_at=None,
        retired_reason=None,
    )


async def test_skill_library_lines_carry_task_source_kind():
    candidate = _skill(kind="task", name="a-candidate")
    learned = _skill(kind="task", name="b-learned")
    journey = _skill(kind="journey", name="c-journey")
    bare = _skill(kind="task", name="d-bare")
    versions = [
        # Latest candidate version (v2) is document-sourced; the
        # older v1 was not — the latest must win.
        _version(candidate, number=2, definition={
            "task": {"source": {"kind": "document",
                                "document_ref": "kb/pricing.md"}},
            "steps": [],
        }),
        _version(candidate, number=1, definition={
            "task": {"source": {"kind": "run_execution"}},
            "steps": [{"action": "navigate", "url": "https://x.example/"}],
        }),
        _version(learned, number=1, definition={
            "task": {"source": {"kind": "run_execution",
                                "run_id": str(uuid4()),
                                "case_id": "case-1"}},
            "steps": [{"action": "navigate", "url": "https://x.example/"}],
        }),
        _version(journey, number=1, definition={"steps": []}),
        _version(bare, number=1, definition={}),
    ]
    session = _FakeSession(
        execute_results=[[candidate, learned, journey, bare], versions, [], []]
    )
    lines = await _repo(session).skill_library_lines(
        workspace_id=WORKSPACE_ID,
        application_id=APPLICATION_ID,
        target_id=TARGET_ID,
    )
    by_name = {line["name"]: line for line in lines}
    assert by_name["a-candidate"]["task_source_kind"] == "document"
    assert by_name["b-learned"]["task_source_kind"] == "run_execution"
    assert by_name["c-journey"]["task_source_kind"] is None
    assert by_name["d-bare"]["task_source_kind"] is None
    # The API model carries the field through unchanged.
    assert AppMapSkillOut(**by_name["a-candidate"]).task_source_kind == "document"
    assert AppMapSkillOut(**by_name["c-journey"]).task_source_kind is None


async def test_skill_library_lines_empty_scope_stays_empty():
    session = _FakeSession(execute_results=[[]])
    lines = await _repo(session).skill_library_lines(
        workspace_id=WORKSPACE_ID,
        application_id=APPLICATION_ID,
        target_id=TARGET_ID,
    )
    assert lines == []
