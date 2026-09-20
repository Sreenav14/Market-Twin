"""Tests for the complete MarketTwin evaluation workflow."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_evaluation_worker import workflow
from markettwin_evaluation_worker.visual_artifact_storage import (
    VisualArtifactStorage,
)
from markettwin_evaluation_worker.visual_batch_evaluator import (
    VisualBatchEvaluationResult,
)


@pytest.mark.asyncio
async def test_workflow_runs_visual_evaluation_before_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Visual verification must run before final report generation."""

    test_run_id = uuid4()
    finding_id = uuid4()
    report_id = uuid4()

    events: list[str] = []

    async def fake_deterministic(
        *,
        test_run_id,
        session,
    ):
        events.append("deterministic")

        return SimpleNamespace(
            finding_ids=(
                finding_id,
            )
        )

    async def fake_visual(
        *,
        test_run_id,
        repository,
        storage,
    ):
        events.append("visual")

        return VisualBatchEvaluationResult(
            test_run_id=test_run_id,
            evaluations=(),
        )
        
    async def fake_visual_findings(
        *,
        test_run_id,
        visual_result,
        repository,
    ):
        events.append("visual_findings")
        return ()

    async def fake_report(
        *,
        test_run_id,
        session,
    ):
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
            session=session,
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

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()