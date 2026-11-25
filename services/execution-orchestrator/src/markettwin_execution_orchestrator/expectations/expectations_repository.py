"""Persistence for the grounding job (doc 21 sections 4, 6).

The repository owns every Phase 2 write the orchestrator makes:
``app_maps.grounding_*``, ``map_expectations`` (INSERT + machinery
columns + status transitions -- never ``oracle_source``/``statement``/
``source_ref``, spec C2), ``map_conflicts``, ``map_expectation_events``
and the probing-owned form/field/state/transition fields (C9).
Sessions come from the worker's injected factory, mirroring the
harvest repository.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from markettwin_database.models.knowledge import (
    AppMap,
    ApplicationKnowledgeEntry,
    BlueprintVersion,
    IngestionEntry,
    KnowledgeFile,
    MapConflict,
    MapElement,
    MapExpectation,
    MapExpectationEvent,
    MapField,
    MapForm,
    MapJourney,
    MapPage,
    MapPageState,
    MapTransition,
    ProductBlueprint,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def assertion_signature(assertion: dict[str, object] | None) -> str:
    """Canonical signature of an assertion for idempotency (section 6.2).

    Statement-only records sign the empty assertion; the signature is
    over {kind, subject, params} exactly as stored.
    """

    payload = json.dumps(assertion or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class GroundingRepository:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        knowledge_text: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        self._session_factory = session_factory
        # Reads one knowledge file's rendered Markdown by object key
        # (doc 33 step 6 wiring). Production passes an S3-backed reader;
        # without one, entries load bare, exactly as before.
        self._knowledge_text = knowledge_text

    # -- claim + lifecycle -------------------------------------------------

    async def claim_next_grounding_job(self) -> AppMap | None:
        """Atomically claim one triggered grounding (doc 21 section 6.1).

        One UPDATE ... WHERE grounding_status='building' AND
        grounding_started_at IS NULL ... RETURNING: the trigger writes
        status only, so a row with grounding_started_at set is claimed
        by construction.
        """
        async with self._session_factory() as session:
            async with session.begin():
                next_id = (
                    select(AppMap.id)
                    .where(
                        AppMap.grounding_status == "building",
                        AppMap.grounding_started_at.is_(None),
                    )
                    .order_by(AppMap.started_at)
                    .limit(1)
                    .scalar_subquery()
                )
                result = await session.execute(
                    update(AppMap)
                    .where(AppMap.id == next_id)
                    .values(grounding_started_at=datetime.now(UTC))
                    .returning(AppMap)
                )
                row = result.scalars().first()
                return row

    async def get_map(self, map_id: UUID) -> AppMap | None:
        async with self._session_factory() as session:
            return await session.get(AppMap, map_id)

    async def list_building_grounding(self) -> list[AppMap]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AppMap).where(AppMap.grounding_status == "building")
            )
            return list(result.scalars().all())

    async def save_grounding_metrics(
        self, map_id: UUID, metrics: dict[str, object]
    ) -> None:
        """Heartbeat + stage ledger write (doc 21 section 6.3): the job
        updates grounding_metrics per stage."""
        async with self._session_factory() as session:
            async with session.begin():
                app_map = await session.get(AppMap, map_id)
                if app_map is None:
                    return
                merged = dict(app_map.grounding_metrics or {})
                merged.update(metrics)
                app_map.grounding_metrics = merged

    async def complete_grounding(
        self, map_id: UUID, *, status: str, metrics: dict[str, object]
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                app_map = await session.get(AppMap, map_id)
                if app_map is None:
                    return
                app_map.grounding_status = status
                app_map.grounding_completed_at = datetime.now(UTC)
                app_map.grounding_metrics = dict(metrics)
                app_map.grounding_failure_code = None
                app_map.grounding_failure_message = None
                app_map.grounding_failure_site = None

    async def fail_grounding(
        self,
        map_id: UUID,
        *,
        failure_code: str,
        failure_message: str,
        failure_site: str,
        metrics: dict[str, object] | None = None,
    ) -> None:
        """Close a crashed job failed with the ORIGINAL error retained."""
        async with self._session_factory() as session:
            async with session.begin():
                app_map = await session.get(AppMap, map_id)
                if app_map is None:
                    return
                app_map.grounding_status = "failed"
                app_map.grounding_completed_at = datetime.now(UTC)
                app_map.grounding_failure_code = failure_code
                app_map.grounding_failure_message = failure_message[:2000]
                app_map.grounding_failure_site = failure_site
                if metrics is not None:
                    app_map.grounding_metrics = dict(metrics)

    # -- graph reads ---------------------------------------------------------

    async def _list(self, model: Any, map_id: UUID) -> list[Any]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(model).where(model.app_map_id == map_id)
            )
            return list(result.scalars().all())

    async def list_pages(self, map_id: UUID) -> list[MapPage]:
        return await self._list(MapPage, map_id)

    async def list_states(self, map_id: UUID) -> list[MapPageState]:
        return await self._list(MapPageState, map_id)

    async def list_elements(self, map_id: UUID) -> list[MapElement]:
        return await self._list(MapElement, map_id)

    async def list_forms(self, map_id: UUID) -> list[MapForm]:
        return await self._list(MapForm, map_id)

    async def list_fields(self, map_id: UUID) -> list[MapField]:
        return await self._list(MapField, map_id)

    async def list_transitions(self, map_id: UUID) -> list[MapTransition]:
        return await self._list(MapTransition, map_id)

    async def list_journeys(self, map_id: UUID) -> list[MapJourney]:
        return await self._list(MapJourney, map_id)

    async def list_expectations(self, map_id: UUID) -> list[MapExpectation]:
        return await self._list(MapExpectation, map_id)

    async def list_conflicts(self, map_id: UUID) -> list[MapConflict]:
        return await self._list(MapConflict, map_id)

    async def list_events(self, map_id: UUID) -> list[MapExpectationEvent]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MapExpectationEvent)
                .where(MapExpectationEvent.app_map_id == map_id)
                .order_by(MapExpectationEvent.occurred_at)
            )
            return list(result.scalars().all())

    # -- candidates ----------------------------------------------------------

    async def load_approved_entries(
        self, application_id: UUID
    ) -> list[IngestionEntry]:
        """Approved ingestion entries linked to the application (§5.2).

        Approval lives on the entry's BlueprintVersion record
        (status='approved'); rejected entries are never candidates.
        """
        async with self._session_factory() as session:
            links = list(
                (
                    await session.execute(
                        select(ApplicationKnowledgeEntry).where(
                            ApplicationKnowledgeEntry.application_id
                            == application_id
                        )
                    )
                ).scalars().all()
            )
            entries: list[IngestionEntry] = []
            for link in links:
                entry = await session.get(
                    IngestionEntry, link.ingestion_entry_id
                )
                if entry is None:
                    continue
                version = (
                    await session.execute(
                        select(BlueprintVersion).join(
                            ProductBlueprint, ProductBlueprint.id == BlueprintVersion.blueprint_id,
                        ).where(
                            BlueprintVersion.id == entry.id,
                            BlueprintVersion.blueprint_id == entry.blueprint_id,
                            ProductBlueprint.workspace_id == entry.workspace_id,
                            ProductBlueprint.status == "active",
                        )
                    )
                ).scalars().first()
                if version is None or version.status != "approved":
                    continue
                entries.append(entry)
            file_rows = await self._approved_file_rows(session, entries)
        if self._knowledge_text is not None:
            for entry in entries:
                entry.knowledge_files = [  # type: ignore[attr-defined]
                    {
                        "slug": row.slug,
                        "content": await self._knowledge_text(row.object_key),
                    }
                    for row in file_rows.get(entry.id, [])
                ]
        return entries

    async def _approved_file_rows(
        self, session: AsyncSession, entries: list[IngestionEntry]
    ) -> dict[UUID, list[KnowledgeFile]]:
        """Approved knowledge-file rows per entry (doc 33 step 6 wiring).

        Grounding's candidate source is the entries' Markdown files;
        only the version the owner approved carries status='approved',
        so the filter is the approval gate for files.
        """
        if self._knowledge_text is None:
            return {}
        rows: dict[UUID, list[KnowledgeFile]] = {}
        for entry in entries:
            rows[entry.id] = list(
                (
                    await session.execute(
                        select(KnowledgeFile)
                        .where(
                            KnowledgeFile.ingestion_entry_id == entry.id,
                            KnowledgeFile.status == "approved",
                        )
                        .order_by(KnowledgeFile.slug)
                    )
                ).scalars().all()
            )
        return rows

    # -- expectation writes ----------------------------------------------------

    async def find_expectation(
        self,
        map_id: UUID,
        *,
        subject_kind: str,
        subject_id: UUID,
        signature: str,
        oracle_source: str,
    ) -> MapExpectation | None:
        """The idempotency lookup of section 6.2 stage 4."""
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.execute(
                        select(MapExpectation).where(
                            MapExpectation.app_map_id == map_id,
                            MapExpectation.subject_kind == subject_kind,
                            MapExpectation.subject_id == subject_id,
                            MapExpectation.oracle_source == oracle_source,
                        )
                    )
                ).scalars().all()
            )
        for row in rows:
            if assertion_signature(row.assertion) == signature:
                return row
        return None

    async def rejected_keys(self, map_id: UUID) -> set[tuple[str, str, str]]:
        """(subject_kind, subject_id, signature) with a standing rejection.

        A record is rejection-bound when its latest decision event is
        'rejected' with no later 'promoted' (doc 21 section 5.5):
        re-grounding never resurrects it.
        """
        expectations = {
            row.id: row for row in await self.list_expectations(map_id)
        }
        latest: dict[UUID, str] = {}
        for event in await self.list_events(map_id):
            if event.event_type in ("rejected", "promoted"):
                latest[event.expectation_id] = event.event_type
        keys: set[tuple[str, str, str]] = set()
        for expectation_id, decision in latest.items():
            if decision != "rejected":
                continue
            row = expectations.get(expectation_id)
            if row is None:
                continue
            keys.add(
                (
                    row.subject_kind,
                    str(row.subject_id),
                    assertion_signature(row.assertion),
                )
            )
        return keys

    async def insert_expectation(
        self,
        app_map: AppMap,
        *,
        subject_kind: str,
        subject_id: UUID,
        statement: str,
        oracle_source: str,
        source_ref: str | None,
        confidence: str,
        assertion: dict[str, object] | None,
        assertion_origin: str | None,
        status: str = "unverified",
        events: tuple[tuple[str, dict[str, object]], ...] = (("authored", {}),),
    ) -> MapExpectation:
        async with self._session_factory() as session:
            async with session.begin():
                row = MapExpectation(
                    id=uuid4(),
                    workspace_id=app_map.workspace_id,
                    application_id=app_map.application_id,
                    target_id=app_map.target_id,
                    app_map_id=app_map.id,
                    subject_kind=subject_kind,
                    subject_id=subject_id,
                    statement=statement,
                    oracle_source=oracle_source,
                    status=status,
                    source_ref=source_ref,
                    confidence=confidence,
                    assertion=assertion,
                    assertion_kind=(
                        str(assertion.get("kind"))
                        if assertion is not None and assertion.get("kind")
                        else None
                    ),
                    assertion_origin=assertion_origin,
                )
                session.add(row)
                await session.flush()
                for event_type, payload in events:
                    session.add(
                        MapExpectationEvent(
                            id=uuid4(),
                            workspace_id=app_map.workspace_id,
                            application_id=app_map.application_id,
                            target_id=app_map.target_id,
                            app_map_id=app_map.id,
                            expectation_id=row.id,
                            event_type=event_type,
                            payload=dict(payload),
                        )
                    )
                await session.flush()
                return row

    async def append_event(
        self,
        expectation: MapExpectation,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                session.add(
                    MapExpectationEvent(
                        id=uuid4(),
                        workspace_id=expectation.workspace_id,
                        application_id=expectation.application_id,
                        target_id=expectation.target_id,
                        app_map_id=expectation.app_map_id,
                        expectation_id=expectation.id,
                        event_type=event_type,
                        payload=dict(payload),
                    )
                )

    async def set_expectation_status(
        self, expectation_id: UUID, status: str
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(MapExpectation, expectation_id)
                if row is not None:
                    row.status = status

    # -- conflict writes -------------------------------------------------------

    async def find_open_conflict(
        self,
        *,
        expectation_id: UUID,
        conflict_kind: str,
        observed_subject_id: UUID | None,
    ) -> MapConflict | None:
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.execute(
                        select(MapConflict).where(
                            MapConflict.expectation_id == expectation_id,
                            MapConflict.status == "open",
                            MapConflict.conflict_kind == conflict_kind,
                        )
                    )
                ).scalars().all()
            )
        for row in rows:
            if row.observed_subject_id == observed_subject_id:
                return row
        return None

    async def insert_conflict(
        self,
        app_map: AppMap,
        expectation: MapExpectation,
        *,
        conflict_kind: str,
        detection_source: str,
        observed_behaviour: str,
        observed_subject_id: UUID | None = None,
        run_id: UUID | None = None,
        evidence_refs: list[object] | None = None,
    ) -> MapConflict:
        """Open a conflict and mark its expectation conflicted (§9.1)."""
        async with self._session_factory() as session:
            async with session.begin():
                conflict = MapConflict(
                    id=uuid4(),
                    workspace_id=app_map.workspace_id,
                    application_id=app_map.application_id,
                    target_id=app_map.target_id,
                    app_map_id=app_map.id,
                    expectation_id=expectation.id,
                    observed_behaviour=observed_behaviour,
                    evidence_refs=list(evidence_refs or []),
                    status="open",
                    conflict_kind=conflict_kind,
                    detection_source=detection_source,
                    observed_subject_id=observed_subject_id,
                    run_id=run_id,
                )
                session.add(conflict)
                row = await session.get(MapExpectation, expectation.id)
                if row is not None:
                    row.status = "conflicted"
                session.add(
                    MapExpectationEvent(
                        id=uuid4(),
                        workspace_id=app_map.workspace_id,
                        application_id=app_map.application_id,
                        target_id=app_map.target_id,
                        app_map_id=app_map.id,
                        expectation_id=expectation.id,
                        event_type="conflicted",
                        payload={
                            "actor": "grounding",
                            "conflict_id": str(conflict.id),
                            "detection_source": detection_source,
                        },
                    )
                )
                await session.flush()
                return conflict

    # -- journey writes ----------------------------------------------------------

    async def insert_journey(
        self, app_map: AppMap, journey: MapJourney
    ) -> MapJourney:
        async with self._session_factory() as session:
            async with session.begin():
                session.add(journey)
                await session.flush()
                return journey

    # -- probing writes (doc 21 section 7.3: only the reserved fields) -------

    async def save_form_probe(
        self,
        form_id: UUID,
        probe_status: str,
        *,
        success_transition_id: UUID | None = None,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                form = await session.get(MapForm, form_id)
                if form is None:
                    return
                form.probe_status = probe_status
                if success_transition_id is not None:
                    form.success_transition_id = success_transition_id

    async def save_field_validation(
        self, field_id: UUID, error_text: str
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                field_row = await session.get(MapField, field_id)
                if field_row is None:
                    return
                field_row.validation_source = "probed"
                field_row.error_text_observed = error_text

    async def add_probe_state(
        self,
        app_map: AppMap,
        *,
        form: MapForm,
        submit_element_id: UUID,
        state_id: str,
        element_signature: str,
        url: str,
    ) -> None:
        """Record a probing-created error state + its transition, if
        the identity is new to the graph (section 7.3)."""
        async with self._session_factory() as session:
            async with session.begin():
                existing = await session.execute(
                    select(MapPageState).where(
                        MapPageState.app_map_id == app_map.id,
                        MapPageState.state_id == state_id,
                    )
                )
                if existing.scalars().first() is not None:
                    return
                state = MapPageState(
                    id=uuid4(),
                    workspace_id=app_map.workspace_id,
                    application_id=app_map.application_id,
                    target_id=app_map.target_id,
                    app_map_id=app_map.id,
                    map_page_id=form.map_page_id,
                    state_key=f"probe_error_{form.id.hex[:8]}",
                    state_kind="observed",
                    state_id=state_id,
                    element_signature=element_signature,
                    form_signature="",
                    source="probe",
                    confidence="high",
                )
                session.add(state)
                session.add(
                    MapTransition(
                        id=uuid4(),
                        workspace_id=app_map.workspace_id,
                        application_id=app_map.application_id,
                        target_id=app_map.target_id,
                        app_map_id=app_map.id,
                        from_state_id=form.map_page_state_id,
                        to_state_id=state.id,
                        via_element_id=submit_element_id,
                        via_action="click",
                        observed_count=1,
                        source="probe",
                        confidence="high",
                    )
                )

    async def resolve_success_transition(
        self,
        app_map: AppMap,
        *,
        form: MapForm,
        submit_element_id: UUID,
        to_state_identity: str,
    ) -> UUID | None:
        """The transition a valid completion took: the existing edge
        when the graph has it, else a new probe-sourced edge."""
        async with self._session_factory() as session:
            async with session.begin():
                target = await session.execute(
                    select(MapPageState).where(
                        MapPageState.app_map_id == app_map.id,
                        MapPageState.state_id == to_state_identity,
                    )
                )
                target_state = target.scalars().first()
                if target_state is None:
                    return None
                existing = await session.execute(
                    select(MapTransition).where(
                        MapTransition.app_map_id == app_map.id,
                        MapTransition.from_state_id == form.map_page_state_id,
                        MapTransition.to_state_id == target_state.id,
                        MapTransition.via_element_id == submit_element_id,
                    )
                )
                row = existing.scalars().first()
                if row is not None:
                    return row.id
                created = MapTransition(
                    id=uuid4(),
                    workspace_id=app_map.workspace_id,
                    application_id=app_map.application_id,
                    target_id=app_map.target_id,
                    app_map_id=app_map.id,
                    from_state_id=form.map_page_state_id,
                    to_state_id=target_state.id,
                    via_element_id=submit_element_id,
                    via_action="click",
                    observed_count=1,
                    source="probe",
                    confidence="high",
                )
                session.add(created)
                await session.flush()
                return created.id
