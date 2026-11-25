"""App map endpoints: build trigger, summary, and page listing (Phase 1a, T-A)."""

from collections import deque
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient
from markettwin_control_api.api import app_maps
from markettwin_database.models.knowledge import AppMap, MapPage
from markettwin_database.models.testing import Application, ApplicationTarget
from sqlalchemy.exc import IntegrityError


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
    """Query result exposing the accessors the map repository uses."""

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
    """Session fake whose query results are programmed in call order."""

    def __init__(
        self,
        *,
        get_results=None,
        scalar_results=(),
        scalars_results=(),
        execute_results=(),
    ):
        self._get_results = dict(get_results or {})
        self._scalar_results = deque(scalar_results)
        self._scalars_results = deque(scalars_results)
        self._execute_results = deque(execute_results)
        self.added: list[object] = []
        self.flush = AsyncMock()

    def begin(self):
        return Context(None)

    async def get(self, model, ident, **kwargs):
        return self._get_results.get((model, ident))

    async def scalar(self, statement):
        return self._scalar_results.popleft() if self._scalar_results else None

    async def scalars(self, statement):
        rows = self._scalars_results.popleft() if self._scalars_results else []
        return FakeResult(rows)

    async def execute(self, statement):
        rows = self._execute_results.popleft() if self._execute_results else []
        return FakeResult(rows)

    def add(self, row):
        self.added.append(row)


def patch_database(monkeypatch, *sessions):
    queue = deque(sessions)
    monkeypatch.setattr(
        app_maps,
        "get_database_runtime",
        lambda _: SimpleNamespace(session_factory=lambda: Context(queue.popleft())),
    )
    monkeypatch.setattr(
        app_maps, "require_app_map_access", AsyncMock(return_value=uuid4())
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


def make_map(
    workspace_id,
    application_id,
    target_id,
    *,
    version_number=1,
    status="ready",
    release_state="partial",
):
    now = datetime.now(UTC)
    return AppMap(
        id=uuid4(),
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=target_id,
        version_number=version_number,
        status=status,
        release_state=release_state,
        release_scope="inventory" if release_state else None,
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
        started_at=now,
        completed_at=None if status == "building" else now,
    )


def make_page(
    workspace_id,
    application_id,
    target_id,
    app_map_id,
    *,
    url,
    crawl_status="fetch_ok",
    pattern="/",
    redirect_target=None,
):
    return MapPage(
        id=uuid4(),
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=target_id,
        app_map_id=app_map_id,
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
        last_verified_at=datetime.now(UTC),
    )


def test_app_map_endpoints_require_a_session() -> None:
    app = FastAPI()
    app.include_router(app_maps.router)
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/workspaces/{uuid4()}/applications/{uuid4()}"
            f"/targets/{uuid4()}/app-map"
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_post_creates_building_map_then_next_version(monkeypatch) -> None:
    workspace_id, application_id, target_id, gets = make_scope()

    scope = FakeSession(get_results=gets)
    first = FakeSession(execute_results=[[], [None]])
    patch_database(monkeypatch, scope, first)
    response = Response()
    result = await app_maps.create_map_build(
        workspace_id, application_id, target_id, request(), response
    )
    assert response.status_code == 202
    assert result.status == "building"
    assert result.version_number == 1
    assert len(first.added) == 1
    created = first.added[0]
    assert created.id == result.map_id
    assert created.workspace_id == workspace_id
    assert created.application_id == application_id
    assert created.target_id == target_id
    assert created.status == "building"
    assert created.base_url == "https://example.com/"
    assert created.builder_version == "census-1a.1"
    assert created.census_config["census_max_urls"] == 5000
    assert created.census_config["census_user_agent"] == "MarketTwinCensus/1a"

    second_scope = FakeSession(get_results=gets)
    second = FakeSession(execute_results=[[], [1]])
    patch_database(monkeypatch, second_scope, second)
    response = Response()
    result = await app_maps.create_map_build(
        workspace_id, application_id, target_id, request(), response
    )
    assert response.status_code == 202
    assert result.version_number == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["https://example.com/agents", "https://other.example/agents"])
async def test_link_research_build_is_scoped_and_persists_the_handoff(monkeypatch, url) -> None:
    workspace_id, application_id, target_id, gets = make_scope()
    scope = FakeSession(get_results=gets)
    auth = AsyncMock(return_value=object())
    monkeypatch.setattr(app_maps, "TargetAuthorizationRepository", lambda _: SimpleNamespace(get_active=auth))
    build = FakeSession(execute_results=[[], [None]])
    patch_database(monkeypatch, scope, build)
    payload = app_maps.AppMapResearchRequest(research_url=url)
    if "other.example" in url:
        with pytest.raises(app_maps.HTTPException) as error:
            await app_maps.create_map_build(workspace_id, application_id, target_id, request(), Response(), payload)
        assert error.value.status_code == 422
        assert build.added == []
        return
    await app_maps.create_map_build(workspace_id, application_id, target_id, request(), Response(), payload)
    auth.assert_awaited_once_with(target_id=target_id)
    assert build.added[0].census_config["skill_research_url"] == url
    assert build.added[0].base_url == "https://example.com/"


@pytest.mark.asyncio
async def test_post_returns_in_flight_build_with_200(monkeypatch) -> None:
    workspace_id, application_id, target_id, gets = make_scope()
    building = make_map(
        workspace_id, application_id, target_id, status="building", release_state=None
    )
    scope = FakeSession(get_results=gets)
    session = FakeSession(execute_results=[[building]])
    patch_database(monkeypatch, scope, session)
    response = Response()
    result = await app_maps.create_map_build(
        workspace_id, application_id, target_id, request(), response
    )
    assert response.status_code == 200
    assert result.map_id == building.id
    assert result.version_number == building.version_number
    assert session.added == []


@pytest.mark.asyncio
async def test_post_single_flight_race_returns_in_flight_build(monkeypatch) -> None:
    workspace_id, application_id, target_id, gets = make_scope()
    building = make_map(
        workspace_id, application_id, target_id, status="building", release_state=None
    )
    scope = FakeSession(get_results=gets)
    racing = FakeSession(execute_results=[[], [None]])
    racing.flush = AsyncMock(
        side_effect=IntegrityError("INSERT", {}, RuntimeError("single flight"))
    )
    reread = FakeSession(execute_results=[[building]])
    patch_database(monkeypatch, scope, racing, reread)
    response = Response()
    result = await app_maps.create_map_build(
        workspace_id, application_id, target_id, request(), response
    )
    assert response.status_code == 200
    assert result.map_id == building.id


@pytest.mark.asyncio
async def test_summary_returns_latest_ready_map(monkeypatch) -> None:
    workspace_id, application_id, target_id, gets = make_scope()
    ready = make_map(workspace_id, application_id, target_id, version_number=1)
    scope = FakeSession(get_results=gets)
    ready_session = FakeSession(execute_results=[[ready]])
    counts_session = FakeSession(
        execute_results=[[("fetch_ok", 3), ("redirect", 1), ("blocked_auth", 2)]]
    )
    harvest_session = FakeSession(execute_results=[[]])
    skills_session = FakeSession(execute_results=[[]])
    patch_database(
        monkeypatch, scope, ready_session, counts_session,
        harvest_session, skills_session,
    )
    summary = await app_maps.get_app_map_summary(
        workspace_id, application_id, target_id, request()
    )
    assert summary.map_id == ready.id
    assert summary.version_number == 1
    assert summary.status == "ready"
    assert summary.release_state == "partial"
    assert summary.release_scope == "inventory"
    assert summary.base_url == "https://example.com/"
    assert summary.counts.expected == 6
    assert summary.counts.reachable == 4
    assert summary.counts.by_status == {
        "fetch_ok": 3,
        "redirect": 1,
        "blocked_auth": 2,
    }
    assert summary.spend.calls == 0
    assert summary.spend.tokens == 0
    assert summary.harvest.status == "not_started"
    assert summary.harvest.visited == 0
    assert summary.harvest.reachable == 0
    assert summary.skills == []


@pytest.mark.asyncio
async def test_summary_without_any_map_is_404(monkeypatch) -> None:
    workspace_id, application_id, target_id, gets = make_scope()
    scope = FakeSession(get_results=gets)
    ready_session = FakeSession(execute_results=[[]])
    latest_session = FakeSession(execute_results=[[]])
    patch_database(monkeypatch, scope, ready_session, latest_session)
    with pytest.raises(HTTPException) as failure:
        await app_maps.get_app_map_summary(
            workspace_id, application_id, target_id, request()
        )
    assert failure.value.status_code == 404
    assert failure.value.detail == "no app map"


async def test_progress_summary_shows_new_build_instead_of_older_ready_map(monkeypatch):
    workspace_id, application_id, target_id, gets = make_scope()
    building = make_map(workspace_id, application_id, target_id, version_number=3,
                        status="building", release_state=None)
    patch_database(monkeypatch, FakeSession(get_results=gets))
    repository = SimpleNamespace(latest_map=AsyncMock(return_value=building),
                                 latest_ready_map=AsyncMock())
    monkeypatch.setattr(app_maps, "_repository", lambda _: repository)
    render_summary = AsyncMock(return_value=SimpleNamespace(map_id=building.id, status="building"))
    monkeypatch.setattr(app_maps, "build_map_summary", render_summary)
    result = await app_maps.get_app_map_summary(workspace_id, application_id, target_id, request())
    assert result.map_id == building.id and result.status == "building"
    repository.latest_ready_map.assert_not_awaited()


@pytest.mark.asyncio
async def test_pages_pagination_and_status_filter(monkeypatch) -> None:
    workspace_id, application_id, target_id, gets = make_scope()
    ready = make_map(workspace_id, application_id, target_id)
    page_a = make_page(
        workspace_id, application_id, target_id, ready.id,
        url="https://example.com/a", pattern="/a",
    )
    page_b = make_page(
        workspace_id, application_id, target_id, ready.id,
        url="https://example.com/b", pattern="/b", crawl_status="blocked_auth",
    )

    scope = FakeSession(get_results=gets)
    ready_session = FakeSession(execute_results=[[ready]])
    session = FakeSession(execute_results=[[3], [page_a, page_b]])
    patch_database(monkeypatch, scope, ready_session, session)
    result = await app_maps.list_app_map_pages(
        workspace_id, application_id, target_id, request(),
        status=None, pattern=None, limit=2, offset=0,
    )
    assert result.map_id == ready.id
    assert result.total == 3
    assert len(result.items) == 2
    assert result.items[0].canonical_url == "https://example.com/a"
    assert result.items[0].crawl_status == "fetch_ok"
    assert result.items[0].source_kinds == ["sitemap"]
    assert result.items[1].crawl_status == "blocked_auth"

    filtered_scope = FakeSession(get_results=gets)
    filtered_ready = FakeSession(execute_results=[[ready]])
    filtered = FakeSession(execute_results=[[1], [page_a]])
    patch_database(monkeypatch, filtered_scope, filtered_ready, filtered)
    result = await app_maps.list_app_map_pages(
        workspace_id, application_id, target_id, request(),
        status="fetch_ok", pattern=None, limit=100, offset=0,
    )
    assert result.total == 1
    assert [item.crawl_status for item in result.items] == ["fetch_ok"]


@pytest.mark.asyncio
async def test_foreign_workspace_scope_is_404_on_all_endpoints(monkeypatch) -> None:
    workspace_id, application_id, target_id, gets = make_scope()
    foreign = Application(
        id=application_id,
        workspace_id=uuid4(),
        created_by_user_id=uuid4(),
        name="Someone else's app",
        status="active",
    )
    gets[(Application, application_id)] = foreign

    post_session = FakeSession(get_results=gets)
    patch_database(monkeypatch, post_session)
    with pytest.raises(HTTPException) as failure:
        await app_maps.create_map_build(
            workspace_id, application_id, target_id, request(), Response()
        )
    assert failure.value.status_code == 404
    assert failure.value.detail == "Application not found."

    summary_session = FakeSession(get_results=gets)
    patch_database(monkeypatch, summary_session)
    with pytest.raises(HTTPException) as failure:
        await app_maps.get_app_map_summary(
            workspace_id, application_id, target_id, request()
        )
    assert failure.value.status_code == 404

    pages_session = FakeSession(get_results=gets)
    patch_database(monkeypatch, pages_session)
    with pytest.raises(HTTPException) as failure:
        await app_maps.list_app_map_pages(
            workspace_id, application_id, target_id, request(),
            status=None, pattern=None, limit=100, offset=0,
        )
    assert failure.value.status_code == 404


@pytest.mark.asyncio
async def test_target_from_another_application_is_404(monkeypatch) -> None:
    workspace_id, application_id, target_id, gets = make_scope()
    foreign_target = ApplicationTarget(
        id=target_id,
        application_id=uuid4(),
        name="Other app's target",
        environment="production",
        base_url="https://example.com/",
        status="active",
    )
    gets[(ApplicationTarget, target_id)] = foreign_target
    session = FakeSession(get_results=gets)
    patch_database(monkeypatch, session)
    with pytest.raises(HTTPException) as failure:
        await app_maps.get_app_map_summary(
            workspace_id, application_id, target_id, request()
        )
    assert failure.value.status_code == 404
    assert failure.value.detail == "Target not found."
