from markettwin_evaluation_worker.deterministic_evaluator import (
    build_deterministic_finding,
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