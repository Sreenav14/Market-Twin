from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from markettwin_execution_orchestrator.browser import AllowedOrigin
from markettwin_execution_orchestrator.workflow import app_plan, run_executor


MAP_BLOCK = {
    "map_id": "map-1",
    "version_number": 1,
    "routes": ["https://app.test/", "https://app.test/setup"],
    "pages": [],
    "counts": {},
}


def request(kind="slop", app_map=None):
    return run_executor.MarketTwinRunRequest(
        run_id=uuid4(), study_brief="Complete onboarding", target_snapshot={},
        start_url="https://app.test/", allowed_origins=(AllowedOrigin("https", "app.test", None),),
        run_kind=kind, unified_native=True,
        app_map=app_map,
    )


def test_explore_prioritizes_observed_controls_without_inventing_them():
    controls = [SimpleNamespace(name="Privacy", status="pending"),
                SimpleNamespace(name="Create workspace", status="pending")]
    state = SimpleNamespace(ordered_items=lambda: controls)
    planned = SimpleNamespace(app_plan={"checks": [{"expectation": "Create a workspace"}]})
    assert app_plan.next_planned_item(state, planned) is controls[1]
    controls[1].status = "worked"
    assert app_plan.next_planned_item(state, planned) is controls[0]


@pytest.mark.asyncio
async def test_plan_without_a_map_stays_discovery_only():
    """R0: document knowledge no longer seeds routes or checks — an
    unmapped run's plan is start-only discovery, and no route or
    expectation is invented from prose."""
    plan = await app_plan.build_app_plan(request())
    assert plan["routes"] == ["https://app.test/"]
    assert plan["status"] == "discovery_only"
    assert plan["checks"] == []
    assert plan["sources"] == []


@pytest.mark.asyncio
async def test_skill_planning_receives_persisted_run_mode(monkeypatch):
    capture = {}
    def plan_skills(app_map, *, mode, approved_keys):
        capture["mode"] = mode
        return {}
    monkeypatch.setattr(app_plan, "plan_skills_section", plan_skills)
    snapshot = {"harness_run_mode": "standard"}
    await app_plan.build_app_plan(
        request(app_map={**MAP_BLOCK, "skills": []}), configuration_snapshot=snapshot,
    )
    assert capture["mode"] == "standard"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,module,entry", [
    ("slop", "slop_run", "execute_slop_run"),
    ("persona", "persona_run", "execute_persona_run"),
    ("explore_test", "harness_run", "execute_harness_run"),
])
async def test_every_mode_receives_the_same_persisted_plan(monkeypatch, kind, module, entry):
    import importlib
    executor = AsyncMock()
    monkeypatch.setattr(importlib.import_module(
        "markettwin_execution_orchestrator.workflow." + module), entry, executor)
    create = AsyncMock()
    monkeypatch.setattr(app_plan, "RunEventRepository", lambda _: SimpleNamespace(create=create))
    run = SimpleNamespace(configuration_snapshot={})
    session = SimpleNamespace(get=AsyncMock(return_value=run), commit=AsyncMock())
    original = request(kind, app_map=dict(MAP_BLOCK))
    await run_executor._execute_markettwin_run(original, session=session)
    received = executor.call_args.kwargs["request"]
    assert received.app_plan == run.configuration_snapshot["app_plan"]
    assert "Application map (reference data" in received.study_brief
    assert app_plan.planned_routes(received)[1] == "https://app.test/setup"
    await run_executor._execute_markettwin_run(original, session=session)
    create.assert_awaited_once()  # Redelivery reuses the snapshot.
