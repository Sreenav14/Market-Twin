"""Run-creation app_map snapshot block (Phase 1a, section 9.3, T-N)."""

from collections import deque
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Request
from markettwin_control_api.api import test_run as test_run_api
from markettwin_control_api.database import DatabaseRuntime
from markettwin_control_api.persistence.repositories import (
    AllowedOriginRecord,
    ApplicationRecord,
    TargetAuthorizationRecord,
    TargetRecord,
    TestRunRecord,
    WorkspaceAccess,
)
from markettwin_database.models.knowledge import (
    AppMap,
    MapElement,
    MapJourney,
    MapPage,
    MapPageState,
    Skill,
    SkillVersion,
)

BUILT_AT = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


class AsyncContext:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


def _fake_query_result(rows):
    """One result shape for every accessor the readers use: the Phase 1a
    block builder calls .all(); the Phase 1b repository helpers call
    .scalars().all()/.first() on execute results."""
    return SimpleNamespace(
        all=lambda: list(rows),
        scalars=lambda: SimpleNamespace(
            all=lambda: list(rows),
            first=lambda: rows[0] if rows else None,
        ),
        scalar_one=lambda: rows[0] if rows else None,
    )


class FakeDatabaseSession:
    """Session fake: repository fakes ignore it; the map block queries it."""

    def __init__(self, *, execute_results=(), scalars_results=()):
        self._execute_results = deque(execute_results)
        self._scalars_results = deque(scalars_results)

    def begin(self):
        return AsyncContext(None)

    async def execute(self, statement):
        rows = self._execute_results.popleft() if self._execute_results else []
        return _fake_query_result(rows)

    async def scalars(self, statement):
        rows = self._scalars_results.popleft() if self._scalars_results else []
        return _fake_query_result(rows)

    async def get(self, model, primary_key):
        return None

    async def refresh(self, instance):
        return None


class FakeApplicationRepository:
    def __init__(self, application):
        self._application = application

    async def get_for_user(self, *, application_id, user_id):
        return self._application


class FakeWorkspaceRepository:
    def __init__(self, workspace):
        self._workspace = workspace

    async def get_for_user(self, *, workspace_id, user_id):
        return self._workspace


class FakeTargetRepository:
    def __init__(self, target):
        self._target = target

    async def get_for_user(self, *, target_id, user_id):
        return self._target


class FakeAuthorizationRepository:
    def __init__(self, authorization):
        self._authorization = authorization

    async def get_active(self, *, target_id):
        return self._authorization


class FakeTestRunRepository:
    def __init__(self, test_run):
        self._test_run = test_run
        self.create_arguments = None

    async def create(self, **kwargs):
        self.create_arguments = kwargs
        return self._test_run


def make_request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": []})


def make_records():
    user_id, workspace_id, application_id, target_id = (uuid4() for _ in range(4))
    application = ApplicationRecord(
        application_id=application_id,
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        name="Demo Store",
        description=None,
        status="active",
    )
    workspace = WorkspaceAccess(
        workspace_id=workspace_id, name="Demo Workspace", status="active", role="owner"
    )
    target = TargetRecord(
        target_id=target_id,
        application_id=application_id,
        name="Production",
        environment="production",
        base_url="https://example.com/",
        requires_auth=False,
        status="active",
        allowed_origins=(
            AllowedOriginRecord(
                scheme="https", hostname="example.com", port=443,
                include_subdomains=False,
            ),
        ),
    )
    now = datetime.now(UTC)
    authorization = TargetAuthorizationRecord(
        authorization_id=uuid4(),
        target_id=target_id,
        created_by_user_id=user_id,
        authorized_by_user_id=user_id,
        status="authorized",
        authorization_basis="Owned application.",
        created_at=now,
        authorized_at=now,
        revoked_at=None,
        expires_at=None,
    )
    persisted_run = TestRunRecord(
        test_run_id=uuid4(),
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=target_id,
        created_by_user_id=user_id,
        status="draft",
        target_snapshot=test_run_api.build_target_snapshot(target),
        configuration_snapshot={},
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )
    return user_id, application, workspace, target, authorization, persisted_run


def make_map(application, target, *, version_number=3):
    return AppMap(
        id=uuid4(),
        workspace_id=application.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        version_number=version_number,
        status="ready",
        release_state="partial",
        release_scope="inventory",
        base_url="https://example.com/",
        builder_version="census-1a.1",
        census_config={},
        census_metrics={},
        pattern_stats={},
        gate_metrics={},
        census_expected_count=0,
        census_reachable_count=0,
        mapping_spend_calls=0,
        mapping_spend_tokens=0,
        mapping_spend_seconds=0.0,
        started_at=BUILT_AT,
        completed_at=BUILT_AT,
    )


def make_page(application, target, app_map, *, url, crawl_status="fetch_ok",
              pattern="/", redirect_target=None):
    return MapPage(
        id=uuid4(),
        workspace_id=application.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        app_map_id=app_map.id,
        canonical_url=url,
        route_pattern=pattern,
        source_kinds=["sitemap"],
        crawl_status=crawl_status,
        http_status=200,
        redirect_target=redirect_target,
        content_type="text/html",
        title="A page",
        requires_auth=False,
        roles_seen=[],
        source="census",
        confidence="high",
        last_verified_at=BUILT_AT,
    )


def patch_run_creation(
    monkeypatch, *, records, session, app_map
) -> FakeTestRunRepository:
    user_id, application, workspace, target, authorization, persisted_run = records
    repository = FakeTestRunRepository(persisted_run)
    database = SimpleNamespace(session_factory=lambda: AsyncContext(session))

    async def authenticated_user_id(*, request):
        return user_id

    monkeypatch.setattr(test_run_api, "get_authenticated_user_id", authenticated_user_id)
    monkeypatch.setattr(
        test_run_api, "get_database_runtime",
        lambda request: cast(DatabaseRuntime, database),
    )
    monkeypatch.setattr(
        test_run_api, "ApplicationRepository", lambda _: FakeApplicationRepository(application)
    )
    monkeypatch.setattr(
        test_run_api, "WorkspaceRepository", lambda _: FakeWorkspaceRepository(workspace)
    )
    monkeypatch.setattr(
        test_run_api, "TargetRepository", lambda _: FakeTargetRepository(target)
    )
    monkeypatch.setattr(
        test_run_api, "TargetAuthorizationRepository",
        lambda _: FakeAuthorizationRepository(authorization),
    )
    monkeypatch.setattr(test_run_api, "TestRunRepository", lambda _: repository)
    monkeypatch.setattr(
        test_run_api.map_repository, "latest_ready_map",
        AsyncMock(return_value=app_map),
    )

    async def preflight_step(*, database, app_map, settings):
        return app_map.id, {
            "preflight_status": "reused",
            "pinned_via_preflight": False,
            "last_preflight_id": None,
            "last_preflight_at": None,
        }

    monkeypatch.setattr(test_run_api, "_preflight_creation_step", preflight_step)
    return repository


async def create_run(records) -> None:
    _, application, _, target, _, _ = records
    await test_run_api.create_test_run(
        application.application_id,
        test_run_api.CreateTestRunRequest(
            target_id=target.target_id,
            study_brief="Evaluate the shopping and checkout experience.",
        ),
        make_request(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("page_url", ["https://example.com/a", "https://other.example/a"])
async def test_create_learning_run_pins_one_check_to_its_target(monkeypatch, page_url) -> None:
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    session = FakeDatabaseSession(execute_results=[[]], scalars_results=[[]])
    repository = patch_run_creation(monkeypatch, records=records, session=session, app_map=app_map)
    payload = test_run_api.CreateTestRunRequest(
        target_id=target.target_id, name="Open the agents page",
        run_kind="explore_test", study_brief="Learn this visible outcome.",
        learn_task={"page_url": page_url, "expected_text": "Agents"},
    )
    if "other.example" in page_url:
        with pytest.raises(test_run_api.HTTPException) as error:
            await test_run_api.create_test_run(application.application_id, payload, make_request())
        assert error.value.status_code == 422
        assert repository.create_arguments is None
        return

    await test_run_api.create_test_run(application.application_id, payload, make_request())
    snapshot = repository.create_arguments["configuration_snapshot"]
    assert snapshot["learn_task"] is True
    item, = snapshot["harness_work_list"]
    assert item["case"]["steps"][0]["url"] == page_url
    assert item["case"]["expected"][0]["expected_value"] == "Agents"


@pytest.mark.asyncio
async def test_snapshot_includes_ready_map_block(monkeypatch) -> None:
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    page_a = make_page(application, target, app_map,
                       url="https://example.com/a", pattern="/a")
    page_b = make_page(application, target, app_map,
                       url="https://example.com/b", pattern="/b")
    page_old = make_page(
        application, target, app_map, url="https://example.com/old",
        crawl_status="redirect", pattern="/old",
        redirect_target="https://example.com/new",
    )
    default_state = MapPageState(
        id=uuid4(),
        workspace_id=application.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        app_map_id=app_map.id,
        map_page_id=page_a.id,
        state_key="default",
        state_kind="default",
        state_id=None,
        element_signature=None,
        form_signature=None,
        source="census",
        confidence="low",
        last_verified_at=None,
    )
    session = FakeDatabaseSession(
        execute_results=[
            [("fetch_ok", 2), ("redirect", 1), ("blocked_auth", 1), ("gone", 1)]
        ],
        scalars_results=[[page_a, page_b, page_old], [default_state]],
    )
    repository = patch_run_creation(
        monkeypatch, records=records, session=session, app_map=app_map
    )
    await create_run(records)

    assert repository.create_arguments is not None
    block = repository.create_arguments["configuration_snapshot"]["app_map"]
    assert block == {
        "map_id": str(app_map.id),
        "version_number": 3,
        "release_state": "partial",
        "release_scope": "inventory",
        "built_at": BUILT_AT.isoformat(),
        "base_url": "https://example.com/",
        "routes": [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/new",
        ],
        "routes_truncated": False,
        "pages": [
            {
                "url": "https://example.com/a",
                "effective_url": "https://example.com/a",
                "pattern": "/a",
                "status": "fetch_ok",
                "requires_auth": False,
                "states": [
                    {
                        "state_key": "default",
                        "state_id": None,
                        "element_signature": None,
                        "form_signature": None,
                    }
                ],
            },
            {
                "url": "https://example.com/b",
                "effective_url": "https://example.com/b",
                "pattern": "/b",
                "status": "fetch_ok",
                "requires_auth": False,
                "states": [],
            },
            {
                "url": "https://example.com/old",
                "effective_url": "https://example.com/new",
                "pattern": "/old",
                "status": "redirect",
                "requires_auth": False,
                "states": [],
            },
        ],
        "counts": {
            "expected": 5,
            "reachable": 3,
            "blocked_auth": 1,
            "blocked_wall": 0,
            "gone": 1,
        },
        "freshness": _expected_freshness_block(),
    }


@pytest.mark.asyncio
async def test_snapshot_omits_block_when_no_ready_map(monkeypatch) -> None:
    # A building or failed map yields None from latest_ready_map by contract.
    records = make_records()
    session = FakeDatabaseSession()
    repository = patch_run_creation(
        monkeypatch, records=records, session=session, app_map=None
    )
    await create_run(records)
    assert repository.create_arguments is not None
    assert "app_map" not in repository.create_arguments["configuration_snapshot"]


@pytest.mark.asyncio
async def test_snapshot_without_maps_matches_pre_1a_behaviour(monkeypatch) -> None:
    records = make_records()
    _, _, _, _, authorization, _ = records
    session = FakeDatabaseSession()
    repository = patch_run_creation(
        monkeypatch, records=records, session=session, app_map=None
    )
    await create_run(records)
    assert repository.create_arguments is not None
    assert repository.create_arguments["configuration_snapshot"] == {
        "runtime_human_assistance": True,
        "allow_offsite_navigation": False,
        "study_brief": "Evaluate the shopping and checkout experience.",
        "testing_depth": "medium",
        "harness_run_mode": "read_only",
        "authorization_id_at_creation": str(authorization.authorization_id),
    }


@pytest.mark.asyncio
async def test_snapshot_truncates_pages_at_cap_with_full_counts(monkeypatch) -> None:
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    pages = [
        make_page(
            application, target, app_map,
            url=f"https://example.com/p{index:04d}", pattern="/p",
        )
        for index in range(2001)
    ]
    session = FakeDatabaseSession(
        execute_results=[[("fetch_ok", 2001)]],
        scalars_results=[pages, []],
    )
    repository = patch_run_creation(
        monkeypatch, records=records, session=session, app_map=app_map
    )
    await create_run(records)
    assert repository.create_arguments is not None
    block = repository.create_arguments["configuration_snapshot"]["app_map"]
    assert block["routes_truncated"] is True
    assert len(block["pages"]) == 2000
    assert len(block["routes"]) == 2000
    assert block["counts"]["expected"] == 2001
    assert block["counts"]["reachable"] == 2001


@pytest.mark.asyncio
async def test_redirect_page_route_uses_redirect_target(monkeypatch) -> None:
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    page = make_page(
        application, target, app_map, url="https://example.com/old",
        crawl_status="redirect", pattern="/old",
        redirect_target="https://example.com/new",
    )
    session = FakeDatabaseSession(
        execute_results=[[("redirect", 1)]],
        scalars_results=[[page], []],
    )
    repository = patch_run_creation(
        monkeypatch, records=records, session=session, app_map=app_map
    )
    await create_run(records)
    assert repository.create_arguments is not None
    block = repository.create_arguments["configuration_snapshot"]["app_map"]
    assert block["routes"] == ["https://example.com/new"]
    assert block["pages"][0]["url"] == "https://example.com/old"
    assert block["pages"][0]["effective_url"] == "https://example.com/new"


# --- Phase 1b snapshot extension (doc 16 section 11.1, T-N6 to T-N8) ----
# These pass once the H1 patch (wave1-patches/phase1b.md) is applied to
# api/test_run.py by integration; against the Phase 1a builder they fail
# on the missing keys, which is the expected pre-integration state.


def make_state(application, target, app_map, page, *, state_id="state-1"):
    return MapPageState(
        id=uuid4(),
        workspace_id=application.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        app_map_id=app_map.id,
        map_page_id=page.id,
        state_key="default",
        state_kind="default",
        state_id=state_id,
        element_signature="button|Go",
        form_signature=None,
        source="harvest",
        confidence="high",
        last_verified_at=BUILT_AT,
    )


def make_element(application, target, app_map, page, state, *, name="Go",
                 locators=None):
    return MapElement(
        id=uuid4(),
        workspace_id=application.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        app_map_id=app_map.id,
        map_page_id=page.id,
        map_page_state_id=state.id,
        role="button",
        name=name,
        ordinal=0,
        label_text=None,
        actionability="click",
        locators=locators
        if locators is not None
        else [{"kind": "role_name", "value": "button|Go", "stability": 2}],
        safety_class="read",
        navigates_to_url="https://example.com/b",
        opens_state_key=None,
        source="harvest",
        confidence="high",
        last_verified_at=BUILT_AT,
    )


@pytest.mark.asyncio
async def test_snapshot_harvested_map_block_carries_the_1b_extension(monkeypatch) -> None:
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    app_map.harvest_status = "ready"
    app_map.harvest_metrics = {
        "template_groups": {"groups": 3, "unenriched_groups": ["g-three"]}
    }
    page_a = make_page(application, target, app_map,
                       url="https://example.com/a", pattern="/a")
    page_a.harvest_status = "visited"
    page_a.source_kinds = ["sitemap", "link_graph"]
    page_b = make_page(application, target, app_map,
                       url="https://example.com/b", pattern="/b")
    page_b.harvest_status = "visited"
    state_a = make_state(application, target, app_map, page_a, state_id="s-a")
    state_b = make_state(application, target, app_map, page_b, state_id="s-b")
    element_a = make_element(application, target, app_map, page_a, state_a)
    journey = MapJourney(
        id=uuid4(),
        workspace_id=application.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        app_map_id=app_map.id,
        name="Get a demo",
        intent="Reach the demo page",
        preconditions=[],
        steps=[
            {
                "map_page_state_id": str(state_a.id),
                "element_id": str(element_a.id),
                "action": "click",
                "value_source": "none",
            }
        ],
        success_state_id=state_b.id,
        skill_id=None,
        selection="rule",
        source="harvest",
        confidence="high",
        last_verified_at=BUILT_AT,
    )
    skill = Skill(
        id=uuid4(),
        workspace_id=application.workspace_id,
        blueprint_id=uuid4(),
        created_by_user_id=uuid4(),
        name="Get a demo",
        skill_kind="journey",
        status="active",
        application_id=application.application_id,
        target_id=target.target_id,
        app_map_id=app_map.id,
    )
    other_skill = Skill(
        id=uuid4(),
        workspace_id=application.workspace_id,
        blueprint_id=uuid4(),
        created_by_user_id=uuid4(),
        name="Other journey",
        status="active",
        application_id=application.application_id,
        target_id=target.target_id,
        app_map_id=app_map.id,
    )

    def version(skill_row, number, lifecycle, **extra):
        values = {
            "id": uuid4(),
            "workspace_id": application.workspace_id,
            "blueprint_id": skill_row.blueprint_id,
            "blueprint_version_id": uuid4(),
            "skill_id": skill_row.id,
            "version_number": number,
            "status": "draft",
            "definition_json": {},
            "generation_metadata": {},
            "created_by_user_id": uuid4(),
            "lifecycle_status": lifecycle,
            "heal_count": 0,
        }
        values.update(extra)
        return SkillVersion(**values)

    versions = [
        version(skill, 2, "active",
                definition_json={"case_id": "get_a_demo"},
                package={"name": "get-a-demo"}),
        version(skill, 1, "draft"),
        version(other_skill, 1, "draft"),
    ]
    journey.skill_id = skill.id
    session = FakeDatabaseSession(
        execute_results=[
            [("fetch_ok", 2)],
            [("visited", 2)],
            [0],
            [element_a],
            [journey],
            [skill, other_skill],
            versions,
        ],
        scalars_results=[[page_a, page_b], [state_a, state_b]],
    )
    repository = patch_run_creation(
        monkeypatch, records=records, session=session, app_map=app_map
    )
    await create_run(records)

    assert repository.create_arguments is not None
    block = repository.create_arguments["configuration_snapshot"]["app_map"]
    assert block["counts"] == {
        "expected": 2,
        "reachable": 2,
        "blocked_auth": 0,
        "blocked_wall": 0,
        "gone": 0,
        "visited_harvest": 2,
        "template_groups": 3,
        "enriched_groups": 2,
        "expectations": 0,
    }
    page_block_a, page_block_b = block["pages"]
    assert page_block_a["harvest_status"] == "visited"
    assert page_block_a["elements"] == [
        {
            "state_key": "default",
            "role": "button",
            "name": "Go",
            "actionability": "click",
            "safety_class": "read",
            "locators": [
                {"kind": "role_name", "value": "button|Go", "stability": 2}
            ],
            "navigates_to_url": "https://example.com/b",
        }
    ]
    assert page_block_b["harvest_status"] == "visited"
    assert page_block_b["elements"] == []
    assert block["elements_truncated"] is False
    assert block["journeys"] == [
        {
            "name": "Get a demo",
            "skill_id": str(skill.id),
            "intent": "Reach the demo page",
            "selection": "rule",
            "terminal_url": "https://example.com/b",
            "steps": journey.steps,
        }
    ]
    # Doc 22 section 7.2 serving: the skill's active version is
    # served in the full entry shape; every non-active version in
    # scope (both drafts here) counts into skills_withheld.
    assert block["skills"] == [
        {
            "name": "Get a demo",
            "skill_id": str(skill.id),
            "skill_version_id": str(versions[0].id),
            "version_number": 2,
            "skill_kind": "journey",
            "lifecycle_status": "active",
            "catalogue": {"name": "get-a-demo", "description": ""},
            "definition": {"case_id": "get_a_demo"},
            "package": {"name": "get-a-demo"},
        }
    ]
    assert block["skills_withheld"] == 2


@pytest.mark.asyncio
async def test_snapshot_byte_cap_drops_elements_in_reverse_reachability_order(
    monkeypatch,
) -> None:
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    app_map.harvest_status = "ready"
    app_map.harvest_metrics = {}
    pages = []
    states = []
    elements = []
    for suffix, kinds in (
        ("a", ["sitemap"]),
        ("b", ["sitemap", "link_graph"]),
        ("c", ["sitemap", "link_graph", "bundle"]),
    ):
        page = make_page(
            application, target, app_map,
            url=f"https://example.com/{suffix}", pattern=f"/{suffix}",
        )
        page.harvest_status = "visited"
        page.source_kinds = kinds
        state = make_state(
            application, target, app_map, page, state_id=f"s-{suffix}"
        )
        pages.append(page)
        states.append(state)
        for index in range(3):
            elements.append(
                make_element(
                    application, target, app_map, page, state,
                    name=f"Go {suffix} {index}",
                    locators=[
                        {
                            "kind": "structural",
                            "value": "x" * 230_000,
                            "stability": 5,
                        }
                    ],
                )
            )
    session = FakeDatabaseSession(
        execute_results=[
            [("fetch_ok", 3)],
            [("visited", 3)],
            [0],
            elements,
            [],
            [],
        ],
        scalars_results=[pages, states],
    )
    repository = patch_run_creation(
        monkeypatch, records=records, session=session, app_map=app_map
    )
    await create_run(records)

    assert repository.create_arguments is not None
    block = repository.create_arguments["configuration_snapshot"]["app_map"]
    assert block["elements_truncated"] is True
    by_url = {page["url"]: page for page in block["pages"]}
    # Fewest source_kinds loses its elements first (page a); the rest stay.
    assert by_url["https://example.com/a"]["elements"] == []
    assert len(by_url["https://example.com/b"]["elements"]) == 3
    assert len(by_url["https://example.com/c"]["elements"]) == 3
    import json as _json

    assert len(_json.dumps(block).encode("utf-8")) <= 2_000_000


@pytest.mark.asyncio
@pytest.mark.parametrize("harvest_status", [None, "not_started"])
async def test_snapshot_unharvested_map_block_is_byte_identical_to_1a(
    monkeypatch, harvest_status
) -> None:
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    app_map.harvest_status = harvest_status
    page_a = make_page(application, target, app_map,
                       url="https://example.com/a", pattern="/a")
    page_b = make_page(application, target, app_map,
                       url="https://example.com/b", pattern="/b")
    page_old = make_page(
        application, target, app_map, url="https://example.com/old",
        crawl_status="redirect", pattern="/old",
        redirect_target="https://example.com/new",
    )
    default_state = MapPageState(
        id=uuid4(),
        workspace_id=application.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        app_map_id=app_map.id,
        map_page_id=page_a.id,
        state_key="default",
        state_kind="default",
        state_id=None,
        element_signature=None,
        form_signature=None,
        source="census",
        confidence="low",
        last_verified_at=None,
    )
    session = FakeDatabaseSession(
        execute_results=[
            [("fetch_ok", 2), ("redirect", 1), ("blocked_auth", 1), ("gone", 1)]
        ],
        scalars_results=[[page_a, page_b, page_old], [default_state]],
    )
    repository = patch_run_creation(
        monkeypatch, records=records, session=session, app_map=app_map
    )
    await create_run(records)

    assert repository.create_arguments is not None
    block = repository.create_arguments["configuration_snapshot"]["app_map"]
    assert block == {
        "map_id": str(app_map.id),
        "version_number": 3,
        "release_state": "partial",
        "release_scope": "inventory",
        "built_at": BUILT_AT.isoformat(),
        "base_url": "https://example.com/",
        "routes": [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/new",
        ],
        "routes_truncated": False,
        "pages": [
            {
                "url": "https://example.com/a",
                "effective_url": "https://example.com/a",
                "pattern": "/a",
                "status": "fetch_ok",
                "requires_auth": False,
                "states": [
                    {
                        "state_key": "default",
                        "state_id": None,
                        "element_signature": None,
                        "form_signature": None,
                    }
                ],
            },
            {
                "url": "https://example.com/b",
                "effective_url": "https://example.com/b",
                "pattern": "/b",
                "status": "fetch_ok",
                "requires_auth": False,
                "states": [],
            },
            {
                "url": "https://example.com/old",
                "effective_url": "https://example.com/new",
                "pattern": "/old",
                "status": "redirect",
                "requires_auth": False,
                "states": [],
            },
        ],
        "counts": {
            "expected": 5,
            "reachable": 3,
            "blocked_auth": 1,
            "blocked_wall": 0,
            "gone": 1,
        },
        "freshness": _expected_freshness_block(),
    }


# -- Phase 4 (doc 23 section 8.1): the snapshot freshness block, T-N --


def _expected_freshness_block() -> dict:
    """The freshness block for this file's maps under the stubbed
    creation step: never preflighted (state unknown, no outcome), the
    step disclosed a reuse, and a verdict run's TTL is not applicable.
    Age is computed exactly as the block builder computes it."""

    age_hours = max(0, int((datetime.now(UTC) - BUILT_AT).total_seconds() // 3600))
    return {
        "state": "unknown",
        "map_built_at": BUILT_AT.isoformat(),
        "map_age_hours": age_hours,
        "last_preflight_at": None,
        "last_preflight_id": None,
        "outcome_counts": {
            "present": 0, "changed": 0, "unreachable": 0, "missing": 0, "new": 0,
        },
        "pinned_via_preflight": False,
        "preflight_status": "reused",
        "ttl_trust": "not_applicable",
    }


async def _create_run_of_kind(records, run_kind: str) -> None:
    _, application, _, target, _, _ = records
    await test_run_api.create_test_run(
        application.application_id,
        test_run_api.CreateTestRunRequest(
            target_id=target.target_id,
            study_brief="Evaluate the shopping and checkout experience.",
            run_kind=run_kind,
        ),
        make_request(),
    )


@pytest.mark.asyncio
async def test_snapshot_freshness_block_explore_test(monkeypatch) -> None:
    """T-N1: an explore_test block carries the section 8.1 freshness
    block — the step's disclosed status, TTL not applicable (a
    verdict run's policy is preflight, not TTL)."""
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    session = FakeDatabaseSession(
        execute_results=[[("fetch_ok", 1)]],
        scalars_results=[[], []],
    )
    repository = patch_run_creation(
        monkeypatch, records=records, session=session, app_map=app_map
    )
    await create_run(records)

    assert repository.create_arguments is not None
    block = repository.create_arguments["configuration_snapshot"]["app_map"]
    assert block["freshness"] == _expected_freshness_block()


@pytest.mark.asyncio
async def test_snapshot_freshness_block_slop_ttl_trust(monkeypatch) -> None:
    """T-N2: a slop block records preflight_status 'not_required' and
    TTL trust computed from the map's age against MAP_TTL_TRUST_DAYS
    (14 days) — never a preflight status."""
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    session = FakeDatabaseSession(
        execute_results=[[("fetch_ok", 1)]],
        scalars_results=[[], []],
    )
    repository = patch_run_creation(
        monkeypatch, records=records, session=session, app_map=app_map
    )
    await _create_run_of_kind(records, "slop")

    assert repository.create_arguments is not None
    block = repository.create_arguments["configuration_snapshot"]["app_map"]
    freshness = block["freshness"]
    age_hours = max(0, int((datetime.now(UTC) - BUILT_AT).total_seconds() // 3600))
    assert freshness["preflight_status"] == "not_required"
    assert freshness["ttl_trust"] == ("within" if age_hours <= 14 * 24 else "beyond")
    assert freshness["pinned_via_preflight"] is False
    assert freshness["state"] == "unknown"


@pytest.mark.asyncio
async def test_snapshot_freshness_block_persona_and_absent_map(
    monkeypatch,
) -> None:
    """T-N3: a persona block is kind-correct like slop's; an app with
    no ready map gets no app_map block at all — the snapshot is
    byte-identical to the unmapped behaviour."""
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    session = FakeDatabaseSession(
        execute_results=[[("fetch_ok", 1)]],
        scalars_results=[[], []],
    )
    repository = patch_run_creation(
        monkeypatch, records=records, session=session, app_map=app_map
    )
    await _create_run_of_kind(records, "persona")

    assert repository.create_arguments is not None
    block = repository.create_arguments["configuration_snapshot"]["app_map"]
    assert block["freshness"]["preflight_status"] == "not_required"
    assert block["freshness"]["ttl_trust"] in ("within", "beyond")

    records = make_records()
    session = FakeDatabaseSession()
    repository = patch_run_creation(
        monkeypatch, records=records, session=session, app_map=None
    )
    await create_run(records)

    assert repository.create_arguments is not None
    assert "app_map" not in repository.create_arguments["configuration_snapshot"]
