"""Probe stability (doc 24 section 4.1, W4-P5-13): the section 2.3
additions are additive only — every pre-existing probe field keeps
its name, shape, and value on a fixed page, and measure_state over a
v1-shaped probe (no new keys at all) behaves exactly as before.
"""

import pytest
from playwright.async_api import async_playwright

from markettwin_execution_orchestrator.slop.measure import measure_state
from markettwin_execution_orchestrator.slop.probe import PROBE_SCRIPT

_PAGE = """<!doctype html><html lang="en"><head><title>Fixture</title>
<style>body { font-family: Inter, sans-serif; }</style></head>
<body>
<button id="buy" style="font-size: 20px; width: 120px; height: 40px;">
Buy now</button>
<p style="font-size: 16px;">A short paragraph of real copy.</p>
<img src="https://cdn.example.test/hero.png" alt="Hero"
     width="400" height="200">
</body></html>"""

_V1_ELEMENT_KEYS = {
    "key", "kind", "tag", "role", "name", "text", "x", "y", "width",
    "height", "font_size", "font_weight", "font_family", "color",
    "background", "border_radius", "padding", "disabled", "selected",
    "expanded", "invalid", "region",
}
_V1_IMAGE_KEYS = {
    "key", "src", "alt", "natural_width", "natural_height", "complete",
    "width", "height",
}
_V1_PAGE_KEYS = {
    "url", "title", "lang", "scroll_width", "client_width", "words",
    "elements", "images",
}


@pytest.mark.asyncio
async def test_probe_v1_fields_are_identical() -> None:
    """T-P5-S1: on a fixed page, every v1 field is present with its
    established value; the v2 fields arrive alongside, not instead."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(
            viewport={"width": 1280, "height": 800},
        )
        await page.set_content(_PAGE)
        probe = await page.evaluate(PROBE_SCRIPT)
        await browser.close()
    assert _V1_PAGE_KEYS <= set(probe)
    assert probe["title"] == "Fixture"
    assert probe["lang"] == "en"
    button = next(e for e in probe["elements"] if e["name"] == "Buy now")
    assert _V1_ELEMENT_KEYS <= set(button)
    assert button["kind"] == "interactive"
    assert button["role"] == "button"
    assert button["font_size"] == 20
    assert button["width"] == 120 and button["height"] == 40
    assert button["disabled"] is False
    image = probe["images"][0]
    assert _V1_IMAGE_KEYS <= set(image)
    assert image["alt"] == "Hero"
    # The v2 additions exist alongside.
    assert "document_background" in probe
    assert "letter_spacing" in button
    assert "parent_key" in button
    assert "object_fit" in image


def test_measure_accepts_a_v1_shaped_probe() -> None:
    """T-P5-S1: a probe dict with none of the new keys measures
    without error and fires no v2-only code."""
    element = {
        "key": 0, "kind": "text", "tag": "p", "role": "p", "name": "",
        "text": "Lorem ipsum dolor sit amet", "x": 0, "y": 0,
        "width": 200, "height": 20, "font_size": 16, "font_weight": 400,
        "font_family": "Inter, sans-serif", "color": "rgb(20, 20, 20)",
        "background": "rgb(255, 255, 255)", "border_radius": "0px",
        "padding": "0px", "disabled": False, "selected": None,
        "expanded": None, "invalid": None, "region": "body",
    }
    probe = {
        "url": "https://app.example.test/", "title": "App", "lang": "en",
        "scroll_width": 1280, "client_width": 1280, "words": 60,
        "elements": [element], "images": [],
    }
    state = measure_state(probe)
    record = state["elements"][0]
    codes = [entry["rule_id"] for entry in record["rules_fired"]]
    assert codes == ["SLOP_PLACEHOLDER_TEXT"]
    assert record["verdict"] == "slop"
