"""Slop tier table + gate consistency (doc 24 sections 4.4/4.3/6.4,
W4-P5-14/17): the catalogue's own assignments are the tier table;
the aggregator re-derives the flag gate from recorded tells and
surfaces — never hides — a verdict the tells cannot justify.
"""

from markettwin_shared.slop_aggregate import load_catalogue, slop_family
from markettwin_shared.slop_tiers import (
    bundle_constituted,
    is_bundle_constituted,
    severe_codes,
    tier_of,
    tier_weight,
)


def _element(verdict, fired, *, area=100.0):
    return {
        "element_id": "e0", "verdict": verdict,
        "rules_fired": fired, "area": area,
    }


def test_every_catalogue_code_is_classified_exactly_once() -> None:
    """T-P5-S9: every DET slop code has exactly the catalogue's tier;
    VIS/HYB codes carry none; the bundle and severe sets match the
    catalogue's own gate data."""
    catalogue = load_catalogue()
    for rule in catalogue["rules"]:
        if rule.get("family") != "slop":
            continue
        if rule.get("spec_class") == "DET":
            assert tier_of(rule["id"]) == rule["tier"], rule["id"]
            assert tier_of(rule["id"][5:]) == rule["tier"], rule["id"]
        else:
            assert tier_of(rule["id"]) is None, rule["id"]
    assert bundle_constituted() == {
        code[5:] if code.startswith("SLOP_") else code
        for code in catalogue["flag_gate"]["bundle_constituted_set"]
    }
    assert severe_codes() == {
        "CLIPPED_CONTROL_LABEL",
        "PLACEHOLDER_TEXT", "DEAD_END", "BROKEN_MEDIA",
        "VIEWPORT_INTEGRITY", "FABRICATED_PROOF",
    }
    assert is_bundle_constituted("SLOP_CARD_GRID")
    assert not is_bundle_constituted("SLOP_CONTRAST")
    assert tier_weight("strong") == 1.0
    assert tier_weight("moderate") == 0.6
    assert tier_weight("weak") == 0.3


def test_conditional_tier_assignments() -> None:
    """T-P5-S9 (conditionals): the three prose assignments in the
    catalogue, applied in tier_of and nowhere else."""
    assert tier_of("GRADIENT_SIGNATURE") == "strong"
    assert tier_of("GRADIENT_SIGNATURE", brand_offset=True) is None
    assert tier_of("TEMPLATE_CHROME") == "moderate"
    assert tier_of("TEMPLATE_CHROME", eyebrow_sections=3) == "strong"
    assert tier_of("GENERIC_PHRASES") == "weak"
    assert (
        tier_of("GENERIC_PHRASES", generic_phrase_viewport_distinct=3)
        == "moderate"
    )


def test_canonical_thread_and_co_aggregates_clean() -> None:
    """T-P5-S12: the canonical verdict table (J=112, S=2, M=9) still
    aggregates to 5.8%, with gate-consistent tells, no provenance
    errors, and the section 6.4 secondary computed from tier loads."""
    elements = []
    for _ in range(2):
        elements.append(_element("slop", [
            {"rule_id": "SLOP_PLACEHOLDER_TEXT", "severity": "severe"},
        ]))
    for _ in range(9):
        elements.append(_element("slop_minor", [
            {"rule_id": "SLOP_GRADIENT_SIGNATURE", "severity": "minor"},
        ]))
    for _ in range(101):
        elements.append(_element("clean", []))
    result = slop_family([{
        "url": "https://thread.example.test/", "elements": elements,
        "page_signals": [], "tier_context": {},
    }])
    assert result["percentage"] == 5.8
    assert result["judged"] == 112
    assert result["provenance_errors"] == []
    # Every flagged element's load is 1.0 (strong tells); each prom is
    # 1/112 of the page, so the page score is 100 * 11/112.
    assert result["prominence_secondary"] == round(100 * 11 / 112, 4)


def test_gate_inconsistent_verdicts_surface_as_provenance_errors() -> None:
    """T-P5-S12: a slop_minor whose only tell is one weak phrase, and
    a slop with no severe tell, are provenance errors — surfaced in
    the result while the counted numbers stay exactly as recorded."""
    elements = [
        _element("slop_minor", [
            {"rule_id": "SLOP_GENERIC_PHRASES", "severity": "minor"},
        ]),
        _element("slop", [
            {"rule_id": "SLOP_CONTRAST", "severity": "minor"},
        ]),
        _element("clean", []),
    ]
    result = slop_family([{
        "url": "https://x.example.test/", "elements": elements,
        "page_signals": [], "tier_context": {},
    }])
    problems = {entry["problem"] for entry in result["provenance_errors"]}
    assert problems == {"slop_minor_gate_unmet", "slop_without_severe_tell"}
    assert result["minor"] == 1 and result["severe"] == 1


def test_bundle_code_alone_satisfies_the_gate() -> None:
    """T-P5-S12 (bundle arm): one verified bundle-constituted tell
    justifies a slop_minor on its own."""
    elements = [
        _element("slop_minor", [
            {"rule_id": "SLOP_CARD_GRID", "severity": "minor"},
        ]),
        _element("clean", []),
    ]
    result = slop_family([{
        "url": "https://x.example.test/", "elements": elements,
        "page_signals": [], "tier_context": {},
    }])
    assert result["provenance_errors"] == []


def test_offset_tells_do_not_count_toward_the_gate() -> None:
    """T-P5-S12 (offsets): two minor tells, both offset, cannot
    justify a flag — the gate counts after offsets."""
    elements = [
        _element("slop_minor", [
            {"rule_id": "SLOP_GRADIENT_SIGNATURE", "severity": "minor",
             "offset_reason": "brand_token"},
            {"rule_id": "SLOP_SIDE_TAB_BORDER", "severity": "minor",
             "offset_reason": "brand_token"},
        ]),
        _element("clean", []),
    ]
    result = slop_family([{
        "url": "https://x.example.test/", "elements": elements,
        "page_signals": [], "tier_context": {},
    }])
    assert [e["problem"] for e in result["provenance_errors"]] == [
        "slop_minor_gate_unmet",
    ]
