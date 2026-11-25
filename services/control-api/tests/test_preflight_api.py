"""Phase 4 (doc 23 section 9.3): the manual preflight trigger API.

T-PA1–T-PA4: 202 on create, 200 joining an in-flight row, 409 on a
non-ready map and on a building harvest, 404 shapes mirroring
doc 16 section 10.1's endpoints; the read returns the row's
outcome/deferred/tier_counts verbatim.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response

from markettwin_control_api.api import app_maps as app_maps_api

WORKSPACE_ID = uuid4()
APPLICATION_ID = uuid4()
TARGET_ID = uuid4()
MAP_ID = uuid4()
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


class AsyncContext:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


class ScopeSession:
    """Serves _resolve_scope: an active application + target."""

    async def get(self, model, primary_key):
        if primary_key == APPLICATION_ID:
            return SimpleNamespace(
                workspace_id=WORKSPACE_ID, status="active", deleted_at=None
            )
        if primary_key == TARGET_ID:
            return SimpleNamespace(
                application_id=APPLICATION_ID, status="active", deleted_at=None
            )
        return None


class FakePreflightRepository:
    def __init__(self, *, app_map=None, created=(None, False), preflight=None):
        self._app_map = app_map
        self._created = created
        self._preflight = preflight
        self.create_calls = []

    async def get_map_in_scope(self, map_id, *, application_id, target_id):
        return self._app_map

    async def create_preflight_for_map(self, map_id, *, trigger):
        self.create_calls.append((map_id, trigger))
        return self._created

    async def get_preflight_in_scope(
        self, preflight_id, *, map_id, application_id, target_id
    ):
        return self._preflight


def _ready_map(**overrides):
    values = {"id": MAP_ID, "status": "ready", "harvest_status": "ready"}
    values.update(overrides)
    return SimpleNamespace(**values)


def _preflight_row(**overrides):
    values = {
        "id": uuid4(),
        "status": "building",
        "resulting_map_id": None,
        "trigger": "manual",
        "outcome": None,
        "deferred": None,
        "tier_counts": None,
        "spend_seconds": None,
        "failure_code": None,
        "failure_message": None,
        "failure_site": None,
        "started_at": NOW,
        "completed_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _patch(monkeypatch, repository) -> None:
    monkeypatch.setattr(
        app_maps_api, "require_app_map_access", AsyncMock(return_value=uuid4())
    )
    database = SimpleNamespace(
        session_factory=lambda: AsyncContext(ScopeSession())
    )
    monkeypatch.setattr(
        app_maps_api, "get_database_runtime", lambda request: database
    )
    monkeypatch.setattr(app_maps_api, "_repository", lambda request: repository)


def _request():
    return SimpleNamespace()


async def _trigger(repository, monkeypatch):
    _patch(monkeypatch, repository)
    response = Response()
    result = await app_maps_api.trigger_app_map_preflight(
        WORKSPACE_ID, APPLICATION_ID, TARGET_ID, MAP_ID, _request(), response
    )
    return result, response


@pytest.mark.asyncio
async def test_preflight_trigger_creates_with_202(monkeypatch) -> None:
    """T-PA1: a ready map with no preflight in flight starts one —
    202, the new row's id and status."""
    row = _preflight_row()
    repository = FakePreflightRepository(
        app_map=_ready_map(), created=(row, True)
    )
    result, response = await _trigger(repository, monkeypatch)
    assert response.status_code == 202
    assert result.preflight_id == row.id
    assert result.map_id == MAP_ID
    assert result.status == "building"
    assert repository.create_calls == [(MAP_ID, "manual")]


@pytest.mark.asyncio
async def test_preflight_trigger_joins_in_flight_with_200(monkeypatch) -> None:
    """T-PA2: a preflight already in flight is joined, not duplicated
    — 200 with the in-flight row."""
    row = _preflight_row(status="building")
    repository = FakePreflightRepository(
        app_map=_ready_map(), created=(row, False)
    )
    result, response = await _trigger(repository, monkeypatch)
    assert response.status_code == 200
    assert result.preflight_id == row.id
    assert result.status == "building"


@pytest.mark.asyncio
async def test_preflight_trigger_conflicts_and_missing_map(monkeypatch) -> None:
    """T-PA3: 409 on a non-ready map and on a building harvest; 404
    when the map is outside the scope."""
    repository = FakePreflightRepository(app_map=_ready_map(status="building"))
    _patch(monkeypatch, repository)
    with pytest.raises(HTTPException) as excinfo:
        await app_maps_api.trigger_app_map_preflight(
            WORKSPACE_ID, APPLICATION_ID, TARGET_ID, MAP_ID,
            _request(), Response(),
        )
    assert excinfo.value.status_code == 409

    repository = FakePreflightRepository(
        app_map=_ready_map(harvest_status="building")
    )
    _patch(monkeypatch, repository)
    with pytest.raises(HTTPException) as excinfo:
        await app_maps_api.trigger_app_map_preflight(
            WORKSPACE_ID, APPLICATION_ID, TARGET_ID, MAP_ID,
            _request(), Response(),
        )
    assert excinfo.value.status_code == 409

    repository = FakePreflightRepository(app_map=None)
    _patch(monkeypatch, repository)
    with pytest.raises(HTTPException) as excinfo:
        await app_maps_api.trigger_app_map_preflight(
            WORKSPACE_ID, APPLICATION_ID, TARGET_ID, MAP_ID,
            _request(), Response(),
        )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_preflight_read_returns_the_row_verbatim(monkeypatch) -> None:
    """T-PA4: the read returns outcome/deferred/tier_counts verbatim
    from the row; a preflight outside the scope is a 404."""
    outcome = {
        "counts": {
            "present": 9, "changed": 1, "unreachable": 0, "missing": 0, "new": 0,
        },
        "release": {"status": "ready"},
    }
    deferred = [{"url": "https://example.com/slow", "reason": "render_cap"}]
    tier_counts = {"tier0_candidates": 12, "tier1_fetched": 12, "tier2_rendered": 2}
    row = _preflight_row(
        status="partial",
        resulting_map_id=uuid4(),
        outcome=outcome,
        deferred=deferred,
        tier_counts=tier_counts,
        spend_seconds=42.5,
        completed_at=NOW,
    )
    repository = FakePreflightRepository(app_map=_ready_map(), preflight=row)
    _patch(monkeypatch, repository)
    result = await app_maps_api.get_app_map_preflight(
        WORKSPACE_ID, APPLICATION_ID, TARGET_ID, MAP_ID, row.id, _request()
    )
    assert result.status == "partial"
    assert result.resulting_map_id == row.resulting_map_id
    assert result.outcome == outcome
    assert result.deferred == deferred
    assert result.tier_counts == tier_counts
    assert result.spend_seconds == 42.5

    repository = FakePreflightRepository(app_map=_ready_map(), preflight=None)
    _patch(monkeypatch, repository)
    with pytest.raises(HTTPException) as excinfo:
        await app_maps_api.get_app_map_preflight(
            WORKSPACE_ID, APPLICATION_ID, TARGET_ID, MAP_ID, uuid4(), _request()
        )
    assert excinfo.value.status_code == 404
