"""Shared census source collection (Phase 4, doc 23 section 6.6).

The collection half of the census -- robots/sitemap walking, route
bundle extraction, route-pattern induction, and the unrendered
link-graph traversal -- lives here exactly once, as pure functions
over injected callables (doc 16 D14's one-implementation discipline).
Control-api's census delegates its stages 1-3 to this module and adds
its disposition table on top; the orchestrator's freshness sweep
reuses the same collection to re-derive a target's expected URL set.

Injected seams: ``fetch`` (each service passes its own fetcher, same
discipline), ``validate`` (a URL target check that raises ValueError
on a forbidden target), and ``resolve_link`` (same-site link
resolution for the traversal's discovery step). No I/O of its own, no
model clients (spec C1).
"""

import asyncio
import itertools
import json
import logging
import re
from collections import deque
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

from markettwin_shared.app_map_common import canonical_url, route_pattern_for

logger = logging.getLogger(__name__)

CENSUS_MAX_URLS = 5000  # [J]
CENSUS_GRAPH_MAX_DISCOVERED = 1000  # maximum graph-discovered URLs
CENSUS_GRAPH_MAX_DEPTH = 3  # [J]
CENSUS_SITEMAP_MAX_DEPTH = 2  # [J]
CENSUS_BUNDLE_MAX_FILES = 10  # [J]
# Sitemap documents are fetched whole-or-nothing: a body truncated at the
# page cap is unparseable XML, so the sitemap stage silently yields zero
# URLs (glean.com's sitemap is 3,082,456 bytes; map v1 recorded sitemap=0 /
# robots_sitemap=0 for exactly this reason). Sitemap fetches therefore use
# their own budget, sized for machine documents rather than pages.
CENSUS_SITEMAP_MAX_BYTES = 64_000_000  # [J]
PATTERN_EXEMPLAR_CAP = 5  # [J]

SOURCE_KINDS = ("sitemap", "robots_sitemap", "route_bundle", "link_graph")
_STATIC_ASSET_EXTENSIONS = (
    ".js", ".css", ".png", ".jpg", ".jpeg", ".svg", ".ico",
    ".woff", ".woff2", ".map", ".json", ".xml", ".txt",
)
_STRING_LITERAL_RE = re.compile(
    r'"([^"\\\n]{1,300})"|\'([^\'\\\n]{1,300})\'|`([^`\\]{1,300})`'
)
_SOURCE_MAP_RE = re.compile(r"//#\s*sourceMappingURL=(\S+)")


class CensusFetchError(Exception):
    """A network-level fetch failure (DNS, TLS, timeout, connection)."""


@dataclass(frozen=True)
class FetchHop:
    url: str
    status: int


@dataclass(frozen=True)
class FetchResult:
    """One completed fetch attempt, as the disposition table consumes it."""

    requested_url: str
    final_url: str | None
    status: int | None  # final (or last good) response status; None if none
    headers: Mapping[str, str]  # final response headers, keys lowercased
    body: bytes
    redirect_chain: tuple[FetchHop, ...] = ()
    error: str | None = None  # network-level failure detail (metrics only)
    blocked_hop: bool = False  # a redirect hop failed validate_link_target


FetchCallable = Callable[[str], Awaitable[FetchResult]]


class _HTMLScan(HTMLParser):
    """Stdlib scan of one unrendered page: links, script sources, embedded
    JSON blocks, and the title. No new dependency (doc 14 section 6.2)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.script_srcs: list[str] = []
        self.json_blocks: list[str] = []
        self._title_parts: list[str] = []
        self._in_title = False
        self._json_buffer: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "a":
            href = attr.get("href")
            if href:
                self.links.append(href)
        elif tag == "title":
            self._in_title = True
        elif tag == "script":
            src = attr.get("src")
            if src:
                self.script_srcs.append(src)
            if (attr.get("type") or "").strip().lower() == "application/json":
                self._json_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._json_buffer is not None:
            self.json_blocks.append("".join(self._json_buffer))
            self._json_buffer = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._json_buffer is not None:
            self._json_buffer.append(data)

    @property
    def title(self) -> str | None:
        text = " ".join("".join(self._title_parts).split())[:300]
        return text or None


def _scan_html(body: bytes) -> _HTMLScan:
    scan = _HTMLScan()
    try:
        scan.feed(body.decode("utf-8", "replace"))
    except Exception:  # html.parser is forgiving; keep what was collected
        logger.debug("HTML scan stopped early", exc_info=True)
    return scan



@dataclass
class RobotsRules:
    sitemaps: list[str] = field(default_factory=list)
    disallowed_prefixes: list[str] = field(default_factory=list)

    def is_disallowed(self, path: str) -> bool:
        return any(
            prefix and path.startswith(prefix) for prefix in self.disallowed_prefixes
        )


def parse_robots(body: bytes) -> RobotsRules:
    """Parse robots.txt text: ``Sitemap:`` lines plus the Disallow rules of
    the groups applying to ``*`` or the census agent (doc 14 section 6.2)."""
    rules = RobotsRules()
    group_agents: list[str] = []
    group_rules: list[str] = []
    group_has_rules = False

    def flush_group() -> None:
        nonlocal group_agents, group_rules, group_has_rules
        if any(
            agent in ("*", "markettwincensus") for agent in group_agents
        ):
            rules.disallowed_prefixes.extend(group_rules)
        group_agents, group_rules, group_has_rules = [], [], False

    for raw_line in body.decode("utf-8", "replace").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        name, _, value = line.partition(":")
        name, value = name.strip().lower(), value.strip()
        if name == "sitemap":
            if value:
                rules.sitemaps.append(value)
        elif name == "user-agent":
            if group_has_rules:
                flush_group()
            group_agents.append(value.lower())
        elif name == "disallow":
            group_has_rules = True
            if value:
                group_rules.append(value)
        elif name in ("allow", "crawl-delay"):
            group_has_rules = True
    flush_group()
    return rules



def parse_sitemap(body: bytes) -> tuple[list[str], list[str]]:
    """``(page locs, child sitemap locs)`` from one sitemap document."""
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return [], []
    locs = [
        (element.text or "").strip()
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "loc"
    ]
    locs = [loc for loc in locs if loc]
    if root.tag.rsplit("}", 1)[-1] == "sitemapindex":
        return [], locs
    if root.tag.rsplit("}", 1)[-1] == "urlset":
        return locs, []
    return [], []



def _is_route_literal(value: str) -> bool:
    """The route-literal rule of doc 14 section 6.2, exactly as specced."""
    if not value.startswith("/") or not 2 <= len(value) <= 200:
        return False
    if any(char.isspace() for char in value):
        return False
    if any(char in value for char in "<>\"'"):
        return False
    if "//" in value[1:]:
        return False
    path = value.split("?", 1)[0].split("#", 1)[0]
    return not path.lower().endswith(_STATIC_ASSET_EXTENSIONS)


def extract_route_literals(text: str) -> list[str]:
    found: list[str] = []
    for match in _STRING_LITERAL_RE.finditer(text):
        value = next(group for group in match.groups() if group is not None)
        if _is_route_literal(value):
            found.append(value)
    return found




@dataclass
class CensusCandidate:
    canonical_url: str
    source_kinds: set[str]
    depth: int
    order: int


@dataclass(frozen=True)
class InducedRow:
    """One denominator row produced by induction: the shared shape of
    census's ``NewPage`` (each service maps it onto its own row type)."""

    canonical_url: str
    route_pattern: str
    source_kinds: tuple[str, ...]

def induce_patterns(
    candidates: Iterable[CensusCandidate],
    *,
    exemplar_cap: int = PATTERN_EXEMPLAR_CAP,
    max_urls: int = CENSUS_MAX_URLS,
) -> tuple[list[InducedRow], dict[str, dict[str, int]], int]:
    """Group candidates by route pattern; the first ``exemplar_cap`` per
    pattern (canonical order) become denominator rows, the rest are counted
    in pattern_stats, never rowed (doc 14 sections 6.3, D2, D3)."""
    by_pattern: dict[str, list[CensusCandidate]] = {}
    for candidate in candidates:
        by_pattern.setdefault(route_pattern_for(candidate.canonical_url), []).append(
            candidate
        )
    rows: list[InducedRow] = []
    pattern_stats: dict[str, dict[str, int]] = {}
    for pattern, group in by_pattern.items():
        ordered = sorted(group, key=lambda candidate: candidate.canonical_url)
        kept = ordered[:exemplar_cap]
        pattern_stats[pattern] = {"instances": len(group), "exemplars": len(kept)}
        rows.extend(
            InducedRow(
                canonical_url=candidate.canonical_url,
                route_pattern=pattern,
                source_kinds=tuple(sorted(candidate.source_kinds)),
            )
            for candidate in kept
        )
    rows.sort(key=lambda row: (row.route_pattern, row.canonical_url))
    overflow = 0
    if len(rows) > max_urls:
        overflow = len(rows) - max_urls
        rows = rows[:max_urls]
    return rows, pattern_stats, overflow




def _response_content_type(headers: Mapping[str, str]) -> str | None:
    raw = headers.get("content-type")
    if not raw:
        return None
    value = raw.split(";", 1)[0].strip().lower()
    return value or None



def _origin_key(url: str) -> tuple[str, str]:
    parsed = urlsplit(url)
    return parsed.scheme, parsed.netloc


def _looks_like_html(result: FetchResult) -> bool:
    content_type = _response_content_type(result.headers)
    if content_type in ("text/html", "application/xhtml+xml"):
        return True
    if content_type is None:
        return b"<" in (result.body or b"")[:512]
    return False



async def _fetch_with_retry(
    fetch: FetchCallable,
    url: str,
    *,
    retry_delay: float,
    sleep: Callable[[float], Awaitable[None]],
) -> FetchResult:
    """One retry, after a pause, on network error or 5xx only (section 6.4)."""
    result: FetchResult | None = None
    for attempt in range(2):
        try:
            result = await fetch(url)
        except CensusFetchError as exc:
            if attempt == 0:
                await sleep(retry_delay)
                continue
            return FetchResult(
                requested_url=url, final_url=None, status=None,
                headers={}, body=b"", error=str(exc),
            )
        retryable = (result.status is not None and result.status >= 500) or (
            result.error is not None and result.status is None
        )
        if retryable and attempt == 0:
            await sleep(retry_delay)
            continue
        return result
    assert result is not None  # the second attempt always returns above
    return result


@dataclass(frozen=True)
class CollectionLimits:
    """The collection caps, defaulting to the census values of record."""

    max_urls: int = CENSUS_MAX_URLS
    max_discovered: int = CENSUS_GRAPH_MAX_DISCOVERED
    max_depth: int = CENSUS_GRAPH_MAX_DEPTH
    max_sitemap_depth: int = CENSUS_SITEMAP_MAX_DEPTH
    max_bundle_files: int = CENSUS_BUNDLE_MAX_FILES
    exemplar_cap: int = PATTERN_EXEMPLAR_CAP


@dataclass
class CandidateSet:
    """The candidate registry: census's ``add_candidate`` closure as a
    small object, so both engines collect into the same bookkeeping.

    ``validate`` is the injected target check (raises ValueError on a
    forbidden target); collection is same-origin only by construction.
    """

    base_canonical: str
    validate: Callable[[str], object]
    candidates: dict[str, CensusCandidate] = field(default_factory=dict)
    source_sets: dict[str, set[str]] = field(
        default_factory=lambda: {kind: set() for kind in SOURCE_KINDS}
    )
    _order: Any = field(default_factory=itertools.count)
    _target_key: tuple[str, str] = field(init=False)

    def __post_init__(self) -> None:
        self._target_key = _origin_key(self.base_canonical)

    def add(
        self, raw_url: str, kind: str | None, depth: int
    ) -> CensusCandidate | None:
        if not raw_url:
            return None
        try:
            self.validate(raw_url)
        except ValueError:
            return None
        canon = canonical_url(raw_url)
        if _origin_key(canon) != self._target_key:
            return None  # collection is same-origin only (rules 1-2 handle the rest)
        existing = self.candidates.get(canon)
        if existing is not None:
            if kind is not None:
                existing.source_kinds.add(kind)
                self.source_sets[kind].add(canon)
            return existing
        candidate = CensusCandidate(
            canonical_url=canon,
            source_kinds={kind} if kind is not None else set(),
            depth=depth,
            order=next(self._order),
        )
        self.candidates[canon] = candidate
        if kind is not None:
            self.source_sets[kind].add(canon)
        return candidate


@dataclass(frozen=True)
class SourceFacts:
    """What source collection learned before any page was fetched."""

    robots: RobotsRules
    robots_status: str  # 'ok' | 'absent' | 'unreachable'
    base_result: FetchResult


def _retried(
    fetch: FetchCallable,
    *,
    retry_delay: float,
    sleep: Callable[[float], Awaitable[None]],
) -> Callable[[str], Awaitable[FetchResult]]:
    async def fetch_page(url: str) -> FetchResult:
        return await _fetch_with_retry(fetch, url, retry_delay=retry_delay, sleep=sleep)

    return fetch_page


async def collect_sources(
    candidate_set: CandidateSet,
    *,
    base_url: str,
    fetch: FetchCallable,
    sitemap_fetch: FetchCallable | None = None,
    limits: CollectionLimits = CollectionLimits(),
    retry_delay: float = 1.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> SourceFacts:
    """Census stages 1a + 1b: robots, sitemaps, route bundles.

    Fills ``candidate_set`` and returns the robots rules, their status,
    and the base page's fetch result (the traversal reuses it). Ends
    with census stage 2's kind defaulting: the base URL is the
    link-graph seed, so an unclaimed candidate is a link-graph find.
    """
    parsed_base = urlsplit(base_url)
    origin_root = f"{parsed_base.scheme}://{parsed_base.netloc}"
    fetch_page = _retried(fetch, retry_delay=retry_delay, sleep=sleep)

    async def fetch_sitemap(url: str) -> FetchResult:
        # Sitemap documents travel their own seam so the caller's
        # sitemap-sized fetch budget applies (see CENSUS_SITEMAP_MAX_BYTES);
        # without one, the page fetch is used unchanged.
        return await _fetch_with_retry(
            sitemap_fetch if sitemap_fetch is not None else fetch,
            url,
            retry_delay=retry_delay,
            sleep=sleep,
        )

    # --- Stage 1a: robots + sitemaps -------------------------------------
    robots_result = await fetch_page(f"{origin_root}/robots.txt")
    robots = RobotsRules()
    if robots_result.error is not None or robots_result.status is None:
        robots_status = "unreachable"
    elif robots_result.status == 200:
        robots_status = "ok"
        robots = parse_robots(robots_result.body)
    elif 400 <= robots_result.status < 500:
        robots_status = "absent"
    else:
        robots_status = "unreachable"
    sitemap_roots = [(url, "robots_sitemap") for url in robots.sitemaps] or [
        (f"{origin_root}/sitemap.xml", "sitemap")
    ]
    sitemap_queue: deque[tuple[str, str, int]] = deque(
        (url, kind, 0) for url, kind in sitemap_roots
    )
    seen_sitemaps: set[str] = set()
    while sitemap_queue:
        sitemap_url, kind, depth = sitemap_queue.popleft()
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        result = await fetch_sitemap(sitemap_url)
        if result.error is not None or result.status != 200 or not result.body:
            continue
        page_urls, child_sitemaps = parse_sitemap(result.body)
        for loc in page_urls:
            candidate_set.add(urljoin(sitemap_url, loc), kind, 0)
        if depth < limits.max_sitemap_depth:
            for child in child_sitemaps:
                child_url = urljoin(sitemap_url, child)
                if _origin_key(canonical_url(child_url)) == candidate_set._target_key:
                    sitemap_queue.append((child_url, kind, depth + 1))

    # --- Stage 1b: route-table / bundle extraction ------------------------
    base_result = await fetch_page(base_url)
    if base_result.body and _looks_like_html(base_result):
        scan = _scan_html(base_result.body)
        for block in scan.json_blocks:
            for literal in extract_route_literals(block):
                candidate_set.add(urljoin(origin_root, literal), "route_bundle", 0)
        script_urls: list[str] = []
        for src in scan.script_srcs:
            resolved = urljoin(base_url, src)
            if _origin_key(canonical_url(resolved)) != candidate_set._target_key:
                continue
            if resolved not in script_urls:
                script_urls.append(resolved)
        bundle_files = 0

        def absorb_source_map(body: bytes) -> None:
            try:
                payload = json.loads(body)
            except ValueError:
                return
            if not isinstance(payload, dict):
                return
            for content in payload.get("sourcesContent") or []:
                if isinstance(content, str):
                    for literal in extract_route_literals(content):
                        candidate_set.add(
                            urljoin(origin_root, literal), "route_bundle", 0
                        )

        for script_url in script_urls:
            if bundle_files >= limits.max_bundle_files:
                break
            bundle_files += 1
            if script_url.split("?", 1)[0].lower().endswith(".map"):
                absorb_source_map((await fetch_page(script_url)).body)
                continue
            script_result = await fetch_page(script_url)
            if not script_result.body:
                continue
            script_text = script_result.body.decode("utf-8", "replace")
            for literal in extract_route_literals(script_text):
                candidate_set.add(urljoin(origin_root, literal), "route_bundle", 0)
            map_match = _SOURCE_MAP_RE.search(script_text)
            if map_match and bundle_files < limits.max_bundle_files:
                bundle_files += 1
                map_result = await fetch_page(urljoin(script_url, map_match.group(1)))
                absorb_source_map(map_result.body)

    # The base URL is the link-graph seed; if no source claimed it, the
    # link_graph kind is what it was discovered by.
    candidate_set.add(base_url, None, 0)
    for candidate in candidate_set.candidates.values():
        if not candidate.source_kinds:
            candidate.source_kinds = {"link_graph"}
            candidate_set.source_sets["link_graph"].add(candidate.canonical_url)
    return SourceFacts(
        robots=robots, robots_status=robots_status, base_result=base_result
    )


async def traverse_link_graph(
    candidate_set: CandidateSet,
    *,
    fetch: FetchCallable,
    robots: RobotsRules,
    base_result: FetchResult,
    base_url: str,
    initial: Iterable[tuple[CensusCandidate, Any]],
    limits: CollectionLimits = CollectionLimits(),
    resolve_link: Callable[[str, str, str], str | None],
    retry_delay: float = 1.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_fetch: Callable[[CensusCandidate, Any, FetchResult], Awaitable[None]] | None = None,
    on_disallowed: Callable[[CensusCandidate, Any], Awaitable[None]] | None = None,
    on_discovered: Callable[[CensusCandidate], Awaitable[Any]] | None = None,
    on_progress: Callable[[int], Awaitable[None]] | None = None,
) -> int:
    """Census stage 3's traversal, minus its verdicts: fetch every
    queued candidate once (robots-disallowed ones are never fetched),
    scan 2xx HTML for links, and close the link graph under the caps.

    ``initial`` pairs each starting candidate with a caller-owned ref
    (census: the inserted row's page id; the sweep: the candidate
    itself). Hooks: ``on_disallowed`` / ``on_fetch`` receive
    (candidate, ref[, result]); ``on_discovered`` receives a newly
    found candidate and returns the ref to queue it with, or None to
    count it without queueing; ``on_progress`` fires every 50 fetches.
    Returns the fetch count.
    """
    fetch_page = _retried(fetch, retry_delay=retry_delay, sleep=sleep)
    base_canonical = candidate_set.base_canonical

    def queue_priority(candidate: CensusCandidate) -> int:
        if candidate.canonical_url == base_canonical:
            return 0
        if candidate.source_kinds & {"sitemap", "robots_sitemap"}:
            return 1
        if "route_bundle" in candidate.source_kinds:
            return 2
        return 3

    queue: deque[tuple[CensusCandidate, Any]] = deque(
        sorted(
            initial,
            key=lambda entry: (queue_priority(entry[0]), entry[0].order),
        )
    )
    fetched = 0
    while queue:
        candidate, ref = queue.popleft()
        path = urlsplit(candidate.canonical_url).path or "/"
        if robots.is_disallowed(path):  # rule 2: never fetched
            if on_disallowed is not None:
                await on_disallowed(candidate, ref)
            continue
        if candidate.canonical_url == base_canonical:
            result = base_result
        else:
            result = await fetch_page(candidate.canonical_url)
        fetched += 1
        if on_fetch is not None:
            await on_fetch(candidate, ref, result)
        if on_progress is not None and fetched % 50 == 0:
            await on_progress(fetched)
        if (
            candidate.depth < limits.max_depth
            and result.status is not None
            and 200 <= result.status < 300
            and _looks_like_html(result)
        ):
            scan = _scan_html(result.body)
            resolution_base = result.final_url or candidate.canonical_url
            for href in scan.links:
                if len(candidate_set.candidates) >= limits.max_discovered:
                    break  # graph discovery cap
                resolved = resolve_link(resolution_base, href, base_url)
                if resolved is None:
                    continue
                if canonical_url(resolved) in candidate_set.candidates:
                    continue
                discovered = candidate_set.add(
                    resolved, "link_graph", candidate.depth + 1
                )
                if discovered is None:
                    continue
                if on_discovered is None:
                    queue.append((discovered, discovered))
                    continue
                discovered_ref = await on_discovered(discovered)
                if discovered_ref is not None:
                    queue.append((discovered, discovered_ref))
    return fetched

