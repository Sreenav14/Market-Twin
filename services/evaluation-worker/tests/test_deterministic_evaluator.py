from uuid import uuid4

from markettwin_evaluation_worker.deterministic_evaluator import (
    build_cross_journey_findings,
    build_deterministic_finding,
)
from markettwin_evaluation_worker.persistence.evaluation_repository import (
    JourneyResultRecord,
)


def test_passed_journey_creates_no_finding() -> None:
    draft = build_deterministic_finding(
        {
            "journey_key": "buyer__checkout",
            "status": "completed",
            "outcome": "passed",
            "summary": "Checkout completed.",
        }
    )

    assert draft is None


def test_failed_journey_creates_high_severity_finding() -> None:
    draft = build_deterministic_finding(
        {
            "journey_key": "buyer__checkout",
            "status": "completed",
            "outcome": "failed",
            "summary": "Could not finish checkout.",
            "blockers": [
                "Continue button remained disabled."
            ],
            "friction_points": [],
            "unsatisfied_criteria": [
                "Order confirmation was not reached."
            ],
        }
    )

    assert draft is not None
    assert draft.severity == "high"
    assert draft.category == "journey_outcome"
    assert "Continue button remained disabled." in (
        draft.summary
    )


def test_policy_block_is_not_called_product_failure() -> None:
    draft = build_deterministic_finding(
        {
            "journey_key": "buyer__checkout",
            "status": "policy_blocked",
            "outcome": None,
            "summary": "Action was blocked.",
        }
    )

    assert draft is not None
    assert draft.category == "policy"
    assert draft.severity == "medium"


def test_repeated_unsatisfied_criterion_is_aggregated() -> None:
    mission_id = uuid4()

    journey_a = uuid4()
    journey_b = uuid4()
    journey_c = uuid4()

    results = (
        JourneyResultRecord(
            journey_id=journey_a,
            persona_id=uuid4(),
            mission_id=mission_id,
            execution_id=uuid4(),
            payload={
                "status": "completed",
                "outcome": "failed",
                "unsatisfied_criteria": [
                    "Order confirmation was displayed."
                ],
            },
        ),
        JourneyResultRecord(
            journey_id=journey_b,
            persona_id=uuid4(),
            mission_id=mission_id,
            execution_id=uuid4(),
            payload={
                "status": "completed",
                "outcome": "partial",
                "unsatisfied_criteria": [
                    "  order confirmation WAS displayed. "
                ],
            },
        ),
        JourneyResultRecord(
            journey_id=journey_c,
            persona_id=uuid4(),
            mission_id=mission_id,
            execution_id=uuid4(),
            payload={
                "status": "completed",
                "outcome": "passed",
                "unsatisfied_criteria": [],
            },
        ),
    )

    findings = build_cross_journey_findings(
        results
    )

    assert len(findings) == 1

    finding = findings[0]

    assert finding.severity == "medium"
    assert (
        finding.category
        == "cross_persona_pattern"
    )
    assert set(finding.journey_ids) == {
        journey_a,
        journey_b,
    }
    assert "2 of 3 personas" in finding.summary


def test_all_personas_reproducing_issue_is_high_severity() -> None:
    mission_id = uuid4()

    results = tuple(
        JourneyResultRecord(
            journey_id=uuid4(),
            persona_id=uuid4(),
            mission_id=mission_id,
            execution_id=uuid4(),
            payload={
                "status": "completed",
                "outcome": "failed",
                "unsatisfied_criteria": [
                    "Checkout completed successfully."
                ],
            },
        )
        for _ in range(3)
    )

    findings = build_cross_journey_findings(
        results
    )

    assert len(findings) == 1
    assert findings[0].severity == "high"
