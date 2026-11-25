"""Phase 1b re-point endpoints (doc 16 sections 10.1-10.3, tests T-RP1
to T-RP5, plus T-RP6/T-RP7 for the inventory and journeys reads).

House style follows test_app_map_api.py: route functions are called
directly with a queue of fake sessions programmed in call order.
"""

from collections import deque
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request, Response
from markettwin_control_api.api import app_maps
from markettwin_database.models.knowledge import (
    AppMap,
    MapElement,
    MapField,
    MapForm,
    MapJourney,
    MapPage,
    MapPageState,
    Skill,
    SkillVersion,
)
from markettwin_database.models.testing import Application, ApplicationTarget


class Context:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *args):
        return False


def request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": []})


class FakeResult:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def scalars(self):
        rows = self._rows
        return SimpleNamespace(
            first=lambda: rows[0] if rows else None,
            all=lambda: list(rows),
        )

    def scalar(self):
        return self._rows[0] if self._rows else None

    def scalar_one(self):
        return self._rows[0]

    def all(self):
        return list(self._rows)


class FakeSession:
    def __init__(self, *, get_results=None, execute_results=()):
        self._get_results = dict(get_results or {})
        self._execute_results = deque(execute_results)
        self.added: list[object] = []
        self.flush = AsyncMock()

    def begin(self):
        return Context(None)

    async def get(self, model, ident):
        return self._get_results.get((model, ident))

    async def execute(self, statement):
        rows = self._execute_results.popleft() if self._execute_results else []
        return FakeResult(rows)

    def add(self, row):
        self.added.append(row)


def patch_database(monkeypatch, module, *sessions):
    queue = deque(sessions)
    monkeypatch.setattr(
        module,
        "get_database_runtime",
        lambda _: SimpleNamespace(session_factory=lambda: Context(queue.popleft())),
    )
    monkeypatch.setattr(
        module, "require_app_map_access", AsyncMock(return_value=uuid4())
    )


def make_scope():
    workspace_id, application_id, target_id = uuid4(), uuid4(), uuid4()
    application = Application(
        id=application_id,
        workspace_id=workspace_id,
        created_by_user_id=uuid4(),
        name="Demo Store",
        status="active",
    )
    target = ApplicationTarget(
        id=target_id,
        application_id=application_id,
        name="Production",
        environment="production",
        base_url="https://example.com/",
        status="active",
    )
    gets = {
        (Application, application_id): application,
        (ApplicationTarget, target_id): target,
    }
    return workspace_id, application_id, target_id, gets


def make_map(workspace_id, application_id, target_id, **overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "workspace_id": workspace_id,
        "application_id": application_id,
        "target_id": target_id,
        "version_number": 2,
        "status": "ready",
        "release_state": "partial",
        "release_scope": "inventory",
        "base_url": "https://example.com/",
        "builder_version": "census-1a.1",
        "census_config": {},
        "census_metrics": {},
        "pattern_stats": {},
        "gate_metrics": {},
        "census_expected_count": 0,
        "census_reachable_count": 0,
        "mapping_spend_calls": 0,
        "mapping_spend_tokens": 0,
        "mapping_spend_seconds": 0.0,
        "harvest_status": "not_started",
        "harvest_metrics": {},
        "started_at": now,
        "completed_at": now,
    }
    values.update(overrides)
    return AppMap(**values)


def make_skill(app_map, **overrides):
    values = {
        "id": uuid4(),
        "workspace_id": app_map.workspace_id,
        "blueprint_id": uuid4(),
        "created_by_user_id": uuid4(),
        "name": "Get a demo",
        "status": "active",
        "application_id": app_map.application_id,
        "target_id": app_map.target_id,
        "app_map_id": app_map.id,
    }
    values.update(overrides)
    return Skill(**values)


def make_skill_version(skill, **overrides):
    values = {
        "id": uuid4(),
        "workspace_id": skill.workspace_id,
        "blueprint_id": skill.blueprint_id,
        "blueprint_version_id": uuid4(),
        "skill_id": skill.id,
        "version_number": 1,
        "status": "draft",
        "definition_json": {},
        "generation_metadata": {},
        "created_by_user_id": uuid4(),
        "lifecycle_status": "verified",
        "last_replay_result": "passed",
        "last_replay_at": datetime.now(UTC),
        "heal_count": 0,
    }
    values.update(overrides)
    return SkillVersion(**values)


# T-RP1: the trigger starts a harvest on a census-ready map (202) and
# persists the owner's journey-terminal choice into harvest_metrics.
@pytest.mark.asyncio
async def test_trigger_starts_harvest_and_persists_journey_terminal(monkeypatch):
    workspace_id, application_id, target_id, gets = make_scope()
    app_map = make_map(workspace_id, application_id, target_id)
    scope = FakeSession(get_results=gets)
    in_scope = FakeSession(execute_results=[[app_map]])
    start = FakeSession(get_results={(AppMap, app_map.id): app_map})
    patch_database(monkeypatch, app_maps, scope, in_scope, start)
    response = Response()
    result = await app_maps.trigger_app_map_harvest(
        workspace_id,
        application_id,
        target_id,
        app_map.id,
        request(),
        response,
        app_maps.AppMapHarvestRequest(
            journey_terminal_url="https://example.com/get-a-demo"
        ),
    )
    assert response.status_code == 202
    assert result.map_id == app_map.id
    assert result.harvest_status == "building"
    assert app_map.harvest_status == "building"
    assert app_map.harvest_started_at is not None
    assert (
        app_map.harvest_metrics["journey_terminal_url"]
        == "https://example.com/get-a-demo"
    )


# T-RP2: a second trigger while a harvest is in flight answers 200 and
# does not restart the job.
@pytest.mark.asyncio
async def test_trigger_in_flight_returns_200(monkeypatch):
    workspace_id, application_id, target_id, gets = make_scope()
    started_at = datetime.now(UTC)
    app_map = make_map(
        workspace_id,
        application_id,
        target_id,
        harvest_status="building",
        harvest_started_at=started_at,
    )
    scope = FakeSession(get_results=gets)
    in_scope = FakeSession(execute_results=[[app_map]])
    start = FakeSession(get_results={(AppMap, app_map.id): app_map})
    patch_database(monkeypatch, app_maps, scope, in_scope, start)
    response = Response()
    result = await app_maps.trigger_app_map_harvest(
        workspace_id, application_id, target_id, app_map.id, request(), response, None
    )
    assert response.status_code == 200
    assert result.harvest_status == "building"
    assert app_map.harvest_started_at == started_at


# T-RP3: a map that is not census-ready cannot be harvested (409), and a
# map outside the path's scope reads as missing (404).
@pytest.mark.asyncio
async def test_trigger_rejects_non_ready_and_out_of_scope_maps(monkeypatch):
    workspace_id, application_id, target_id, gets = make_scope()
    building = make_map(workspace_id, application_id, target_id, status="building")
    scope = FakeSession(get_results=gets)
    in_scope = FakeSession(execute_results=[[building]])
    patch_database(monkeypatch, app_maps, scope, in_scope)
    with pytest.raises(HTTPException) as failure:
        await app_maps.trigger_app_map_harvest(
            workspace_id,
            application_id,
            target_id,
            building.id,
            request(),
            Response(),
            None,
        )
    assert failure.value.status_code == 409

    scope = FakeSession(get_results=gets)
    missing = FakeSession(execute_results=[[]])
    patch_database(monkeypatch, app_maps, scope, missing)
    with pytest.raises(HTTPException) as failure:
        await app_maps.trigger_app_map_harvest(
            workspace_id, application_id, target_id, uuid4(), request(), Response(), None
        )
    assert failure.value.status_code == 404


# T-RP4: the summary carries the harvest block and the skills list.
@pytest.mark.asyncio
async def test_summary_includes_harvest_block_and_skills(monkeypatch):
    workspace_id, application_id, target_id, gets = make_scope()
    app_map = make_map(
        workspace_id,
        application_id,
        target_id,
        harvest_status="partial",
        harvest_metrics={
            "template_groups": {"groups": 2, "unenriched_groups": ["g-two"]}
        },
        mapping_spend_calls=2,
        mapping_spend_tokens=900,
    )
    skill = make_skill(app_map)
    version = make_skill_version(skill)
    scope = FakeSession(get_results=gets)
    ready_session = FakeSession(execute_results=[[app_map]])
    counts_session = FakeSession(
        execute_results=[[("fetch_ok", 4), ("gone", 1)]]
    )
    harvest_session = FakeSession(
        execute_results=[[("visited", 3), ("blocked_auth", 1)]]
    )
    skills_session = FakeSession(execute_results=[[skill], [version]])
    patch_database(
        monkeypatch,
        app_maps,
        scope,
        ready_session,
        counts_session,
        harvest_session,
        skills_session,
    )
    summary = await app_maps.get_app_map_summary(
        workspace_id, application_id, target_id, request()
    )
    assert summary.counts.expected == 5
    assert summary.counts.reachable == 4
    assert summary.harvest.status == "partial"
    assert summary.harvest.visited == 3
    assert summary.harvest.reachable == 4
    assert summary.harvest.blocked == 1
    assert summary.harvest.failed == 0
    assert summary.harvest.unprobed_budget == 0
    assert summary.harvest.template_groups == 2
    assert summary.harvest.enriched_groups == 1
    assert summary.harvest.spend.calls == 2
    assert summary.harvest.spend.tokens == 900
    assert len(summary.skills) == 1
    assert summary.skills[0].name == "Get a demo"
    assert summary.skills[0].lifecycle_status == "verified"
    assert summary.skills[0].last_replay_result == "passed"
    assert summary.skills[0].last_replay_at is not None


def make_page(app_map, **overrides):
    values = {
        "id": uuid4(),
        "workspace_id": app_map.workspace_id,
        "application_id": app_map.application_id,
        "target_id": app_map.target_id,
        "app_map_id": app_map.id,
        "canonical_url": "https://example.com/",
        "route_pattern": "/",
        "source_kinds": ["sitemap"],
        "crawl_status": "fetch_ok",
        "http_status": 200,
        "redirect_target": None,
        "content_type": "text/html",
        "title": "Home",
        "requires_auth": False,
        "roles_seen": [],
        "source": "census",
        "confidence": "high",
        "last_verified_at": datetime.now(UTC),
        "harvest_status": "visited",
    }
    values.update(overrides)
    return MapPage(**values)


def make_state(app_map, page, **overrides):
    values = {
        "id": uuid4(),
        "workspace_id": app_map.workspace_id,
        "application_id": app_map.application_id,
        "target_id": app_map.target_id,
        "app_map_id": app_map.id,
        "map_page_id": page.id,
        "state_key": "default",
        "state_kind": "default",
        "state_id": "state-abc",
        "element_signature": "button|Go",
        "form_signature": None,
        "source": "harvest",
        "confidence": "high",
        "last_verified_at": datetime.now(UTC),
    }
    values.update(overrides)
    return MapPageState(**values)


# T-RP6: the inventory read assembles states, elements, and forms with
# their fields for one page.
@pytest.mark.asyncio
async def test_page_inventory_read(monkeypatch):
    workspace_id, application_id, target_id, gets = make_scope()
    app_map = make_map(workspace_id, application_id, target_id)
    page = make_page(app_map)
    state = make_state(app_map, page)
    element = MapElement(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        app_map_id=app_map.id,
        map_page_id=page.id,
        map_page_state_id=state.id,
        role="button",
        name="Go",
        ordinal=0,
        label_text=None,
        actionability="click",
        locators=[{"kind": "role_name", "value": "button|Go", "stability": 2}],
        safety_class="read",
        navigates_to_url="https://example.com/next",
        opens_state_key=None,
        source="harvest",
        confidence="high",
        last_verified_at=datetime.now(UTC),
    )
    form = MapForm(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        app_map_id=app_map.id,
        map_page_id=page.id,
        map_page_state_id=state.id,
        form_key="form-0",
        method="post",
        action_url=None,
        submit_element_id=None,
        success_transition_id=None,
        probe_status="unprobed_readonly",
        source="harvest",
        confidence="high",
        last_verified_at=datetime.now(UTC),
    )
    field = MapField(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        app_map_id=app_map.id,
        form_id=form.id,
        element_id=None,
        label="Email",
        field_type="email",
        name_attr="email",
        required=True,
        constraints={},
        options=[],
        help_text=None,
        error_text_observed=None,
        validation_source="dom",
        ordinal=0,
        source="harvest",
        confidence="high",
        last_verified_at=datetime.now(UTC),
    )
    scope = FakeSession(get_results=gets)
    sessions = [
        FakeSession(execute_results=[[app_map]]),
        FakeSession(execute_results=[[page]]),
        FakeSession(execute_results=[[state]]),
        FakeSession(execute_results=[[element]]),
        FakeSession(execute_results=[[form]]),
        FakeSession(execute_results=[[field]]),
    ]
    patch_database(monkeypatch, app_maps, scope, *sessions)
    inventory = await app_maps.get_app_map_page_inventory(
        workspace_id, application_id, target_id, page.id, request()
    )
    assert inventory.page.canonical_url == "https://example.com/"
    assert inventory.page.harvest_status == "visited"
    assert len(inventory.states) == 1
    assert inventory.states[0].signatures_present is True
    assert inventory.states[0].element_count == 1
    assert inventory.states[0].form_count == 1
    assert inventory.elements[0].role == "button"
    assert inventory.elements[0].navigates_to_url == "https://example.com/next"
    assert inventory.forms[0].fields[0].label == "Email"
    assert inventory.forms[0].fields[0].field_type == "email"


# T-RP7: the journeys read resolves step pages/elements and the compiled
# skill's lifecycle.
@pytest.mark.asyncio
async def test_journeys_read(monkeypatch):
    workspace_id, application_id, target_id, gets = make_scope()
    app_map = make_map(workspace_id, application_id, target_id)
    page = make_page(app_map)
    state = make_state(app_map, page)
    skill = make_skill(app_map)
    version = make_skill_version(skill)
    element = MapElement(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        app_map_id=app_map.id,
        map_page_id=page.id,
        map_page_state_id=state.id,
        role="link",
        name="Get a demo",
        ordinal=0,
        label_text=None,
        actionability="click",
        locators=[],
        safety_class="read",
        navigates_to_url="https://example.com/get-a-demo",
        opens_state_key=None,
        source="harvest",
        confidence="high",
        last_verified_at=datetime.now(UTC),
    )
    journey = MapJourney(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        app_map_id=app_map.id,
        name="Get a demo",
        intent="Reach the demo page",
        preconditions=[],
        steps=[
            {
                "map_page_state_id": str(state.id),
                "element_id": str(element.id),
                "action": "click",
                "value_source": "none",
            }
        ],
        success_state_id=state.id,
        skill_id=skill.id,
        selection="rule",
        source="harvest",
        confidence="high",
        last_verified_at=datetime.now(UTC),
    )
    scope = FakeSession(get_results=gets)
    sessions = [
        FakeSession(execute_results=[[app_map]]),
        FakeSession(execute_results=[[journey]]),
        FakeSession(execute_results=[[state]]),
        FakeSession(execute_results=[[page]]),
        FakeSession(execute_results=[[element]]),
        FakeSession(execute_results=[[skill], [version]]),
    ]
    patch_database(monkeypatch, app_maps, scope, *sessions)
    result = await app_maps.list_app_map_journeys(
        workspace_id, application_id, target_id, request()
    )
    assert len(result.items) == 1
    item = result.items[0]
    assert item.name == "Get a demo"
    assert item.selection == "rule"
    assert item.skill is not None
    assert item.skill.name == "Get a demo"
    assert item.skill.lifecycle_status == "verified"
    assert item.steps[0].page_url == "https://example.com/"
    assert item.steps[0].role == "link"
    assert item.steps[0].name == "Get a demo"
