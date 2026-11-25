"""Doc 21 section 6: grounding job lifecycle tests (T-GR1..T-GR9)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # for grounding_fakes

import ast
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from grounding_fakes import (
    FakeDoor,
    FakeGroundingRepository,
    entry_with_items,
    make_map,
    seed_graph,
)

from markettwin_execution_orchestrator.expectations import grounding_job
from markettwin_execution_orchestrator.expectations.grounding_job import (
    GroundingStages,
    execute_grounding,
    production_stages,
)

pytestmark = pytest.mark.asyncio

CLOSED_METRIC_KEYS = {
    "candidates_total",
    "candidates_by_source",
    "matched_deterministic",
    "matched_adjudicated",
    "unmatched_candidates",
    "authored_by_source_status",
    "assertions_compiled",
    "adjudication_calls",
    "adjudication_deferred",
    "probes",
    "conflicts_opened",
    "journeys_assembled",
    "journey_terminals_named",
    "promotions_at_grounding",
    "failures",
    "gate",
}


def _doc_entry(text: str, name: str = "Checkout"):
    return entry_with_items(
        uuid4(),
        [{"name": name, "content": text, "source_kind": "owner_document"}],
    )


async def test_t_gr1_claim_single_winner():
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    first, second = await asyncio.gather(
        repo.claim_next_grounding_job(), repo.claim_next_grounding_job()
    )
    assert (first is None) != (second is None)
    # The real repository's claim is one atomic UPDATE ... RETURNING
    # with the pinned predicates (source pin; semantics above).
    import markettwin_execution_orchestrator.expectations.expectations_repository as repo_module

    source = Path(repo_module.__file__).read_text(encoding="utf-8")
    claim = source[source.index("claim_next_grounding_job"):]
    claim = claim[: claim.index("async def get_map")]
    assert "update(AppMap)" in claim
    assert 'AppMap.grounding_status == "building"' in claim
    assert "AppMap.grounding_started_at.is_(None)" in claim
    assert ".returning(AppMap)" in claim


async def test_grounding_retries_preserve_cumulative_adjudication_budget():
    app_map = make_map()
    app_map.grounding_metrics = {"adjudication_calls": 199}
    repo = FakeGroundingRepository(app_map)
    attempts = []
    async def noop(ctx):
        pass
    async def adjudicate(ctx):
        attempts.append(ctx.ledger.spend())
    async def gate(ctx):
        ctx.final_status = "partial"
        app_map.grounding_metrics = dict(ctx.metrics)
    stages = GroundingStages(candidates=noop, match=noop, adjudicate=adjudicate,
                             author=noop, probe=noop, journeys=noop, conflicts=noop, gate=gate)
    await execute_grounding(repo, app_map, stages)
    await execute_grounding(repo, app_map, stages)
    assert attempts == [True, False]
    assert app_map.grounding_metrics["adjudication_calls"] == 200


async def test_gate_coverage_uses_element_subjects_and_full_expectations(monkeypatch):
    from markettwin_database.models.knowledge import MapExpectation, MapJourney

    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    graph = seed_graph(repo, app_map)
    element = graph["buy"]
    repo.journeys = [MapJourney(
        id=uuid4(), intent="Buy", steps=[{"element_id": str(element.id),
                                         "map_page_state_id": str(element.map_page_state_id)}],
        success_state_id=element.map_page_state_id,
    )]
    repo.expectations = [MapExpectation(
        id=uuid4(), subject_kind="element", subject_id=element.id,
        oracle_source="documentation", status="owner-confirmed", promoted_by="owner",
        assertion={"kind": "element_state"}, assertion_origin="deterministic",
    )]
    stages = production_stages(None)
    ctx = grounding_job.GroundingContext(repository=repo, app_map=app_map)
    await stages.candidates(ctx)
    real_coverage = grounding_job.expectation_coverage
    observed = {}
    def coverage(**kwargs):
        value = real_coverage(**kwargs)
        observed.update(value)
        return value
    monkeypatch.setattr(grounding_job, "expectation_coverage", coverage)
    await stages.gate(ctx)
    assert observed["journeys_with_expectations"] == 1
    assert observed["verdict_eligible"] == 1
    assert observed["doc_sourced_share"] == 1.0


async def test_t_gr2_poller_claims_and_completes():
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    seed_graph(repo, app_map)
    repo.entries = [_doc_entry("'Buy now' completes the purchase.")]
    running: dict = {}
    await grounding_job._supervise(
        repo, production_stages(FakeDoor([])), running, door=FakeDoor([])
    )
    assert len(running) == 1
    await asyncio.gather(*running.values())
    assert app_map.grounding_status in ("ready", "partial")
    assert repo.completed_with is not None
    assert repo.completed_with["metrics"]["gate"]["release_scope"] in (
        "expectations",
        "partial",
        "none",
    )


async def test_t_gr3_stage_order_and_heartbeats():
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    calls: list[str] = []

    def stage(name):
        async def run(ctx):
            calls.append(name)

        return run

    async def gate(ctx):
        calls.append("gate")
        ctx.final_status = "partial"
        await ctx.repository.complete_grounding(
            ctx.app_map.id, status="partial", metrics=ctx.metrics
        )

    stages = GroundingStages(
        candidates=stage("candidates"),
        match=stage("match"),
        adjudicate=stage("adjudicate"),
        author=stage("author"),
        probe=stage("probe"),
        journeys=stage("journeys"),
        conflicts=stage("conflicts"),
        gate=gate,
    )
    result = await execute_grounding(repo, app_map, stages)
    assert result == "partial"
    assert calls == [
        "candidates",
        "match",
        "adjudicate",
        "author",
        "probe",
        "journeys",
        "conflicts",
        "gate",
    ]
    assert repo.metrics_writes >= 7  # one heartbeat per non-gate stage


async def test_t_gr4_stage_failure_recorded_job_continues():
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    seed_graph(repo, app_map)
    stages = production_stages(FakeDoor([]))

    async def broken_author(ctx):
        raise RuntimeError("author exploded")

    stages = GroundingStages(
        candidates=stages.candidates,
        match=stages.match,
        adjudicate=stages.adjudicate,
        author=broken_author,
        probe=stages.probe,
        journeys=stages.journeys,
        conflicts=stages.conflicts,
        gate=stages.gate,
    )
    result = await execute_grounding(repo, app_map, stages, door=FakeDoor([]))
    assert result in ("ready", "partial")
    failures = app_map.grounding_metrics["failures"]
    assert any(
        failure["stage"] == "author" and "author exploded" in failure["message"]
        for failure in failures
    )


async def test_t_gr5_job_crash_retains_original_error():
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    stages = production_stages(FakeDoor([]))

    async def broken_gate(ctx):
        raise RuntimeError("boom-original")

    stages = GroundingStages(
        candidates=stages.candidates,
        match=stages.match,
        adjudicate=stages.adjudicate,
        author=stages.author,
        probe=stages.probe,
        journeys=stages.journeys,
        conflicts=stages.conflicts,
        gate=broken_gate,
    )
    result = await execute_grounding(repo, app_map, stages, door=FakeDoor([]))
    assert result == "failed"
    assert repo.failed_with is not None
    assert repo.failed_with["code"] == "RuntimeError"
    assert "boom-original" in repo.failed_with["message"]


async def test_t_gr6_orphan_reaping():
    stale = make_map(
        grounding_started_at=datetime.now(UTC) - timedelta(minutes=31),
        grounding_completed_at=None,
    )
    repo = FakeGroundingRepository(stale)
    await grounding_job._reap_orphans(repo, {})
    assert repo.failed_with is not None
    assert repo.failed_with["code"] == "grounding_orphaned"

    fresh = make_map(
        grounding_started_at=datetime.now(UTC) - timedelta(minutes=5),
        grounding_completed_at=None,
    )
    repo2 = FakeGroundingRepository(fresh)
    await grounding_job._reap_orphans(repo2, {})
    assert repo2.failed_with is None


async def test_t_gr7_metrics_closed_key_set():
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    seed_graph(repo, app_map)
    repo.entries = [_doc_entry("'Buy now' completes the purchase.")]
    await execute_grounding(
        repo, app_map, production_stages(FakeDoor([])), door=FakeDoor([])
    )
    metrics = app_map.grounding_metrics
    assert set(metrics.keys()) == CLOSED_METRIC_KEYS
    assert metrics["promotions_at_grounding"] == 0
    assert metrics["gate"] is not None


async def test_t_gr8_regrounding_is_idempotent():
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    seed_graph(repo, app_map)
    repo.entries = [_doc_entry("'Buy now' completes the purchase.")]
    door = FakeDoor([])
    await execute_grounding(repo, app_map, production_stages(door), door=door)
    first_count = len(repo.expectations)
    first_conflicts = len(repo.conflicts)
    assert first_count > 0
    await execute_grounding(repo, app_map, production_stages(door), door=door)
    assert len(repo.expectations) == first_count
    assert len(repo.conflicts) == first_conflicts


def test_t_gr9_model_boundary_ast():
    import markettwin_execution_orchestrator.expectations as package

    package_dir = Path(package.__file__).parent
    model_touching = set()
    for path in package_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = ""
            names: list[str] = []
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.Import):
                module = ",".join(alias.name for alias in node.names)
            if (
                "models.ask" in module
                or "openai" in module
                or ("models" in module and "ask" in names)
            ):
                model_touching.add(path.name)
    assert model_touching == {"adjudicate.py"}
