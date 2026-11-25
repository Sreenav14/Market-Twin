"""Slop tier table (doc 24 section 4.4, W4-P5-14): the ONE home for
code -> tier, shared by the measurer (the section 4.3 flag gate) and
the aggregator (the section 6.4 prominence secondary), so the two can
never drift into different opinions of what a tell is worth.

The base table is the catalogue's own per-rule tier field — the
catalogue stays the constants source of truth. Three assignments are
conditional on page facts the catalogue states in prose; they are
applied here, in tier_of, and nowhere else:

- GRADIENT_SIGNATURE is strong only when it is not brand-offset; a
  brand-offset tell carries no tier at all (it is recorded, never
  counted), so tier_of returns None for it.
- TEMPLATE_CHROME is strong only on a page with >= 3 eyebrow
  sections; otherwise it is its catalogue tier (moderate).
- GENERIC_PHRASES escalates from weak to moderate when >= 3 distinct
  generic phrases occur in the page's first viewport.

VIS and HYB codes carry no tier (tier_of returns None): they never
create element signals and never enter a measured count.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, Literal

Tier = Literal["strong", "moderate", "weak"]

_CATALOGUE: dict[str, Any] | None = None


def _catalogue() -> dict[str, Any]:
    global _CATALOGUE
    if _CATALOGUE is None:
        text = (
            resources.files("markettwin_shared")
            .joinpath("slop_catalogue.json")
            .read_text(encoding="utf-8")
        )
        _CATALOGUE = json.loads(text)
    return _CATALOGUE


def bare_code(code: str) -> str:
    """Catalogue ids carry the SLOP_ prefix; the tier table keys the
    bare code so callers may pass either form."""

    return code[5:] if code.startswith("SLOP_") else code


def _base_tiers() -> dict[str, Tier]:
    return {
        bare_code(rule["id"]): rule["tier"]
        for rule in _catalogue()["rules"]
        if rule.get("family") == "slop" and rule.get("tier") is not None
    }


def severe_codes() -> frozenset[str]:
    """The severe slop codes (bare form): flag singly, never offset."""

    return frozenset(
        bare_code(rule["id"])
        for rule in _catalogue()["rules"]
        if rule.get("family") == "slop" and rule.get("severity") == "severe"
    )


def bundle_constituted() -> frozenset[str]:
    """Codes whose verified presence alone constitutes a bundle flag
    (catalogue flag_gate.bundle_constituted_set, bare form)."""

    return frozenset(
        bare_code(code)
        for code in _catalogue()["flag_gate"]["bundle_constituted_set"]
    )


def is_bundle_constituted(code: str) -> bool:
    return bare_code(code) in bundle_constituted()


def tier_of(
    code: str,
    *,
    brand_offset: bool = False,
    eyebrow_sections: int = 0,
    generic_phrase_viewport_distinct: int = 0,
) -> Tier | None:
    """The tier of one tell, with the catalogue's conditional
    assignments applied. None for VIS/HYB codes, unknown codes, and
    a brand-offset GRADIENT_SIGNATURE."""

    bare = bare_code(code)
    base = _base_tiers().get(bare)
    if base is None:
        return None
    if bare == "GRADIENT_SIGNATURE" and brand_offset:
        return None
    if bare == "TEMPLATE_CHROME" and eyebrow_sections >= 3:
        return "strong"
    if bare == "GENERIC_PHRASES" and generic_phrase_viewport_distinct >= 3:
        return "moderate"
    return base


def tier_weight(tier: Tier) -> float:
    """Section 6.4 load weights, read from the catalogue constants."""

    name = {
        "strong": "SLOP_TIER_WEIGHT_STRONG",
        "moderate": "SLOP_TIER_WEIGHT_MODERATE",
        "weak": "SLOP_TIER_WEIGHT_WEAK",
    }[tier]
    for constant in _catalogue()["constants"]:
        if constant["name"] == name:
            return float(constant["value"])
    return {"strong": 1.0, "moderate": 0.6, "weak": 0.3}[tier]
