"""Deterministic report generation for MarketTwin."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from markettwin_shared.finding_classification import classify_finding
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
    JourneyResultRecord,
)
from markettwin_evaluation_worker.persistence.report_repository import (
    ReportFindingRecord,
    ReportRepository,
)


@dataclass(frozen=True, slots=True)
class GeneratedReportResult:
    """Persisted MarketTwin report result."""

    report_id: UUID
    test_run_id: UUID
    version: int = 1


def _text(
    payload: dict[str, object],
    key: str,
) -> str | None:
    value = payload.get(key)

    if not isinstance(value, str):
        return None

    value = value.strip()

    return value or None


def _severity_rank(
    severity: str,
) -> int:
    return {
        "critical": 5,
        "high": 4,
        "medium": 3,
        "low": 2,
        "info": 1,
    }.get(severity, 0)


def _classification(finding: ReportFindingRecord) -> tuple[str, str]:
    return classify_finding(finding.category, has_visual_evidence=finding.has_visual_evidence)


def _severity(finding: ReportFindingRecord) -> str:
    return "info" if finding.category == "cross_persona_pattern" else finding.severity


def _build_executive_summary(
    *,
    journey_results: tuple[
        JourneyResultRecord,
        ...,
    ],
    findings: tuple[
        ReportFindingRecord,
        ...,
    ],
) -> str:
    outcome_counts = Counter(
        _text(result.payload, "outcome")
        or "none"
        for result in journey_results
    )

    status_counts = Counter(
        _text(result.payload, "status")
        or "unknown"
        for result in journey_results
    )

    passed = outcome_counts["passed"]
    partial = outcome_counts["partial"]
    failed = outcome_counts["failed"]
    inconclusive = outcome_counts[
        "inconclusive"
    ]

    non_completed = sum(
        count
        for status, count
        in status_counts.items()
        if status != "completed"
    )

    parts = [
        (
            f"MarketTwin evaluated "
            f"{len(journey_results)} persona "
            "journey(s)."
        ),
        (
            f"Recorded journey outcomes: {passed} passed, "
            f"{partial} partially completed, "
            f"{failed} failed, and "
            f"{inconclusive} were inconclusive."
        ),
    ]

    if non_completed:
        parts.append(
            f"{non_completed} journey(s) ended "
            "before normal completion."
        )

    if not findings:
        parts.append(
            "No confirmed product issues were produced. "
            "This does not establish that the application is defect-free."
        )

        return " ".join(parts)

    classifications = Counter(_classification(finding)[0] for finding in findings)
    parts.append(
        f"{classifications['observed_product_issue']} visually verified product issue(s), "
        f"{classifications['not_verified']} unverified observation(s), and "
        f"{classifications['test_execution_issue']} test execution diagnostic(s)."
    )

    return " ".join(parts)


def build_report_payload(
    *,
    test_run_id: UUID,
    journey_results: tuple[
        JourneyResultRecord,
        ...,
    ],
    findings: tuple[
        ReportFindingRecord,
        ...,
    ],
    evaluation_records: tuple[dict[str, object], ...] = (),
) -> tuple[str, dict[str, object]]:
    """Build a deterministic MarketTwin report."""

    status_counts = Counter(
        _text(result.payload, "status")
        or "unknown"
        for result in journey_results
    )

    outcome_counts = Counter(
        _text(result.payload, "outcome")
        or "none"
        for result in journey_results
    )

    severity_counts = Counter(
        _severity(finding)
        for finding in findings
    )

    category_counts = Counter(
        finding.category
        for finding in findings
    )

    sorted_findings = sorted(
        findings,
        key=lambda finding: (
            -_severity_rank(
                _severity(finding)
            ),
            finding.category,
            finding.title.casefold(),
        ),
    )

    finding_items: list[
        dict[str, object]
    ] = []

    for finding in sorted_findings:
        finding_items.append(
            {
                "finding_id": str(
                    finding.finding_id
                ),
                "severity": _severity(finding),
                "category": finding.category,
                "finding_kind": _classification(finding)[0],
                "verification_status": _classification(finding)[1],
                "title": finding.title,
                "summary": finding.summary,
                "recommendation": (
                    finding.recommendation
                ),
                "journey_ids": [
                    str(journey_id)
                    for journey_id
                    in finding.journey_ids
                ],
                "affected_journey_count": len(
                    finding.journey_ids
                ),
            }
        )

    payload: dict[str, object] = {
        "schema_version": 1,
        "generator": (
            "deterministic_evaluation_v1"
        ),
        "test_run_id": str(test_run_id),
        "evaluation_records": list(evaluation_records),
        "journeys": {
            "total": len(journey_results),
            "status_counts": dict(
                sorted(status_counts.items())
            ),
            "outcome_counts": dict(
                sorted(outcome_counts.items())
            ),
        },
        "findings": {
            "total": len(findings),
            "confirmed_issue_count": sum(
                _classification(finding)[0] == "observed_product_issue"
                for finding in findings
            ),
            "unverified_observation_count": sum(
                _classification(finding)[0] == "not_verified" for finding in findings
            ),
            "execution_diagnostic_count": sum(
                _classification(finding)[0] == "test_execution_issue"
                for finding in findings
            ),
            "severity_counts": dict(
                sorted(
                    severity_counts.items()
                )
            ),
            "category_counts": dict(
                sorted(
                    category_counts.items()
                )
            ),
            "items": cast(
                list[object],
                finding_items,
            ),
        },
    }

    executive_summary = (
        _build_executive_summary(
            journey_results=journey_results,
            findings=findings,
        )
    )

    return (
        executive_summary,
        payload,
    )


async def generate_deterministic_report(
    *,
    test_run_id: UUID,
    session: AsyncSession,
    evaluation_records: tuple[dict[str, object], ...] = (),
    assessment: dict[str, object] | None = None,
) -> GeneratedReportResult:
    """Generate and persist report version 1."""

    report_repository = ReportRepository(
        session
    )

    await report_repository.validate_run_ready(
        test_run_id=test_run_id,
    )

    evaluation_repository = (
        EvaluationRepository(session)
    )

    journey_results = (
        await evaluation_repository
        .list_journey_results(
            test_run_id=test_run_id,
        )
    )

    findings = (
        await report_repository.list_findings(
            test_run_id=test_run_id,
        )
    )

    (
        executive_summary,
        report_payload,
    ) = build_report_payload(
        test_run_id=test_run_id,
        journey_results=journey_results,
        findings=findings,
        evaluation_records=evaluation_records,
    )

    if assessment is not None:
        report_payload["assessment"] = assessment

    report_id = (
        await report_repository
        .create_completed_report(
            test_run_id=test_run_id,
            executive_summary=(
                executive_summary
            ),
            report_payload=report_payload,
        )
    )

    return GeneratedReportResult(
        report_id=report_id,
        test_run_id=test_run_id,
    )
