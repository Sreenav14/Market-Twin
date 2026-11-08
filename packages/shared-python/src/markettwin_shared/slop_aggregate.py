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

_CATALOGUE: dict[str, Any] | None = None


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
    for state in states:
        page_signals.extend(state.get("page_signals", []))
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
            if verdict == "slop":
                severe += 1
            elif verdict == "slop_minor":
                minor += 1
            elif verdict == "clean":
                clean += 1
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
    }


def defect_family(states: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-rule defect counts from state js_errors + defect signals."""

    rules = catalogue_rules()
    per_rule: dict[str, dict[str, Any]] = {}
    serious = 0
    minor = 0
    for state in states:
        for error in state.get("js_errors", []):
            rule_id = str(error.get("rule_id", ""))
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
            entry["occurrences"] += int(error.get("count", 1))
            entry["pages"].add(state.get("url", ""))
            if severity == "serious":
                serious += int(error.get("count", 1))
            else:
                minor += int(error.get("count", 1))
    return {
        "serious": serious,
        "minor": minor,
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
