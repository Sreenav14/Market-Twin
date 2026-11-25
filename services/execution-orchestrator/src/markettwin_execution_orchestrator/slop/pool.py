"""Parallel page-claim pool for slop runs (doc 18 section 8, S1).

The pool moves pages and results; it contains no slop judgement.
Lanes claim pages in queue order from a shared ClaimLedger, run the
caller's per-page procedure against their own browser context, and
hand every record to the caller's absorber - the single writer of
run state (I4). The pool owns the two failure-isolation mechanisms
that are scoped below the run: the per-lane stall guard (section
10.2) and the host circuit-breaker (section 10.4). The worker-level
stall watchdog is untouched by design: it keys on run events, and
the absorber keeps those flowing while any lane works.
"""

import asyncio
import time

from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlsplit

# Doc 18 section 12 values ([J] = judgement starting values, tuned
# on gate evidence). Lane counts are module constants in this build;
# the values actually used are recorded in the run snapshot.
SLOP_LANE_COUNT = 4  # [J] default lanes for slop
MAX_LANE_COUNT = 8  # [J] hard ceiling regardless of configuration
LANE_STALL_SECONDS = 420  # [J] 2 x traversal budget + 60 s margin
LANE_CHECK_SECONDS = 30  # [J] mirrors the worker watchdog's cadence
RATE_LIMIT_TRIP_COUNT = 3  # [J] 429/503 count that trips the breaker
RATE_LIMIT_WINDOW_SECONDS = 60  # [J] breaker counting window
RATE_LIMIT_BACKOFF_BASE_SECONDS = 30  # [J] first pause; doubles per trip
RATE_LIMIT_BACKOFF_MAX_SECONDS = 240  # [J] pause ceiling

# Bounded teardown for a lane close (the F5 shape): a dead lane
# browser can never wedge pool shutdown.
LANE_CLOSE_TIMEOUT_SECONDS = 30

_IDLE_POLL_SECONDS = 0.05
_LANE_CAUSES = frozenset({
    "browser_action", "browser_policy", "browser_session", "browser_timeout",
    "lane_error", "lane_watchdog", "session_factory",
})


def safe_lane_cause(site: str) -> str:
    return site if site in _LANE_CAUSES else "lane_died"


class LaneDiedError(Exception):
    """The lane's browser context died mid-page (target closed,
    context disposed). The page is attempted-failed, the lane is
    retired, and the pool continues at N-1 lanes (section 10.1)."""

    def __init__(self, site: str) -> None:
        super().__init__(site)
        self.site = site


class PoolExhaustedError(RuntimeError):
    """Every lane retired while unclaimed work remained."""

    def __init__(self, retired_lanes: dict[int, str]) -> None:
        super().__init__("All slop lanes retired while pages remained uninspected.")
        self.retired_lanes = retired_lanes


class SlopPersistenceError(RuntimeError):
    """A shared writer failed, so further lane results cannot be trusted."""


class SlopBudgetReached(Exception):
    """The desktop scan stopped admitting and working on browser claims."""


@dataclass
class PageClaim:
    """One page handed to one lane. Claims are issued in queue
    order; claim_seq is the run's recorded order, used wherever
    ordering must be deterministic (section 9.2)."""

    url: str
    claimed_by: int
    claimed_at: float
    attempt: int
    claim_seq: int


class ClaimLedger:
    """The run's queue/visited structures made claim-aware (section
    8.3) - not a second queue. The absorber owns the instance; the
    pool claims through it. All methods are synchronous: mutations
    are atomic between awaits on the event loop."""

    def __init__(self, *, canonical: Callable[[str], str], rotate_routes: bool = False) -> None:
        self._canonical = canonical
        self._rotate_routes = rotate_routes
        self._sections: OrderedDict[tuple[str, str], OrderedDict[tuple[str, str], deque[str]]] = OrderedDict()
        self._pending_keys: set[str] = set()
        self._visited: set[str] = set()
        self._in_flight: dict[int, PageClaim] = {}
        self._attempts: dict[str, int] = {}
        self._next_seq = 0

    # -- queue construction (seeding / resume) --
    def seed(self, urls: list[str]) -> None:
        self._sections.clear()
        self._pending_keys.clear()
        for url in urls:
            key = self._canonical(url)
            if key not in self._pending_keys:
                self._append(url, key)

    def _append(self, url: str, key: str, *, front: bool = False) -> None:
        parts = urlsplit(url)
        section = (parts.netloc, parts.path.strip("/").partition("/")[0])
        fragment = parts.fragment.partition("?")[0] if parts.fragment.startswith(("/", "!/")) else ""
        route = (parts.path or "/", fragment) if self._rotate_routes else ("", "")
        routes = self._sections.setdefault(section, OrderedDict())
        queue = routes.setdefault(route, deque())
        if front:
            queue.appendleft(url)
            routes.move_to_end(route, last=False)
            self._sections.move_to_end(section, last=False)
        else:
            queue.append(url)
            if self._rotate_routes and parts.path.strip("/") == section[1]:
                routes.move_to_end(route, last=False)
        self._pending_keys.add(key)

    def set_visited(self, canonical_keys) -> None:
        self._visited = set(canonical_keys)

    # -- queue growth (absorber-side; section 8.4 semantics) --
    def is_known(self, url: str) -> bool:
        key = self._canonical(url)
        return key in self._visited or key in self._pending_keys

    def enqueue(self, url: str) -> bool:
        key = self._canonical(url)
        if key in self._visited or key in self._pending_keys:
            return False
        self._append(url, key)
        return True

    # -- claims --
    def claim_next(self, lane_id: int) -> Optional[PageClaim]:
        while self._sections:
            section, routes = self._sections.popitem(last=False)
            route, urls = routes.popitem(last=False)
            url = urls.popleft()
            if urls:
                routes[route] = urls
            if routes:
                self._sections[section] = routes
            key = self._canonical(url)
            self._pending_keys.remove(key)
            if key in self._visited:
                continue
            self._visited.add(key)
            self._next_seq += 1
            self._attempts[key] = self._attempts.get(key, 0) + 1
            claim = PageClaim(
                url=url, claimed_by=lane_id, claimed_at=time.time(),
                attempt=self._attempts[key], claim_seq=self._next_seq,
            )
            self._in_flight[claim.claim_seq] = claim
            return claim
        return None

    def release(self, claim: PageClaim) -> None:
        """A claimed-but-not-started page returns to the queue
        unvisited (section 10.1)."""
        if self._in_flight.pop(claim.claim_seq, None) is None:
            return
        key = self._canonical(claim.url)
        self._visited.discard(key)
        self._append(claim.url, key, front=True)

    def finish(self, claim: PageClaim) -> bool:
        return self._in_flight.pop(claim.claim_seq, None) is not None

    # -- state reads --
    @property
    def pending_urls(self) -> list[str]:
        return [url for routes in self._sections.values() for urls in routes.values() for url in urls]

    @property
    def visited_keys(self) -> set[str]:
        return set(self._visited)

    @property
    def in_flight_claims(self) -> list[PageClaim]:
        return [self._in_flight[seq] for seq in sorted(self._in_flight)]

    @property
    def claims_issued(self) -> int:
        return self._next_seq

    def work_remaining(self) -> bool:
        return bool(self._sections or self._in_flight)


class HostCircuitBreaker:
    """One host-level breaker shared by all lanes (section 10.4).
    Page records carry load outcomes; the absorber reports them here
    (single-threaded counting, no race). The pool owns the pause:
    while paused, no lane claims."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: deque = deque()
        self._trips = 0
        self._paused_until = 0.0

    def note_outcome(self, status: Optional[int]) -> float:
        """Record one page-load outcome. Returns the pause seconds
        when this outcome trips the breaker, else 0."""
        now = self._clock()
        if status in (429, 503):
            while self._hits and now - self._hits[0] > RATE_LIMIT_WINDOW_SECONDS:
                self._hits.popleft()
            self._hits.append(now)
            if len(self._hits) >= RATE_LIMIT_TRIP_COUNT and now >= self._paused_until:
                self._trips += 1
                pause = min(
                    RATE_LIMIT_BACKOFF_BASE_SECONDS * (2 ** (self._trips - 1)),
                    RATE_LIMIT_BACKOFF_MAX_SECONDS,
                )
                self._paused_until = now + pause
                # The pause is the response to these hits; counting
                # them again would re-trip on the first post-pause
                # outcome. A fresh window starts with the pause.
                self._hits.clear()
                return pause
            return 0
        if status is not None:
            # A completed load that was not rate-limited resets the
            # backoff doubling.
            self._trips = 0
        return 0

    def paused_remaining(self) -> float:
        return max(0.0, self._paused_until - self._clock())

    @property
    def paused_until(self) -> float:
        return self._paused_until

    @property
    def trips(self) -> int:
        return self._trips


@dataclass
class _LaneState:
    lane_id: int
    last_progress: float
    current_claim: Optional[PageClaim] = None
    session: Any = None
    watchdog_fired: bool = False
    retired_reason: Optional[str] = None
    replacement_used: bool = False


@dataclass
class PoolResult:
    stopped: bool
    drained: bool
    retired_lanes: dict[int, str]


class LanePool:
    """Spawns lane_count lane tasks plus the lane supervisor;
    run() returns when the queue is drained and all lanes are idle,
    or when the caller's stop condition ends the crawl (section
    8.3). Constructed with the lane factory, the claim source, the
    absorber callbacks, and section 12's constants (injectable for
    tests)."""

    def __init__(
        self,
        *,
        lane_count: int,
        session_factory: Callable[[int], Awaitable[Any]],
        process_page: Callable[..., Awaitable[None]],
        claim_next: Callable[[int], Awaitable[Optional[PageClaim]]],
        work_remaining: Callable[[], bool],
        should_stop: Callable[[], bool],
        complete_claim: Callable[[PageClaim], Awaitable[None]],
        fail_claim: Callable[..., Awaitable[None]],
        release_claim: Callable[[PageClaim], Awaitable[None]],
        breaker: Optional[HostCircuitBreaker] = None,
        on_event: Optional[Callable[..., Awaitable[None]]] = None,
        work_paused: Optional[Callable[[], bool]] = None,
        replace_browser_sessions: bool = False,
        clock: Callable[[], float] = time.monotonic,
        stall_seconds: float = LANE_STALL_SECONDS,
        check_seconds: float = LANE_CHECK_SECONDS,
    ) -> None:
        self._lane_count = max(1, min(int(lane_count), MAX_LANE_COUNT))
        self._session_factory = session_factory
        self._process_page = process_page
        self._claim_next = claim_next
        self._work_remaining = work_remaining
        self._should_stop = should_stop
        self._complete_claim = complete_claim
        self._fail_claim = fail_claim
        self._release_claim = release_claim
        self._breaker = breaker if breaker is not None else HostCircuitBreaker(clock=clock)
        self._on_event = on_event
        self._work_paused = work_paused
        self._replace_browser_sessions = replace_browser_sessions
        self._clock = clock
        self._stall_seconds = stall_seconds
        self._check_seconds = check_seconds
        self._lanes: dict[int, _LaneState] = {}
        self._pause_announced_until = 0.0

    @property
    def breaker(self) -> HostCircuitBreaker:
        return self._breaker

    @property
    def lane_count(self) -> int:
        return self._lane_count

    def note_progress(self, lane_id: int) -> None:
        lane = self._lanes.get(lane_id)
        if lane is not None:
            lane.last_progress = self._clock()

    async def run(self) -> PoolResult:
        now = self._clock()
        self._lanes = {
            lane_id: _LaneState(lane_id=lane_id, last_progress=now)
            for lane_id in range(self._lane_count)
        }
        tasks = [
            asyncio.create_task(self._lane_loop(lane_id))
            for lane_id in self._lanes
        ]
        supervisor = asyncio.create_task(self._supervise(tasks))
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        finally:
            supervisor.cancel()
            try:
                await supervisor
            except asyncio.CancelledError:
                pass
        failed = {
            lane.lane_id: lane.retired_reason for lane in self._lanes.values()
            if lane.retired_reason is not None
        }
        if len(failed) == self._lane_count and self._work_remaining():
            raise PoolExhaustedError(failed)
        return PoolResult(
            stopped=self._should_stop(),
            drained=not self._work_remaining(),
            retired_lanes=failed,
        )

    async def _record_retirement(
        self, lane: _LaneState, claim: PageClaim, *, reason: str, phase: str,
    ) -> None:
        lane.retired_reason = reason
        if self._on_event is not None:
            await self._on_event("slop.lane.retired", {
                "lane_id": lane.lane_id, "claim_seq": claim.claim_seq,
                "cause": reason, "phase": phase,
                "remaining_lanes": sum(item.retired_reason is None for item in self._lanes.values()),
                "replacement_scheduled": False,
            })

    async def _lane_loop(self, lane_id: int) -> None:
        lane = self._lanes[lane_id]
        try:
            while True:
                if self._should_stop():
                    return
                pause = self._breaker.paused_remaining()
                if pause > 0:
                    if self._breaker.paused_until != self._pause_announced_until:
                        self._pause_announced_until = self._breaker.paused_until
                        if self._on_event is not None:
                            await self._on_event(
                                "slop.rate_limit.pause",
                                {"pause_seconds": round(pause, 1),
                                 "trips": self._breaker.trips,
                                 "reason": "rate_limited"},
                            )
                    await asyncio.sleep(min(pause, 0.25))
                    continue
                claim = await self._claim_next(lane_id)
                if claim is None:
                    if not self._work_remaining():
                        return
                    await asyncio.sleep(_IDLE_POLL_SECONDS)
                    continue
                lane.current_claim = claim
                self.note_progress(lane_id)
                if lane.session is None:
                    try:
                        lane.session = await self._session_factory(lane_id)
                    except asyncio.CancelledError:
                        if not lane.watchdog_fired:
                            raise
                        await self._release_claim(claim)
                        lane.current_claim = None
                        await self._record_retirement(lane, claim, reason="lane_watchdog", phase="startup")
                        return
                    except SlopPersistenceError:
                        raise
                    except SlopBudgetReached:
                        await self._release_claim(claim)
                        lane.current_claim = None
                        return
                    except Exception:
                        await self._release_claim(claim)
                        lane.current_claim = None
                        await self._record_retirement(lane, claim, reason="session_factory", phase="startup")
                        return
                try:
                    await self._process_page(
                        claim, lane.session,
                        lambda: self.note_progress(lane_id),
                    )
                except LaneDiedError as error:
                    await self._fail_claim(
                        claim, site=error.site, lane_id=lane_id)
                    lane.current_claim = None
                    if (
                        self._replace_browser_sessions
                        and error.site == "browser_session"
                        and not lane.replacement_used
                        and not self._should_stop()
                        and self._work_remaining()
                        and await self._close_session(lane)
                    ):
                        lane.replacement_used = True
                        if self._on_event is not None:
                            await self._on_event("slop.lane.replacement_scheduled", {
                                "lane_id": lane_id, "claim_seq": claim.claim_seq,
                                "cause": "browser_session",
                            })
                        continue
                    await self._record_retirement(lane, claim, reason=safe_lane_cause(error.site), phase="inspection")
                    return
                except asyncio.CancelledError:
                    if lane.watchdog_fired:
                        await self._fail_claim(
                            claim, site="lane_watchdog", lane_id=lane_id)
                        lane.current_claim = None
                        await self._record_retirement(lane, claim, reason="lane_watchdog", phase="inspection")
                        return
                    raise
                except SlopPersistenceError:
                    raise
                except SlopBudgetReached:
                    await self._release_claim(claim)
                    lane.current_claim = None
                    return
                except Exception:
                    await self._fail_claim(
                        claim, site="lane_error", lane_id=lane_id)
                    lane.current_claim = None
                    await self._record_retirement(lane, claim, reason="lane_error", phase="inspection")
                    return
                await self._complete_claim(claim)
                lane.current_claim = None
                self.note_progress(lane_id)
        finally:
            await self._close_session(lane)

    async def _close_session(self, lane: _LaneState) -> bool:
        session, lane.session = lane.session, None
        if session is not None:
            try:
                async with asyncio.timeout(LANE_CLOSE_TIMEOUT_SECONDS):
                    await session.close()
            except Exception:
                return False
        return True

    async def _supervise(self, tasks: list) -> None:
        """Lane stall guard (section 10.2): a lane silent past the
        stall bound WHILE THE RUN IS OTHERWISE ACTIVE is cancelled
        and retired. A lane silent because the whole run is stalled
        is the worker watchdog's case, never this guard's."""
        while True:
            await asyncio.sleep(self._check_seconds)
            now = self._clock()
            if self._work_paused is not None and self._work_paused():
                for lane in self._lanes.values():
                    lane.last_progress = now
                continue
            active = [
                lane for lane in self._lanes.values()
                if lane.retired_reason is None
            ]
            if len(active) < 2:
                continue
            progressed = [
                lane for lane in active
                if now - lane.last_progress <= self._stall_seconds
            ]
            if not progressed:
                continue
            for lane in active:
                if lane.current_claim is None:
                    continue
                if now - lane.last_progress > self._stall_seconds:
                    lane.watchdog_fired = True
                    tasks[lane.lane_id].cancel()
