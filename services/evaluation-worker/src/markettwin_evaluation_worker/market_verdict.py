"""Coverage and confirmed findings determine the market-readiness verdict.

Persona impressions are deliberately NOT an input (U-P5-01): feelings
are reported as anchored quotes in their own band and can never move
a verdict — the two-track rule. This function's signature is the
enforcement: there is no persona parameter to pass.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Verdict = Literal["ready", "ready_with_issues", "not_ready", "insufficient_evidence"]


@dataclass(frozen=True)
class MarketVerdict:
    verdict: Verdict
    journeys_executed: int
    journeys_approved: int
    coverage: float
    confirmed_defects: int


def market_verdict(
    *, journeys_executed: int, journeys_approved: int,
    confirmed_severities: Sequence[str],
) -> MarketVerdict:
    if not 0 <= journeys_executed <= journeys_approved:
        raise ValueError("Coverage counts must describe actual approved journeys.")
    coverage = journeys_executed / journeys_approved if journeys_approved else 0.0
    verdict: Verdict
    if coverage < 0.6:
        verdict = "insufficient_evidence"
    elif any(severity in {"high", "critical"} for severity in confirmed_severities):
        verdict = "not_ready"
    elif confirmed_severities:
        verdict = "ready_with_issues"
    else:
        verdict = "ready"
    return MarketVerdict(
        verdict, journeys_executed, journeys_approved, coverage,
        len(confirmed_severities),
    )
