"""Tests for the complete MarketTwin evaluation workflow."""

from types import SimpleNamespace
from typing import cast
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
    VisualBatchEvaluationResult,
)
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_workflow_runs_visual_evaluation_before_report(
    monkeypatch: pytest.MonkeyPatch,
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

        return DeterministicEvaluationResult(
            test_run_id=test_run_id,
            finding_ids=(
                finding_id,
            )
        )

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
            evaluations=(),
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
    ) -> GeneratedReportResult:
        events.append("report")

        return GeneratedReportResult(
            report_id=report_id,
            test_run_id=test_run_id,
        )

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
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )

    storage = cast(
        VisualArtifactStorage,
        object(),
    )

    result = (
        await workflow.evaluate_and_generate_report(
            test_run_id=test_run_id,
            session=cast(
                AsyncSession,
                session,
            ),
            visual_storage=storage,
        )
    )

    assert events == [
        "deterministic",
        "visual",
        "visual_findings",
        "report",
    ]

    assert result.test_run_id == test_run_id

    assert result.finding_ids == (
        finding_id,
    )

    assert result.report_id == report_id

    assert (
        result.visual_evaluation_count
        == 0
    )

    assert session.commit.await_count == 2
    session.rollback.assert_not_awaited()