"""Doc 21 sections 5.2/5.4/5.5: authoring tests (T-AU1..T-AU7)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # for grounding_fakes

import re
from pathlib import Path
from uuid import uuid4

import pytest
from grounding_fakes import (
    BASE,
    FakeDoor,
    FakeGroundingRepository,
    entry_with_items,
    make_element,
    make_map,
    make_page,
    make_state,
    seed_graph,
)

from markettwin_execution_orchestrator.expectations import authoring
from markettwin_execution_orchestrator.expectations.expectations_repository import (
    assertion_signature,
)
from markettwin_execution_orchestrator.expectations.grounding_job import (
    execute_grounding,
    production_stages,
)

pytestmark = pytest.mark.asyncio


def _entry(text: str, name: str = "Note"):
    return entry_with_items(
        uuid4(),
        [{"name": name, "content": text, "source_kind": "owner_document"}],
    )


async def _run(repo, door):
    await execute_grounding(
        repo, repo.app_map, production_stages(door), door=door
    )
    return repo.app_map.grounding_metrics


async def test_t_au1_match_key_order_route_then_element_then_journey():
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    graph = seed_graph(repo, app_map)
    # Route beats element: the statement names the checkout URL and
    # quotes the 'Buy now' label; the page wins (section 5.2 order).
    repo.entries = [
        _entry(f"See {BASE}/checkout -- the 'Buy now' step ends there.")
    ]
    await _run(repo, FakeDoor([]))
    doc_rows = [r for r in repo.expectations if r.oracle_source == "documentation"]
    assert len(doc_rows) == 1
    assert doc_rows[0].subject_kind == "page"
    assert doc_rows[0].subject_id == graph["checkout"].id


async def test_t_au2_ambiguous_goes_to_adjudication():
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    graph = seed_graph(repo, app_map)
    second_state = make_state(graph["home"])
    save_a = make_element(graph["home_state"], "Save", page_id=graph["home"].id)
    save_b = make_element(second_state, "Save", page_id=graph["home"].id)
    repo.elements = [graph["buy"], save_a, save_b]
    repo.states = [graph["home_state"], graph["checkout_state"], second_state]
    repo.entries = [_entry("'Save' applies the changes.")]
    door = FakeDoor(
        [{"chosen_subject_id": str(save_b.id), "confidence": 0.9, "rationale": "x"}]
    )
    metrics = await _run(repo, door)
    doc_rows = [r for r in repo.expectations if r.oracle_source == "documentation"]
    assert len(doc_rows) == 1
    assert doc_rows[0].subject_id == save_b.id
    assert metrics["matched_adjudicated"] == 1

    # An invented subject id is rejected: nothing is authored.
    repo2 = FakeGroundingRepository(make_map())
    graph2 = seed_graph(repo2, repo2.app_map)
    state2 = make_state(graph2["home"])
    repo2.elements = [
        graph2["buy"],
        make_element(graph2["home_state"], "Save", page_id=graph2["home"].id),
        make_element(state2, "Save", page_id=graph2["home"].id),
    ]
    repo2.states = [graph2["home_state"], graph2["checkout_state"], state2]
    repo2.entries = [_entry("'Save' applies the changes.")]
    door2 = FakeDoor(
        [{"chosen_subject_id": str(uuid4()), "confidence": 0.9, "rationale": "x"}]
    )
    metrics2 = await _run(repo2, door2)
    assert [
        r for r in repo2.expectations if r.oracle_source == "documentation"
    ] == []
    assert metrics2["unmatched_candidates"][0]["reason"] == "ambiguous_unresolved"


async def test_t_au3_unmatched_candidates_are_named():
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    seed_graph(repo, app_map)
    entry_id = uuid4()
    repo.entries = [
        entry_with_items(
            entry_id,
            [
                {
                    "name": "Zebra",
                    "content": "The 'Zebra' module handles striping.",
                    "source_kind": "owner_document",
                }
            ],
        )
    ]
    metrics = await _run(repo, FakeDoor([]))
    assert metrics["unmatched_candidates"] == [
        {"entry_id": str(entry_id), "ordinal": 0, "reason": "no_subject_match"}
    ]
    assert [
        r for r in repo.expectations if r.oracle_source == "documentation"
    ] == []


async def test_t_au4_drafted_assertions_are_validated():
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    graph = seed_graph(repo, app_map)
    repo.entries = [_entry(f"See {BASE}/checkout for payment.")]
    door = FakeDoor(
        [
            {
                "statement": "The checkout page mentions Payment.",
                "assertion": {
                    "kind": "page_text",
                    "params": {"text": "Payment", "present": True},
                },
                "confidence": 0.9,
            }
        ]
    )
    await _run(repo, door)
    drafts = [r for r in repo.expectations if r.oracle_source == "model-draft"]
    assert len(drafts) == 1
    assert drafts[0].assertion["kind"] == "page_text"
    assert drafts[0].assertion_origin == "model-drafted"
    assert drafts[0].status == "unverified"
    assert graph["checkout"].id == drafts[0].subject_id

    # An invalid draft (kind that cannot bind to the subject) lands
    # statement-only, never with the invented assertion.
    repo2 = FakeGroundingRepository(make_map())
    seed_graph(repo2, repo2.app_map)
    repo2.entries = [_entry(f"See {BASE}/checkout for payment.")]
    door2 = FakeDoor(
        [
            {
                "statement": "Checkout does something.",
                "assertion": {
                    "kind": "navigation",
                    "params": {"expected_url": "https://evil.example.com/x"},
                },
                "confidence": 0.9,
            }
        ]
    )
    await _run(repo2, door2)
    drafts2 = [r for r in repo2.expectations if r.oracle_source == "model-draft"]
    assert len(drafts2) == 1
    assert drafts2[0].assertion is None


async def test_t_au5_rejected_never_resurrected():
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    graph = seed_graph(repo, app_map)
    rejected = await repo.rejected_keys(app_map.id)
    outcome = await authoring.author_expectation(
        repo,
        app_map,
        subject_kind="element",
        subject_id=graph["buy"].id,
        statement="'Buy now' is present and visible",
        oracle_source="observation",
        source_ref=f"census:{graph['buy'].id}",
        confidence="medium",
        assertion={
            "kind": "element_state",
            "subject": {"element_id": str(graph["buy"].id)},
            "params": {"oracle": "visible"},
        },
        assertion_origin="deterministic",
        rejected_keys=rejected,
    )
    assert outcome.created
    row = repo.expectations[0]
    await repo.append_event(row, "rejected", {"actor": "owner", "reason": "wrong"})
    rejected = await repo.rejected_keys(app_map.id)
    again = await authoring.author_expectation(
        repo,
        app_map,
        subject_kind="element",
        subject_id=graph["buy"].id,
        statement="'Buy now' is present and visible",
        oracle_source="observation",
        source_ref=f"census:{graph['buy'].id}",
        confidence="medium",
        assertion={
            "kind": "element_state",
            "subject": {"element_id": str(graph["buy"].id)},
            "params": {"oracle": "visible"},
        },
        assertion_origin="deterministic",
        rejected_keys=rejected,
    )
    assert not again.created
    assert again.skipped_reason == "rejected"
    assert len(repo.expectations) == 1
    assert assertion_signature(row.assertion)


async def test_t_au6_grounding_never_promotes():
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    seed_graph(repo, app_map)
    repo.entries = [_entry("'Buy now' completes the purchase.")]
    metrics = await _run(repo, FakeDoor([]))
    assert metrics["promotions_at_grounding"] == 0
    assert all(row.promoted_by is None for row in repo.expectations)
    assert all(
        event.event_type != "promoted" for event in repo.events
    )


def test_t_au7_oracle_fields_are_write_once():
    """C2 pin: no module in the package assigns oracle_source,
    statement or source_ref onto an existing row."""
    import markettwin_execution_orchestrator.expectations as package

    package_dir = Path(package.__file__).parent
    pattern = re.compile(r"\.(oracle_source|statement|source_ref)\s*=[^=]")
    offenders = []
    for path in package_dir.glob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if pattern.search(line):
                offenders.append(f"{path.name}: {line.strip()}")
    assert offenders == []
