"""In-memory fakes for the Phase 2 grounding tests.

FakeGroundingRepository implements the GroundingRepository surface
the stages call, storing real model instances so GraphIndex and the
shared gate functions run unmodified.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from markettwin_database.models.knowledge import (
    AppMap,
    MapConflict,
    MapElement,
    MapExpectation,
    MapExpectationEvent,
    MapJourney,
    MapPage,
    MapPageState,
    MapTransition,
)

WS = UUID("11111111-1111-1111-1111-111111111111")
APP = UUID("22222222-2222-2222-2222-222222222222")
TGT = UUID("33333333-3333-3333-3333-333333333333")
BASE = "https://app.example.com"


def make_map(**overrides) -> AppMap:
    values = dict(
        id=uuid4(),
        workspace_id=WS,
        application_id=APP,
        target_id=TGT,
        base_url=BASE,
        status="ready",
        harvest_status="ready",
        grounding_status="building",
        grounding_started_at=None,
        grounding_completed_at=None,
        grounding_metrics={},
        started_at=datetime(2026, 11, 14, tzinfo=UTC),
    )
    values.update(overrides)
    return AppMap(**values)


def make_page(url: str, **overrides) -> MapPage:
    from markettwin_shared.app_map_common import canonical_url, route_pattern_for

    values = dict(
        id=uuid4(),
        workspace_id=WS,
        application_id=APP,
        target_id=TGT,
        app_map_id=uuid4(),
        canonical_url=canonical_url(url),
        route_pattern=route_pattern_for(url),
        source_kinds=["sitemap"],
        crawl_status="visited",
        source="census",
        confidence="high",
        harvest_status="enriched",
    )
    values.update(overrides)
    return MapPage(**values)


def make_state(page: MapPage, key: str = "default") -> MapPageState:
    return MapPageState(
        id=uuid4(),
        workspace_id=WS,
        application_id=APP,
        target_id=TGT,
        app_map_id=page.app_map_id,
        map_page_id=page.id,
        state_key=key,
        element_signature="",
        state_kind="default",
        source="crawl",
        confidence="high",
    )


def make_element(
    state: MapPageState, name: str, *, role: str = "button", page_id: UUID | None = None
) -> MapElement:
    return MapElement(
        id=uuid4(),
        workspace_id=WS,
        application_id=APP,
        target_id=TGT,
        app_map_id=state.app_map_id,
        map_page_id=page_id or state.map_page_id,
        map_page_state_id=state.id,
        role=role,
        name=name,
        locators=[{"strategy": "role", "role": role, "name": name}],
        actionability="click",
        safety_class="read_only",
        source="crawl",
        confidence="high",
    )


def make_transition(
    from_state: MapPageState, to_state: MapPageState, element: MapElement | None
) -> MapTransition:
    return MapTransition(
        id=uuid4(),
        workspace_id=WS,
        application_id=APP,
        target_id=TGT,
        app_map_id=from_state.app_map_id,
        from_state_id=from_state.id,
        to_state_id=to_state.id,
        via_element_id=element.id if element else None,
        via_action="click",
        observed_count=1,
        source="crawl",
        confidence="high",
    )


def entry_with_items(entry_id: UUID, items: list[dict]) -> SimpleNamespace:
    """Doc-33 shape: the items as sections of one Markdown knowledge file."""
    sections = []
    for item in items:
        name = item.get("name") or ""
        content = item.get("content") or ""
        sections.append(f"## {name}\n{content}")
    markdown = "# Knowledge\n\n" + "\n\n".join(sections) + "\n"
    return SimpleNamespace(
        id=entry_id,
        knowledge_files=[SimpleNamespace(slug="knowledge", content=markdown)],
    )


def entry_with_files(entry_id: UUID, files: list[dict]) -> SimpleNamespace:
    """An approved entry carrying Markdown files (slug + content dicts)."""
    return SimpleNamespace(
        id=entry_id,
        knowledge_files=[SimpleNamespace(**file) for file in files],
    )


class FakeGroundingRepository:
    def __init__(self, app_map: AppMap) -> None:
        self.app_map = app_map
        self.pages: list[MapPage] = []
        self.states: list[MapPageState] = []
        self.elements: list[MapElement] = []
        self.forms: list = []
        self.fields: list = []
        self.transitions: list[MapTransition] = []
        self.journeys: list[MapJourney] = []
        self.expectations: list[MapExpectation] = []
        self.conflicts: list[MapConflict] = []
        self.events: list[MapExpectationEvent] = []
        self.entries: list = []
        self.metrics_writes = 0
        self.failed_with: dict | None = None
        self.completed_with: dict | None = None
        self._claim_lock = asyncio.Lock()

    # lifecycle
    async def claim_next_grounding_job(self):
        async with self._claim_lock:
            if (
                self.app_map.grounding_status == "building"
                and self.app_map.grounding_started_at is None
            ):
                self.app_map.grounding_started_at = datetime.now(UTC)
                return self.app_map
            return None

    async def get_map(self, map_id):
        return self.app_map if map_id == self.app_map.id else None

    async def list_building_grounding(self):
        return [self.app_map] if self.app_map.grounding_status == "building" else []

    async def save_grounding_metrics(self, map_id, metrics):
        self.metrics_writes += 1
        merged = dict(self.app_map.grounding_metrics or {})
        merged.update(metrics)
        self.app_map.grounding_metrics = merged

    async def complete_grounding(self, map_id, *, status, metrics):
        self.app_map.grounding_status = status
        self.app_map.grounding_completed_at = datetime.now(UTC)
        self.app_map.grounding_metrics = dict(metrics)
        self.completed_with = {"status": status, "metrics": metrics}

    async def fail_grounding(self, map_id, *, failure_code, failure_message, failure_site, metrics=None):
        self.app_map.grounding_status = "failed"
        self.app_map.grounding_completed_at = datetime.now(UTC)
        if metrics is not None:
            self.app_map.grounding_metrics = dict(metrics)
        self.failed_with = {
            "code": failure_code,
            "message": failure_message,
            "site": failure_site,
        }

    # graph reads
    async def list_pages(self, map_id):
        return list(self.pages)

    async def list_states(self, map_id):
        return list(self.states)

    async def list_elements(self, map_id):
        return list(self.elements)

    async def list_forms(self, map_id):
        return list(self.forms)

    async def list_fields(self, map_id):
        return list(self.fields)

    async def list_transitions(self, map_id):
        return list(self.transitions)

    async def list_journeys(self, map_id):
        return list(self.journeys)

    async def list_expectations(self, map_id):
        return list(self.expectations)

    async def list_conflicts(self, map_id):
        return list(self.conflicts)

    async def list_events(self, map_id):
        return list(self.events)

    async def load_approved_entries(self, application_id):
        return list(self.entries)

    # expectation writes (mirrors the real repository's semantics)
    async def find_expectation(self, map_id, *, subject_kind, subject_id, signature, oracle_source):
        from markettwin_execution_orchestrator.expectations.expectations_repository import (
            assertion_signature,
        )

        for row in self.expectations:
            if (
                row.subject_kind == subject_kind
                and row.subject_id == subject_id
                and row.oracle_source == oracle_source
                and assertion_signature(row.assertion) == signature
            ):
                return row
        return None

    async def rejected_keys(self, map_id):
        from markettwin_execution_orchestrator.expectations.expectations_repository import (
            assertion_signature,
        )

        by_id = {row.id: row for row in self.expectations}
        latest: dict[UUID, str] = {}
        for event in self.events:
            if event.event_type in ("rejected", "promoted"):
                latest[event.expectation_id] = event.event_type
        keys = set()
        for expectation_id, decision in latest.items():
            if decision == "rejected" and expectation_id in by_id:
                row = by_id[expectation_id]
                keys.add(
                    (row.subject_kind, str(row.subject_id), assertion_signature(row.assertion))
                )
        return keys

    async def insert_expectation(self, app_map, **kwargs):
        row = MapExpectation(
            id=uuid4(),
            workspace_id=app_map.workspace_id,
            application_id=app_map.application_id,
            target_id=app_map.target_id,
            app_map_id=app_map.id,
            subject_kind=kwargs["subject_kind"],
            subject_id=kwargs["subject_id"],
            statement=kwargs["statement"],
            oracle_source=kwargs["oracle_source"],
            status=kwargs.get("status", "unverified"),
            source_ref=kwargs.get("source_ref"),
            confidence=kwargs.get("confidence", "medium"),
            assertion=kwargs.get("assertion"),
            assertion_kind=(
                kwargs["assertion"].get("kind") if kwargs.get("assertion") else None
            ),
            assertion_origin=kwargs.get("assertion_origin"),
        )
        self.expectations.append(row)
        for event_type, payload in kwargs.get("events", (("authored", {}),)):
            self.events.append(
                MapExpectationEvent(
                    id=uuid4(),
                    workspace_id=app_map.workspace_id,
                    application_id=app_map.application_id,
                    target_id=app_map.target_id,
                    app_map_id=app_map.id,
                    expectation_id=row.id,
                    event_type=event_type,
                    payload=dict(payload),
                    occurred_at=datetime.now(UTC),
                )
            )
        return row

    async def append_event(self, expectation, event_type, payload):
        self.events.append(
            MapExpectationEvent(
                id=uuid4(),
                workspace_id=expectation.workspace_id,
                application_id=expectation.application_id,
                target_id=expectation.target_id,
                app_map_id=expectation.app_map_id,
                expectation_id=expectation.id,
                event_type=event_type,
                payload=dict(payload),
                occurred_at=datetime.now(UTC),
            )
        )

    async def set_expectation_status(self, expectation_id, status):
        for row in self.expectations:
            if row.id == expectation_id:
                row.status = status

    async def find_open_conflict(self, *, expectation_id, conflict_kind, observed_subject_id):
        for row in self.conflicts:
            if (
                row.expectation_id == expectation_id
                and row.status == "open"
                and row.conflict_kind == conflict_kind
                and row.observed_subject_id == observed_subject_id
            ):
                return row
        return None

    async def insert_conflict(self, app_map, expectation, **kwargs):
        conflict = MapConflict(
            id=uuid4(),
            workspace_id=app_map.workspace_id,
            application_id=app_map.application_id,
            target_id=app_map.target_id,
            app_map_id=app_map.id,
            expectation_id=expectation.id,
            observed_behaviour=kwargs["observed_behaviour"],
            evidence_refs=list(kwargs.get("evidence_refs") or []),
            status="open",
            conflict_kind=kwargs["conflict_kind"],
            detection_source=kwargs["detection_source"],
            observed_subject_id=kwargs.get("observed_subject_id"),
            run_id=kwargs.get("run_id"),
        )
        self.conflicts.append(conflict)
        for row in self.expectations:
            if row.id == expectation.id:
                row.status = "conflicted"
        self.events.append(
            MapExpectationEvent(
                id=uuid4(),
                workspace_id=app_map.workspace_id,
                application_id=app_map.application_id,
                target_id=app_map.target_id,
                app_map_id=app_map.id,
                expectation_id=expectation.id,
                event_type="conflicted",
                payload={"conflict_id": str(conflict.id)},
                occurred_at=datetime.now(UTC),
            )
        )
        return conflict

    async def insert_journey(self, app_map, journey):
        self.journeys.append(journey)
        return journey

    # probing writes
    async def save_form_probe(self, form_id, probe_status, *, success_transition_id=None):
        for form in self.forms:
            if form.id == form_id:
                form.probe_status = probe_status
                if success_transition_id is not None:
                    form.success_transition_id = success_transition_id

    async def save_field_validation(self, field_id, error_text):
        for field_row in self.fields:
            if field_row.id == field_id:
                field_row.validation_source = "probed"
                field_row.error_text_observed = error_text

    async def add_probe_state(self, app_map, *, form, submit_element_id, state_id, element_signature, url):
        self.probe_states = getattr(self, "probe_states", [])
        self.probe_states.append(
            {"form_id": form.id, "state_id": state_id, "url": url}
        )

    async def resolve_success_transition(self, app_map, *, form, submit_element_id, to_state_identity):
        self.success_requests = getattr(self, "success_requests", [])
        self.success_requests.append(to_state_identity)
        return uuid4()


class FakeDoor:
    """Adjudication door fake: queued JSON replies, calls recorded."""

    def __init__(self, replies: list[dict]) -> None:
        self.replies = list(replies)
        self.calls: list[dict] = []

    async def complete_json(self, *, system, user, max_tokens):
        self.calls.append({"system": system, "user": user})
        if self.replies:
            return self.replies.pop(0)
        return {}


def seed_graph(repo: FakeGroundingRepository, app_map: AppMap):
    """Home page with a 'Buy now' button navigating to /checkout."""
    home = make_page(f"{BASE}/", app_map_id=app_map.id)
    checkout = make_page(f"{BASE}/checkout", app_map_id=app_map.id)
    home_state = make_state(home)
    checkout_state = make_state(checkout)
    buy = make_element(home_state, "Buy now", page_id=home.id)
    transition = make_transition(home_state, checkout_state, buy)
    repo.pages = [home, checkout]
    repo.states = [home_state, checkout_state]
    repo.elements = [buy]
    repo.transitions = [transition]
    return {
        "home": home,
        "checkout": checkout,
        "home_state": home_state,
        "checkout_state": checkout_state,
        "buy": buy,
        "transition": transition,
    }


def make_form(page, state, submit_element, **overrides):
    from markettwin_database.models.knowledge import MapForm

    values = dict(
        id=uuid4(),
        workspace_id=WS,
        application_id=APP,
        target_id=TGT,
        app_map_id=page.app_map_id,
        map_page_id=page.id,
        map_page_state_id=state.id,
        form_key="form-main",
        method="post",
        action_url=None,
        submit_element_id=submit_element.id if submit_element else None,
        success_transition_id=None,
        probe_status="unprobed_readonly",
        source="crawl",
        confidence="high",
    )
    values.update(overrides)
    return MapForm(**values)


def make_field(form, label, **overrides):
    from markettwin_database.models.knowledge import MapField

    values = dict(
        id=uuid4(),
        workspace_id=WS,
        application_id=APP,
        target_id=TGT,
        app_map_id=form.app_map_id,
        form_id=form.id,
        element_id=None,
        label=label,
        field_type="email",
        name_attr=label.lower(),
        required=True,
        constraints={},
        options=[],
        help_text=None,
        error_text_observed=None,
        validation_source="dom",
        ordinal=0,
        source="crawl",
        confidence="high",
    )
    values.update(overrides)
    return MapField(**values)
