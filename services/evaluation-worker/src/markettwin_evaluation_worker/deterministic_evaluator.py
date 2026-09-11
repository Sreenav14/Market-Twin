"""Deterministic evaluation of persisted MarketTwin Journey results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
)


@dataclass(frozen=True, slots=True)
class DeterministicFindingDraft:
    """Finding produced without LLM interpretation."""

    severity: str
    category: str
    title: str
    summary: str
    recommendation: str


@dataclass(frozen=True, slots=True)
class DeterministicEvaluationResult:
    """Result of deterministic evaluation for one TestRun."""

    test_run_id: UUID
    finding_ids: tuple[UUID, ...]

    @property
    def finding_count(self) -> int:
        return len(self.finding_ids)


def _text(
    payload: dict[str, object],
    key: str,
) -> str | None:
    value = payload.get(key)

    if not isinstance(value, str):
        return None

    value = value.strip()

    return value or None


def _strings(
    payload: dict[str, object],
    key: str,
) -> tuple[str, ...]:
    value = payload.get(key)

    if not isinstance(value, list):
        return ()

    items = cast(list[object], value)

    return tuple(
        item.strip()
        for item in items
        if isinstance(item, str) and item.strip()
    )


def _journey_summary(
    payload: dict[str, object],
) -> str:
    parts: list[str] = []

    summary = _text(payload, "summary")

    if summary:
        parts.append(summary)

    blockers = _strings(
        payload,
        "blockers",
    )

    if blockers:
        parts.append(
            "Blockers: "
            + "; ".join(blockers)
        )

    friction_points = _strings(
        payload,
        "friction_points",
    )

    if friction_points:
        parts.append(
            "Friction: "
            + "; ".join(friction_points)
        )

    unsatisfied = _strings(
        payload,
        "unsatisfied_criteria",
    )

    if unsatisfied:
        parts.append(
            "Unsatisfied criteria: "
            + "; ".join(unsatisfied)
        )

    if not parts:
        return (
            "The Journey did not produce additional "
            "descriptive details."
        )

    return "\n".join(parts)


def build_deterministic_finding(
    payload: dict[str, object],
) -> DeterministicFindingDraft | None:
    """Convert one Journey result into a deterministic finding."""

    status = _text(payload, "status")
    outcome = _text(payload, "outcome")
    journey_key = (
        _text(payload, "journey_key")
        or "unknown_journey"
    )

    # Infrastructure / policy result.
    if status != "completed":
        if status == "policy_blocked":
            return DeterministicFindingDraft(
                severity="medium",
                category="policy",
                title=(
                    "Journey blocked by policy: "
                    f"{journey_key}"
                ),
                summary=_journey_summary(payload),
                recommendation=(
                    "Review whether the mission requires "
                    "an action prohibited by the current "
                    "target or safety policy. Do not relax "
                    "policy without explicit authorization."
                ),
            )

        if status == "timed_out":
            return DeterministicFindingDraft(
                severity="high",
                category="execution_reliability",
                title=(
                    "Journey timed out: "
                    f"{journey_key}"
                ),
                summary=_journey_summary(payload),
                recommendation=(
                    "Inspect the linked browser trajectory "
                    "to determine whether the product flow "
                    "or the configured runtime limit caused "
                    "the timeout."
                ),
            )

        return DeterministicFindingDraft(
            severity="high",
            category="execution_reliability",
            title=(
                "Journey execution failed: "
                f"{journey_key}"
            ),
            summary=_journey_summary(payload),
            recommendation=(
                "Inspect the linked execution evidence and "
                "separate product-flow failure from "
                "MarketTwin runtime failure before acting "
                "on this result."
            ),
        )

    # Completed and successful = no problem Finding.
    if outcome == "passed":
        return None

    if outcome == "failed":
        return DeterministicFindingDraft(
            severity="high",
            category="journey_outcome",
            title=(
                "Journey failed: "
                f"{journey_key}"
            ),
            summary=_journey_summary(payload),
            recommendation=(
                "Review the listed blockers and "
                "unsatisfied success criteria together "
                "with the linked browser evidence."
            ),
        )

    if outcome == "partial":
        return DeterministicFindingDraft(
            severity="medium",
            category="journey_outcome",
            title=(
                "Journey only partially completed: "
                f"{journey_key}"
            ),
            summary=_journey_summary(payload),
            recommendation=(
                "Review the friction points and incomplete "
                "success criteria to identify what "
                "prevented full Journey completion."
            ),
        )

    if outcome == "inconclusive":
        return DeterministicFindingDraft(
            severity="info",
            category="journey_outcome",
            title=(
                "Journey result was inconclusive: "
                f"{journey_key}"
            ),
            summary=_journey_summary(payload),
            recommendation=(
                "Review the evidence and success criteria "
                "before deciding whether this Journey "
                "should be rerun or clarified."
            ),
        )

    raise RuntimeError(
        "Completed Journey has an invalid or missing "
        f'outcome: "{outcome}".'
    )


async def evaluate_completed_run(
    *,
    test_run_id: UUID,
    session: AsyncSession,
) -> DeterministicEvaluationResult:
    """Evaluate one completed TestRun without using an LLM."""

    repository = EvaluationRepository(session)

    await repository.validate_run_ready(
        test_run_id=test_run_id,
    )

    journey_results = (
        await repository.list_journey_results(
            test_run_id=test_run_id,
        )
    )

    finding_ids: list[UUID] = []

    for journey_result in journey_results:
        draft = build_deterministic_finding(
            journey_result.payload
        )

        if draft is None:
            continue

        evidence = (
            await repository.find_preferred_evidence(
                execution_id=(
                    journey_result.execution_id
                ),
            )
        )

        finding_id = await repository.create_finding(
            test_run_id=test_run_id,
            journey_id=journey_result.journey_id,
            severity=draft.severity,
            category=draft.category,
            title=draft.title,
            summary=draft.summary,
            recommendation=draft.recommendation,
            evidence=evidence,
        )

        finding_ids.append(finding_id)

    # Intentionally no commit here.
    # The worker/job transaction owns commit/rollback.

    return DeterministicEvaluationResult(
        test_run_id=test_run_id,
        finding_ids=tuple(finding_ids),
    )