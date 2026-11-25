"""Dispatch persisted app-map builds to the census engine, independently
of the UI. Each claim uses
a pinned connection, a ``pg_try_advisory_lock`` claim per map, sessions
bound to that connection, and the lock released in a ``finally`` block."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

from markettwin_database.models.knowledge import AppMap
from markettwin_shared.app_map_common import compute_inventory_gate
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from markettwin_control_api.config import Settings
from markettwin_control_api.knowledge.census import (
    CENSUS_FETCH_MAX_BYTES,
    CENSUS_FETCH_TIMEOUT_SECONDS,
    CENSUS_SITEMAP_MAX_BYTES,
    FetchCallable,
    HttpxCensusFetcher,
    build_census,
)
from markettwin_control_api.knowledge.map_repository import (
    MapRepository,
)

logger = logging.getLogger(__name__)

class CensusProcessor:
    def __init__(self, engine: AsyncEngine, settings: Settings) -> None:
        self.engine = engine
        self.settings = settings
        self._slots = settings.census_processor_slots
        self._poll_seconds = settings.census_poll_seconds
        self._orphan_minutes = settings.census_orphan_minutes

    def _repository_on(self, connection: AsyncConnection) -> MapRepository:
        return MapRepository(lambda: AsyncSession(connection, expire_on_commit=False))

    async def process_next(self) -> bool:
        repository = MapRepository(
            lambda: AsyncSession(self.engine, expire_on_commit=False)
        )
        await self.reap_orphans(repository)
        started_research = False
        for map_id in await repository.pending_link_research():
            _, started = await repository.start_harvest(map_id, only_unstarted=True)
            started_research = started_research or started
        for app_map in await repository.list_building(limit=10):
            if await self.process_map(app_map.id):
                return True
        return started_research

    async def process_map(self, map_id: UUID) -> bool:
        async with self._claim(map_id) as connection:
            if connection is None:
                return False
            await self._run(connection, map_id)
            return True

    @asynccontextmanager
    async def _claim(self, map_id: UUID) -> AsyncIterator[AsyncConnection | None]:
        # Pin a connection: session locks must never be left on a pooled connection.
        async with self.engine.connect() as connection:
            key = {"key": f"markettwin-census:{map_id}"}
            try:
                locked = await connection.scalar(
                    text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"), key
                )
                await connection.commit()
            except BaseException:
                await connection.invalidate()
                raise
            if not locked:
                yield None
                return
            try:
                yield connection
            finally:
                try:
                    await connection.rollback()
                    await connection.execute(
                        text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                        key,
                    )
                    await connection.commit()
                except BaseException:
                    # Discard the physical connection if shutdown/error prevents cleanup.
                    await connection.invalidate()
                    raise

    async def _run(self, connection: AsyncConnection, map_id: UUID) -> None:
        repository = self._repository_on(connection)
        app_map = await repository.get_map(map_id)
        if app_map is None or app_map.status != "building":
            return
        if await repository.count_pages_by_status(map_id):
            # The crawl rebuilds its in-memory queue from scratch. Reusing this
            # version would insert the same URLs into the persisted inventory.
            await repository.fail_map(
                map_id,
                failure_code="census_interrupted",
                failure_message="The map build was interrupted. Start a new build to retry.",
                failure_site="census_processor:_run",
                spend_seconds=max(0.0, (datetime.now(UTC) - app_map.started_at).total_seconds()),
            )
            return
        await self.run_build(repository, app_map)

    async def run_build(
        self,
        repository: MapRepository,
        app_map: AppMap,
        *,
        fetch: FetchCallable | None = None,
    ) -> None:
        """Run one build to a terminal state. A crash is recorded on the map
        row with the original error retained (doc 14 section 11) and never
        re-raised: a failed job must not block the queue."""
        # perf_counter, not monotonic: spend accounting needs sub-ms
        # resolution (Windows monotonic ticks are ~15 ms, which records
        # an honest 0.0 for fast builds and breaks T-C16's pin).
        started = time.perf_counter()
        try:
            if fetch is None:
                fetcher = HttpxCensusFetcher(
                    timeout_seconds=CENSUS_FETCH_TIMEOUT_SECONDS,
                    max_bytes=CENSUS_FETCH_MAX_BYTES,
                )
                sitemap_fetcher = HttpxCensusFetcher(
                    timeout_seconds=CENSUS_FETCH_TIMEOUT_SECONDS,
                    max_bytes=CENSUS_SITEMAP_MAX_BYTES,
                )
                async with fetcher, sitemap_fetcher:
                    report = await build_census(
                        repository,
                        app_map,
                        fetch=fetcher,
                        sitemap_fetch=sitemap_fetcher,
                    )
            else:
                report = await build_census(repository, app_map, fetch=fetch)
            counts = await repository.count_pages_by_status(app_map.id)
            gate = compute_inventory_gate(counts, report.overflow_count)
            await repository.apply_gate(
                app_map.id,
                gate=gate,
                spend_seconds=time.perf_counter() - started,
                census_metrics=report.census_metrics,
                pattern_stats=report.pattern_stats,
            )
        except Exception as exc:
            logger.exception("Census build failed for map %s", app_map.id)
            await repository.fail_map(
                app_map.id,
                failure_code=type(exc).__name__,
                failure_message=str(exc)[:2000],
                failure_site="census_processor:run_build",
                spend_seconds=time.perf_counter() - started,
            )

    async def reap_orphans(
        self, repository: MapRepository, *, now: datetime | None = None
    ) -> int:
        """Fail ``building`` rows older than the orphan window that have no
        live claim (their advisory lock is free). A live long-running build
        holds its lock and is never reaped (doc 14 section 6.5)."""
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(minutes=self._orphan_minutes)
        reaped = 0
        for app_map in await repository.list_stale_building(cutoff):
            async with self._claim(app_map.id) as connection:
                if connection is None:
                    continue
                claimed = self._repository_on(connection)
                current = await claimed.get_map(app_map.id)
                if current is None or current.status != "building" or current.started_at >= cutoff:
                    continue
                await claimed.fail_map(
                    app_map.id,
                    failure_code="census_orphaned",
                    failure_message=(
                        f"building exceeded {self._orphan_minutes} minutes "
                        "without a live claim"
                    ),
                    failure_site="census_processor:reap_orphans",
                    spend_seconds=max(0.0, (now - current.started_at).total_seconds()),
                )
                reaped += 1
        return reaped


async def run_census_processor(engine: AsyncEngine, settings: Settings) -> None:
    """Bounded dispatch slots; queued maps survive a restart and interrupted
    maps with partial inventory are failed. Started beside the ingestion
    processor with ``run_census_processor(database.engine, settings)``."""
    processor = CensusProcessor(engine, settings)

    async def dispatch() -> None:
        while True:
            try:
                if await processor.process_next():
                    continue
            except Exception:
                logger.exception("Could not dispatch census builds")
            await asyncio.sleep(processor._poll_seconds)

    async with asyncio.TaskGroup() as group:
        for _ in range(max(1, processor._slots)):
            group.create_task(dispatch())
