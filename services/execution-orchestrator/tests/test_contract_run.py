"""Scheduling mechanics only; no model-quality or defect-recall claims."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from markettwin_database.models import TestRun
from markettwin_execution_orchestrator.browser import AllowedOrigin
from markettwin_execution_orchestrator.browser.errors import BrowserActionBlockedError
from markettwin_execution_orchestrator.workflow import contract_run
from markettwin_execution_orchestrator.workflow.run_executor import MarketTwinRunRequest
from markettwin_shared.deep_testing import AssertionResult, CaseExecutionResult
from markettwin_shared.discovery_contract import (
    ContractAssertion,
    FrozenJourneyContract,
    TestContract,
)
from markettwin_shared.feature_plan import CaseAction, SemanticTarget


@pytest.mark.parametrize("fails,attempts", [(True, 6), (False, 3)])
async def test_three_variants_and_exactly_one_confirmation_on_failure(monkeypatch, fails, attempts):
    run_id = uuid4()
    contract = TestContract(
        contract_id=uuid4(), test_run_id=run_id, status="frozen", approved_by_user_id=uuid4(),
        approved_at=datetime.now(UTC), journeys=(FrozenJourneyContract(
            journey_key="details", title="Open details", feature_key="catalog",
            steps=(CaseAction(action="click", target=SemanticTarget(role="button", name="Open")),),
            assertions=(ContractAssertion(
                assertion_id="title", oracle="title", expected_value="Details",
                plain_language="After opening details, the title is Details.",
                source_step_ordinal=1, origin="user_approved",
            ),),
        ),),
    )
    run = TestRun(id=run_id, status="planning", configuration_snapshot={
        "frozen_contract": contract.model_dump(mode="json"),
        "frozen_contract_hash": contract.content_hash(), "discovery_stage": "executing",
    })
    session = Mock(
        get=AsyncMock(return_value=run), flush=AsyncMock(), commit=AsyncMock(),
        scalar=AsyncMock(return_value=2),
    )
    events = Mock(create=AsyncMock())
    executions = Mock(create_agent_execution=AsyncMock(), finish_agent_execution=AsyncMock())
    states = Mock(mark_running=AsyncMock(), mark_completed=AsyncMock())
    monkeypatch.setattr(contract_run, "RunEventRepository", lambda _: events)
    monkeypatch.setattr(contract_run, "ExecutionRepository", lambda _: executions)
    monkeypatch.setattr(contract_run, "RunStateRepository", lambda _: states)
    controller = AsyncMock()
    monkeypatch.setattr(contract_run, "BrowserController", lambda: controller)

    async def execute(**kwargs):
        request, case = kwargs["request"], kwargs["case"]
        assertion = AssertionResult(
            case_id=case.case_id, assertion_id="title", oracle="title", expected_value="Details",
            observed_value="Wrong" if fails else "Details",
            status="not_satisfied" if fails else "satisfied", execution_id=request.execution_id,
            step_id=3, artifact_ids=(uuid4(),), origin="user_approved", elapsed_ms=1,
        )
        return CaseExecutionResult(
            case_id=case.case_id, execution_id=request.execution_id, execution_status="completed",
            verdict=assertion.status, action_step_ids=(1, 2), assertion_results=(assertion,),
            elapsed_ms=1,
        )

    execute_mock = AsyncMock(side_effect=execute)
    monkeypatch.setattr(contract_run, "execute_test_case", execute_mock)
    results = await contract_run.execute_contract_run(
        request=MarketTwinRunRequest(
            run_id=run_id, study_brief="Inspect the catalog", target_snapshot={},
            start_url="https://example.test/",
            allowed_origins=(AllowedOrigin("https", "example.test"),),
            execution_mode="discovery_contract_v1",
        ), session=session,
    )
    assert len(results) == attempts
    assert len({r.execution_id for r in results}) == attempts
    requests = [call.kwargs["request"] for call in execute_mock.await_args_list]
    assert {r.viewport_preset for r in requests} == {"desktop1280", "mobile320"}
    assert all(r.max_duration_seconds == 240 for r in requests)
    replays = [call for call in events.create.await_args_list
               if call.kwargs["event_type"] == "test_case.replay"]
    assert len(replays) == (3 if fails else 0)
    completed_events = [call.kwargs["payload"] for call in events.create.await_args_list
                        if call.kwargs["event_type"] == "contract.case.completed"]
    assert {event["completed_steps"] for event in completed_events} == {2}
    assert all(len(event["result"]["action_step_ids"]) == 2 for event in completed_events)
    assert run.configuration_snapshot["discovery_stage"] == "evaluating"


@pytest.mark.asyncio
async def test_opaque_confirmation_stops_contract_after_persisting_blocked_case(monkeypatch):
    run_id = uuid4()
    contract = TestContract(
        contract_id=uuid4(), test_run_id=run_id, status="frozen",
        approved_by_user_id=uuid4(), approved_at=datetime.now(UTC),
        journeys=tuple(FrozenJourneyContract(
            journey_key=key, title=f"Open {key}", feature_key=key,
            steps=(CaseAction(action="click", target=SemanticTarget(
                role="button", name=f"Open {key}")),),
            assertions=(ContractAssertion(
                assertion_id="title", oracle="title", expected_value=key,
                plain_language=f"Title is {key}.", source_step_ordinal=1,
                origin="user_approved",
            ),),
        ) for key in ("first", "second")),
    )
    run = TestRun(id=run_id, status="planning", configuration_snapshot={
        "frozen_contract": contract.model_dump(mode="json"),
        "frozen_contract_hash": contract.content_hash(), "discovery_stage": "executing",
    })
    session = Mock(
        get=AsyncMock(return_value=run), flush=AsyncMock(), commit=AsyncMock(),
        scalar=AsyncMock(return_value=0),
    )
    events = Mock(create=AsyncMock())
    executions = Mock(create_agent_execution=AsyncMock(), finish_agent_execution=AsyncMock())
    states = Mock(mark_running=AsyncMock(), mark_completed=AsyncMock())
    monkeypatch.setattr(contract_run, "RunEventRepository", lambda _: events)
    monkeypatch.setattr(contract_run, "ExecutionRepository", lambda _: executions)
    monkeypatch.setattr(contract_run, "RunStateRepository", lambda _: states)
    monkeypatch.setattr(contract_run, "BrowserController", lambda: AsyncMock())
    blocked = CaseExecutionResult(
        case_id="first", execution_id=uuid4(), execution_status="policy_blocked",
        verdict="unverified", blocker="human_takeover_required", elapsed_ms=1,
    )
    execute_mock = AsyncMock(return_value=blocked)
    monkeypatch.setattr(contract_run, "execute_test_case", execute_mock)

    with pytest.raises(
        BrowserActionBlockedError,
        match="opaque confirmation requires human browser takeover",
    ):
        await contract_run.execute_contract_run(
            request=MarketTwinRunRequest(
                run_id=run_id, study_brief="Inspect both", target_snapshot={},
                start_url="https://example.test/",
                allowed_origins=(AllowedOrigin("https", "example.test"),),
                execution_mode="discovery_contract_v1",
            ), session=session,
        )

    assert execute_mock.await_count == 1
    assert executions.finish_agent_execution.await_count == 1
    assert states.mark_completed.await_count == 0
    completion = next(call.kwargs["payload"] for call in events.create.await_args_list
                      if call.kwargs["event_type"] == "contract.case.completed")
    assert completion["result"]["blocker"] == "human_takeover_required"
