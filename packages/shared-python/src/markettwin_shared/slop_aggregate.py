"""Three-family aggregation for Slop runs (U-P6-02).

Pure math over a verdict table — the same semantics as the
ui-quality skill's aggregate.py, ported into the product:

- slop: per-element verdicts (clean / slop_minor / slop / cant_tell)
  derive the headline percentage 100 * (2S + M) / (2J), shown only
  when coverage >= 0.80 and the undecided weight <= 0.10; page-level
  signals roll up OUTSIDE the percentage.
- inefficiency: performed-task effort ratios; with no performed
  tasks the family reports None with the reason (never a fake 0).
- defect: per-rule fail counts with severities; JS errors live here
  and never enter the slop percentage.

The numbers are always derived from counted verdicts. No caller may
supply a percentage.
"""

import json
from decimal import ROUND_HALF_UP, Decimal
from importlib import resources
from typing import Any

from markettwin_shared.slop_tiers import (
    bare_code,
    is_bundle_constituted,
    tier_of,
    tier_weight,
)

_CATALOGUE: dict[str, Any] | None = None
SLOP_EVALUATION_CONTRACT_VERSION = 1


def load_catalogue() -> dict[str, Any]:
    global _CATALOGUE
    if _CATALOGUE is None:
        text = (
            resources.files("markettwin_shared")
            .joinpath("slop_catalogue.json")
            .read_text(encoding="utf-8")
        )
        _CATALOGUE = json.loads(text)
    return _CATALOGUE


def catalogue_rules() -> dict[str, dict[str, Any]]:
    return {rule["id"]: rule for rule in load_catalogue()["rules"]}


def _round_half_up_1dp(value: float) -> float:
    return float(
        Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    )


def _element_load(
    element: dict[str, Any], tier_context: dict[str, Any],
) -> float:
    """Section 6.4 load for one flagged element: min(1, the sum of
    tier weights over its distinct verified non-offset tells)."""

    weights: dict[str, float] = {}
    for entry in element.get("rules_fired", []):
        if entry.get("offset_reason"):
            continue
        rule_id = str(entry.get("rule_id", ""))
        tier = tier_of(
            rule_id,
            eyebrow_sections=int(
                tier_context.get("template_chrome_eyebrow_sections", 0),
            ),
            generic_phrase_viewport_distinct=int(
                tier_context.get("generic_phrase_viewport_distinct", 0),
            ),
        )
        if tier is not None:
            weights[bare_code(rule_id)] = tier_weight(tier)
    return min(1.0, sum(weights.values()))


def _gate_problem(
    element: dict[str, Any], tier_context: dict[str, Any],
) -> str | None:
    """Re-derive the section 4.3 gate from the recorded tells. A
    flagged verdict the tells cannot justify is a provenance error."""

    verdict = element.get("verdict")
    fired = element.get("rules_fired", [])
    severe = any(entry.get("severity") == "severe" for entry in fired)
    if verdict == "slop":
        return None if severe else "slop_without_severe_tell"
    if verdict == "slop_minor":
        if severe:
            return "slop_minor_with_severe_tell"
        counting = [
            entry for entry in fired if not entry.get("offset_reason")
        ]
        gate_met = (
            any(
                tier_of(
                    str(entry.get("rule_id", "")),
                    eyebrow_sections=int(
                        tier_context.get(
                            "template_chrome_eyebrow_sections", 0,
                        ),
                    ),
                    generic_phrase_viewport_distinct=int(
                        tier_context.get(
                            "generic_phrase_viewport_distinct", 0,
                        ),
                    ),
                ) == "strong"
                for entry in counting
            )
            or any(
                is_bundle_constituted(str(entry.get("rule_id", "")))
                for entry in counting
            )
            or len({bare_code(str(entry.get("rule_id", ""))) for entry in counting}) >= 2
        )
        return None if gate_met else "slop_minor_gate_unmet"
    return None


def _provenance_error_key(
    error: dict[str, Any],
) -> tuple[str, str, str, str]:
    """Total order for provenance errors: the aggregate is a pure
    function of the verdict set, never of lane arrival order, so the
    errors are reported in one canonical order. Any field may be
    None; the key is built from strings only."""

    return (
        str(error.get("url") or ""),
        str(error.get("element_id") or ""),
        str(error.get("verdict") or ""),
        str(error.get("problem") or ""),
    )


def slop_family(states: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate element verdicts across state results.

    Each state: {"elements": [{"verdict": clean|slop|slop_minor|
    cant_tell, "area": float|None}], "page_signals": [...]}.
    """

    judged = severe = minor = clean = cant_tell = 0
    cant_tell_area = 0.0
    judged_area = 0.0
    areas_known = True
    page_signals: list[dict[str, Any]] = []
    page_scores: list[float] = []
    provenance_errors: list[dict[str, Any]] = []
    for state in states:
        page_signals.extend(state.get("page_signals", []))
        tier_context = state.get("tier_context") or {}
        state_judged_area = 0.0
        state_load = 0.0
        for element in state.get("elements", []):
            verdict = element.get("verdict")
            area = element.get("area")
            if verdict not in {"slop", "slop_minor", "clean"}:
                # "cant_tell" itself, and any unrecognized verdict: an
                # element the measurer could not classify is
                # unmeasurable, and unmeasurable counts as cant_tell —
                # never as silently judged (which would dilute the %).
                cant_tell += 1
                if area is None:
                    areas_known = False
                else:
                    cant_tell_area += float(area)
                continue
            judged += 1
            if area is None:
                areas_known = False
            else:
                judged_area += float(area)
                state_judged_area += float(area)
                if verdict in {"slop", "slop_minor"}:
                    state_load += float(area) * _element_load(
                        element, tier_context,
                    )
            if verdict in {"slop", "slop_minor"}:
                problem = _gate_problem(element, tier_context)
                if problem is not None:
                    provenance_errors.append({
                        "url": state.get("url"),
                        "element_id": element.get("element_id"),
                        "verdict": verdict,
                        "problem": problem,
                    })
            if verdict == "slop":
                severe += 1
            elif verdict == "slop_minor":
                minor += 1
            elif verdict == "clean":
                clean += 1
        if state_judged_area > 0:
            page_scores.append(100.0 * state_load / state_judged_area)
    total = judged + cant_tell
    coverage = (judged / total) if total else 0.0
    if areas_known and judged_area > 0:
        undecided_weight = cant_tell_area / (judged_area + cant_tell_area)
        undecided_basis = "area"
    else:
        undecided_weight = (cant_tell / total) if total else 0.0
        undecided_basis = "count_fallback"
    percentage: float | None = None
    headline = "Can't tell"
    if coverage >= 0.80 and undecided_weight <= 0.10:
        # judged > 0 is guaranteed here: coverage >= 0.80 with
        # judged == 0 would make coverage 0.
        percentage = _round_half_up_1dp(100 * (2 * severe + minor) / (2 * judged))
        headline = f"{percentage}%"
    elif coverage >= 0.50:
        headline = "Insufficient coverage"
    return {
        "headline": headline,
        "percentage": percentage,
        "judged": judged,
        "severe": severe,
        "minor": minor,
        "clean": clean,
        "cant_tell": cant_tell,
        "coverage": round(coverage, 4),
        "undecided_weight": round(undecided_weight, 4),
        "undecided_basis": undecided_basis,
        "page_signals": page_signals,
        "prominence_secondary": (
            round(sum(page_scores) / len(page_scores), 4)
            if page_scores else None
        ),
        "provenance_errors": sorted(
            provenance_errors, key=_provenance_error_key
        ),
    }


def defect_family(states: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-rule defect counts from state js_errors + defect signals."""

    rules = catalogue_rules()
    per_rule: dict[str, dict[str, Any]] = {}
    serious = 0
    minor = 0
    test_condition_occurrences = 0
    for state in states:
        for error in state.get("js_errors", []):
            rule_id = str(error.get("rule_id", ""))
            occurrences = int(error.get("count", 1))
            message = str(error.get("message") or "")
            if rule_id == "DEF_JS_CONSOLE_ERROR" and any(
                message.startswith(f"Failed to load resource: net::{code}")
                for code in ("ERR_BLOCKED_BY_CLIENT", "ERR_EMPTY_RESPONSE")
            ):
                test_condition_occurrences += occurrences
                continue
            # Each error counts under its OWN severity: the same rule
            # legitimately arrives serious on one page (a reproduced
            # console error) and minor on another, so totalling by the
            # first-seen severity made the headline counts depend on
            # page order. A missing severity falls back to the
            # catalogue's severity for the rule, never silently minor.
            severity = (
                error.get("severity")
                or (rules.get(rule_id) or {}).get("severity")
                or "minor"
            )
            entry = per_rule.setdefault(rule_id, {
                "rule_id": rule_id,
                "name": (rules.get(rule_id) or {}).get("name", rule_id),
                "severity": severity,
                "occurrences": 0,
                "pages": set(),
            })
            if severity == "serious":
                entry["severity"] = "serious"
            entry["occurrences"] += occurrences
            entry["pages"].add(state.get("url", ""))
            if severity == "serious":
                serious += occurrences
            else:
                minor += occurrences
    return {
        "serious": serious,
        "minor": minor,
        "test_condition_occurrences": test_condition_occurrences,
        "per_rule": [
            {**entry, "pages": sorted(entry["pages"])}
            for entry in sorted(per_rule.values(), key=lambda e: e["rule_id"])
        ],
    }


def effort_family(states: list[dict[str, Any]]) -> dict[str, Any]:
    """No performed tasks in a crawl-only run: the family reports why
    it is empty instead of inventing a ratio (aggregate.py semantics)."""

    return {
        "value": None,
        "reason": (
            "No performed tasks in this run. Effort is measured when an "
            "agent performs a task (interaction cost, first click, error "
            "recovery); a look-only crawl does not perform tasks."
        ),
    }


def aggregate_run(states: list[dict[str, Any]]) -> dict[str, Any]:
    """The three family numbers over one shared verdict table."""

    return {
        "slop": slop_family(states),
        "defects": defect_family(states),
        "effort": effort_family(states),
        "states_visited": len(states),
    }
