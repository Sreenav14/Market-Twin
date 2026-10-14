"""Deterministic evaluation of persisted MarketTwin Journey results."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
    EvidenceReference,
    JourneyResultRecord,
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


@dataclass(frozen=True, slots=True)
class CrossJourneyFindingDraft:
    """Unverified claim repeated across multiple synthetic personas."""

    severity: str
    category: str
    title: str
    summary: str
    recommendation: str
    criterion: str

    journey_ids: tuple[UUID, ...]
    execution_ids: tuple[UUID, ...]


def _text(
    payload: dict[str, object],
    key: str,
) -> str | None:
    value = payload.get(key)

    if not isinstance(value, str):
        return None

    value = value.strip()

    return value or None


def _normalize_issue_text(
    value: str,
) -> str:
    """Normalize text without applying semantic interpretation."""

    return " ".join(
        value.split()
    ).casefold()


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
        parts.append(
            "The Journey did not produce additional "
            "descriptive details."
        )

    return "Agent-reported details; not a verified product defect.\n" + "\n".join(parts)


def _reported_step_ids(
    payload: dict[str, object],
    criterion: str | None = None,
) -> tuple[int, ...]:
    """Extract exact cited steps, without inferring evidence from execution recency."""
    entries: list[object] = []
    for key in ("criterion_evidence", "reported_criterion_evidence"):
        raw_entries = payload.get(key)
        if isinstance(raw_entries, list):
            entries.extend(cast(list[object], raw_entries))
    step_ids: list[int] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        item = cast(dict[str, object], entry)
        text = item.get("criterion")
        if item.get("status") not in {"unsatisfied", "unverified"}:
            continue
        if criterion is not None and (
            not isinstance(text, str)
            or _normalize_issue_text(text) != _normalize_issue_text(criterion)
        ):
            continue
        references = item.get("evidence_step_ids")
        if isinstance(references, list):
            step_ids.extend(value for value in cast(list[object], references)
                            if type(value) is int and value > 0)
    return tuple(dict.fromkeys(step_ids))


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
                "Agent reported journey failure: "
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
                "Agent reported partial completion: "
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


def build_cross_journey_findings(
    journey_results: tuple[
        JourneyResultRecord,
        ...,
    ],
) -> tuple[CrossJourneyFindingDraft, ...]:
    """Find the same unmet criterion across personas."""

    total_by_mission: dict[UUID, int] = defaultdict(
        int
    )

    grouped: dict[
        tuple[UUID, str],
        list[JourneyResultRecord],
    ] = defaultdict(list)

    display_text: dict[
        tuple[UUID, str],
        str,
    ] = {}

    for result in journey_results:
        total_by_mission[result.mission_id] += 1

        status = _text(
            result.payload,
            "status",
        )

        outcome = _text(
            result.payload,
            "outcome",
        )
        reported_outcome = _text(result.payload, "reported_outcome") or outcome

        # Infrastructure problems and inconclusive
        # Journeys must not become product-pattern
        # findings.
        if (
            status != "completed"
            or reported_outcome not in {
                "failed",
                "partial",
            }
        ):
            continue

        criteria = _strings(
            result.payload,
            "reported_unsatisfied_criteria"
            if isinstance(result.payload.get("reported_unsatisfied_criteria"), list)
            else "unsatisfied_criteria",
        )

        # Prevent one malformed result from counting the
        # same criterion twice for one Persona.
        seen_in_journey: set[str] = set()

        for criterion in criteria:
            normalized = _normalize_issue_text(
                criterion
            )

            if (
                not normalized
                or normalized in seen_in_journey
            ):
                continue

            seen_in_journey.add(normalized)

            key = (
                result.mission_id,
                normalized,
            )

            grouped[key].append(result)

            display_text.setdefault(
                key,
                criterion,
            )

    findings: list[
        CrossJourneyFindingDraft
    ] = []

    for key, affected_results in grouped.items():
        mission_id, _ = key

        affected_count = len(
            affected_results
        )

        if affected_count < 2:
            continue

        total_count = total_by_mission[
            mission_id
        ]

        criterion = display_text[key]

        title_criterion = criterion

        if len(title_criterion) > 180:
            title_criterion = (
                title_criterion[:177]
                + "..."
            )

        findings.append(
            CrossJourneyFindingDraft(
                severity="info",
                category="cross_persona_pattern",
                title=(
                    "Repeated agent-reported unmet criterion: "
                    f"{title_criterion}"
                ),
                summary=(
                    f"{affected_count} of "
                    f"{total_count} personas testing "
                    "this mission reported the same "
                    "unmet success criterion: "
                    f'"{criterion}". Agreement between synthetic personas '
                    "is not independent verification. Needs verification; "
                    "this is not a confirmed product defect."
                ),
                recommendation=(
                    "Verify this criterion against the cited browser steps. "
                    "If evidence is unavailable or inconclusive, retain this "
                    "observation as unverified."
                ),
                criterion=criterion,
                journey_ids=tuple(
                    result.journey_id
                    for result
                    in affected_results
                ),
                execution_ids=tuple(
                    result.execution_id
                    for result
                    in affected_results
                ),
            )
        )

    return tuple(findings)


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
            await repository.find_reported_evidence(
                execution_id=(
                    journey_result.execution_id
                ),
                step_ids=_reported_step_ids(journey_result.payload),
            )
        )

        finding_id = await repository.create_finding(
            test_run_id=test_run_id,
            journey_id=journey_result.journey_id,
            severity=draft.severity,
            category=draft.category,
            title=draft.title,
            summary=draft.summary + (
                "\nEvidence unavailable: no valid cited execution steps were found."
                if not evidence else ""
            ),
            recommendation=draft.recommendation,
            evidence=evidence,
        )

        finding_ids.append(finding_id)

    cross_journey_findings = (
        build_cross_journey_findings(
            journey_results
        )
    )

    for draft in cross_journey_findings:
        evidence_references: list[
            EvidenceReference
        ] = []

        results_by_execution = {result.execution_id: result for result in journey_results}
        for execution_id in draft.execution_ids:
            evidence = (
                await repository.find_reported_evidence(
                    execution_id=execution_id,
                    step_ids=_reported_step_ids(
                        results_by_execution[execution_id].payload, draft.criterion,
                    ),
                )
            )

            evidence_references.extend(evidence)

        finding_id = (
            await repository.create_linked_finding(
                test_run_id=test_run_id,
                journey_ids=draft.journey_ids,
                severity=draft.severity,
                category=draft.category,
                title=draft.title,
                summary=draft.summary + (
                    "\nEvidence unavailable: no valid cited execution steps were found."
                    if not evidence_references else ""
                ),
                recommendation=(
                    draft.recommendation
                ),
                evidence=tuple(
                    evidence_references
                ),
            )
        )

        finding_ids.append(finding_id)

    # Intentionally no commit here.
    # The worker/job transaction owns commit/rollback.

    return DeterministicEvaluationResult(
        test_run_id=test_run_id,
        finding_ids=tuple(finding_ids),
    )
