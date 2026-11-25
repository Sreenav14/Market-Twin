"""Phase 4 freshness job (doc 23 sections 9, 10; T-FJ1 to T-FJ8).

Fake repository + fake stages throughout: the job's lifecycle,
supervision and terminal writes are pinned without a database or a
browser.
"""

import ast
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import markettwin_execution_orchestrator.freshness as freshness_package

from markettwin_execution_orchestrator.freshness.freshness_job import (
    _run_claimed,
    execute_preflight,
    reap_orphans,
)

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def _now():
    return NOW


class FakeRepository:
    def __init__(self, *, app_map=None, pages=()):
        self.app_map = app_map
        self.pages = list(pages)
        self.events = []
        self.completed = []
        self.failed = []
        self.freshness_updates = []
        self.history = []
        self.building = []
        self.latest_events = {}

    async def get_map(self, app_map_id):
        return self.app_map

    async def list_pages(self, app_map_id):
        return self.pages

    async def record_event(self, preflight_id, event_type, payload=None):
        self.events.append((event_type, payload or {}))

    async def complete_preflight(self, preflight_id, **kwargs):
        self.completed.append(kwargs)

    async def fail_preflight(self, preflight_id, **kwargs):
        self.failed.append(kwargs)

    async def update_map_freshness(self, app_map_id, **kwargs):
        self.freshness_updates.append(kwargs)

    async def append_history(self, rows):
        self.history.extend(rows)

    async def list_building_preflights(self, *, limit=10):
        return self.building[:limit]

    async def latest_event_at(self, preflight_id):
        return self.latest_events.get(preflight_id)


def _preflight(**overrides):
    base = {"id": uuid4(), "app_map_id": uuid4(), "trigger": "manual",
            "started_at": NOW}
    base.update(overrides)
    return SimpleNamespace(**base)


def _delta(counts, *, expected=0):
    return {
        "counts": counts,
        "expected_in_snapshot": expected,
        "basis_counts": {"state": 0, "html": 0},
    }


def _sweep_return(counts, *, expected=0, status="ready", history_rows=()):
    result = SimpleNamespace(
        status=status, deferred=[], tier_counts={"tier0_urls": 0},
        history_rows=list(history_rows),
    )
    return {"result": result, "delta": _delta(counts, expected=expected)}


def _stage(return_value=None, *, raises=None, calls=None):
    async def stage(*args):
        if calls is not None:
            calls.append(args)
        if raises is not None:
            raise raises
        return return_value

    return stage


def test_fj1_claim_refusal_leaves_the_job_untouched():
    preflight = _preflight()
    repository = FakeRepository(app_map=SimpleNamespace(id=preflight.app_map_id))
    stage_calls = []

    class FakeSession:
        def __init__(self, acquired):
            self.acquired = acquired

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def scalar(self, statement, *_args, **_kwargs):
            assert "pg_try_advisory_xact_lock" in str(statement)
            return self.acquired

        async def execute(self, *_args, **_kwargs):
            return None

    def factory(acquired):
        return lambda: FakeSession(acquired)

    asyncio.run(
        _run_claimed(
            factory(False), repository, preflight,
            sweep_stage=_stage(calls=stage_calls), reconcile_stage=None,
        )
    )
    assert stage_calls == []
    assert repository.events == []
    assert repository.completed == [] and repository.failed == []

    asyncio.run(
        _run_claimed(
            factory(True), repository, preflight,
            sweep_stage=_stage(
                _sweep_return(
                    {"present": 0, "changed": 0, "unreachable": 0,
                     "missing": 0, "new": 0}
                ),
                calls=stage_calls,
            ),
            reconcile_stage=None,
        )
    )
    assert len(stage_calls) == 1
    assert repository.completed and repository.completed[0]["status"] == "ready"


def test_fj2_terminal_writes_for_an_all_present_sweep():
    preflight = _preflight()
    repository = FakeRepository(
        app_map=SimpleNamespace(id=preflight.app_map_id),
        pages=[SimpleNamespace(id=uuid4())],
    )
    status = asyncio.run(
        execute_preflight(
            repository,
            preflight,
            sweep_stage=_stage(
                _sweep_return(
                    {"present": 1, "changed": 0, "unreachable": 0,
                     "missing": 0, "new": 0},
                    expected=1,
                    history_rows=[{"canonical_url": "https://app.example.com/"}],
                )
            ),
            reconcile_stage=None,
            now=_now,
        )
    )
    assert status == "ready"
    assert repository.completed[0]["status"] == "ready"
    assert repository.freshness_updates[0]["freshness_state"] == "current"
    metrics = repository.freshness_updates[0]["freshness_metrics"]
    assert metrics["preflight_id"] == str(preflight.id)
    assert metrics["outcome_counts"]["present"] == 1
    assert repository.history  # history rows were appended
    event_types = [event_type for event_type, _ in repository.events]
    assert event_types[0] == "preflight.started"
    assert event_types[-1] == "preflight.completed"


def test_fj3_orphan_reaping_measures_events_not_started_at():
    old = NOW - timedelta(hours=3)
    fresh = _preflight(started_at=old)          # old start, fresh event
    orphan = _preflight(started_at=old)         # old start, stale event
    silent = _preflight(started_at=old)         # no events, old start
    newborn = _preflight(started_at=NOW)        # no events, just created
    repository = FakeRepository()
    repository.building = [fresh, orphan, silent, newborn]
    repository.latest_events = {
        fresh.id: NOW - timedelta(minutes=1),
        orphan.id: NOW - timedelta(minutes=31),
    }
    reaped = asyncio.run(reap_orphans(repository, now=_now))
    assert reaped == 2
    assert {call["failure_code"] for call in repository.failed} == {
        "preflight_orphaned"
    }
    assert len(repository.failed) == 2


def test_fj4_a_stage_crash_fails_the_job_and_touches_no_freshness():
    preflight = _preflight()
    repository = FakeRepository(app_map=SimpleNamespace(id=preflight.app_map_id))
    status = asyncio.run(
        execute_preflight(
            repository,
            preflight,
            sweep_stage=_stage(raises=RuntimeError("browser exploded")),
            reconcile_stage=None,
            now=_now,
        )
    )
    assert status == "failed"
    assert repository.completed == []
    assert repository.freshness_updates == []  # a crash proves nothing (C11)
    failure = repository.failed[0]
    assert failure["failure_code"] == "RuntimeError"
    assert failure["failure_message"] == "browser exploded"
    assert failure["failure_site"] == "freshness_job:execute_preflight"
    assert repository.events[-1][0] == "preflight.failed"


def test_fj5_unreachable_only_outcome_mints_no_successor():
    preflight = _preflight()
    repository = FakeRepository(app_map=SimpleNamespace(id=preflight.app_map_id))
    reconcile_calls = []
    status = asyncio.run(
        execute_preflight(
            repository,
            preflight,
            sweep_stage=_stage(
                _sweep_return(
                    {"present": 0, "changed": 0, "unreachable": 2,
                     "missing": 0, "new": 0},
                    expected=2,
                )
            ),
            reconcile_stage=_stage(uuid4(), calls=reconcile_calls),
            now=_now,
        )
    )
    assert status == "ready"
    assert reconcile_calls == []
    assert repository.freshness_updates[0]["freshness_state"] == "stale"


def test_fj6_changed_outcome_reconciles_and_carries_its_delta():
    preflight = _preflight()
    repository = FakeRepository(app_map=SimpleNamespace(id=preflight.app_map_id))
    successor_id = uuid4()
    delta = _delta(
        {"present": 0, "changed": 1, "unreachable": 0, "missing": 0, "new": 0},
        expected=1,
    )

    async def sweep_stage(*args):
        return {
            "result": SimpleNamespace(
                status="ready", deferred=[], tier_counts={}, history_rows=[]
            ),
            "delta": delta,
        }

    async def reconcile_stage(repository_, preflight_, app_map_, result_, delta_):
        delta_["skills_demoted"] = ["00000000-0000-0000-0000-000000000001"]
        return successor_id

    status = asyncio.run(
        execute_preflight(
            repository, preflight,
            sweep_stage=sweep_stage, reconcile_stage=reconcile_stage, now=_now,
        )
    )
    assert status == "ready"
    event_types = [event_type for event_type, _ in repository.events]
    assert "preflight.reconcile.started" in event_types
    completed_event = next(
        payload for event_type, payload in repository.events
        if event_type == "preflight.reconcile.completed"
    )
    assert completed_event["resulting_map_id"] == str(successor_id)
    # The outcome written is the delta reconcile annotated (section 7.5).
    assert repository.completed[0]["outcome"]["skills_demoted"] == [
        "00000000-0000-0000-0000-000000000001"
    ]


def test_fj7_a_partial_sweep_never_sets_current():
    preflight = _preflight()
    repository = FakeRepository(app_map=SimpleNamespace(id=preflight.app_map_id))
    status = asyncio.run(
        execute_preflight(
            repository,
            preflight,
            sweep_stage=_stage(
                _sweep_return(
                    {"present": 1, "changed": 0, "unreachable": 0,
                     "missing": 0, "new": 0},
                    expected=2,
                    status="partial",
                )
            ),
            reconcile_stage=None,
            now=_now,
        )
    )
    assert status == "partial"
    assert repository.completed[0]["status"] == "partial"
    assert repository.freshness_updates[0]["freshness_state"] == "stale"


def test_fj8_the_freshness_package_makes_no_model_calls():
    # AST pin (doc 23 section 3, T-FJ8): no import in the package may
    # reach a model client or the ask door. The allowlist is empty.
    package_dir = Path(freshness_package.__file__).parent
    banned_roots = {"litellm", "openai", "anthropic"}
    offenders = []
    for path in sorted(package_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                root = module.split(".", 1)[0]
                if (
                    root in banned_roots
                    or "ask_door" in module
                    or "model_client" in module
                ):
                    offenders.append((path.name, module))
    assert offenders == []


# ---------------------------------------------------------------------------
# FRESH-1 wiring proofs: the PRODUCTION stage composition (T-FJ1..FJ8
# inject fake stages, which is how the four wiring defects survived).
# These two tests call _build_production_stages' own closures with the
# execute_preflight contract's argument shapes, the real delta builder,
# the real reconcile_preflight and the real _demote_skills.
# ---------------------------------------------------------------------------

from markettwin_execution_orchestrator.freshness import freshness_job
from markettwin_execution_orchestrator.freshness import preflight_sweep
from markettwin_execution_orchestrator.freshness.preflight_sweep import (
    SweepResult,
)
from markettwin_execution_orchestrator.workflow.coverage_delta import (
    build_preflight_delta,
)


class _FakeStageRoom:
    def __init__(self, **kwargs):
        self.validate = lambda url: url
        self.render = object()
        self.aria_excerpts = {}

    async def close(self):
        return None


class _FakeSweepFetcher:
    def __init__(self, **kwargs):
        pass


def _fresh1_page(url, *, state_id):
    page_id = uuid4()
    page = SimpleNamespace(
        id=page_id, canonical_url=url, crawl_status="complete"
    )
    state = SimpleNamespace(
        id=uuid4(), map_page_id=page_id, state_id=state_id,
        state_key="default",
    )
    return page, state


def test_fj9_production_sweep_stage_matches_the_job_contract(monkeypatch):
    page, state = _fresh1_page("https://example.test/agents", state_id="st-1")
    app_map = SimpleNamespace(
        id=uuid4(), application_id=uuid4(), target_id=uuid4(),
        base_url="https://example.test/", version_number=3,
    )
    preflight = SimpleNamespace(id=uuid4(), app_map_id=app_map.id)

    class Repo:
        async def list_pages(self, app_map_id):
            return [page]

        async def list_states(self, app_map_id):
            return [state]

        async def record_event(self, preflight_id, event_type, payload):
            assert preflight_id == preflight.id
            assert event_type == "preflight.test"
            assert payload == {"ok": True}
            return None

    swept = SweepResult(
        status="ready",
        tier1={"https://example.test/agents": {
            "http_status": 200, "fetch_error": None, "differs": True}},
        tier2={"https://example.test/agents": {
            "outcome": "changed", "recorded_state_id": "st-1",
            "live_state_id": "st-1", "basis": "signature",
            "reason": None, "html_drift": False}},
        recollected={"https://example.test/agents": ("sitemap",)},
    )

    async def fake_run_sweep(*, repository, preflight, app_map, pages, states_by_page,
                             fetch, sitemap_fetch, render, validate, resolve_link,
                             emit, render_cap, wall_budget_seconds):
        assert render_cap == freshness_job.PREFLIGHT_RENDER_CAP
        assert wall_budget_seconds == freshness_job.PREFLIGHT_WALL_BUDGET_SECONDS
        await emit("preflight.test", {"ok": True})
        return swept

    monkeypatch.setattr(freshness_job, "_StageRoom", _FakeStageRoom)
    monkeypatch.setattr(freshness_job, "_SweepFetcher", _FakeSweepFetcher)
    monkeypatch.setattr(preflight_sweep, "run_sweep", fake_run_sweep)
    sweep_stage, _reconcile_stage = freshness_job._build_production_stages(
        session_factory=lambda: None
    )
    # The contract's exact call shape: (repository, preflight, app_map).
    out = asyncio.run(sweep_stage(Repo(), preflight, app_map))
    assert out["result"] is swept
    assert out["delta"]["counts"]["changed"] == 1
    assert [entry["url"] for entry in out["delta"]["changed"]] == [
        "https://example.test/agents"
    ]


def test_fj10_production_reconcile_demotes_the_stale_skill_end_to_end(
    monkeypatch,
):
    page, state = _fresh1_page("https://example.test/agents", state_id="st-1")
    app_map = SimpleNamespace(
        id=uuid4(), workspace_id=uuid4(), application_id=uuid4(),
        target_id=uuid4(), base_url="https://example.test/",
        version_number=3, harvest_status="ready", census_metrics={},
    )
    preflight = SimpleNamespace(id=uuid4(), app_map_id=app_map.id)
    version = SimpleNamespace(
        id=uuid4(), skill_id=uuid4(), lifecycle_status="active",
        verified_fingerprint={
            "start_state_id": "st-1", "terminal_state_id": "st-1"},
    )
    skill = SimpleNamespace(id=version.skill_id)
    transitions = []

    class FreshRepo:
        async def list_pages(self, app_map_id):
            return [page]

        async def list_states(self, app_map_id):
            return [state]

        async def list_journeys(self, app_map_id):
            return []

        async def get_map(self, app_map_id):
            return app_map

        async def mint_successor(self, base, *, preflight, builder_version,
                                 freshness_metrics, completed_at):
            return SimpleNamespace(
                id=uuid4(), census_metrics={},
                census_config={
                    "origin": "reconcile",
                    "base_map_id": str(base.id),
                    "preflight_id": str(preflight.id),
                },
            )

        async def set_resulting_map(self, preflight_id, resulting_map_id):
            return None

        async def copy_forward(self, **kwargs):
            return {}

        async def page_status_counts(self, app_map_id):
            return {"reachable": 1}

        async def harvest_counts(self, app_map_id):
            return {"reachable": 1, "visited": 1, "enriched_groups": 1,
                    "template_groups": 1, "spend_calls": 0,
                    "spend_tokens": 0, "skill_verified": False,
                    "skill_reason": "fixture"}

        async def apply_successor_gates(self, successor, release=None,
                                        ledger=None):
            return None

    class HarvestRepo:
        def __init__(self, session_factory):
            pass

        async def list_skills_for_scope(self, *, workspace_id,
                                        application_id, target_id):
            return [skill]

        async def list_versions_for_skill(self, skill_id):
            return [version]

        async def get_skill_version(self, version_id):
            return version

        async def apply_skill_transition(self, version_id, *, fields,
                                         event):
            for key, value in fields.items():
                setattr(version, key, value)
            transitions.append(event)
            return version

    async def fake_visit_pages(**kwargs):
        return {}

    async def fake_enrich_touched(**kwargs):
        return None

    import markettwin_execution_orchestrator.harvest.harvest_repository as hr

    monkeypatch.setattr(freshness_job, "_StageRoom", _FakeStageRoom)
    monkeypatch.setattr(freshness_job, "_SweepFetcher", _FakeSweepFetcher)
    monkeypatch.setattr(freshness_job, "_visit_pages", fake_visit_pages)
    monkeypatch.setattr(freshness_job, "_enrich_touched", fake_enrich_touched)
    monkeypatch.setattr(hr, "HarvestRepository", HarvestRepo)
    _sweep_stage, reconcile_stage = freshness_job._build_production_stages(
        session_factory=lambda: None
    )
    block = {
        "map_id": str(app_map.id), "version_number": 3,
        "routes_truncated": False, "counts": {"expected": 1},
        "pages": [{"url": "https://example.test/agents",
                   "status": "complete",
                   "states": [{"state_id": "st-1"}]}],
    }
    delta = build_preflight_delta(
        map_block=block,
        tier1={"https://example.test/agents": {
            "http_status": 200, "fetch_error": None, "differs": True}},
        tier2={"https://example.test/agents": {
            "outcome": "changed", "recorded_state_id": "st-1",
            "live_state_id": "st-1", "basis": "signature",
            "reason": None, "html_drift": False}},
        recollected={"https://example.test/agents": ("sitemap",)},
    )
    result = SweepResult(status="ready")
    # The contract's exact call shape:
    # (repository, preflight, app_map, result, delta).
    successor_id = asyncio.run(
        reconcile_stage(FreshRepo(), preflight, app_map, result, delta)
    )
    assert successor_id is not None
    # The demotion actually fired, through the lifecycle authority:
    assert version.lifecycle_status == "suspect"
    assert delta["skills_demoted"] == [str(version.id)]
    assert transitions and transitions[0]["kind"] == "demotion"
    assert transitions[0]["from_status"] == "active"
    assert transitions[0]["to_status"] == "suspect"


def test_fj11_stalled_job_is_awaited_before_it_is_closed(monkeypatch):
    # ORC1-04: the stall watchdog cancelled a wedged job and wrote
    # its terminal state without awaiting the task, so the job's
    # teardown (its stage room close) raced the terminal write.
    # The fix awaits the cancelled task (bounded) first: at the
    # moment of the terminal write, teardown has already run.
    state = {"teardown_done": False, "fail_calls": []}
    preflight = _preflight(started_at=datetime.now(UTC))
    app_map = SimpleNamespace(id=preflight.app_map_id)

    class PollerRepository:
        def __init__(self):
            self.building = [preflight]
            self.event_calls = 0

        async def list_building_preflights(self, *, limit=10):
            return self.building[:limit]

        async def latest_event_at(self, preflight_id):
            self.event_calls += 1
            if self.event_calls <= 5:
                return datetime.now(UTC)
            # Older than the 15-minute stall watchdog, younger than
            # the 30-minute orphan reap: the stall branch owns it.
            return datetime.now(UTC) - timedelta(minutes=20)

        async def get_map(self, app_map_id):
            return app_map

        async def list_pages(self, app_map_id):
            return []

        async def record_event(self, preflight_id, event_type, payload=None):
            return None

        async def fail_preflight(self, preflight_id, **kwargs):
            state["fail_calls"].append((kwargs, state["teardown_done"]))
            self.building = []

        async def complete_preflight(self, preflight_id, **kwargs):
            raise AssertionError("a stalled job never completes")

    repository = PollerRepository()
    monkeypatch.setattr(
        freshness_job, "FreshnessRepository", lambda factory: repository
    )

    class LockSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def scalar(self, statement, *_args, **_kwargs):
            return True

        async def execute(self, *_args, **_kwargs):
            return None

    async def hanging_stage(repository_, preflight_, app_map_):
        try:
            await asyncio.sleep(3600)
        finally:
            state["teardown_done"] = True

    async def reconcile_stage(*args):
        return None

    async def scenario():
        poller = asyncio.create_task(
            freshness_job.run_preflight_poller(
                lambda: LockSession(),
                sweep_stage=hanging_stage,
                reconcile_stage=reconcile_stage,
                poll_seconds=0.01,
            )
        )
        try:
            for _ in range(500):
                if state["fail_calls"]:
                    break
                await asyncio.sleep(0.01)
        finally:
            poller.cancel()
            await asyncio.gather(poller, return_exceptions=True)

    asyncio.run(scenario())
    assert len(state["fail_calls"]) == 1
    kwargs, teardown_done_at_write = state["fail_calls"][0]
    assert kwargs["failure_code"] == "preflight_stalled"
    assert teardown_done_at_write is True


def test_sweep_fetcher_records_redirect_hop(monkeypatch):
    """T-FJ12 (live preflight c672bc72): execute_preflight died with
    TypeError on the first redirect — the sweep fetcher built its
    redirect hop with a ``location`` keyword the shared FetchHop does
    not accept. This drives the real _SweepFetcher (the class
    execute_preflight instantiates) against a stubbed httpx client, so
    the hop is constructed exactly as production constructs it."""

    import httpx

    from markettwin_execution_orchestrator.freshness.freshness_job import (
        _SweepFetcher,
    )

    class _Response:
        def __init__(self, status, headers, body=b""):
            self.status_code = status
            self.headers = headers
            self._body = body

        async def aiter_bytes(self):
            yield self._body

    class _Stream:
        def __init__(self, response):
            self._response = response

        async def __aenter__(self):
            return self._response

        async def __aexit__(self, *exc):
            return False

    class _Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def stream(self, method, url):
            if url == "https://example.com/old":
                return _Stream(_Response(301, {"location": "/new"}))
            return _Stream(_Response(200, {}, b"ok"))

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    fetcher = _SweepFetcher(
        max_bytes=1024, timeout_seconds=5, validate=lambda url: None
    )
    result = asyncio.run(fetcher("https://example.com/old"))
    assert result.status == 200
    assert result.final_url == "https://example.com/new"
    assert len(result.redirect_chain) == 1
    hop = result.redirect_chain[0]
    assert hop.url == "https://example.com/old"
    assert hop.status == 301
