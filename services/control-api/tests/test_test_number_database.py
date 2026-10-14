"""Opt-in local check of database-generated numbers under concurrent creation."""

import asyncio
import os

import pytest
from dotenv import load_dotenv
from markettwin_database import create_database_engine, create_session_factory
from markettwin_database.models import TestRun as RunModel
from sqlalchemy import select
from sqlalchemy.engine import URL


@pytest.mark.skipif(os.environ.get("MARKETTWIN_TEST_DATABASE") != "1",
                    reason="Opt-in local PostgreSQL check.")
async def test_concurrent_test_numbers_are_unique_and_backfilled():
    load_dotenv()
    assert os.environ["POSTGRES_HOST"] in {"localhost", "127.0.0.1", "::1"}
    url = URL.create("postgresql+asyncpg", username=os.environ["POSTGRES_USER"],
                     password=os.environ["POSTGRES_PASSWORD"], host=os.environ["POSTGRES_HOST"],
                     port=int(os.environ["POSTGRES_PORT"]), database=os.environ["POSTGRES_DB"])
    engine = create_database_engine(url.render_as_string(hide_password=False))
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            existing = (await session.scalars(select(RunModel))).all()
            if not existing:
                pytest.skip("Requires an existing local test target.")
            assert all(run.test_number > 0 for run in existing)
            assert len({run.test_number for run in existing}) == len(existing)
            sample = existing[0]

        async def allocate():
            async with factory() as session:
                run = RunModel(workspace_id=sample.workspace_id,
                               application_id=sample.application_id, target_id=sample.target_id,
                               created_by_user_id=sample.created_by_user_id, status="draft",
                               target_snapshot={}, configuration_snapshot={"test_name": "Probe"})
                session.add(run)
                await session.flush()
                number = run.test_number
                await session.rollback()
                return number

        first, second = await asyncio.gather(allocate(), allocate())
        assert first != second
        assert min(first, second) > max(run.test_number for run in existing)
    finally:
        await engine.dispose()
