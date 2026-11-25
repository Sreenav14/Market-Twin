"""Exercise the Phase 1a app-map migration in a disposable loopback database.

Follows the opt-in convention of test_hitl_migrations.py (doc 14 section
13 item 16): these tests run only when MARKETTWIN_TEST_DATABASE=1 and
only against a throwaway database created per test. T-D1 checks the
upgrade creates the three tables with their named constraints and the
partial single-flight index; T-D2 checks the downgrade drops all three.
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

EXPECTED_TABLES = {"app_maps", "map_pages", "map_page_states"}
EXPECTED_CONSTRAINTS = {
    "ck_app_maps_release_state_allowed",
    "ck_app_maps_status_allowed",
    "ck_map_page_states_confidence_allowed",
    "ck_map_page_states_state_kind_allowed",
    "ck_map_pages_confidence_allowed",
    "ck_map_pages_crawl_status_allowed",
    "uq_app_maps_version",
    "uq_app_maps_workspace_id_id",
    "uq_map_page_states_key",
    "uq_map_pages_canonical",
    "uq_map_pages_workspace_id_id",
}
EXPECTED_INDEXES = {
    "ix_app_maps_poll",
    "ix_map_pages_pattern",
    "ix_map_pages_status",
    "uq_app_maps_single_flight",
}


def _app_map_revision() -> tuple[str, str]:
    matches = sorted(VERSIONS_DIR.glob("*_add_app_maps.py"))
    assert len(matches) == 1, matches
    source = matches[0].read_text(encoding="utf-8")
    revision = re.search(r'^revision(?::\s*str)?\s*=\s*"([^"]+)"', source, re.M)
    down_revision = re.search(r'^down_revision(?::[^=]+)?=\s*"([^"]+)"', source, re.M)
    assert revision is not None and down_revision is not None
    return revision.group(1), down_revision.group(1)


async def _run_alembic(environment: dict[str, str], *arguments: str) -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "alembic", "-c", "database/alembic.ini", *arguments,
        cwd=REPOSITORY_ROOT, env=environment,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await asyncio.wait_for(process.communicate(), timeout=60)
    assert process.returncode == 0, output.decode("utf-8", errors="replace")


class _DisposableDatabase:
    """Create/drop one throwaway database, mirroring test_hitl_migrations."""

    def __init__(self) -> None:
        url = make_url(get_settings().database_url)
        assert url.host in {"localhost", "127.0.0.1", "::1"}
        self.host = url.host
        self.port = url.port or 5432
        self.username = url.username
        self.password = url.password
        self.name = "app_map_migration_" + uuid4().hex
        assert re.fullmatch(r"app_map_migration_[0-9a-f]{32}", self.name)
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
            host=self.host, port=self.port, user=self.username, password=self.password
        )
        try:
            await connection.execute(f'CREATE DATABASE "{self.name}"')
            self.created = True
        finally:
            await connection.close()

    async def drop(self) -> None:
        if not self.created:
            return
        assert re.fullmatch(r"app_map_migration_[0-9a-f]{32}", self.name)
        connection = await asyncpg.connect(
            host=self.host, port=self.port, user=self.username, password=self.password
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


@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_DATABASE") != "1", reason="Local DB opt-in"
)
async def test_app_map_migration_upgrade_creates_tables_constraints_and_indexes() -> None:
    revision, _down_revision = _app_map_revision()
    database = _DisposableDatabase()
    try:
        await database.create()
        await _run_alembic(database.environment(), "upgrade", revision)
        connection = await database.connect()
        try:
            assert EXPECTED_TABLES <= await _knowledge_tables(connection)
            constraint_rows = await connection.fetch(
                "SELECT conname FROM pg_constraint "
                "WHERE connamespace = 'knowledge'::regnamespace"
            )
            assert EXPECTED_CONSTRAINTS <= {row["conname"] for row in constraint_rows}
            index_rows = await connection.fetch(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = 'knowledge'"
            )
            indexes = {row["indexname"]: row["indexdef"] for row in index_rows}
            assert EXPECTED_INDEXES <= set(indexes)
            single_flight = indexes["uq_app_maps_single_flight"]
            assert "WHERE" in single_flight and "building" in single_flight
        finally:
            await connection.close()
    finally:
        await database.drop()


@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_DATABASE") != "1", reason="Local DB opt-in"
)
async def test_app_map_migration_downgrade_drops_the_three_tables() -> None:
    revision, down_revision = _app_map_revision()
    database = _DisposableDatabase()
    try:
        await database.create()
        await _run_alembic(database.environment(), "upgrade", revision)
        connection = await database.connect()
        try:
            assert EXPECTED_TABLES <= await _knowledge_tables(connection)
        finally:
            await connection.close()
        await _run_alembic(database.environment(), "downgrade", down_revision)
        connection = await database.connect()
        try:
            assert EXPECTED_TABLES.isdisjoint(await _knowledge_tables(connection))
        finally:
            await connection.close()
    finally:
        await database.drop()
