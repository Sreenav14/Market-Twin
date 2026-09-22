"""Tests for the complete MarketTwin evaluation workflow."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from markettwin_evaluation_worker import workflow
from markettwin_evaluation_worker.observability import VisualInvocationRecorder
from markettwin_evaluation_worker.persistence.evaluation_repository import EvaluationRepository
from markettwin_evaluation_worker.persistence.observability_repository import (
    EvaluationObservabilityRepository,
)
from markettwin_evaluation_worker.visual_artifact_storage import (
    VisualArtifactStorage,
)
from markettwin_evaluation_worker.visual_batch_evaluator import (
    VisualBatchEvaluationResult,
)
from markettwin_shared.observability import AgentRuntimeSnapshotSpec
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_workflow_runs_visual_evaluation_before_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Visual verification must run before final report generation."""

    test_run_id = uuid4()
    finding_id = uuid4()
    report_id = uuid4()

    events: list[str] = []
    observability_repository = MagicMock(spec=EvaluationObservabilityRepository)
    async def fake_snapshot(*, snapshot_id: UUID, snapshot: AgentRuntimeSnapshotSpec) -> UUID:
        events.append("snapshot")
        return snapshot_id

    observability_repository.create_agent_snapshot.side_effect = fake_snapshot
    repository_factory = MagicMock(return_value=observability_repository)
    monkeypatch.setattr(workflow, "EvaluationObservabilityRepository", repository_factory)

    async def fake_deterministic(
        *,
        test_run_id: UUID,
        session: AsyncSession,
    ) -> SimpleNamespace:
        events.append("deterministic")

        return SimpleNamespace(
            finding_ids=(
                finding_id,
            )
        )

    async def fake_visual(
        *,
        test_run_id: UUID,
        repository: EvaluationRepository,
        storage: VisualArtifactStorage,
        invocation_recorder: VisualInvocationRecorder,
    ) -> VisualBatchEvaluationResult:
        assert isinstance(invocation_recorder, VisualInvocationRecorder)
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
    ) -> SimpleNamespace:
        events.append("report")

        return SimpleNamespace(
            report_id=report_id,
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

    session = MagicMock(spec=AsyncSession)

    storage = cast(
        VisualArtifactStorage,
        object(),
    )

    result = (
        await workflow.evaluate_and_generate_report(
            test_run_id=test_run_id,
            session=session,
            visual_storage=storage,
        )
    )

    assert events == [
        "deterministic",
        "snapshot",
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

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    repository_factory.assert_called_once_with(session)
    observability_repository.create_agent_snapshot.assert_awaited_once()
    snapshot = observability_repository.create_agent_snapshot.call_args.kwargs["snapshot"]
    assert snapshot.test_run_id == str(test_run_id)
    assert snapshot.agent_role == "visual_verifier"
