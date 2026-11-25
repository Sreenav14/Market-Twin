"""Exercise the D-LIVE-1 worker-role migration in a disposable loopback
database.

Follows the opt-in convention of test_preflight_migration.py: these
tests run only when MARKETTWIN_TEST_DATABASE=1 and only against a
throwaway database created per test. The pair checks the upgrade widens
ck_browser_sessions_session_role_allowed to include 'worker' (the role
whose INSERT killed MT-000153 live) and that the downgrade restores
exactly the P2-era set.
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

WIDENED_ROLES = {"room", "proof", "persona", "legacy", "worker"}
ORIGINAL_ROLES = {"room", "proof", "persona", "legacy"}


def _worker_role_revision() -> tuple[str, str]:
    matches = sorted(VERSIONS_DIR.glob("*_allow_worker_browser_session_role.py"))
    assert len(matches) == 1, matches
    source = matches[0].read_text(encoding="utf-8")
    revision = re.search(r'^revision(?::\s*str)?\s*=\s*"([^"]+)"', source, re.M)
    down_revision = re.search(
        r'^down_revision(?::[^=]+)?\s*=\s*"([^"]+)"', source, re.M
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
    """Create/drop one throwaway database, mirroring test_preflight_migration."""

    def __init__(self) -> None:
        url = make_url(get_settings().database_url)
        assert url.host in {"localhost", "127.0.0.1", "::1"}
        self.host = url.host
        self.port = url.port or 5432
        self.username = url.username
        self.password = url.password
        self.name = "worker_role_migration_" + uuid4().hex
        assert re.fullmatch(r"worker_role_migration_[0-9a-f]{32}", self.name)
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
        assert re.fullmatch(r"worker_role_migration_[0-9a-f]{32}", self.name)
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


async def _allowed_roles(connection: asyncpg.Connection) -> set[str]:
    definition = await connection.fetchval(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'ck_browser_sessions_session_role_allowed'"
    )
    assert definition is not None
    return set(re.findall(r"'([a-z_]+)'", definition))


@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_DATABASE") != "1", reason="Local DB opt-in"
)
async def test_worker_role_migration_upgrade_widens_the_role_set() -> None:
    revision, _down_revision = _worker_role_revision()
    database = _DisposableDatabase()
    try:
        await database.create()
        await _run_alembic(database.environment(), "upgrade", revision)
        connection = await database.connect()
        try:
            assert await _allowed_roles(connection) == WIDENED_ROLES
        finally:
            await connection.close()
    finally:
        await database.drop()


@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_DATABASE") != "1", reason="Local DB opt-in"
)
async def test_worker_role_migration_downgrade_restores_the_role_set() -> None:
    revision, down_revision = _worker_role_revision()
    database = _DisposableDatabase()
    try:
        await database.create()
        await _run_alembic(database.environment(), "upgrade", revision)
        await _run_alembic(database.environment(), "downgrade", down_revision)
        connection = await database.connect()
        try:
            assert await _allowed_roles(connection) == ORIGINAL_ROLES
        finally:
            await connection.close()
    finally:
        await database.drop()


def _execution_unique_revision() -> tuple[str, str]:
    matches = sorted(
        VERSIONS_DIR.glob("*_drop_browser_session_execution_unique.py")
    )
    assert len(matches) == 1, matches
    source = matches[0].read_text(encoding="utf-8")
    revision = re.search(r'^revision(?::\s*str)?\s*=\s*"([^"]+)"', source, re.M)
    down_revision = re.search(
        r'^down_revision(?::[^=]+)?\s*=\s*"([^"]+)"', source, re.M
    )
    assert revision is not None and down_revision is not None
    return revision.group(1), down_revision.group(1)


async def _execution_unique_exists(connection: asyncpg.Connection) -> bool:
    return await connection.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_constraint "
        "WHERE conname = 'uq_browser_sessions_execution_id')"
    )


@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_DATABASE") != "1", reason="Local DB opt-in"
)
async def test_execution_unique_migration_drops_and_restores() -> None:
    revision, down_revision = _execution_unique_revision()
    database = _DisposableDatabase()
    try:
        await database.create()
        await _run_alembic(database.environment(), "upgrade", revision)
        connection = await database.connect()
        try:
            assert await _execution_unique_exists(connection) is False
        finally:
            await connection.close()
        await _run_alembic(database.environment(), "downgrade", down_revision)
        connection = await database.connect()
        try:
            assert await _execution_unique_exists(connection) is True
        finally:
            await connection.close()
    finally:
        await database.drop()
