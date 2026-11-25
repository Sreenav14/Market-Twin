"""Phase 4 shared census collection (doc 23 section 6.6; T-CS1 to T-CS3).

T-CS1 pins the shared collection against a literal expected set from a
fake site -- including URLs only the link graph can find. The census
engine's own T-C suite in control-api is the behavioural parity net for
this extraction (census delegates to this module unchanged), so this
file pins the shared seam itself, not the engine's dispositions.

T-CS2: injected-fetcher failures surface as error ``FetchResult``s
through the one-retry discipline, never as exceptions escaping
collection or traversal.

T-CS3: one-implementation pin (doc 16 D14) -- this module USES
``app_map_common``'s canonicaliser and pattern function; it defines
neither itself.
"""

import asyncio
import inspect
from urllib.parse import urljoin, urlsplit

import markettwin_shared.census_sources as census_sources
from markettwin_shared.app_map_common import canonical_url
from markettwin_shared.census_sources import (
    CandidateSet,
    CensusFetchError,
    FetchResult,
    collect_sources,
    induce_patterns,
    traverse_link_graph,
)

BASE = "https://app.example.com/"
ORIGIN = "https://app.example.com"

_ROBOTS = (
    b"User-agent: *\nDisallow: /private\n"
    b"Sitemap: https://app.example.com/sitemap.xml\n"
)
_SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://app.example.com/</loc></url>
  <url><loc>https://app.example.com/about</loc></url>
  <url><loc>https://app.example.com/pricing</loc></url>
</urlset>
"""


def _result(url: str, body: bytes, *, status: int = 200, content_type: str = "text/html") -> FetchResult:
    return FetchResult(
        requested_url=url,
        final_url=url,
        status=status,
        headers={"content-type": content_type},
        body=body,
    )


_PAGES = {
    BASE: _result(
        BASE,
        b'<html><head><title>Home</title></head><body>'
        b'<a href="/about">About</a><a href="/contact">Contact</a>'
        b'<script src="/static/app.js"></script></body></html>',
    ),
    ORIGIN + "/about": _result(
        ORIGIN + "/about",
        b'<html><body><a href="/deep/only">Deep</a></body></html>',
    ),
    ORIGIN + "/pricing": _result(
        ORIGIN + "/pricing",
        b'<html><body><a href="/private/secret">Secret</a></body></html>',
    ),
    ORIGIN + "/contact": _result(ORIGIN + "/contact", b"<html><body>Contact</body></html>"),
    ORIGIN + "/deep/only": _result(ORIGIN + "/deep/only", b"<html><body>Deep</body></html>"),
    ORIGIN + "/changelog": _result(ORIGIN + "/changelog", b"<html><body>Changes</body></html>"),
    ORIGIN + "/flaky": _result(ORIGIN + "/flaky", b"<html><body>Flaky</body></html>"),
    ORIGIN + "/robots.txt": _result(
        ORIGIN + "/robots.txt", _ROBOTS, content_type="text/plain"
    ),
    ORIGIN + "/sitemap.xml": _result(
        ORIGIN + "/sitemap.xml", _SITEMAP, content_type="application/xml"
    ),
    ORIGIN + "/static/app.js": _result(
        ORIGIN + "/static/app.js",
        b'const routes = ["/changelog"]; fetch(routes[0]);',
        content_type="application/javascript",
    ),
}


def _validate(url: str) -> None:
    if urlsplit(url).scheme not in ("http", "https"):
        raise ValueError(f"forbidden scheme in {url!r}")


def _resolve(page_url: str, href: str, base_url: str) -> str | None:
    resolved = urljoin(page_url, href)
    if urlsplit(resolved).netloc != urlsplit(base_url).netloc:
        return None
    return resolved


async def _no_sleep(_seconds: float) -> None:
    return None


def test_cs1_collection_matches_the_literal_expected_set():
    async def run():
        calls: list[str] = []

        async def fetch(url: str) -> FetchResult:
            calls.append(url)
            return _PAGES.get(url) or _result(url, b"nope", status=404)

        candidate_set = CandidateSet(
            base_canonical=canonical_url(BASE), validate=_validate
        )
        facts = await collect_sources(
            candidate_set, base_url=BASE, fetch=fetch,
            retry_delay=0, sleep=_no_sleep,
        )
        rows, _stats, _overflow = induce_patterns(list(candidate_set.candidates.values()))
        fetched_urls: list[str] = []
        disallowed: list[str] = []

        async def on_fetch(candidate, ref, result) -> None:
            fetched_urls.append(candidate.canonical_url)

        async def on_disallowed(candidate, ref) -> None:
            disallowed.append(candidate.canonical_url)

        async def on_discovered(candidate):
            return candidate

        count = await traverse_link_graph(
            candidate_set,
            fetch=fetch,
            robots=facts.robots,
            base_result=facts.base_result,
            base_url=BASE,
            initial=[
                (candidate_set.candidates[row.canonical_url], row.canonical_url)
                for row in rows
            ],
            resolve_link=_resolve,
            retry_delay=0,
            sleep=_no_sleep,
            on_fetch=on_fetch,
            on_disallowed=on_disallowed,
            on_discovered=on_discovered,
        )
        return candidate_set, facts, count, fetched_urls, disallowed, calls

    candidate_set, facts, count, fetched_urls, disallowed, calls = asyncio.run(run())

    expected = {
        BASE,
        ORIGIN + "/about",
        ORIGIN + "/pricing",
        ORIGIN + "/contact",
        ORIGIN + "/deep/only",
        ORIGIN + "/changelog",
        ORIGIN + "/private/secret",
    }
    assert set(candidate_set.candidates) == expected
    assert facts.robots_status == "ok"
    kinds = {url: c.source_kinds for url, c in candidate_set.candidates.items()}
    assert kinds[ORIGIN + "/pricing"] == {"robots_sitemap"}
    assert kinds[ORIGIN + "/changelog"] == {"route_bundle"}
    # Link-graph-only finds: nothing but traversal reaches these two.
    assert kinds[ORIGIN + "/contact"] == {"link_graph"}
    assert kinds[ORIGIN + "/deep/only"] == {"link_graph"}
    # Robots-disallowed: collected, named, never fetched.
    assert disallowed == [ORIGIN + "/private/secret"]
    assert ORIGIN + "/private/secret" not in calls
    assert count == 6
    assert set(fetched_urls) == expected - {ORIGIN + "/private/secret"}


def test_cs2_fetcher_failures_surface_as_error_results():
    async def run():
        attempts: dict[str, int] = {}

        async def fetch(url: str) -> FetchResult:
            attempts[url] = attempts.get(url, 0) + 1
            if url.endswith("/flaky") and attempts[url] == 1:
                raise CensusFetchError("connection reset")
            if url.endswith("/down"):
                raise CensusFetchError("dns failure")
            return _PAGES.get(url) or _result(url, b"nope", status=404)

        candidate_set = CandidateSet(
            base_canonical=canonical_url(BASE), validate=_validate
        )
        facts = await collect_sources(
            candidate_set, base_url=BASE, fetch=fetch,
            retry_delay=0, sleep=_no_sleep,
        )
        seen: dict[str, FetchResult] = {}

        async def on_fetch(candidate, ref, result) -> None:
            seen[candidate.canonical_url] = result

        rows, _stats, _overflow = induce_patterns(list(candidate_set.candidates.values()))
        # Two extra queued pages: one flaky (fails once, then succeeds),
        # one down (fails both attempts).
        for extra in ("/flaky", "/down"):
            candidate_set.add(ORIGIN + extra, "link_graph", 0)
        initial = [
            (candidate_set.candidates[row.canonical_url], row.canonical_url)
            for row in rows
        ] + [
            (candidate_set.candidates[ORIGIN + extra], ORIGIN + extra)
            for extra in ("/flaky", "/down")
        ]
        await traverse_link_graph(
            candidate_set,
            fetch=fetch,
            robots=facts.robots,
            base_result=facts.base_result,
            base_url=BASE,
            initial=initial,
            resolve_link=_resolve,
            retry_delay=0,
            sleep=_no_sleep,
            on_fetch=on_fetch,
        )
        return seen, attempts

    seen, attempts = asyncio.run(run())
    # One retry, then success: the delivered result is the good page.
    assert attempts[ORIGIN + "/flaky"] == 2
    assert seen[ORIGIN + "/flaky"].status == 200
    assert seen[ORIGIN + "/flaky"].error is None
    # Both attempts fail: an error result is delivered, nothing raises.
    assert attempts[ORIGIN + "/down"] == 2
    assert seen[ORIGIN + "/down"].status is None
    assert seen[ORIGIN + "/down"].error == "dns failure"


def test_cs3_one_implementation_of_canonicalisation_and_patterns():
    source = inspect.getsource(census_sources)
    assert "def canonical_url" not in source
    assert "def route_pattern_for" not in source
    # The names the module uses ARE app_map_common's objects, not copies.
    assert census_sources.canonical_url is canonical_url
    from markettwin_shared.app_map_common import route_pattern_for

    assert census_sources.route_pattern_for is route_pattern_for
