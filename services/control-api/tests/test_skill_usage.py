"""Phase 3 usage-ledger summary test (doc 22 section 12.1): T-AC2 --
the per-skill summary reads its totals from skill_usage_events (the
diagnosis spend is the heal_diagnosis rows only) and carries the
latest version's replay/heal rollups. Fake sessions follow the
test_skill_repository pattern."""

from collections import deque
from types import SimpleNamespace
from uuid import uuid4

import pytest
from markettwin_control_api.knowledge.map_repository import MapRepository
from markettwin_database.models.knowledge import SkillUsageEvent, SkillVersion


def _fake_result(rows):
    rows = list(rows)
    return SimpleNamespace(
        scalars=lambda: SimpleNamespace(
            all=lambda: list(rows),
            first=lambda: rows[0] if rows else None,
        ),
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
        self.added: list[object] = []

    def begin(self):
        return _Context(None)

    async def execute(self, statement):
        rows = self._execute_results.popleft() if self._execute_results else []
        return _fake_result(rows)

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        return None


def _event(skill_id, version_id, *, kind, calls=0, tokens=0, result=None):
    return SkillUsageEvent(
        id=uuid4(),
        workspace_id=uuid4(),
        skill_id=skill_id,
        skill_version_id=version_id,
        kind=kind,
        model_calls=calls,
        model_tokens=tokens,
        result=result,
        payload={},
    )


@pytest.mark.asyncio
async def test_t_ac2_usage_summary_reads_the_ledger():
    skill_id = uuid4()
    version_id = uuid4()
    events = [
        _event(skill_id, version_id, kind="compile"),
        _event(skill_id, version_id, kind="verification_replay", result="passed"),
        _event(skill_id, version_id, kind="heal_diagnosis", calls=3, tokens=900),
        _event(skill_id, version_id, kind="heal_diagnosis", calls=2, tokens=400),
        _event(skill_id, version_id, kind="run_replay", result="passed"),
        _event(skill_id, version_id, kind="activation", result="passed"),
    ]
    version = SkillVersion(
        id=version_id,
        workspace_id=uuid4(),
        skill_id=skill_id,
        version_number=2,
        status="draft",
        definition_json={},
        package={},
        lifecycle_status="active",
        heal_count=1,
        replay_count=4,
        last_replay_result="passed",
    )
    session = _FakeSession(execute_results=[events, [version]])
    queue = deque([session])
    repo = MapRepository(session_factory=lambda: _Context(queue.popleft()))
    summary = await repo.skill_usage_summary(skill_id)
    assert summary["total_model_calls"] == 5
    assert summary["total_model_tokens"] == 1300
    assert summary["diagnosis_model_calls"] == 5
    assert summary["events_by_kind"] == {
        "compile": 1,
        "verification_replay": 1,
        "heal_diagnosis": 2,
        "run_replay": 1,
        "activation": 1,
    }
    latest = summary["latest_version"]
    assert latest["version_number"] == 2
    assert latest["lifecycle_status"] == "active"
    assert latest["replay_count"] == 4
    assert latest["heal_count"] == 1
    assert latest["last_replay_result"] == "passed"


@pytest.mark.asyncio
async def test_t_ac2_usage_summary_for_an_unknown_skill_is_zeroed():
    session = _FakeSession(execute_results=[[], []])
    queue = deque([session])
    repo = MapRepository(session_factory=lambda: _Context(queue.popleft()))
    summary = await repo.skill_usage_summary(uuid4())
    assert summary["total_model_calls"] == 0
    assert summary["events_by_kind"] == {}
    assert summary["latest_version"] is None
