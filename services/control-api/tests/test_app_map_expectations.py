"""Phase 2 expectation schema + migration (doc 21 section 4; T-SC1, T-SC2).

T-SC1 is metadata-level (always runs): the Phase 2 columns, checks and
tables exist in the ORM metadata and the legacy skill-registry columns
are nullable in the models, mirroring the migration. T-SC2 follows the
opt-in disposable-database convention of test_app_map_database.py and
pins the Wave 1 OQ2 fix against a real database: after upgrading to the
Phase 2 revision, the five legacy skills/skill_versions columns accept
NULL (they refused graph-scoped skill rows in Wave 1); after
downgrading, they are NOT NULL again and the Phase 2 tables are gone.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from markettwin_control_api.api import app_maps, test_run as test_run_api
from markettwin_control_api.knowledge import map_repository
from markettwin_database.base import Base
from markettwin_database.models import knowledge as knowledge_models  # noqa: F401
from markettwin_database.models.knowledge import (
    AppMap,
    MapConflict,
    MapExpectation,
    MapExpectationEvent,
    MapPage,
    MapPageState,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VERSIONS_DIR = REPOSITORY_ROOT / "database" / "migrations" / "versions"

OQ2_COLUMNS = {
    "skills": {"blueprint_id", "created_by_user_id"},
    "skill_versions": {"blueprint_id", "blueprint_version_id", "created_by_user_id"},
}


def _table(name: str):  # noqa: ANN202
    return Base.metadata.tables[f"knowledge.{name}"]


def _check_names(table) -> set[str]:  # noqa: ANN001, ANN202
    return {
        constraint.name
        for constraint in table.constraints
        if constraint.name is not None
    }


def test_t_sc1_phase2_schema_in_metadata() -> None:
    app_maps = _table("app_maps")
    for column in (
        "grounding_status",
        "grounding_metrics",
        "grounding_started_at",
        "grounding_completed_at",
        "grounding_failure_code",
        "grounding_failure_message",
        "grounding_failure_site",
    ):
        assert column in app_maps.columns, column
    assert "ck_app_maps_grounding_status_allowed" in _check_names(app_maps)
    index_names = {index.name for index in app_maps.indexes}
    assert "uq_app_maps_grounding_single_flight" in index_names
    assert "ix_app_maps_grounding_poll" in index_names

    expectations = _table("map_expectations")
    for column in (
        "assertion",
        "assertion_kind",
        "assertion_origin",
        "promoted_by",
        "promoted_at",
        "superseded_by_id",
        "last_checked_at",
        "last_check_result",
    ):
        assert column in expectations.columns, column
    assert expectations.columns["assertion"].nullable is True
    assert "conflicted" not in expectations.columns  # conflict is a status
    assert "ck_map_expectations_last_check_result_allowed" in _check_names(
        expectations
    )
    assert "ck_map_expectations_assertion_kind_allowed" in _check_names(
        expectations
    )
    assert "ck_map_expectations_assertion_origin_allowed" in _check_names(
        expectations
    )
    assert "ix_map_expectations_seeding" in {
        index.name for index in expectations.indexes
    }
    # The Phase 1b uniqueness the Board seeding relies on is untouched.
    assert "ix_map_expectations_subject" in {
        index.name for index in expectations.indexes
    }

    conflicts = _table("map_conflicts")
    for column in ("conflict_kind", "detection_source", "observed_subject_id", "run_id"):
        assert column in conflicts.columns, column
    assert conflicts.columns["conflict_kind"].nullable is False
    assert conflicts.columns["detection_source"].nullable is False
    assert "ck_map_conflicts_kind_allowed" in _check_names(conflicts)
    assert "ck_map_conflicts_detection_source_allowed" in _check_names(conflicts)
    assert "ix_map_conflicts_open" in {index.name for index in conflicts.indexes}

    events = _table("map_expectation_events")
    assert "ck_map_expectation_events_type_allowed" in _check_names(events)
    for column in ("expectation_id", "event_type", "payload", "occurred_at"):
        assert column in events.columns, column
    assert "actor" not in events.columns  # the actor rides the payload

    reports = _table("graph_audit_reports")
    for column in ("audit_kind", "checks", "findings", "graph_fingerprint"):
        assert column in reports.columns, column
    assert "ck_graph_audit_reports_kind_allowed" in _check_names(reports)
    assert reports.columns["app_map_id"].nullable is True

    # OQ2 mirror: the ORM agrees with the relaxed database columns.
    for table_name, columns in OQ2_COLUMNS.items():
        table = _table(table_name)
        for column in columns:
            assert table.columns[column].nullable is True, (table_name, column)


def _phase2_revision() -> tuple[str, str, Path]:
    matches = sorted(VERSIONS_DIR.glob("*_add_phase_2_expectations_wiring.py"))
    assert len(matches) == 1, matches
    source = matches[0].read_text(encoding="utf-8")
    revision = re.search(r'^revision(?::\s*str)?\s*=\s*"([^"]+)"', source, re.M)
    down_revision = re.search(r'^down_revision(?::[^=]+)?=\s*"([^"]+)"', source, re.M)
    assert revision is not None and down_revision is not None
    return revision.group(1), down_revision.group(1), matches[0]


def test_t_sc2_migration_carries_oq2_relaxation() -> None:
    """Static pin (always runs): the revision relaxes exactly the OQ2 set."""

    revision, down_revision, path = _phase2_revision()
    assert down_revision == "51e27d6f11a2"
    source = path.read_text(encoding="utf-8")
    for table_name, columns in OQ2_COLUMNS.items():
        for column in columns:
            assert (
                f'op.alter_column("{table_name}", "{column}", nullable=True'
                in source
                or f'op.alter_column(\n        "{table_name}", "{column}", nullable=True'
                in source
                or f'"{column}", nullable=True' in source
            ), (table_name, column)
    upgrade_section = source.split("def downgrade")[0]
    for column in (
        "grounding_status",
        "assertion",
        "assertion_origin",
        "promoted_by",
        "superseded_by_id",
        "conflict_kind",
        "map_expectation_events",
        "graph_audit_reports",
    ):
        assert column in upgrade_section, column


async def _run_alembic(environment: dict[str, str], *arguments: str) -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "alembic", "-c", "database/alembic.ini", *arguments,
        cwd=REPOSITORY_ROOT, env=environment,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await asyncio.wait_for(process.communicate(), timeout=120)
    assert process.returncode == 0, output.decode("utf-8", errors="replace")


@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_DATABASE") != "1", reason="Local DB opt-in"
)
async def test_t_sc2_migration_round_trip_on_disposable_db() -> None:
    """Live pin: upgrade relaxes the OQ2 columns; downgrade restores them."""

    import asyncpg
    from markettwin_control_api.config import get_settings
    from sqlalchemy.engine import make_url

    revision, down_revision, _path = _phase2_revision()
    url = make_url(get_settings().database_url)
    assert url.host in {"localhost", "127.0.0.1", "::1"}
    name = "phase2_migration_" + uuid4().hex
    assert re.fullmatch(r"phase2_migration_[0-9a-f]{32}", name)
    environment = {
        **os.environ,
        "POSTGRES_HOST": url.host,
        "POSTGRES_PORT": str(url.port or 5432),
        "POSTGRES_DB": name,
        "POSTGRES_USER": url.username or "",
        "POSTGRES_PASSWORD": url.password or "",
    }

    async def connect(database: str | None = None):  # noqa: ANN202
        return await asyncpg.connect(
            host=url.host, port=url.port or 5432, user=url.username,
            password=url.password, database=database,
        )

    admin = await connect()
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    try:
        await _run_alembic(environment, "upgrade", revision)
        connection = await connect(name)
        try:
            rows = await connection.fetch(
                "SELECT table_name, column_name, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'knowledge' AND table_name IN "
                "('skills', 'skill_versions') AND column_name IN "
                "('blueprint_id', 'blueprint_version_id', 'created_by_user_id')"
            )
            relaxed = {
                (row["table_name"], row["column_name"])
                for row in rows
                if row["is_nullable"] == "YES"
            }
            expected = {
                (table, column)
                for table, columns in OQ2_COLUMNS.items()
                for column in columns
            }
            assert relaxed == expected
            tables = {
                row["table_name"]
                for row in await connection.fetch(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'knowledge'"
                )
            }
            assert {"map_expectation_events", "graph_audit_reports"} <= tables
        finally:
            await connection.close()
        await _run_alembic(environment, "downgrade", down_revision)
        connection = await connect(name)
        try:
            rows = await connection.fetch(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'knowledge' AND table_name IN "
                "('skills', 'skill_versions') AND column_name IN "
                "('blueprint_id', 'blueprint_version_id', 'created_by_user_id')"
            )
            assert rows and all(row["is_nullable"] == "NO" for row in rows)
            tables = {
                row["table_name"]
                for row in await connection.fetch(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'knowledge'"
                )
            }
            assert {"map_expectation_events", "graph_audit_reports"}.isdisjoint(
                tables
            )
        finally:
            await connection.close()
    finally:
        admin = await connect()
        try:
            await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        finally:
            await admin.close()


# --- Section 14.1 snapshot extension + section 9.3 resolution (T-SN, T-CF) ---

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


class _Context:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *args):
        return False


def _fake_result(rows):
    rows = list(rows)
    return SimpleNamespace(
        all=lambda: list(rows),
        scalars=lambda: SimpleNamespace(
            all=lambda: list(rows),
            first=lambda: rows[0] if rows else None,
        ),
        scalar_one=lambda: rows[0] if rows else None,
    )


class _FakeSession:
    """One session fake for both the API tests (get-programmed) and the
    snapshot builder (execute/scalars queues in pinned call order)."""

    def __init__(self, *, get_results=None, execute_results=(), scalars_results=()):
        self._get_results = dict(get_results or {})
        self._execute_results = deque(execute_results)
        self._scalars_results = deque(scalars_results)
        self.added: list[object] = []
        self.flush = AsyncMock()

    def begin(self):
        return _Context(None)

    async def get(self, model, ident):
        return self._get_results.get((model, ident))

    async def execute(self, statement):
        rows = self._execute_results.popleft() if self._execute_results else []
        return _fake_result(rows)

    async def scalars(self, statement):
        rows = self._scalars_results.popleft() if self._scalars_results else []
        return _fake_result(rows)

    def add(self, row):
        self.added.append(row)


def _make_map(**overrides) -> AppMap:
    values = dict(
        id=uuid4(),
        workspace_id=uuid4(),
        application_id=uuid4(),
        target_id=uuid4(),
        version_number=2,
        status="ready",
        release_state="partial",
        release_scope="inventory",
        base_url="https://example.com/",
        builder_version="census-1a.1",
        census_config={},
        census_metrics={},
        pattern_stats={},
        gate_metrics={},
        census_expected_count=1,
        census_reachable_count=1,
        mapping_spend_calls=0,
        mapping_spend_tokens=0,
        mapping_spend_seconds=0.0,
        started_at=NOW,
        completed_at=NOW,
        harvest_status="not_started",
        harvest_metrics={},
        grounding_status="not_started",
        grounding_metrics={},
    )
    values.update(overrides)
    return AppMap(**values)


def _make_page(app_map: AppMap, *, url: str) -> MapPage:
    return MapPage(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        app_map_id=app_map.id,
        canonical_url=url,
        route_pattern="/pricing",
        source_kinds=["sitemap"],
        crawl_status="fetch_ok",
        http_status=200,
        redirect_target=None,
        content_type="text/html",
        title="Pricing",
        requires_auth=False,
        roles_seen=[],
        source="census",
        confidence="high",
        last_verified_at=NOW,
        harvest_status="visited",
    )


def _make_expectation(
    app_map: AppMap, page: MapPage, **overrides
) -> MapExpectation:
    values = dict(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        app_map_id=app_map.id,
        subject_kind="page",
        subject_id=page.id,
        statement="The pricing page shows a billing toggle.",
        oracle_source="documentation",
        status="replay-verified",
        source_ref="entry-1:0",
        confidence="high",
        assertion={
            "kind": "page_text",
            "subject": {},
            "params": {"text": "Billing", "present": True},
        },
        assertion_kind="page_text",
        assertion_origin="deterministic",
    )
    values.update(overrides)
    return MapExpectation(**values)


@pytest.mark.asyncio
async def test_t_sn1_grounded_snapshot_block_carries_expectations() -> None:
    app_map = _make_map(harvest_status="ready", grounding_status="ready")
    page = _make_page(app_map, url="https://example.com/pricing")
    state = MapPageState(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        app_map_id=app_map.id,
        map_page_id=page.id,
        state_key="default",
        state_kind="default",
        state_id="state-1",
        element_signature="",
        form_signature="",
        source="harvest",
        confidence="high",
        last_verified_at=NOW,
    )
    eligible = _make_expectation(app_map, page)
    draft = _make_expectation(
        app_map,
        page,
        statement="A draft the model suggested.",
        oracle_source="model-draft",
        status="unverified",
        source_ref=None,
        assertion=None,
    )
    conflict = MapConflict(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        app_map_id=app_map.id,
        expectation_id=draft.id,
        observed_behaviour="The toggle is absent.",
        evidence_refs=[],
        status="open",
        conflict_kind="statement_vs_observation",
        detection_source="run",
    )
    session = _FakeSession(
        execute_results=[
            [("fetch_ok", 1)],  # census counts
            [("visited", 1)],  # harvest counts
            [2],  # expectation count
            [],  # snapshot elements
            [],  # snapshot journeys
            [],  # snapshot skills (empty: versions query is skipped)
            [eligible, draft],  # records: expectations
            [conflict],  # records: open conflicts
            [page],  # records: pages
            [state],  # records: states
            [],  # records: elements
            [],  # records: forms
            [],  # records: fields
            [],  # records: journeys
            [conflict],  # open conflicts for the block
        ],
        scalars_results=[[page], [state]],
    )
    block = await test_run_api._app_map_snapshot_block(session, app_map)
    assert block["expectations_truncated"] is False
    entries = block["expectations"]
    assert [entry["id"] for entry in entries] == [str(eligible.id), str(draft.id)]
    first = entries[0]
    assert first["verdict_eligible"] is True
    assert first["page_url"] == "https://example.com/pricing"
    assert first["assertion"] == {
        "kind": "page_text",
        "subject": {},
        "params": {"text": "Billing", "present": True},
    }
    assert first["assertion_origin"] == "deterministic"
    assert first["promoted"] is False
    second = entries[1]
    assert second["verdict_eligible"] is False
    assert second["has_open_conflict"] is True
    assert "assertion" not in second
    coverage = block["coverage"]
    assert coverage["expectations_total"] == 2
    assert coverage["verdict_eligible"] == 1
    assert coverage["expectations_by_source"] == {
        "documentation": 1,
        "owner-rule": 0,
        "observation": 0,
        "model-draft": 1,
    }
    assert coverage["conflicted_open"] == 1
    assert block["open_conflicts"] == [
        {
            "id": str(conflict.id),
            "expectation_id": str(draft.id),
            "conflict_kind": "statement_vs_observation",
            "observed_behaviour": "The toggle is absent.",
        }
    ]


@pytest.mark.asyncio
async def test_t_sn2_snapshot_byte_cap_drops_in_pinned_order(monkeypatch) -> None:
    # The cap sits between the measured ladder stages (pages dropped:
    # 2228 bytes; non-eligible draft also dropped: 1666), so pages and
    # the draft still drop in pinned order while the eligible entry
    # survives. It rose from 1500 when Phase 4's section 8.1 freshness
    # block became a permanent part of the snapshot — the post-drop
    # floor is 1666 bytes now, above the old cap.
    monkeypatch.setattr(map_repository, "SNAPSHOT_MAP_MAX_BYTES", 1800)
    app_map = _make_map(grounding_status="ready")
    page = _make_page(app_map, url="https://example.com/pricing")
    eligible = _make_expectation(app_map, page)
    draft = _make_expectation(
        app_map,
        page,
        statement="A draft the model suggested with a long statement. " * 4,
        oracle_source="model-draft",
        status="unverified",
        source_ref=None,
        assertion=None,
    )
    session = _FakeSession(
        execute_results=[
            [("fetch_ok", 1)],
            [eligible, draft],
            [],
            [page],
            [],
            [],
            [],
            [],
            [],
            [],
        ],
        scalars_results=[[page], []],
    )
    block = await test_run_api._app_map_snapshot_block(session, app_map)
    assert len(json.dumps(block).encode("utf-8")) <= 1800
    assert block["pages"] == []
    entries = block["expectations"]
    assert [entry["id"] for entry in entries] == [str(eligible.id)]
    assert block["expectations_truncated"] is True


def _patch_api(monkeypatch, *sessions, user_id=None):
    queue = deque(sessions)
    monkeypatch.setattr(
        app_maps,
        "get_database_runtime",
        lambda _: SimpleNamespace(
            session_factory=lambda: _Context(queue.popleft())
        ),
    )
    monkeypatch.setattr(
        app_maps,
        "require_app_map_access",
        AsyncMock(return_value=user_id or uuid4()),
    )


def _request():
    from fastapi import Request

    return Request({"type": "http", "method": "POST", "path": "/", "headers": []})


def _scope_sessions(app_map: AppMap):
    from markettwin_database.models.testing import Application, ApplicationTarget

    application = Application(
        id=app_map.application_id,
        workspace_id=app_map.workspace_id,
        created_by_user_id=uuid4(),
        name="Demo",
        status="active",
    )
    target = ApplicationTarget(
        id=app_map.target_id,
        application_id=app_map.application_id,
        name="Prod",
        environment="production",
        base_url="https://example.com/",
        status="active",
    )
    scope = _FakeSession(
        get_results={
            (Application, app_map.application_id): application,
            (ApplicationTarget, app_map.target_id): target,
        }
    )
    in_scope = _FakeSession(execute_results=[[app_map]])
    return scope, in_scope


def _conflict_setup(*, resolution_status="conflicted"):
    app_map = _make_map(harvest_status="ready", grounding_status="ready")
    page = _make_page(app_map, url="https://example.com/pricing")
    expectation = _make_expectation(
        app_map, page, status=resolution_status
    )
    conflict = MapConflict(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        app_map_id=app_map.id,
        expectation_id=expectation.id,
        observed_behaviour="The toggle is absent.",
        evidence_refs=[],
        status="open",
        conflict_kind="statement_vs_observation",
        detection_source="run",
    )
    return app_map, expectation, conflict


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["promote", "reject", "resolve"])
async def test_foreign_map_mutation_is_refused_before_writes(operation):
    app_map, expectation, conflict = _conflict_setup(resolution_status="unverified")
    session = _FakeSession(get_results={
        (MapExpectation, expectation.id): expectation,
        (MapConflict, conflict.id): conflict,
    })
    repository = map_repository.MapRepository(lambda: _Context(session))
    foreign_map_id = uuid4()
    with pytest.raises(ValueError, match="_not_found"):
        if operation == "promote":
            await repository.record_promotion(expectation.id, app_map_id=foreign_map_id, actor="owner")
        elif operation == "reject":
            await repository.record_rejection(
                expectation.id, app_map_id=foreign_map_id, actor="owner", reason="reject")
        else:
            await repository.resolve_conflict(
                conflict.id, app_map_id=foreign_map_id, actor="owner", resolution="docs-win")
    assert expectation.status == "unverified"
    assert conflict.status == "open"
    assert session.added == []
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_conflict_resolution_is_refused():
    repository = map_repository.MapRepository(lambda: pytest.fail("must validate before transaction"))
    with pytest.raises(ValueError, match="invalid_resolution"):
        await repository.resolve_conflict(
            uuid4(), app_map_id=uuid4(), actor="owner", resolution="garbage")


@pytest.mark.asyncio
async def test_t_cf4_resolve_docs_win_reseeds_the_expectation(monkeypatch) -> None:
    app_map, expectation, conflict = _conflict_setup()
    scope, in_scope = _scope_sessions(app_map)
    resolve_session = _FakeSession(
        get_results={
            (MapConflict, conflict.id): conflict,
            (MapExpectation, expectation.id): expectation,
        }
    )
    _patch_api(monkeypatch, scope, in_scope, resolve_session)
    result = await app_maps.resolve_app_map_conflict(
        app_map.workspace_id,
        app_map.application_id,
        app_map.target_id,
        app_map.id,
        conflict.id,
        _request(),
        payload=app_maps.AppMapResolveConflictRequest(resolution="docs-win"),
    )
    assert result.status == "resolved"
    assert result.resolution == "docs-win"
    # Resolving a disagreement does not establish execution evidence.
    assert expectation.status == "unverified"
    assert expectation.superseded_by_id is None
    event_types = [
        row.event_type
        for row in resolve_session.added
        if isinstance(row, MapExpectationEvent)
    ]
    assert event_types == ["resolved"]


@pytest.mark.asyncio
async def test_t_cf5_resolve_app_win_supersedes_with_owner_rule(monkeypatch) -> None:
    app_map, expectation, conflict = _conflict_setup()
    scope, in_scope = _scope_sessions(app_map)
    resolve_session = _FakeSession(
        get_results={
            (MapConflict, conflict.id): conflict,
            (MapExpectation, expectation.id): expectation,
        }
    )
    _patch_api(monkeypatch, scope, in_scope, resolve_session)
    result = await app_maps.resolve_app_map_conflict(
        app_map.workspace_id,
        app_map.application_id,
        app_map.target_id,
        app_map.id,
        conflict.id,
        _request(),
        payload=app_maps.AppMapResolveConflictRequest(
            resolution="app-win",
            owner_text="The toggle is optional at checkout.",
        ),
    )
    assert result.status == "resolved"
    successors = [
        row for row in resolve_session.added if isinstance(row, MapExpectation)
    ]
    assert len(successors) == 1
    successor = successors[0]
    assert successor.oracle_source == "owner-rule"
    assert successor.status == "owner-confirmed"
    assert successor.statement == "The toggle is optional at checkout."
    assert successor.source_ref == f"conflict:{conflict.id}"
    # C2: the original keeps its source and status; superseded_by_id
    # retires it everywhere (section 8.2 rule 3).
    assert expectation.oracle_source == "documentation"
    assert expectation.status == "conflicted"
    assert expectation.superseded_by_id == successor.id
    event_types = [
        row.event_type
        for row in resolve_session.added
        if isinstance(row, MapExpectationEvent)
    ]
    assert event_types == ["resolved", "authored", "superseded"]


@pytest.mark.asyncio
async def test_t_cf6_owner_decided_needs_text_and_write_role(monkeypatch) -> None:
    app_map, _expectation, conflict = _conflict_setup()
    _patch_api(monkeypatch)
    with pytest.raises(HTTPException) as failure:
        await app_maps.resolve_app_map_conflict(
            app_map.workspace_id,
            app_map.application_id,
            app_map.target_id,
            app_map.id,
            conflict.id,
            _request(),
            payload=app_maps.AppMapResolveConflictRequest(
                resolution="owner-decided"
            ),
        )
    assert failure.value.status_code == 422

    async def deny(request, workspace_id, *, write):
        raise HTTPException(status_code=403, detail="Workspace write access is required.")

    monkeypatch.setattr(app_maps, "require_app_map_access", deny)
    with pytest.raises(HTTPException) as failure:
        await app_maps.resolve_app_map_conflict(
            app_map.workspace_id,
            app_map.application_id,
            app_map.target_id,
            app_map.id,
            conflict.id,
            _request(),
            payload=app_maps.AppMapResolveConflictRequest(
                resolution="owner-decided", owner_text="The toggle is optional."
            ),
        )
    assert failure.value.status_code == 403


@pytest.mark.asyncio
async def test_grounding_trigger_conflict_names_both_statuses(monkeypatch) -> None:
    app_map = _make_map(harvest_status="building", grounding_status="not_started")
    scope, in_scope = _scope_sessions(app_map)
    _patch_api(monkeypatch, scope, in_scope)
    with pytest.raises(HTTPException) as failure:
        await app_maps.trigger_app_map_grounding(
            app_map.workspace_id,
            app_map.application_id,
            app_map.target_id,
            app_map.id,
            _request(),
            SimpleNamespace(status_code=202),
            payload=app_maps.AppMapGroundingRequest(probe=False),
        )
    assert failure.value.status_code == 409
    assert "harvest_status='building'" in failure.value.detail
    assert "grounding_status='not_started'" in failure.value.detail
