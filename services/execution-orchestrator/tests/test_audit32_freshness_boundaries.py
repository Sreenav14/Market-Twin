"""Production adapters use real browser, harvest and history contracts."""

import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_database.models.knowledge import MapFingerprintHistory
from markettwin_execution_orchestrator.freshness import freshness_job
from markettwin_execution_orchestrator.harvest import harvest_inventory


def test_production_evidence_store_uses_existing_adapters(monkeypatch):
    from markettwin_execution_orchestrator.harvest.harvest_capture import S3EvidenceStore
    from markettwin_execution_orchestrator.persistence.artifact_storage import S3ArtifactStorage

    storage = object()
    monkeypatch.setattr(S3ArtifactStorage, "from_environment", lambda: storage)
    store = freshness_job._evidence_store()
    assert isinstance(store, S3EvidenceStore)
    assert store._storage is storage


def test_real_stage_room_and_link_resolver():
    room = freshness_job._StageRoom(
        run_key=uuid4(), base_url="https://example.com/", page_budget_seconds=60,
        capture_network=False,
    )
    room.validate("https://example.com/agents")
    assert freshness_job._resolve_same_site(
        "https://example.com/docs/", "../agents", "https://example.com/",
    ) == "https://example.com/agents"
    assert freshness_job._resolve_same_site(
        "https://example.com/", "https://other.example/", "https://example.com/",
    ) is None


@pytest.mark.asyncio
async def test_real_visit_adapter_uses_monotonic_deadline_and_history_model(monkeypatch):
    successor = SimpleNamespace(id=uuid4(), workspace_id=uuid4(), application_id=uuid4(),
                                target_id=uuid4(), census_config={})
    page = SimpleNamespace(id=uuid4(), canonical_url="https://example.com/agents")
    state = SimpleNamespace(id=uuid4(), state_key="default", state_id="state",
                            dom_structure_hash="dom", aria_hash="aria",
                            screenshot_hash=None, screenshot_phash=None)
    repository = SimpleNamespace(get_page_by_url=AsyncMock(return_value=page),
                                 append_history=AsyncMock(), mark_reconciled_states=AsyncMock())
    harvest = SimpleNamespace(mark_page_harvest=AsyncMock(),
                              list_states=AsyncMock(return_value=[state]))
    room = SimpleNamespace(ensure=AsyncMock(return_value=object()), controller=object(),
                           execution_id=uuid4(), journey_id=uuid4(), network=None,
                           aria_excerpts={})
    async def visit_page(*, controller, handle, repository, store, app_map, page,
                         execution_id, journey_id, network, deadline):
        assert time.monotonic() < deadline <= time.monotonic() + 61
        return harvest_inventory.PageVisitResult(disposition="visited", aria_excerpt="Observed ARIA")
    monkeypatch.setattr(harvest_inventory, "visit_page", visit_page)
    monkeypatch.setattr(freshness_job, "_evidence_store", lambda: object())
    await freshness_job._visit_pages(
        harvest_repository=harvest, room=room, repository=repository, successor=successor,
        urls={page.canonical_url}, observed_at=datetime.now(UTC), mark_reconciled=True,
    )
    rows = repository.append_history.call_args.args[0]
    history = MapFingerprintHistory(id=uuid4(), **rows[0])
    assert history.map_page_state_id == state.id
    assert history.workspace_id == successor.workspace_id
    assert history.source == "reconcile"


@pytest.mark.asyncio
async def test_changed_intermediate_page_demotes_endpoint_fingerprint():
    base = SimpleNamespace(id=uuid4(), workspace_id=uuid4(), application_id=uuid4(), target_id=uuid4())
    pages = [SimpleNamespace(id=uuid4(), canonical_url=f"https://example.com/{name}")
             for name in ("start", "middle", "finish")]
    states = [SimpleNamespace(id=uuid4(), map_page_id=page.id, state_id=f"state-{index}")
              for index, page in enumerate(pages)]
    journey = SimpleNamespace(success_state_id=states[-1].id, steps=[
        {"map_page_state_id": str(state.id)} for state in states[:-1]
    ])
    version = SimpleNamespace(id=uuid4(), lifecycle_status="active",
                              verified_fingerprint={"start_state_id": "state-0", "terminal_state_id": "state-2"})
    fresh = SimpleNamespace(get_map=AsyncMock(return_value=base), list_pages=AsyncMock(return_value=pages),
                            list_states=AsyncMock(return_value=states), list_journeys=AsyncMock(return_value=[journey]))
    harvest = SimpleNamespace(list_skills_for_scope=AsyncMock(return_value=[SimpleNamespace(id=uuid4())]),
                              list_versions_for_skill=AsyncMock(return_value=[version]),
                              get_skill_version=AsyncMock(return_value=version), apply_skill_transition=AsyncMock())
    successor = SimpleNamespace(census_config={"base_map_id": str(base.id)})
    result = await freshness_job._demote_skills(
        freshness_repository=fresh, harvest_repository=harvest, successor=successor,
        delta={"changed": [{"url": pages[1].canonical_url}], "missing": []},
    )
    assert result == [str(version.id)]
    assert harvest.apply_skill_transition.call_args.kwargs["fields"]["lifecycle_status"] == "suspect"


@pytest.mark.asyncio
async def test_stage_room_ensure_installs_a_real_network_capture(monkeypatch):
    # ORC1-01 regression: ensure() must resolve its NetworkCapture
    # import and install a real capture on the session context. The
    # controller is the fake boundary; the import under test is NOT
    # mocked - before the fix this raised ModuleNotFoundError for
    # browser.network_capture, which does not exist.
    from markettwin_execution_orchestrator.browser import controller as controller_module
    from markettwin_execution_orchestrator.harvest.harvest_capture import (
        NetworkCapture,
    )

    registered = []

    class FakeContext:
        def on(self, event, handler):
            registered.append(event)

    session = SimpleNamespace(context=FakeContext())
    handle = SimpleNamespace(session_id=uuid4())

    class FakeController:
        async def open_room_session(self, **kwargs):
            return handle

        def _get_session(self, *, session_id):
            assert session_id == handle.session_id
            return session

    monkeypatch.setattr(controller_module, "BrowserController", FakeController)
    room = freshness_job._StageRoom(
        run_key=uuid4(), base_url="https://example.com/", page_budget_seconds=60,
        capture_network=True,
    )
    await room.ensure()
    assert isinstance(room.network, NetworkCapture)
    assert registered == ["request", "response", "requestfailed"]
