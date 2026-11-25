"""Phase 4 reconcile (doc 23 section 7; T-RC1 to T-RC7).

The composition is pinned with a fake repository and fake seams; the
pure gates are monkeypatched to canned verdicts (their own behaviour
is pinned by the shared test suites), so these tests own the version
arithmetic, the ordering, the overflow honesty and the ceiling.
"""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from markettwin_execution_orchestrator.freshness import reconcile
from markettwin_execution_orchestrator.freshness.reconcile import (
    carried_row_values,
    reconcile_preflight,
    successor_release,
)

A = "https://app.example.com/a"
B = "https://app.example.com/b"
C = "https://app.example.com/c"


def _gate(**kwargs):
    base = {
        "status": "ready", "release_state": "partial",
        "release_scope": "inventory", "failure_code": None,
        "failure_message": None,
    }
    base.update(kwargs)
    gate = SimpleNamespace(**base)
    gate.metrics = lambda: {"gate": base["release_scope"]}
    return gate


def _harvest_gate(**kwargs):
    base = {
        "harvest_status": "ready", "release_state": "partial",
        "release_scope": "harvest",
    }
    base.update(kwargs)
    gate = SimpleNamespace(**base)
    gate.metrics = lambda: {"gate": "harvest"}
    return gate


class FakeRepository:
    def __init__(self, calls):
        self.calls = calls
        self.successor = SimpleNamespace(id=uuid4(), census_metrics={})
        self.mint_kwargs = None
        self.copy_kwargs = None
        self.release = None

    async def mint_successor(self, app_map, **kwargs):
        self.calls.append("mint")
        self.mint_kwargs = kwargs
        return self.successor

    async def set_resulting_map(self, preflight_id, resulting_map_id):
        self.calls.append("set_resulting_map")
        self.resulting = resulting_map_id

    async def copy_forward(self, **kwargs):
        self.calls.append("copy_forward")
        self.copy_kwargs = kwargs
        return {"carried": 3, "changed": 1, "new": 1, "missing": 0,
                "unreachable": 0}

    async def page_status_counts(self, app_map_id):
        return {"fetch_ok": 3}

    async def harvest_counts(self, app_map_id):
        return {}

    async def apply_successor_gates(self, successor, *, release, ledger):
        self.calls.append("gates")
        self.release = release


def _seam(name, calls, return_value=None):
    async def seam(*args, **kwargs):
        calls.append(name)
        return return_value

    return seam


def _run_reconcile(monkeypatch, *, delta, result=None, cap=100, calls=None,
                   demoted=()):
    calls = calls if calls is not None else []
    repository = FakeRepository(calls)
    monkeypatch.setattr(
        reconcile, "compute_inventory_gate",
        lambda counts, overflow_count: _gate(),
    )
    monkeypatch.setattr(
        reconcile, "compute_harvest_gate", lambda counts: _harvest_gate()
    )
    if result is None:
        result = SimpleNamespace(
            deferred=[], page_fingerprints={}, tier2={}, captures={}
        )
    preflight = SimpleNamespace(id=uuid4())
    app_map = SimpleNamespace(
        id=uuid4(), version_number=3, release_scope="inventory",
        release_state="partial", harvest_status="ready",
    )

    async def demote(repository_, successor_, delta_, **kwargs):
        calls.append("demote")
        return list(demoted)

    successor_id = asyncio.run(
        reconcile_preflight(
            repository, preflight, app_map, result, delta,
            visit_new_pages=_seam("visit_new", calls),
            persist_changed_pages=_seam("persist_changed", calls),
            enrich_touched=_seam("enrich", calls),
            demote_skills=demote,
            new_page_cap=cap,
        )
    )
    return successor_id, repository, result, calls


def _delta(**overrides):
    delta = {
        "changed": [], "missing": [], "unreachable": [], "new": [],
        "counts": {"present": 0, "changed": 0, "unreachable": 0,
                   "missing": 0, "new": 0},
        "basis_counts": {"state": 0, "html": 0},
    }
    delta.update(overrides)
    return delta


def test_rc1_mint_is_findable_before_the_copy_starts(monkeypatch):
    delta = _delta(changed=[{"url": A, "recorded_state_id": "s1",
                             "live_state_id": "s2", "basis": "state"}])
    successor_id, repository, _result, calls = _run_reconcile(
        monkeypatch, delta=delta
    )
    assert successor_id == repository.successor.id
    assert calls.index("mint") < calls.index("set_resulting_map")
    assert calls.index("set_resulting_map") < calls.index("copy_forward")
    assert repository.resulting == repository.successor.id
    assert repository.mint_kwargs["builder_version"] == "preflight-4.1"
    metrics = repository.mint_kwargs["freshness_metrics"]
    assert metrics["outcome_counts"] == delta["counts"]
    assert repository.copy_kwargs["changed_urls"] == {A}
    # Re-observation and gates run before enrichment and demotion.
    assert calls.index("persist_changed") < calls.index("gates")
    assert calls.index("gates") < calls.index("enrich")


def test_rc2_carried_rows_share_evidence_by_key_and_remap_ids():
    page_id, successor_map_id = uuid4(), uuid4()
    row = SimpleNamespace(
        id=uuid4(), created_at="then", updated_at="then",
        app_map_id=uuid4(), map_page_id=page_id,
        object_key="app-maps/base/state/shot.png", sha256="abc123",
        kind="screenshot",
    )
    row.__table__ = SimpleNamespace(
        columns=[
            SimpleNamespace(name=name)
            for name in (
                "id", "created_at", "updated_at", "app_map_id",
                "map_page_id", "object_key", "sha256", "kind",
            )
        ]
    )
    values = carried_row_values(
        row,
        remap={
            "app_map_id": {row.app_map_id: successor_map_id},
            "map_page_id": {page_id: uuid4()},
        },
    )
    assert values["app_map_id"] == successor_map_id
    assert values["map_page_id"] != page_id
    # Q7: evidence is shared by object_key/sha256, never re-uploaded.
    assert values["object_key"] == "app-maps/base/state/shot.png"
    assert values["sha256"] == "abc123"
    assert "created_at" not in values and "updated_at" not in values
    assert values["id"] != row.id


def test_rc3_missing_pages_are_carried_as_the_gone_set(monkeypatch):
    delta = _delta(missing=[{"url": B, "http_status": 410}])
    _id, repository, _result, _calls = _run_reconcile(monkeypatch, delta=delta)
    assert repository.copy_kwargs["missing_urls"] == {B}


def test_rc4_new_page_overflow_is_named_and_recommends_a_remap(monkeypatch):
    delta = _delta(new=[
        {"url": A, "source_kinds": ["sitemap"]},
        {"url": B, "source_kinds": ["link_graph"]},
        {"url": C, "source_kinds": ["sitemap"]},
    ])
    _id, repository, result, _calls = _run_reconcile(
        monkeypatch, delta=delta, cap=2
    )
    copied_new = repository.copy_kwargs["new_pages"]
    assert [entry["canonical_url"] for entry in copied_new] == [A, B]
    assert result.deferred == [{"url": C, "reason": "new_page_cap"}]
    metrics = repository.mint_kwargs["freshness_metrics"]
    assert metrics["remap_recommended"] is True


def test_rc5_the_release_ceiling_binds_without_a_gate_behind_it():
    base = SimpleNamespace(
        release_scope="inventory", release_state="partial",
        harvest_status="ready",
    )
    # Inventory-only path: the inventory gate's scope stands (equal).
    release = successor_release(base, _gate(), None)
    assert release["release_scope"] == "inventory"
    assert release["status"] == "ready"
    # A genuinely re-run harvest gate earns the harvest scope itself.
    release = successor_release(base, _gate(), _harvest_gate())
    assert release["release_scope"] == "harvest"
    # A failed inventory gate fails the successor with its own code.
    failed = _gate(status="failed", release_state="failed",
                   release_scope=None, failure_code="empty_census",
                   failure_message="no denominator")
    release = successor_release(base, failed, None)
    assert release["status"] == "failed"
    assert release["release_scope"] is None
    assert release["failure_code"] == "empty_census"
    # A partial harvest gate: the map stands (census release), the
    # harvest axis reads partial.
    release = successor_release(
        base, _gate(), _harvest_gate(harvest_status="partial")
    )
    assert release["status"] == "ready"
    assert release["harvest_status"] == "partial"


def test_rc6_unreachable_pages_are_in_neither_work_set(monkeypatch):
    delta = _delta(unreachable=[{"url": A, "reason": "fetch_error"}])
    _id, repository, _result, calls = _run_reconcile(monkeypatch, delta=delta)
    assert repository.copy_kwargs["changed_urls"] == set()
    assert repository.copy_kwargs["missing_urls"] == set()
    assert repository.copy_kwargs["new_pages"] == []
    assert "visit_new" not in calls  # nothing to visit


def test_rc7_demotion_runs_last_and_annotates_the_outcome(monkeypatch):
    delta = _delta(changed=[{"url": A, "recorded_state_id": "s1",
                             "live_state_id": "s2", "basis": "state"}])
    _id, _repo, _result, calls = _run_reconcile(
        monkeypatch, delta=delta, demoted=["sv-1"]
    )
    assert calls[-1] == "demote"
    assert delta["skills_demoted"] == ["sv-1"]
    # No demotions -> the key stays absent (the outcome is not padded).
    delta2 = _delta()
    _run_reconcile(monkeypatch, delta=delta2, demoted=[])
    assert "skills_demoted" not in delta2
