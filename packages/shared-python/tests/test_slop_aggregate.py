"""U-P6-02: the aggregate reproduces the canonical example exactly
and keeps the three families in their own currencies."""

from markettwin_shared.slop_aggregate import (
    aggregate_run,
    defect_family,
    slop_family,
)


def _elements(judged: int, severe: int, minor: int, cant_tell: int) -> list[dict]:
    elements = (
        [{"verdict": "slop"}] * severe
        + [{"verdict": "slop_minor"}] * minor
        + [{"verdict": "clean"}] * (judged - severe - minor)
        + [{"verdict": "cant_tell"}] * cant_tell
    )
    return elements


def test_canonical_thread_and_co_example_is_5_point_8() -> None:
    # Catalogue worked example: J=112, S=2, M=9, C=101, U=8.
    states = [{"url": "https://thread.example/", "elements": _elements(112, 2, 9, 8)}]
    result = slop_family(states)
    assert result["judged"] == 112
    assert result["severe"] == 2
    assert result["minor"] == 9
    assert result["cant_tell"] == 8
    assert result["percentage"] == 5.8
    assert result["headline"] == "5.8%"


def test_percentage_is_suppressed_below_coverage() -> None:
    states = [{"url": "u", "elements": _elements(40, 4, 4, 60)}]
    result = slop_family(states)
    assert result["percentage"] is None
    assert result["headline"] == "Can't tell"


def test_insufficient_coverage_band() -> None:
    states = [{"url": "u", "elements": _elements(60, 4, 4, 40)}]
    result = slop_family(states)
    assert result["percentage"] is None
    assert result["headline"] == "Insufficient coverage"


def test_js_errors_land_in_defects_never_in_slop() -> None:
    states = [{
        "url": "https://app.example/",
        "elements": _elements(10, 0, 0, 0),
        "js_errors": [
            {"rule_id": "DEF_JS_UNCAUGHT", "severity": "serious", "count": 1},
            {"rule_id": "DEF_JS_CONSOLE_ERROR", "severity": "minor", "count": 2},
        ],
    }]
    result = aggregate_run(states)
    assert result["slop"]["percentage"] == 0.0
    assert result["defects"]["serious"] == 1
    assert result["defects"]["minor"] == 2
    assert result["effort"]["value"] is None


def test_defect_totals_use_each_errors_own_severity_in_any_order() -> None:
    # Audit fix: the same rule arrives serious where it reproduced
    # and minor where it did not; the totals must not depend on
    # which page is aggregated first.
    serious_state = {
        "url": "https://app.example/a",
        "js_errors": [
            {"rule_id": "DEF_JS_CONSOLE_ERROR", "severity": "serious", "count": 1},
        ],
    }
    minor_state = {
        "url": "https://app.example/b",
        "js_errors": [
            {"rule_id": "DEF_JS_CONSOLE_ERROR", "severity": "minor", "count": 1},
        ],
    }
    for states in ([serious_state, minor_state], [minor_state, serious_state]):
        result = defect_family(states)
        assert result["serious"] == 1
        assert result["minor"] == 1
        assert result["per_rule"][0]["severity"] == "serious"
        assert result["per_rule"][0]["occurrences"] == 2


def test_defect_severity_falls_back_to_the_catalogue() -> None:
    states = [{
        "url": "https://app.example/",
        "js_errors": [{"rule_id": "DEF_JS_UNCAUGHT", "count": 1}],
    }]
    result = defect_family(states)
    assert result["serious"] == 1
    assert result["minor"] == 0


def test_unrecognized_verdict_counts_as_cant_tell() -> None:
    states = [{
        "url": "u",
        "elements": [{"verdict": "clean"}, {"verdict": "unmeasurable-ish"}],
    }]
    result = slop_family(states)
    assert result["judged"] == 1
    assert result["cant_tell"] == 1
