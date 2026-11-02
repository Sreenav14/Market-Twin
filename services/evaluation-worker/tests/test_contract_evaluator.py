"""Report confirmation is checked against persisted steps and both browser attempts."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
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


def saved_run(replay_passes=False, foreign_artifact=False, failed_action=False):
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
    journeys, executions, personas, steps, artifacts = [], [], [], [], []
    for persona in range(3):
        persona_id, journey_id = uuid4(), uuid4()
        personas.append(RunPersona(id=persona_id, attributes={"contract_persona": persona}))
        journeys.append(PersonaJourney(id=journey_id, persona_id=persona_id, test_run_id=run_id))
        original_id = None
        for attempt in (1, 2):
            execution_id, artifact_id = uuid4(), uuid4()
            base = len(steps)
            passed = attempt == 2 and replay_passes
            assertion = AssertionResult(
                case_id=case.case_id, assertion_id="details_title", oracle="title",
                expected_value="Details", observed_value="Details" if passed else "Wrong",
                status="satisfied" if passed else "not_satisfied", origin="user_approved",
                execution_id=execution_id, step_id=base + 3,
                artifact_ids=(artifact_id,), elapsed_ms=1,
            )
            result = CaseExecutionResult(
                case_id=case.case_id, execution_id=execution_id,
                execution_status="failed" if failed_action else "completed",
                verdict="unverified" if failed_action else assertion.status,
                blocker="action_failed" if failed_action else None,
                action_step_ids=(base + 1, base + 2), assertion_results=(assertion,), elapsed_ms=2,
            )
            executions.append(AgentExecution(id=execution_id, journey_id=journey_id,
                                              status="failed" if failed_action else "completed",
                                              attempt_number=attempt))
            for number, action in enumerate(("navigate", "click", "assertion"), start=1):
                steps.append(ExecutionStep(
                    id=base + number, execution_id=execution_id, step_number=number,
                    action_type=action,
                    status="failed" if failed_action and action == "click" else "completed",
                    action_summary=action,
                    observation_summary=json.dumps(assertion.model_dump(mode="json"))
                    if action == "assertion" else None,
                ))
            artifacts.append(Artifact(
                id=artifact_id, execution_id=uuid4() if foreign_artifact else execution_id,
                step_id=base + 3, artifact_type="screenshot", content_type="image/png",
                metadata_json={"kind": "viewport"},
            ))
            events.append(RunEvent(
                test_run_id=run_id, journey_id=journey_id, execution_id=execution_id,
                event_type="contract.case.completed", payload={
                    **identity, "attempt": attempt, "persona_index": persona,
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
    return run_id, contract, (events, journeys, executions, personas, steps, artifacts)


@pytest.mark.parametrize("passes,foreign,confirmed", [(False, False, 1), (True, False, 0),
                                                      (False, True, 0)])
async def test_saved_evidence_replay_and_persona_dedup(monkeypatch, passes, foreign, confirmed):
    run_id, contract, rows = saved_run(passes, foreign)
    session = Mock(scalars=AsyncMock(side_effect=[Mock(all=Mock(return_value=r)) for r in rows]))
    finding_repo = Mock(create_linked_finding=AsyncMock(return_value=uuid4()))
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
        test_run_id=run_id, contract=contract,
        discovery=DiscoveryMap(target_origin="https://example.test"), session=session,
    )
    payload = report_repo.create_completed_report.call_args.kwargs["report_payload"]
    assert len(finding_ids) == confirmed
    assert finding_repo.create_linked_finding.await_count == confirmed
    assert len(payload["confirmed"]) == confirmed
    assert payload["what_works"] == []
    if confirmed:
        assert len(payload["confirmed_occurrences"]) == 3
        evidence = finding_repo.create_linked_finding.call_args.kwargs["evidence"]
        assert len({reference.execution_id for reference in evidence}) == 2
        assert payload["confirmed"][0]["screenshot_artifact_ids"]
        assert payload["confirmed"][0]["replay_screenshot_artifact_ids"]
    elif passes:
        assert {o["reason"] for o in payload["unverified"]} == {"did_not_reproduce"}
    if confirmed:
        from markettwin_control_api.api.contract_report_validation import validate_contract_report

        # The final API must accept the exact proof created by evaluation, not
        # only reject incomplete hand-authored report payloads.
        proof_session = Mock(
            scalar=AsyncMock(return_value=uuid4()),
            scalars=AsyncMock(side_effect=[Mock(all=Mock(return_value=r)) for r in (
                rows[0], rows[4], rows[5], rows[4], rows[5],
            )]),
        )
        discovery = DiscoveryMap(target_origin="https://example.test")
        await validate_contract_report(
            run_id=run_id, snapshot={
                "frozen_contract": contract.model_dump(mode="json"),
                "frozen_contract_hash": contract.content_hash(),
                "discovery_map": discovery.model_dump(mode="json"),
            }, payload=payload, finding_ids=set(finding_ids), session=proof_session,
        )


async def test_report_completed_step_count_excludes_failed_attempted_action(monkeypatch):
    run_id, contract, rows = saved_run(failed_action=True)
    session = Mock(scalars=AsyncMock(side_effect=[Mock(all=Mock(return_value=r)) for r in rows]))
    finding_repo = Mock(create_linked_finding=AsyncMock(return_value=uuid4()))
    report_repo = Mock(create_completed_report=AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(evaluator, "EvaluationRepository", lambda _: finding_repo)
    monkeypatch.setattr(evaluator, "ReportRepository", lambda _: report_repo)
    monkeypatch.setattr(evaluator, "assess_experience", AsyncMock(
        return_value={"status": "unavailable"},
    ))
    monkeypatch.setattr(evaluator.VisualArtifactStorage, "from_environment", Mock(
        side_effect=ValueError,
    ))

    await evaluator.evaluate_contract_run(
        test_run_id=run_id, contract=contract,
        discovery=DiscoveryMap(target_origin="https://example.test"), session=session,
    )

    payload = report_repo.create_completed_report.call_args.kwargs["report_payload"]
    assert len(payload["cases"]) == 3
    assert {case["completed_steps"] for case in payload["cases"]} == {1}
    assert {case["planned_steps"] for case in payload["cases"]} == {2}
    assert all(case["reason"] == "execution_incomplete" for case in payload["cases"])
