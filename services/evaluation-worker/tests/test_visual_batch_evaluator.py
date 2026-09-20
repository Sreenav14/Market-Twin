"""Tests for vision-on-demand criterion evaluation."""

from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from markettwin_evaluation_worker import (
    visual_batch_evaluator,
)
from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
    JourneyResultRecord,
    VisualArtifactRecord,
    VisualEvidenceSet,
)
from markettwin_evaluation_worker.visual_artifact_storage import (
    VisualArtifactStorage,
)
from markettwin_evaluation_worker.visual_evaluation import (
    VisualCriterionEvaluation,
)


class FakeRepository:
    def __init__(self) -> None:
        self.execution_id = uuid4()
        self.journey_id = uuid4()

    async def list_journey_results(
        self,
        *,
        test_run_id,
    ):
        return (
            JourneyResultRecord(
                journey_id=self.journey_id,
                persona_id=uuid4(),
                mission_id=uuid4(),
                execution_id=self.execution_id,
                payload={
                    "criterion_evidence": [
                        {
                            "criterion": (
                                "Continue button exists."
                            ),
                            "status": "satisfied",
                            "evidence_step_ids": [4],
                        },
                        {
                            "criterion": (
                                "Heading is visually readable."
                            ),
                            "status": "unverified",
                            "evidence_step_ids": [7],
                        },
                    ]
                },
            ),
        )

    async def list_visual_evidence(
        self,
        *,
        execution_id,
        step_ids,
    ):
        artifact = VisualArtifactRecord(
            artifact_id=uuid4(),
            step_id=step_ids[0],
            kind="viewport",
            storage_provider="minio",
            bucket="markettwin",
            object_key="viewport.png",
            content_type="image/png",
        )

        if step_ids == (4,):
            return (
                VisualEvidenceSet(
                    step_id=4,
                    action_type="click",
                    viewport=artifact,
                ),
            )

        return (
            VisualEvidenceSet(
                step_id=7,
                action_type="capture_element",
                viewport=artifact,
            ),
        )


class FakeStorage:
    async def download(
        self,
        *,
        artifact,
        directory: Path,
    ) -> Path:
        raise AssertionError(
            "Storage should be handled by the mocked evaluator."
        )


@pytest.mark.asyncio
async def test_batch_runs_vision_only_for_explicit_visual_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Semantic evidence must not cause a visual model call."""

    test_run_id = uuid4()
    repository = FakeRepository()

    called: list[str] = []

    async def fake_evaluate(
        *,
        criterion,
        evidence,
        storage,
    ):
        called.append(
            criterion
        )

        assert len(evidence) == 1
        assert (
            evidence[0].action_type
            == "capture_element"
        )

        return VisualCriterionEvaluation(
            criterion=criterion,
            status="satisfied",
            rationale=(
                "The heading is clearly readable."
            ),
            observed_details=(
                "Heading is unobscured.",
            ),
            evidence_step_id=7,
            artifact_ids=(
                evidence[0]
                .viewport
                .artifact_id,
            ),
        )

    monkeypatch.setattr(
        visual_batch_evaluator,
        "evaluate_visual_criterion_from_evidence",
        fake_evaluate,
    )

    result = (
        await visual_batch_evaluator
        .evaluate_visual_criteria_for_run(
            test_run_id=test_run_id,
            repository=cast(
                EvaluationRepository,
                repository,
            ),
            storage=cast(
                VisualArtifactStorage,
                FakeStorage(),
            ),
        )
    )

    assert called == [
        "Heading is visually readable."
    ]

    assert len(result.evaluations) == 1

    item = result.evaluations[0]

    assert item.reported_status == "unverified"
    assert (
        item.evaluation.status
        == "satisfied"
    )
    assert (
        item.evaluation.evidence_step_id
        == 7
    )