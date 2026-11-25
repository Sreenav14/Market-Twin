"""Exercise the Phase 4 freshness migration in a disposable loopback
database.

Follows the opt-in convention of test_app_map_database.py (doc 14
section 13 item 16): these tests run only when
MARKETTWIN_TEST_DATABASE=1 and only against a throwaway database
created per test. The pair checks the upgrade creates the three
freshness tables, the app_maps freshness columns with their CHECK
and defaults, map_page_states.screenshot_phash and the partial
single-flight index; and that the downgrade removes exactly those.
"""

import asyncio
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from markettwin_control_api.config import get_settings
from sqlalchemy.engine import make_url

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VERSIONS_DIR = REPOSITORY_ROOT / "database" / "migrations" / "versions"

EXPECTED_TABLES = {
    "map_preflights",
    "map_preflight_events",
    "map_fingerprint_history",
}
EXPECTED_MAP_COLUMNS = {"freshness_state", "last_preflight_at", "freshness_metrics"}


def _freshness_revision() -> tuple[str, str]:
    matches = sorted(VERSIONS_DIR.glob("*_add_phase_4_freshness_schema.py"))
    assert len(matches) == 1, matches
    source = matches[0].read_text(encoding="utf-8")
    revision = re.search(r'^revision(?::\s*str)?\s*=\s*"([^"]+)"', source, re.M)
    down_revision = re.search(
        r'^down_revision(?::[^=]+)?=\s*"([^"]+)"', source, re.M
    )
    assert revision is not None and down_revision is not None
    return revision.group(1), down_revision.group(1)


async def _run_alembic(environment: dict[str, str], *arguments: str) -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "alembic", "-c", "database/alembic.ini", *arguments,
        cwd=REPOSITORY_ROOT, env=environment,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await asyncio.wait_for(process.communicate(), timeout=300)
    assert process.returncode == 0, output.decode("utf-8", errors="replace")


class _DisposableDatabase:
    """Create/drop one throwaway database, mirroring test_app_map_database."""

    def __init__(self) -> None:
        url = make_url(get_settings().database_url)
        assert url.host in {"localhost", "127.0.0.1", "::1"}
        self.host = url.host
        self.port = url.port or 5432
        self.username = url.username
        self.password = url.password
        self.name = "preflight_migration_" + uuid4().hex
        assert re.fullmatch(r"preflight_migration_[0-9a-f]{32}", self.name)
        assert self.name != url.database
        self.created = False

    def environment(self) -> dict[str, str]:
        return {
            **os.environ,
            "POSTGRES_HOST": self.host,
            "POSTGRES_PORT": str(self.port),
            "POSTGRES_DB": self.name,
            "POSTGRES_USER": self.username or "",
            "POSTGRES_PASSWORD": self.password or "",
        }

    async def create(self) -> None:
        connection = await asyncpg.connect(
            host=self.host, port=self.port, user=self.username,
            password=self.password,
        )
        try:
            await connection.execute(f'CREATE DATABASE "{self.name}"')
            self.created = True
        finally:
            await connection.close()

    async def drop(self) -> None:
        if not self.created:
            return
        assert re.fullmatch(r"preflight_migration_[0-9a-f]{32}", self.name)
        connection = await asyncpg.connect(
            host=self.host, port=self.port, user=self.username,
            password=self.password,
        )
        try:
            await connection.execute(f'DROP DATABASE "{self.name}" WITH (FORCE)')
        finally:
            await connection.close()

    async def connect(self) -> asyncpg.Connection:
        return await asyncpg.connect(
            host=self.host, port=self.port, user=self.username,
            password=self.password, database=self.name,
        )


async def _knowledge_tables(connection: asyncpg.Connection) -> set[str]:
    rows = await connection.fetch(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'knowledge'"
    )
    return {row["table_name"] for row in rows}


async def _columns(
    connection: asyncpg.Connection, table: str
) -> dict[str, str | None]:
    rows = await connection.fetch(
        "SELECT column_name, column_default FROM information_schema.columns "
        "WHERE table_schema = 'knowledge' AND table_name = $1",
        table,
    )
    return {row["column_name"]: row["column_default"] for row in rows}


@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_DATABASE") != "1", reason="Local DB opt-in"
)
async def test_freshness_migration_upgrade_creates_schema() -> None:
    revision, _down_revision = _freshness_revision()
    database = _DisposableDatabase()
    try:
        await database.create()
        await _run_alembic(database.environment(), "upgrade", revision)
        connection = await database.connect()
        try:
            assert EXPECTED_TABLES <= await _knowledge_tables(connection)
            map_columns = await _columns(connection, "app_maps")
            assert EXPECTED_MAP_COLUMNS <= set(map_columns)
            # A pre-existing row reads the server defaults: freshness
            # 'unknown', no preflight yet (proven on the dev stack's
            # real rows at build time; the default is what a
            # disposable database can pin).
            assert "unknown" in (map_columns["freshness_state"] or "")
            state_columns = await _columns(connection, "map_page_states")
            assert "screenshot_phash" in state_columns
            constraint_rows = await connection.fetch(
                "SELECT conname FROM pg_constraint "
                "WHERE connamespace = 'knowledge'::regnamespace"
            )
            assert "ck_app_maps_freshness_state_allowed" in {
                row["conname"] for row in constraint_rows
            }
            index_rows = await connection.fetch(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = 'knowledge'"
            )
            indexes = {row["indexname"]: row["indexdef"] for row in index_rows}
            single_flight = indexes["uq_map_preflights_single_flight"]
            assert "WHERE" in single_flight
            assert "building" in single_flight
        finally:
            await connection.close()
    finally:
        await database.drop()


@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_DATABASE") != "1", reason="Local DB opt-in"
)
async def test_freshness_migration_downgrade_removes_exactly_the_schema() -> None:
    revision, down_revision = _freshness_revision()
    database = _DisposableDatabase()
    try:
        await database.create()
        await _run_alembic(database.environment(), "upgrade", revision)
        await _run_alembic(database.environment(), "downgrade", down_revision)
        connection = await database.connect()
        try:
            tables = await _knowledge_tables(connection)
            assert not (EXPECTED_TABLES & tables)
            assert "app_maps" in tables
            map_columns = await _columns(connection, "app_maps")
            assert not (EXPECTED_MAP_COLUMNS & set(map_columns))
            state_columns = await _columns(connection, "map_page_states")
            assert "screenshot_phash" not in state_columns
        finally:
            await connection.close()
    finally:
        await database.drop()
