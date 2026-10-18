"""Real migrated PostgreSQL live read-model checks; disposable local database only."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from markettwin_control_api.config import get_settings
from markettwin_control_api.persistence.repositories.execution_pause_repository import (
    ExecutionPauseRepository,
    PauseRejected,
)
from markettwin_control_api.persistence.repositories.human_action_repository import (
    HumanActionConflictError,
    HumanActionRepository,
)
from markettwin_control_api.persistence.repositories.live_browser_repository import (
    LiveBrowserRepository,
)
from markettwin_database.models import (
    ActionApprovalRequest,
    AgentExecution,
    Application,
    ApplicationTarget,
    BrowserSession,
    ExecutionStep,
    HumanActionRequest,
    HumanControlLease,
    PersonaJourney,
    Report,
    RunEvent,
    RunMission,
    RunPersona,
    TargetAllowedOrigin,
    TargetAuthorization,
    User,
    Workspace,
    WorkspaceMember,
)
from markettwin_database.models import TestRun as RunModel
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.skipif(os.environ.get("MARKETTWIN_SCOPE_TEST_DATABASE") != "1",
                    reason="Requires generated disposable local database migrated to head.")
@pytest.mark.parametrize("port", [None, 443, 8765])
async def test_live_browser_real_tenant_scope_activity_and_lifecycle(port):
    settings = get_settings()
    assert settings.postgres_host in {"127.0.0.1", "localhost", "::1"}
    assert settings.postgres_db.startswith("mt_scope_")
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner, admin, member, outsider, workspace_id, app_id, target_id, run_id = (
        uuid4() for _ in range(8)
    )
    persona_id, mission_id, journey_id, execution_id, browser_id = (uuid4() for _ in range(5))
    origin = {"scheme": "https", "hostname": "synthetic.example.invalid", "port": port,
              "include_subdomains": False}
    try:
        async with factory.begin() as session:
            for actor in (owner, admin, member, outsider):
                email = f"observer-{actor}@example.invalid"
                session.add(User(id=actor, email=email, normalized_email=email))
            await session.flush()
            session.add(Workspace(id=workspace_id, name="Synthetic", created_by_user_id=owner))
            await session.flush()
            session.add_all([
                WorkspaceMember(workspace_id=workspace_id, user_id=actor, role=role)
                for actor, role in ((owner, "owner"), (admin, "admin"), (member, "member"))
            ])
            session.add(Application(id=app_id, workspace_id=workspace_id,
                                    created_by_user_id=owner, name="Synthetic"))
            await session.flush()
            session.add(ApplicationTarget(id=target_id, application_id=app_id, name="Synthetic",
                environment="test", base_url="https://synthetic.example.invalid/"))
            await session.flush()
            session.add_all([
                TargetAllowedOrigin(target_id=target_id, **origin),
                TargetAuthorization(target_id=target_id, created_by_user_id=owner,
                    authorized_by_user_id=owner, status="authorized",
                    authorization_basis="Owned synthetic database fixture."),
                RunModel(id=run_id, workspace_id=workspace_id, application_id=app_id,
                    target_id=target_id, created_by_user_id=owner, status="running",
                    target_snapshot={"target_id": str(target_id), "allowed_origins": [origin]},
                    configuration_snapshot={}),
            ])
            await session.flush()
            session.add_all([
                RunPersona(id=persona_id, test_run_id=run_id, ordinal=1, name="Synthetic tester",
                           description="Synthetic"),
                RunMission(id=mission_id, test_run_id=run_id, ordinal=1, title="Synthetic journey",
                           objective="Synthetic", priority="low"),
            ])
            await session.flush()
            session.add(PersonaJourney(id=journey_id, test_run_id=run_id, persona_id=persona_id,
                                      mission_id=mission_id, ordinal=1))
            await session.flush()
            session.add(AgentExecution(id=execution_id, journey_id=journey_id, attempt_number=1,
                                      runtime_name="deterministic_case_steps_v1", status="running"))
            await session.flush()
            session.add(BrowserSession(id=browser_id, execution_id=execution_id, state="open",
                                       control_mode="agent", control_generation=0))
            step = ExecutionStep(execution_id=execution_id, step_number=1, action_type="fill",
                                 action_summary="PASSWORD_CANARY", status="running")
            session.add(step)
            await session.flush()
            session.add_all([
                RunEvent(test_run_id=run_id, journey_id=journey_id, execution_id=execution_id,
                         event_type="test_plan.created", payload={"secret": "TOKEN_CANARY"}),
                HumanActionRequest(execution_id=execution_id, browser_session_id=browser_id,
                                   request_type="login", status="completed"),
                ActionApprovalRequest(test_run_id=run_id, execution_id=execution_id,
                    browser_session_id=browser_id, step_id=step.id, requested_by_user_id=owner,
                    action_fingerprint="a" * 64, resource_fingerprint="b" * 64, environment="test",
                    policy_version=1, action_summary="PRIVATE_CANARY", status="rejected",
                    expires_at=datetime.now(UTC) + timedelta(minutes=1)),
                Report(test_run_id=run_id, version=1, status="generating"),
            ])
        async with factory() as session:
            repository = LiveBrowserRepository(session)
            for actor in (owner, admin):
                assert await repository.authorized_run(run_id=run_id, actor_id=actor) is not None
            for actor in (member, outsider):
                assert await repository.authorized_run(run_id=run_id, actor_id=actor) is None
            run = await repository.authorized_run(run_id=run_id, actor_id=owner)
            browser = await repository.selected_browser(run=run, browser_session_id=None)
            assert browser["browser_session_id"] == browser_id
            assert browser["generation"] == 0 and browser["viewer_state"] == "available"
            assert await repository.selected_browser(run=run, browser_session_id=uuid4()) is None
            page = await repository.activity(run_id=run_id, cursor=None, limit=2)
            next_page = await repository.activity(
                run_id=run_id, cursor=page["next_cursor"], limit=50,
            )
            items = page["items"] + next_page["items"]
            assert len(items) == len({item["id"] for item in items}) == 5
            assert {item["source"] for item in items} == {
                "deterministic_case", "planner", "human_assistance", "approval", "report",
            }
            assert "CANARY" not in str(items)
        # A lower identity allocated by an earlier transaction commits after a
        # newer row. Latest-window refresh must not use an after-ID watermark.
        async with factory() as pending:
            late = ExecutionStep(execution_id=execution_id, step_number=2,
                                 action_type="click", action_summary="CANARY", status="running")
            pending.add(late)
            await pending.flush()
            async with factory.begin() as newer:
                committed = ExecutionStep(execution_id=execution_id, step_number=3,
                    action_type="wait", action_summary="CANARY", status="completed")
                newer.add(committed)
                await newer.flush()
                newer_id = committed.id
            async with factory() as reader:
                before = await LiveBrowserRepository(reader).activity(
                    run_id=run_id, cursor=None, limit=50,
                )
                assert f"step:{late.id}" not in {item["id"] for item in before["items"]}
                assert f"step:{newer_id}" in {item["id"] for item in before["items"]}
            await pending.commit()
            async with factory() as reader:
                after = await LiveBrowserRepository(reader).activity(
                    run_id=run_id, cursor=None, limit=50,
                )
                assert f"step:{late.id}" in {item["id"] for item in after["items"]}
        async with factory.begin() as session:
            pause = await ExecutionPauseRepository(session).request(
                run_id=run_id, actor_id=owner, browser_session_id=browser_id, generation=0,
            )
            pause_id, original_expiry = pause.id, pause.expires_at
            assert pause.status == "requested" and pause.human_request_id is None
        async with factory.begin() as session:
            same = await ExecutionPauseRepository(session).request(
                run_id=run_id, actor_id=admin, browser_session_id=browser_id, generation=0,
            )
            assert same.id == pause_id and same.expires_at == original_expiry
        rejected_requests = ((member, 0, 404), (outsider, 0, 404), (owner, 1, 409))
        for actor, generation, error_status in rejected_requests:
            async with factory() as session:
                with pytest.raises(PauseRejected) as error:
                    await ExecutionPauseRepository(session).request(
                        run_id=run_id, actor_id=actor, browser_session_id=browser_id,
                        generation=generation,
                    )
                assert error.value.status_code == error_status
        # API request does not acknowledge. Simulate only the durable worker ACK
        # here; the full worker/browser boundary is tested independently.
        from markettwin_database.models import ExecutionPauseRequest

        human_id = uuid4()
        async with factory.begin() as session:
            session.add(HumanActionRequest(id=human_id, execution_id=execution_id,
                browser_session_id=browser_id, request_type="other", status="pending"))
            await session.flush()
            await session.execute(update(ExecutionPauseRequest).where(
                ExecutionPauseRequest.id == pause_id,
            ).values(status="paused", human_request_id=human_id, acknowledged_at=datetime.now(UTC)))
            await session.execute(update(BrowserSession).where(BrowserSession.id == browser_id)
                                  .values(control_mode="human_pending"))
            await session.execute(update(RunModel).where(RunModel.id == run_id)
                                  .values(status="awaiting_human"))
        async with factory.begin() as session:
            duplicate = await ExecutionPauseRepository(session).request(
                run_id=run_id, actor_id=owner, browser_session_id=browser_id, generation=0,
            )
            assert duplicate.id == pause_id and duplicate.expires_at == original_expiry
            resumed = await ExecutionPauseRepository(session).resume(
                run_id=run_id, actor_id=owner, pause_id=pause_id,
            )
            assert resumed.status == "resume_requested" and resumed.completed_at is None
            assert resumed.resume_requested_by_user_id == owner
            activity = await LiveBrowserRepository(session).activity(
                run_id=run_id, cursor=None, limit=50,
            )
            recorded_pause = next(item for item in activity["items"]
                                  if item["id"] == f"pause:{pause_id}")
            assert recorded_pause["status"] == "resume_requested"
            assert recorded_pause["title"] == "Operator pause request."
        # Plain Resume wins the browser lock before a later claim. The existing
        # takeover path must not grant a competing lease during that transition.
        async with factory() as session:
            with pytest.raises(HumanActionConflictError, match="already resuming"):
                await HumanActionRepository(session).claim(request_id=human_id, actor_id=owner)
        lease_id = uuid4()
        async with factory.begin() as session:
            session.add(HumanControlLease(id=lease_id, request_id=human_id,
                browser_session_id=browser_id, user_id=owner, lease_token_hash=uuid4().hex * 2,
                generation=0, expires_at=datetime.now(UTC) + timedelta(seconds=30)))
        async with factory() as session:
            with pytest.raises(PauseRejected) as error:
                await ExecutionPauseRepository(session).resume(
                    run_id=run_id, actor_id=owner, pause_id=pause_id,
                )
            assert error.value.status_code == 409
        async with factory.begin() as session:
            await session.execute(update(HumanControlLease).where(HumanControlLease.id == lease_id)
                                  .values(released_at=datetime.now(UTC)))
            await session.execute(update(ExecutionPauseRequest).where(
                ExecutionPauseRequest.id == pause_id,
            ).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        async with factory() as session:
            with pytest.raises(PauseRejected) as error:
                await ExecutionPauseRepository(session).resume(
                    run_id=run_id, actor_id=owner, pause_id=pause_id,
                )
            assert error.value.status_code == 410
        async with factory.begin() as session:
            await session.execute(update(ExecutionPauseRequest).where(
                ExecutionPauseRequest.id == pause_id,
            ).values(status="expired"))
            await session.execute(update(RunModel).where(RunModel.id == run_id)
                                  .values(status="running"))
        for values, expected in (({"control_mode": "human"}, "suppressed"),
                                 ({"control_mode": "verifying"}, "suppressed"),
                                 ({"control_mode": "agent"}, "available")):
            async with factory.begin() as session:
                await session.execute(update(BrowserSession).where(BrowserSession.id == browser_id)
                                      .values(**values))
            async with factory() as session:
                repository = LiveBrowserRepository(session)
                run = await repository.authorized_run(run_id=run_id, actor_id=owner)
                assert (await repository.selected_browser(run=run,
                        browser_session_id=browser_id))["viewer_state"] == expected
        async with factory.begin() as session:
            await session.execute(update(RunModel).where(RunModel.id == run_id).values(
                target_snapshot={"target_id": str(target_id), "allowed_origins": [
                    {**origin, "hostname": "unapproved.example.invalid"},
                ]},
            ))
        async with factory() as session:
            assert await LiveBrowserRepository(session).authorized_run(
                run_id=run_id, actor_id=owner,
            ) is None
        async with factory.begin() as session:
            await session.execute(update(RunModel).where(RunModel.id == run_id).values(
                target_snapshot={"target_id": str(target_id), "allowed_origins": [origin]},
            ))
            await session.execute(update(TargetAuthorization).where(
                TargetAuthorization.target_id == target_id,
            ).values(status="revoked", revoked_at=datetime.now(UTC)))
        async with factory() as session:
            assert await LiveBrowserRepository(session).authorized_run(
                run_id=run_id, actor_id=owner,
            ) is None
    finally:
        await engine.dispose()
