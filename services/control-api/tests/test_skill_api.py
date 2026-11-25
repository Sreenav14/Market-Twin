"""Phase 3 skill-library endpoints (doc 22 section 12.2): the five
routes over the repository — list (with T-AC3's diagnosis-spend
aggregation read off the ledger), usage, retire, reverify, and
journey compile — exercised through the handlers with the module's
access/runtime seams patched, the Phase 2 API-test pattern.
"""

from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from markettwin_control_api.api import app_maps
from markettwin_database.models.knowledge import (
    AppMap,
    MapJourney,
    Skill,
    SkillUsageEvent,
    SkillVersion,
)
from markettwin_database.models.testing import Application, ApplicationTarget


def _result(rows):
    rows = list(rows)
    return SimpleNamespace(
        scalars=lambda: SimpleNamespace(
            all=lambda: list(rows),
            first=lambda: rows[0] if rows else None,
        ),
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
    def __init__(self, *, get_results=None, execute_results=()):
        self._get_results = dict(get_results or {})
        self._execute_results = deque(execute_results)
        self.added: list[object] = []

    def begin(self):
        return _Context(None)

    async def get(self, model, ident):
        return self._get_results.get((model, ident))

    async def execute(self, statement):
        rows = self._execute_results.popleft() if self._execute_results else []
        return _result(rows)

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        return None


def _request():
    from fastapi import Request

    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def _patch(monkeypatch, *sessions):
    queue = deque(sessions)
    monkeypatch.setattr(
        app_maps,
        "get_database_runtime",
        lambda _request: SimpleNamespace(
            session_factory=lambda: _Context(queue.popleft())
        ),
    )
    monkeypatch.setattr(
        app_maps, "require_app_map_access", AsyncMock(return_value=uuid4())
    )


def _scope(app_map):
    application = Application(
        id=app_map.application_id,
        workspace_id=app_map.workspace_id,
        created_by_user_id=uuid4(),
        name="Demo",
        status="active",
    )
    target = ApplicationTarget(
        id=app_map.target_id,
        application_id=app_map.application_id,
        name="Prod",
        environment="production",
        base_url="https://example.com/",
        status="active",
    )
    return _FakeSession(
        get_results={
            (Application, app_map.application_id): application,
            (ApplicationTarget, app_map.target_id): target,
        }
    )


def _map():
    return AppMap(
        id=uuid4(),
        workspace_id=uuid4(),
        application_id=uuid4(),
        target_id=uuid4(),
        version_number=3,
        status="ready",
        base_url="https://example.com/",
        builder_version="census-1a.1",
        census_config={},
        census_metrics={},
        pattern_stats={},
        gate_metrics={},
        harvest_metrics={},
    )


def _skill(app_map, *, kind="journey", name="checkout"):
    return Skill(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        name=name,
        skill_kind=kind,
    )


def _version(skill, *, lifecycle="active", number=1, app_map_id=None):
    return SkillVersion(
        id=uuid4(),
        workspace_id=skill.workspace_id,
        skill_id=skill.id,
        version_number=number,
        status="draft",
        definition_json={},
        package={},
        lifecycle_status=lifecycle,
        heal_count=0,
        replay_count=4,
        app_map_id=app_map_id,
    )


def _lines_session(skill, versions, *, diagnosis=0):
    return _FakeSession(
        execute_results=[
            [skill],
            versions,
            [(skill.id, diagnosis)],
            [],  # demotion/quarantine reason events
        ]
    )


@pytest.mark.asyncio
async def test_list_endpoint_serves_lines_with_ledger_diagnosis_spend(
    monkeypatch,
):
    app_map = _map()
    skill = _skill(app_map)
    version = _version(skill, lifecycle="active")
    _patch(
        monkeypatch,
        _scope(app_map),
        _lines_session(skill, [version], diagnosis=3),
    )
    result = await app_maps.list_app_map_skills(
        app_map.workspace_id, app_map.application_id, app_map.target_id,
        _request(),
    )
    assert len(result.items) == 1
    line = result.items[0]
    assert line.name == "checkout"
    assert line.lifecycle_status == "active"
    assert line.version_number == 1
    assert line.replay_count == 4
    # T-AC3: the diagnosis spend on the line is the ledger's
    # heal_diagnosis sum for the skill, not a recomputation.
    assert line.diagnosis_model_calls == 3
    assert line.status_reason is None


@pytest.mark.asyncio
async def test_usage_endpoint_returns_the_ledger_summary(monkeypatch):
    app_map = _map()
    skill = _skill(app_map)
    version = _version(skill, lifecycle="active")
    events = [
        SkillUsageEvent(
            id=uuid4(),
            skill_id=skill.id,
            skill_version_id=version.id,
            kind="heal_diagnosis",
            from_status="suspect",
            to_status="suspect",
            result="failed",
            model_calls=2,
            model_tokens=500,
            payload={},
        ),
        SkillUsageEvent(
            id=uuid4(),
            skill_id=skill.id,
            skill_version_id=version.id,
            kind="compile",
            from_status=None,
            to_status="draft",
            result="applied",
            model_calls=0,
            model_tokens=0,
            payload={},
        ),
    ]
    summary_session = _FakeSession(execute_results=[events, [version]])
    _patch(
        monkeypatch,
        _scope(app_map),
        _lines_session(skill, [version]),
        summary_session,
    )
    result = await app_maps.get_app_map_skill_usage(
        app_map.workspace_id, app_map.application_id, app_map.target_id,
        skill.id, _request(),
    )
    assert result.total_model_calls == 2
    assert result.total_model_tokens == 500
    assert result.diagnosis_model_calls == 2
    assert result.events_by_kind == {"heal_diagnosis": 1, "compile": 1}
    assert result.latest_version["lifecycle_status"] == "active"


@pytest.mark.asyncio
async def test_usage_endpoint_404s_a_skill_outside_the_scope(monkeypatch):
    app_map = _map()
    _patch(
        monkeypatch,
        _scope(app_map),
        _FakeSession(execute_results=[[]]),
    )
    with pytest.raises(HTTPException) as excinfo:
        await app_maps.get_app_map_skill_usage(
            app_map.workspace_id, app_map.application_id, app_map.target_id,
            uuid4(), _request(),
        )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_retire_endpoint_retires_the_latest_version(monkeypatch):
    app_map = _map()
    skill = _skill(app_map)
    version = _version(skill, lifecycle="active")
    transition_session = _FakeSession(
        get_results={(SkillVersion, version.id): version}
    )
    _patch(
        monkeypatch,
        _scope(app_map),
        _lines_session(skill, [version]),
        transition_session,
    )
    result = await app_maps.retire_app_map_skill(
        app_map.workspace_id, app_map.application_id, app_map.target_id,
        skill.id, _request(), None,
    )
    assert result.status == "retired"
    assert version.lifecycle_status == "retired"
    assert version.retired_reason == "owner"
    events = [
        row for row in transition_session.added
        if isinstance(row, SkillUsageEvent)
    ]
    assert len(events) == 1
    assert events[0].kind == "retirement"


@pytest.mark.asyncio
async def test_reverify_endpoint_queues_a_draft_for_the_poller(monkeypatch):
    app_map = _map()
    skill = _skill(app_map)
    version = _version(skill, lifecycle="draft")
    select_session = _FakeSession(execute_results=[[app_map]])
    reverify_session = _FakeSession(
        get_results={(Skill, skill.id): skill, (AppMap, app_map.id): app_map},
        execute_results=[[version]],
    )
    _patch(
        monkeypatch,
        _scope(app_map),
        _lines_session(skill, [version]),
        select_session,
        reverify_session,
    )
    result = await app_maps.reverify_app_map_skill(
        app_map.workspace_id, app_map.application_id, app_map.target_id,
        skill.id, _request(),
    )
    assert result.status == "queued"


@pytest.mark.asyncio
async def test_reverify_endpoint_reports_a_current_platform_skill(monkeypatch):
    app_map = _map()
    skill = _skill(app_map, kind="platform", name="login")
    version = _version(skill, lifecycle="active", app_map_id=app_map.id)
    select_session = _FakeSession(execute_results=[[app_map]])
    reverify_session = _FakeSession(
        get_results={(Skill, skill.id): skill, (AppMap, app_map.id): app_map},
        execute_results=[[version]],
    )
    _patch(
        monkeypatch,
        _scope(app_map),
        _lines_session(skill, [version]),
        select_session,
        reverify_session,
    )
    result = await app_maps.reverify_app_map_skill(
        app_map.workspace_id, app_map.application_id, app_map.target_id,
        skill.id, _request(),
    )
    assert result.status == "current"


@pytest.mark.asyncio
async def test_compile_endpoint_queues_the_journey_on_the_map(monkeypatch):
    app_map = _map()
    journey = MapJourney(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        app_map_id=app_map.id,
        name="Checkout",
        steps=[],
        preconditions=[],
        success_state_id=uuid4(),
        selection="rule",
    )
    select_session = _FakeSession(execute_results=[[app_map]])
    compile_session = _FakeSession(
        get_results={
            (MapJourney, journey.id): journey,
            (AppMap, app_map.id): app_map,
        }
    )
    _patch(monkeypatch, _scope(app_map), select_session, compile_session)
    result = await app_maps.compile_app_map_journey(
        app_map.workspace_id, app_map.application_id, app_map.target_id,
        journey.id, _request(),
    )
    assert result.status == "queued"
    assert app_map.harvest_metrics["skill_compile_requests"] == [
        str(journey.id)
    ]


@pytest.mark.asyncio
async def test_compile_endpoint_404s_a_journey_from_another_map(monkeypatch):
    app_map = _map()
    journey = MapJourney(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        app_map_id=uuid4(),  # a different map
        name="Checkout",
        steps=[],
        preconditions=[],
        success_state_id=uuid4(),
        selection="rule",
    )
    select_session = _FakeSession(execute_results=[[app_map]])
    compile_session = _FakeSession(
        get_results={(MapJourney, journey.id): journey}
    )
    _patch(monkeypatch, _scope(app_map), select_session, compile_session)
    with pytest.raises(HTTPException) as excinfo:
        await app_maps.compile_app_map_journey(
            app_map.workspace_id, app_map.application_id, app_map.target_id,
            journey.id, _request(),
        )
    assert excinfo.value.status_code == 404
