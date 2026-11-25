"""Phase 3 persona-fence tests (doc 22 section 11, 17): T-PC2 —
the login seam's selection follows the Phase 3 serving rule
(platform only; active > replay_verified > draft) and the seam's
lifecycle advances use the six-state spellings through the shared
authority. T-PC3 — persona_run.py carries no knowledge/lifecycle
surface at all: personas reach skills only through the shared
case-execution seam, which declares the consumer from the run kind
(F5(B)); the module must stay import-clean of the library.
"""

import ast
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from markettwin_database.models.knowledge import SkillUsageEvent, SkillVersion
from markettwin_execution_orchestrator.expectations import login_skill

ORCHESTRATOR_SRC = Path(__file__).resolve().parents[1] / "src"


class _FakeSession:
    def __init__(self, *, scalars_results=()):
        self._scalars_results = deque(scalars_results)
        self.added: list = []

    async def scalars(self, statement):
        return self._scalars_results.popleft() if self._scalars_results else []

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        return None


def _version(number, lifecycle):
    return SkillVersion(
        id=uuid4(),
        workspace_id=uuid4(),
        skill_id=uuid4(),
        version_number=number,
        status="draft",
        definition_json={},
        generation_metadata={},
        lifecycle_status=lifecycle,
        package={"kind": "login_skill"},
        heal_count=0,
        replay_count=0,
    )


@pytest.mark.asyncio
async def test_t_pc2_login_selection_prefers_active_over_newer_draft():
    versions = [
        _version(3, "draft"),
        _version(2, "active"),
        _version(1, "replay_verified"),
    ]
    session = _FakeSession(scalars_results=[versions])
    selected = await login_skill.select_login_version(
        session, app_map_id=uuid4()
    )
    assert selected is versions[1]
    session = _FakeSession(scalars_results=[[_version(2, "draft"), _version(1, "replay_verified")]])
    selected = await login_skill.select_login_version(
        session, app_map_id=uuid4()
    )
    assert selected.lifecycle_status == "replay_verified"
    session = _FakeSession(scalars_results=[[_version(1, "suspect")]])
    # The query itself excludes suspect rows; an all-suspect answer
    # set (impossible via the real query) still selects nothing
    # selectable by preference.
    selected = await login_skill.select_login_version(
        session, app_map_id=uuid4()
    )
    assert selected is None


def test_t_pc2_login_selection_query_is_platform_only():
    source = Path(login_skill.__file__).read_text(encoding="utf-8")
    body = source[source.index("async def select_login_version"):]
    body = body[: body.index("def login_mode_allowed")]
    assert 'Skill.skill_kind == "platform"' in body
    assert '"active", "replay_verified", "draft"' in body


@pytest.mark.asyncio
async def test_t_pc2_seam_replay_advances_draft_to_replay_verified():
    version = _version(1, "draft")
    passed = SimpleNamespace(id=uuid4(), result="passed")
    session = _FakeSession(scalars_results=[[passed, passed]])
    await login_skill.record_login_replay(
        session, version=version, app_map_id=uuid4(), result="passed"
    )
    assert version.lifecycle_status == "replay_verified"
    events = [row for row in session.added if isinstance(row, SkillUsageEvent)]
    assert len(events) == 1
    assert events[0].kind == "verification_replay"
    assert events[0].from_status == "draft"
    assert events[0].to_status == "replay_verified"


@pytest.mark.asyncio
async def test_t_pc2_seam_failures_suspect_an_active_login():
    version = _version(2, "active")
    failed = SimpleNamespace(id=uuid4(), result="failed")
    session = _FakeSession(scalars_results=[[failed, failed]])
    await login_skill.record_login_replay(
        session, version=version, app_map_id=uuid4(), result="failed"
    )
    assert version.lifecycle_status == "suspect"
    events = [row for row in session.added if isinstance(row, SkillUsageEvent)]
    assert len(events) == 1
    assert events[0].kind == "demotion"
    assert events[0].payload["demotion"]["kind"] == "seam_failures"


def test_t_pc3_persona_run_is_import_clean_of_the_library():
    path = (
        ORCHESTRATOR_SRC
        / "markettwin_execution_orchestrator/workflow/persona_run.py"
    )
    source = path.read_text(encoding="utf-8-sig")
    module = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
            imported.extend(alias.name for alias in node.names)
    banned = ("knowledge", "lifecycle", "skill", "map_lookup")
    offenders = [
        name for name in imported if any(b in name.lower() for b in banned)
    ]
    assert offenders == []
    # And no direct skill handling of any kind: the seam owns it.
    assert "skill" not in source.lower()
