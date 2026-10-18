"""Actual local PostgreSQL and Chromium cooperative pause/control boundaries."""

import asyncio
import os
import threading
from datetime import UTC, datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from markettwin_control_api.config import get_settings
from markettwin_control_api.persistence.repositories.execution_pause_repository import (
    ExecutionPauseRepository,
    PauseRejected,
)
from markettwin_control_api.persistence.repositories.human_action_repository import (
    HumanActionRepository,
)
from markettwin_database.models import (
    AgentExecution,
    Application,
    ApplicationTarget,
    BrowserSession,
    ExecutionPauseRequest,
    ExecutionStep,
    HumanActionRequest,
    PersonaJourney,
    RunMission,
    RunPersona,
    TargetAllowedOrigin,
    TargetAuthorization,
    User,
    Workspace,
    WorkspaceMember,
)
from markettwin_database.models import TestRun as RunModel
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.errors import (
    BrowserPolicyError,
    HumanAssistanceSkipped,
)
from markettwin_execution_orchestrator.browser.owner import OwnerLease, ViewerInput
from markettwin_execution_orchestrator.browser.owner_registry import browser_owner_registry
from markettwin_execution_orchestrator.browser.viewer_authority import DatabaseViewerAuthority
from markettwin_execution_orchestrator.workflow.cooperative_pause import (
    cooperative_pause_checkpoint,
    finalize_browser_pauses,
)
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


async def seed(factory, port):
    owner, workspace, app, target, run, persona, mission, journey, execution = (
        uuid4() for _ in range(9)
    )
    origin = {"scheme": "http", "hostname": "127.0.0.1", "port": port, "include_subdomains": False}
    async with factory.begin() as session:
        email = f"pause-{owner}@example.invalid"
        session.add(User(id=owner, email=email, normalized_email=email))
        await session.flush()
        session.add(Workspace(id=workspace, name="Pause fixture", created_by_user_id=owner))
        await session.flush()
        session.add_all(
            [
                WorkspaceMember(workspace_id=workspace, user_id=owner, role="owner"),
                Application(id=app, workspace_id=workspace, created_by_user_id=owner, name="Pause"),
            ]
        )
        await session.flush()
        session.add(
            ApplicationTarget(
                id=target,
                application_id=app,
                name="Local",
                environment="test",
                base_url=f"http://127.0.0.1:{port}/",
            )
        )
        await session.flush()
        session.add_all(
            [
                TargetAllowedOrigin(target_id=target, **origin),
                TargetAuthorization(
                    target_id=target,
                    created_by_user_id=owner,
                    authorized_by_user_id=owner,
                    status="authorized",
                    authorization_basis="Owned synthetic local fixture.",
                ),
                RunModel(
                    id=run,
                    workspace_id=workspace,
                    application_id=app,
                    target_id=target,
                    created_by_user_id=owner,
                    status="running",
                    target_snapshot={"target_id": str(target), "allowed_origins": [origin]},
                    configuration_snapshot={},
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                RunPersona(
                    id=persona, test_run_id=run, ordinal=1, name="Fixture", description="Fixture"
                ),
                RunMission(
                    id=mission,
                    test_run_id=run,
                    ordinal=1,
                    title="Check",
                    objective="Check",
                    priority="low",
                ),
            ]
        )
        await session.flush()
        session.add(
            PersonaJourney(
                id=journey, test_run_id=run, persona_id=persona, mission_id=mission, ordinal=1
            )
        )
        await session.flush()
        session.add(
            AgentExecution(id=execution, journey_id=journey, attempt_number=1, status="running")
        )
    return SimpleNamespace(
        test_run_id=run, execution_id=execution, journey_id=journey, owner=owner, target=target
    )


@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_SCOPE_TEST_DATABASE") != "1",
    reason="Requires explicitly generated migrated disposable local PostgreSQL.",
)
async def test_pause_plain_resume_takeover_skip_cancel_expiry_and_reserved_action(tmp_path):
    settings = get_settings()
    assert settings.postgres_host in {"127.0.0.1", "localhost", "::1"}
    assert settings.postgres_db.startswith("mt_scope_")
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    directory = Path(__file__).parent / "fixtures/hitl_app"
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(directory)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        async with BrowserController(artifact_root=tmp_path) as controller:
            for scenario in (
                "plain",
                "human",
                "skip",
                "cancel",
                "expiry",
                "busy",
                "revoked",
                "other_operator",
                "close",
                "initial_expiry",
                "scope_revoked",
            ):
                request = await seed(factory, server.server_port)
                handle = await controller.create_session(
                    execution_id=request.execution_id,
                    journey_id=request.journey_id,
                    allowed_origins=(AllowedOrigin("http", "127.0.0.1", server.server_port),),
                    network_policy="local_development",
                    authenticated_session=True,
                )
                await controller.navigate(
                    session_id=handle.session_id,
                    url=f"http://127.0.0.1:{server.server_port}/index.html",
                )
                async with factory.begin() as session:
                    session.add(
                        BrowserSession(
                            id=handle.session_id,
                            execution_id=handle.execution_id,
                            state="open",
                            control_mode="agent",
                            control_generation=0,
                        )
                    )
                async with factory.begin() as session:
                    pause = await ExecutionPauseRepository(session).request(
                        run_id=request.test_run_id,
                        actor_id=request.owner,
                        browser_session_id=handle.session_id,
                        generation=0,
                    )
                    pause_id = pause.id
                if scenario in {"close", "initial_expiry"}:
                    if scenario == "initial_expiry":
                        async with factory.begin() as session:
                            await session.execute(
                                update(ExecutionPauseRequest)
                                .where(
                                    ExecutionPauseRequest.id == pause_id,
                                )
                                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
                            )
                        async with factory() as session:
                            await cooperative_pause_checkpoint(
                                request=request,
                                controller=controller,
                                handle=handle,
                                session=session,
                            )
                    await controller.close_session(session_id=handle.session_id)
                    async with factory.begin() as session:
                        await finalize_browser_pauses(session, handle)
                    async with factory() as session:
                        final = await session.get(ExecutionPauseRequest, pause_id)
                        assert final.status == (
                            "expired" if scenario == "initial_expiry" else "unavailable"
                        )
                    continue
                async with factory() as worker_session:
                    if scenario == "busy":
                        async with factory.begin() as session:
                            session.add(
                                ExecutionStep(
                                    execution_id=request.execution_id,
                                    step_number=1,
                                    action_type="click",
                                    action_summary="Reserved action",
                                    status="running",
                                )
                            )
                        await cooperative_pause_checkpoint(
                            request=request,
                            controller=controller,
                            handle=handle,
                            session=worker_session,
                        )
                        async with factory.begin() as session:
                            waiting = await session.get(ExecutionPauseRequest, pause_id)
                            assert (
                                waiting.status == "requested" and waiting.human_request_id is None
                            )
                            await session.execute(
                                update(ExecutionStep)
                                .where(
                                    ExecutionStep.execution_id == request.execution_id,
                                )
                                .values(status="completed")
                            )
                    if scenario in {"revoked", "scope_revoked"}:
                        async with factory.begin() as session:
                            if scenario == "revoked":
                                await session.execute(
                                    update(User)
                                    .where(User.id == request.owner)
                                    .values(status="disabled")
                                )
                            else:
                                await session.execute(
                                    delete(TargetAllowedOrigin).where(
                                        TargetAllowedOrigin.target_id == request.target,
                                    )
                                )
                        with pytest.raises(BrowserPolicyError):
                            await cooperative_pause_checkpoint(
                                request=request,
                                controller=controller,
                                handle=handle,
                                session=worker_session,
                            )
                        await controller.close_session(session_id=handle.session_id)
                        continue

                    async def checkpoint(
                        request=request, handle=handle, worker_session=worker_session,
                    ):
                        await cooperative_pause_checkpoint(
                            request=request,
                            controller=controller,
                            handle=handle,
                            session=worker_session,
                        )

                    controller.bind_cooperative_pause_handler(handle, checkpoint)
                    task = asyncio.create_task(controller.get_state(session_id=handle.session_id))
                    try:
                        async with asyncio.timeout(5):
                            while True:
                                async with factory() as session:
                                    paused = await session.get(ExecutionPauseRequest, pause_id)
                                    if paused.status == "paused":
                                        human_id = paused.human_request_id
                                        break
                                await asyncio.sleep(0.02)
                        assert not task.done()
                        # Browser lock is free throughout the acknowledged wait.
                        assert await controller.cooperative_pause_ready(handle)
                        if scenario == "other_operator":
                            new_owner = uuid4()
                            async with factory.begin() as session:
                                run = await session.get(RunModel, request.test_run_id)
                                email = f"resume-{new_owner}@example.invalid"
                                session.add(User(id=new_owner, email=email, normalized_email=email))
                                await session.flush()
                                session.add(
                                    WorkspaceMember(
                                        workspace_id=run.workspace_id,
                                        user_id=new_owner,
                                        role="admin",
                                    )
                                )
                                await session.execute(
                                    update(User)
                                    .where(User.id == request.owner)
                                    .values(status="disabled")
                                )
                            async with factory.begin() as session:
                                await ExecutionPauseRepository(session).resume(
                                    run_id=request.test_run_id,
                                    pause_id=pause_id,
                                    actor_id=new_owner,
                                )
                        elif scenario in {"plain", "busy"}:
                            async with factory.begin() as session:
                                await ExecutionPauseRepository(session).resume(
                                    run_id=request.test_run_id,
                                    pause_id=pause_id,
                                    actor_id=request.owner,
                                )
                        elif scenario == "human":
                            async with factory.begin() as session:
                                grant = await HumanActionRepository(session).claim(
                                    request_id=human_id, actor_id=request.owner
                                )
                            lease = OwnerLease(
                                handle,
                                request.owner,
                                grant.lease_id,
                                grant.generation,
                                grant.expires_at,
                                human_id,
                            )
                            await browser_owner_registry.begin_human_control(
                                handle, generation=grant.generation
                            )
                            authority = DatabaseViewerAuthority(factory, browser_owner_registry)
                            assert await authority.activate_human(lease)
                            await browser_owner_registry.attach(lease)
                            await browser_owner_registry.input(
                                lease,
                                ViewerInput(sequence=1, event="resize", width=900, height=700),
                            )
                            async with factory.begin() as session:
                                with pytest.raises(PauseRejected):
                                    await ExecutionPauseRepository(session).resume(
                                        run_id=request.test_run_id,
                                        pause_id=pause_id,
                                        actor_id=request.owner,
                                    )
                            async with factory.begin() as session:
                                generation = await HumanActionRepository(
                                    session
                                ).release_for_verification(
                                    lease_id=grant.lease_id,
                                    actor_id=request.owner,
                                    lease_token=grant.lease_token,
                                    generation=grant.generation,
                                    expected_request_id=human_id,
                                )
                            await browser_owner_registry.revoke(handle, generation)
                        elif scenario == "skip":
                            async with factory.begin() as session:
                                await HumanActionRepository(session).skip(
                                    request_id=human_id, actor_id=request.owner
                                )
                        elif scenario == "cancel":
                            task.cancel()
                        else:
                            async with factory.begin() as session:
                                await session.execute(
                                    update(ExecutionPauseRequest)
                                    .where(
                                        ExecutionPauseRequest.id == pause_id,
                                    )
                                    .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
                                )
                        expected_error = {
                            "skip": HumanAssistanceSkipped,
                            "cancel": asyncio.CancelledError,
                            "expiry": BrowserPolicyError,
                        }.get(scenario)
                        if expected_error:
                            with pytest.raises(expected_error):
                                await asyncio.wait_for(task, 5)
                        else:
                            await asyncio.wait_for(task, 5)
                        async with factory() as session:
                            final = await session.get(ExecutionPauseRequest, pause_id)
                            assert final.status == {
                                "skip": "skipped",
                                "cancel": "cancelled",
                                "expiry": "expired",
                            }.get(scenario, "resumed")
                            if scenario in {"plain", "busy", "human", "other_operator"}:
                                human = await session.get(HumanActionRequest, human_id)
                                assert human.status == "completed"
                    finally:
                        if not task.done():
                            task.cancel()
                            await asyncio.gather(task, return_exceptions=True)
                await controller.close_session(session_id=handle.session_id)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        await engine.dispose()
