"""Phase 1b harvest job mechanics (doc 16 section 6, tests T-JB1 to
T-JB8). Everything is faked except the job logic itself and, in
T-JB8, the real module sources. The database half of T-JB1 — the
partial unique index that backs the claim — was verified against the
live migration (revision 51e27d6f11a2) at build time; the always-on
half here pins the claim protocol.
"""

import ast
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from markettwin_execution_orchestrator.harvest import harvest_job
from markettwin_execution_orchestrator.harvest.harvest_enrich import (
    EnrichResult,
)
from markettwin_execution_orchestrator.harvest.harvest_job import (
    AdvisoryClaim,
    HarvestStages,
    execute_harvest,
)
from markettwin_execution_orchestrator.harvest.harvest_replay import (
    VerifyResult,
)
from markettwin_execution_orchestrator.harvest.harvest_skill import (
    CompileResult,
)
from markettwin_execution_orchestrator.worker import STALL_WATCHDOG_SECONDS


def make_map(**overrides):
    values = {
        "id": uuid4(),
        "harvest_status": "building",
        "harvest_metrics": {
            "template_groups": {"groups": 1, "unenriched_groups": []}
        },
        "mapping_spend_calls": 1,
        "mapping_spend_tokens": 100,
        "base_url": "https://example.com/",
        "workspace_id": uuid4(),
        "application_id": uuid4(),
        "target_id": uuid4(),
        "harvest_started_at": datetime.now(UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeRepository:
    def __init__(self, app_map, *, counts=None, latest_event=None):
        self.map_row = app_map
        self.events = []
        self.gate = None
        self.failure = None
        self._counts = counts or {
            "reachable": 10,
            "visited": 10,
            "blocked_auth": 0,
            "blocked_wall": 0,
            "failed": 0,
            "unprobed_budget": 0,
            "pending": 0,
        }
        self._latest_event = latest_event

    async def harvest_counts(self, map_id):
        return dict(self._counts)

    async def record_event(self, map_id, event_type, payload):
        self.events.append((event_type, payload))

    async def get_map(self, map_id):
        return self.map_row

    async def apply_gate(self, map_id, *, gate):
        self.gate = gate
        self.map_row.harvest_status = gate.harvest_status

    async def fail_harvest(self, map_id, *, failure_code, failure_message,
                           failure_site):
        self.failure = {
            "code": failure_code,
            "message": failure_message,
            "site": failure_site,
        }
        self.map_row.harvest_status = "failed"

    async def latest_event_at(self, map_id):
        return self._latest_event

    # The Phase 3 library stage's surface (doc 22 section 6.1):
    # this fake's map has no journeys and no skills, so the stage
    # completes with zero counts.
    async def application_name(self, application_id):
        return "Example"

    async def list_journeys(self, map_id):
        return []

    async def work_list(self, app_map):
        return []

    async def list_states_for_map(self, map_id):
        return []

    async def list_skills_for_scope(self, *args, **kwargs):
        return []

    async def list_building_harvests(self):
        return [self.map_row] if self.map_row.harvest_status == "building" else []


def fake_stages(*, capture=None, enrich=None, compile_result="replay_verified",
                replay=None):
    async def default_capture(ctx):
        return None

    async def default_enrich(ctx):
        return EnrichResult(groups_total=1, enriched_groups=1, spend_calls=1,
                            spend_tokens=100)

    async def default_compile(ctx):
        if compile_result == "replay_verified":
            return CompileResult(
                journey=SimpleNamespace(id=uuid4()),
                skill_version=SimpleNamespace(id=uuid4()),
                definition={"success_assertion": {"state_id": "s"}},
                package={},
                registry_error=None,
            )
        return None

    async def default_replay(ctx):
        return VerifyResult("replay_verified", None, 2)

    return HarvestStages(
        capture=capture or default_capture,
        enrich=enrich or default_enrich,
        compile=compile_result if callable(compile_result) else default_compile,
        replay=replay or default_replay,
    )


# T-JB1 (always-on half): the advisory claim is single-winner — a
# session that loses the lock race reports False and is closed.
async def test_advisory_claim_single_winner():
    class FakeSession:
        def __init__(self, locked):
            self._locked = locked
            self.committed = False
            self.unlocked = False

        async def scalar(self, statement, params):
            return self._locked

        async def execute(self, statement, params):
            self.unlocked = True

        async def commit(self):
            self.committed = True

    sessions = []

    def factory(locked):
        session = FakeSession(locked)
        sessions.append(session)

        @asynccontextmanager
        async def make():
            yield session

        return SimpleNamespace(kw={"bind": SimpleNamespace(connect=make)})

    winner = AdvisoryClaim(factory(True), "harvest:x")
    assert await winner.acquire() is True
    await winner.release()
    assert sessions[0].unlocked is True

    loser = AdvisoryClaim(factory(False), "harvest:x")
    assert await loser.acquire() is False


# T-JB2: the poller claims a building map and the job runs to its gate.
async def test_poller_claims_and_completes_a_harvest():
    app_map = make_map()
    repository = FakeRepository(app_map)

    class FakeSession:
        async def scalar(self, statement, params):
            return True

        async def execute(self, statement, params):
            return None

        async def commit(self):
            return None

    @asynccontextmanager
    async def factory():
        yield FakeSession()

    await harvest_job._poll_once(
        repository, SimpleNamespace(kw={"bind": SimpleNamespace(connect=factory)}),
        lambda repo: fake_stages(),
    )
    for _ in range(20):
        await asyncio.sleep(0)
        if app_map.harvest_status != "building":
            break
    assert repository.gate is not None
    assert repository.gate.harvest_status == "ready"
    assert repository.gate.release_scope == "harvest"
    assert app_map.harvest_status == "ready"


# T-JB3: the event sequence for a full successful job is the section
# 6.4 sequence, ending in harvest.completed.
async def test_execute_harvest_event_sequence():
    app_map = make_map()
    repository = FakeRepository(app_map)
    status = await execute_harvest(repository, app_map, fake_stages())
    assert status == "ready"
    types = [event_type for event_type, _ in repository.events]
    assert types[0] == "harvest.started"
    assert types.count("harvest.stage.completed") == 4
    assert types[-2] == "harvest.completed"
    completed = repository.events[-2][1]
    assert completed == {"harvest_status": "ready", "gate_rule": "harvest-1b.1"}
    # Phase 3 (doc 22 section 6.1): the failure-isolated library
    # stage runs after the gate and closes the event sequence.
    assert types[-1] == "harvest.library.completed"
    assert repository.events[-1][1] == {
        "compiled": 0, "skipped": 0, "compile_failed": 0, "activated": 0}


# T-JB4: a stage crash closes the job failed with the ORIGINAL error
# retained, and the gate is never evaluated.
async def test_stage_crash_retains_error_and_skips_gate():
    async def exploding_capture(ctx):
        raise RuntimeError("boom in capture")

    app_map = make_map()
    repository = FakeRepository(app_map)
    status = await execute_harvest(
        repository, app_map, fake_stages(capture=exploding_capture)
    )
    assert status == "failed"
    assert repository.failure == {
        "code": "RuntimeError",
        "message": "boom in capture",
        "site": "harvest_job:capture",
    }
    assert repository.gate is None
    types = [event_type for event_type, _ in repository.events]
    assert types[-1] == "harvest.failed"


# T-JB5: orphan reaping closes a building map whose worker vanished
# (free lock, 30+ minutes of event silence) and leaves a recently
# active one alone.
async def test_orphan_reaping():
    stale = make_map(
        harvest_started_at=datetime.now(UTC) - timedelta(minutes=31)
    )
    fresh = make_map()
    repository = FakeRepository(
        stale, latest_event=datetime.now(UTC) - timedelta(minutes=31)
    )
    repository.list_building_harvests = lambda: _async_list([stale, fresh])

    async def latest_event_at(map_id):
        if map_id == stale.id:
            return datetime.now(UTC) - timedelta(minutes=31)
        return datetime.now(UTC) - timedelta(minutes=5)

    repository.latest_event_at = latest_event_at

    class FakeSession:
        async def scalar(self, statement, params):
            return True

        async def execute(self, statement, params):
            return None

        async def commit(self):
            return None

    @asynccontextmanager
    async def factory():
        yield FakeSession()

    failures = []
    repository.fail_harvest = lambda map_id, **kwargs: _async_record(
        failures, (map_id, kwargs)
    )
    await harvest_job._reap_orphans(
        repository, SimpleNamespace(kw={"bind": SimpleNamespace(connect=factory)}),
    )
    assert [item[0] for item in failures] == [stale.id]
    assert failures[0][1]["failure_code"] == "harvest_orphaned"


async def _async_list(value):
    return value


async def _async_record(store, value):
    store.append(value)


# T-JB6: supervision cancels a claimed harvest whose heartbeat is
# older than the watchdog window, and the cancellation closes the
# job as harvest_stalled with the reason retained.
async def test_watchdog_cancels_silent_harvest_and_retains_reason():
    app_map = make_map()
    repository = FakeRepository(
        app_map,
        latest_event=datetime.now(UTC)
        - timedelta(seconds=STALL_WATCHDOG_SECONDS + 60),
    )

    async def hanging_capture(ctx):
        await asyncio.sleep(3600)

    task = asyncio.create_task(
        execute_harvest(
            repository, app_map, fake_stages(capture=hanging_capture)
        )
    )
    harvest_job._harvest_tasks[app_map.id] = task
    try:
        await asyncio.sleep(0)
        await harvest_job._supervise(repository)
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        harvest_job._harvest_tasks.pop(app_map.id, None)
        harvest_job._harvest_cancelling.discard(app_map.id)
    assert repository.failure is not None
    assert repository.failure["code"] == "harvest_stalled"
    assert repository.failure["site"] == "harvest_job:stall_watchdog"


# T-JB7: a capture stage that hits the wall budget records the
# harvest.cap.reached event and the job still lands its gate.
async def test_wall_cap_event_recorded_and_gate_still_lands():
    async def capped_capture(ctx):
        ctx.wall_cap_reached = True
        ctx.wall_unprobed = 3

    app_map = make_map()
    repository = FakeRepository(
        app_map,
        counts={
            "reachable": 10,
            "visited": 7,
            "blocked_auth": 0,
            "blocked_wall": 0,
            "failed": 0,
            "unprobed_budget": 3,
            "pending": 0,
        },
    )
    status = await execute_harvest(
        repository, app_map, fake_stages(capture=capped_capture)
    )
    cap_events = [
        payload
        for event_type, payload in repository.events
        if event_type == "harvest.cap.reached"
    ]
    assert cap_events == [{"kind": "wall", "spend": {"unprobed": 3}}]
    assert status == "partial"  # 7/10 visited is below the 0.98 line
    assert repository.gate is not None


# T-JB8: the model boundary — model-call imports exist ONLY in
# harvest/enrich.py across the harvest package and the run-side
# lookup module.
def test_model_boundary_ast_guard():
    package_root = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "markettwin_execution_orchestrator"
    )
    forbidden_roots = (
        "litellm",
        "openai",
        "anthropic",
        "markettwin_execution_orchestrator.models",
    )
    offenders = []
    candidates = sorted((package_root / "harvest").glob("*.py"))
    lookup = package_root / "workflow" / "map_lookup.py"
    if lookup.exists():
        candidates.append(lookup)
    for path in candidates:
        if path.name in ("harvest_enrich.py", "skill_reverify.py"):
            # The two sanctioned model-call sites: enrichment
            # (doc 16) and the section 9.3 model-assisted heal
            # diagnosis (doc 22 — a fixed-choice locator pick,
            # capped per job and recorded on the usage ledger).
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            for module in modules:
                if any(
                    module == root or module.startswith(root + ".")
                    for root in forbidden_roots
                ):
                    offenders.append(f"{path.name}: {module}")
            if isinstance(node, ast.Name) and node.id == "_model_json":
                offenders.append(f"{path.name}: _model_json reference")
            if isinstance(node, ast.Attribute) and node.attr == "_model_json":
                offenders.append(f"{path.name}: _model_json reference")
    assert offenders == []
