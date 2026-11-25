"""Phase 4 preflight sweep (doc 23 section 6.4; T-PF1 to T-PF7).

House fake style: a dict-driven fetcher (the shared census_sources
seam), a recording render fake, an in-memory repository fake. No
network, no browser, no database.
"""

import asyncio
import hashlib
from types import SimpleNamespace
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

from markettwin_shared.census_sources import FetchResult

from markettwin_execution_orchestrator.freshness.preflight_sweep import (
    RenderedState,
    RenderOutcome,
    run_sweep,
)
from markettwin_execution_orchestrator.workflow.coverage_delta import (
    build_preflight_delta,
)

BASE = "https://app.example.com/"
ORIGIN = "https://app.example.com"


def _result(url, body, *, status=200, content_type="text/html", error=None):
    return FetchResult(
        requested_url=url,
        final_url=url if status is not None else None,
        status=status,
        headers={"content-type": content_type} if status is not None else {},
        body=body,
        error=error,
    )


def _html(title, extra=""):
    return f"<html><head><title>{title}</title></head><body>{extra}</body></html>".encode()


def _page_row(url, body, *, status=200, title=None):
    """A recorded page row whose fingerprint matches ``body`` exactly."""
    return SimpleNamespace(
        id=uuid4(),
        canonical_url=url,
        http_status=status,
        redirect_target=None,
        content_type="text/html",
        title=title,
        html_sha256=hashlib.sha256(body).hexdigest() if body else None,
    )


def _state_row(state_id, *, phash=None):
    return SimpleNamespace(
        id=uuid4(),
        state_id=state_id,
        state_key="default",
        dom_structure_hash="dom",
        aria_hash="aria",
        screenshot_hash="shot",
        screenshot_phash=phash,
    )


class _Repository:
    def __init__(self):
        self.touched = []

    async def touch_verified_state(self, state_row_id, *, last_verified_at, screenshot_phash):
        self.touched.append((state_row_id, screenshot_phash))


def _validate(url):
    if urlsplit(url).scheme not in ("http", "https"):
        raise ValueError("scheme")


def _resolve(page_url, href, base_url):
    resolved = urljoin(page_url, href)
    if urlsplit(resolved).netloc != urlsplit(base_url).netloc:
        return None
    return resolved


async def _no_sleep(_seconds):
    return None


def _run(*, pages, states_by_page, site, render, render_cap=150, sitemap_urls=None):
    """site: url -> FetchResult for page fetches (sitemap/robots/base
    are synthesised from ``sitemap_urls`` and the base body)."""

    sitemap_body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{url}</loc></url>" for url in (sitemap_urls or []))
        + "</urlset>"
    ).encode()
    robots = b"User-agent: *\nSitemap: https://app.example.com/sitemap.xml\n"
    base_body = _html("Home")

    async def fetch(url):
        if url == ORIGIN + "/robots.txt":
            return _result(url, robots, content_type="text/plain")
        if url == ORIGIN + "/sitemap.xml":
            return _result(url, sitemap_body, content_type="application/xml")
        if url == BASE:
            return _result(url, base_body)
        return site.get(url) or _result(url, b"missing", status=404)

    # The base page is always a map row and always recollected (the
    # collection's seed), so every scenario carries it in E.
    base_page = _page_row(BASE, base_body, title="Home")
    base_state = _state_row("state-base")
    pages = [base_page, *pages]
    states_by_page = {base_page.id: [base_state], **states_by_page}
    app_map = SimpleNamespace(
        id=uuid4(), workspace_id=uuid4(), application_id=uuid4(),
        target_id=uuid4(), base_url=BASE,
    )
    preflight = SimpleNamespace(id=uuid4())
    repository = _Repository()
    events = []

    async def emit(event_type, payload):
        events.append((event_type, payload))

    result = asyncio.run(
        run_sweep(
            repository=repository,
            preflight=preflight,
            app_map=app_map,
            pages=pages,
            states_by_page=states_by_page,
            fetch=fetch,
            sitemap_fetch=None,
            render=render,
            validate=_validate,
            resolve_link=_resolve,
            emit=emit,
            render_cap=render_cap,
            wall_budget_seconds=1800,
            retry_delay=0,
            sleep=_no_sleep,
        )
    )
    return result, repository, events, pages, states_by_page


def _delta(pages, states_by_page, result):
    block = {
        "map_id": "map-x",
        "version_number": 3,
        "routes_truncated": False,
        "counts": {"expected": len(pages)},
        "pages": [
            {
                "url": page.canonical_url,
                "status": "fetch_ok",
                "states": [
                    {"state_id": state.state_id}
                    for state in states_by_page.get(page.id, [])
                ],
            }
            for page in pages
        ],
    }
    return build_preflight_delta(
        map_block=block, tier1=result.tier1, tier2=result.tier2,
        recollected=result.recollected,
    )


def test_pf1_unchanged_app_renders_nothing_and_reports_all_present():
    body_a = _html("A")
    page_a = _page_row(ORIGIN + "/a", body_a, title="A")
    state_a = _state_row("state-a")
    render_calls = []

    async def render(url):
        render_calls.append(url)
        raise AssertionError("tier 2 must not run on an unchanged app")

    result, repository, _events, _pages, _states = _run(
        pages=[page_a],
        states_by_page={page_a.id: [state_a]},
        site={ORIGIN + "/a": _result(ORIGIN + "/a", body_a)},
        render=render,
        sitemap_urls=[ORIGIN + "/a"],
    )
    assert render_calls == []
    assert result.status == "ready"
    assert result.tier2 == {}
    delta = _delta(_pages, _states, result)
    assert delta["present"] == [BASE, ORIGIN + "/a"]
    assert delta["counts"] == {"present": 2, "missing": 0, "unreachable": 0,
                               "changed": 0, "new": 0}
    # Tier-1-only pages get page-grade history rows, no state touches.
    assert repository.touched == []
    assert any(
        row["state_key"] == "page" and row["canonical_url"] == ORIGIN + "/a"
        for row in result.history_rows
    )


def test_pf2_html_drift_is_present_with_distance_and_a_state_touch():
    recorded_body = _html("B")
    drifted_body = _html("B", "<p>rotated banner</p>")
    page_b = _page_row(ORIGIN + "/b", recorded_body, title="B")
    state_b = _state_row("state-b", phash="ahash:0000000000000000")

    async def render(url):
        return RenderOutcome(
            kind="ok",
            states=[RenderedState(
                state_id="state-b", dom_structure_hash="dom",
                aria_hash="aria", screenshot_hash="shot",
                screenshot_phash="ahash:000000000000000f",
            )],
            title="B",
        )

    result, repository, _events, _pages, _states = _run(
        pages=[page_b],
        states_by_page={page_b.id: [state_b]},
        site={ORIGIN + "/b": _result(ORIGIN + "/b", drifted_body)},
        render=render,
        sitemap_urls=[ORIGIN + "/b"],
    )
    entry = result.tier2[ORIGIN + "/b"]
    assert entry["outcome"] == "present"
    assert entry["html_drift"] is True
    assert entry["visual_distance"] == 4
    delta = _delta(_pages, _states, result)
    assert delta["present"] == [BASE, ORIGIN + "/b"]
    assert delta["html_drift_count"] == 1
    # The verified state was touched with the live phash recorded.
    assert repository.touched == [(state_b.id, "ahash:000000000000000f")]


def test_pf3_state_change_is_changed_with_the_default_pair():
    body_c = _html("C")
    page_c = _page_row(ORIGIN + "/c", body_c, title="C")
    state_c = _state_row("state-c")

    async def render(url):
        return RenderOutcome(
            kind="ok",
            states=[RenderedState(state_id="state-c2")],
            title="C",
        )

    result, _repo, _events, _pages, _states = _run(
        pages=[page_c],
        states_by_page={page_c.id: [state_c]},
        site={ORIGIN + "/c": _result(ORIGIN + "/c", _html("C", "<p>new</p>"))},
        render=render,
        sitemap_urls=[ORIGIN + "/c"],
    )
    delta = _delta(_pages, _states, result)
    assert delta["changed"] == [
        {"url": ORIGIN + "/c", "recorded_state_id": "state-c",
         "live_state_id": "state-c2", "basis": "state"}
    ]
    assert delta["basis_counts"] == {"state": 1, "html": 0}


def test_pf4_missing_needs_both_confirmations():
    body = _html("X")
    gone = _page_row(ORIGIN + "/gone", body, title="X")
    claimed = _page_row(ORIGIN + "/claimed", body, title="X")
    pages = [gone, claimed]
    states = {gone.id: [_state_row("s-gone")], claimed.id: [_state_row("s-claimed")]}

    async def render(url):
        raise AssertionError("404 pages are not rendered")

    result, _repo, _events, _pages, _states = _run(
        pages=pages,
        states_by_page=states,
        site={
            ORIGIN + "/gone": _result(ORIGIN + "/gone", b"nope", status=404),
            ORIGIN + "/claimed": _result(ORIGIN + "/claimed", b"nope", status=404),
        },
        render=render,
        sitemap_urls=[ORIGIN + "/claimed"],  # 'gone' is absent from the collection
    )
    delta = _delta(_pages, _states, result)
    assert delta["missing"] == [{"url": ORIGIN + "/gone", "http_status": 404}]
    assert delta["unreachable"] == [
        {"url": ORIGIN + "/claimed", "reason": "fetch_error"}
    ]


def test_pf5_unreachable_reasons_from_fetch_and_render():
    body = _html("W")
    walled = _page_row(ORIGIN + "/walled", body, title="W")
    down = _page_row(ORIGIN + "/down", body, title="W")
    pages = [walled, down]
    states = {walled.id: [_state_row("s-w")], down.id: [_state_row("s-d")]}

    async def render(url):
        return RenderOutcome(kind="blocked_auth")

    result, _repo, _events, _pages, _states = _run(
        pages=pages,
        states_by_page=states,
        site={
            ORIGIN + "/walled": _result(ORIGIN + "/walled", _html("W", "<p>x</p>")),
            ORIGIN + "/down": _result(
                ORIGIN + "/down", b"", status=None, error="dns failure"
            ),
        },
        render=render,
        sitemap_urls=[ORIGIN + "/walled", ORIGIN + "/down"],
    )
    delta = _delta(_pages, _states, result)
    assert delta["unreachable"] == [
        {"url": ORIGIN + "/down", "reason": "fetch_error"},
        {"url": ORIGIN + "/walled", "reason": "blocked_auth"},
    ]


def test_pf6_render_cap_overflow_is_deferred_and_partial():
    pages = []
    states = {}
    site = {}
    sitemap = []
    for letter in "abcd":
        url = ORIGIN + f"/{letter}"
        body = _html(letter.upper())
        page = _page_row(url, body, title=letter.upper())
        pages.append(page)
        states[page.id] = [_state_row(f"state-{letter}")]
        site[url] = _result(url, _html(letter.upper(), "<p>drift</p>"))
        sitemap.append(url)
    rendered = []

    async def render(url):
        rendered.append(url)
        letter = url.rsplit("/", 1)[1]
        return RenderOutcome(
            kind="ok", states=[RenderedState(state_id=f"state-{letter}")],
            title=letter.upper(),
        )

    result, _repo, events, _pages, _states = _run(
        pages=pages, states_by_page=states, site=site, render=render,
        sitemap_urls=sitemap, render_cap=2,
    )
    assert len(rendered) == 2
    assert result.status == "partial"
    assert {entry["reason"] for entry in result.deferred} == {"render_cap"}
    assert len(result.deferred) == 2
    assert any(t == "preflight.cap.reached" for t, _p in events)
    delta = _delta(_pages, _states, result)
    assert delta["delta_scope"] == "partial_sweep"


def test_pf7_signature_less_page_stands_on_the_html_basis():
    body = _html("F")
    page_f = _page_row(ORIGIN + "/f", body, title="F")

    async def render(url):
        return RenderOutcome(kind="ok", states=[], title="F")

    result, _repo, _events, _pages, _states = _run(
        pages=[page_f],
        states_by_page={page_f.id: []},
        site={ORIGIN + "/f": _result(ORIGIN + "/f", _html("F", "<p>changed</p>"))},
        render=render,
        sitemap_urls=[ORIGIN + "/f"],
    )
    delta = _delta(_pages, _states, result)
    assert delta["changed"] == [
        {"url": ORIGIN + "/f", "recorded_state_id": None,
         "live_state_id": None, "basis": "html"}
    ]
    assert delta["basis_counts"] == {"state": 0, "html": 1}


def test_pf8_one_pages_capture_failure_is_that_pages_outcome_only():
    # ORC1-02: a render that raises for one candidate page must not
    # fail the whole sweep; the page dispositions as unreachable
    # (fetch_error) and the other candidates render normally.
    body = _html("P")
    boom = _page_row(ORIGIN + "/boom", body, title="P")
    fine = _page_row(ORIGIN + "/fine", body, title="P")
    pages = [boom, fine]
    states = {boom.id: [_state_row("s-boom")], fine.id: [_state_row("s-fine")]}

    async def render(url):
        if url.endswith("/boom"):
            raise RuntimeError("capture exploded")
        return RenderOutcome(
            kind="ok",
            states=[RenderedState(state_id="s-fine")],
            title="P",
        )

    result, _repo, _events, _pages, _states = _run(
        pages=pages,
        states_by_page=states,
        site={
            ORIGIN + "/boom": _result(ORIGIN + "/boom", _html("P", "<p>x</p>")),
            ORIGIN + "/fine": _result(ORIGIN + "/fine", _html("P", "<p>x</p>")),
        },
        render=render,
        sitemap_urls=[ORIGIN + "/boom", ORIGIN + "/fine"],
    )
    assert result.tier2[ORIGIN + "/boom"] == {
        "outcome": "unreachable", "reason": "fetch_error",
    }
    delta = _delta(_pages, _states, result)
    assert delta["unreachable"] == [
        {"url": ORIGIN + "/boom", "reason": "fetch_error"}
    ]
    assert ORIGIN + "/fine" in delta["present"]
