"""Persistence for the Phase 1b harvest (doc 16 sections 5 and 6).

``HarvestRepository`` is the ONLY database writer the harvest modules
use: the job, capture, inventory, enrichment, compile, and replay
stages all write through here, so the write surface stays auditable in
one place (the enrichment spend sink of doc 27 R2 is the
``record_enrichment_spend`` method below, called from exactly one
module). Sessions come from an injected factory — the worker's runtime
factory in production, fakes in tests.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from markettwin_database.models.knowledge import (
    AppMap,
    MapElement,
    MapEvidenceObject,
    MapField,
    MapForm,
    MapHarvestEvent,
    MapJourney,
    MapPage,
    MapPageState,
    MapTransition,
    Skill,
    SkillReplay,
    SkillUsageEvent,
    SkillVersion,
)
from markettwin_shared.app_map_common import HarvestGateResult
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.persistence.skill_creation import create_draft_version

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

REACHABLE_STATUSES = ("fetch_ok", "redirect")
FAILURE_LIST_CAP = 50
HARVEST_GATE_FAILURE_SITE = "harvest_repository:apply_gate"


def _now() -> datetime:
    return datetime.now(UTC)


def harvest_metric_counts(
    harvest_metrics: dict[str, object] | None,
) -> tuple[int, int]:
    """(template_groups, enriched_groups) from the job's metrics
    ledger. Defensive mirror of the control-api reader: a partially
    written ledger reads as zero, never raises."""
    if not isinstance(harvest_metrics, dict):
        return (0, 0)
    groups = harvest_metrics.get("template_groups")
    if not isinstance(groups, dict):
        return (0, 0)
    total = groups.get("groups")
    unenriched = groups.get("unenriched_groups")
    total_int = total if isinstance(total, int) else 0
    unenriched_int = len(unenriched) if isinstance(unenriched, list) else 0
    return (total_int, max(total_int - unenriched_int, 0))


class HarvestRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    # --- job lifecycle -----------------------------------------------------

    async def get_map(self, map_id: UUID) -> AppMap | None:
        async with self._session_factory() as session:
            return await session.get(AppMap, map_id)

    async def list_building_harvests(self) -> list[AppMap]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AppMap)
                .where(AppMap.harvest_status == "building")
                .order_by(AppMap.harvest_started_at)
            )
            return list(result.scalars().all())

    async def record_event(
        self, map_id: UUID, event_type: str, payload: dict[str, object]
    ) -> None:
        """Append one harvest event (doc 16 section 6.4). The event
        stream doubles as the job's watchdog heartbeat, so every stage
        boundary and page disposition lands here."""
        async with self._session_factory() as session:
            async with session.begin():
                session.add(
                    MapHarvestEvent(
                        id=uuid4(),
                        app_map_id=map_id,
                        event_type=event_type,
                        payload=payload,
                        occurred_at=_now(),
                    )
                )
                await session.flush()

    async def latest_event_at(self, map_id: UUID) -> datetime | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.max(MapHarvestEvent.occurred_at)).where(
                    MapHarvestEvent.app_map_id == map_id
                )
            )
            return result.scalar()

    async def fail_harvest(
        self,
        map_id: UUID,
        *,
        failure_code: str,
        failure_message: str,
        failure_site: str,
    ) -> None:
        """Crash path (doc 16 section 12): the original error is
        retained on the map row; the gate is never evaluated for a
        crashed job."""
        async with self._session_factory() as session:
            async with session.begin():
                app_map = await session.get(AppMap, map_id)
                if app_map is None:
                    return
                app_map.harvest_status = "failed"
                app_map.harvest_failure_code = failure_code
                app_map.harvest_failure_message = failure_message
                app_map.harvest_failure_site = failure_site
                app_map.harvest_completed_at = _now()
                await session.flush()

    async def apply_gate(self, map_id: UUID, *, gate: HarvestGateResult) -> None:
        """Write the shared gate function's outcome (doc 16 section
        5.9): the harvest block merges into gate_metrics over the
        census keys; release_state comes from the gate (always
        'partial' — no path to 'trusted')."""
        async with self._session_factory() as session:
            async with session.begin():
                app_map = await session.get(AppMap, map_id)
                if app_map is None:
                    return
                app_map.harvest_status = gate.harvest_status
                app_map.harvest_failure_code = gate.failure_code
                app_map.harvest_failure_message = gate.failure_message
                app_map.harvest_failure_site = (
                    HARVEST_GATE_FAILURE_SITE if gate.failure_code else None
                )
                app_map.harvest_completed_at = _now()
                merged = dict(app_map.gate_metrics or {})
                merged.update(gate.metrics())
                app_map.gate_metrics = merged
                app_map.release_state = gate.release_state
                app_map.release_scope = gate.release_scope
                await session.flush()

    async def harvest_counts(self, map_id: UUID) -> dict[str, int]:
        """Gate counts for one map: census-reachable pages split by
        harvest disposition; NULL and 'pending' both count as pending."""
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

    # --- metrics ledger ------------------------------------------------------

    async def save_harvest_metrics(
        self, map_id: UUID, updates: dict[str, object]
    ) -> dict[str, object]:
        """Merge-write keys into the map's harvest_metrics ledger and
        return the merged ledger."""
        async with self._session_factory() as session:
            async with session.begin():
                app_map = await session.get(AppMap, map_id)
                if app_map is None:
                    return {}
                merged = dict(app_map.harvest_metrics or {})
                merged.update(updates)
                app_map.harvest_metrics = merged
                await session.flush()
                return merged

    async def append_page_failure(
        self, map_id: UUID, failure: dict[str, object]
    ) -> None:
        """Record one per-page failure in the ledger (doc 16 section
        12): the list is capped, overflow is counted, the job goes on."""
        async with self._session_factory() as session:
            async with session.begin():
                app_map = await session.get(AppMap, map_id)
                if app_map is None:
                    return
                merged = dict(app_map.harvest_metrics or {})
                failures = list(merged.get("failures") or [])
                if len(failures) < FAILURE_LIST_CAP:
                    failures.append(failure)
                else:
                    merged["failures_overflow"] = (
                        int(merged.get("failures_overflow") or 0) + 1
                    )
                merged["failures"] = failures
                app_map.harvest_metrics = merged
                await session.flush()

    # --- work list and pages ---------------------------------------------------

    async def work_list(self, app_map: AppMap) -> list[MapPage]:
        """The harvest visit order (doc 16 section 5.2): the base-URL
        page first, then BFS over the census link topology — the census
        inserted link-graph pages in BFS discovery order, so insertion
        order replays it — then pages with no link provenance by
        canonical URL."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapPage).where(
                    MapPage.app_map_id == app_map.id,
                    MapPage.crawl_status.in_(REACHABLE_STATUSES),
                )
            )
            pages = list(result.scalars().all())
        base_url = app_map.base_url
        by_insertion = sorted(
            pages, key=lambda page: (page.created_at or _now(), str(page.id))
        )
        base = [page for page in by_insertion if page.canonical_url == base_url]
        linked = [
            page
            for page in by_insertion
            if page.canonical_url != base_url
            and "link_graph" in (page.source_kinds or [])
        ]
        rest = sorted(
            (
                page
                for page in by_insertion
                if page.canonical_url != base_url
                and "link_graph" not in (page.source_kinds or [])
            ),
            key=lambda page: page.canonical_url,
        )
        return base + linked + rest

    async def find_page_by_url(
        self, map_id: UUID, canonical_url_value: str
    ) -> MapPage | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapPage).where(
                    MapPage.app_map_id == map_id,
                    MapPage.canonical_url == canonical_url_value,
                )
            )
            return result.scalars().first()

    async def mark_page_harvest(self, page_id: UUID, status: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                page = await session.get(MapPage, page_id)
                if page is None:
                    return
                page.harvest_status = status
                await session.flush()

    async def set_page_template_group(
        self, page_id: UUID, template_group: str | None
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                page = await session.get(MapPage, page_id)
                if page is None:
                    return
                page.template_group = template_group
                await session.flush()

    async def set_page_purpose(
        self,
        page_id: UUID,
        *,
        purpose: str,
        purpose_source: str,
        template_group: str | None,
    ) -> None:
        """The enrichment write (doc 16 section 5.6): purposes only,
        stamped with their oracle source ('model-draft')."""
        async with self._session_factory() as session:
            async with session.begin():
                page = await session.get(MapPage, page_id)
                if page is None:
                    return
                page.purpose = purpose
                page.purpose_source = purpose_source
                page.template_group = template_group
                page.enriched_at = _now()
                await session.flush()

    # --- states, elements, forms, transitions --------------------------------

    async def get_default_state(self, page_id: UUID) -> MapPageState | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapPageState).where(
                    MapPageState.map_page_id == page_id,
                    MapPageState.state_key == "default",
                )
            )
            return result.scalars().first()

    async def get_state(self, state_id: UUID) -> MapPageState | None:
        async with self._session_factory() as session:
            return await session.get(MapPageState, state_id)

    async def list_states(self, page_id: UUID) -> list[MapPageState]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapPageState)
                .where(MapPageState.map_page_id == page_id)
                .order_by(MapPageState.state_key)
            )
            return list(result.scalars().all())

    async def complete_default_state(
        self,
        state_id: UUID,
        *,
        state_id_value: str | None,
        element_signature: str | None,
        form_signature: str | None,
        dom_structure_hash: str | None,
        aria_hash: str | None,
        screenshot_hash: str | None,
    ) -> None:
        """Complete the census-created default state IN PLACE with the
        harvested capture (doc 16 section 5.4): the single sanctioned
        census-row mutation — signatures, identity, and hashes land,
        and the row's provenance upgrades to harvest/high."""
        async with self._session_factory() as session:
            async with session.begin():
                state = await session.get(MapPageState, state_id)
                if state is None:
                    return
                state.state_id = state_id_value
                state.element_signature = element_signature
                state.form_signature = form_signature
                state.dom_structure_hash = dom_structure_hash
                state.aria_hash = aria_hash
                state.screenshot_hash = screenshot_hash
                state.source = "harvest"
                state.confidence = "high"
                state.last_verified_at = _now()
                await session.flush()

    async def create_observed_state(
        self,
        app_map: AppMap,
        page: MapPage,
        *,
        state_key: str,
        state_kind: str,
        state_id_value: str | None,
        element_signature: str | None,
        form_signature: str | None,
        dom_structure_hash: str | None,
        aria_hash: str | None,
        screenshot_hash: str | None,
    ) -> MapPageState:
        async with self._session_factory() as session:
            async with session.begin():
                row = MapPageState(
                    id=uuid4(),
                    workspace_id=app_map.workspace_id,
                    application_id=app_map.application_id,
                    target_id=app_map.target_id,
                    app_map_id=app_map.id,
                    map_page_id=page.id,
                    state_key=state_key,
                    state_kind=state_kind,
                    state_id=state_id_value,
                    element_signature=element_signature,
                    form_signature=form_signature,
                    dom_structure_hash=dom_structure_hash,
                    aria_hash=aria_hash,
                    screenshot_hash=screenshot_hash,
                    source="harvest",
                    confidence="high",
                    last_verified_at=_now(),
                )
                session.add(row)
                await session.flush()
                return row

    async def insert_elements(
        self,
        app_map: AppMap,
        page: MapPage,
        state: MapPageState,
        elements: list[dict[str, object]],
    ) -> list[MapElement]:
        async with self._session_factory() as session:
            async with session.begin():
                rows: list[MapElement] = []
                for element in elements:
                    row = MapElement(
                        id=uuid4(),
                        workspace_id=app_map.workspace_id,
                        application_id=app_map.application_id,
                        target_id=app_map.target_id,
                        app_map_id=app_map.id,
                        map_page_id=page.id,
                        map_page_state_id=state.id,
                        role=str(element["role"]),
                        name=str(element["name"]),
                        ordinal=int(element["ordinal"]),
                        label_text=element.get("label_text"),  # type: ignore[arg-type]
                        actionability=str(element["actionability"]),
                        locators=list(element.get("locators") or []),  # type: ignore[arg-type]
                        safety_class=str(element["safety_class"]),
                        navigates_to_url=element.get("navigates_to_url"),  # type: ignore[arg-type]
                        opens_state_key=None,
                        source="harvest",
                        confidence="high",
                        last_verified_at=_now(),
                    )
                    session.add(row)
                    rows.append(row)
                await session.flush()
                return rows

    async def set_element_opens_state(
        self, element_id: UUID, state_key: str
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                element = await session.get(MapElement, element_id)
                if element is None:
                    return
                element.opens_state_key = state_key
                await session.flush()

    async def set_element_navigates(self, element_id: UUID, url: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                element = await session.get(MapElement, element_id)
                if element is None:
                    return
                element.navigates_to_url = url
                await session.flush()

    async def insert_forms(
        self,
        app_map: AppMap,
        page: MapPage,
        state: MapPageState,
        forms: list[dict[str, object]],
    ) -> list[MapForm]:
        async with self._session_factory() as session:
            async with session.begin():
                rows: list[MapForm] = []
                for form in forms:
                    form_row = MapForm(
                        id=uuid4(),
                        workspace_id=app_map.workspace_id,
                        application_id=app_map.application_id,
                        target_id=app_map.target_id,
                        app_map_id=app_map.id,
                        map_page_id=page.id,
                        map_page_state_id=state.id,
                        form_key=str(form["form_key"]),
                        method=form.get("method"),  # type: ignore[arg-type]
                        action_url=form.get("action_url"),  # type: ignore[arg-type]
                        submit_element_id=form.get("submit_element_id"),  # type: ignore[arg-type]
                        success_transition_id=None,
                        probe_status=str(form.get("probe_status") or "unprobed_readonly"),
                        source="harvest",
                        confidence="high",
                        last_verified_at=_now(),
                    )
                    session.add(form_row)
                    await session.flush()
                    for field in form.get("fields") or []:  # type: ignore[union-attr]
                        session.add(
                            MapField(
                                id=uuid4(),
                                workspace_id=app_map.workspace_id,
                                application_id=app_map.application_id,
                                target_id=app_map.target_id,
                                app_map_id=app_map.id,
                                form_id=form_row.id,
                                element_id=field.get("element_id"),  # type: ignore[union-attr]
                                label=str(field["label"]),  # type: ignore[union-attr]
                                field_type=str(field["field_type"]),  # type: ignore[union-attr]
                                name_attr=field.get("name_attr"),  # type: ignore[union-attr]
                                required=bool(field.get("required")),  # type: ignore[union-attr]
                                constraints=dict(field.get("constraints") or {}),  # type: ignore[union-attr]
                                options=list(field.get("options") or []),  # type: ignore[union-attr]
                                help_text=field.get("help_text"),  # type: ignore[union-attr]
                                error_text_observed=field.get("error_text_observed"),  # type: ignore[union-attr]
                                validation_source=str(field.get("validation_source") or "dom"),  # type: ignore[union-attr]
                                ordinal=int(field.get("ordinal") or 0),  # type: ignore[union-attr]
                                source="harvest",
                                confidence="high",
                                last_verified_at=_now(),
                            )
                        )
                    rows.append(form_row)
                await session.flush()
                return rows

    async def upsert_transition(
        self,
        app_map: AppMap,
        *,
        from_state_id: UUID,
        to_state_id: UUID,
        via_element_id: UUID | None,
        via_action: str,
    ) -> MapTransition:
        """Insert or re-observe a transition. Dedupe compares
        via_element_id in Python because NULL never equals NULL in
        SQL (doc 16 section 5.5)."""
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(MapTransition).where(
                        MapTransition.app_map_id == app_map.id,
                        MapTransition.from_state_id == from_state_id,
                        MapTransition.to_state_id == to_state_id,
                        MapTransition.via_action == via_action,
                    )
                )
                for existing in result.scalars().all():
                    if existing.via_element_id == via_element_id:
                        existing.observed_count += 1
                        existing.last_verified_at = _now()
                        await session.flush()
                        return existing
                row = MapTransition(
                    id=uuid4(),
                    workspace_id=app_map.workspace_id,
                    application_id=app_map.application_id,
                    target_id=app_map.target_id,
                    app_map_id=app_map.id,
                    from_state_id=from_state_id,
                    to_state_id=to_state_id,
                    via_element_id=via_element_id,
                    via_action=via_action,
                    observed_count=1,
                    source="harvest",
                    confidence="high",
                    last_verified_at=_now(),
                )
                session.add(row)
                await session.flush()
                return row

    # --- stage-glue reads (exemplars, journey graph) -------------------------

    async def list_elements_for_state(
        self, state_id: UUID
    ) -> list[MapElement]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapElement)
                .where(MapElement.map_page_state_id == state_id)
                .order_by(MapElement.ordinal)
            )
            return list(result.scalars().all())

    async def list_fields_for_state(self, state_id: UUID) -> list[MapField]:
        async with self._session_factory() as session:
            forms = await session.execute(
                select(MapForm).where(MapForm.map_page_state_id == state_id)
            )
            form_ids = [form.id for form in forms.scalars().all()]
            if not form_ids:
                return []
            result = await session.execute(
                select(MapField)
                .where(MapField.form_id.in_(form_ids))
                .order_by(MapField.form_id, MapField.ordinal)
            )
            return list(result.scalars().all())

    async def list_states_for_map(self, map_id: UUID) -> list[MapPageState]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapPageState).where(MapPageState.app_map_id == map_id)
            )
            return list(result.scalars().all())

    async def list_transitions(self, map_id: UUID) -> list[MapTransition]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapTransition).where(
                    MapTransition.app_map_id == map_id
                )
            )
            return list(result.scalars().all())

    async def get_element(self, element_id: UUID) -> MapElement | None:
        async with self._session_factory() as session:
            return await session.get(MapElement, element_id)

    async def application_name(self, application_id: UUID) -> str:
        from markettwin_database.models.testing import Application

        async with self._session_factory() as session:
            application = await session.get(Application, application_id)
            return application.name if application is not None else "the application"

    # --- evidence --------------------------------------------------------------

    async def record_evidence(
        self,
        app_map: AppMap,
        page: MapPage,
        state: MapPageState | None,
        *,
        kind: str,
        viewport: str,
        object_key: str,
        sha256: str,
        byte_size: int,
        redaction_status: str,
        redaction_count: int,
    ) -> MapEvidenceObject:
        async with self._session_factory() as session:
            async with session.begin():
                row = MapEvidenceObject(
                    id=uuid4(),
                    workspace_id=app_map.workspace_id,
                    application_id=app_map.application_id,
                    target_id=app_map.target_id,
                    app_map_id=app_map.id,
                    map_page_id=page.id,
                    map_page_state_id=state.id if state is not None else None,
                    kind=kind,
                    viewport=viewport,
                    object_key=object_key,
                    sha256=sha256,
                    byte_size=byte_size,
                    redaction_status=redaction_status,
                    redaction_count=redaction_count,
                    captured_at=_now(),
                )
                session.add(row)
                await session.flush()
                return row

    # --- enrichment budgets and spend (the R2 sink) ---------------------------

    async def record_mapping_budgets(
        self, map_id: UUID, *, calls_cap: int, tokens_cap: int
    ) -> None:
        """Record the provisional caps on the map row BEFORE the first
        model call (doc 16 section 5.6): the cap is a stored fact, not
        a constant the spend can silently outgrow."""
        async with self._session_factory() as session:
            async with session.begin():
                app_map = await session.get(AppMap, map_id)
                if app_map is None:
                    return
                app_map.mapping_budget_calls = calls_cap
                app_map.mapping_budget_tokens = tokens_cap
                await session.flush()

    async def record_enrichment_spend(
        self, map_id: UUID, *, calls_delta: int, tokens_delta: int
    ) -> tuple[int, int]:
        """THE enrichment spend sink: called ONLY from
        harvest/enrich.py (doc 27 R2). Returns the new totals."""
        async with self._session_factory() as session:
            async with session.begin():
                app_map = await session.get(AppMap, map_id)
                if app_map is None:
                    return (0, 0)
                app_map.mapping_spend_calls = (
                    app_map.mapping_spend_calls or 0
                ) + calls_delta
                app_map.mapping_spend_tokens = (
                    app_map.mapping_spend_tokens or 0
                ) + tokens_delta
                await session.flush()
                return (
                    app_map.mapping_spend_calls,
                    app_map.mapping_spend_tokens,
                )

    # --- journeys, skills, replays ---------------------------------------------

    async def create_journey(
        self,
        app_map: AppMap,
        *,
        name: str,
        intent: str | None,
        preconditions: list[object],
        steps: list[dict[str, object]],
        success_state_id: UUID | None,
        selection: str,
    ) -> MapJourney:
        async with self._session_factory() as session:
            async with session.begin():
                row = MapJourney(
                    id=uuid4(),
                    workspace_id=app_map.workspace_id,
                    application_id=app_map.application_id,
                    target_id=app_map.target_id,
                    app_map_id=app_map.id,
                    name=name,
                    intent=intent,
                    preconditions=preconditions,
                    steps=steps,
                    success_state_id=success_state_id,
                    skill_id=None,
                    selection=selection,
                    source="harvest",
                    confidence="high",
                    last_verified_at=_now(),
                )
                session.add(row)
                await session.flush()
                return row

    async def attach_journey_skill(self, journey_id: UUID, skill_id: UUID) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                journey = await session.get(MapJourney, journey_id)
                if journey is None:
                    return
                journey.skill_id = skill_id
                await session.flush()

    async def create_skill_with_version(
        self,
        app_map: AppMap,
        *,
        name: str,
        definition: dict[str, object],
        package: dict[str, object],
        created_by_user_id: UUID | None,
    ) -> tuple[Skill, SkillVersion]:
        """Insert the graph-scoped registry rows (doc 16 section 4.2).

        NOTE (OQ2): on the current schema this raises IntegrityError —
        the legacy Skill/SkillVersion blueprint and creator columns
        are NOT NULL and a graph-scoped row has neither. The compile
        stage calls this in its own transaction and records the
        failure honestly in harvest_metrics; the write path activates
        unchanged when a later approved revision relaxes those
        columns. No sentinel blueprint row is ever fabricated.
        """
        async with self._session_factory() as session:
            async with session.begin():
                skill = Skill(
                    id=uuid4(),
                    workspace_id=app_map.workspace_id,
                    blueprint_id=None,  # type: ignore[arg-type]
                    created_by_user_id=created_by_user_id,  # type: ignore[arg-type]
                    name=name,
                    status="active",
                    application_id=app_map.application_id,
                    target_id=app_map.target_id,
                    app_map_id=app_map.id,
                )
                session.add(skill)
                await session.flush()
                version = SkillVersion(
                    id=uuid4(),
                    workspace_id=app_map.workspace_id,
                    blueprint_id=None,  # type: ignore[arg-type]
                    blueprint_version_id=None,  # type: ignore[arg-type]
                    skill_id=skill.id,
                    version_number=1,
                    status="draft",
                    definition_json=definition,
                    generation_metadata={"source": "phase-1b-compile"},
                    created_by_user_id=created_by_user_id,  # type: ignore[arg-type]
                    lifecycle_status="draft",
                    package=package,
                    heal_count=0,
                )
                session.add(version)
                await session.flush()
                return skill, version

    async def get_skill_version(self, version_id: UUID) -> SkillVersion | None:
        async with self._session_factory() as session:
            return await session.get(SkillVersion, version_id)

    async def latest_skill_version(self, skill_id: UUID) -> SkillVersion | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SkillVersion)
                .where(SkillVersion.skill_id == skill_id)
                .order_by(SkillVersion.version_number.desc())
                .limit(1)
            )
            return result.scalars().first()

    async def update_skill_version(
        self, version_id: UUID, **fields: object
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                version = await session.get(SkillVersion, version_id)
                if version is None:
                    return
                for key, value in fields.items():
                    setattr(version, key, value)
                await session.flush()

    async def insert_replay(
        self,
        app_map: AppMap,
        *,
        skill_version_id: UUID,
        result: str,
        failure_step: int | None,
        failure_site: str | None,
        heal_cycle: bool,
        context_kind: str,
        model_calls: int,
        started_at: datetime,
        finished_at: datetime,
    ) -> SkillReplay:
        async with self._session_factory() as session:
            async with session.begin():
                row = SkillReplay(
                    id=uuid4(),
                    skill_version_id=skill_version_id,
                    app_map_id=app_map.id,
                    result=result,
                    failure_step=failure_step,
                    failure_site=failure_site,
                    heal_cycle=heal_cycle,
                    context_kind=context_kind,
                    model_calls=model_calls,
                    started_at=started_at,
                    finished_at=finished_at,
                )
                session.add(row)
                await session.flush()
                return row

    # --- Phase 3: skill library (doc 22 sections 5.1, 6.1, 6.3) -------------

    async def find_graph_skill(
        self,
        *,
        workspace_id: UUID,
        application_id: UUID,
        target_id: UUID,
        name: str,
    ) -> Skill | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Skill).where(
                    Skill.workspace_id == workspace_id,
                    Skill.application_id == application_id,
                    Skill.target_id == target_id,
                    Skill.name == name,
                )
            )
            return result.scalars().first()

    async def get_skill(self, skill_id: UUID) -> Skill | None:
        async with self._session_factory() as session:
            return await session.get(Skill, skill_id)

    async def create_platform_skill(
        self,
        app_map: AppMap,
        *,
        name: str,
        definition: dict[str, object],
        package: dict[str, object],
    ) -> tuple[Skill, SkillVersion]:
        """Register a platform skill (doc 22 section 6.3): born draft,
        kind 'platform', first version bound to the registering map."""
        async with self._session_factory() as session:
            async with session.begin():
                skill = Skill(
                    id=uuid4(),
                    workspace_id=app_map.workspace_id,
                    blueprint_id=None,  # type: ignore[arg-type]
                    created_by_user_id=None,  # type: ignore[arg-type]
                    name=name,
                    status="active",
                    application_id=app_map.application_id,
                    target_id=app_map.target_id,
                    app_map_id=app_map.id,
                    skill_kind="platform",
                )
                session.add(skill)
                await session.flush()
                version = SkillVersion(
                    id=uuid4(),
                    workspace_id=app_map.workspace_id,
                    blueprint_id=None,  # type: ignore[arg-type]
                    blueprint_version_id=None,  # type: ignore[arg-type]
                    skill_id=skill.id,
                    version_number=1,
                    status="draft",
                    definition_json=definition,
                    generation_metadata={"source": "phase-3-platform"},
                    created_by_user_id=None,  # type: ignore[arg-type]
                    lifecycle_status="draft",
                    package=package,
                    heal_count=0,
                    app_map_id=app_map.id,
                )
                session.add(version)
                await session.flush()
                return skill, version

    async def create_task_skill(
        self,
        app_map: AppMap,
        *,
        name: str,
        definition: dict[str, object],
        package: dict[str, object],
    ) -> tuple[Skill, SkillVersion]:
        """Register a task skill (doc 29 section 5): born draft,
        kind 'task', first version bound to the compiling map."""
        async with self._session_factory() as session:
            async with session.begin():
                skill = Skill(
                    id=uuid4(),
                    workspace_id=app_map.workspace_id,
                    blueprint_id=None,  # type: ignore[arg-type]
                    created_by_user_id=None,  # type: ignore[arg-type]
                    name=name,
                    status="active",
                    application_id=app_map.application_id,
                    target_id=app_map.target_id,
                    app_map_id=app_map.id,
                    skill_kind="task",
                )
                session.add(skill)
                await session.flush()
                version = SkillVersion(
                    id=uuid4(),
                    workspace_id=app_map.workspace_id,
                    blueprint_id=None,  # type: ignore[arg-type]
                    blueprint_version_id=None,  # type: ignore[arg-type]
                    skill_id=skill.id,
                    version_number=1,
                    status="draft",
                    definition_json=definition,
                    generation_metadata={"source": "task-compile"},
                    created_by_user_id=None,  # type: ignore[arg-type]
                    lifecycle_status="draft",
                    package=package,
                    heal_count=0,
                    app_map_id=app_map.id,
                )
                await create_draft_version(session, version, source="task-compile")
                return skill, version

    async def append_skill_version(
        self,
        skill: Skill,
        app_map: AppMap,
        *,
        definition: dict[str, object],
        package: dict[str, object],
        heal_of_version_id: UUID | None = None,
        source: str = "phase-3-compile",
    ) -> SkillVersion:
        """Append the next version to an existing skill, born draft
        and bound to the compiling map; the skill row's app_map_id
        follows the newest compile (the 1b scoping rule)."""
        async with self._session_factory() as session:
            async with session.begin():
                current = await session.get(Skill, skill.id)
                if current is None:
                    raise ValueError(f"skill_unknown: {skill.id}")
                max_number = (
                    await session.execute(
                        select(func.max(SkillVersion.version_number)).where(
                            SkillVersion.skill_id == skill.id
                        )
                    )
                ).scalar()
                version = SkillVersion(
                    id=uuid4(),
                    workspace_id=skill.workspace_id,
                    blueprint_id=None,  # type: ignore[arg-type]
                    blueprint_version_id=None,  # type: ignore[arg-type]
                    skill_id=skill.id,
                    version_number=(max_number or 0) + 1,
                    status="draft",
                    definition_json=definition,
                    generation_metadata={"source": source},
                    created_by_user_id=None,  # type: ignore[arg-type]
                    lifecycle_status="draft",
                    package=package,
                    heal_count=0,
                    app_map_id=app_map.id,
                    heal_of_version_id=heal_of_version_id,
                )
                current.app_map_id = app_map.id
                await create_draft_version(session, version, source=source)
                return version

    async def list_journeys(self, map_id: UUID) -> list[MapJourney]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapJourney)
                .where(MapJourney.app_map_id == map_id)
                .order_by(MapJourney.name)
            )
            return list(result.scalars().all())

    async def get_journey(self, journey_id: UUID) -> MapJourney | None:
        async with self._session_factory() as session:
            return await session.get(MapJourney, journey_id)

    async def list_skills_for_scope(
        self,
        *,
        workspace_id: UUID,
        application_id: UUID,
        target_id: UUID,
    ) -> list[Skill]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Skill)
                .where(
                    Skill.workspace_id == workspace_id,
                    Skill.application_id == application_id,
                    Skill.target_id == target_id,
                )
                .order_by(Skill.name)
            )
            return list(result.scalars().all())

    async def list_versions_for_skill(
        self, skill_id: UUID
    ) -> list[SkillVersion]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SkillVersion)
                .where(SkillVersion.skill_id == skill_id)
                .order_by(SkillVersion.version_number)
            )
            return list(result.scalars().all())

    async def list_ready_maps(self) -> list[AppMap]:
        """Ready maps, newest version first per scope (the
        re-verification poller's work list)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(AppMap)
                .where(AppMap.status == "ready")
                .order_by(
                    AppMap.application_id,
                    AppMap.target_id,
                    AppMap.version_number.desc(),
                )
            )
            return list(result.scalars().all())

    async def apply_skill_transition(
        self,
        version_id: UUID,
        *,
        fields: dict[str, object],
        event: dict[str, object],
    ) -> SkillVersion | None:
        """A lifecycle status write and its skill_usage_events row in
        ONE transaction (doc 22 section 5.1: the transition and its
        record commit together or not at all). ``event`` carries
        kind/from_status/to_status/result/run_id/job_ref/model_calls/
        model_tokens/payload."""
        async with self._session_factory() as session:
            async with session.begin():
                version = await session.get(SkillVersion, version_id)
                if version is None:
                    return None
                for key, value in fields.items():
                    setattr(version, key, value)
                session.add(
                    SkillUsageEvent(
                        id=uuid4(),
                        workspace_id=version.workspace_id,
                        skill_id=version.skill_id,
                        skill_version_id=version.id,
                        app_map_id=version.app_map_id,
                        run_id=event.get("run_id"),  # type: ignore[arg-type]
                        job_ref=event.get("job_ref"),  # type: ignore[arg-type]
                        kind=str(event["kind"]),
                        from_status=event.get("from_status"),  # type: ignore[arg-type]
                        to_status=event.get("to_status"),  # type: ignore[arg-type]
                        model_calls=int(event.get("model_calls") or 0),  # type: ignore[arg-type]
                        model_tokens=int(event.get("model_tokens") or 0),  # type: ignore[arg-type]
                        result=event.get("result"),  # type: ignore[arg-type]
                        payload=dict(event.get("payload") or {}),  # type: ignore[arg-type]
                    )
                )
                await session.flush()
                return version

    async def list_replays_for_version(
        self, version_id: UUID
    ) -> list[SkillReplay]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SkillReplay)
                .where(SkillReplay.skill_version_id == version_id)
                .order_by(SkillReplay.started_at)
            )
            return list(result.scalars().all())

    async def insert_usage_event(
        self,
        version: SkillVersion,
        *,
        kind: str,
        from_status: str | None,
        to_status: str | None,
        result: str | None = None,
        run_id: UUID | None = None,
        job_ref: str | None = None,
        model_calls: int = 0,
        model_tokens: int = 0,
        payload: dict[str, object] | None = None,
    ) -> SkillUsageEvent:
        async with self._session_factory() as session:
            async with session.begin():
                row = SkillUsageEvent(
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
                    payload=dict(payload or {}),
                )
                session.add(row)
                await session.flush()
                return row
