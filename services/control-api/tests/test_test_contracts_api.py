"""Tests for TestContract API endpoints (review, edit, approve, start)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from markettwin_control_api.api import test_contracts
from markettwin_control_api.api.test_contracts import UpdateJourneyRequest
from markettwin_control_api.persistence.repositories import (
    TestRunRecord as RunRecord,
)
from markettwin_control_api.persistence.repositories import (
    WorkspaceAccess,
)
from markettwin_shared.discovery_contract import (
    DiscoveredFeature,
    DiscoveredJourney,
    DiscoveredStep,
    DiscoveryMap,
)


class AsyncContext:
    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


def _make_sample_discovery_map(journey_count: int = 1) -> dict[str, Any]:
    journeys = []
    features = []
    for index in range(journey_count):
        key = "journey_explore" if index == 0 else f"journey_explore_{index}"
        feature_key = "explore" if index == 0 else f"explore_{index}"
        step = DiscoveredStep(
            ordinal=1,
            action="click",
            target_role="button",
            target_name="Explore",
            resulting_url_path="/explore",
            resulting_page_title="Explore Page",
            observed_text_markers=("Explore Header",),
            execution_step_id=index + 1,
            name_source="playwright",
        )
        journeys.append(DiscoveredJourney(
            journey_key=key,
            title=f"Explore Journey {index + 1}",
            feature_key=feature_key,
            completed=True,
            steps=(step,),
        ))
        features.append(DiscoveredFeature(
            feature_key=feature_key,
            title=f"Explore {index + 1}",
            entry_url_path="/explore",
            journey_keys=(key,),
        ))
    return DiscoveryMap(
        target_origin="https://app.test",
        features=tuple(features),
        journeys=tuple(journeys),
        coverage_notes=(),
    ).model_dump(mode="json")


class FakeSession:
    def __init__(self, run: RunRecord, workspace: WorkspaceAccess) -> None:
        self.run = run
        self.workspace = workspace
        self.queued = False

    def begin(self) -> AsyncContext:
        return AsyncContext(None)


class FakeTestRunRepository:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def get_for_user(self, *, test_run_id: UUID, user_id: UUID) -> RunRecord | None:
        if self.session.run.test_run_id == test_run_id:
            return self.session.run
        return None

    async def update_configuration_snapshot(
        self, *, test_run_id: UUID, configuration_snapshot: dict[str, object],
    ) -> None:
        self.session.run = RunRecord(
            test_run_id=self.session.run.test_run_id,
            workspace_id=self.session.run.workspace_id,
            application_id=self.session.run.application_id,
            target_id=self.session.run.target_id,
            created_by_user_id=self.session.run.created_by_user_id,
            status=self.session.run.status,
            target_snapshot=self.session.run.target_snapshot,
            configuration_snapshot=configuration_snapshot,
            created_at=self.session.run.created_at,
            updated_at=datetime.now(UTC),
            started_at=self.session.run.started_at,
            completed_at=self.session.run.completed_at,
        )

    async def queue_if_awaiting_human_or_draft(
        self, *, test_run_id: UUID
    ) -> RunRecord | None:
        self.session.queued = True
        return self.session.run


class FakeWorkspaceRepository:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def get_for_user(self, *, workspace_id: UUID, user_id: UUID) -> WorkspaceAccess | None:
        if self.session.workspace.workspace_id == workspace_id:
            return self.session.workspace
        return None


class FakeDatabaseRuntime:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def session_factory(self) -> AsyncContext:
        return AsyncContext(self.session)


@pytest.fixture
def api_context(monkeypatch):
    workspace_id = uuid4()
    run_id = uuid4()
    user_id = uuid4()

    run = RunRecord(
        test_run_id=run_id,
        workspace_id=workspace_id,
        application_id=uuid4(),
        target_id=uuid4(),
        created_by_user_id=user_id,
        status="awaiting_human",
        target_snapshot={"base_url": "https://app.test"},
        configuration_snapshot={
            "discovery_map": _make_sample_discovery_map(),
            "discovery_stage": "awaiting_approval",
        },
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
        completed_at=None,
    )
    workspace = WorkspaceAccess(
        workspace_id=workspace_id,
        name="Test Workspace",
        status="active",
        role="owner",
    )
    session = FakeSession(run=run, workspace=workspace)
    db = FakeDatabaseRuntime(session)

    async def fake_get_user(**_):
        return user_id

    monkeypatch.setattr(test_contracts, "get_database_runtime", lambda _: db)
    monkeypatch.setattr(test_contracts, "get_authenticated_user_id", fake_get_user)
    monkeypatch.setattr(test_contracts, "TestRunRepository", FakeTestRunRepository)
    monkeypatch.setattr(test_contracts, "WorkspaceRepository", FakeWorkspaceRepository)

    request = object()
    return session, workspace_id, run_id, user_id, request


@pytest.mark.asyncio
async def test_contract_get_generates_and_returns_draft(api_context):
    session, workspace_id, run_id, user_id, request = api_context
    contract = await test_contracts.get_test_contract(workspace_id, run_id, request)

    assert contract.status == "draft"
    assert contract.version == 1
    assert len(contract.journeys) == 1
    assert contract.journeys[0].journey_key == "journey_explore"
    # Origin is None in draft
    assert contract.journeys[0].assertions[0].origin is None


@pytest.mark.asyncio
async def test_contract_generation_marks_completed_journeys_past_depth_as_excluded(api_context):
    from dataclasses import replace

    session, workspace_id, run_id, _, request = api_context
    snapshot = {
        **session.run.configuration_snapshot,
        "testing_depth": "low",
        "discovery_map": _make_sample_discovery_map(journey_count=5),
    }
    session.run = replace(session.run, configuration_snapshot=snapshot)

    contract = await test_contracts.get_test_contract(workspace_id, run_id, request)

    assert [journey.excluded for journey in contract.journeys] == [False, False, False, True, True]


@pytest.mark.asyncio
async def test_approval_rejects_edit_that_reenables_journeys_past_depth(api_context):
    from dataclasses import replace

    from fastapi import HTTPException

    session, workspace_id, run_id, _, request = api_context
    session.run = replace(session.run, configuration_snapshot={
        **session.run.configuration_snapshot,
        "testing_depth": "low",
        "discovery_map": _make_sample_discovery_map(journey_count=4),
    })
    contract = await test_contracts.get_test_contract(workspace_id, run_id, request)
    depth_excluded = contract.journeys[-1]
    assert depth_excluded.excluded

    await test_contracts.update_journey_contract(
        workspace_id, run_id, depth_excluded.journey_key,
        UpdateJourneyRequest(excluded=False), request,
    )
    with pytest.raises(HTTPException) as error:
        await test_contracts.approve_test_contract(workspace_id, run_id, request)

    assert error.value.status_code == 422
    assert "allows at most 3" in str(error.value.detail)
    assert session.run.configuration_snapshot["test_contract"]["status"] == "draft"


@pytest.mark.asyncio
async def test_contract_put_journey_updates_and_bumps_version(api_context):
    session, workspace_id, run_id, user_id, request = api_context
    # First get generates contract
    await test_contracts.get_test_contract(workspace_id, run_id, request)

    updated = await test_contracts.update_journey_contract(
        workspace_id,
        run_id,
        "journey_explore",
        UpdateJourneyRequest(excluded=True, title="Renamed Journey"),
        request,
    )

    assert updated.version == 2
    assert updated.status == "draft"
    assert updated.journeys[0].excluded is True
    assert updated.journeys[0].title == "Renamed Journey"


@pytest.mark.asyncio
async def test_contract_approve_sets_user_approved_origin(api_context):
    session, workspace_id, run_id, user_id, request = api_context
    await test_contracts.get_test_contract(workspace_id, run_id, request)

    approved = await test_contracts.approve_test_contract(workspace_id, run_id, request)

    assert approved.status == "approved"
    assert approved.approved_by_user_id == user_id
    assert approved.approved_at is not None
    # All non-excluded assertions gained user_approved origin
    for j in approved.journeys:
        if not j.excluded:
            for a in j.assertions:
                if not a.excluded:
                    assert a.origin == "user_approved"


@pytest.mark.asyncio
async def test_contract_reapproval_preserves_original_approver_stamp(api_context):
    session, workspace_id, run_id, user_id, request = api_context
    await test_contracts.get_test_contract(workspace_id, run_id, request)

    first = await test_contracts.approve_test_contract(workspace_id, run_id, request)
    second = await test_contracts.approve_test_contract(workspace_id, run_id, request)

    assert second.status == "approved"
    assert second.approved_by_user_id == first.approved_by_user_id == user_id
    assert second.approved_at == first.approved_at


@pytest.mark.asyncio
@pytest.mark.parametrize("worker_available", [True, False])
async def test_contract_start_freezes_contract_and_queues_run(
    api_context, monkeypatch, worker_available,
):
    from unittest.mock import AsyncMock

    from fastapi import HTTPException

    ready = AsyncMock(side_effect=None if worker_available else HTTPException(
        503, "Runner unavailable",
    ))
    monkeypatch.setattr(test_contracts, "require_run_ready", ready)
    session, workspace_id, run_id, user_id, request = api_context
    await test_contracts.get_test_contract(workspace_id, run_id, request)
    await test_contracts.approve_test_contract(workspace_id, run_id, request)

    # Mock OutboxRepository and RunDispatchService
    class FakeOutbox:
        def __init__(self, _):
            pass

        async def add(self, **kwargs):
            pass

    monkeypatch.setattr(test_contracts, "OutboxRepository", FakeOutbox)

    if not worker_available:
        with pytest.raises(HTTPException) as error:
            await test_contracts.start_test_contract_execution(workspace_id, run_id, request)
        assert error.value.status_code == 503
        assert session.run.configuration_snapshot["test_contract"]["status"] == "approved"
        assert "frozen_contract" not in session.run.configuration_snapshot
        assert session.queued is False
        return
    frozen = await test_contracts.start_test_contract_execution(workspace_id, run_id, request)

    assert frozen.status == "frozen"
    snapshot = session.run.configuration_snapshot
    assert snapshot["discovery_stage"] == "executing"
    assert "frozen_contract" in snapshot
    assert "frozen_contract_hash" in snapshot
    assert snapshot["frozen_contract_hash"] == frozen.content_hash()
    assert session.queued is True
    ready.assert_awaited_once()


@pytest.mark.asyncio
async def test_contract_start_rejects_approved_contract_above_selected_depth(api_context):
    from dataclasses import replace

    from fastapi import HTTPException
    session, workspace_id, run_id, user_id, request = api_context
    contract = await test_contracts.get_test_contract(workspace_id, run_id, request)
    template = contract.journeys[0]
    journeys = tuple(template.model_copy(update={
        "journey_key": f"journey_{index}", "title": f"Journey {index + 1}",
        "excluded": False,
    }) for index in range(4))
    approved = contract.model_copy(update={
        "status": "approved", "journeys": journeys, "approved_by_user_id": user_id,
        "approved_at": datetime.now(UTC),
    })
    session.run = replace(session.run, configuration_snapshot={
        **session.run.configuration_snapshot,
        "testing_depth": "low",
        "test_contract": approved.model_dump(mode="json"),
    })

    with pytest.raises(HTTPException) as error:
        await test_contracts.start_test_contract_execution(workspace_id, run_id, request)

    assert error.value.status_code == 409
    assert "allows at most 3" in str(error.value.detail)
    assert "frozen_contract" not in session.run.configuration_snapshot
    assert session.queued is False


async def test_incomplete_journey_cannot_be_unexcluded(api_context):
    from dataclasses import replace

    from fastapi import HTTPException

    session, workspace_id, run_id, _, request = api_context
    discovery = dict(session.run.configuration_snapshot["discovery_map"])
    discovery["journeys"][0]["completed"] = False
    discovery["journeys"][0]["blocked_reason"] = "authentication_required"
    session.run = replace(session.run, configuration_snapshot={
        **session.run.configuration_snapshot, "discovery_map": discovery,
    })
    contract = await test_contracts.get_test_contract(workspace_id, run_id, request)
    with pytest.raises(HTTPException) as error:
        await test_contracts.update_journey_contract(
            workspace_id, run_id, contract.journeys[0].journey_key,
            UpdateJourneyRequest(excluded=False), request,
        )
    assert error.value.status_code == 422
