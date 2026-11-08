"""Verdict = coverage + confirmed findings ONLY (U-P5-01 regression).

The pre-unification function took persona score means as verdict
inputs (a mean below 3 forced "ready_with_issues"; fewer than 2
personas forced "insufficient_evidence") — the two-track leak. These
tests pin the leak shut: the signature carries no persona parameter,
and outcomes depend on coverage and severities alone.
"""

import inspect

import pytest
from markettwin_evaluation_worker.market_verdict import market_verdict


def test_verdict_signature_has_no_persona_inputs() -> None:
    parameters = inspect.signature(market_verdict).parameters
    assert not any("persona" in name for name in parameters)


@pytest.mark.parametrize(
    "executed,approved,severities,expected",
    [(2, 5, [], "insufficient_evidence"),
     (3, 5, [], "ready"),
     (5, 5, ["critical"], "not_ready"),
     (5, 5, ["high"], "not_ready"),
     (5, 5, ["medium"], "ready_with_issues"),
     (3, 5, ["low"], "ready_with_issues"),
     (0, 0, [], "insufficient_evidence")],
)
def test_market_verdict_order_and_coverage_boundary(
    executed, approved, severities, expected,
):
    result = market_verdict(
        journeys_executed=executed, journeys_approved=approved,
        confirmed_severities=severities,
    )
    assert result.verdict == expected
    assert result.journeys_executed == executed
    assert result.journeys_approved == approved
    assert result.confirmed_defects == len(severities)
    assert not hasattr(result, "persona_means")
