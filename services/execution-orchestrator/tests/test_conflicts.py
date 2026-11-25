"""Doc 21 section 9: conflict detection tests (T-CF1..T-CF3).

(T-CF4..T-CF6 -- owner resolution -- live in control-api's
test_app_map_expectations.py.)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # for grounding_fakes

from uuid import uuid4

import pytest
from grounding_fakes import (
    BASE,
    FakeDoor,
    FakeGroundingRepository,
    entry_with_items,
    make_map,
    seed_graph,
)

from markettwin_execution_orchestrator.expectations.grounding_job import (
    GroundingContext,
    execute_grounding,
    production_stages,
)

pytestmark = pytest.mark.asyncio


def _entry(text: str):
    return entry_with_items(
        uuid4(),
        [{"name": "Nav", "content": text, "source_kind": "owner_document"}],
    )


async def test_t_cf1_grounding_time_contradiction_opens_conflict():
    """Section 9.1 point 1: the docs promise /pricing; the harvested
    graph shows the button going to /checkout. The conflict opens in
    the same grounding pass that authors the expectation."""
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    seed_graph(repo, app_map)
    repo.entries = [
        _entry(f"'Buy now' navigates to {BASE}/pricing.")
    ]
    await execute_grounding(
        repo, app_map, production_stages(FakeDoor([])), door=FakeDoor([])
    )
    doc_rows = [r for r in repo.expectations if r.oracle_source == "documentation"]
    assert len(doc_rows) == 1
    assert doc_rows[0].status == "conflicted"
    assert doc_rows[0].assertion["params"]["expected_url"] == f"{BASE}/pricing"
    conflicts = [c for c in repo.conflicts if c.expectation_id == doc_rows[0].id]
    assert len(conflicts) == 1
    assert conflicts[0].conflict_kind == "navigation_mismatch"
    assert conflicts[0].detection_source == "grounding"
    assert "/checkout" in conflicts[0].observed_behaviour


async def test_t_cf2_verification_sweep_opens_conflict_once():
    """Section 9.1 point 2: the stage-7 sweep re-verifies authored
    assertions against the graph; a stale navigation claim opens a
    'verification' conflict, and re-running the sweep adds none."""
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    graph = seed_graph(repo, app_map)
    stale = await repo.insert_expectation(
        app_map,
        subject_kind="element",
        subject_id=graph["buy"].id,
        statement="Clicking 'Buy now' navigates to /pricing",
        oracle_source="observation",
        source_ref=f"transition:{graph['transition'].id}",
        confidence="medium",
        assertion={
            "kind": "navigation",
            "subject": {
                "element_id": str(graph["buy"].id),
                "state_id": str(graph["home_state"].id),
                "locators": [],
            },
            "params": {"expected_url": f"{BASE}/pricing"},
        },
        assertion_origin="deterministic",
    )
    stages = production_stages(None)
    ctx = GroundingContext(repository=repo, app_map=app_map)
    from markettwin_execution_orchestrator.expectations.grounding import GraphIndex

    ctx.index = GraphIndex(
        pages=repo.pages,
        states=repo.states,
        elements=repo.elements,
        forms=[],
        fields=[],
        transitions=repo.transitions,
        journeys=[],
    )
    await stages.conflicts(ctx)
    await stages.conflicts(ctx)
    conflicts = [c for c in repo.conflicts if c.expectation_id == stale.id]
    assert len(conflicts) == 1
    assert conflicts[0].detection_source == "verification"
    assert conflicts[0].conflict_kind == "navigation_mismatch"


async def test_t_cf3_conflict_never_overwrites_either_side():
    """The split rule (C2/section 9.2): opening a conflict leaves the
    documented statement and source untouched; the observed behaviour
    lives on the conflict row."""
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    seed_graph(repo, app_map)
    statement = f"'Buy now' navigates to {BASE}/pricing."
    repo.entries = [_entry(statement)]
    await execute_grounding(
        repo, app_map, production_stages(FakeDoor([])), door=FakeDoor([])
    )
    doc_row = [
        r for r in repo.expectations if r.oracle_source == "documentation"
    ][0]
    assert doc_row.statement == statement
    assert doc_row.oracle_source == "documentation"
    assert doc_row.source_ref is not None
    conflict = repo.conflicts[0]
    assert conflict.observed_behaviour != doc_row.statement
