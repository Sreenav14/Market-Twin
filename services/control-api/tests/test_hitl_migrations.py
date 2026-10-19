"""Exercise the real additive migration chain in a disposable loopback database."""

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


@pytest.mark.skipif(os.environ.get("MARKETTWIN_TEST_DATABASE") != "1", reason="Local DB opt-in")
async def test_hitl_migration_upgrade_downgrade_and_model_readiness() -> None:
    url = make_url(get_settings().database_url)
    assert url.host in {"localhost", "127.0.0.1", "::1"}
    name = "hitl_migration_" + uuid4().hex
    assert re.fullmatch(r"hitl_migration_[0-9a-f]{32}", name) and name != url.database
    connection = await asyncpg.connect(
        host=url.host, port=url.port or 5432, user=url.username,
        password=url.password, database=url.database, timeout=5,
    )
    created = False
    try:
        await connection.execute(f'CREATE DATABASE "{name}"')
        created = True
        environment = {**os.environ, "POSTGRES_HOST": url.host,
                       "POSTGRES_PORT": str(url.port or 5432), "POSTGRES_DB": name,
                       "POSTGRES_USER": url.username or "", "POSTGRES_PASSWORD": url.password or ""}
        for arguments in (("upgrade", "head"), ("check",),
                          ("downgrade", "a1b2c3d4e5f6"), ("upgrade", "head"), ("check",)):
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "alembic", "-c", "database/alembic.ini", *arguments,
                cwd=REPOSITORY_ROOT, env=environment,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            output, _ = await asyncio.wait_for(process.communicate(), timeout=30)
            # DDL diagnostics contain only schema/operation names; no run/user data.
            assert process.returncode == 0, output.decode("utf-8", errors="replace")
    finally:
        if created:
            assert re.fullmatch(r"hitl_migration_[0-9a-f]{32}", name) and name != url.database
            await connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await connection.close()
