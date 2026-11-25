"""Census-lite: the code-only denominator builder for one application target.

Phase 1a (doc 14 sections 6.2-6.4). Collects candidate URLs from robots +
sitemaps, route-table/bundle extraction, and the *unrendered* link graph;
canonicalises and route-pattern-induces them into denominator rows; then
fetches every row once and assigns it a named disposition from the section
6.4 decision table. No browser, no model calls (spec C1): the engine is
built around an injectable fetch seam so tests run against a fake site.

Persistence goes through the map repository's engine-facing surface
(``insert_pages`` / ``update_disposition`` / ``save_progress``); rows are
created BEFORE any disposition fetching, so an aborted job leaves a truthful
partial map (incremental publish).
"""


import asyncio
import hashlib
import ipaddress
import logging
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit
from uuid import UUID

import httpx
from markettwin_shared.app_map_common import (
    WALL_TEXT_MARKERS,
    canonical_url,
    has_wall_markers,
    is_login_path,
    route_pattern_for,
)
from markettwin_shared.census_sources import (
    CENSUS_BUNDLE_MAX_FILES,
    CENSUS_GRAPH_MAX_DEPTH,
    CENSUS_GRAPH_MAX_DISCOVERED,
    CENSUS_MAX_URLS,
    CENSUS_SITEMAP_MAX_BYTES,
    CENSUS_SITEMAP_MAX_DEPTH,
    PATTERN_EXEMPLAR_CAP,
    SOURCE_KINDS,
    CandidateSet,
    CensusCandidate,
    CensusFetchError,
    CollectionLimits,
    FetchCallable,
    FetchHop,
    FetchResult,
    _response_content_type,
    _scan_html,
    collect_sources,
    induce_patterns,
    traverse_link_graph,
)

from markettwin_control_api.knowledge.map_repository import (
    DispositionUpdate,
    InsertedPage,
    NewPage,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CensusCandidate",
    "CensusFetchError",
    "CensusReport",
    "CensusStore",
    "Disposition",
    "FetchCallable",
    "FetchHop",
    "FetchResult",
    "HttpxCensusFetcher",
    "build_census",
    "classify_disposition",
    "default_census_config",
    "induce_patterns",
    "public_url",
    "same_site_link",
    "validate_link_target",
]


# Engine constants (doc 14 section 8; [J] = judgement starting value).
# The collection limits (CENSUS_MAX_URLS, CENSUS_GRAPH_MAX_DISCOVERED,
# CENSUS_GRAPH_MAX_DEPTH, CENSUS_SITEMAP_MAX_DEPTH, CENSUS_BUNDLE_MAX_FILES,
# CENSUS_SITEMAP_MAX_BYTES, PATTERN_EXEMPLAR_CAP) live in
# markettwin_shared.census_sources since Phase 4 (doc 23 section 6.6) and
# are imported above; the fetcher/classifier values below stay local.
CENSUS_FETCH_TIMEOUT_SECONDS = 15  # [J]
CENSUS_FETCH_MAX_BYTES = 2_000_000  # [J]
CENSUS_USER_AGENT = "MarketTwinCensus/1a"
WALL_SCAN_MAX_CHARS = 65_536  # doc 14 section 4.3

_REDIRECT_STATUSES = (301, 302, 303, 307, 308)


def default_census_config() -> dict[str, Any]:
    """The section 8 values a build runs with; recorded on the map row so a
    map is reproducible against its own configuration."""
    return {
        "census_max_urls": CENSUS_MAX_URLS,
        "census_graph_max_discovered": CENSUS_GRAPH_MAX_DISCOVERED,
        "census_graph_max_depth": CENSUS_GRAPH_MAX_DEPTH,
        "census_sitemap_max_depth": CENSUS_SITEMAP_MAX_DEPTH,
        "census_bundle_max_files": CENSUS_BUNDLE_MAX_FILES,
        "census_fetch_timeout_seconds": CENSUS_FETCH_TIMEOUT_SECONDS,
        "census_fetch_max_bytes": CENSUS_FETCH_MAX_BYTES,
        "census_sitemap_max_bytes": CENSUS_SITEMAP_MAX_BYTES,
        "pattern_exemplar_cap": PATTERN_EXEMPLAR_CAP,
        "census_user_agent": CENSUS_USER_AGENT,
    }


# Public-target validation and same-site link scoping (spec C5):
# every URL the census fetches or follows passes validate_link_target,
# and traverse_link_graph resolves out-links through same_site_link.

def validate_link_target(url: str) -> str:
    """Reject unsafe targets before any DNS lookup or connection."""
    url = url.strip()
    _scheme, host, _port = public_url(url)
    lowered = host.lower().rstrip(".")
    if (
        lowered in {"localhost", "metadata", "metadata.google.internal"}
        or lowered.endswith(".localhost")
        or lowered.endswith(".local")
    ):
        raise ValueError("Linked sources must resolve only to public internet addresses.")
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Linked sources must resolve only to public internet addresses.")
    return url


def public_url(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Enter a public HTTP or HTTPS link without embedded credentials.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port != (443 if parsed.scheme == "https" else 80):
        raise ValueError("Linked sources must use the standard HTTP or HTTPS port.")
    return parsed.scheme, parsed.hostname, port


def same_site_link(base: str, href: str, origin: str) -> str | None:
    candidate = urljoin(base, href)
    parsed = urlsplit(candidate)
    root = urlsplit(origin)
    if (parsed.scheme, parsed.netloc) != (root.scheme, root.netloc):
        return None
    if any(word in parsed.path.lower().split("/") for word in (
        "logout", "signout", "delete", "remove", "checkout", "purchase",
    )):
        return None
    # Preserve SPA hash routes, while ordinary document anchors are one page.
    fragment = parsed.fragment if parsed.fragment.startswith("/") else ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, fragment))


class HttpxCensusFetcher:
    """Single-attempt fetcher: GET only, redirects followed manually (at
    most 5 hops) with ``validate_link_target`` run on every hop (spec C5),
    body capped, HTTPS verification always on. Retry policy lives in the
    engine, not here, so tests can count seam calls."""

    def __init__(
        self,
        *,
        timeout_seconds: float = CENSUS_FETCH_TIMEOUT_SECONDS,
        max_bytes: int = CENSUS_FETCH_MAX_BYTES,
        user_agent: str = CENSUS_USER_AGENT,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._user_agent = user_agent
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "HttpxCensusFetcher":
        self._client = self._new_client()
        return self

    async def __aexit__(self, *_args: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout_seconds, connect=5.0),
            follow_redirects=False,
            trust_env=False,
        )

    async def __call__(self, url: str) -> FetchResult:
        if self._client is not None:
            return await self._fetch(self._client, url)
        async with self._new_client() as client:
            return await self._fetch(client, url)

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> FetchResult:
        chain: list[FetchHop] = []
        current = url
        for hop in range(6):  # the request itself plus up to 5 redirects
            try:
                validate_link_target(current)
                parsed = httpx.URL(current)
                addresses = await asyncio.to_thread(
                    socket.getaddrinfo, parsed.host, parsed.port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
                ips = [str(item[4][0]) for item in addresses]
                if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
                    raise ValueError("Linked sources must resolve only to public internet addresses.")
            except ValueError:
                return FetchResult(
                    requested_url=url,
                    final_url=chain[-1].url if chain else None,
                    status=chain[-1].status if chain else None,
                    headers={},
                    body=b"",
                    redirect_chain=tuple(chain),
                    blocked_hop=True,
                )
            except OSError as exc:
                raise CensusFetchError("DNS resolution failed") from exc
            try:
                # Dial the checked address, retaining the original Host and TLS
                # identity. DNS cannot change between validation and connection.
                pinned = parsed.copy_with(host=ips[0])
                async with client.stream(
                    "GET", pinned,
                    headers={"User-Agent": self._user_agent, "Host": parsed.netloc.decode("ascii")},
                    extensions={"sni_hostname": parsed.host},
                ) as response:
                    body = await self._read_capped(response)
                    status = response.status_code
                    headers = {
                        key.lower(): value for key, value in response.headers.items()
                    }
            except httpx.RequestError as exc:
                raise CensusFetchError(f"{type(exc).__name__}: {exc}") from exc
            location = headers.get("location")
            if status in _REDIRECT_STATUSES and location:
                if hop == 5:
                    return FetchResult(
                        requested_url=url,
                        final_url=current,
                        status=status,
                        headers=headers,
                        body=body,
                        redirect_chain=tuple(chain),
                        error="too many redirects",
                    )
                chain.append(FetchHop(url=current, status=status))
                current = urljoin(current, location)
                continue
            return FetchResult(
                requested_url=url,
                final_url=current,
                status=status,
                headers=headers,
                body=body,
                redirect_chain=tuple(chain),
            )
        raise AssertionError("redirect loop is bounded by construction")

    async def _read_capped(self, response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            chunks.append(chunk)
            total += len(chunk)
            if total >= self._max_bytes:
                break
        return b"".join(chunks)[: self._max_bytes]



@dataclass(frozen=True)
class Disposition:
    crawl_status: str
    http_status: int | None
    redirect_target: str | None
    content_type: str | None
    title: str | None
    html_sha256: str | None
    requires_auth: bool
    confidence: str
    last_verified_at: datetime | None

    def update_for(self, page_id: UUID) -> DispositionUpdate:
        return DispositionUpdate(
            page_id=page_id,
            crawl_status=self.crawl_status,
            http_status=self.http_status,
            redirect_target=self.redirect_target,
            content_type=self.content_type,
            title=self.title,
            html_sha256=self.html_sha256,
            requires_auth=self.requires_auth,
            confidence=self.confidence,
            last_verified_at=self.last_verified_at,
        )




def _wall_signals(result: FetchResult, body_text_lower: str) -> bool:
    server = result.headers.get("server", "").lower()
    if "cloudflare" in server or "datadome" in server:
        return True
    if "x-datadome" in result.headers:
        return True
    return has_wall_markers(body_text_lower)


def classify_disposition(
    *, requested_canonical: str, result: FetchResult, now: datetime
) -> Disposition:
    """The disposition decision table of doc 14 section 6.4, in order."""
    status = result.status
    received = status is not None
    body = result.body or b""
    final_canonical = canonical_url(result.final_url) if result.final_url else None
    redirect_target = (
        final_canonical
        if result.redirect_chain
        and final_canonical is not None
        and final_canonical != requested_canonical
        else None
    )
    content_type = _response_content_type(result.headers) if received else None
    title = _scan_html(body).title if received and body else None
    fields: dict[str, Any] = {
        "http_status": status if received else None,
        "redirect_target": redirect_target,
        "content_type": content_type,
        "title": title,
        "html_sha256": hashlib.sha256(body).hexdigest() if received else None,
        "requires_auth": False,
        "last_verified_at": now,  # rules 3-12: an actual fetch attempt
    }
    if result.blocked_hop:  # rule 3
        return Disposition(crawl_status="fetch_error", confidence="low", **fields)
    if result.error is not None:  # rule 4 (network failure, post-retry)
        return Disposition(crawl_status="fetch_error", confidence="low", **fields)
    if status == 401:  # rule 5
        return Disposition(
            crawl_status="blocked_auth", confidence="medium",
            **{**fields, "requires_auth": True},
        )
    body_text_lower = body.decode("utf-8", "replace")[:WALL_SCAN_MAX_CHARS].lower()
    if status in (403, 429) and _wall_signals(result, body_text_lower):  # rule 6
        return Disposition(crawl_status="blocked_wall", confidence="medium", **fields)
    if status in (404, 410):  # rule 7
        return Disposition(crawl_status="gone", confidence="medium", **fields)
    if (
        result.redirect_chain
        and final_canonical is not None
        and is_login_path(final_canonical)
    ):  # rule 8
        return Disposition(
            crawl_status="blocked_auth", confidence="medium",
            **{**fields, "requires_auth": True},
        )
    if (
        status is not None
        and 200 <= status < 300
        and final_canonical is not None
        and final_canonical != requested_canonical
        and is_login_path(final_canonical)
    ):  # rule 9
        return Disposition(
            crawl_status="blocked_auth", confidence="medium",
            **{**fields, "requires_auth": True},
        )
    if (
        status is not None
        and 200 <= status < 300
        and has_wall_markers(body_text_lower)
        and title is not None
        and any(marker in title.lower() for marker in WALL_TEXT_MARKERS)
    ):  # the 2xx checkpoint page, checked between rules 9 and 10
        return Disposition(crawl_status="blocked_wall", confidence="medium", **fields)
    if status is not None and 200 <= status < 300 and redirect_target is not None:
        return Disposition(crawl_status="redirect", confidence="medium", **fields)
    if status is not None and 200 <= status < 300:  # rule 11
        return Disposition(crawl_status="fetch_ok", confidence="high", **fields)
    return Disposition(crawl_status="fetch_error", confidence="low", **fields)



class CensusStore(Protocol):
    """The repository surface the engine writes through."""

    async def insert_pages(
        self, app_map: Any, pages: list[NewPage]
    ) -> list[InsertedPage]: ...

    async def update_disposition(self, update: DispositionUpdate) -> None: ...

    async def save_progress(
        self,
        map_id: UUID,
        *,
        census_metrics: dict[str, Any],
        pattern_stats: dict[str, Any],
    ) -> None: ...


@dataclass(frozen=True)
class CensusReport:
    census_metrics: dict[str, Any]
    pattern_stats: dict[str, dict[str, int]]
    overflow_count: int
    rows_created: int
    fetched: int




async def build_census(
    repository: CensusStore,
    app_map: Any,
    *,
    fetch: FetchCallable,
    sitemap_fetch: FetchCallable | None = None,
    retry_delay: float = 1.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> CensusReport:
    """Run census stages 1-3 for one ``building`` map row.

    Collection -- stages 1a/1b plus the link-graph traversal -- is the
    shared implementation in ``markettwin_shared.census_sources``
    (doc 23 section 6.6, one implementation); this function layers
    census's disposition table on top through the traversal's hooks,
    so the engine's observable behaviour is unchanged.

    ``app_map`` carries id/workspace_id/application_id/target_id/base_url and
    the census_config the build was created with. Job-level exceptions
    propagate (the processor records them per section 11); the stage ledger
    is persisted from a ``finally`` block so partial progress stays truthful.
    """
    config: dict[str, Any] = default_census_config()
    config.update(getattr(app_map, "census_config", None) or {})
    limits = CollectionLimits(
        max_urls=int(config["census_max_urls"]),
        max_discovered=int(config["census_graph_max_discovered"]),
        max_depth=int(config["census_graph_max_depth"]),
        max_sitemap_depth=int(config["census_sitemap_max_depth"]),
        max_bundle_files=int(config["census_bundle_max_files"]),
        exemplar_cap=int(config["pattern_exemplar_cap"]),
    )
    base_url = app_map.base_url
    candidate_set = CandidateSet(
        base_canonical=canonical_url(base_url), validate=validate_link_target
    )
    research_url = config.get("skill_research_url")
    if isinstance(research_url, str):
        candidate_set.add(research_url, "link_graph", 0)
    facts = await collect_sources(
        candidate_set,
        base_url=base_url,
        fetch=fetch,
        sitemap_fetch=sitemap_fetch,
        limits=limits,
        retry_delay=retry_delay,
        sleep=sleep,
    )
    robots_status = facts.robots_status

    # --- Stage 2: canonicalisation + induction, rows before fetching -----
    rows, pattern_stats, overflow = induce_patterns(
        list(candidate_set.candidates.values()),
        exemplar_cap=limits.exemplar_cap,
        max_urls=limits.max_urls,
    )
    inserted = await repository.insert_pages(
        app_map,
        [
            NewPage(
                canonical_url=row.canonical_url,
                route_pattern=row.route_pattern,
                source_kinds=row.source_kinds,
            )
            for row in rows
        ],
    )
    rows_created = len(inserted)

    # --- Stage 3: disposition fetching, link discovery interleaved --------
    by_status: dict[str, int] = {}
    fetched = 0

    def current_metrics() -> dict[str, Any]:
        return {
            "robots_status": robots_status,
            "sources_total_urls": {
                kind: len(candidate_set.source_sets[kind]) for kind in SOURCE_KINDS
            },
            "rows_created": rows_created,
            "fetched": fetched,
            "by_status": dict(by_status),
            "overflow_count": overflow,
            "discovered": len(candidate_set.candidates),
        }

    async def save_progress() -> None:
        await repository.save_progress(
            app_map.id,
            census_metrics=current_metrics(),
            pattern_stats=pattern_stats,
        )

    async def on_disallowed(candidate: CensusCandidate, page_id: UUID) -> None:
        await repository.update_disposition(
            DispositionUpdate(
                page_id=page_id,
                crawl_status="out_of_scope",
                http_status=None,
                redirect_target=None,
                content_type=None,
                title=None,
                html_sha256=None,
                requires_auth=False,
                confidence="low",
                last_verified_at=None,
            )
        )
        by_status["out_of_scope"] = by_status.get("out_of_scope", 0) + 1

    async def on_fetch(
        candidate: CensusCandidate, page_id: UUID, result: FetchResult
    ) -> None:
        nonlocal fetched
        fetched += 1  # counted here so an abort leaves a truthful count
        disposition = classify_disposition(
            requested_canonical=candidate.canonical_url,
            result=result,
            now=datetime.now(UTC),
        )
        await repository.update_disposition(disposition.update_for(page_id))
        by_status[disposition.crawl_status] = (
            by_status.get(disposition.crawl_status, 0) + 1
        )

    async def on_discovered(candidate: CensusCandidate) -> UUID | None:
        nonlocal rows_created, overflow
        pattern = route_pattern_for(candidate.canonical_url)
        stats = pattern_stats.setdefault(
            pattern, {"instances": 0, "exemplars": 0}
        )
        stats["instances"] += 1
        if stats["exemplars"] < limits.exemplar_cap and rows_created < limits.max_urls:
            new_pages = await repository.insert_pages(
                app_map,
                [
                    NewPage(
                        canonical_url=candidate.canonical_url,
                        route_pattern=pattern,
                        source_kinds=("link_graph",),
                    )
                ],
            )
            stats["exemplars"] += 1
            rows_created += 1
            return new_pages[0].id
        if stats["exemplars"] >= limits.exemplar_cap:
            return None  # counted in pattern_stats, never queued (section 6.4)
        overflow += 1  # the row cap is the binding limit
        return None

    async def on_progress(count: int) -> None:
        await save_progress()

    try:
        await traverse_link_graph(
            candidate_set,
            fetch=fetch,
            robots=facts.robots,
            base_result=facts.base_result,
            base_url=base_url,
            initial=[
                (candidate_set.candidates[page.canonical_url], page.id)
                for page in inserted
            ],
            limits=limits,
            resolve_link=same_site_link,
            retry_delay=retry_delay,
            sleep=sleep,
            on_fetch=on_fetch,
            on_disallowed=on_disallowed,
            on_discovered=on_discovered,
            on_progress=on_progress,
        )
    finally:
        await save_progress()
    return CensusReport(
        census_metrics=current_metrics(),
        pattern_stats=pattern_stats,
        overflow_count=overflow,
        rows_created=rows_created,
        fetched=fetched,
    )
