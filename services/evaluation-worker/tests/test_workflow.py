"""Tests for the complete MarketTwin evaluation workflow."""

from types import SimpleNamespace
from typing import Literal, cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from markettwin_evaluation_worker import workflow
from markettwin_evaluation_worker.deterministic_evaluator import (
    DeterministicEvaluationResult,
)
from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
)
from markettwin_evaluation_worker.report_generator import (
    GeneratedReportResult,
)
from markettwin_evaluation_worker.visual_artifact_storage import (
    VisualArtifactStorage,
)
from markettwin_evaluation_worker.visual_batch_evaluator import (
    JourneyVisualEvaluation,
    VisualBatchEvaluationResult,
)
from markettwin_evaluation_worker.visual_evaluation import VisualCriterionEvaluation
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
@pytest.mark.parametrize("visual_status", [None, "satisfied", "unsatisfied", "unverified"])
async def test_workflow_runs_visual_evaluation_before_report(
    monkeypatch: pytest.MonkeyPatch,
    visual_status: Literal["satisfied", "unsatisfied", "unverified"] | None,
) -> None:
    """Visual verification must run before final report generation."""

    test_run_id = uuid4()
    visual_snapshot_id = uuid4()
    finding_id = uuid4()
    report_id = uuid4()

    events: list[str] = []

    async def fake_deterministic(
        *,
        test_run_id: UUID,
        session: AsyncSession,
    ) -> DeterministicEvaluationResult:
        events.append("deterministic")

        return DeterministicEvaluationResult(test_run_id=test_run_id, finding_ids=(finding_id,))

    async def fake_visual(
        *,
        test_run_id: UUID,
        agent_snapshot_id: UUID,
        repository: EvaluationRepository,
        storage: VisualArtifactStorage,
    ) -> VisualBatchEvaluationResult:
        assert agent_snapshot_id == visual_snapshot_id
        events.append("visual")

        return VisualBatchEvaluationResult(
            test_run_id=test_run_id,
            evaluations=()
            if visual_status is None
            else (
                JourneyVisualEvaluation(
                    journey_id=test_run_id,
                    execution_id=visual_snapshot_id,
                    reported_status="satisfied",
                    evaluation=VisualCriterionEvaluation(
                        criterion="The heading is visible",
                        status=visual_status,
                        rationale="A recorded pixel-based explanation",
                        observed_details=("A visible heading",),
                        evidence_step_id=42,
                        artifact_ids=(finding_id,),
                    ),
                ),
            ),
        )

    async def fake_visual_findings(
        *,
        test_run_id: UUID,
        visual_result: VisualBatchEvaluationResult,
        repository: EvaluationRepository,
    ) -> tuple[UUID, ...]:
        events.append("visual_findings")
        return ()

    async def fake_report(
        *,
        test_run_id: UUID,
        session: AsyncSession,
        evaluation_records: tuple[dict[str, object], ...],
        assessment: dict[str, object],
    ) -> GeneratedReportResult:
        events.append("report")
        assert assessment == {"status": "completed", "test_run_id": str(test_run_id)}
        if visual_status is None:
            assert evaluation_records == ()
        else:
            assert len(evaluation_records) == 1
            assert evaluation_records[0]["status"] == visual_status
            assert evaluation_records[0]["reported_status"] == "satisfied"
            assert evaluation_records[0]["evidence"] == {
                "step_ids": [42],
                "artifact_ids": [str(finding_id)],
            }

        return GeneratedReportResult(
            report_id=report_id,
            test_run_id=test_run_id,
        )

    expected_test_run_id = test_run_id

    async def fake_assessment(
        *, test_run_id: UUID, session: AsyncSession,
        evaluation_records: tuple[dict[str, object], ...],
    ) -> dict[str, object]:
        events.append("assessment")
        assert test_run_id == expected_test_run_id
        assert len(evaluation_records) == (0 if visual_status is None else 1)
        return {"status": "completed", "test_run_id": str(test_run_id)}

    monkeypatch.setattr(workflow, "assess_completed_run", fake_assessment)
    monkeypatch.setattr(
        workflow,
        "evaluate_completed_run",
        fake_deterministic,
    )

    monkeypatch.setattr(
        workflow,
        "evaluate_visual_criteria_for_run",
        fake_visual,
    )

    monkeypatch.setattr(
        workflow,
        "persist_visual_findings",
        fake_visual_findings,
    )

    monkeypatch.setattr(
        workflow,
        "generate_deterministic_report",
        fake_report,
    )

    snapshot_repository = SimpleNamespace(
        ensure_run_level_snapshot=AsyncMock(
            return_value=visual_snapshot_id,
        )
    )

    def fake_snapshot_repository_factory(
        session: AsyncSession,
    ) -> SimpleNamespace:
        return snapshot_repository

    monkeypatch.setattr(
        workflow,
        "EvaluationRuntimeSnapshotRepository",
        fake_snapshot_repository_factory,
    )

    evaluation_repository = SimpleNamespace(
        validate_run_ready=AsyncMock(),
    )

    def fake_evaluation_repository_factory(
        session: AsyncSession,
    ) -> SimpleNamespace:
        return evaluation_repository

    monkeypatch.setattr(
        workflow,
        "EvaluationRepository",
        fake_evaluation_repository_factory,
    )

    session = SimpleNamespace(
        get=AsyncMock(return_value=None),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )

    storage = cast(
        VisualArtifactStorage,
        object(),
    )

    result = await workflow.evaluate_and_generate_report(
        test_run_id=test_run_id,
        session=cast(
            AsyncSession,
            session,
        ),
        visual_storage=storage,
    )

    assert events == [
        "deterministic",
        "visual",
        "visual_findings",
        "assessment",
        "report",
    ]

    assert result.test_run_id == test_run_id

    assert result.finding_ids == (finding_id,)

    assert result.report_id == report_id

    assert result.visual_evaluation_count == (0 if visual_status is None else 1)

    assert session.commit.await_count == 2
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize("failure_stage", ["provenance", "evaluation", "report"])
async def test_retry_after_each_commit_boundary(
    monkeypatch: pytest.MonkeyPatch, failure_stage: str,
) -> None:
    """An intermediate snapshot commit cannot be mistaken for final completion."""
    run_id, snapshot_id, report_id = uuid4(), uuid4(), uuid4()
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = None
    repository = SimpleNamespace(validate_run_ready=AsyncMock())
    snapshot_repository = SimpleNamespace(
        ensure_run_level_snapshot=AsyncMock(return_value=snapshot_id)
    )
    def make_evaluation_repository(session: AsyncSession) -> SimpleNamespace:
        return repository

    def make_snapshot_repository(session: AsyncSession) -> SimpleNamespace:
        return snapshot_repository

    monkeypatch.setattr(workflow, "EvaluationRepository", make_evaluation_repository)
    monkeypatch.setattr(
        workflow, "EvaluationRuntimeSnapshotRepository", make_snapshot_repository
    )
    deterministic = AsyncMock(return_value=DeterministicEvaluationResult(
        test_run_id=run_id, finding_ids=(),
    ))
    report = AsyncMock(return_value=SimpleNamespace(report_id=report_id))
    monkeypatch.setattr(workflow, "evaluate_completed_run", deterministic)
    monkeypatch.setattr(workflow, "evaluate_visual_criteria_for_run", AsyncMock(
        return_value=VisualBatchEvaluationResult(test_run_id=run_id, evaluations=()),
    ))
    monkeypatch.setattr(workflow, "persist_visual_findings", AsyncMock(return_value=()))
    monkeypatch.setattr(workflow, "assess_completed_run", AsyncMock())
    monkeypatch.setattr(workflow, "generate_deterministic_report", report)
    failing = {"provenance": snapshot_repository.ensure_run_level_snapshot,
               "evaluation": deterministic, "report": report}[failure_stage]
    failing.side_effect = RuntimeError("injected failure")
    with pytest.raises(RuntimeError, match="injected failure"):
        await workflow.evaluate_and_generate_report(
            test_run_id=run_id, session=session,
            visual_storage=cast(VisualArtifactStorage, object()),
        )
    assert session.commit.await_count == (0 if failure_stage == "provenance" else 1)
    session.rollback.assert_awaited_once()
    failing.side_effect = None
    result = await workflow.evaluate_and_generate_report(
        test_run_id=run_id, session=session, visual_storage=cast(VisualArtifactStorage, object()),
    )
    assert result.report_id == report_id
    assert result.finding_ids == ()
    assert snapshot_repository.ensure_run_level_snapshot.await_count == 2
    assert session.commit.await_count == (2 if failure_stage == "provenance" else 3)
