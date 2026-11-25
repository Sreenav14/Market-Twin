"""Phase 4 (doc 23 section 6.2): the run-creation preflight step.

T-TT1–T-TT3 pin the creation step's contract: non-verdict kinds
never preflight; a verdict run inserts, waits (bounded), and pins
the successor; a wait expiry still creates the run on the swept
version; a preflight-row read error is a creation error (1a D16
posture) while a preflight job failure is disclosed data. T-SN1 pins
snapshot immutability (C2) across a preflight + reconcile; T-SN2
pins that creation itself writes nothing on the swept version (the
orchestrator-side half of the section 5.4 spy lives in the
orchestrator's test_freshness_repository.py).
"""

import json
from collections import deque
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.exc import IntegrityError

from markettwin_control_api.api import test_run as test_run_api
from markettwin_control_api.database import DatabaseRuntime
from markettwin_control_api.persistence.repositories import (
    AllowedOriginRecord,
    ApplicationRecord,
    TargetAuthorizationRecord,
    TargetRecord,
    TestRunRecord,
    WorkspaceAccess,
)
from markettwin_database.models.knowledge import AppMap

BUILT_AT = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
SETTINGS = SimpleNamespace(
    preflight_wait_seconds=5.0,
    preflight_wait_poll_seconds=0.01,
    preflight_reuse_hours=24.0,
)


class AsyncContext:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


def _fake_query_result(rows):
    return SimpleNamespace(
        all=lambda: list(rows),
        scalars=lambda: SimpleNamespace(
            all=lambda: list(rows),
            first=lambda: rows[0] if rows else None,
        ),
        scalar_one=lambda: rows[0] if rows else None,
    )


class FakeDatabaseSession:
    """Session fake: repository fakes ignore it; the map block queries
    it; ``get`` serves the pinned-map load from a prepared map dict."""

    def __init__(self, *, execute_results=(), scalars_results=(), maps=None):
        self._execute_results = deque(execute_results)
        self._scalars_results = deque(scalars_results)
        self._maps = maps or {}

    def begin(self):
        return AsyncContext(None)

    async def execute(self, statement):
        rows = self._execute_results.popleft() if self._execute_results else []
        return _fake_query_result(rows)

    async def scalars(self, statement):
        rows = self._scalars_results.popleft() if self._scalars_results else []
        return _fake_query_result(rows)

    async def get(self, model, primary_key):
        return self._maps.get(primary_key)

    async def refresh(self, instance):
        return None


class FakeApplicationRepository:
    def __init__(self, application):
        self._application = application

    async def get_for_user(self, *, application_id, user_id):
        return self._application


class FakeWorkspaceRepository:
    def __init__(self, workspace):
        self._workspace = workspace

    async def get_for_user(self, *, workspace_id, user_id):
        return self._workspace


class FakeTargetRepository:
    def __init__(self, target):
        self._target = target

    async def get_for_user(self, *, target_id, user_id):
        return self._target


class FakeAuthorizationRepository:
    def __init__(self, authorization):
        self._authorization = authorization

    async def get_active(self, *, target_id):
        return self._authorization


class FakeTestRunRepository:
    def __init__(self, test_run):
        self._test_run = test_run
        self.create_arguments = None

    async def create(self, **kwargs):
        self.create_arguments = kwargs
        return self._test_run


def make_records():
    user_id, workspace_id, application_id, target_id = (uuid4() for _ in range(4))
    application = ApplicationRecord(
        application_id=application_id,
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        name="Demo Store",
        description=None,
        status="active",
    )
    workspace = WorkspaceAccess(
        workspace_id=workspace_id, name="Demo Workspace", status="active",
        role="owner",
    )
    target = TargetRecord(
        target_id=target_id,
        application_id=application_id,
        name="Production",
        environment="production",
        base_url="https://example.com/",
        requires_auth=False,
        status="active",
        allowed_origins=(
            AllowedOriginRecord(
                scheme="https", hostname="example.com", port=443,
                include_subdomains=False,
            ),
        ),
    )
    now = datetime.now(UTC)
    authorization = TargetAuthorizationRecord(
        authorization_id=uuid4(),
        target_id=target_id,
        created_by_user_id=user_id,
        authorized_by_user_id=user_id,
        status="authorized",
        authorization_basis="Owned application.",
        created_at=now,
        authorized_at=now,
        revoked_at=None,
        expires_at=None,
    )
    persisted_run = TestRunRecord(
        test_run_id=uuid4(),
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=target_id,
        created_by_user_id=user_id,
        status="draft",
        target_snapshot=test_run_api.build_target_snapshot(target),
        configuration_snapshot={},
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )
    return user_id, application, workspace, target, authorization, persisted_run


def make_map(application, target, *, version_number=3):
    return AppMap(
        id=uuid4(),
        workspace_id=application.workspace_id,
        application_id=application.application_id,
        target_id=target.target_id,
        version_number=version_number,
        status="ready",
        release_state="partial",
        release_scope="inventory",
        base_url="https://example.com/",
        builder_version="census-1a.1",
        census_config={},
        census_metrics={},
        pattern_stats={},
        gate_metrics={},
        census_expected_count=0,
        census_reachable_count=0,
        mapping_spend_calls=0,
        mapping_spend_tokens=0,
        mapping_spend_seconds=0.0,
        started_at=BUILT_AT,
        completed_at=BUILT_AT,
    )


def make_request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": []})


def patch_creation(monkeypatch, *, records, session, app_map) -> FakeTestRunRepository:
    user_id, application, workspace, target, authorization, persisted_run = records
    repository = FakeTestRunRepository(persisted_run)
    database = SimpleNamespace(session_factory=lambda: AsyncContext(session))

    async def authenticated_user_id(*, request):
        return user_id

    monkeypatch.setattr(test_run_api, "get_authenticated_user_id", authenticated_user_id)
    monkeypatch.setattr(
        test_run_api, "get_database_runtime",
        lambda request: cast(DatabaseRuntime, database),
    )
    monkeypatch.setattr(
        test_run_api, "ApplicationRepository",
        lambda _: FakeApplicationRepository(application),
    )
    monkeypatch.setattr(
        test_run_api, "WorkspaceRepository",
        lambda _: FakeWorkspaceRepository(workspace),
    )
    monkeypatch.setattr(
        test_run_api, "TargetRepository", lambda _: FakeTargetRepository(target)
    )
    monkeypatch.setattr(
        test_run_api, "TargetAuthorizationRepository",
        lambda _: FakeAuthorizationRepository(authorization),
    )
    monkeypatch.setattr(test_run_api, "TestRunRepository", lambda _: repository)
    monkeypatch.setattr(
        test_run_api.map_repository, "latest_ready_map",
        AsyncMock(return_value=app_map),
    )
    return repository


async def _create(records, *, run_kind=None) -> None:
    _, application, _, target, _, _ = records
    payload = test_run_api.CreateTestRunRequest(
        target_id=target.target_id,
        study_brief="Evaluate the shopping and checkout experience.",
        run_kind=run_kind,
    )
    await test_run_api.create_test_run(
        application.application_id, payload, make_request()
    )


def _empty_block_session(**kwargs):
    return FakeDatabaseSession(
        execute_results=[[("fetch_ok", 1)]],
        scalars_results=[[], []],
        **kwargs,
    )


# -- the step itself, over faked repository helpers -------------------


def _patch_step_helpers(monkeypatch, *, create=None, read=None, latest=None):
    if create is not None:
        monkeypatch.setattr(
            test_run_api.map_repository, "create_preflight", create
        )
    if read is not None:
        monkeypatch.setattr(test_run_api.map_repository, "get_preflight", read)
    if latest is not None:
        monkeypatch.setattr(
            test_run_api.map_repository, "latest_preflight_for_map", latest
        )


@pytest.mark.asyncio
async def test_step_reuses_a_recent_recorded_preflight(monkeypatch) -> None:
    """D6 reuse: a preflight inside the reuse window with its outcome
    recorded is pinned as-is — no row is inserted, no wait happens."""
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    app_map.freshness_state = "stale"
    app_map.last_preflight_at = datetime.now(UTC) - timedelta(hours=2)
    receipt_id = uuid4()
    app_map.freshness_metrics = {"preflight_id": str(receipt_id)}

    async def create_must_not_run(session, *, app_map, trigger):
        raise AssertionError("reuse must not insert a preflight row")

    async def read(session, preflight_id):
        assert preflight_id == receipt_id
        return SimpleNamespace(status="ready", app_map_id=app_map.id, resulting_map_id=None)

    _patch_step_helpers(monkeypatch, create=create_must_not_run, read=read)
    database = SimpleNamespace(session_factory=lambda: AsyncContext(None))
    pinned_id, context = await test_run_api._preflight_creation_step(
        database=database, app_map=app_map, settings=SETTINGS
    )
    assert pinned_id == app_map.id
    assert context["preflight_status"] == "reused"
    assert context["pinned_via_preflight"] is False
    assert context["last_preflight_id"] == str(receipt_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("has_recent_failed_receipt", [False, True])
async def test_step_waits_and_reports_failure_as_data(monkeypatch, has_recent_failed_receipt) -> None:
    """A failed preflight JOB is disclosed data (section 6.2 step 4):
    creation proceeds on the swept version with status 'failed'."""
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    row_id = uuid4()
    failed_receipt_id = uuid4()
    completed_at = datetime.now(UTC)
    if has_recent_failed_receipt:
        app_map.last_preflight_at = completed_at
        app_map.freshness_metrics = {"preflight_id": str(failed_receipt_id)}

    async def create(session, *, app_map, trigger):
        return SimpleNamespace(id=row_id)

    async def read(session, preflight_id):
        return SimpleNamespace(
            id=preflight_id, status="failed", resulting_map_id=None,
            completed_at=completed_at,
        )

    _patch_step_helpers(monkeypatch, create=create, read=read)
    database = SimpleNamespace(
        session_factory=lambda: AsyncContext(FakeDatabaseSession())
    )
    pinned_id, context = await test_run_api._preflight_creation_step(
        database=database, app_map=app_map, settings=SETTINGS
    )
    assert pinned_id == app_map.id
    assert context["preflight_status"] == "failed"
    assert context["last_preflight_id"] == str(row_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("winner_status", ["building", "ready", "failed"])
async def test_step_joins_the_in_flight_row_on_single_flight(
    monkeypatch,
    winner_status,
) -> None:
    """The single-flight index's IntegrityError joins the in-flight
    row instead of starting a second sweep (section 6.2 step 3)."""
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    row_id = uuid4()
    successor_id = uuid4()

    async def create(session, *, app_map, trigger):
        raise IntegrityError("insert", {}, Exception("single flight"))

    async def latest(session, app_map_id):
        return SimpleNamespace(id=row_id, status=winner_status)

    async def read(session, preflight_id):
        assert preflight_id == row_id
        return SimpleNamespace(
            id=row_id,
            status="ready",
            resulting_map_id=successor_id,
            completed_at=datetime.now(UTC),
        )

    _patch_step_helpers(monkeypatch, create=create, read=read, latest=latest)
    database = SimpleNamespace(
        session_factory=lambda: AsyncContext(FakeDatabaseSession())
    )
    pinned_id, context = await test_run_api._preflight_creation_step(
        database=database, app_map=app_map, settings=SETTINGS
    )
    assert pinned_id == successor_id
    assert context["preflight_status"] == "completed"
    assert context["pinned_via_preflight"] is True


# -- T-TT1: non-verdict kinds never preflight --------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("run_kind", ["slop", "persona"])
async def test_non_verdict_creation_never_preflights(
    monkeypatch, run_kind
) -> None:
    """T-TT1: slop + persona creation on a mapped app creates no
    map_preflights row and does not wait — the creation step is not
    executed at all (its insert is wired to fail this test)."""
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    session = _empty_block_session()
    repository = patch_creation(
        monkeypatch, records=records, session=session, app_map=app_map
    )

    async def create_must_not_run(session, *, app_map, trigger):
        raise AssertionError(f"{run_kind} creation inserted a preflight row")

    _patch_step_helpers(monkeypatch, create=create_must_not_run)
    await _create(records, run_kind=run_kind)

    assert repository.create_arguments is not None
    block = repository.create_arguments["configuration_snapshot"]["app_map"]
    assert block["freshness"]["preflight_status"] == "not_required"


# -- T-TT2: verdict creation inserts, waits, pins the successor -------


@pytest.mark.asyncio
@pytest.mark.parametrize("successor_status", ["ready", "failed"])
async def test_verdict_creation_pins_only_an_eligible_successor(monkeypatch, successor_status) -> None:
    """T-TT2: explore_test creation inserts the preflight, waits for
    it, and pins the successor when resulting_map_id is set; the
    snapshot freshness block matches section 8.1's shape with
    pinned_via_preflight true."""
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    successor = make_map(application, target, version_number=4)
    successor.status = successor_status
    successor.freshness_state = "current"
    successor.freshness_metrics = {
        "preflight_id": "pf-new",
        "outcome_counts": {
            "present": 4, "changed": 1, "unreachable": 0, "missing": 0, "new": 0,
        },
        "deferred_count": 0,
    }
    successor.last_preflight_at = datetime.now(UTC)
    row_id = uuid4()
    session = _empty_block_session(maps={successor.id: successor})
    repository = patch_creation(
        monkeypatch, records=records, session=session, app_map=app_map
    )

    async def create(session, *, app_map, trigger):
        assert trigger == "run_creation"
        return SimpleNamespace(id=row_id)

    async def read(session, preflight_id):
        return SimpleNamespace(
            id=row_id,
            status="ready",
            resulting_map_id=successor.id,
            completed_at=datetime.now(UTC),
        )

    _patch_step_helpers(monkeypatch, create=create, read=read)
    monkeypatch.setattr(test_run_api, "get_settings", lambda: SETTINGS)
    await _create(records)

    assert repository.create_arguments is not None
    block = repository.create_arguments["configuration_snapshot"]["app_map"]
    if successor_status == "failed":
        assert block["map_id"] == str(app_map.id)
        assert block["freshness"]["preflight_status"] == "failed"
        assert block["freshness"]["pinned_via_preflight"] is False
        return
    assert block["map_id"] == str(successor.id)
    assert block["version_number"] == 4
    freshness = block["freshness"]
    assert freshness["preflight_status"] == "completed"
    assert freshness["pinned_via_preflight"] is True
    assert freshness["ttl_trust"] == "not_applicable"
    assert freshness["state"] == "current"
    assert freshness["outcome_counts"]["changed"] == 1
    assert freshness["last_preflight_id"] == str(row_id)


# -- T-TT3: the C3 pair -------------------------------------------------


@pytest.mark.asyncio
async def test_pending_preflight_returns_a_preparing_draft(monkeypatch) -> None:
    """T-TT3a: the wait budget expires with the job still building —
    creation completes, pinning the swept version, with
    preflight_status 'timed_out' disclosed."""
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    row_id = uuid4()

    async def create(session, *, app_map, trigger):
        return SimpleNamespace(id=row_id)

    async def read(session, preflight_id):
        return SimpleNamespace(
            id=row_id, status="building", resulting_map_id=None,
            completed_at=None,
        )

    _patch_step_helpers(monkeypatch, create=create, read=read)
    database = SimpleNamespace(
        session_factory=lambda: AsyncContext(FakeDatabaseSession())
    )
    settings = SimpleNamespace(
        preflight_wait_seconds=0.05,
        preflight_wait_poll_seconds=0.01,
        preflight_reuse_hours=24.0,
    )
    pinned_id, context = await test_run_api._preflight_creation_step(
        database=database, app_map=app_map, settings=settings
    )
    assert pinned_id == app_map.id
    assert context["preflight_status"] == "preparing"
    assert context["last_preflight_id"] == str(row_id)
    assert context["pinned_via_preflight"] is False


@pytest.mark.asyncio
async def test_preflight_row_read_error_is_a_creation_error(
    monkeypatch,
) -> None:
    """T-TT3b: a preflight-row READ raising propagates out of
    creation (1a D16 posture) — the opposite side of the pair from a
    job failure's disclosed-data handling."""
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    row_id = uuid4()

    async def create(session, *, app_map, trigger):
        return SimpleNamespace(id=row_id)

    async def read(session, preflight_id):
        raise RuntimeError("database read failed")

    _patch_step_helpers(monkeypatch, create=create, read=read)
    database = SimpleNamespace(
        session_factory=lambda: AsyncContext(FakeDatabaseSession())
    )
    with pytest.raises(RuntimeError, match="database read failed"):
        await test_run_api._preflight_creation_step(
            database=database, app_map=app_map, settings=SETTINGS
        )


# -- T-SN1 / T-SN2 -------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_immutable_across_preflight_and_reconcile(
    monkeypatch,
) -> None:
    """T-SN1: a run created before a preflight keeps a byte-identical
    snapshot block after the preflight + reconcile complete — the
    frozen block is the run's, and later freshness writes land on the
    map versions, never in it (C2)."""
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    session = _empty_block_session()
    repository = patch_creation(
        monkeypatch, records=records, session=session, app_map=app_map
    )

    async def reused_step(*, database, app_map, settings):
        return app_map.id, {
            "preflight_status": "reused",
            "pinned_via_preflight": False,
            "last_preflight_id": None,
            "last_preflight_at": None,
        }

    monkeypatch.setattr(test_run_api, "_preflight_creation_step", reused_step)
    await _create(records)

    assert repository.create_arguments is not None
    frozen = json.dumps(
        repository.create_arguments["configuration_snapshot"], sort_keys=True
    )

    # The preflight + reconcile now complete against the same map
    # object the creation read: freshness fields move, a successor
    # version exists. None of it may reach the frozen snapshot.
    app_map.freshness_state = "stale"
    app_map.last_preflight_at = datetime.now(UTC)
    app_map.freshness_metrics = {
        "preflight_id": "pf-later",
        "outcome_counts": {
            "present": 3, "changed": 1, "unreachable": 0, "missing": 0, "new": 1,
        },
        "deferred_count": 0,
    }
    successor = make_map(application, target, version_number=4)
    assert successor.version_number == 4

    assert (
        json.dumps(
            repository.create_arguments["configuration_snapshot"],
            sort_keys=True,
        )
        == frozen
    )


@pytest.mark.asyncio
async def test_creation_writes_nothing_on_the_swept_version(
    monkeypatch,
) -> None:
    """T-SN2 (creation half): with a preflight in flight for the map,
    run creation inserts only the preflight row — every field of the
    swept version is exactly as it was (the orchestrator half, over
    the preflight job's own writes, is in the orchestrator suite)."""
    records = make_records()
    _, application, _, target, _, _ = records
    app_map = make_map(application, target)
    before = {
        key: value
        for key, value in vars(app_map).items()
        if not key.startswith("_")
    }
    session = _empty_block_session()
    repository = patch_creation(
        monkeypatch, records=records, session=session, app_map=app_map
    )

    async def timed_out_step(*, database, app_map, settings):
        return app_map.id, {
            "preflight_status": "timed_out",
            "pinned_via_preflight": False,
            "last_preflight_id": "pf-running",
            "last_preflight_at": None,
        }

    monkeypatch.setattr(test_run_api, "_preflight_creation_step", timed_out_step)
    await _create(records)

    assert repository.create_arguments is not None
    after = {
        key: value
        for key, value in vars(app_map).items()
        if not key.startswith("_")
    }
    assert after == before

@pytest.mark.asyncio
@pytest.mark.parametrize("status,age,eligible,expected", [
    ("building", 0, True, "blocked"),
    ("building", 90, True, "timed_out"),
    ("failed", 0, True, "failed"),
    ("partial", 0, True, "completed"),
    ("ready", 0, False, "failed"),
])
async def test_start_resolves_draft_receipt(monkeypatch, status, age, eligible, expected):
    _, app, _, target, _, run = make_records()
    original = make_map(app, target)
    successor = make_map(app, target, version_number=4)
    if not eligible:
        successor.target_id = uuid4()
    receipt = SimpleNamespace(id=uuid4(), app_map_id=original.id, resulting_map_id=successor.id,
                              completed_at=None if status == "building" else datetime.now(UTC), status=status)
    block = {"map_id": str(original.id), "freshness": {
        "preflight_status": "preparing", "last_preflight_id": str(receipt.id)}}
    run = replace(run, created_at=run.created_at-timedelta(seconds=age), configuration_snapshot={"app_map": block})
    session = _empty_block_session(maps={successor.id: successor, original.id: original})
    repo = AsyncMock()
    _patch_step_helpers(monkeypatch, read=AsyncMock(return_value=receipt))
    monkeypatch.setattr(test_run_api, "get_settings", lambda: SETTINGS)
    if expected == "blocked":
        with pytest.raises(HTTPException, match="still preparing"):
            await test_run_api._finish_draft_preflight(session, run, repo)
        repo.update_configuration_snapshot.assert_not_called()
        return
    await test_run_api._finish_draft_preflight(session, run, repo)
    saved = repo.update_configuration_snapshot.await_args.kwargs["configuration_snapshot"]["app_map"]
    assert saved["freshness"]["preflight_status"] == expected
    assert saved["map_id"] == str(successor.id if expected == "completed" else original.id)


@pytest.mark.asyncio
async def test_duplicate_create_returns_the_original_run_before_queueing_preparation(monkeypatch):
    records = make_records()
    _, app, _, target, _, original_run = records
    repo = patch_creation(monkeypatch, records=records, session=_empty_block_session(), app_map=None)
    repo.lock_creation_request = AsyncMock(return_value=original_run)
    payload = test_run_api.CreateTestRunRequest(target_id=target.target_id, creation_request_id=uuid4(),
                                                study_brief="Evaluate the shopping experience.")
    result = await test_run_api.create_test_run(app.application_id, payload, make_request())
    assert result.id == original_run.test_run_id
    assert repo.create_arguments is None
