"""Run visual verification only for explicitly visual criteria."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast
from uuid import UUID

from markettwin_evaluation_worker.observability import (
    VisualInvocationRecorder,
)
from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
)
from markettwin_evaluation_worker.visual_artifact_storage import (
    VisualArtifactStorage,
)
from markettwin_evaluation_worker.visual_evaluation import (
    VisualCriterionEvaluation,
    evaluate_visual_criterion_from_evidence,
)

ReportedCriterionStatus = Literal[
    "satisfied",
    "unsatisfied",
    "unverified",
]


@dataclass(frozen=True, slots=True)
class CriterionEvidenceReference:
    """Persona-reported evidence references for one criterion."""

    criterion: str
    reported_status: ReportedCriterionStatus
    step_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class JourneyVisualEvaluation:
    """Visual verification attached to its Journey."""

    journey_id: UUID
    execution_id: UUID
    reported_status: ReportedCriterionStatus
    evaluation: VisualCriterionEvaluation


@dataclass(frozen=True, slots=True)
class VisualBatchEvaluationResult:
    """All on-demand visual checks performed for one TestRun."""

    test_run_id: UUID
    evaluations: tuple[
        JourneyVisualEvaluation,
        ...,
    ]


def _criterion_evidence(
    payload: dict[str, object],
) -> tuple[CriterionEvidenceReference, ...]:
    """Parse persisted criterion evidence from a Journey result."""

    raw_entries = payload.get(
        "criterion_evidence"
    )

    # Older TestRuns may predate criterion evidence.
    if raw_entries is None:
        return ()

    if not isinstance(raw_entries, list):
        raise RuntimeError(
            "criterion_evidence must be a list."
        )

    entries = cast(list[object], raw_entries)

    parsed: list[
        CriterionEvidenceReference
    ] = []

    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            raise RuntimeError(
                "criterion_evidence entry must be an object."
            )

        entry = cast(dict[str, object], raw_entry)

        criterion = entry.get("criterion")
        status = entry.get("status")
        raw_step_ids = entry.get(
            "evidence_step_ids"
        )

        if (
            not isinstance(criterion, str)
            or not criterion.strip()
        ):
            raise RuntimeError(
                "Criterion evidence is missing criterion text."
            )

        if status not in {
            "satisfied",
            "unsatisfied",
            "unverified",
        }:
            raise RuntimeError(
                "Criterion evidence has an invalid status."
            )

        reported_status = cast(
            ReportedCriterionStatus,
            status,
        )

        if not isinstance(raw_step_ids, list):
            raise RuntimeError(
                "Criterion evidence step IDs must be a list."
            )

        step_id_values = cast(
            list[object],
            raw_step_ids,
        )
        step_ids: list[int] = []

        for value in step_id_values:
            if (
                type(value) is not int
                or value <= 0
            ):
                raise RuntimeError(
                    "Criterion evidence contains an invalid step ID."
                )

            if value not in step_ids:
                step_ids.append(value)

        parsed.append(
            CriterionEvidenceReference(
                criterion=criterion.strip(),
                reported_status=reported_status,
                step_ids=tuple(step_ids),
            )
        )

    return tuple(parsed)


async def evaluate_visual_criteria_for_run(
    *,
    test_run_id: UUID,
    repository: EvaluationRepository,
    storage: VisualArtifactStorage,
    invocation_recorder: VisualInvocationRecorder | None = None,
) -> VisualBatchEvaluationResult:
    """Run vision only where the Journey explicitly requested it."""

    journey_results = (
        await repository.list_journey_results(
            test_run_id=test_run_id,
        )
    )

    evaluations: list[
        JourneyVisualEvaluation
    ] = []

    for journey in journey_results:
        for reference in _criterion_evidence(
            journey.payload
        ):
            if not reference.step_ids:
                continue

            evidence = (
                await repository.list_visual_evidence(
                    execution_id=(
                        journey.execution_id
                    ),
                    step_ids=reference.step_ids,
                )
            )

            explicit_visual_evidence = tuple(
                item
                for item in evidence
                if (
                    item
                    .explicitly_requests_visual_verification
                )
            )

            # Semantic-only criterion.
            # No VLM call is needed.
            if not explicit_visual_evidence:
                continue

            if invocation_recorder is None:
                evaluation = (
                    await evaluate_visual_criterion_from_evidence(
                        criterion=reference.criterion,
                        evidence=explicit_visual_evidence,
                        storage=storage,
                    )
                )
            else:
                scoped_recorder = invocation_recorder.scoped(
                    journey_id=journey.journey_id,
                    execution_id=journey.execution_id,
                )
                evaluation = (
                    await evaluate_visual_criterion_from_evidence(
                        criterion=reference.criterion,
                        evidence=explicit_visual_evidence,
                        storage=storage,
                        invocation_recorder=scoped_recorder,
                    )
                )

            evaluations.append(
                JourneyVisualEvaluation(
                    journey_id=journey.journey_id,
                    execution_id=(
                        journey.execution_id
                    ),
                    reported_status=(
                        reference.reported_status
                    ),
                    evaluation=evaluation,
                )
            )

    return VisualBatchEvaluationResult(
        test_run_id=test_run_id,
        evaluations=tuple(evaluations),
    )