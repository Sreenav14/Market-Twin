"""Tests for visual Finding persistence."""

from uuid import UUID, uuid4

import pytest
from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvidenceReference,
)
from markettwin_evaluation_worker.visual_batch_evaluator import (
    JourneyVisualEvaluation,
    VisualBatchEvaluationResult,
)
from markettwin_evaluation_worker.visual_evaluation import (
    VisualCriterionEvaluation,
)
from markettwin_evaluation_worker.visual_findings import (
    persist_visual_findings,
)


class FakeRepository:
    def __init__(self) -> None:
        self.created: list[
            dict[str, object]
        ] = []

    async def create_linked_finding(
        self,
        **kwargs: object,
    ) -> UUID:
        self.created.append(kwargs)
        return uuid4()


@pytest.mark.asyncio
async def test_unsatisfied_visual_result_creates_finding() -> None:
    """Confirmed visual failures must become evidence-backed Findings."""

    test_run_id = uuid4()
    journey_id = uuid4()
    execution_id = uuid4()

    viewport_id = uuid4()
    crop_id = uuid4()

    visual_result = VisualBatchEvaluationResult(
        test_run_id=test_run_id,
        evaluations=(
            JourneyVisualEvaluation(
                journey_id=journey_id,
                execution_id=execution_id,
                reported_status="unverified",
                evaluation=(
                    VisualCriterionEvaluation(
                        criterion=(
                            "Heading is visually readable."
                        ),
                        status="unsatisfied",
                        rationale=(
                            "The heading is visibly clipped."
                        ),
                        observed_details=(
                            "Right side of the heading is cut off.",
                        ),
                        evidence_step_id=7,
                        artifact_ids=(
                            viewport_id,
                            crop_id,
                        ),
                    )
                ),
            ),
        ),
    )

    repository = FakeRepository()

    finding_ids = await persist_visual_findings(
        test_run_id=test_run_id,
        visual_result=visual_result,
        repository=repository,
    )

    assert len(finding_ids) == 1
    assert len(repository.created) == 1

    created = repository.created[0]

    assert (
        created["category"]
        == "visual_criterion"
    )

    assert created["journey_ids"] == (
        journey_id,
    )

    evidence = created["evidence"]

    assert isinstance(
        evidence,
        tuple,
    )

    assert evidence == (
        EvidenceReference(
            artifact_id=viewport_id,
        ),
        EvidenceReference(
            artifact_id=crop_id,
        ),
    )


@pytest.mark.asyncio
async def test_satisfied_visual_result_creates_no_finding() -> None:
    """Visually satisfied criteria are not product issues."""

    test_run_id = uuid4()

    visual_result = VisualBatchEvaluationResult(
        test_run_id=test_run_id,
        evaluations=(
            JourneyVisualEvaluation(
                journey_id=uuid4(),
                execution_id=uuid4(),
                reported_status="unverified",
                evaluation=(
                    VisualCriterionEvaluation(
                        criterion="Heading is readable.",
                        status="satisfied",
                        rationale=(
                            "The heading is clearly readable."
                        ),
                        observed_details=(),
                        evidence_step_id=7,
                        artifact_ids=(
                            uuid4(),
                        ),
                    )
                ),
            ),
        ),
    )

    repository = FakeRepository()

    finding_ids = await persist_visual_findings(
        test_run_id=test_run_id,
        visual_result=visual_result,
        repository=repository,
    )

    assert finding_ids == ()
    assert repository.created == []