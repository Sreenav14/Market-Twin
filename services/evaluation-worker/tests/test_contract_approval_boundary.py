"""Persisted failing fixture evidence confirms only under approved frozen tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from markettwin_control_api.api.contract_report_validation import validate_contract_report
from markettwin_database.models import (
    AgentExecution,
    Artifact,
    ExecutionStep,
    PersonaJourney,
    RunEvent,
    RunPersona,
)
from markettwin_evaluation_worker import contract_evaluator as evaluator
from markettwin_shared.contract_execution import contract_case
from markettwin_shared.deep_testing import AssertionResult, CaseExecutionResult
from markettwin_shared.discovery_contract import (
    ContractAssertion,
    DiscoveryMap,
    FrozenJourneyContract,
    TestContract,
)
from markettwin_shared.feature_plan import CaseAction, SemanticTarget


def persisted_failure():
    run_id = uuid4()
    journey = FrozenJourneyContract(
        journey_key="open_details", title="Open details", feature_key="catalog",
        steps=(CaseAction(action="click", target=SemanticTarget(role="button", name="Open")),),
        assertions=(ContractAssertion(
            assertion_id="details_title", oracle="title", expected_value="Details",
            plain_language="After opening details, title is Details.", source_step_ordinal=1,
            origin="user_approved",
        ),),
    )
    contract = TestContract(
        test_run_id=run_id, contract_id=uuid4(), status="frozen", journeys=(journey,),
        approved_by_user_id=uuid4(), approved_at=datetime.now(UTC),
    )
    case = contract_case(journey, "https://example.test")
    identity = {"contract_id": str(contract.contract_id), "contract_version": contract.version,
                "contract_hash": contract.content_hash()}
    events = [RunEvent(test_run_id=run_id, event_type="contract.execution_plan", payload={
        **identity, "cases": [case.model_dump(mode="json")],
    })]
    persona_id, journey_id = uuid4(), uuid4()
    rows = [
        events,
        [PersonaJourney(id=journey_id, persona_id=persona_id, test_run_id=run_id)],
        [],
        [RunPersona(id=persona_id, attributes={"contract_persona": 0})],
        [],
        [],
    ]
    original_id = None
    for attempt in (1, 2):
        execution_id, artifact_id = uuid4(), uuid4()
        assertion = AssertionResult(
            case_id=case.case_id, assertion_id="details_title", oracle="title",
            expected_value="Details", observed_value="Wrong", status="not_satisfied",
            origin="user_approved", execution_id=execution_id,
            step_id=(attempt - 1) * 3 + 3, artifact_ids=(artifact_id,), elapsed_ms=1,
        )
        result = CaseExecutionResult(
            case_id=case.case_id, execution_id=execution_id, execution_status="completed",
            verdict="not_satisfied", action_step_ids=((attempt - 1) * 3 + 1,
                                                        (attempt - 1) * 3 + 2),
            assertion_results=(assertion,), elapsed_ms=2,
        )
        rows[2].append(AgentExecution(
            id=execution_id, journey_id=journey_id, status="completed", attempt_number=attempt,
        ))
        for number, action in enumerate(("navigate", "click", "assertion"), start=1):
            step_id = (attempt - 1) * 3 + number
            rows[4].append(ExecutionStep(
                id=step_id, execution_id=execution_id, step_number=number,
                action_type=action, status="completed", action_summary=action,
                observation_summary=(
                    assertion.model_dump_json() if action == "assertion" else None
                ),
            ))
        rows[5].append(Artifact(
            id=artifact_id, execution_id=execution_id, step_id=(attempt - 1) * 3 + 3,
            artifact_type="screenshot", content_type="image/png",
            metadata_json={"kind": "viewport"},
        ))
        events.append(RunEvent(
            test_run_id=run_id, journey_id=journey_id, execution_id=execution_id,
            event_type="contract.case.completed", payload={
                **identity, "attempt": attempt, "persona_index": 0,
                "result": result.model_dump(mode="json"),
            },
        ))
        if attempt == 1:
            original_id = execution_id
        else:
            events.append(RunEvent(
                test_run_id=run_id, journey_id=journey_id, execution_id=execution_id,
                event_type="test_case.replay", payload={
                    **identity, "replay_of_execution_id": str(original_id),
                },
            ))
    return run_id, contract, rows


async def test_persisted_fail_fail_confirms_only_for_frozen_approved_contract(monkeypatch):
    run_id, contract, rows = persisted_failure()
    discovery = DiscoveryMap(target_origin="https://example.test")
    finding_id = uuid4()
    session = Mock(scalars=AsyncMock(
        side_effect=[Mock(all=Mock(return_value=items)) for items in rows],
    ))
    finding_repo = Mock(create_linked_finding=AsyncMock(return_value=finding_id))
    report_repo = Mock(create_completed_report=AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(evaluator, "EvaluationRepository", lambda _: finding_repo)
    monkeypatch.setattr(evaluator, "ReportRepository", lambda _: report_repo)
    monkeypatch.setattr(evaluator, "assess_experience", AsyncMock(
        return_value={"status": "unavailable"},
    ))
    monkeypatch.setattr(evaluator.VisualArtifactStorage, "from_environment", Mock(
        side_effect=ValueError,
    ))

    finding_ids, _ = await evaluator.evaluate_contract_run(
        test_run_id=run_id, contract=contract, discovery=discovery, session=session,
    )
    report = report_repo.create_completed_report.call_args.kwargs["report_payload"]
    assert finding_ids == (finding_id,)
    assert len(report["confirmed"]) == 1
    assert report["confirmed"][0]["verification"] == "verified_deterministic"

    proof_session = Mock(
        scalar=AsyncMock(return_value=uuid4()),
        scalars=AsyncMock(side_effect=[Mock(all=Mock(return_value=items)) for items in (
            rows[0], rows[4], rows[5], rows[4], rows[5],
        )]),
    )
    await validate_contract_report(
        run_id=run_id,
        snapshot={
            "frozen_contract": contract.model_dump(mode="json"),
            "frozen_contract_hash": contract.content_hash(),
            "discovery_map": discovery.model_dump(mode="json"),
        },
        payload=report,
        finding_ids=set(finding_ids),
        session=proof_session,
    )

    draft = contract.model_copy(update={"status": "draft"})
    rejected_repo = Mock(create_linked_finding=AsyncMock())
    rejected_reports = Mock(create_completed_report=AsyncMock())
    monkeypatch.setattr(evaluator, "EvaluationRepository", lambda _: rejected_repo)
    monkeypatch.setattr(evaluator, "ReportRepository", lambda _: rejected_reports)
    with pytest.raises(ValueError, match="approved frozen contract"):
        await evaluator.evaluate_contract_run(
            test_run_id=run_id, contract=draft, discovery=discovery, session=Mock(),
        )
    rejected_repo.create_linked_finding.assert_not_awaited()
    rejected_reports.create_completed_report.assert_not_awaited()
