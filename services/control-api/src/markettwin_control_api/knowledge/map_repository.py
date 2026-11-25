"""Persistence and the deterministic inventory gate for application maps.

Phase 1a (doc 14): the map repository owns every write to
``knowledge.app_maps`` / ``knowledge.map_pages`` / ``knowledge.map_page_states``
and the pure inventory-gate computation of spec section 7. Sessions come from
an injected factory so the census processor can bind them to its advisory-lock
connection (the ingestion pattern) while API code passes the runtime factory.
"""

import logging
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from markettwin_database.models.knowledge import (
    AppMap,
    GraphAuditReport,
    MapConflict,
    MapElement,
    MapEvidenceObject,
    MapExpectation,
    MapExpectationEvent,
    MapField,
    MapForm,
    MapJourney,
    MapPage,
    MapPageState,
    MapPreflight,
    Skill,
    SkillUsageEvent,
    SkillVersion,
)
from markettwin_database.models.testing import TargetAuthorization
from markettwin_shared.app_map_common import (
    FRESHNESS_OUTCOMES,
    MAP_TTL_TRUST_DAYS,
    REACHABLE_STATUSES,
    GateResult,
    HarvestGateResult,
    check_skill_transition,
    compute_inventory_gate as compute_inventory_gate,
    compute_expectation_gate,
    compute_harvest_gate,
    expectation_coverage,
    expectation_verdict_eligible,
    skill_currency_check,
)
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

CENSUS_BUILDER_VERSION = "census-1a.1"
# The inventory gate itself (GateResult / compute_inventory_gate /
# GATE_RULE_ID / GATE_COVERAGE_THRESHOLD / REACHABLE_STATUSES /
# NAMED_STATUSES) lives in markettwin_shared.app_map_common since
# Phase 4 (doc 23 section 6.6, one implementation) and is imported
# below; this label stays because it names the applier, which is here.
GATE_FAILURE_SITE = "map_repository:compute_inventory_gate"
SNAPSHOT_MAP_PAGE_CAP = 2000  # [J] doc 14 section 8
SNAPSHOT_MAP_MAX_BYTES = 2_000_000  # [J] doc 16 section 11.1
EXPECTATIONS_SNAPSHOT_CAP = 500  # [J] doc 21 section 16
HARVEST_FAILURE_SITE = "map_repository:compute_harvest_gate"

@dataclass(frozen=True)
class NewPage:
    """One denominator row to create, with its default state."""

    canonical_url: str
    route_pattern: str
    source_kinds: tuple[str, ...]


@dataclass(frozen=True)
class InsertedPage:
    id: UUID
    canonical_url: str


@dataclass(frozen=True)
class DispositionUpdate:
    """The outcome of one census fetch, written back to its page row."""

    page_id: UUID
    crawl_status: str
    http_status: int | None
    redirect_target: str | None
    content_type: str | None
    title: str | None
    html_sha256: str | None
    requires_auth: bool
    confidence: str
    last_verified_at: datetime | None


@dataclass(frozen=True)
class HarvestExtras:
    """The section 10.1 summary's harvest block, pre-serialisation."""

    visited: int
    reachable: int
    blocked: int
    failed: int
    unprobed_budget: int
    enriched_groups: int
    template_groups: int
    spend_calls: int
    spend_tokens: int


@dataclass(frozen=True)
class MapSkillLine:
    """One row of the section 10.1 summary's skills list."""

    name: str
    lifecycle_status: str | None
    last_replay_result: str | None
    last_replay_at: datetime | None


def page_effective_url(page: MapPage) -> str:
    """The URL a run should visit for this page (doc 14 section 6.4)."""
    if page.crawl_status == "redirect" and page.redirect_target:
        return page.redirect_target
    return page.canonical_url


def harvest_metric_counts(
    harvest_metrics: Mapping[str, object] | None,
) -> tuple[int, int]:
    """(template_groups, enriched_groups) from the job's metrics ledger.

    Defensive by design (doc 16 section 11.1): the snapshot and summary
    readers must never fail on a partially written ledger, so any shape
    surprise reads as zero rather than raising.
    """
    if not isinstance(harvest_metrics, Mapping):
        return (0, 0)
    groups = harvest_metrics.get("template_groups")
    if not isinstance(groups, Mapping):
        return (0, 0)
    total = groups.get("groups")
    unenriched = groups.get("unenriched_groups")
    total_int = total if isinstance(total, int) else 0
    unenriched_int = len(unenriched) if isinstance(unenriched, list) else 0
    return (total_int, max(total_int - unenriched_int, 0))


class MapRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def create_build(
        self,
        *,
        workspace_id: UUID,
        application_id: UUID,
        target_id: UUID,
        base_url: str,
        census_config: dict[str, object],
    ) -> tuple[AppMap, bool]:
        """Get-or-create the single in-flight build for (application, target).

        Returns ``(map, created)``. An existing ``building`` row is returned
        with ``created=False`` (doc 14 section 6.1 idempotent create); the
        partial unique index is the backstop for the concurrent race.
        """
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    existing = (
                        await session.execute(
                            select(AppMap).where(
                                AppMap.application_id == application_id,
                                AppMap.target_id == target_id,
                                AppMap.status == "building",
                            )
                        )
                    ).scalars().first()
                    if existing is not None:
                        return existing, False
                    max_version = (
                        await session.execute(
                            select(func.max(AppMap.version_number)).where(
                                AppMap.application_id == application_id,
                                AppMap.target_id == target_id,
                            )
                        )
                    ).scalar()
                    row = AppMap(
                        id=uuid4(),
                        workspace_id=workspace_id,
                        application_id=application_id,
                        target_id=target_id,
                        version_number=(max_version or 0) + 1,
                        status="building",
                        base_url=base_url,
                        builder_version=CENSUS_BUILDER_VERSION,
                        census_config=census_config,
                        census_metrics={},
                        pattern_stats={},
                        gate_metrics={},
                        started_at=datetime.now(UTC),
                    )
                    session.add(row)
                    await session.flush()
                    return row, True
        except IntegrityError:
            # Lost the single-flight race: the winner's row is the build.
            async with self._session_factory() as session:
                existing = (
                    await session.execute(
                        select(AppMap).where(
                            AppMap.application_id == application_id,
                            AppMap.target_id == target_id,
                            AppMap.status == "building",
                        )
                    )
                ).scalars().first()
                if existing is None:
                    raise
                return existing, False

    async def get_map(self, map_id: UUID) -> AppMap | None:
        async with self._session_factory() as session:
            return await session.get(AppMap, map_id)

    async def list_building(self, limit: int = 10) -> list[AppMap]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AppMap)
                .where(AppMap.status == "building")
                .order_by(AppMap.started_at)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def list_stale_building(self, cutoff: datetime) -> list[AppMap]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AppMap).where(
                    AppMap.status == "building", AppMap.started_at < cutoff
                )
            )
            return list(result.scalars().all())

    async def latest_map(self, application_id: UUID, target_id: UUID) -> AppMap | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AppMap)
                .where(
                    AppMap.application_id == application_id,
                    AppMap.target_id == target_id,
                )
                .order_by(AppMap.version_number.desc())
                .limit(1)
            )
            return result.scalars().first()

    async def latest_ready_map(
        self, application_id: UUID, target_id: UUID
    ) -> AppMap | None:
        """Highest-version map a run may consume (doc 14 section 9.3)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(AppMap)
                .where(
                    AppMap.application_id == application_id,
                    AppMap.target_id == target_id,
                    AppMap.status == "ready",
                    AppMap.release_state.in_(("partial", "trusted")),
                )
                .order_by(AppMap.version_number.desc())
                .limit(1)
            )
            return result.scalars().first()

    async def insert_pages(
        self, app_map: AppMap, pages: list[NewPage]
    ) -> list[InsertedPage]:
        """Create denominator rows plus exactly one default state per row,
        in batches of 200 (doc 14 sections 5.4, 6.3)."""
        inserted: list[InsertedPage] = []
        for start in range(0, len(pages), 200):
            batch = pages[start:start + 200]
            async with self._session_factory() as session:
                async with session.begin():
                    for new_page in batch:
                        page_id = uuid4()
                        session.add(
                            MapPage(
                                id=page_id,
                                workspace_id=app_map.workspace_id,
                                application_id=app_map.application_id,
                                target_id=app_map.target_id,
                                app_map_id=app_map.id,
                                canonical_url=new_page.canonical_url,
                                route_pattern=new_page.route_pattern,
                                source_kinds=list(new_page.source_kinds),
                                crawl_status="census_incomplete",
                                requires_auth=False,
                                roles_seen=[],
                                source="census",
                                confidence="low",
                            )
                        )
                        session.add(
                            MapPageState(
                                id=uuid4(),
                                workspace_id=app_map.workspace_id,
                                application_id=app_map.application_id,
                                target_id=app_map.target_id,
                                app_map_id=app_map.id,
                                map_page_id=page_id,
                                state_key="default",
                                state_kind="default",
                                state_id=None,
                                element_signature=None,
                                form_signature=None,
                                source="census",
                                confidence="low",
                                last_verified_at=None,
                            )
                        )
                        inserted.append(
                            InsertedPage(id=page_id, canonical_url=new_page.canonical_url)
                        )
                    await session.flush()
        return inserted

    async def update_disposition(self, update: DispositionUpdate) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                page = await session.get(MapPage, update.page_id)
                if page is None:
                    return
                page.crawl_status = update.crawl_status
                page.http_status = update.http_status
                page.redirect_target = update.redirect_target
                page.content_type = update.content_type
                page.title = update.title
                page.html_sha256 = update.html_sha256
                page.requires_auth = update.requires_auth
                page.confidence = update.confidence
                page.last_verified_at = update.last_verified_at
                await session.flush()

    async def save_progress(
        self,
        map_id: UUID,
        *,
        census_metrics: dict[str, object],
        pattern_stats: dict[str, object],
    ) -> None:
        """Refresh the stage ledger on the map row (doc 14 section 6.4)."""
        async with self._session_factory() as session:
            async with session.begin():
                app_map = await session.get(AppMap, map_id)
                if app_map is None:
                    return
                app_map.census_metrics = dict(census_metrics)
                app_map.pattern_stats = dict(pattern_stats)
                await session.flush()

    async def count_pages_by_status(self, map_id: UUID) -> dict[str, int]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapPage.crawl_status, func.count())
                .where(MapPage.app_map_id == map_id)
                .group_by(MapPage.crawl_status)
            )
            return {status: count for status, count in result.all()}

    async def list_pages(
        self,
        map_id: UUID,
        *,
        crawl_status: str | None = None,
        route_pattern: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[MapPage]]:
        async with self._session_factory() as session:
            filters = [MapPage.app_map_id == map_id]
            if crawl_status is not None:
                filters.append(MapPage.crawl_status == crawl_status)
            if route_pattern is not None:
                filters.append(MapPage.route_pattern == route_pattern)
            total = (
                await session.execute(
                    select(func.count()).select_from(MapPage).where(*filters)
                )
            ).scalar_one()
            result = await session.execute(
                select(MapPage)
                .where(*filters)
                .order_by(MapPage.canonical_url)
                .limit(limit)
                .offset(offset)
            )
            return total, list(result.scalars().all())

    async def apply_gate(
        self,
        map_id: UUID,
        *,
        gate: GateResult,
        spend_seconds: float,
        census_metrics: dict[str, object],
        pattern_stats: dict[str, object],
    ) -> None:
        """Write the gate's release in one update (doc 14 section 7)."""
        async with self._session_factory() as session:
            async with session.begin():
                app_map = await session.get(AppMap, map_id)
                if app_map is None:
                    return
                app_map.status = gate.status
                app_map.release_state = gate.release_state
                app_map.release_scope = gate.release_scope
                app_map.census_expected_count = gate.expected
                app_map.census_reachable_count = gate.reachable
                app_map.gate_metrics = gate.metrics()
                app_map.failure_code = gate.failure_code
                app_map.failure_message = gate.failure_message
                app_map.failure_site = GATE_FAILURE_SITE if gate.failure_code else None
                app_map.mapping_spend_calls = 0
                app_map.mapping_spend_tokens = 0
                app_map.mapping_spend_seconds = spend_seconds
                app_map.census_metrics = dict(census_metrics)
                app_map.pattern_stats = dict(pattern_stats)
                app_map.completed_at = datetime.now(UTC)
                await session.flush()

    async def fail_map(
        self,
        map_id: UUID,
        *,
        failure_code: str,
        failure_message: str,
        failure_site: str,
        spend_seconds: float,
        census_metrics: dict[str, object] | None = None,
        pattern_stats: dict[str, object] | None = None,
    ) -> None:
        """Crash path (doc 14 section 11): the original error is retained on
        the job record; the gate is never evaluated for a crashed job."""
        async with self._session_factory() as session:
            async with session.begin():
                app_map = await session.get(AppMap, map_id)
                if app_map is None:
                    return
                app_map.status = "failed"
                app_map.failure_code = failure_code
                app_map.failure_message = failure_message
                app_map.failure_site = failure_site
                app_map.mapping_spend_seconds = spend_seconds
                if census_metrics is not None:
                    app_map.census_metrics = dict(census_metrics)
                if pattern_stats is not None:
                    app_map.pattern_stats = dict(pattern_stats)
                app_map.completed_at = datetime.now(UTC)
                await session.flush()

    # --- Phase 1b: harvest gate, trigger, reads, snapshot helpers --------

    async def harvest_counts(self, map_id: UUID) -> dict[str, int]:
        """Gate counts for one map (doc 16 section 5.9): census-reachable
        pages split by harvest disposition; NULL and 'pending' both count
        as pending (a page the job has not dispositioned yet)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapPage.harvest_status, func.count())
                .where(
                    MapPage.app_map_id == map_id,
                    MapPage.crawl_status.in_(REACHABLE_STATUSES),
                )
                .group_by(MapPage.harvest_status)
            )
            by_status = {status: count for status, count in result.all()}
        return {
            "reachable": sum(by_status.values()),
            "visited": by_status.get("visited", 0),
            "blocked_auth": by_status.get("blocked_auth", 0),
            "blocked_wall": by_status.get("blocked_wall", 0),
            "failed": by_status.get("failed", 0),
            "unprobed_budget": by_status.get("unprobed_budget", 0),
            "pending": by_status.get(None, 0) + by_status.get("pending", 0),
        }

    async def evaluate_harvest_gate(
        self,
        map_id: UUID,
        *,
        skill_verified: bool,
        skill_reason: str | None,
    ) -> HarvestGateResult:
        """Assemble the counts and delegate to the ONE shared gate
        function (doc 16 section 5.9): the applier and the tests can
        never drift, because both call markettwin_shared's function."""
        app_map = await self.get_map(map_id)
        counts = await self.harvest_counts(map_id)
        template_groups, enriched_groups = harvest_metric_counts(
            app_map.harvest_metrics if app_map is not None else None
        )
        counts.update(
            enriched_groups=enriched_groups,
            template_groups=template_groups,
            spend_calls=(app_map.mapping_spend_calls or 0) if app_map else 0,
            spend_tokens=(app_map.mapping_spend_tokens or 0) if app_map else 0,
            skill_verified=skill_verified,
            skill_reason=skill_reason,
        )
        return compute_harvest_gate(counts)

    async def apply_harvest_gate(
        self, map_id: UUID, *, gate: HarvestGateResult
    ) -> None:
        """Write the harvest gate's outcome (doc 16 section 5.9). The
        harvest block MERGES into gate_metrics: the census keys of
        Phase 1a stay. release_state comes from the gate (always
        'partial'); no path here can write 'trusted'."""
        async with self._session_factory() as session:
            async with session.begin():
                app_map = await session.get(AppMap, map_id)
                if app_map is None:
                    return
                app_map.harvest_status = gate.harvest_status
                app_map.harvest_failure_code = gate.failure_code
                app_map.harvest_failure_message = gate.failure_message
                app_map.harvest_failure_site = (
                    HARVEST_FAILURE_SITE if gate.failure_code else None
                )
                app_map.harvest_completed_at = datetime.now(UTC)
                merged = dict(app_map.gate_metrics or {})
                merged.update(gate.metrics())
                app_map.gate_metrics = merged
                app_map.release_state = gate.release_state
                app_map.release_scope = gate.release_scope
                await session.flush()

    async def get_map_in_scope(
        self, map_id: UUID, *, application_id: UUID, target_id: UUID
    ) -> AppMap | None:
        """The map only when it belongs to the path's application and
        target (doc 16 section 10.1): anything else reads as missing."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(AppMap).where(
                    AppMap.id == map_id,
                    AppMap.application_id == application_id,
                    AppMap.target_id == target_id,
                )
            )
            return result.scalars().first()

    async def pending_link_research(self) -> list[UUID]:
        newer = aliased(AppMap)
        authorized = select(TargetAuthorization.id).where(
            TargetAuthorization.target_id == AppMap.target_id,
            TargetAuthorization.status == "authorized",
            TargetAuthorization.revoked_at.is_(None),
            or_(TargetAuthorization.expires_at.is_(None), TargetAuthorization.expires_at > func.now()),
        ).exists()
        async with self._session_factory() as session:
            result = await session.scalars(
                select(AppMap.id).where(
                    AppMap.status == "ready",
                    AppMap.harvest_status == "not_started",
                    AppMap.census_config["skill_research_url"].as_string().is_not(None),
                    authorized,
                    ~select(newer.id).where(
                        newer.target_id == AppMap.target_id,
                        newer.version_number > AppMap.version_number,
                    ).exists(),
                ).order_by(AppMap.started_at).limit(10)
            )
            return list(result)

    async def start_harvest(
        self, map_id: UUID, *, journey_terminal_url: str | None = None, only_unstarted: bool = False,
    ) -> tuple[AppMap | None, bool]:
        """Mark a map's harvest as building (doc 16 sections 6.1, 10.1).

        Returns ``(map, started)``: an already-building map returns
        ``started=False`` (the in-flight answer); the partial unique
        index is the backstop for the concurrent race, mirroring
        ``create_build``. The owner's journey-terminal choice rides in
        harvest_metrics for the worker to read.
        """
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    app_map = await session.get(AppMap, map_id, with_for_update=True)
                    if app_map is None:
                        return None, False
                    if app_map.harvest_status == "building":
                        return app_map, False
                    if only_unstarted and (app_map.status != "ready" or app_map.harvest_status != "not_started"):
                        return app_map, False
                    app_map.harvest_status = "building"
                    app_map.harvest_started_at = datetime.now(UTC)
                    app_map.harvest_completed_at = None
                    app_map.harvest_failure_code = None
                    app_map.harvest_failure_message = None
                    app_map.harvest_failure_site = None
                    if journey_terminal_url is not None:
                        metrics = dict(app_map.harvest_metrics or {})
                        metrics["journey_terminal_url"] = journey_terminal_url
                        app_map.harvest_metrics = metrics
                    await session.flush()
                    return app_map, True
        except IntegrityError:
            existing = await self.get_map(map_id)
            return existing, False

    async def create_preflight_for_map(
        self, map_id: UUID, *, trigger: str
    ) -> tuple[MapPreflight | None, bool]:
        """Queue a freshness preflight for a map (doc 23 sections
        5.2, 9.3).

        Returns ``(preflight, created)``: when one is already in
        flight for the map, the in-flight row returns with
        ``created=False`` (the join answer); the partial unique index
        is the backstop for the concurrent race, mirroring
        ``start_harvest``.
        """
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    app_map = await session.get(AppMap, map_id)
                    if app_map is None:
                        return None, False
                    in_flight = await session.scalar(
                        select(MapPreflight)
                        .where(
                            MapPreflight.app_map_id == map_id,
                            MapPreflight.status == "building",
                        )
                        .order_by(MapPreflight.started_at.desc())
                    )
                    if in_flight is not None:
                        return in_flight, False
                    preflight = MapPreflight(
                        id=uuid4(),
                        workspace_id=app_map.workspace_id,
                        application_id=app_map.application_id,
                        target_id=app_map.target_id,
                        app_map_id=app_map.id,
                        run_id=None,
                        trigger=trigger,
                        status="building",
                        config={},
                        started_at=datetime.now(UTC),
                    )
                    session.add(preflight)
                    await session.flush()
                    return preflight, True
        except IntegrityError:
            async with self._session_factory() as session:
                in_flight = await session.scalar(
                    select(MapPreflight)
                    .where(
                        MapPreflight.app_map_id == map_id,
                        MapPreflight.status == "building",
                    )
                    .order_by(MapPreflight.started_at.desc())
                )
                return in_flight, False

    async def get_preflight_in_scope(
        self,
        preflight_id: UUID,
        *,
        map_id: UUID,
        application_id: UUID,
        target_id: UUID,
    ) -> MapPreflight | None:
        async with self._session_factory() as session:
            return await session.scalar(
                select(MapPreflight).where(
                    MapPreflight.id == preflight_id,
                    MapPreflight.app_map_id == map_id,
                    MapPreflight.application_id == application_id,
                    MapPreflight.target_id == target_id,
                )
            )

    async def harvest_extras(self, app_map: AppMap) -> HarvestExtras:
        counts = await self.harvest_counts(app_map.id)
        template_groups, enriched_groups = harvest_metric_counts(
            app_map.harvest_metrics
        )
        return HarvestExtras(
            visited=counts["visited"],
            reachable=counts["reachable"],
            blocked=counts["blocked_auth"] + counts["blocked_wall"],
            failed=counts["failed"],
            unprobed_budget=counts["unprobed_budget"],
            enriched_groups=enriched_groups,
            template_groups=template_groups,
            spend_calls=app_map.mapping_spend_calls or 0,
            spend_tokens=app_map.mapping_spend_tokens or 0,
        )

    async def list_map_skills(self, map_id: UUID) -> list[MapSkillLine]:
        """Skills scoped to this map, each with its latest version's
        lifecycle and replay outcome (doc 16 section 10.1)."""
        async with self._session_factory() as session:
            skills = list(
                (
                    await session.execute(
                        select(Skill)
                        .where(Skill.app_map_id == map_id)
                        .order_by(Skill.name)
                    )
                ).scalars().all()
            )
            if not skills:
                return []
            versions = list(
                (
                    await session.execute(
                        select(SkillVersion)
                        .where(
                            SkillVersion.skill_id.in_([s.id for s in skills])
                        )
                        .order_by(SkillVersion.version_number.desc())
                    )
                ).scalars().all()
            )
        latest: dict[UUID, SkillVersion] = {}
        for version in versions:
            latest.setdefault(version.skill_id, version)
        lines: list[MapSkillLine] = []
        for skill in skills:
            version = latest.get(skill.id)
            lines.append(
                MapSkillLine(
                    name=skill.name,
                    lifecycle_status=(
                        version.lifecycle_status if version is not None else None
                    ),
                    last_replay_result=(
                        version.last_replay_result if version is not None else None
                    ),
                    last_replay_at=(
                        version.last_replay_at if version is not None else None
                    ),
                )
            )
        return lines

    async def skill_lines_by_ids(
        self, skill_ids: list[UUID]
    ) -> dict[UUID, MapSkillLine]:
        """MapSkillLine per skill id (journeys endpoint, section 10.2)."""
        unique_ids = list(dict.fromkeys(skill_ids))
        if not unique_ids:
            return {}
        async with self._session_factory() as session:
            skills = list(
                (
                    await session.execute(
                        select(Skill).where(Skill.id.in_(unique_ids))
                    )
                ).scalars().all()
            )
            if not skills:
                return {}
            versions = list(
                (
                    await session.execute(
                        select(SkillVersion)
                        .where(
                            SkillVersion.skill_id.in_([s.id for s in skills])
                        )
                        .order_by(SkillVersion.version_number.desc())
                    )
                ).scalars().all()
            )
        latest: dict[UUID, SkillVersion] = {}
        for version in versions:
            latest.setdefault(version.skill_id, version)
        lines: dict[UUID, MapSkillLine] = {}
        for skill in skills:
            version = latest.get(skill.id)
            lines[skill.id] = MapSkillLine(
                name=skill.name,
                lifecycle_status=(
                    version.lifecycle_status if version is not None else None
                ),
                last_replay_result=(
                    version.last_replay_result if version is not None else None
                ),
                last_replay_at=(
                    version.last_replay_at if version is not None else None
                ),
            )
        return lines

    async def get_page_in_map(
        self, map_id: UUID, page_id: UUID
    ) -> MapPage | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapPage).where(
                    MapPage.id == page_id, MapPage.app_map_id == map_id
                )
            )
            return result.scalars().first()

    async def list_states_for_page(self, page_id: UUID) -> list[MapPageState]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapPageState)
                .where(MapPageState.map_page_id == page_id)
                .order_by(MapPageState.state_key)
            )
            return list(result.scalars().all())

    async def list_elements_for_states(
        self, state_ids: list[UUID]
    ) -> list[MapElement]:
        if not state_ids:
            return []
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapElement)
                .where(MapElement.map_page_state_id.in_(state_ids))
                .order_by(MapElement.map_page_state_id, MapElement.ordinal)
            )
            return list(result.scalars().all())

    async def list_forms_for_states(self, state_ids: list[UUID]) -> list[MapForm]:
        if not state_ids:
            return []
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapForm)
                .where(MapForm.map_page_state_id.in_(state_ids))
                .order_by(MapForm.map_page_state_id, MapForm.form_key)
            )
            return list(result.scalars().all())

    async def list_fields_for_forms(self, form_ids: list[UUID]) -> list[MapField]:
        if not form_ids:
            return []
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapField)
                .where(MapField.form_id.in_(form_ids))
                .order_by(MapField.form_id, MapField.ordinal)
            )
            return list(result.scalars().all())

    async def list_journeys(self, map_id: UUID) -> list[MapJourney]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapJourney)
                .where(MapJourney.app_map_id == map_id)
                .order_by(MapJourney.name)
            )
            return list(result.scalars().all())

    async def get_states_by_ids(
        self, state_ids: list[UUID]
    ) -> dict[UUID, MapPageState]:
        if not state_ids:
            return {}
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapPageState).where(MapPageState.id.in_(state_ids))
            )
            return {state.id: state for state in result.scalars().all()}

    async def get_elements_by_ids(
        self, element_ids: list[UUID]
    ) -> dict[UUID, MapElement]:
        if not element_ids:
            return {}
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapElement).where(MapElement.id.in_(element_ids))
            )
            return {element.id: element for element in result.scalars().all()}

    async def get_pages_by_ids(self, page_ids: list[UUID]) -> dict[UUID, MapPage]:
        if not page_ids:
            return {}
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapPage).where(MapPage.id.in_(page_ids))
            )
            return {page.id: page for page in result.scalars().all()}

    async def get_evidence(
        self, evidence_id: UUID
    ) -> MapEvidenceObject | None:
        async with self._session_factory() as session:
            return await session.get(MapEvidenceObject, evidence_id)

    async def count_expectations(self, map_id: UUID) -> int:
        """Authored expectations on this map (0 throughout Phase 1b:
        the table exists, its writers arrive in Phase 2)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.count())
                .select_from(MapExpectation)
                .where(MapExpectation.app_map_id == map_id)
            )
            return result.scalars().first() or 0

    # Snapshot helpers (doc 16 section 11.1). Each performs exactly one
    # query, in the pinned order the snapshot block consumes them:
    # harvest counts, elements, journeys, skills, skill versions.

    async def snapshot_page_elements(
        self, state_ids: list[UUID]
    ) -> list[MapElement]:
        return await self.list_elements_for_states(state_ids)

    async def snapshot_journeys(self, map_id: UUID) -> list[MapJourney]:
        return await self.list_journeys(map_id)

    # -- Phase 2: expectations, conflicts, grounding (doc 21 sections 9,
    # 14.2). Eligibility is NEVER re-implemented here: every stamped
    # record's verdict_eligible comes from the shared C3 function.

    async def list_conflicts(self, map_id: UUID) -> list[MapConflict]:
        """All conflicts on the map, oldest first (open and resolved)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapConflict)
                .where(MapConflict.app_map_id == map_id)
                .order_by(MapConflict.created_at)
            )
            return list(result.scalars().all())

    async def list_open_conflicts(self, map_id: UUID) -> list[MapConflict]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapConflict)
                .where(
                    MapConflict.app_map_id == map_id,
                    MapConflict.status == "open",
                )
                .order_by(MapConflict.created_at)
            )
            return list(result.scalars().all())

    async def list_expectation_records(
        self, map_id: UUID
    ) -> list[dict[str, object]]:
        """Expectations as stamped serving records (doc 21 section 14).

        Each record carries its subject's resolution in this map
        version (``subject_resolvable``, ``page_url``) and its
        ``verdict_eligible`` stamp from the ONE shared implementation
        (spec C3) -- the snapshot, the panel and Board seeding all read
        these stamps, so the rule cannot drift between consumers.
        """
        async with self._session_factory() as session:
            expectations = list(
                (
                    await session.execute(
                        select(MapExpectation)
                        .where(
                            MapExpectation.app_map_id == map_id,
                            MapExpectation.superseded_by_id.is_(None),
                        )
                        .order_by(MapExpectation.created_at)
                    )
                ).scalars().all()
            )
            if not expectations:
                return []
            open_conflicts = list(
                (
                    await session.execute(
                        select(MapConflict).where(
                            MapConflict.app_map_id == map_id,
                            MapConflict.status == "open",
                        )
                    )
                ).scalars().all()
            )
            pages = {
                page.id: page
                for page in (
                    await session.execute(
                        select(MapPage).where(MapPage.app_map_id == map_id)
                    )
                ).scalars().all()
            }
            states = {
                state.id: state
                for state in (
                    await session.execute(
                        select(MapPageState).where(
                            MapPageState.app_map_id == map_id
                        )
                    )
                ).scalars().all()
            }
            elements = {
                element.id: element
                for element in (
                    await session.execute(
                        select(MapElement).where(MapElement.app_map_id == map_id)
                    )
                ).scalars().all()
            }
            forms = {
                form.id: form
                for form in (
                    await session.execute(
                        select(MapForm).where(MapForm.app_map_id == map_id)
                    )
                ).scalars().all()
            }
            fields = {
                field.id: field
                for field in (
                    await session.execute(
                        select(MapField).where(MapField.app_map_id == map_id)
                    )
                ).scalars().all()
            }
            journeys = {
                journey.id: journey
                for journey in (
                    await session.execute(
                        select(MapJourney).where(MapJourney.app_map_id == map_id)
                    )
                ).scalars().all()
            }

        open_for = {conflict.expectation_id for conflict in open_conflicts}

        def page_url_for(expectation: MapExpectation) -> tuple[bool, str | None]:
            page: MapPage | None = None
            subject_id = expectation.subject_id
            if expectation.subject_kind == "page":
                page = pages.get(subject_id)
            elif expectation.subject_kind == "element":
                element = elements.get(subject_id)
                if element is not None:
                    page = pages.get(element.map_page_id)
            elif expectation.subject_kind == "form":
                form = forms.get(subject_id)
                if form is not None:
                    state = states.get(form.map_page_state_id)
                    if state is not None:
                        page = pages.get(state.map_page_id)
            elif expectation.subject_kind == "field":
                field = fields.get(subject_id)
                if field is not None:
                    form = forms.get(field.form_id)
                    if form is not None:
                        state = states.get(form.map_page_state_id)
                        if state is not None:
                            page = pages.get(state.map_page_id)
            elif expectation.subject_kind == "journey":
                journey = journeys.get(subject_id)
                if journey is not None:
                    state = states.get(journey.success_state_id)
                    if state is not None:
                        page = pages.get(state.map_page_id)
            if page is None:
                return False, None
            return True, page_effective_url(page)

        records: list[dict[str, object]] = []
        for expectation in expectations:
            resolvable, page_url = page_url_for(expectation)
            record: dict[str, object] = {
                "id": str(expectation.id),
                "subject_kind": expectation.subject_kind,
                "subject_id": str(expectation.subject_id),
                "page_url": page_url,
                "statement": expectation.statement,
                "oracle_source": expectation.oracle_source,
                "source_ref": expectation.source_ref,
                "status": expectation.status,
                "confidence": expectation.confidence,
                "assertion": expectation.assertion,
                "assertion_kind": expectation.assertion_kind,
                "assertion_origin": expectation.assertion_origin,
                "promoted_by": expectation.promoted_by,
                "superseded_by_id": (
                    str(expectation.superseded_by_id)
                    if expectation.superseded_by_id is not None
                    else None
                ),
                "conflicted": expectation.status == "conflicted",
                "has_open_conflict": expectation.id in open_for,
                "subject_resolvable": resolvable,
                "last_checked_at": (
                    expectation.last_checked_at.isoformat()
                    if expectation.last_checked_at is not None
                    else None
                ),
                "last_check_result": expectation.last_check_result,
            }
            record["verdict_eligible"] = expectation_verdict_eligible(record)
            records.append(record)
        return records

    async def expectation_summary(self, map_id: UUID) -> dict[str, object]:
        """Coverage (section 10) + gate (section 15) for the panel."""
        app_map = await self.get_map(map_id)
        records = await self.list_expectation_records(map_id)
        coverage = expectation_coverage(records)
        gate = compute_expectation_gate(
            coverage,
            {
                "eligible_with_assertion": int(coverage["verdict_eligible"]),
                "conflicts_open": int(coverage["conflicted_open"]),
                "taxonomy_violations_open": None,
                "sweep_violations": 0,
                "grounding_completed": (
                    app_map is not None
                    and app_map.grounding_status in ("ready", "partial")
                ),
                "accounting_complete": True,
            },
        )
        summary: dict[str, object] = dict(coverage)
        summary.update(gate.metrics())
        summary["grounding_status"] = (
            app_map.grounding_status if app_map is not None else None
        )
        summary["release_state"] = gate.release_state
        summary["release_scope"] = gate.release_scope
        return summary

    async def list_suggestions(
        self, map_id: UUID
    ) -> list[dict[str, object]]:
        """The promotion queue (doc 21 section 5.5): unverified
        documentation/model-draft records, minus records whose latest
        decision event is a rejection with no later promotion."""
        records = await self.list_expectation_records(map_id)
        candidates = {
            record["id"]: record
            for record in records
            if record["status"] == "unverified"
            and (
                record["oracle_source"] in ("observation", "model-draft")
                or (
                    record["oracle_source"] == "documentation"
                    and record["assertion_origin"] == "model-drafted"
                )
            )
        }
        if not candidates:
            return []
        async with self._session_factory() as session:
            events = list(
                (
                    await session.execute(
                        select(MapExpectationEvent)
                        .where(
                            MapExpectationEvent.app_map_id == map_id,
                            MapExpectationEvent.event_type.in_(
                                ("rejected", "promoted")
                            ),
                        )
                        .order_by(MapExpectationEvent.occurred_at)
                    )
                ).scalars().all()
            )
        latest_decision: dict[UUID, str] = {}
        for event in events:
            latest_decision[event.expectation_id] = event.event_type
        return [
            record
            for expectation_id, record in candidates.items()
            if latest_decision.get(UUID(expectation_id)) != "rejected"
        ]

    async def _append_expectation_event(
        self,
        session: AsyncSession,
        expectation: MapExpectation,
        event_type: str,
        *,
        actor: str,
        payload: dict[str, object],
    ) -> MapExpectationEvent:
        event = MapExpectationEvent(
            id=uuid4(),
            workspace_id=expectation.workspace_id,
            application_id=expectation.application_id,
            target_id=expectation.target_id,
            app_map_id=expectation.app_map_id,
            expectation_id=expectation.id,
            event_type=event_type,
            payload={**payload, "actor": actor},
        )
        session.add(event)
        return event

    async def record_promotion(
        self, expectation_id: UUID, *, app_map_id: UUID, actor: str, note: str | None = None
    ) -> MapExpectation:
        """Owner promotion (doc 21 section 5.5): the ONLY road to
        verdict grade for documentation/model-draft records. Per-record
        only -- no bulk path exists. The source NEVER changes."""
        async with self._session_factory() as session:
            async with session.begin():
                expectation = await session.get(MapExpectation, expectation_id)
                if expectation is None or expectation.app_map_id != app_map_id:
                    raise ValueError("expectation_not_found")
                if expectation.status != "unverified":
                    # Conflicted records promote only via section 9
                    # resolution; verified/confirmed records are done.
                    raise ValueError("expectation_not_promotable")
                expectation.status = "owner-confirmed"
                expectation.promoted_by = actor
                expectation.promoted_at = datetime.now(UTC)
                await self._append_expectation_event(
                    session,
                    expectation,
                    "promoted",
                    actor=actor,
                    payload={"note": note} if note else {},
                )
                await session.flush()
                return expectation

    async def record_rejection(
        self, expectation_id: UUID, *, app_map_id: UUID, actor: str, reason: str
    ) -> MapExpectationEvent:
        """Owner rejection: the record keeps its source and status; the
        event removes it from the suggestion queue until re-promoted."""
        async with self._session_factory() as session:
            async with session.begin():
                expectation = await session.get(MapExpectation, expectation_id)
                if expectation is None or expectation.app_map_id != app_map_id:
                    raise ValueError("expectation_not_found")
                event = await self._append_expectation_event(
                    session,
                    expectation,
                    "rejected",
                    actor=actor,
                    payload={"reason": reason},
                )
                await session.flush()
                return event

    async def resolve_conflict(
        self,
        conflict_id: UUID,
        *,
        app_map_id: UUID,
        resolution: str,
        actor: str,
        owner_text: str | None = None,
    ) -> MapConflict:
        """Conflict resolution mechanics (doc 21 section 9.3).

        docs-win: the documented expectation's assertion is re-derived
        (it never left the record) and reseeds Board checks.
        app-win / owner-decided: a NEW owner-rule expectation carries
        the winning behaviour; the original keeps its source and gains
        a ``superseded`` event (spec C2 -- nothing is overwritten).
        """
        if resolution not in {"docs-win", "app-win", "owner-decided"}:
            raise ValueError("invalid_resolution")
        if resolution != "docs-win" and not (owner_text and owner_text.strip()):
            raise ValueError("owner_text_required")
        async with self._session_factory() as session:
            async with session.begin():
                conflict = await session.get(MapConflict, conflict_id)
                if conflict is None or conflict.app_map_id != app_map_id:
                    raise ValueError("conflict_not_found")
                if conflict.status != "open":
                    raise ValueError("conflict_not_open")
                expectation = await session.get(
                    MapExpectation, conflict.expectation_id
                )
                if expectation is None or expectation.app_map_id != app_map_id:
                    raise ValueError("expectation_not_found")
                conflict.status = "resolved"
                conflict.resolution = resolution
                conflict.decided_by = actor
                conflict.decided_at = datetime.now(UTC)
                await self._append_expectation_event(
                    session,
                    expectation,
                    "resolved",
                    actor=actor,
                    payload={
                        "conflict_id": str(conflict.id),
                        "resolution": resolution,
                    },
                )
                if resolution == "docs-win":
                    expectation.status = "unverified"
                else:
                    # app-win / owner-decided: the owner's restated
                    # text (endpoint-enforced) becomes a NEW owner-rule
                    # record; the original keeps its source and status
                    # and is retired by superseded_by_id (section 9.4).
                    successor = MapExpectation(
                        id=uuid4(),
                        workspace_id=expectation.workspace_id,
                        application_id=expectation.application_id,
                        target_id=expectation.target_id,
                        app_map_id=expectation.app_map_id,
                        subject_kind=expectation.subject_kind,
                        subject_id=expectation.subject_id,
                        statement=owner_text or "",
                        oracle_source="owner-rule",
                        status="owner-confirmed",
                        source_ref=f"conflict:{conflict.id}",
                        confidence=expectation.confidence,
                        assertion=expectation.assertion,
                        assertion_kind=expectation.assertion_kind,
                        assertion_origin=expectation.assertion_origin,
                    )
                    session.add(successor)
                    await session.flush()
                    await self._append_expectation_event(
                        session,
                        successor,
                        "authored",
                        actor=actor,
                        payload={
                            "via": "conflict_resolution",
                            "conflict_id": str(conflict.id),
                        },
                    )
                    expectation.superseded_by_id = successor.id
                    await self._append_expectation_event(
                        session,
                        expectation,
                        "superseded",
                        actor=actor,
                        payload={
                            "superseded_by": str(successor.id),
                            "conflict_id": str(conflict.id),
                        },
                    )
                await session.flush()
                return conflict

    async def start_grounding(
        self,
        map_id: UUID,
        *,
        probe: bool = False,
        approved_test_data: dict[str, str] | None = None,
    ) -> tuple[AppMap | None, bool]:
        """Mark a map's grounding as building (doc 21 section 14.2).

        Mirrors ``start_harvest``: ``(map, started)``; an already-
        building map returns ``started=False``. The trigger payload
        (the probing election + owner-approved test data) rides in
        grounding_metrics for the orchestrator's grounding job.
        """
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    app_map = await session.get(AppMap, map_id)
                    if app_map is None:
                        return None, False
                    if app_map.grounding_status == "building":
                        return app_map, False
                    app_map.grounding_status = "building"
                    app_map.grounding_started_at = datetime.now(UTC)
                    app_map.grounding_completed_at = None
                    app_map.grounding_failure_code = None
                    app_map.grounding_failure_message = None
                    app_map.grounding_failure_site = None
                    metrics = dict(app_map.grounding_metrics or {})
                    metrics["trigger"] = {
                        "probe": bool(probe),
                        "approved_test_data": dict(approved_test_data or {}),
                    }
                    app_map.grounding_metrics = metrics
                    await session.flush()
                    return app_map, True
        except IntegrityError:
            existing = await self.get_map(map_id)
            return existing, False

    async def latest_audit_report(
        self, map_id: UUID
    ) -> GraphAuditReport | None:
        """The newest read-only graph audit for the panel (section 11)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(GraphAuditReport)
                .where(GraphAuditReport.app_map_id == map_id)
                .order_by(GraphAuditReport.created_at.desc())
                .limit(1)
            )
            return result.scalars().first()

    # -- Phase 3: skill library (doc 22 sections 5.1, 5.2, 5.3, 7.1,
    # 11.1, 12.1). Every lifecycle write passes the ONE shared
    # authority (check_skill_transition) at the write site and records
    # its skill_usage_events row in the same transaction.

    async def _write_transition(
        self,
        session: AsyncSession,
        version: SkillVersion,
        *,
        to_status: str,
        kind: str,
        evidence: Mapping[str, object],
        result: str | None = None,
        run_id: UUID | None = None,
        job_ref: str | None = None,
        model_calls: int = 0,
        model_tokens: int = 0,
        payload: Mapping[str, object] | None = None,
    ) -> None:
        """Check + apply + record one transition inside ``session``.

        A refusal raises ValueError: a refused transition is the
        caller's bug, surfaced -- never a skipped write (doc 22
        section 5.1).
        """
        from_status = version.lifecycle_status
        if not check_skill_transition(from_status, to_status, evidence):
            raise ValueError(
                f"skill_transition_refused: {from_status} -> {to_status}"
            )
        version.lifecycle_status = to_status
        if to_status == "retired":
            retirement = evidence.get("retirement")
            if isinstance(retirement, Mapping):
                reason = retirement.get("retired_reason")
                version.retired_reason = (
                    reason if isinstance(reason, str) else None
                )
            version.retired_at = datetime.now(UTC)
        session.add(
            SkillUsageEvent(
                id=uuid4(),
                workspace_id=version.workspace_id,
                skill_id=version.skill_id,
                skill_version_id=version.id,
                app_map_id=version.app_map_id,
                run_id=run_id,
                job_ref=job_ref,
                kind=kind,
                from_status=from_status,
                to_status=to_status,
                model_calls=model_calls,
                model_tokens=model_tokens,
                result=result,
                payload=dict(payload) if payload is not None else dict(evidence),
            )
        )
        await session.flush()

    async def transition_skill_version(
        self,
        *,
        version_id: UUID,
        to_status: str,
        kind: str,
        evidence: Mapping[str, object],
        result: str | None = None,
        run_id: UUID | None = None,
        job_ref: str | None = None,
        model_calls: int = 0,
        model_tokens: int = 0,
        payload: Mapping[str, object] | None = None,
    ) -> SkillVersion:
        """One lifecycle transition in its own transaction (doc 22
        section 5.1). Raises ValueError on a refused transition or an
        unknown version id."""
        async with self._session_factory() as session:
            async with session.begin():
                version = await session.get(SkillVersion, version_id)
                if version is None:
                    raise ValueError(f"skill_version_unknown: {version_id}")
                await self._write_transition(
                    session,
                    version,
                    to_status=to_status,
                    kind=kind,
                    evidence=evidence,
                    result=result,
                    run_id=run_id,
                    job_ref=job_ref,
                    model_calls=model_calls,
                    model_tokens=model_tokens,
                    payload=payload,
                )
                return version

    async def record_skill_usage(
        self,
        *,
        version: SkillVersion,
        kind: str,
        result: str | None = None,
        run_id: UUID | None = None,
        job_ref: str | None = None,
        model_calls: int = 0,
        model_tokens: int = 0,
        payload: Mapping[str, object] | None = None,
    ) -> None:
        """A usage-ledger row with NO lifecycle change (a replay, a
        heal diagnosis, a persona-fence refusal)."""
        async with self._session_factory() as session:
            async with session.begin():
                session.add(
                    SkillUsageEvent(
                        id=uuid4(),
                        workspace_id=version.workspace_id,
                        skill_id=version.skill_id,
                        skill_version_id=version.id,
                        app_map_id=version.app_map_id,
                        run_id=run_id,
                        job_ref=job_ref,
                        kind=kind,
                        from_status=version.lifecycle_status,
                        to_status=version.lifecycle_status,
                        model_calls=model_calls,
                        model_tokens=model_tokens,
                        result=result,
                        payload=dict(payload or {}),
                    )
                )

    async def latest_active_skills(
        self,
        *,
        workspace_id: UUID,
        application_id: UUID,
        target_id: UUID,
        consumer: str = "run",
    ) -> tuple[list[tuple[Skill, SkillVersion]], int]:
        """Doc 22 section 7.1 serving: the active version of every
        skill in the graph scope, plus the withheld count -- versions
        in the scope in non-active states, the honest denominator
        (section 7.2). A persona consumer (section 11.1) is served
        platform skills only; journey skills are not returned."""
        async with self._session_factory() as session:
            skills = list(
                (
                    await session.execute(
                        select(Skill)
                        .where(
                            Skill.workspace_id == workspace_id,
                            Skill.application_id == application_id,
                            Skill.target_id == target_id,
                        )
                        .order_by(Skill.name)
                    )
                ).scalars().all()
            )
            if not skills:
                return [], 0
            versions = list(
                (
                    await session.execute(
                        select(SkillVersion).where(
                            SkillVersion.skill_id.in_([s.id for s in skills])
                        ).order_by(SkillVersion.version_number.desc())
                    )
                ).scalars().all()
            )
        active: dict[UUID, SkillVersion] = {}
        withheld = 0
        for version in versions:
            if version.lifecycle_status == "active":
                if version.skill_id in active:
                    raise ValueError("multiple_active_skill_versions")
                active[version.skill_id] = version
            else:
                withheld += 1
        served: list[tuple[Skill, SkillVersion]] = []
        for skill in skills:
            version = active.get(skill.id)
            if version is None:
                continue
            if consumer == "persona_setup" and skill.skill_kind != "platform":
                continue
            served.append((skill, version))
        return served, withheld

    async def serve_skill_for_consumer(
        self,
        *,
        skill_id: UUID,
        consumer: str,
        run_id: UUID | None = None,
    ) -> SkillVersion | None:
        """The active version of one skill for a named consumer.

        The persona fence (doc 22 section 11.1): a persona consumer
        asking for a journey skill is REFUSED -- the refusal is
        recorded on the ledger (kind 'run_replay', result 'refused')
        and None is returned. A skill with no active version serves
        None without a refusal row (nothing was asked to replay)."""
        async with self._session_factory() as session:
            skill = await session.get(Skill, skill_id)
            if skill is None:
                return None
            versions = list(
                (
                    await session.execute(
                        select(SkillVersion)
                        .where(SkillVersion.skill_id == skill_id)
                        .order_by(SkillVersion.version_number.desc())
                    )
                ).scalars().all()
            )
        if not versions:
            return None
        active = next(
            (v for v in versions if v.lifecycle_status == "active"), None
        )
        if active is None:
            return None
        if consumer == "persona_setup" and skill.skill_kind != "platform":
            await self.record_skill_usage(
                version=active,
                kind="run_replay",
                result="refused",
                run_id=run_id,
                payload={"consumer": consumer, "reason": "persona_fence"},
            )
            return None
        return active

    async def run_activation_pass(
        self,
        *,
        workspace_id: UUID,
        application_id: UUID,
        target_id: UUID,
        current_map_id: UUID,
    ) -> dict[str, int]:
        """Doc 22 section 5.2: for every replay_verified version in
        the scope, run the point currency check (section 5.3) against
        the current ready map. Pass -> retire the active sibling as
        superseded and activate. Journey absent from the current map
        -> retire as journey_absent. Currency mismatch with the
        journey present -> stays replay_verified; the failed
        activation is recorded and the re-verification poller owns
        the retry. Platform skills are current iff the version was
        compiled against the current map itself."""
        counts = {
            "activated": 0,
            "retired_superseded": 0,
            "retired_journey_absent": 0,
            "currency_failed": 0,
        }
        async with self._session_factory() as session:
            async with session.begin():
                app_map = await session.get(AppMap, current_map_id)
                if app_map is None:
                    return counts
                skills = list(
                    (
                        await session.execute(
                            select(Skill).where(
                                Skill.workspace_id == workspace_id,
                                Skill.application_id == application_id,
                                Skill.target_id == target_id,
                            )
                        )
                    ).scalars().all()
                )
                if not skills:
                    return counts
                versions = list(
                    (
                        await session.execute(
                            select(SkillVersion).where(
                                SkillVersion.skill_id.in_(
                                    [s.id for s in skills]
                                )
                            )
                        )
                    ).scalars().all()
                )
                pages = list(
                    (
                        await session.execute(
                            select(MapPage).where(
                                MapPage.app_map_id == current_map_id
                            )
                        )
                    ).scalars().all()
                )
                states = (
                    list(
                        (
                            await session.execute(
                                select(MapPageState).where(
                                    MapPageState.app_map_id == current_map_id,
                                )
                            )
                        ).scalars().all()
                    )
                    if pages
                    else []
                )
                journeys = list(
                    (
                        await session.execute(
                            select(MapJourney).where(
                                MapJourney.app_map_id == current_map_id
                            )
                        )
                    ).scalars().all()
                )
                source_journeys = {}
                source_ids = {
                    v.definition_json.get("source_journey_id")
                    for v in versions
                    if isinstance(v.definition_json, Mapping)
                }
                source_ids.discard(None)
                if source_ids:
                    rows = list(
                        (
                            await session.execute(
                                select(MapJourney).where(
                                    MapJourney.id.in_(
                                        [UUID(str(s)) for s in source_ids]
                                    )
                                )
                            )
                        ).scalars().all()
                    )
                    source_journeys = {str(j.id): j for j in rows}
                base_page = next(
                    (p for p in pages if p.canonical_url == app_map.base_url),
                    pages[0] if pages else None,
                )
                # Currency compares MapPageState.state_id identity
                # strings (doc 22 section 5.3: "default-state id ...
                # compared as strings, from the map rows").
                default_state_by_page = {
                    s.map_page_id: s.state_id
                    for s in states
                    if s.state_key == "default"
                }
                state_identity_by_row = {s.id: s.state_id for s in states}
                start_state_id = (
                    default_state_by_page.get(base_page.id)
                    if base_page is not None
                    else None
                )
                journey_by_name = {j.name: j for j in journeys}
                skill_by_id = {s.id: s for s in skills}
                active_by_skill: dict[UUID, SkillVersion] = {}
                candidates: list[SkillVersion] = []
                for version in versions:
                    if version.lifecycle_status == "active":
                        active_by_skill[version.skill_id] = version
                    elif version.lifecycle_status == "replay_verified":
                        candidates.append(version)
                for version in candidates:
                    skill = skill_by_id[version.skill_id]
                    if skill.skill_kind == "platform":
                        current = version.app_map_id == current_map_id
                        journey_present = True
                    else:
                        source = source_journeys.get(
                            str(
                                version.definition_json.get("source_journey_id")
                            )
                        ) if isinstance(version.definition_json, Mapping) else None
                        current_journey = (
                            journey_by_name.get(source.name)
                            if source is not None
                            else None
                        )
                        journey_present = current_journey is not None
                        current = journey_present and skill_currency_check(
                            version.verified_fingerprint,
                            start_state_id,
                            state_identity_by_row.get(
                                current_journey.success_state_id
                            ),
                        )
                    if not journey_present:
                        await self._write_transition(
                            session,
                            version,
                            to_status="retired",
                            kind="retirement",
                            evidence={
                                "retirement": {
                                    "retired_reason": "journey_absent"
                                }
                            },
                            payload={"reason": "journey_absent"},
                        )
                        counts["retired_journey_absent"] += 1
                        continue
                    if not current:
                        session.add(
                            SkillUsageEvent(
                                id=uuid4(),
                                workspace_id=version.workspace_id,
                                skill_id=version.skill_id,
                                skill_version_id=version.id,
                                app_map_id=version.app_map_id,
                                kind="activation",
                                from_status=version.lifecycle_status,
                                to_status=version.lifecycle_status,
                                result="failed",
                                payload={"reason": "currency_mismatch"},
                            )
                        )
                        counts["currency_failed"] += 1
                        continue
                    sibling = active_by_skill.get(version.skill_id)
                    if sibling is not None and sibling.id != version.id:
                        await self._write_transition(
                            session,
                            sibling,
                            to_status="retired",
                            kind="retirement",
                            evidence={
                                "retirement": {
                                    "retired_reason": "superseded",
                                    "superseded_by_version_id": str(version.id),
                                }
                            },
                            payload={
                                "retired_reason": "superseded",
                                "superseded_by_version_id": str(version.id),
                            },
                        )
                        counts["retired_superseded"] += 1
                    await self._write_transition(
                        session,
                        version,
                        to_status="active",
                        kind="activation",
                        evidence={
                            "currency_pass": {
                                "app_map_id": str(current_map_id)
                            }
                        },
                        result="passed",
                    )
                    active_by_skill[version.skill_id] = version
                    counts["activated"] += 1
                await session.flush()
        return counts

    async def skill_usage_summary(self, skill_id: UUID) -> dict[str, object]:
        """Doc 22 section 12.1: per-skill ledger totals (model spend
        is read from the ledger, never recomputed) plus the latest
        version's replay/heal rollups."""
        async with self._session_factory() as session:
            events = list(
                (
                    await session.execute(
                        select(SkillUsageEvent)
                        .where(SkillUsageEvent.skill_id == skill_id)
                        .order_by(SkillUsageEvent.created_at)
                    )
                ).scalars().all()
            )
            versions = list(
                (
                    await session.execute(
                        select(SkillVersion)
                        .where(SkillVersion.skill_id == skill_id)
                        .order_by(SkillVersion.version_number.desc())
                    )
                ).scalars().all()
            )
        by_kind: dict[str, int] = {}
        total_calls = 0
        total_tokens = 0
        diagnosis_calls = 0
        for event in events:
            by_kind[event.kind] = by_kind.get(event.kind, 0) + 1
            total_calls += event.model_calls or 0
            total_tokens += event.model_tokens or 0
            if event.kind == "heal_diagnosis":
                diagnosis_calls += event.model_calls or 0
        latest = versions[0] if versions else None
        return {
            "skill_id": str(skill_id),
            "total_model_calls": total_calls,
            "total_model_tokens": total_tokens,
            "diagnosis_model_calls": diagnosis_calls,
            "events_by_kind": by_kind,
            "latest_version": (
                {
                    "version_id": str(latest.id),
                    "version_number": latest.version_number,
                    "lifecycle_status": latest.lifecycle_status,
                    "replay_count": latest.replay_count,
                    "heal_count": latest.heal_count,
                    "last_replay_result": latest.last_replay_result,
                    "last_replay_at": (
                        latest.last_replay_at.isoformat()
                        if latest.last_replay_at is not None
                        else None
                    ),
                    "retired_reason": latest.retired_reason,
                }
                if latest is not None
                else None
            ),
        }

    async def skill_library_lines(
        self,
        *,
        workspace_id: UUID,
        application_id: UUID,
        target_id: UUID,
    ) -> list[dict[str, object]]:
        """Doc 22 section 12.2: one line per skill in the scope —
        the skill, its LATEST version's lifecycle and rollups, and
        its heal-diagnosis spend read from the ledger."""
        async with self._session_factory() as session:
            skills = list(
                (
                    await session.execute(
                        select(Skill)
                        .where(
                            Skill.workspace_id == workspace_id,
                            Skill.application_id == application_id,
                            Skill.target_id == target_id,
                        )
                        .order_by(Skill.name)
                    )
                ).scalars().all()
            )
            if not skills:
                return []
            versions = list(
                (
                    await session.execute(
                        select(SkillVersion)
                        .where(
                            SkillVersion.skill_id.in_([s.id for s in skills])
                        )
                        .order_by(SkillVersion.version_number.desc())
                    )
                ).scalars().all()
            )
            diagnosis_rows = list(
                (
                    await session.execute(
                        select(
                            SkillUsageEvent.skill_id,
                            func.coalesce(
                                func.sum(SkillUsageEvent.model_calls), 0
                            ),
                        )
                        .where(
                            SkillUsageEvent.skill_id.in_(
                                [s.id for s in skills]
                            ),
                            SkillUsageEvent.kind == "heal_diagnosis",
                        )
                        .group_by(SkillUsageEvent.skill_id)
                    )
                ).all()
            )
            reason_events = list(
                (
                    await session.execute(
                        select(SkillUsageEvent)
                        .where(
                            SkillUsageEvent.skill_id.in_(
                                [s.id for s in skills]
                            ),
                            SkillUsageEvent.kind.in_(
                                ("demotion", "quarantine")
                            ),
                        )
                        .order_by(SkillUsageEvent.created_at.desc())
                    )
                ).scalars().all()
            )
        latest: dict[UUID, SkillVersion] = {}
        for version in versions:
            latest.setdefault(version.skill_id, version)
        diagnosis = {row[0]: int(row[1]) for row in diagnosis_rows}
        reason_event: dict[UUID, SkillUsageEvent] = {}
        for event in reason_events:
            reason_event.setdefault(event.skill_id, event)

        def status_reason(
            lifecycle: str | None,
            retired_reason: str | None,
            event: SkillUsageEvent | None,
        ) -> str | None:
            if lifecycle == "retired":
                return retired_reason
            if lifecycle not in ("suspect", "quarantined") or event is None:
                return None
            payload = event.payload if isinstance(event.payload, dict) else {}
            demotion = payload.get("demotion")
            if isinstance(demotion, dict) and demotion.get("kind"):
                return str(demotion["kind"])
            if payload.get("reason"):
                return str(payload["reason"])
            heal = payload.get("heal_record")
            if isinstance(heal, dict) and heal.get("reason"):
                return str(heal["reason"])
            return event.kind
        lines: list[dict[str, object]] = []
        for skill in skills:
            version = latest.get(skill.id)
            definition = version.definition_json if version is not None else None
            task_block = (
                definition.get("task") if isinstance(definition, dict) else None
            )
            source = (
                task_block.get("source") if isinstance(task_block, dict) else None
            )
            source_kind = source.get("kind") if isinstance(source, dict) else None
            lines.append(
                {
                    "skill_id": skill.id,
                    "name": skill.name,
                    "skill_kind": skill.skill_kind,
                    "task_source_kind": (
                        source_kind if isinstance(source_kind, str) else None
                    ),
                    "lifecycle_status": (
                        version.lifecycle_status if version else None
                    ),
                    "version_id": version.id if version else None,
                    "version_number": (
                        version.version_number if version else None
                    ),
                    "last_replay_result": (
                        version.last_replay_result if version else None
                    ),
                    "last_replay_at": (
                        version.last_replay_at if version else None
                    ),
                    "replay_count": version.replay_count if version else 0,
                    "heal_count": version.heal_count if version else 0,
                    "retired_reason": (
                        version.retired_reason if version else None
                    ),
                    "diagnosis_model_calls": diagnosis.get(skill.id, 0),
                    "status_reason": status_reason(
                        version.lifecycle_status if version else None,
                        version.retired_reason if version else None,
                        reason_event.get(skill.id),
                    ),
                }
            )
        return lines

    async def reverify_skill(
        self, skill_id: UUID, *, current_map_id: UUID
    ) -> str:
        """Doc 22 section 12.2 reverify: run the point currency
        check for the skill's served (active) or verified version
        against the current map NOW. Outcomes: 'current' (the check
        passes; nothing changes), 'demoted' (an active version whose
        currency failed is demoted to suspect so the heal cycle
        engages), 'queued' (draft/suspect/replay_verified versions
        belong to the re-verification poller), 'not_found'."""
        async with self._session_factory() as session:
            skill = await session.get(Skill, skill_id)
            if skill is None:
                return "not_found"
            versions = list(
                (
                    await session.execute(
                        select(SkillVersion)
                        .where(SkillVersion.skill_id == skill_id)
                        .order_by(SkillVersion.version_number.desc())
                    )
                ).scalars().all()
            )
            app_map = await session.get(AppMap, current_map_id)
        if not versions or app_map is None:
            return "not_found"
        served = next(
            (v for v in versions if v.lifecycle_status == "active"), None
        )
        candidate = served or next(
            (v for v in versions if v.lifecycle_status == "replay_verified"),
            None,
        )
        if candidate is None:
            return "queued"
        if skill.skill_kind == "platform":
            current = candidate.app_map_id == current_map_id
        else:
            async with self._session_factory() as session:
                pages = list(
                    (
                        await session.execute(
                            select(MapPage).where(
                                MapPage.app_map_id == current_map_id
                            )
                        )
                    ).scalars().all()
                )
                states = list(
                    (
                        await session.execute(
                            select(MapPageState).where(
                                MapPageState.app_map_id == current_map_id
                            )
                        )
                    ).scalars().all()
                )
                journeys = list(
                    (
                        await session.execute(
                            select(MapJourney).where(
                                MapJourney.app_map_id == current_map_id
                            )
                        )
                    ).scalars().all()
                )
                source = None
                source_id = (
                    candidate.definition_json.get("source_journey_id")
                    if isinstance(candidate.definition_json, Mapping)
                    else None
                )
                if source_id:
                    source = await session.get(MapJourney, UUID(str(source_id)))
            base_page = next(
                (p for p in pages if p.canonical_url == app_map.base_url),
                pages[0] if pages else None,
            )
            default_identity = {
                s.map_page_id: s.state_id
                for s in states
                if s.state_key == "default"
            }
            identity_by_row = {s.id: s.state_id for s in states}
            start_state_id = (
                default_identity.get(base_page.id)
                if base_page is not None
                else None
            )
            current_journey = (
                {j.name: j for j in journeys}.get(source.name)
                if source is not None
                else None
            )
            if current_journey is None:
                current = False
            else:
                current = skill_currency_check(
                    candidate.verified_fingerprint,
                    start_state_id,
                    identity_by_row.get(current_journey.success_state_id),
                )
        if current:
            return "current"
        if served is None:
            return "queued"
        await self.transition_skill_version(
            version_id=served.id,
            to_status="suspect",
            kind="demotion",
            evidence={
                "demotion": {
                    "kind": "currency_mismatch",
                    "app_map_id": str(current_map_id),
                }
            },
            result="failed",
        )
        return "demoted"

    async def request_journey_compile(
        self, map_id: UUID, journey_id: UUID
    ) -> bool:
        """Doc 22 section 12.2: queue one journey's compilation into
        the library (the re-verification poller compiles on its next
        pass and clears the request). False when the journey is not
        on the map."""
        async with self._session_factory() as session:
            async with session.begin():
                journey = await session.get(MapJourney, journey_id)
                if journey is None or journey.app_map_id != map_id:
                    return False
                app_map = await session.get(AppMap, map_id)
                if app_map is None:
                    return False
                metrics = dict(app_map.harvest_metrics or {})
                requests = list(metrics.get("skill_compile_requests") or [])
                if str(journey_id) not in requests:
                    requests.append(str(journey_id))
                metrics["skill_compile_requests"] = requests
                app_map.harvest_metrics = metrics
                await session.flush()
                return True


def session_factory_for(session: AsyncSession) -> SessionFactory:
    """Adapt a caller-owned session to the repository's factory shape.

    The session is yielded as-is and is NOT closed on exit: ownership stays
    with the caller (run creation, whose transaction the map lookup joins).
    """

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        yield session

    return factory


async def latest_ready_map(
    session: AsyncSession, application_id: UUID, target_id: UUID
) -> AppMap | None:
    """Session-bound form of ``MapRepository.latest_ready_map`` for callers
    that already own a session (doc 14 section 9.3 run creation). The query
    itself lives in the repository class; this is only an adapter."""
    repository = MapRepository(session_factory_for(session))
    return await repository.latest_ready_map(application_id, target_id)


def freshness_summary(app_map: AppMap) -> dict:
    """The freshness facts every surface renders (doc 23 sections
    5.2, 8.1, 9.3): the map's own freshness columns plus the outcome
    counts its last preflight recorded. Pure — no session, no writes.
    """

    metrics = app_map.freshness_metrics or {}
    counts = metrics.get("outcome_counts")
    if not isinstance(counts, dict):
        counts = {}
    deferred = metrics.get("deferred_count")
    return {
        "state": app_map.freshness_state or "unknown",
        "last_preflight_at": (
            app_map.last_preflight_at.isoformat()
            if app_map.last_preflight_at is not None
            else None
        ),
        "last_preflight_id": metrics.get("preflight_id"),
        "outcome_counts": {
            name: counts.get(name) if isinstance(counts.get(name), int) else 0
            for name in FRESHNESS_OUTCOMES
        },
        "deferred_count": deferred if isinstance(deferred, int) else 0,
    }


def freshness_snapshot_block(
    app_map: AppMap,
    *,
    preflight_status: str,
    pinned_via_preflight: bool,
) -> dict:
    """The run snapshot's freshness block (doc 23 section 8.1): the
    pinned map's freshness summary plus what run creation did about
    it. TTL trust applies only when no preflight ran for this run
    (decision 5: preflight is for verdict runs; other kinds trust the
    map inside its TTL and say so)."""

    summary = freshness_summary(app_map)
    built_at = app_map.completed_at or app_map.started_at
    age_hours = 0
    if built_at is not None:
        age_hours = max(
            0, int((datetime.now(UTC) - built_at).total_seconds() // 3600)
        )
    if preflight_status == "not_required":
        ttl_trust = (
            "within" if age_hours <= MAP_TTL_TRUST_DAYS * 24 else "beyond"
        )
    else:
        ttl_trust = "not_applicable"
    return {
        "state": summary["state"],
        "map_built_at": built_at.isoformat() if built_at is not None else None,
        "map_age_hours": age_hours,
        "last_preflight_at": summary["last_preflight_at"],
        "last_preflight_id": summary["last_preflight_id"],
        "outcome_counts": summary["outcome_counts"],
        "pinned_via_preflight": pinned_via_preflight,
        "preflight_status": preflight_status,
        "ttl_trust": ttl_trust,
    }


async def create_preflight(
    session: AsyncSession, *, app_map: AppMap, trigger: str
) -> MapPreflight:
    """Session-bound preflight insert for run creation (doc 23
    section 6.2): added and flushed on the CALLER's session —
    committing it independently of the creation transaction is the
    caller's job, because the worker can only see committed rows. An
    IntegrityError from the single-flight index propagates; the
    caller joins the in-flight row instead."""

    preflight = MapPreflight(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        app_map_id=app_map.id,
        run_id=None,
        trigger=trigger,
        status="building",
        config={},
        started_at=datetime.now(UTC),
    )
    session.add(preflight)
    await session.flush()
    return preflight


async def get_preflight(
    session: AsyncSession, preflight_id: UUID
) -> MapPreflight | None:
    return await session.get(MapPreflight, preflight_id)


async def latest_preflight_for_map(
    session: AsyncSession, app_map_id: UUID
) -> MapPreflight | None:
    return await session.scalar(
        select(MapPreflight)
        .where(MapPreflight.app_map_id == app_map_id)
        .order_by(MapPreflight.started_at.desc())
    )
