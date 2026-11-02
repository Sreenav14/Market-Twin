"""Coverage and confirmed findings determine the market-readiness verdict."""

from collections.abc import Mapping, Sequence
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
    personas_completed: int
    persona_means: dict[str, float]


def market_verdict(
    *, journeys_executed: int, journeys_approved: int,
    confirmed_severities: Sequence[str], personas_completed: int,
    persona_means: Mapping[str, float],
) -> MarketVerdict:
    if not 0 <= journeys_executed <= journeys_approved or personas_completed < 0:
        raise ValueError("Coverage counts must describe actual approved journeys.")
    if any(not 1 <= mean <= 5 for mean in persona_means.values()):
        raise ValueError("Persona means must be available rubric scores between 1 and 5.")
    coverage = journeys_executed / journeys_approved if journeys_approved else 0.0
    verdict: Verdict
    if coverage < 0.6 or personas_completed < 2:
        verdict = "insufficient_evidence"
    elif any(severity in {"high", "critical"} for severity in confirmed_severities):
        verdict = "not_ready"
    elif confirmed_severities or any(mean < 3 for mean in persona_means.values()):
        verdict = "ready_with_issues"
    else:
        verdict = "ready"
    return MarketVerdict(
        verdict, journeys_executed, journeys_approved, coverage,
        len(confirmed_severities), personas_completed, dict(persona_means),
    )
