"""Opt-in persisted Board -> evaluator -> real results endpoint -> Chromium UI."""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from markettwin_control_api.api import test_run_results
from markettwin_database.models import (
    AgentExecution, Application, ApplicationTarget, PersonaJourney, Report,
    RunEvent, RunMission, RunPersona, TestRun, User, Workspace, WorkspaceMember,
)
from playwright.async_api import async_playwright
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from markettwin_evaluation_worker.workflow import _evaluate_and_generate_report
from markettwin_evaluation_worker.persistence.report_repository import ReportRepository


@pytest.mark.skipif(os.getenv("MARKETTWIN_SCOPE_TEST_DATABASE") != "1",
                    reason="Disposable migrated local database and local Vite required")
async def test_persisted_board_reaches_results_ui_without_legacy_findings(monkeypatch):
    from markettwin_control_api.config import get_settings

    settings = get_settings()
    assert settings.postgres_host == "127.0.0.1"
    assert settings.postgres_db.startswith("mt_scope_")
    engine = create_async_engine(settings.database_url)
    user, workspace, app_id, target, run_id, persona, mission, journey, execution = (
        uuid4() for _ in range(9)
    )
    items = {
        "checked": {"item_id": "checked", "name": "Read menu", "role": "button",
                    "status": "worked", "journey_id": str(journey)},
        "unchecked": {"item_id": "unchecked", "name": "Search", "role": "button",
                      "status": "could_not_check", "blocker": "outcome_not_established"},
        "disabled": {"item_id": "disabled", "name": "Delete", "role": "button",
                     "status": "owner_disabled"},
    }
    snapshot = {"harness_state": {"items": items}}
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            factory = async_sessionmaker(connection, expire_on_commit=False,
                                         join_transaction_mode="create_savepoint")
            try:
                async with factory() as session:
                    session.add(User(id=user, email=f"{user}@example.invalid",
                                     normalized_email=f"{user}@example.invalid"))
                    await session.flush()
                    session.add(Workspace(id=workspace, name="Board acceptance",
                                          created_by_user_id=user))
                    await session.flush()
                    session.add(WorkspaceMember(workspace_id=workspace, user_id=user, role="owner"))
                    session.add(Application(id=app_id, workspace_id=workspace,
                                            created_by_user_id=user, name="Synthetic Board"))
                    await session.flush()
                    session.add(ApplicationTarget(id=target, application_id=app_id,
                        name="Local fixture", environment="test", base_url="https://fixture.invalid/"))
                    await session.flush()
                    session.add(TestRun(id=run_id, workspace_id=workspace, application_id=app_id,
                        target_id=target, created_by_user_id=user, status="completed",
                        run_kind="explore_test", configuration_snapshot=snapshot))
                    await session.flush()
                    session.add(RunPersona(id=persona, test_run_id=run_id, ordinal=1,
                                          name="Fixture", description="Synthetic evidence"))
                    session.add(RunMission(id=mission, test_run_id=run_id, ordinal=1,
                                          title="Menu", objective="Read menu", priority="medium"))
                    await session.flush()
                    session.add(PersonaJourney(id=journey, test_run_id=run_id,
                                               persona_id=persona, mission_id=mission, ordinal=1))
                    await session.flush()
                    session.add(AgentExecution(id=execution, journey_id=journey,
                        attempt_number=1, runtime_name="synthetic", status="completed"))
                    await session.flush()
                    for key, item in items.items():
                        session.add(RunEvent(test_run_id=run_id, event_type="board.item.result",
                            journey_id=journey if key == "checked" else None,
                            execution_id=execution if key == "checked" else None,
                            payload={"board_item_id": key, "board_status": item["status"]}))
                    await session.commit()
                    original_create = ReportRepository.create_completed_report
                    async def fail_after_insert(repository, **kwargs):
                        await original_create(repository, **kwargs)
                        raise RuntimeError("Synthetic report publication failure")
                    with monkeypatch.context() as failure_patch:
                        failure_patch.setattr(ReportRepository, "create_completed_report", fail_after_insert)
                        with pytest.raises(RuntimeError, match="Synthetic report publication failure"):
                            await _evaluate_and_generate_report(test_run_id=run_id, session=session)
                    assert await session.scalar(select(func.count()).select_from(Report).where(
                        Report.test_run_id == run_id)) == 0
                    first = await _evaluate_and_generate_report(test_run_id=run_id, session=session)
                    second = await _evaluate_and_generate_report(test_run_id=run_id, session=session)
                    assert first.report_id == second.report_id
                    assert await session.scalar(select(func.count()).select_from(Report).where(
                        Report.test_run_id == run_id)) == 1
                monkeypatch.setattr(test_run_results, "get_authenticated_user_id",
                                    AsyncMock(return_value=user))
                monkeypatch.setattr(test_run_results, "get_database_runtime",
                                    lambda _: SimpleNamespace(session_factory=factory))
                api_app = FastAPI()
                api_app.include_router(test_run_results.router)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api_app),
                                             base_url="http://synthetic.local") as client:
                    result = await client.get(f"/api/v1/test-runs/{run_id}/results")
                    assert result.status_code == 200, result.text
                    data = result.json()
                    assert data["report"]["payload"]["verdict"] == "Ready"
                    assert data["report"]["payload"]["board"]["coverage"]["checked"] == 1
                    async with async_playwright() as playwright:
                        browser = await playwright.chromium.launch()
                        try:
                            page = await browser.new_page()
                            async def route_api(route):
                                path = route.request.url.split("/api/v1", 1)[1].split("?", 1)[0]
                                if path == f"/test-runs/{run_id}/results":
                                    response = await client.get("/api/v1" + path)
                                    return await route.fulfill(status=response.status_code,
                                        body=response.content, content_type="application/json")
                                body = {
                                    "/me": {"id": str(user), "email": "fixture@example.invalid"},
                                    "/workspaces": [{"id": str(workspace), "name": "Board acceptance", "role": "owner"}],
                                    f"/test-runs/{run_id}/flow": {"nodes": [], "edges": [],
                                        "revision": "synthetic", "execution_policy": "once_per_journey"},
                                    f"/test-runs/{run_id}": {"id": str(run_id), "workspace_id": str(workspace),
                                        "application_id": str(app_id), "target_id": str(target),
                                        "created_by_user_id": str(user), "status": "completed",
                                        "run_kind": "explore_test", "target_snapshot": {},
                                        "configuration_snapshot": snapshot},
                                }.get(path, [])
                                await route.fulfill(json=body)
                            await page.route("**/api/v1/**", route_api)
                            await page.goto(f"http://127.0.0.1:5173/runs/{run_id}/results")
                            try:
                                await page.get_by_role("heading", name="Ready", exact=True).wait_for()
                            except Exception:
                                Path(".local/audit-20261108/report-ui-diagnostic.txt").write_text(
                                    await page.locator("body").inner_text(), encoding="utf-8",
                                )
                                raise
                            assert await page.get_by_text("Checked 1 of 3 found.", exact=False).count() == 1
                            assert await page.get_by_text("Search", exact=True).count() == 1
                            assert await page.get_by_text("outcome not established", exact=False).count() == 1
                            assert await page.get_by_text("Data gap: no saved reason.", exact=False).count() == 1
                            link = page.get_by_role("link", name="Review recorded steps")
                            assert await link.get_attribute("href") == f"/runs/{run_id}/journeys/{journey}"
                        finally:
                            await browser.close()
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
