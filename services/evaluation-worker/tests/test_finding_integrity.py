"""Regression tests for findings that overstate or misattribute evidence."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from markettwin_evaluation_worker import deterministic_evaluator, report_generator
from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
    EvidenceReference,
    JourneyResultRecord,
)
from markettwin_evaluation_worker.persistence.report_repository import ReportFindingRecord
from sqlalchemy.ext.asyncio import AsyncSession


def _rows(values: list[object]) -> SimpleNamespace:
    return SimpleNamespace(all=lambda: values)


@pytest.mark.asyncio
async def test_agent_claims_never_use_latest_screenshot_as_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id, mission_id = uuid4(), uuid4()
    journeys = tuple(
        JourneyResultRecord(
            journey_id=uuid4(),
            persona_id=uuid4(),
            mission_id=mission_id,
            execution_id=uuid4(),
            payload={
                "status": "completed",
                "outcome": "failed",
                "summary": "Checkout failed",
                "unsatisfied_criteria": ["Confirmation visible"],
            },
        )
        for _ in range(2)
    )
    repository = SimpleNamespace(
        validate_run_ready=AsyncMock(),
        list_journey_results=AsyncMock(return_value=journeys),
        find_preferred_evidence=AsyncMock(
            side_effect=AssertionError("Unrelated latest screenshot"),
        ),
        find_reported_evidence=AsyncMock(return_value=()),
        create_finding=AsyncMock(side_effect=lambda **kwargs: uuid4()),
        create_linked_finding=AsyncMock(side_effect=lambda **kwargs: uuid4()),
    )
    monkeypatch.setattr(deterministic_evaluator, "EvaluationRepository", lambda session: repository)
    result = await deterministic_evaluator.evaluate_completed_run(
        test_run_id=run_id,
        session=cast(AsyncSession, object()),
    )
    assert result.finding_count == 3
    repository.find_preferred_evidence.assert_not_awaited()
    for call in repository.create_finding.await_args_list:
        assert call.kwargs["evidence"] == ()
        assert "not a verified product defect" in call.kwargs["summary"]
    cross = repository.create_linked_finding.await_args.kwargs
    assert cross["evidence"] == ()
    assert cross["severity"] == "info"
    assert "not independent verification" in cross["summary"]


@pytest.mark.asyncio
@pytest.mark.parametrize("original_report_only", [False, True])
async def test_repeated_claims_link_only_the_exact_criterion_steps(
    monkeypatch: pytest.MonkeyPatch,
    original_report_only: bool,
) -> None:
    run_id, mission_id = uuid4(), uuid4()
    journeys = tuple(
        JourneyResultRecord(
            journey_id=uuid4(),
            persona_id=uuid4(),
            mission_id=mission_id,
            execution_id=uuid4(),
            payload={
                "status": "completed",
                "outcome": "failed",
                "unsatisfied_criteria": ["Confirmation visible"],
                "criterion_evidence": [
                    {
                        "criterion": "Confirmation visible",
                        "status": "unsatisfied",
                        "evidence_step_ids": [step_id],
                    },
                    {
                        "criterion": "Other criterion",
                        "status": "unsatisfied",
                        "evidence_step_ids": [99],
                    },
                    {
                        "criterion": "Confirmation visible",
                        "status": "satisfied",
                        "evidence_step_ids": [100],
                    },
                ],
            },
        )
        for step_id in (7, 9)
    )
    if original_report_only:
        for journey in journeys:
            journey.payload["reported_criterion_evidence"] = journey.payload.pop(
                "criterion_evidence"
            )
            journey.payload["criterion_evidence"] = []
            journey.payload["outcome"] = "inconclusive"
            journey.payload["reported_outcome"] = "failed"
            journey.payload["reported_unsatisfied_criteria"] = ["Confirmation visible"]
            journey.payload["unsatisfied_criteria"] = []

    async def reported_evidence(
        *,
        execution_id: UUID,
        step_ids: tuple[int, ...],
    ) -> tuple[EvidenceReference, ...]:
        return tuple(
            EvidenceReference(step_id=step_id, execution_id=execution_id) for step_id in step_ids
        )

    repository = SimpleNamespace(
        validate_run_ready=AsyncMock(),
        list_journey_results=AsyncMock(return_value=journeys),
        find_reported_evidence=AsyncMock(side_effect=reported_evidence),
        create_finding=AsyncMock(side_effect=lambda **kwargs: uuid4()),
        create_linked_finding=AsyncMock(side_effect=lambda **kwargs: uuid4()),
    )
    monkeypatch.setattr(deterministic_evaluator, "EvaluationRepository", lambda session: repository)
    await deterministic_evaluator.evaluate_completed_run(
        test_run_id=run_id,
        session=cast(AsyncSession, object()),
    )
    cross = repository.create_linked_finding.await_args.kwargs
    assert cross["journey_ids"] == tuple(journey.journey_id for journey in journeys)
    assert cross["evidence"] == (
        EvidenceReference(step_id=7, execution_id=journeys[0].execution_id),
        EvidenceReference(step_id=9, execution_id=journeys[1].execution_id),
    )
    assert cross["severity"] == "info"


@pytest.mark.asyncio
async def test_missing_reported_step_has_no_substitute_screenshot() -> None:
    execution_id = uuid4()
    session = SimpleNamespace(scalars=AsyncMock(side_effect=[_rows([]), _rows([])]))
    evidence = await EvaluationRepository(cast(AsyncSession, session)).find_reported_evidence(
        execution_id=execution_id,
        step_ids=(999,),
    )
    assert evidence == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_reference",
    [
        "wrong_execution",
        "missing_step",
        "wrong_step",
        "missing_artifact",
        "cross_run",
        "wrong_attempt",
    ],
)
async def test_visual_evidence_rejects_invalid_ownership(bad_reference: str) -> None:
    run_id, journey_id, execution_id, artifact_id = (uuid4() for _ in range(4))
    artifact = SimpleNamespace(
        id=artifact_id,
        execution_id=execution_id,
        step_id=7,
        artifact_type="screenshot",
    )
    step = SimpleNamespace(id=7, execution_id=execution_id)
    if bad_reference == "wrong_execution":
        artifact.execution_id = uuid4()
    if bad_reference == "wrong_step":
        artifact.step_id = 8
    session = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                _rows([] if bad_reference == "cross_run" else [journey_id]),
                _rows([execution_id]),
                _rows([] if bad_reference == "missing_artifact" else [artifact]),
                _rows([] if bad_reference == "missing_step" else [step]),
            ]
        ),
        add=Mock(),
        flush=AsyncMock(),
    )
    repository = EvaluationRepository(cast(AsyncSession, session))
    with pytest.raises(ValueError):
        await repository.create_linked_finding(
            test_run_id=run_id,
            journey_ids=(journey_id,),
            severity="medium",
            category="visual_criterion",
            title="Clipped heading",
            summary="Visible clipping",
            recommendation="Inspect heading",
            evidence=(
                EvidenceReference(
                    step_id=7,
                    artifact_id=artifact_id,
                    execution_id=uuid4() if bad_reference == "wrong_attempt" else execution_id,
                ),
            ),
        )
    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_visual_finding_retains_exact_step_and_screenshot() -> None:
    from markettwin_database.models import FindingEvidence

    run_id, journey_id, execution_id, artifact_id = (uuid4() for _ in range(4))
    artifact = SimpleNamespace(
        id=artifact_id, execution_id=execution_id, step_id=7, artifact_type="screenshot"
    )
    step = SimpleNamespace(id=7, execution_id=execution_id)
    session = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                _rows([journey_id]),
                _rows([execution_id]),
                _rows([artifact]),
                _rows([step]),
            ]
        ),
        add=Mock(),
        flush=AsyncMock(),
    )
    await EvaluationRepository(cast(AsyncSession, session)).create_linked_finding(
        test_run_id=run_id,
        journey_ids=(journey_id,),
        severity="medium",
        category="visual_criterion",
        title="Clipped heading",
        summary="Observed clipping",
        recommendation="Fix heading",
        evidence=(
            EvidenceReference(step_id=7, artifact_id=artifact_id, execution_id=execution_id),
        ),
    )
    links = [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], FindingEvidence)
    ]
    assert [(link.step_id, link.artifact_id) for link in links] == [(7, None), (None, artifact_id)]


@pytest.mark.asyncio
async def test_diagnostic_without_evidence_is_preserved() -> None:
    run_id, journey_id = uuid4(), uuid4()
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=_rows([journey_id])),
        add=Mock(),
        flush=AsyncMock(),
    )
    await EvaluationRepository(cast(AsyncSession, session)).create_linked_finding(
        test_run_id=run_id,
        journey_ids=(journey_id,),
        severity="high",
        category="execution_reliability",
        title="Browser crashed",
        summary="No capture available",
        recommendation="Check runtime",
        evidence=(),
    )
    assert session.add.call_count == 2  # Finding and Journey; no fabricated evidence.


def test_report_does_not_call_agent_claims_evidence_backed() -> None:
    summary, payload = report_generator.build_report_payload(
        test_run_id=uuid4(),
        journey_results=(),
        findings=(
            ReportFindingRecord(
                finding_id=uuid4(),
                severity="high",
                category="journey_outcome",
                title="Agent reported failure",
                summary="No confirmation",
                recommendation=None,
                journey_ids=(uuid4(),),
            ),
        ),
    )
    assert "evidence-backed" not in summary
    assert "unverified" in summary
    finding_payload = cast(dict[str, object], payload["findings"])
    items = cast(list[dict[str, object]], finding_payload["items"])
    assert items[0]["verification_status"] == "unverified"
    assert finding_payload["confirmed_issue_count"] == 0


@pytest.mark.parametrize("has_visual_evidence", [False, True])
def test_report_counts_only_visual_findings_with_valid_evidence(has_visual_evidence: bool) -> None:
    _, payload = report_generator.build_report_payload(
        test_run_id=uuid4(),
        journey_results=(),
        findings=(
            ReportFindingRecord(
                finding_id=uuid4(),
                severity="medium",
                category="visual_criterion",
                title="Heading clipped",
                summary="Clipping observed",
                recommendation=None,
                journey_ids=(uuid4(),),
                has_visual_evidence=has_visual_evidence,
            ),
        ),
    )
    counts = cast(dict[str, object], payload["findings"])
    assert counts["confirmed_issue_count"] == int(has_visual_evidence)
    assert counts["unverified_observation_count"] == int(not has_visual_evidence)


@pytest.mark.asyncio
async def test_report_persists_assessment_before_returning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid4()
    report_repository = SimpleNamespace(
        validate_run_ready=AsyncMock(),
        list_findings=AsyncMock(return_value=()),
        create_completed_report=AsyncMock(return_value=uuid4()),
    )
    monkeypatch.setattr(report_generator, "ReportRepository", lambda session: report_repository)
    monkeypatch.setattr(
        report_generator,
        "EvaluationRepository",
        lambda session: SimpleNamespace(
            list_journey_results=AsyncMock(return_value=()),
        ),
    )
    assessment = {"status": "completed", "overall_outcome": "inconclusive"}
    await report_generator.generate_deterministic_report(
        test_run_id=run_id,
        session=cast(AsyncSession, object()),
        assessment=assessment,
    )
    saved = report_repository.create_completed_report.await_args.kwargs["report_payload"]
    assert saved["assessment"] == assessment
