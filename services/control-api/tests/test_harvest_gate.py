"""Phase 1b harvest gate: repository delegation and application.

Doc 16 section 16, tests T-GT1 to T-GT4. The shared half of T-GT1 (the
gate matrix against the pure function) lives in shared-python's
test_app_map_common.py; here the repository's delegation and its
apply path are pinned against fake sessions.
"""

import random
from collections import deque
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

from markettwin_control_api.knowledge import map_repository
from markettwin_control_api.knowledge.map_repository import MapRepository
from markettwin_database.models.knowledge import AppMap
from markettwin_shared.app_map_common import (
    compute_harvest_gate as shared_compute_harvest_gate,
)


class FakeSession:
    """Just enough of AsyncSession for the repository's gate paths."""

    def __init__(self, *, app_map=None, execute_results=()):
        self._app_map = app_map
        self._execute_results = deque(execute_results)
        self.flush_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def begin(self):
        return self

    async def get(self, model, primary_key):
        return self._app_map

    async def execute(self, statement):
        return self._execute_results.popleft()

    async def flush(self):
        self.flush_count += 1


def factory_for(session):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


def make_map(**overrides):
    values = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "application_id": uuid4(),
        "target_id": uuid4(),
        "version_number": 1,
        "status": "ready",
        "release_state": "partial",
        "release_scope": "inventory",
        "base_url": "https://example.com/",
        "builder_version": "census-1a.1",
        "census_config": {},
        "census_metrics": {},
        "pattern_stats": {},
        "gate_metrics": {"rule": "inventory-1a.1", "expected": 100, "coverage": 1.0},
        "harvest_status": "not_started",
        "harvest_metrics": {
            "template_groups": {"groups": 4, "unenriched_groups": []}
        },
        "mapping_spend_calls": 4,
        "mapping_spend_tokens": 4000,
    }
    values.update(overrides)
    return AppMap(**values)


def rows_result(rows):
    return SimpleNamespace(all=lambda: list(rows))


# T-GT1 (repository half): the repository delegates to the shared function.

async def test_repository_gate_is_the_shared_gate():
    assert map_repository.compute_harvest_gate is shared_compute_harvest_gate
    app_map = make_map()
    session = FakeSession(
        app_map=app_map,
        execute_results=[rows_result([("visited", 98), ("blocked_wall", 2)])],
    )
    repository = MapRepository(factory_for(session))
    result = await repository.evaluate_harvest_gate(
        app_map.id, skill_verified=True, skill_reason=None
    )
    expected = shared_compute_harvest_gate(
        {
            "reachable": 100,
            "visited": 98,
            "blocked_auth": 0,
            "blocked_wall": 2,
            "failed": 0,
            "unprobed_budget": 0,
            "pending": 0,
            "enriched_groups": 4,
            "template_groups": 4,
            "spend_calls": 4,
            "spend_tokens": 4000,
            "skill_verified": True,
            "skill_reason": None,
        }
    )
    assert result == expected
    assert result.harvest_status == "ready"
    assert result.release_scope == "harvest"


# T-GT2: applying a ready gate writes the harvest fields and MERGES the
# gate metrics over the census block (the census keys stay).

async def test_apply_harvest_gate_merges_metrics_and_releases_harvest_scope():
    app_map = make_map()
    session = FakeSession(app_map=app_map)
    repository = MapRepository(factory_for(session))
    gate = shared_compute_harvest_gate(
        {
            "reachable": 100,
            "visited": 100,
            "blocked_auth": 0,
            "blocked_wall": 0,
            "failed": 0,
            "unprobed_budget": 0,
            "pending": 0,
            "enriched_groups": 4,
            "template_groups": 4,
            "spend_calls": 4,
            "spend_tokens": 4000,
            "skill_verified": True,
            "skill_reason": None,
        }
    )
    await repository.apply_harvest_gate(app_map.id, gate=gate)
    assert app_map.harvest_status == "ready"
    assert app_map.harvest_failure_code is None
    assert app_map.harvest_failure_site is None
    assert app_map.harvest_completed_at is not None
    assert app_map.release_state == "partial"
    assert app_map.release_scope == "harvest"
    assert app_map.gate_metrics["rule"] == "inventory-1a.1"  # census key kept
    assert app_map.gate_metrics["harvest_rule"] == "harvest-1b.1"
    assert app_map.gate_metrics["harvest_coverage"] == 1.0
    assert app_map.gate_metrics["spend_calls"] == 4


# T-GT3: a failed harvest records the failure trio and the release stays
# inventory-scoped; the census metrics still survive the merge.

async def test_apply_failed_harvest_gate_keeps_inventory_scope():
    app_map = make_map()
    session = FakeSession(app_map=app_map)
    repository = MapRepository(factory_for(session))
    gate = shared_compute_harvest_gate(
        {
            "reachable": 12,
            "visited": 0,
            "blocked_auth": 0,
            "blocked_wall": 0,
            "failed": 0,
            "unprobed_budget": 0,
            "pending": 12,
            "enriched_groups": 0,
            "template_groups": 0,
            "spend_calls": 0,
            "spend_tokens": 0,
            "skill_verified": False,
            "skill_reason": "no_journey_compiled",
        }
    )
    await repository.apply_harvest_gate(app_map.id, gate=gate)
    assert app_map.harvest_status == "failed"
    assert app_map.harvest_failure_code == "harvest_empty"
    assert app_map.harvest_failure_site == "map_repository:compute_harvest_gate"
    assert app_map.release_state == "partial"
    assert app_map.release_scope == "inventory"
    assert app_map.gate_metrics["rule"] == "inventory-1a.1"
    assert app_map.gate_metrics["skill_gate"] == "failed"


# T-GT4: no count combination can produce a 'trusted' release.
def test_harvest_gate_never_produces_trusted():
    rng = random.Random(20261114)
    for _ in range(300):
        reachable = rng.randrange(0, 500)
        visited = rng.randrange(0, reachable + 1) if reachable else 0
        counts = {
            "reachable": reachable,
            "visited": visited,
            "blocked_auth": rng.randrange(0, 20),
            "blocked_wall": rng.randrange(0, 20),
            "failed": rng.randrange(0, 20),
            "unprobed_budget": rng.randrange(0, 20),
            "pending": rng.randrange(0, 20),
            "enriched_groups": rng.randrange(0, 30),
            "template_groups": rng.randrange(0, 30),
            "spend_calls": rng.randrange(0, 300),
            "spend_tokens": rng.randrange(0, 1_000_000),
            "skill_verified": rng.random() < 0.5,
            "skill_reason": None,
        }
        result = shared_compute_harvest_gate(counts)
        assert result.release_state == "partial"
        assert result.release_scope in ("harvest", "inventory")
        assert result.harvest_status in ("ready", "partial", "failed")
        assert "trusted" not in result.metrics().values()
