"""Census-lite (Phase 1a, doc 14): engine, disposition table, inventory
gate, processor lifecycle. Every test runs against an in-memory fake site
through the injectable fetch seam; no test touches the network. The single
database test is opt-in, following the repo's MARKETTWIN_TEST_DATABASE
convention."""

import ast
import hashlib
import os
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from markettwin_control_api.knowledge.census import (
    CensusCandidate,
    CensusFetchError,
    FetchHop,
    FetchResult,
    build_census,
    default_census_config,
    induce_patterns,
    public_url,
    same_site_link,
    validate_link_target,
)
from markettwin_control_api.knowledge.census_processor import CensusProcessor
from markettwin_control_api.knowledge.map_repository import (
    DispositionUpdate,
    GateResult,
    InsertedPage,
    MapRepository,
    NewPage,
    compute_inventory_gate,
)

ORIGIN = "https://t.example"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

def make_map(base_url: str = f"{ORIGIN}/", **overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "application_id": uuid4(),
        "target_id": uuid4(),
        "base_url": base_url,
        "status": "building",
        "version_number": 1,
        "census_config": {},
        "census_metrics": {},
        "pattern_stats": {},
        "gate_metrics": {},
        "release_state": None,
        "release_scope": None,
        "failure_code": None,
        "failure_message": None,
        "failure_site": None,
        "mapping_spend_calls": None,
        "mapping_spend_tokens": None,
        "mapping_spend_seconds": None,
        "census_expected_count": None,
        "census_reachable_count": None,
        "started_at": datetime.now(UTC),
        "completed_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeRepository:
    """In-memory stand-in for MapRepository's engine/processor surface."""

    def __init__(self) -> None:
        self.maps: dict[UUID, SimpleNamespace] = {}
        self.pages: dict[UUID, SimpleNamespace] = {}
        self.progress: list[dict[str, Any]] = []

    async def insert_pages(
        self, app_map: SimpleNamespace, pages: list[NewPage]
    ) -> list[InsertedPage]:
        inserted = []
        for new_page in pages:
            page_id = uuid4()
            self.pages[page_id] = SimpleNamespace(
                id=page_id,
                app_map_id=app_map.id,
                canonical_url=new_page.canonical_url,
                route_pattern=new_page.route_pattern,
                source_kinds=list(new_page.source_kinds),
                crawl_status="census_incomplete",
                http_status=None,
                redirect_target=None,
                content_type=None,
                title=None,
                html_sha256=None,
                requires_auth=False,
                confidence="low",
                last_verified_at=None,
            )
            inserted.append(InsertedPage(id=page_id, canonical_url=new_page.canonical_url))
        return inserted

    async def update_disposition(self, update: DispositionUpdate) -> None:
        page = self.pages[update.page_id]
        page.crawl_status = update.crawl_status
        page.http_status = update.http_status
        page.redirect_target = update.redirect_target
        page.content_type = update.content_type
        page.title = update.title
        page.html_sha256 = update.html_sha256
        page.requires_auth = update.requires_auth
        page.confidence = update.confidence
        page.last_verified_at = update.last_verified_at

    async def save_progress(
        self,
        map_id: UUID,
        *,
        census_metrics: dict[str, Any],
        pattern_stats: dict[str, Any],
    ) -> None:
        self.progress.append(census_metrics)
        app_map = self.maps[map_id]
        app_map.census_metrics = census_metrics
        app_map.pattern_stats = pattern_stats

    async def get_map(self, map_id: UUID) -> SimpleNamespace | None:
        return self.maps.get(map_id)

    async def count_pages_by_status(self, map_id: UUID) -> dict[str, int]:
        counts: dict[str, int] = {}
        for page in self.pages.values():
            if page.app_map_id == map_id:
                counts[page.crawl_status] = counts.get(page.crawl_status, 0) + 1
        return counts

    async def apply_gate(
        self,
        map_id: UUID,
        *,
        gate: GateResult,
        spend_seconds: float,
        census_metrics: dict[str, Any],
        pattern_stats: dict[str, Any],
    ) -> None:
        app_map = self.maps[map_id]
        app_map.status = gate.status
        app_map.release_state = gate.release_state
        app_map.release_scope = gate.release_scope
        app_map.census_expected_count = gate.expected
        app_map.census_reachable_count = gate.reachable
        app_map.gate_metrics = gate.metrics()
        app_map.failure_code = gate.failure_code
        app_map.failure_message = gate.failure_message
        app_map.mapping_spend_calls = 0
        app_map.mapping_spend_tokens = 0
        app_map.mapping_spend_seconds = spend_seconds
        app_map.census_metrics = census_metrics
        app_map.pattern_stats = pattern_stats
        app_map.completed_at = datetime.now(UTC)

    async def fail_map(
        self,
        map_id: UUID,
        *,
        failure_code: str,
        failure_message: str,
        failure_site: str,
        spend_seconds: float,
        census_metrics: dict[str, Any] | None = None,
        pattern_stats: dict[str, Any] | None = None,
    ) -> None:
        app_map = self.maps[map_id]
        app_map.status = "failed"
        app_map.failure_code = failure_code
        app_map.failure_message = failure_message
        app_map.failure_site = failure_site
        app_map.mapping_spend_seconds = spend_seconds
        app_map.completed_at = datetime.now(UTC)

    async def list_stale_building(self, cutoff: datetime) -> list[SimpleNamespace]:
        return [
            app_map
            for app_map in self.maps.values()
            if app_map.status == "building" and app_map.started_at < cutoff
        ]

    def pages_for(self, map_id: UUID) -> list[SimpleNamespace]:
        return [page for page in self.pages.values() if page.app_map_id == map_id]

    def page_by_url(self, map_id: UUID, url: str) -> SimpleNamespace | None:
        for page in self.pages_for(map_id):
            if page.canonical_url == url:
                return page
        return None


def http_result(
    url: str,
    *,
    status: int = 200,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
    chain: tuple[FetchHop, ...] = (),
    final: str | None = None,
    error: str | None = None,
    blocked_hop: bool = False,
) -> FetchResult:
    return FetchResult(
        requested_url=url,
        final_url=final if final is not None else url,
        status=status,
        headers={key.lower(): value for key, value in (headers or {}).items()},
        body=body,
        redirect_chain=chain,
        error=error,
        blocked_hop=blocked_hop,
    )


def html_result(url: str, html: str, **kwargs: Any) -> FetchResult:
    headers = {"content-type": "text/html; charset=utf-8"}
    return http_result(url, body=html.encode(), headers=headers, **kwargs)


class FakeSite:
    """URL -> FetchResult / exception / callable. Unknown URLs are 404,
    which also makes robots.txt and sitemap.xml absent by default."""

    def __init__(self) -> None:
        self.routes: dict[str, Any] = {}
        self.calls: list[str] = []

    def add(self, url: str, result: Any) -> "FakeSite":
        self.routes[url] = result
        return self

    async def __call__(self, url: str) -> FetchResult:
        self.calls.append(url)
        entry = self.routes.get(url)
        if entry is None:
            return http_result(url, status=404)
        if isinstance(entry, BaseException):
            raise entry
        if callable(entry):
            return entry(url)
        return entry


def sitemap_xml(*urls: str) -> bytes:
    locs = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>'.encode()


def sitemap_index_xml(*urls: str) -> bytes:
    locs = "".join(f"<sitemap><loc>{url}</loc></sitemap>" for url in urls)
    return f'<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</sitemapindex>'.encode()


async def run_build(
    site: FakeSite, base_url: str = f"{ORIGIN}/"
) -> tuple[FakeRepository, SimpleNamespace, Any]:
    repository = FakeRepository()
    app_map = make_map(base_url)
    repository.maps[app_map.id] = app_map
    report = await build_census(repository, app_map, fetch=site, retry_delay=0.0)
    return repository, app_map, report


# ---------------------------------------------------------------------------
# T-C1 / T-C2: sitemap + robots source collection
# ---------------------------------------------------------------------------

async def test_research_link_adds_a_same_origin_seed() -> None:
    site = FakeSite()
    seed = f"{ORIGIN}/agents"
    site.add(f"{ORIGIN}/", html_result(f"{ORIGIN}/", "<html><title>Home</title></html>"))
    site.add(seed, html_result(seed, "<html><title>Agents</title></html>"))
    app_map = make_map()
    app_map.census_config["skill_research_url"] = seed
    repository = FakeRepository()
    repository.maps[app_map.id] = app_map
    await build_census(repository, app_map, fetch=site, retry_delay=0.0)
    assert seed in {page.canonical_url for page in repository.pages.values()}


async def test_processor_hands_ready_link_research_to_harvest(monkeypatch) -> None:
    from markettwin_control_api.config import Settings
    from markettwin_control_api.knowledge import census_processor
    from sqlalchemy.ext.asyncio import AsyncEngine

    map_id = uuid4()
    repository = MagicMock()
    repository.pending_link_research = AsyncMock(return_value=[map_id])
    repository.start_harvest = AsyncMock(return_value=(None, True))
    repository.list_building = AsyncMock(return_value=[])
    repository.list_stale_building = AsyncMock(return_value=[])
    monkeypatch.setattr(census_processor, "MapRepository", lambda _: repository)
    processor = CensusProcessor(MagicMock(spec=AsyncEngine), Settings())
    assert await processor.process_next()
    repository.start_harvest.assert_awaited_once_with(map_id, only_unstarted=True)

async def test_t_c1_sitemap_index_recursion_and_depth_cap() -> None:
    site = FakeSite()
    site.add(f"{ORIGIN}/robots.txt", http_result(
        f"{ORIGIN}/robots.txt", status=200,
        body=b"User-agent: *\nSitemap: https://t.example/maps/root.xml\n",
    ))
    site.add(f"{ORIGIN}/maps/root.xml", http_result(
        f"{ORIGIN}/maps/root.xml", status=200,
        body=sitemap_index_xml(f"{ORIGIN}/maps/a.xml", f"{ORIGIN}/maps/mid.xml"),
    ))
    site.add(f"{ORIGIN}/maps/a.xml", http_result(
        f"{ORIGIN}/maps/a.xml", status=200,
        body=sitemap_xml(f"{ORIGIN}/one", f"{ORIGIN}/two"),
    ))
    site.add(f"{ORIGIN}/maps/mid.xml", http_result(
        f"{ORIGIN}/maps/mid.xml", status=200,
        body=sitemap_index_xml(f"{ORIGIN}/maps/leaf.xml", f"{ORIGIN}/maps/deep.xml"),
    ))
    site.add(f"{ORIGIN}/maps/leaf.xml", http_result(
        f"{ORIGIN}/maps/leaf.xml", status=200, body=sitemap_xml(f"{ORIGIN}/three"),
    ))
    site.add(f"{ORIGIN}/maps/deep.xml", http_result(
        f"{ORIGIN}/maps/deep.xml", status=200,
        body=sitemap_index_xml(f"{ORIGIN}/maps/never.xml"),
    ))
    site.add(f"{ORIGIN}/maps/never.xml", http_result(
        f"{ORIGIN}/maps/never.xml", status=200, body=sitemap_xml(f"{ORIGIN}/never"),
    ))
    repository, app_map, _report = await run_build(site)
    urls = {page.canonical_url for page in repository.pages_for(app_map.id)}
    assert {f"{ORIGIN}/one", f"{ORIGIN}/two", f"{ORIGIN}/three"} <= urls
    assert f"{ORIGIN}/never" not in urls  # a 3-deep index is never followed
    assert f"{ORIGIN}/maps/never.xml" not in site.calls


async def test_t_c2_robots_sitemap_kinds_and_absent_robots() -> None:
    # (a) robots Sitemap: lines -> source kind robots_sitemap.
    site = FakeSite()
    site.add(f"{ORIGIN}/robots.txt", http_result(
        f"{ORIGIN}/robots.txt", status=200,
        body=b"Sitemap: https://t.example/map.xml\n",
    ))
    site.add(f"{ORIGIN}/map.xml", http_result(
        f"{ORIGIN}/map.xml", status=200, body=sitemap_xml(f"{ORIGIN}/from-robots"),
    ))
    repository, app_map, report = await run_build(site)
    page = repository.page_by_url(app_map.id, f"{ORIGIN}/from-robots")
    assert page is not None and page.source_kinds == ["robots_sitemap"]
    assert report.census_metrics["robots_status"] == "ok"

    # (b) no robots sitemaps -> /sitemap.xml tried with kind sitemap.
    site = FakeSite()
    site.add(f"{ORIGIN}/robots.txt", http_result(
        f"{ORIGIN}/robots.txt", status=200, body=b"User-agent: *\nAllow: /\n",
    ))
    site.add(f"{ORIGIN}/sitemap.xml", http_result(
        f"{ORIGIN}/sitemap.xml", status=200, body=sitemap_xml(f"{ORIGIN}/from-file"),
    ))
    repository, app_map, _report = await run_build(site)
    assert f"{ORIGIN}/sitemap.xml" in site.calls
    page = repository.page_by_url(app_map.id, f"{ORIGIN}/from-file")
    assert page is not None and page.source_kinds == ["sitemap"]

    # (c) robots 404 -> robots_status absent, build proceeds allow-all.
    site = FakeSite()
    site.add(f"{ORIGIN}/sitemap.xml", http_result(
        f"{ORIGIN}/sitemap.xml", status=200, body=sitemap_xml(f"{ORIGIN}/listed"),
    ))
    _repository, _app_map, report = await run_build(site)
    assert report.census_metrics["robots_status"] == "absent"


# ---------------------------------------------------------------------------
# T-C3 / T-C4 / T-C5: bundle + embedded extraction
# ---------------------------------------------------------------------------

async def test_t_c3_bundle_route_literals_assets_excluded() -> None:
    site = FakeSite()
    site.add(f"{ORIGIN}/", html_result(
        f"{ORIGIN}/", '<html><head><script src="/static/app.js"></script></head></html>',
    ))
    site.add(f"{ORIGIN}/static/app.js", http_result(
        f"{ORIGIN}/static/app.js", status=200,
        body=(
            b'const a = "/products/42"; const b = \'/about\';'
            b'const c = "/img/logo.png"; const d = "/has space";'
            b'const e = "/a//b"; const f = "/app.js"; const g = "/styles.css";'
        ),
    ))
    repository, app_map, _report = await run_build(site)
    urls = {page.canonical_url for page in repository.pages_for(app_map.id)}
    assert f"{ORIGIN}/products/42" in urls
    assert f"{ORIGIN}/about" in urls
    assert not any("logo.png" in url or "styles.css" in url for url in urls)
    assert f"{ORIGIN}/a//b" not in urls and f"{ORIGIN}/a/b" not in urls


async def test_t_c4_source_map_counts_toward_bundle_cap() -> None:
    scripts = "".join(
        f'<script src="/s{index}.js"></script>' for index in range(1, 11)
    )
    site = FakeSite()
    site.add(f"{ORIGIN}/", html_result(f"{ORIGIN}/", f"<html><head>{scripts}</head></html>"))
    site.add(f"{ORIGIN}/s1.js", http_result(
        f"{ORIGIN}/s1.js", status=200,
        body=b'const x = "/one";\n//# sourceMappingURL=s1.js.map',
    ))
    site.add(f"{ORIGIN}/s1.js.map", http_result(
        f"{ORIGIN}/s1.js.map", status=200,
        body=b'{"version": 3, "sourcesContent": ["const r = \\"/from-map/route\\";"]}',
    ))
    for index in range(2, 11):
        site.add(f"{ORIGIN}/s{index}.js", http_result(
            f"{ORIGIN}/s{index}.js", status=200, body=b"const y = 1;",
        ))
    repository, app_map, _report = await run_build(site)
    urls = {page.canonical_url for page in repository.pages_for(app_map.id)}
    assert f"{ORIGIN}/from-map/route" in urls  # sourcesContent literals extracted
    bundle_calls = [
        call for call in site.calls if call.endswith(".js") or call.endswith(".js.map")
    ]
    assert len(bundle_calls) == 10  # scripts + source maps share the cap
    assert f"{ORIGIN}/s10.js" not in site.calls


async def test_t_c5_embedded_json_block_routes_extracted() -> None:
    site = FakeSite()
    site.add(f"{ORIGIN}/", html_result(
        f"{ORIGIN}/",
        '<html><head><script type="application/json">'
        '{"next": "/embedded/route", "count": 3}'
        "</script></head></html>",
    ))
    repository, app_map, _report = await run_build(site)
    assert repository.page_by_url(app_map.id, f"{ORIGIN}/embedded/route") is not None


# ---------------------------------------------------------------------------
# T-C6: link graph BFS
# ---------------------------------------------------------------------------

async def test_t_c6_link_graph_depth_and_discovery_cap() -> None:
    site = FakeSite()
    site.add(f"{ORIGIN}/", html_result(f"{ORIGIN}/", '<a href="/a">a</a>'))
    site.add(f"{ORIGIN}/a", html_result(f"{ORIGIN}/a", '<a href="/b">b</a>'))
    site.add(f"{ORIGIN}/b", html_result(f"{ORIGIN}/b", '<a href="/c">c</a>'))
    site.add(f"{ORIGIN}/c", html_result(f"{ORIGIN}/c", '<a href="/d">d</a>'))
    site.add(f"{ORIGIN}/d", html_result(f"{ORIGIN}/d", "<p>leaf</p>"))
    repository, app_map, _report = await run_build(site)
    urls = {page.canonical_url for page in repository.pages_for(app_map.id)}
    assert urls == {f"{ORIGIN}/", f"{ORIGIN}/a", f"{ORIGIN}/b", f"{ORIGIN}/c"}
    assert f"{ORIGIN}/d" not in site.calls  # depth 3 is fetched, never expanded

    links = '<a href="https://other.example/x">x</a><a href="#frag">f</a>'
    links += "".join(f'<a href="/p/{index}">p</a>' for index in range(1, 1501))
    site = FakeSite()
    site.add(f"{ORIGIN}/", html_result(f"{ORIGIN}/", links))
    repository, app_map, report = await run_build(site)
    # 1 seed + 999 discovered = the 1000 discovery cap, the legacy research cap.
    assert report.census_metrics["discovered"] == 1000
    assert report.pattern_stats["/p/{id}"] == {"instances": 999, "exemplars": 5}
    assert not any(
        "other.example" in page.canonical_url
        for page in repository.pages_for(app_map.id)
    )


# ---------------------------------------------------------------------------
# T-C7 / T-C8: induction
# ---------------------------------------------------------------------------

def test_t_c7_induction_patterns_and_stats() -> None:
    def candidate(url: str, order: int) -> CensusCandidate:
        return CensusCandidate(
            canonical_url=url, source_kinds={"sitemap"}, depth=0, order=order
        )

    rows, stats, overflow = induce_patterns([
        candidate(f"{ORIGIN}/products/42", 0),
        candidate(f"{ORIGIN}/products/7", 1),
        candidate(f"{ORIGIN}/blog/my-post-123", 2),
        candidate(f"{ORIGIN}/2024/11/report", 3),
        candidate(f"{ORIGIN}/users/123e4567-e89b-12d3-a456-426614174000/settings", 4),
        candidate(f"{ORIGIN}/about", 5),
    ])
    assert overflow == 0
    assert {row.route_pattern for row in rows} == {
        "/products/{id}", "/blog/{slug}", "/{date}/11/report",
        "/users/{uuid}/settings", "/about",
    }
    assert stats["/products/{id}"] == {"instances": 2, "exemplars": 2}
    assert stats["/about"] == {"instances": 1, "exemplars": 1}


async def test_t_c8_exemplar_cap_rows_and_stats() -> None:
    site = FakeSite()
    site.add(f"{ORIGIN}/sitemap.xml", http_result(
        f"{ORIGIN}/sitemap.xml", status=200,
        body=sitemap_xml(*[f"{ORIGIN}/item/{index}" for index in range(1, 9)]),
    ))
    repository, app_map, report = await run_build(site)
    item_pages = [
        page for page in repository.pages_for(app_map.id)
        if page.route_pattern == "/item/{id}"
    ]
    assert len(item_pages) == 5
    assert report.pattern_stats["/item/{id}"] == {"instances": 8, "exemplars": 5}


# ---------------------------------------------------------------------------
# T-C9 / T-C10: the disposition decision table
# ---------------------------------------------------------------------------

async def single_page(
    result: Any, base_url: str = f"{ORIGIN}/page"
) -> SimpleNamespace:
    site = FakeSite()
    site.add(base_url, result)
    repository, app_map, _report = await run_build(site, base_url)
    page = repository.page_by_url(app_map.id, base_url)
    assert page is not None
    return page


async def test_t_c9_disposition_decision_table() -> None:
    # Plain 200 -> fetch_ok, high confidence, title + hash recorded.
    body = b"<html><head><title>Hello</title></head><body>ok</body></html>"
    page = await single_page(html_result(f"{ORIGIN}/page", body.decode()))
    assert page.crawl_status == "fetch_ok"
    assert page.confidence == "high"
    assert page.http_status == 200
    assert page.title == "Hello"
    assert page.html_sha256 == hashlib.sha256(body).hexdigest()
    assert page.last_verified_at is not None

    # 401 -> blocked_auth.
    page = await single_page(http_result(f"{ORIGIN}/page", status=401))
    assert page.crawl_status == "blocked_auth"
    assert page.requires_auth is True
    assert page.confidence == "medium"

    # 403 with a bot-wall server signal -> blocked_wall.
    page = await single_page(http_result(
        f"{ORIGIN}/page", status=403, headers={"server": "cloudflare"},
    ))
    assert page.crawl_status == "blocked_wall"

    # 429 with an x-datadome header -> blocked_wall.
    page = await single_page(http_result(
        f"{ORIGIN}/page", status=429, headers={"x-datadome": "1"},
    ))
    assert page.crawl_status == "blocked_wall"

    # Plain 403 without signals -> fetch_error (rule 12).
    page = await single_page(http_result(f"{ORIGIN}/page", status=403))
    assert page.crawl_status == "fetch_error"

    # 404 / 410 -> gone.
    for status in (404, 410):
        page = await single_page(http_result(f"{ORIGIN}/page", status=status))
        assert page.crawl_status == "gone"

    # Redirect to a login path -> blocked_auth with the effective target kept.
    page = await single_page(html_result(
        f"{ORIGIN}/page", "<html></html>",
        chain=(FetchHop(url=f"{ORIGIN}/page", status=301),),
        final=f"{ORIGIN}/login",
    ))
    assert page.crawl_status == "blocked_auth"
    assert page.requires_auth is True
    assert page.redirect_target == f"{ORIGIN}/login"

    # Redirect to another same-origin path -> redirect.
    page = await single_page(html_result(
        f"{ORIGIN}/page", "<html></html>",
        chain=(FetchHop(url=f"{ORIGIN}/page", status=301),),
        final=f"{ORIGIN}/new-path",
    ))
    assert page.crawl_status == "redirect"
    assert page.redirect_target == f"{ORIGIN}/new-path"
    assert page.confidence == "medium"

    # A redirect hop that failed target validation -> fetch_error, and the
    # row keeps the last good hop's status.
    page = await single_page(http_result(
        f"{ORIGIN}/page", status=302, blocked_hop=True,
        chain=(FetchHop(url=f"{ORIGIN}/page", status=302),),
        final=f"{ORIGIN}/page",
    ))
    assert page.crawl_status == "fetch_error"
    assert page.http_status == 302


async def test_t_c9_retry_then_error_dispositions() -> None:
    # 500 on both attempts -> fetch_error; the seam saw exactly 2 calls.
    site = FakeSite()
    site.add(f"{ORIGIN}/page", http_result(f"{ORIGIN}/page", status=500))
    repository, app_map, _report = await run_build(site, f"{ORIGIN}/page")
    page = repository.page_by_url(app_map.id, f"{ORIGIN}/page")
    assert page is not None and page.crawl_status == "fetch_error"
    assert site.calls.count(f"{ORIGIN}/page") == 2

    # Network failure on both attempts -> fetch_error with no status.
    site = FakeSite()
    site.add(f"{ORIGIN}/page", CensusFetchError("ConnectTimeout"))
    repository, app_map, _report = await run_build(site, f"{ORIGIN}/page")
    page = repository.page_by_url(app_map.id, f"{ORIGIN}/page")
    assert page is not None and page.crawl_status == "fetch_error"
    assert page.http_status is None
    assert page.last_verified_at is not None
    assert site.calls.count(f"{ORIGIN}/page") == 2


async def test_t_c9_robots_disallowed_and_cross_origin() -> None:
    site = FakeSite()
    site.add(f"{ORIGIN}/robots.txt", http_result(
        f"{ORIGIN}/robots.txt", status=200,
        body=(
            b"User-agent: *\nDisallow: /private\n"
            b"Sitemap: https://t.example/sitemap.xml\n"
        ),
    ))
    site.add(f"{ORIGIN}/sitemap.xml", http_result(
        f"{ORIGIN}/sitemap.xml", status=200,
        body=sitemap_xml(
            f"{ORIGIN}/private/secret", "https://other.example/foreign",
        ),
    ))
    repository, app_map, _report = await run_build(site)
    page = repository.page_by_url(app_map.id, f"{ORIGIN}/private/secret")
    assert page is not None
    assert page.crawl_status == "out_of_scope"
    assert page.http_status is None
    assert page.last_verified_at is None
    assert f"{ORIGIN}/private/secret" not in site.calls  # never fetched
    # Cross-origin sitemap entries are filtered at collection (rule 1).
    assert repository.page_by_url(app_map.id, "https://other.example/foreign") is None


async def test_t_c10_checkpoint_page_is_blocked_wall() -> None:
    page = await single_page(html_result(
        f"{ORIGIN}/page",
        "<html><head><title>Just a moment...</title></head>"
        "<body>Just a moment, checking your browser</body></html>",
    ))
    assert page.crawl_status == "blocked_wall"
    assert page.confidence == "medium"


# ---------------------------------------------------------------------------
# T-C11: incremental publish
# ---------------------------------------------------------------------------

async def test_t_c11_abort_leaves_truthful_partial_map() -> None:
    site = FakeSite()
    site.add(f"{ORIGIN}/sitemap.xml", http_result(
        f"{ORIGIN}/sitemap.xml", status=200,
        body=sitemap_xml(
            f"{ORIGIN}/alpha", f"{ORIGIN}/beta", f"{ORIGIN}/gamma", f"{ORIGIN}/delta",
        ),
    ))
    site.add(f"{ORIGIN}/beta", RuntimeError("job-level abort"))
    repository = FakeRepository()
    app_map = make_map()
    repository.maps[app_map.id] = app_map
    with pytest.raises(RuntimeError, match="job-level abort"):
        await build_census(repository, app_map, fetch=site, retry_delay=0.0)
    pages = repository.pages_for(app_map.id)
    dispositioned = [page for page in pages if page.crawl_status != "census_incomplete"]
    remaining = [page for page in pages if page.crawl_status == "census_incomplete"]
    assert len(pages) == 5
    assert len(dispositioned) == 2  # base + alpha, in queue order
    assert len(remaining) == 3
    assert repository.progress[-1]["fetched"] == 2


# ---------------------------------------------------------------------------
# T-C12 / T-C14: the inventory gate
# ---------------------------------------------------------------------------

def test_t_c12_gate_math() -> None:
    result = compute_inventory_gate({}, 0)
    assert result.status == "failed" and result.failure_code == "empty_census"
    assert result.release_state == "failed"

    result = compute_inventory_gate({"gone": 5}, 0)
    assert result.failure_code == "nothing_reachable"

    result = compute_inventory_gate({"fetch_ok": 49, "census_incomplete": 1}, 0)
    assert result.status == "ready"
    assert result.release_state == "partial"
    assert result.release_scope == "inventory"
    assert result.coverage == pytest.approx(0.98)

    result = compute_inventory_gate({"fetch_ok": 979, "census_incomplete": 21}, 0)
    assert result.status == "failed" and result.failure_code == "census_incomplete"

    # Overflow joins the incomplete count and flips a borderline case.
    result = compute_inventory_gate({"fetch_ok": 50}, 2)
    assert result.status == "failed" and result.failure_code == "census_incomplete"
    assert result.incomplete == 2
    assert result.metrics()["rule"] == "inventory-1a.1"


def test_t_c14_gate_never_releases_trusted() -> None:
    statuses = [
        "fetch_ok", "redirect", "blocked_auth", "blocked_wall",
        "gone", "fetch_error", "out_of_scope", "census_incomplete",
    ]
    cases: list[tuple[dict[str, int], int]] = [
        ({}, 0),
        ({"fetch_ok": 100}, 0),
        ({"fetch_ok": 1}, 0),
        ({"fetch_ok": 49, "census_incomplete": 1}, 0),
        ({"gone": 10, "fetch_error": 10}, 0),
    ]
    rng = random.Random(20261113)
    for _ in range(200):
        counts = {
            status: rng.randrange(0, 60)
            for status in statuses
            if rng.random() < 0.8
        }
        cases.append((counts, rng.randrange(0, 50)))
    for counts, overflow in cases:
        result = compute_inventory_gate(counts, overflow)
        assert result.release_state in ("partial", "failed")
        assert result.release_state != "trusted"


# ---------------------------------------------------------------------------
# T-C13: zero model calls in the map pipeline
# ---------------------------------------------------------------------------

def test_t_c13_no_model_imports_in_map_pipeline() -> None:
    service_root = Path(__file__).resolve().parents[1]
    files = [
        service_root / "src/markettwin_control_api/knowledge/census.py",
        service_root / "src/markettwin_control_api/knowledge/census_processor.py",
        service_root / "src/markettwin_control_api/knowledge/map_repository.py",
        service_root / "src/markettwin_control_api/api/app_maps.py",
    ]
    banned_roots = {
        "litellm", "openai", "anthropic", "google", "markettwin_execution_orchestrator",
    }
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in banned_roots, path
                    assert alias.name.split(".")[-1] != "ask", path
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in banned_roots, path
                for alias in node.names:
                    assert alias.name != "ask", path


# ---------------------------------------------------------------------------
# T-C15: single-flight (opt-in database test)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_DATABASE") != "1",
    reason="Opt-in local PostgreSQL check.",
)
async def test_t_c15_single_flight_create_and_partial_index() -> None:
    from markettwin_control_api.config import get_settings
    from markettwin_database.models import User, Workspace
    from markettwin_database.models.knowledge import AppMap
    from markettwin_database.models.testing import Application, ApplicationTarget
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(get_settings().database_url, connect_args={"timeout": 5})
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            try:
                factory = async_sessionmaker(
                    connection, expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                )
                user_id, workspace_id = uuid4(), uuid4()
                application_id, target_id = uuid4(), uuid4()
                async with factory() as session:
                    email = f"census-test-{user_id}@example.invalid"
                    session.add(User(id=user_id, email=email, normalized_email=email))
                    await session.flush()
                    session.add(Workspace(
                        id=workspace_id, name="Census test", created_by_user_id=user_id,
                    ))
                    await session.flush()
                    session.add(Application(
                        id=application_id, workspace_id=workspace_id,
                        name="Census application", created_by_user_id=user_id,
                    ))
                    await session.flush()
                    session.add(ApplicationTarget(
                        id=target_id, application_id=application_id, name="Production",
                        environment="production", base_url="https://t.example/",
                    ))
                    await session.flush()
                    # Release the setup savepoint: under create_savepoint
                    # joins, closing without a commit rolls the parents back.
                    await session.commit()
                repository = MapRepository(factory)
                first, created = await repository.create_build(
                    workspace_id=workspace_id, application_id=application_id,
                    target_id=target_id, base_url="https://t.example/",
                    census_config=default_census_config(),
                )
                assert created and first.version_number == 1
                second, created = await repository.create_build(
                    workspace_id=workspace_id, application_id=application_id,
                    target_id=target_id, base_url="https://t.example/",
                    census_config=default_census_config(),
                )
                assert not created and second.id == first.id
                async with factory() as session:
                    with pytest.raises(IntegrityError):
                        async with session.begin_nested():
                            session.add(AppMap(
                                id=uuid4(), workspace_id=workspace_id,
                                application_id=application_id, target_id=target_id,
                                version_number=99, status="building",
                                base_url="https://t.example/",
                                builder_version="census-1a.1",
                                census_config={}, census_metrics={},
                                pattern_stats={}, gate_metrics={},
                                started_at=datetime.now(UTC),
                            ))
                            await session.flush()
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# T-C16 / T-C17: processor behaviour over fakes
# ---------------------------------------------------------------------------

async def test_t_c16_full_fake_build_spends_no_model_calls() -> None:
    from markettwin_control_api.config import Settings
    from sqlalchemy.ext.asyncio import AsyncEngine

    site = FakeSite()
    site.add(f"{ORIGIN}/", html_result(f"{ORIGIN}/", "<html><title>Home</title></html>"))
    repository = FakeRepository()
    app_map = make_map()
    repository.maps[app_map.id] = app_map
    processor = CensusProcessor(MagicMock(spec=AsyncEngine), Settings())
    await processor.run_build(
        repository, app_map, fetch=site,  # type: ignore[arg-type]
    )
    assert app_map.status == "ready"
    assert app_map.release_state == "partial"
    assert app_map.release_scope == "inventory"
    assert app_map.mapping_spend_calls == 0
    assert app_map.mapping_spend_tokens == 0
    assert app_map.mapping_spend_seconds is not None
    assert app_map.mapping_spend_seconds > 0


async def test_t_c17_orphan_reaping() -> None:
    from markettwin_control_api.config import Settings
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

    engine = MagicMock(spec=AsyncEngine)
    connection = AsyncMock(spec=AsyncConnection)
    engine.connect.return_value.__aenter__.return_value = connection
    processor = CensusProcessor(engine, Settings())
    repository = FakeRepository()
    stale = make_map(started_at=datetime.now(UTC) - timedelta(minutes=31))
    fresh = make_map()
    repository.maps[stale.id] = stale
    repository.maps[fresh.id] = fresh

    connection.scalar.return_value = True
    processor._repository_on = MagicMock(return_value=repository)  # type: ignore[method-assign]
    fail_map = repository.fail_map

    async def fail_while_claimed(*args: Any, **kwargs: Any) -> None:
        connection.execute.assert_not_awaited()
        await fail_map(*args, **kwargs)

    repository.fail_map = AsyncMock(side_effect=fail_while_claimed)  # type: ignore[method-assign]
    assert await processor.reap_orphans(repository) == 1  # type: ignore[arg-type]
    connection.execute.assert_awaited_once()
    assert stale.status == "failed"
    assert stale.failure_code == "census_orphaned"
    assert fresh.status == "building"

    repository = FakeRepository()
    stale = make_map(started_at=datetime.now(UTC) - timedelta(minutes=31))
    repository.maps[stale.id] = stale
    connection.scalar.return_value = False
    assert await processor.reap_orphans(repository) == 0  # type: ignore[arg-type]
    assert stale.status == "building"  # a live claim is never reaped


async def test_interrupted_census_keeps_partial_inventory_and_requires_new_build() -> None:
    from markettwin_control_api.config import Settings
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

    engine = MagicMock(spec=AsyncEngine)
    connection = AsyncMock(spec=AsyncConnection)
    connection.scalar.return_value = True
    engine.connect.return_value.__aenter__.return_value = connection
    processor = CensusProcessor(engine, Settings())
    app_map = make_map()
    repository = FakeRepository()
    repository.maps[app_map.id] = app_map
    repository.count_pages_by_status = AsyncMock(  # type: ignore[method-assign]
        return_value={"census_incomplete": 1},
    )
    processor._repository_on = MagicMock(return_value=repository)  # type: ignore[method-assign]
    processor.run_build = AsyncMock()  # type: ignore[method-assign]

    assert await processor.process_map(app_map.id)
    assert app_map.status == "failed"
    assert app_map.failure_code == "census_interrupted"
    processor.run_build.assert_not_awaited()


# ---------------------------------------------------------------------------
# T-C18: an oversized sitemap travels the sitemap fetch seam, not the
# page-capped one. Map v1 defect: glean.com's sitemap is 3,082,456 bytes;
# the production fetcher's 2 MB page cap truncated it mid-document, the XML
# parse yielded zero URLs, and the census recorded sitemap=0 /
# robots_sitemap=0 while robots_status stayed "ok".
# ---------------------------------------------------------------------------

async def test_t_c18_oversized_sitemap_uses_sitemap_fetch_seam() -> None:
    urls = [f"{ORIGIN}/guides/guide-entry-{index:02d}" for index in range(40)]
    full_body = sitemap_xml(*urls)
    truncated_body = full_body[:1000]
    assert len(truncated_body) < len(full_body)

    site = FakeSite()
    site.add(
        f"{ORIGIN}/robots.txt",
        http_result(
            f"{ORIGIN}/robots.txt",
            body=b"User-agent: *\nSitemap: https://t.example/sitemap.xml\n",
        ),
    )
    # What the page-capped production fetcher hands the engine for this
    # document: a 200 whose body ends mid-tag, which parses to zero URLs.
    site.add(
        f"{ORIGIN}/sitemap.xml",
        http_result(f"{ORIGIN}/sitemap.xml", status=200, body=truncated_body),
    )
    sitemap_site = FakeSite()
    sitemap_site.add(
        f"{ORIGIN}/sitemap.xml",
        http_result(f"{ORIGIN}/sitemap.xml", status=200, body=full_body),
    )

    repository = FakeRepository()
    app_map = make_map()
    repository.maps[app_map.id] = app_map
    report = await build_census(
        repository,
        app_map,
        fetch=site,
        sitemap_fetch=sitemap_site,
        retry_delay=0.0,
    )

    assert sitemap_site.calls == [f"{ORIGIN}/sitemap.xml"]
    sources = report.census_metrics["sources_total_urls"]
    assert sources["robots_sitemap"] == 40
    assert sources["sitemap"] == 0
    assert any(
        "robots_sitemap" in page.source_kinds
        for page in repository.pages_for(app_map.id)
    )


# ---------------------------------------------------------------------------
# Public-target validation (moved with the functions from the retired
# link-research module: URL-shape rejection, private-target rejection,
# same-site scoping)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:secret@example.com",
        "http://example.com:9000",
        "javascript:alert(1)",
    ],
)
def test_invalid_link_rejected(url):
    with pytest.raises(ValueError):
        public_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://169.254.169.254/",
        "http://[::1]/",
        "http://192.168.1.1/",
        "http://localhost/docs",
    ],
)
def test_private_link_target_rejected(url):
    with pytest.raises(ValueError, match="public"):
        validate_link_target(url)


def test_connected_link_scope_and_spa_routes():
    origin = "https://example.com/"
    assert same_site_link(origin, "/guide#heading", origin) == "https://example.com/guide"
    assert same_site_link(origin, "#/guide", origin) == "https://example.com/#/guide"
    assert same_site_link(origin, "https://other.example/", origin) is None
    assert same_site_link(origin, "/logout", origin) is None
