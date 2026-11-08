"""Deterministic slop measurement (U-P6-04): probe data in, verdict
rows out. Pure functions over the probe dict — thresholds and data
lists come from the shared catalogue (the constants source of truth).

v1 rule set (all deterministic, all measurable from real page data):
element rules — SLOP_PLACEHOLDER_TEXT (severe), SLOP_BROKEN_MEDIA
(severe), SLOP_GENERIC_PHRASES, SLOP_CONTRAST, SLOP_EMOJI_ICONS,
SLOP_ROUND_STATS (minor); page rules (outside the percentage) —
SLOP_VIEWPORT_INTEGRITY (severe), SLOP_DEAD_END (severe),
SLOP_GENERIC_CTA (minor). An element's verdict is the worst rule it
fired (GATE-FLAG-01); elements the probe could not measure are
cant_tell, never silently clean.
"""

import re
from typing import Any

from markettwin_shared.slop_aggregate import load_catalogue

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF]"
)
_ROUND_STAT_RE = re.compile(r"^(99\.9%|100%|10x|10×|24/7)$", re.IGNORECASE)
_BIG_ROUND_RE = re.compile(r"^\d{1,3}(,\d{3})*\+?$")


def _data_lists() -> dict[str, Any]:
    return load_catalogue()["data_lists"]


def _parse_rgb(value: str) -> tuple[float, float, float] | None:
    match = re.match(
        r"rgba?\((\d+)[,\s]+(\d+)[,\s]+(\d+)", value or "",
    )
    if not match:
        return None
    return tuple(float(match.group(i)) / 255 for i in (1, 2, 3))  # type: ignore[return-value]


def _luminance(rgb: tuple[float, float, float]) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: str, background: str) -> float | None:
    """WCAG contrast ratio (catalogue formula; never rounded up)."""

    fg = _parse_rgb(foreground)
    bg = _parse_rgb(background)
    if fg is None or bg is None:
        return None
    light = max(_luminance(fg), _luminance(bg))
    dark = min(_luminance(fg), _luminance(bg))
    return (light + 0.05) / (dark + 0.05)


def _emoji_share(text: str) -> float:
    if not text:
        return 0.0
    glyphs = [ch for ch in text if not ch.isspace()]
    if not glyphs:
        return 0.0
    return sum(1 for ch in glyphs if _EMOJI_RE.match(ch)) / len(glyphs)


def measure_state(probe: dict[str, Any]) -> dict[str, Any]:
    """Judge one probed page. Returns the state verdict rows the
    evaluator aggregates: elements + page_signals."""

    lists = _data_lists()
    placeholders = [
        str(p).lower()
        for p in lists["placeholder_patterns"]["substrings"]
    ]
    generic_phrases = [
        str(p).lower() for p in lists["generic_phrases"]["phrases"]
    ]
    generic_ctas = {
        str(label).lower() for label in lists["generic_cta_labels"]["labels"]
    }
    stat_labels = [
        str(label).lower() for label in lists["generic_stat_labels"]["labels"]
    ]

    elements: list[dict[str, Any]] = []
    for element in probe.get("elements", []):
        fired: list[dict[str, str]] = []
        text = str(element.get("text") or element.get("name") or "")
        lowered = text.lower()
        if any(pattern in lowered for pattern in placeholders):
            fired.append({"rule_id": "SLOP_PLACEHOLDER_TEXT", "severity": "severe"})
        if any(phrase in lowered for phrase in generic_phrases):
            fired.append({"rule_id": "SLOP_GENERIC_PHRASES", "severity": "minor"})
        if element.get("kind") == "interactive" and _emoji_share(text) >= 0.5:
            fired.append({"rule_id": "SLOP_EMOJI_ICONS", "severity": "minor"})
        font_size = float(element.get("font_size") or 0)
        if text and font_size >= 28:
            first_token = text.split(" ")[0]
            if _ROUND_STAT_RE.match(first_token) or (
                _BIG_ROUND_RE.match(first_token)
                and int(first_token.replace(",", "").rstrip("+")) >= 10_000
            ):
                if any(label in lowered for label in stat_labels):
                    fired.append({"rule_id": "SLOP_ROUND_STATS", "severity": "minor"})
        if text and element.get("color") and element.get("background"):
            ratio = contrast_ratio(
                str(element["color"]), str(element["background"]),
            )
            large = font_size >= 24 or (
                font_size >= 18.66 and int(element.get("font_weight") or 400) >= 700
            )
            floor = 3.0 if large else 4.5
            if ratio is not None and ratio < floor:
                fired.append({"rule_id": "SLOP_CONTRAST", "severity": "minor"})
        width = int(element.get("width") or 0)
        height = int(element.get("height") or 0)
        if fired:
            verdict = (
                "slop" if any(f["severity"] == "severe" for f in fired)
                else "slop_minor"
            )
        elif width > 0 and height > 0:
            verdict = "clean"
        else:
            verdict = "cant_tell"
        elements.append({
            "element_id": f"e{element.get('key')}",
            "verdict": verdict,
            "rules_fired": fired,
            "area": float(width * height) if width > 0 and height > 0 else None,
            "label": text[:80],
        })
    for image in probe.get("images", []):
        fired = []
        if int(image.get("natural_width") or 0) == 0:
            fired.append({"rule_id": "SLOP_BROKEN_MEDIA", "severity": "severe"})
        src = str(image.get("src") or "")
        if any(domain in src for domain in
               lists["placeholder_patterns"].get("domains_in_src_or_href", [])):
            fired.append({"rule_id": "SLOP_PLACEHOLDER_TEXT", "severity": "severe"})
        width = int(image.get("width") or 0)
        height = int(image.get("height") or 0)
        elements.append({
            "element_id": f"img{image.get('key')}",
            "verdict": "slop" if fired else "clean",
            "rules_fired": fired,
            "area": float(width * height) if width > 0 and height > 0 else None,
            "label": (image.get("alt") or src)[:80],
        })

    page_signals: list[dict[str, Any]] = []
    if int(probe.get("scroll_width") or 0) > int(probe.get("client_width") or 0) + 1:
        page_signals.append({
            "rule_id": "SLOP_VIEWPORT_INTEGRITY", "severity": "severe",
            "detail": "Page overflows horizontally.",
        })
    interactive_count = sum(
        1 for e in probe.get("elements", []) if e.get("kind") == "interactive"
    )
    if interactive_count == 0 and int(probe.get("words") or 0) < 40:
        page_signals.append({
            "rule_id": "SLOP_DEAD_END", "severity": "severe",
            "detail": "No interactive elements and almost no content.",
        })
    cta_labels = [
        str(e.get("name") or "").strip().lower()
        for e in probe.get("elements", [])
        if e.get("role") in {"button", "link"} and e.get("name")
    ]
    ctas = [label for label in cta_labels if label in generic_ctas]
    if len(cta_labels) >= 3 and len(ctas) == len(cta_labels):
        page_signals.append({
            "rule_id": "SLOP_GENERIC_CTA", "severity": "minor",
            "detail": f"All {len(cta_labels)} call-to-action labels are generic.",
        })
    return {
        "url": probe.get("url"),
        "title": probe.get("title"),
        "elements": elements,
        "page_signals": page_signals,
    }


def dedupe_js_errors(
    records: list[dict[str, Any]], *, state_url: str,
) -> list[dict[str, Any]]:
    """Group structured JS records by (kind, normalised message) for
    one state visit; map kinds to the DEF_JS rules."""

    rule_by_kind = {
        "uncaught": ("DEF_JS_UNCAUGHT", "serious"),
        "unhandled_rejection": ("DEF_JS_UNHANDLED_REJECTION", "serious"),
        "console_error": ("DEF_JS_CONSOLE_ERROR", "minor"),
    }
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        kind = str(record.get("kind", ""))
        if kind not in rule_by_kind:
            continue
        message = str(record.get("message", ""))
        normalised = re.sub(r"\d+", "N", message).strip().lower()[:200]
        key = (kind, normalised)
        rule_id, severity = rule_by_kind[kind]
        entry = grouped.setdefault(key, {
            "rule_id": rule_id, "severity": severity, "kind": kind,
            "message": message[:300], "stack": record.get("stack"),
            "url": state_url, "count": 0,
        })
        entry["count"] += 1
    return list(grouped.values())
