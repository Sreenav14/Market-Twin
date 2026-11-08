"""U-P6-04: deterministic measurement over probe data."""

from markettwin_execution_orchestrator.slop.measure import (
    contrast_ratio,
    dedupe_js_errors,
    measure_state,
)


def _element(**overrides) -> dict:
    base = {
        "key": 0, "kind": "text", "tag": "p", "role": "p", "name": "",
        "text": "Real product copy.", "x": 0, "y": 0, "width": 200,
        "height": 20, "font_size": 16, "font_weight": 400,
        "font_family": "Inter", "color": "rgb(0, 0, 0)",
        "background": "rgb(255, 255, 255)",
    }
    base.update(overrides)
    return base


def _probe(**overrides) -> dict:
    base = {
        "url": "https://app.example/", "title": "App", "lang": "en",
        "scroll_width": 1280, "client_width": 1280, "words": 120,
        "elements": [], "images": [],
    }
    base.update(overrides)
    return base


def test_clean_page_acquits_every_element() -> None:
    result = measure_state(_probe(elements=[_element(), _element(key=1)]))
    assert [e["verdict"] for e in result["elements"]] == ["clean", "clean"]
    assert result["page_signals"] == []


def test_placeholder_text_fires_severe() -> None:
    result = measure_state(_probe(elements=[
        _element(text="Lorem ipsum dolor sit amet, sign up today."),
    ]))
    assert result["elements"][0]["verdict"] == "slop"
    assert result["elements"][0]["rules_fired"][0]["rule_id"] == "SLOP_PLACEHOLDER_TEXT"


def test_broken_image_fires_severe() -> None:
    result = measure_state(_probe(images=[{
        "key": 0, "src": "https://app.example/badge.png", "alt": "badge",
        "natural_width": 0, "natural_height": 0, "width": 80, "height": 20,
    }]))
    assert result["elements"][0]["verdict"] == "slop"


def test_contrast_math_and_rule() -> None:
    assert contrast_ratio("rgb(0, 0, 0)", "rgb(255, 255, 255)") == 21.0
    result = measure_state(_probe(elements=[
        _element(color="rgb(200, 200, 200)"),  # ~1.6:1 on white
    ]))
    assert result["elements"][0]["verdict"] == "slop_minor"
    assert result["elements"][0]["rules_fired"][0]["rule_id"] == "SLOP_CONTRAST"


def test_dead_end_and_overflow_are_page_signals() -> None:
    result = measure_state(_probe(words=3, scroll_width=1600, elements=[]))
    ids = {s["rule_id"] for s in result["page_signals"]}
    assert ids == {"SLOP_DEAD_END", "SLOP_VIEWPORT_INTEGRITY"}


def test_js_dedup_groups_and_maps_rules() -> None:
    records = [
        {"kind": "console_error", "message": "Failed to load chunk 123", "stack": None},
        {"kind": "console_error", "message": "Failed to load chunk 456", "stack": None},
        {"kind": "uncaught", "message": "TypeError: x is not a function", "stack": "at a"},
        {"kind": "unhandled_rejection", "message": "timeout", "stack": None},
    ]
    grouped = dedupe_js_errors(records, state_url="https://app.example/")
    by_rule = {g["rule_id"]: g for g in grouped}
    assert by_rule["DEF_JS_CONSOLE_ERROR"]["count"] == 2
    assert by_rule["DEF_JS_CONSOLE_ERROR"]["severity"] == "minor"
    assert by_rule["DEF_JS_UNCAUGHT"]["severity"] == "serious"
    assert by_rule["DEF_JS_UNHANDLED_REJECTION"]["count"] == 1
