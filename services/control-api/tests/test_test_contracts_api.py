"""Tests for the TestContract API: the historical GET reader (U-P8)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from markettwin_control_api.api import test_contracts
from markettwin_control_api.persistence.repositories import (
    TestRunRecord as RunRecord,
)
from markettwin_control_api.persistence.repositories import (
    WorkspaceAccess,
)
from markettwin_shared.discovery_contract import (
    ContractAssertion,
    FrozenJourneyContract,
    TestContract,
)


class AsyncContext:
    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class FakeSession:
    def __init__(self, run: RunRecord, workspace: WorkspaceAccess) -> None:
        self.run = run
        self.workspace = workspace

    def begin(self) -> AsyncContext:
        return AsyncContext(None)


class FakeTestRunRepository:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def get_for_user(self, *, test_run_id: UUID, user_id: UUID) -> RunRecord | None:
        if self.session.run.test_run_id == test_run_id:
            return self.session.run
        return None


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
        configuration_snapshot={},
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
async def test_contract_get_returns_the_stored_contract(api_context):
    """U-P8: the contract endpoint is a pure historical reader."""

    session, workspace_id, run_id, user_id, request = api_context
    # No stored contract -> honest 404, nothing generated on read.
    with pytest.raises(HTTPException) as error:
        await test_contracts.get_test_contract(workspace_id, run_id, request)
    assert error.value.status_code == 404

    stored_contract = TestContract(
        contract_id=uuid4(),
        test_run_id=run_id,
        version=3,
        status="approved",
        journeys=[
            FrozenJourneyContract(
                journey_key="journey_explore",
                title="Explore",
                feature_key="explore",
                assertions=[
                    ContractAssertion(
                        assertion_id="a1",
                        oracle="visible_text",
                        plain_language="The home heading is visible",
                        origin="user_approved",
                        source_step_ordinal=1,
                    )
                ],
            )
        ],
    )
    stored = stored_contract.model_dump(mode="json")
    session.run = replace(
        session.run,
        configuration_snapshot={
            **session.run.configuration_snapshot,
            "test_contract": stored,
        },
    )
    contract = await test_contracts.get_test_contract(workspace_id, run_id, request)
    assert contract.version == 3
    assert contract.status == "approved"
    assert contract.journeys[0].assertions[0].origin == "user_approved"


@pytest.mark.asyncio
async def test_preserved_contract_payload_passes_serve_validation():
    """T-P5-E1 (serve half): a preserved contract report payload —
    frozen identity, no confirmed findings, zero coverage — is
    exactly what get_test_run_results serves for a
    discovery_contract_v1 run: validate_contract_report accepts it
    and raises no 409."""
    from types import SimpleNamespace

    from markettwin_control_api.api.contract_report_validation import (
        validate_contract_report,
    )
    from markettwin_shared.discovery_contract import (
        DiscoveryMap,
        TestContract,
    )

    run_id = uuid4()
    contract = TestContract(
        contract_id=uuid4(),
        test_run_id=run_id,
        version=1,
        status="frozen",
        approved_by_user_id=uuid4(),
        approved_at=datetime.now(UTC),
        journeys=[],
    )
    discovery = DiscoveryMap(target_origin="https://app.test")
    identity = {
        "contract_id": str(contract.contract_id),
        "contract_version": contract.version,
        "contract_hash": contract.content_hash(),
    }
    snapshot = {
        "frozen_contract": contract.model_dump(mode="json"),
        "discovery_map": discovery.model_dump(mode="json"),
        "frozen_contract_hash": contract.content_hash(),
    }
    payload = {
        **identity,
        "confirmed": [],
        "what_works": [],
        "coverage": {"executed": 0, "approved": 0, "verified_findings": 0},
        "market_verdict": {"coverage": 0.0, "confirmed_defects": 0},
    }
    plan_event = SimpleNamespace(
        event_type="contract.execution_plan",
        payload={**identity, "cases": []},
        execution_id=None,
        journey_id=None,
    )

    class _Scalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _Session:
        async def scalars(self, _select):
            return _Scalars([plan_event])

    # Returns None (no HTTPException) when the payload serves.
    await validate_contract_report(
        run_id=run_id,
        snapshot=snapshot,
        payload=payload,
        finding_ids=set(),
        session=_Session(),
    )
