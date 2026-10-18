"""A rolled-back HITL wait must not leave the run lifecycle identity expired."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from markettwin_control_api.config import get_settings
from markettwin_database.models import (
    AgentExecution,
    Application,
    ApplicationTarget,
    BrowserSession,
    HumanActionRequest,
    PersonaJourney,
    RunMission,
    RunPersona,
    User,
    Workspace,
)
from markettwin_database.models import TestRun as RunModel
from markettwin_execution_orchestrator.persistence.human_action_lifecycle_repository import (
    HumanActionLifecycleRepository,
)
from markettwin_execution_orchestrator.persistence.run_state_repository import RunStateRepository
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_SCOPE_TEST_DATABASE") != "1",
    reason="Requires a generated disposable local database migrated to head.",
)
async def test_run_can_complete_after_rolled_back_handoff_resumes() -> None:
    settings = get_settings()
    assert settings.postgres_host in {"127.0.0.1", "localhost", "::1"}
    assert settings.postgres_db.startswith("mt_scope_")
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id, workspace_id, app_id, target_id, run_id = (uuid4() for _ in range(5))
    persona_id, mission_id, journey_id, execution_id = (uuid4() for _ in range(4))
    browser_id, request_id = uuid4(), uuid4()
    try:
        async with factory.begin() as session:
            email = f"handoff-{user_id}@example.invalid"
            session.add(User(id=user_id, email=email, normalized_email=email))
            await session.flush()
            session.add(Workspace(
                id=workspace_id, name="Handoff fixture", created_by_user_id=user_id,
            ))
            await session.flush()
            session.add(Application(
                id=app_id, workspace_id=workspace_id, created_by_user_id=user_id,
                name="Synthetic handoff fixture",
            ))
            await session.flush()
            session.add(ApplicationTarget(
                id=target_id, application_id=app_id, name="Local fixture", environment="test",
                base_url="http://127.0.0.1:8765/", requires_auth=False,
            ))
            await session.flush()
            session.add(RunModel(
                id=run_id, workspace_id=workspace_id, application_id=app_id, target_id=target_id,
                created_by_user_id=user_id, status="awaiting_human", target_snapshot={},
                configuration_snapshot={}, started_at=datetime.now(UTC),
            ))
            await session.flush()
            session.add_all([
                RunPersona(id=persona_id, test_run_id=run_id, ordinal=1,
                           name="Synthetic user", description="Synthetic user"),
                RunMission(id=mission_id, test_run_id=run_id, ordinal=1,
                           title="Synthetic check", objective="Check fixture", priority="low"),
            ])
            await session.flush()
            session.add(PersonaJourney(
                id=journey_id, test_run_id=run_id, persona_id=persona_id,
                mission_id=mission_id, ordinal=1,
            ))
            await session.flush()
            session.add(AgentExecution(
                id=execution_id, journey_id=journey_id, attempt_number=1, status="skipped",
            ))
            await session.flush()
            session.add(BrowserSession(
                id=browser_id, execution_id=execution_id, state="open",
                control_mode="none", control_generation=1,
            ))
            await session.flush()
            session.add(HumanActionRequest(
                id=request_id, execution_id=execution_id, browser_session_id=browser_id,
                request_type="login", status="skipped", terminal_generation=1,
            ))
        async with factory() as session:
            run = await session.get(RunModel, run_id)
            assert run is not None and run.status == "awaiting_human"
            # verify_or_request_login performs rollback before acknowledging Skip.
            await session.rollback()
            assert "status" in inspect(run).expired_attributes
            await HumanActionLifecycleRepository(session).acknowledge_skipped(request_id=request_id)
            await session.commit()
            # A synchronized bulk UPDATE can leave an expired identity-map object.
            # The lifecycle boundary must refresh before reading its attributes.
            await RunStateRepository(session).mark_completed(test_run_id=run_id)
            await session.commit()
        async with factory() as session:
            assert await session.scalar(select(RunModel.status).where(
                RunModel.id == run_id,
            )) == "completed"
    finally:
        await engine.dispose()
