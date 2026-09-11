from typing import cast
from uuid import uuid4

from markettwin_evaluation_worker.persistence.evaluation_repository import (
    JourneyResultRecord,
)
from markettwin_evaluation_worker.persistence.report_repository import (
    ReportFindingRecord,
)
from markettwin_evaluation_worker.report_generator import (
    build_report_payload,
)


def _journey(
    *,
    outcome: str,
) -> JourneyResultRecord:
    return JourneyResultRecord(
        journey_id=uuid4(),
        persona_id=uuid4(),
        mission_id=uuid4(),
        execution_id=uuid4(),
        payload={
            "status": "completed",
            "outcome": outcome,
        },
    )


def test_report_counts_journey_outcomes() -> None:
    test_run_id = uuid4()

    summary, payload = build_report_payload(
        test_run_id=test_run_id,
        journey_results=(
            _journey(outcome="passed"),
            _journey(outcome="passed"),
            _journey(outcome="failed"),
        ),
        findings=(),
    )

    journeys = payload["journeys"]

    assert isinstance(journeys, dict)

    assert journeys["total"] == 3

    assert journeys["outcome_counts"] == {
        "failed": 1,
        "passed": 2,
    }

    assert "2 passed" in summary


def test_report_orders_high_severity_first() -> None:
    test_run_id = uuid4()

    low = ReportFindingRecord(
        finding_id=uuid4(),
        severity="low",
        category="usability",
        title="Minor friction",
        summary="Minor issue.",
        recommendation="Improve copy.",
        journey_ids=(uuid4(),),
    )

    high = ReportFindingRecord(
        finding_id=uuid4(),
        severity="high",
        category="journey_outcome",
        title="Checkout failed",
        summary="Checkout could not finish.",
        recommendation="Inspect checkout.",
        journey_ids=(
            uuid4(),
            uuid4(),
        ),
    )

    _, payload = build_report_payload(
        test_run_id=test_run_id,
        journey_results=(
            _journey(outcome="failed"),
        ),
        findings=(
            low,
            high,
        ),
    )

    findings = payload["findings"]

    assert isinstance(findings, dict)

    items = cast(list[object], findings["items"])

    assert isinstance(items, list)

    first = cast(dict[str, object], items[0])

    assert isinstance(first, dict)
    assert first["severity"] == "high"
    assert first["affected_journey_count"] == 2


def test_clean_run_report_has_no_findings() -> None:
    summary, payload = build_report_payload(
        test_run_id=uuid4(),
        journey_results=(
            _journey(outcome="passed"),
            _journey(outcome="passed"),
            _journey(outcome="passed"),
        ),
        findings=(),
    )

    findings = payload["findings"]

    assert isinstance(findings, dict)
    assert findings["total"] == 0

    assert (
        "No evidence-backed issue findings"
        in summary
    )