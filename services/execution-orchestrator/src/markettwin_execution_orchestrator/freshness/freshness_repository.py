"""The freshness package's only database writer (doc 23 section 6.1).

Every freshness module reads and writes through this repository:
preflight rows and their events, fingerprint-history appends, the
section 5.4 freshness fields on the swept version, tier-2-verified
state touches, and the successor version's rows. History is
append-only (C9): this class exposes ``append_history`` and
``list_history_for_page`` for that table and no update or delete.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from markettwin_database.models import (
    AppMap,
    MapConflict,
    MapElement,
    MapEvidenceObject,
    MapExpectation,
    MapField,
    MapFingerprintHistory,
    MapForm,
    MapJourney,
    MapPage,
    MapPageState,
    MapPreflight,
    MapPreflightEvent,
    MapTransition,
    Skill,
    SkillVersion,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class FreshnessRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    # -- preflight rows -------------------------------------------------

    async def get_preflight(self, preflight_id: UUID) -> MapPreflight | None:
        async with self._session_factory() as session:
            return await session.get(MapPreflight, preflight_id)

    async def list_building_preflights(self, *, limit: int = 10) -> list[MapPreflight]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(MapPreflight)
                .where(MapPreflight.status == "building")
                .order_by(MapPreflight.started_at)
                .limit(limit)
            )
            return list(rows)

    async def record_event(
        self, preflight_id: UUID, event_type: str, payload: dict | None = None
    ) -> None:
        async with self._session_factory() as session, session.begin():
            session.add(
                MapPreflightEvent(
                    preflight_id=preflight_id,
                    event_type=event_type,
                    payload=payload or {},
                )
            )

    async def latest_event_at(self, preflight_id: UUID) -> datetime | None:
        async with self._session_factory() as session:
            return await session.scalar(
                select(MapPreflightEvent.occurred_at)
                .where(MapPreflightEvent.preflight_id == preflight_id)
                .order_by(MapPreflightEvent.occurred_at.desc())
                .limit(1)
            )

    async def set_resulting_map(self, preflight_id: UUID, resulting_map_id: UUID) -> None:
        async with self._session_factory() as session, session.begin():
            preflight = await session.get(MapPreflight, preflight_id)
            if preflight is not None:
                preflight.resulting_map_id = resulting_map_id

    async def complete_preflight(
        self,
        preflight_id: UUID,
        *,
        status: str,
        outcome: dict,
        deferred: list,
        tier_counts: dict,
        spend_seconds: float,
        completed_at: datetime,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            preflight = await session.get(MapPreflight, preflight_id)
            if preflight is None:
                return
            preflight.status = status
            preflight.outcome = outcome
            preflight.deferred = deferred
            preflight.tier_counts = tier_counts
            preflight.spend_seconds = spend_seconds
            preflight.completed_at = completed_at

    async def fail_preflight(
        self,
        preflight_id: UUID,
        *,
        failure_code: str,
        failure_message: str,
        failure_site: str,
        completed_at: datetime,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            preflight = await session.get(MapPreflight, preflight_id)
            if preflight is None:
                return
            preflight.status = "failed"
            preflight.failure_code = failure_code
            preflight.failure_message = failure_message[:2000]
            preflight.failure_site = failure_site
            preflight.completed_at = completed_at

    # -- the swept version's freshness fields (section 5.4's list) -------

    async def get_map(self, app_map_id: UUID) -> AppMap | None:
        async with self._session_factory() as session:
            return await session.get(AppMap, app_map_id)

    async def update_map_freshness(
        self,
        app_map_id: UUID,
        *,
        freshness_state: str,
        last_preflight_at: datetime,
        freshness_metrics: dict,
    ) -> None:
        """The ONLY write this package makes to a swept version's own
        map row: the three section 5.2 freshness fields."""

        async with self._session_factory() as session, session.begin():
            app_map = await session.get(AppMap, app_map_id)
            if app_map is None:
                return
            app_map.freshness_state = freshness_state
            app_map.last_preflight_at = last_preflight_at
            app_map.freshness_metrics = freshness_metrics

    async def list_pages(self, app_map_id: UUID) -> list[MapPage]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(MapPage)
                .where(MapPage.app_map_id == app_map_id)
                .order_by(MapPage.canonical_url)
            )
            return list(rows)

    async def list_states(self, app_map_id: UUID) -> list[MapPageState]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(MapPageState).where(MapPageState.app_map_id == app_map_id)
            )
            return list(rows)

    async def touch_verified_state(
        self,
        state_row_id: UUID,
        *,
        last_verified_at: datetime,
        screenshot_phash: str | None,
    ) -> None:
        """Section 5.4's state writes: a tier-2-verified state's
        ``last_verified_at`` and (first write) its ``screenshot_phash``.
        Nothing else on the row is touched."""

        async with self._session_factory() as session, session.begin():
            state = await session.get(MapPageState, state_row_id)
            if state is None:
                return
            state.last_verified_at = last_verified_at
            if state.screenshot_phash is None and screenshot_phash is not None:
                state.screenshot_phash = screenshot_phash

    # -- fingerprint history (append + read only, C9) --------------------

    async def append_history(self, rows: list[dict]) -> None:
        if not rows:
            return
        async with self._session_factory() as session, session.begin():
            for row in rows:
                session.add(MapFingerprintHistory(id=uuid4(), **row))

    async def list_history_for_page(
        self,
        *,
        application_id: UUID,
        target_id: UUID,
        canonical_url: str,
        state_key: str,
    ) -> list[MapFingerprintHistory]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(MapFingerprintHistory)
                .where(
                    MapFingerprintHistory.application_id == application_id,
                    MapFingerprintHistory.target_id == target_id,
                    MapFingerprintHistory.canonical_url == canonical_url,
                    MapFingerprintHistory.state_key == state_key,
                )
                .order_by(MapFingerprintHistory.observed_at)
            )
            return list(rows)

    # -- successor versions (doc 23 section 7) ---------------------------

    async def get_page_by_url(
        self, app_map_id: UUID, canonical_url: str
    ) -> MapPage | None:
        async with self._session_factory() as session:
            return await session.scalar(
                select(MapPage).where(
                    MapPage.app_map_id == app_map_id,
                    MapPage.canonical_url == canonical_url,
                )
            )

    async def list_journeys(self, app_map_id: UUID) -> list[MapJourney]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(MapJourney).where(MapJourney.app_map_id == app_map_id)
            )
            return list(rows)

    async def mint_successor(
        self,
        base: AppMap,
        *,
        preflight: MapPreflight,
        builder_version: str,
        freshness_metrics: dict,
        completed_at: datetime,
    ) -> AppMap:
        """Create version V+1 of the base's (application, target) in
        ``building`` (doc 23 section 7.1): census/harvest ledgers carry
        forward, mapping spend starts at zero (the successor's own
        scoped enrichment accounts on its own row, section 7.4), and
        the version is born ``current`` — reconcile just verified it
        page by page (section 7.3). Its grounding_status is the base's
        own: the expectations and conflicts copy forward with the
        version (see copy_forward), so the successor serves the same
        oracle the base served instead of an ungrounded empty one."""

        async with self._session_factory() as session, session.begin():
            successor = AppMap(
                id=uuid4(),
                workspace_id=base.workspace_id,
                application_id=base.application_id,
                target_id=base.target_id,
                version_number=base.version_number + 1,
                status="building",
                release_state=None,
                release_scope=None,
                base_url=base.base_url,
                builder_version=builder_version,
                census_config={
                    "origin": "reconcile",
                    "base_map_id": str(base.id),
                    "preflight_id": str(preflight.id),
                },
                census_metrics=dict(base.census_metrics or {}),
                pattern_stats=dict(base.pattern_stats or {}),
                gate_metrics={},
                census_expected_count=base.census_expected_count,
                census_reachable_count=base.census_reachable_count,
                mapping_spend_calls=0,
                mapping_spend_tokens=0,
                mapping_spend_seconds=0.0,
                started_at=completed_at,
                harvest_status="building",
                harvest_metrics=dict(base.harvest_metrics or {}),
                harvest_started_at=completed_at,
                grounding_status=base.grounding_status or "not_started",
                grounding_metrics={},
                freshness_state="current",
                last_preflight_at=completed_at,
                freshness_metrics=freshness_metrics,
            )
            session.add(successor)
            await session.flush()
            return successor

    async def copy_forward(
        self,
        *,
        base: AppMap,
        successor: AppMap,
        changed_urls: set[str],
        missing_urls: set[str],
        new_pages: list[dict],
        observed_at: datetime,
    ) -> dict:
        """Copy the base's rows forward under the successor (section
        7.2): unchanged pages verbatim, missing pages as ``gone``,
        changed pages as census rows plus a fresh seeded default state
        (their inventory is re-observed by the visit seam, never
        copied stale), new pages as census-grade rows from the sweep's
        facts. Evidence rows keep the base's object keys — the objects
        are shared, never re-uploaded. Journeys and transitions that
        touch a changed page's states are not copied (their state rows
        are being replaced; the library recompiles journeys against
        the successor) and are counted in the ledger. Expectations and
        conflicts carry too (programme decision after doc 23: section
        7.2's list predates the serving fact that expectations are
        read by map version, so a successor without them would
        silently lose the run's oracle). An expectation copies when
        its subject row copied, its subject id remapped per kind; one
        whose subject was not copied is skipped and counted.
        Page-anchored expectations on a changed page still copy — the
        page row exists on the successor — and are counted as
        expectations_carried_changed so the fact stays visible."""

        from markettwin_shared.app_map_common import route_pattern_for

        from markettwin_execution_orchestrator.freshness.reconcile import (
            carried_row_values,
        )

        remap_base = {"app_map_id": {base.id: successor.id}}
        ledger = {
            "carried": 0,
            "changed": 0,
            "new": len(new_pages),
            "missing": 0,
            "journeys_skipped": 0,
            "transitions_skipped": 0,
            "expectations_carried": 0,
            "expectations_carried_changed": 0,
            "expectations_skipped": 0,
            "conflicts_carried": 0,
            "conflicts_skipped": 0,
        }
        async with self._session_factory() as session, session.begin():
            base_pages = list(
                await session.scalars(
                    select(MapPage)
                    .where(MapPage.app_map_id == base.id)
                    .order_by(MapPage.canonical_url)
                )
            )
            page_id_map: dict[UUID, UUID] = {}
            changed_page_ids: set[UUID] = set()
            for page in base_pages:
                overrides: dict = {}
                if page.canonical_url in missing_urls:
                    overrides["crawl_status"] = "gone"
                    ledger["missing"] += 1
                elif page.canonical_url in changed_urls:
                    # Re-observation is pending: the page counts as
                    # unvisited until the visit seam dispositions it.
                    overrides["harvest_status"] = None
                    changed_page_ids.add(page.id)
                    ledger["changed"] += 1
                else:
                    ledger["carried"] += 1
                values = carried_row_values(
                    page, remap=remap_base, overrides=overrides
                )
                session.add(MapPage(**values))
                page_id_map[page.id] = values["id"]

            new_page_id_map: dict[str, UUID] = {}
            for entry in new_pages:
                fingerprint = entry.get("fingerprint")
                page_id = uuid4()
                session.add(
                    MapPage(
                        id=page_id,
                        workspace_id=successor.workspace_id,
                        application_id=successor.application_id,
                        target_id=successor.target_id,
                        app_map_id=successor.id,
                        canonical_url=entry["canonical_url"],
                        route_pattern=route_pattern_for(entry["canonical_url"]),
                        source_kinds=list(entry["source_kinds"]),
                        crawl_status=_new_page_disposition(fingerprint),
                        http_status=(
                            fingerprint.http_status if fingerprint else None
                        ),
                        redirect_target=(
                            fingerprint.redirect_target if fingerprint else None
                        ),
                        content_type=(
                            fingerprint.content_type if fingerprint else None
                        ),
                        title=fingerprint.title if fingerprint else None,
                        html_sha256=(
                            fingerprint.html_sha256 if fingerprint else None
                        ),
                        requires_auth=False,
                        roles_seen=[],
                        source="preflight",
                        confidence="low",
                        last_verified_at=None,
                        harvest_status=None,
                    )
                )
                new_page_id_map[entry["canonical_url"]] = page_id

            base_states = list(
                await session.scalars(
                    select(MapPageState).where(
                        MapPageState.app_map_id == base.id
                    )
                )
            )
            state_id_map: dict[UUID, UUID] = {}
            for state in base_states:
                if state.map_page_id in changed_page_ids:
                    continue
                values = carried_row_values(
                    state,
                    remap={
                        **remap_base,
                        "map_page_id": page_id_map,
                    },
                )
                session.add(MapPageState(**values))
                state_id_map[state.id] = values["id"]
            seeded_page_ids = [
                page_id_map[page_id] for page_id in changed_page_ids
            ] + list(new_page_id_map.values())
            for page_id in seeded_page_ids:
                session.add(
                    MapPageState(
                        id=uuid4(),
                        workspace_id=successor.workspace_id,
                        application_id=successor.application_id,
                        target_id=successor.target_id,
                        app_map_id=successor.id,
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

            base_elements = list(
                await session.scalars(
                    select(MapElement).where(MapElement.app_map_id == base.id)
                )
            )
            element_id_map: dict[UUID, UUID] = {}
            for element in base_elements:
                if element.map_page_state_id not in state_id_map:
                    continue
                values = carried_row_values(
                    element,
                    remap={
                        **remap_base,
                        "map_page_id": page_id_map,
                        "map_page_state_id": state_id_map,
                    },
                )
                session.add(MapElement(**values))
                element_id_map[element.id] = values["id"]

            base_transitions = list(
                await session.scalars(
                    select(MapTransition).where(
                        MapTransition.app_map_id == base.id
                    )
                )
            )
            transition_id_map: dict[UUID, UUID] = {}
            for transition in base_transitions:
                if (
                    transition.from_state_id not in state_id_map
                    or transition.to_state_id not in state_id_map
                ):
                    ledger["transitions_skipped"] += 1
                    continue
                values = carried_row_values(
                    transition,
                    remap={
                        **remap_base,
                        "from_state_id": state_id_map,
                        "to_state_id": state_id_map,
                        "via_element_id": element_id_map,
                    },
                )
                session.add(MapTransition(**values))
                transition_id_map[transition.id] = values["id"]

            base_forms = list(
                await session.scalars(
                    select(MapForm).where(MapForm.app_map_id == base.id)
                )
            )
            form_id_map: dict[UUID, UUID] = {}
            for form in base_forms:
                if form.map_page_state_id not in state_id_map:
                    continue
                overrides = {}
                if (
                    form.submit_element_id is not None
                    and form.submit_element_id not in element_id_map
                ):
                    overrides["submit_element_id"] = None
                if (
                    form.success_transition_id is not None
                    and form.success_transition_id not in transition_id_map
                ):
                    overrides["success_transition_id"] = None
                values = carried_row_values(
                    form,
                    remap={
                        **remap_base,
                        "map_page_id": page_id_map,
                        "map_page_state_id": state_id_map,
                        "submit_element_id": element_id_map,
                        "success_transition_id": transition_id_map,
                    },
                    overrides=overrides,
                )
                session.add(MapForm(**values))
                form_id_map[form.id] = values["id"]

            base_fields = list(
                await session.scalars(
                    select(MapField).where(MapField.app_map_id == base.id)
                )
            )
            field_id_map: dict[UUID, UUID] = {}
            for field_row in base_fields:
                if field_row.form_id not in form_id_map:
                    continue
                overrides = {}
                if (
                    field_row.element_id is not None
                    and field_row.element_id not in element_id_map
                ):
                    overrides["element_id"] = None
                values = carried_row_values(
                    field_row,
                    remap={
                        **remap_base,
                        "form_id": form_id_map,
                        "element_id": element_id_map,
                    },
                    overrides=overrides,
                )
                session.add(MapField(**values))
                field_id_map[field_row.id] = values["id"]

            base_journeys = list(
                await session.scalars(
                    select(MapJourney).where(MapJourney.app_map_id == base.id)
                )
            )
            state_key_by_str = {str(key): str(value) for key, value in state_id_map.items()}
            element_key_by_str = {
                str(key): str(value) for key, value in element_id_map.items()
            }
            journey_id_map: dict[UUID, UUID] = {}
            for journey in base_journeys:
                steps = journey.steps or []
                step_state_ids = [
                    step.get("map_page_state_id")
                    for step in steps
                    if isinstance(step, dict)
                ]
                if journey.success_state_id not in state_id_map or any(
                    step_state_id not in state_key_by_str
                    for step_state_id in step_state_ids
                ):
                    ledger["journeys_skipped"] += 1
                    continue
                new_steps = []
                for step in steps:
                    if not isinstance(step, dict):
                        new_steps.append(step)
                        continue
                    copied = dict(step)
                    copied["map_page_state_id"] = state_key_by_str[
                        copied["map_page_state_id"]
                    ]
                    element_ref = copied.get("element_id")
                    if element_ref in element_key_by_str:
                        copied["element_id"] = element_key_by_str[element_ref]
                    new_steps.append(copied)
                values = carried_row_values(
                    journey,
                    remap={
                        **remap_base,
                        "success_state_id": state_id_map,
                    },
                    overrides={"steps": new_steps},
                )
                session.add(MapJourney(**values))
                journey_id_map[journey.id] = values["id"]

            base_evidence = list(
                await session.scalars(
                    select(MapEvidenceObject).where(
                        MapEvidenceObject.app_map_id == base.id
                    )
                )
            )
            for evidence in base_evidence:
                if evidence.map_page_state_id not in state_id_map:
                    continue
                values = carried_row_values(
                    evidence,
                    remap={
                        **remap_base,
                        "map_page_id": page_id_map,
                        "map_page_state_id": state_id_map,
                    },
                )
                session.add(MapEvidenceObject(**values))

            base_expectations = list(
                await session.scalars(
                    select(MapExpectation).where(
                        MapExpectation.app_map_id == base.id
                    )
                )
            )
            subject_maps = {
                "page": page_id_map,
                "element": element_id_map,
                "journey": journey_id_map,
                "field": field_id_map,
                "form": form_id_map,
            }
            expectation_id_map: dict[UUID, UUID] = {}
            carried_expectations: list[dict] = []
            for expectation in base_expectations:
                new_subject_id = subject_maps.get(
                    expectation.subject_kind, {}
                ).get(expectation.subject_id)
                if new_subject_id is None:
                    # The subject row was not copied (its state is
                    # being replaced): skip and count, never dangle.
                    ledger["expectations_skipped"] += 1
                    continue
                values = carried_row_values(
                    expectation,
                    remap=remap_base,
                    overrides={"subject_id": new_subject_id},
                )
                expectation_id_map[expectation.id] = values["id"]
                carried_expectations.append(values)
                ledger["expectations_carried"] += 1
                if (
                    expectation.subject_kind == "page"
                    and expectation.subject_id in changed_page_ids
                ):
                    ledger["expectations_carried_changed"] += 1
            for values in carried_expectations:
                # A supersession pointer means something on the
                # successor only when its target carried too; an
                # uncarried target is nulled (the form-field
                # discipline for unmapped optional references), never
                # left pointing at the base version's row.
                if values["superseded_by_id"] is not None:
                    values["superseded_by_id"] = expectation_id_map.get(
                        values["superseded_by_id"]
                    )
                session.add(MapExpectation(**values))

            base_conflicts = list(
                await session.scalars(
                    select(MapConflict).where(
                        MapConflict.app_map_id == base.id
                    )
                )
            )
            observed_subject_remap: dict[UUID, UUID] = {
                **page_id_map,
                **state_id_map,
                **element_id_map,
                **form_id_map,
                **field_id_map,
                **journey_id_map,
                **transition_id_map,
            }
            for conflict in base_conflicts:
                if conflict.expectation_id not in expectation_id_map:
                    ledger["conflicts_skipped"] += 1
                    continue
                values = carried_row_values(
                    conflict,
                    remap={
                        **remap_base,
                        "expectation_id": expectation_id_map,
                        "observed_subject_id": observed_subject_remap,
                    },
                )
                session.add(MapConflict(**values))
                ledger["conflicts_carried"] += 1
        return ledger

    async def page_status_counts(self, app_map_id: UUID) -> dict[str, int]:
        """crawl_status -> row count for one version (the inventory
        gate's input, doc 23 section 7.3)."""

        async with self._session_factory() as session:
            result = await session.execute(
                select(MapPage.crawl_status, func.count())
                .where(MapPage.app_map_id == app_map_id)
                .group_by(MapPage.crawl_status)
            )
            return {status: count for status, count in result.all()}

    async def harvest_counts(self, app_map_id: UUID) -> dict[str, object]:
        """Gate counts for one version (doc 16 section 5.9's shape):
        census-reachable pages split by harvest disposition, plus the
        group/spend/skill facts the shared gate consumes — assembled
        exactly as control-api's repository assembles them, so the
        successor's gate is the same gate."""

        from markettwin_shared.app_map_common import REACHABLE_STATUSES

        from markettwin_execution_orchestrator.harvest.harvest_repository import (
            harvest_metric_counts,
        )

        async with self._session_factory() as session:
            app_map = await session.get(AppMap, app_map_id)
            result = await session.execute(
                select(MapPage.harvest_status, func.count())
                .where(
                    MapPage.app_map_id == app_map_id,
                    MapPage.crawl_status.in_(REACHABLE_STATUSES),
                )
                .group_by(MapPage.harvest_status)
            )
            by_status = {status: count for status, count in result.all()}
            skill_verified = False
            if app_map is not None:
                versions = await session.scalars(
                    select(SkillVersion)
                    .join(Skill, Skill.id == SkillVersion.skill_id)
                    .where(
                        Skill.workspace_id == app_map.workspace_id,
                        Skill.application_id == app_map.application_id,
                        Skill.target_id == app_map.target_id,
                        SkillVersion.lifecycle_status.in_(
                            ("replay_verified", "active")
                        ),
                    )
                )
                skill_verified = any(True for _ in versions)
        template_groups, enriched_groups = harvest_metric_counts(
            app_map.harvest_metrics if app_map is not None else None
        )
        return {
            "reachable": sum(by_status.values()),
            "visited": by_status.get("visited", 0),
            "blocked_auth": by_status.get("blocked_auth", 0),
            "blocked_wall": by_status.get("blocked_wall", 0),
            "failed": by_status.get("failed", 0),
            "unprobed_budget": by_status.get("unprobed_budget", 0),
            "pending": by_status.get(None, 0) + by_status.get("pending", 0),
            "enriched_groups": enriched_groups,
            "template_groups": template_groups,
            "spend_calls": (app_map.mapping_spend_calls or 0) if app_map else 0,
            "spend_tokens": (app_map.mapping_spend_tokens or 0) if app_map else 0,
            "skill_verified": skill_verified,
            "skill_reason": None if skill_verified else "no_verified_skill",
        }

    async def apply_successor_gates(
        self,
        successor: AppMap,
        *,
        release: dict,
        ledger: dict,
    ) -> None:
        """Land the gate verdicts on the successor (section 7.3): the
        release pair, the recomputed census counts, the gate metrics,
        and the reconcile ledger appended to the carried census
        metrics."""

        async with self._session_factory() as session, session.begin():
            row = await session.get(AppMap, successor.id)
            if row is None:
                return
            count_rows = await session.execute(
                select(MapPage.crawl_status, func.count())
                .where(MapPage.app_map_id == successor.id)
                .group_by(MapPage.crawl_status)
            )
            counts = {status: count for status, count in count_rows.all()}
            row.status = release["status"]
            row.harvest_status = release["harvest_status"]
            row.release_state = release["release_state"]
            row.release_scope = release["release_scope"]
            row.failure_code = release["failure_code"]
            row.failure_message = release["failure_message"]
            row.gate_metrics = release["gate_metrics"]
            row.census_expected_count = sum(counts.values())
            row.census_reachable_count = counts.get("fetch_ok", 0) + counts.get(
                "redirect", 0
            )
            metrics = dict(row.census_metrics or {})
            metrics["reconcile"] = {
                "preflight_id": (row.census_config or {}).get("preflight_id"),
                **ledger,
            }
            row.census_metrics = metrics
            now = datetime.now(UTC)
            if release["status"] in ("ready", "failed"):
                row.completed_at = now
            if release["harvest_status"] in ("ready", "partial", "failed"):
                row.harvest_completed_at = now

    async def mark_reconciled_states(
        self, app_map_id: UUID, page_id: UUID, *, observed_at: datetime
    ) -> None:
        """Provenance for re-observed states (section 5.4): the visit
        seam's rows on a changed page belong to the reconcile, so
        their source says so and their verification time is the
        sweep's."""

        async with self._session_factory() as session, session.begin():
            states = await session.scalars(
                select(MapPageState).where(
                    MapPageState.app_map_id == app_map_id,
                    MapPageState.map_page_id == page_id,
                )
            )
            for state in states:
                state.source = "reconcile"
                state.last_verified_at = observed_at


def _new_page_disposition(fingerprint) -> str:
    """The census-grade crawl_status for a page the sweep found
    (section 7.2 step 3): the fetch's own facts, nothing inferred."""

    if fingerprint is None or fingerprint.http_status is None:
        return "fetch_error"
    if fingerprint.http_status in (404, 410):
        return "gone"
    if fingerprint.redirect_target:
        return "redirect"
    if fingerprint.http_status < 400:
        return "fetch_ok"
    return "fetch_error"
