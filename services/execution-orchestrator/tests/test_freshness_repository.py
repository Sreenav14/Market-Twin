"""Phase 4 (doc 23 section 5.4): the preflight's write discipline.

T-SN2 (orchestrator half; the creation half is control-api's
test_preflight_creation.py): the only writes the freshness
repository makes to a SWEPT version's own rows are the section 5.4
fields — the three freshness columns on the map row, and
last_verified_at / screenshot_phash on a tier-2-verified state row.
A spy session diffs every other field before and after.
"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from markettwin_database.models import (
    MapConflict,
    MapElement,
    MapExpectation,
    MapPage,
    MapPageState,
)

from markettwin_execution_orchestrator.freshness.freshness_repository import (
    FreshnessRepository,
)

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


class AsyncContext:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


class SpySession:
    def __init__(self, rows):
        self._rows = rows

    def begin(self):
        return AsyncContext(None)

    async def get(self, model, primary_key):
        return self._rows[primary_key]


def _repository_for(session):
    return FreshnessRepository(lambda: AsyncContext(session))


def _fields(row) -> dict:
    return {
        key: value for key, value in vars(row).items() if not key.startswith("_")
    }


def test_swept_version_writes_stay_inside_section_5_4() -> None:
    """T-SN2: update_map_freshness changes exactly the three
    freshness fields; touch_verified_state changes exactly
    last_verified_at and screenshot_phash. Every census, harvest and
    grounding field on the swept version is byte-identical after."""
    map_id = uuid4()
    state_id = uuid4()
    app_map = SimpleNamespace(
        id=map_id,
        status="ready",
        release_state="partial",
        release_scope="inventory",
        census_metrics={"pages": 12},
        gate_metrics={"inventory": "pass"},
        harvest_status="ready",
        harvest_metrics={"visited": 12},
        grounding_status="ready",
        mapping_spend_calls=30,
        freshness_state="unknown",
        last_preflight_at=None,
        freshness_metrics={},
    )
    state = SimpleNamespace(
        id=state_id,
        state_id="state-abc",
        element_signature="button|Save",
        form_signature=None,
        source="harvest",
        confidence="high",
        dom_structure_hash="dom-1",
        aria_hash="aria-1",
        screenshot_hash="shot-1",
        last_verified_at=None,
        screenshot_phash=None,
    )
    session = SpySession({map_id: app_map, state_id: state})
    repository = _repository_for(session)
    map_before = _fields(app_map)
    state_before = _fields(state)

    async def writes() -> None:
        await repository.update_map_freshness(
            map_id,
            freshness_state="current",
            last_preflight_at=NOW,
            freshness_metrics={"preflight_id": "pf-1"},
        )
        await repository.touch_verified_state(
            state_id, last_verified_at=NOW, screenshot_phash="ahash:0123abcd"
        )

    asyncio.run(writes())

    map_changed = {
        key for key in map_before if map_before[key] != _fields(app_map)[key]
    }
    assert map_changed == {
        "freshness_state",
        "last_preflight_at",
        "freshness_metrics",
    }
    state_changed = {
        key for key in state_before if state_before[key] != _fields(state)[key]
    }
    assert state_changed == {"last_verified_at", "screenshot_phash"}
    assert app_map.freshness_state == "current"
    assert state.screenshot_phash == "ahash:0123abcd"


# -- the oracle carry (programme decision after doc 23 section 7.2) ---


class CopySession:
    """A scalars-dispatching fake session for copy_forward: rows are
    real model instances grouped by entity; adds are collected."""

    def __init__(self, rows_by_entity):
        self._rows = rows_by_entity
        self.added = []

    def begin(self):
        return AsyncContext(None)

    async def scalars(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        return list(self._rows.get(entity, []))

    def add(self, obj):
        self.added.append(obj)


class MintSession:
    def __init__(self):
        self.added = []

    def begin(self):
        return AsyncContext(None)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


def test_mint_successor_inherits_the_base_grounding_status() -> None:
    """The successor serves the carried oracle, so it is born with
    the base's grounding state — not 'not_started', which the
    snapshot extension reads as 'no expectations to serve'."""
    base = SimpleNamespace(
        id=uuid4(), workspace_id=uuid4(), application_id=uuid4(),
        target_id=uuid4(), version_number=3,
        base_url="https://app.example.com/",
        census_metrics={}, pattern_stats={},
        census_expected_count=4, census_reachable_count=4,
        harvest_metrics={}, grounding_status="ready",
    )
    repository = _repository_for(MintSession())
    successor = asyncio.run(
        repository.mint_successor(
            base,
            preflight=SimpleNamespace(id=uuid4()),
            builder_version="preflight-4.1",
            freshness_metrics={},
            completed_at=NOW,
        )
    )
    assert successor.grounding_status == "ready"
    assert successor.version_number == 4


def test_copy_forward_carries_expectations_and_conflicts() -> None:
    """Base map with expectations (one anchored to an unchanged page,
    one to a changed page, one to a copied element, one to an element
    whose state was not copied) and two conflicts: after the copy,
    the successor holds the carried expectations with statuses
    preserved and subjects remapped, the changed-page anchor is
    counted as carried_changed, the uncopied-subject expectation and
    its conflict are skipped and counted, and the kept conflict
    points at the successor's expectation row."""
    workspace_id, application_id, target_id = uuid4(), uuid4(), uuid4()
    base = SimpleNamespace(
        id=uuid4(), workspace_id=workspace_id,
        application_id=application_id, target_id=target_id,
    )
    successor = SimpleNamespace(
        id=uuid4(), workspace_id=workspace_id,
        application_id=application_id, target_id=target_id,
    )
    scope = {
        "workspace_id": workspace_id,
        "application_id": application_id,
        "target_id": target_id,
        "app_map_id": base.id,
    }
    url_a = "https://app.example.com/a"
    url_b = "https://app.example.com/b"
    page_a = MapPage(
        id=uuid4(), canonical_url=url_a, crawl_status="fetch_ok", **scope
    )
    page_b = MapPage(
        id=uuid4(), canonical_url=url_b, crawl_status="fetch_ok", **scope
    )
    state_a = MapPageState(
        id=uuid4(), map_page_id=page_a.id, state_key="default", **scope
    )
    state_b = MapPageState(
        id=uuid4(), map_page_id=page_b.id, state_key="default", **scope
    )
    element_a = MapElement(
        id=uuid4(), map_page_id=page_a.id,
        map_page_state_id=state_a.id, **scope,
    )
    element_b = MapElement(
        id=uuid4(), map_page_id=page_b.id,
        map_page_state_id=state_b.id, **scope,
    )

    def expectation(subject_kind, subject_id, statement, status):
        return MapExpectation(
            id=uuid4(), subject_kind=subject_kind, subject_id=subject_id,
            statement=statement, oracle_source="documentation",
            status=status, confidence="high", **scope,
        )

    exp_page_a = expectation("page", page_a.id, "A holds", "owner-confirmed")
    exp_page_b = expectation("page", page_b.id, "B holds", "replay-verified")
    exp_element_a = expectation(
        "element", element_a.id, "A button holds", "owner-confirmed"
    )
    exp_element_b = expectation(
        "element", element_b.id, "B button holds", "unverified"
    )
    conflict_kept = MapConflict(
        id=uuid4(), expectation_id=exp_page_a.id,
        observed_behaviour="A differs", status="open",
        conflict_kind="statement_vs_observation",
        detection_source="grounding", evidence_refs=[], **scope,
    )
    conflict_orphaned = MapConflict(
        id=uuid4(), expectation_id=exp_element_b.id,
        observed_behaviour="B differs", status="open",
        conflict_kind="statement_vs_observation",
        detection_source="grounding", evidence_refs=[], **scope,
    )
    session = CopySession({
        MapPage: [page_a, page_b],
        MapPageState: [state_a, state_b],
        MapElement: [element_a, element_b],
        MapExpectation: [exp_page_a, exp_page_b, exp_element_a, exp_element_b],
        MapConflict: [conflict_kept, conflict_orphaned],
    })
    repository = _repository_for(session)

    ledger = asyncio.run(
        repository.copy_forward(
            base=base, successor=successor,
            changed_urls={url_b}, missing_urls=set(), new_pages=[],
            observed_at=NOW,
        )
    )

    assert ledger["expectations_carried"] == 3
    assert ledger["expectations_carried_changed"] == 1
    assert ledger["expectations_skipped"] == 1
    assert ledger["conflicts_carried"] == 1
    assert ledger["conflicts_skipped"] == 1

    carried = [
        obj for obj in session.added if isinstance(obj, MapExpectation)
    ]
    assert len(carried) == 3
    assert all(obj.app_map_id == successor.id for obj in carried)
    by_statement = {obj.statement: obj for obj in carried}
    assert by_statement["A holds"].status == "owner-confirmed"
    assert by_statement["B holds"].status == "replay-verified"
    new_page_ids = {
        obj.canonical_url: obj.id
        for obj in session.added if isinstance(obj, MapPage)
    }
    assert by_statement["A holds"].subject_id == new_page_ids[url_a]
    assert by_statement["B holds"].subject_id == new_page_ids[url_b]
    new_elements = [
        obj for obj in session.added if isinstance(obj, MapElement)
    ]
    assert len(new_elements) == 1
    assert by_statement["A button holds"].subject_id == new_elements[0].id

    conflicts = [
        obj for obj in session.added if isinstance(obj, MapConflict)
    ]
    assert len(conflicts) == 1
    assert conflicts[0].app_map_id == successor.id
    assert conflicts[0].expectation_id == by_statement["A holds"].id
    assert conflicts[0].status == "open"
