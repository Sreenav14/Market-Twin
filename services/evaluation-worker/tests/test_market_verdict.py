import pytest
from markettwin_evaluation_worker.market_verdict import market_verdict


@pytest.mark.parametrize(
    "executed,approved,personas,severities,means,expected",
    [(2, 5, 3, [], {}, "insufficient_evidence"),
     (3, 5, 2, [], {"expert": 4}, "ready"),
     (5, 5, 1, ["critical"], {}, "insufficient_evidence"),
     (5, 5, 3, ["high"], {}, "not_ready"),
     (5, 5, 3, ["medium"], {}, "ready_with_issues"),
     (5, 5, 3, [], {"novice": 2.9}, "ready_with_issues"),
     (0, 0, 0, [], {}, "insufficient_evidence")],
)
def test_market_verdict_order_and_coverage_boundary(
    executed, approved, personas, severities, means, expected,
):
    result = market_verdict(
        journeys_executed=executed, journeys_approved=approved,
        personas_completed=personas, confirmed_severities=severities, persona_means=means,
    )
    assert result.verdict == expected
    assert result.journeys_executed == executed
    assert result.journeys_approved == approved
    assert result.confirmed_defects == len(severities)
