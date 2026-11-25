"""Deterministic slop measurement (U-P6-04): probe data in, verdict
rows out. Pure functions over the probe dict — thresholds and data
lists come from the shared catalogue (the constants source of truth).

Catalogue v2 (doc 24 section 4): the full DET rule set over the
extended probe, judged under the section 4.3 flag gate — an element
is slop with >= 1 verified severe tell; slop_minor only when the
minor gate is met (>= 1 strong-tier minor, >= 1 bundle-constituted
code, or >= 2 distinct minor codes, all counted AFTER offsets);
otherwise a judged element is clean and its unflagged minor tells
ride along as lone_tells, recorded with their measured values and
any offset reason, never deleted. Page- and region-unit signals are
not gated. Verdict vocabulary is the incumbent one (clean — the
catalogue's not_slop under its shipped name; the aggregator and the
web surfaces already speak it).
"""

import math
import re
from typing import Any
from urllib.parse import urlsplit

from markettwin_shared.slop_aggregate import load_catalogue
from markettwin_shared.slop_tiers import (
    bare_code,
    is_bundle_constituted,
    tier_of,
)

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF]"
)
_ROUND_STAT_RE = re.compile(r"^(99\.9%|100%|10x|10×|24/7)$", re.IGNORECASE)
_BIG_ROUND_RE = re.compile(r"^\d{1,3}(,\d{3})*\+?$")
_EDITORIAL_DATE_RE = re.compile(
    r"^(?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\.?\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2})"
    r"(?:\s+[-–—·|]\s+.+)?$",
    re.IGNORECASE,
)
_REBUTTAL_RES = (
    re.compile(r"\bnot just\b[^.!?]{1,60}[-—–]", re.IGNORECASE),
    re.compile(r"\bnot an?\s+\w+[^.!?]{0,40}[.!]\s+(a|an|the)\s+\w+", re.IGNORECASE),
)
_GENERIC_FAMILIES = {
    "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui",
    "-apple-system", "blinkmacsystemfont", "ui-serif", "ui-sans-serif",
    "ui-monospace", "inherit", "initial", "emoji",
}
_SATURATED_MIN = 0.4


def _data_lists() -> dict[str, Any]:
    return load_catalogue()["data_lists"]


def _list_values(lists: dict[str, Any], key: str) -> list[str]:
    """Every string in a catalogue data list, whatever subkey holds it.

    Only sub-lists carry values: a scalar string in a list entry is
    provenance prose (a source citation, a rule note), never data.
    """

    raw = lists.get(key)
    if isinstance(raw, list):
        return [str(value) for value in raw]
    if isinstance(raw, dict):
        values: list[str] = []
        for value in raw.values():
            if isinstance(value, list):
                values.extend(str(item) for item in value)
        return values
    return []


def _thresholds(code: str) -> dict[str, Any]:
    for rule in load_catalogue()["rules"]:
        if rule["id"] == f"SLOP_{code}":
            return rule.get("thresholds") or {}
    return {}


def _parse_rgb(value: str) -> tuple[float, float, float] | None:
    match = re.match(
        r"rgba?\((\d+)[,\s]+(\d+)[,\s]+(\d+)", value or "",
    )
    if not match:
        return None
    return tuple(float(match.group(i)) / 255 for i in (1, 2, 3))  # type: ignore[return-value]


def _parse_rgba(value: str) -> tuple[float, float, float, float] | None:
    match = re.match(
        r"rgba?\((\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s/]+([\d.]+))?", value or "",
    )
    if not match:
        return None
    alpha = float(match.group(4)) if match.group(4) is not None else 1.0
    return (
        float(match.group(1)) / 255, float(match.group(2)) / 255,
        float(match.group(3)) / 255, alpha,
    )


def _hex_rgb(value: str) -> tuple[float, float, float] | None:
    match = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", (value or "").strip())
    if not match:
        return None
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return tuple(int(digits[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _hue_saturation(
    rgb: tuple[float, float, float],
) -> tuple[float, float]:
    """(hue degrees 0-360, HSL saturation 0-1) for one colour."""

    r, g, b = rgb
    high, low = max(rgb), min(rgb)
    delta = high - low
    if delta == 0:
        return 0.0, 0.0
    lightness = (high + low) / 2
    saturation = delta / (1 - abs(2 * lightness - 1)) if lightness not in {0.0, 1.0} else 0.0
    if high == r:
        hue = 60 * (((g - b) / delta) % 6)
    elif high == g:
        hue = 60 * ((b - r) / delta + 2)
    else:
        hue = 60 * ((r - g) / delta + 4)
    return hue, saturation


def _oklch(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """(lightness, chroma, hue degrees) in OKLCH for one sRGB colour."""

    def linearise(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linearise(c) for c in rgb)
    ll = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    mm = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    ss = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    ll, mm, ss = ll ** (1 / 3), mm ** (1 / 3), ss ** (1 / 3)
    lightness = 0.2104542553 * ll + 0.7936177850 * mm - 0.0040720468 * ss
    a = 1.9779984951 * ll - 2.4285922050 * mm + 0.4505937099 * ss
    bb = 0.0259040371 * ll + 0.7827717662 * mm - 0.8086757660 * ss
    chroma = (a * a + bb * bb) ** 0.5
    hue = math.degrees(math.atan2(bb, a)) % 360
    return lightness, chroma, hue


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


def _first_family(font_family: str) -> str:
    """The first non-generic family in a computed font stack."""

    for part in (font_family or "").split(","):
        name = part.strip().strip("\"'").lower()
        if name and name not in _GENERIC_FAMILIES:
            return name
    return ""


def _px(value: object) -> float:
    match = re.match(r"^(-?[\d.]+)px$", str(value or "").strip())
    return float(match.group(1)) if match else 0.0


def _round_radius(element: dict[str, Any]) -> bool:
    """Whether the element's border radius rounds it fully: a px
    radius at least half the width, or a percentage radius >= 50%
    (a circle authored in % computes to a % string, not px)."""

    token = str(element.get("border_radius") or "").split(" ")[0]
    width = float(element.get("width") or 0)
    if token.endswith("%"):
        try:
            return float(token[:-1]) >= 50
        except ValueError:
            return False
    return width > 0 and _px(token) >= width / 2


def _letter_spacing_em(element: dict[str, Any]) -> float:
    raw = str(element.get("letter_spacing") or "")
    font_size = float(element.get("font_size") or 0)
    if not font_size or raw in {"", "normal"}:
        return 0.0
    return _px(raw) / font_size


def _host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _gradient_colours(background_image: str) -> list[tuple[float, float, float]]:
    colours: list[tuple[float, float, float]] = []
    for match in re.finditer(r"rgba?\([^)]*\)", background_image or ""):
        rgb = _parse_rgb(match.group(0))
        if rgb is not None:
            colours.append(rgb)
    for match in re.finditer(r"#[0-9a-fA-F]{3,6}\b", background_image or ""):
        rgb = _hex_rgb(match.group(0))
        if rgb is not None:
            colours.append(rgb)
    return colours


def _craft_credits(
    elements: list[dict[str, Any]], probe: dict[str, Any], lists: dict[str, Any],
) -> set[str]:
    """Section 4.7 craft credits, measured — a credit is earned by the
    page's own facts, never asserted. Each credit offsets exactly the
    codes the catalogue maps it to."""

    credits: set[str] = set()
    default_fonts = {name.lower() for name in _list_values(lists, "default_fonts")}
    headings = [
        e for e in elements
        if e.get("tag") in {"h1", "h2", "h3"} or float(e.get("font_size") or 0) >= 24
    ]
    text_elements = [e for e in elements if e.get("kind") == "text"]
    heading_family = next(
        (_first_family(str(e.get("font_family") or "")) for e in headings
         if _first_family(str(e.get("font_family") or ""))),
        "",
    )
    body_family = ""
    if text_elements:
        families = [
            _first_family(str(e.get("font_family") or "")) for e in text_elements
        ]
        body_family = max(
            (f for f in families if f), key=families.count, default="",
        )
    if (
        heading_family and body_family and heading_family != body_family
        and heading_family not in default_fonts
        and body_family not in default_fonts
    ):
        credits.add("display_face")
    big_headings = [
        e for e in headings if float(e.get("font_size") or 0) >= 24
    ]
    spacing_by_size: dict[float, set[float]] = {}
    for element in headings:
        spacing_by_size.setdefault(
            float(element.get("font_size") or 0), set(),
        ).add(round(_letter_spacing_em(element), 4))
    if any(_px(e.get("letter_spacing")) < 0 for e in big_headings) or (
        len(spacing_by_size) >= 2
        and len({next(iter(v)) for v in spacing_by_size.values() if v}) >= 2
    ):
        credits.add("optical_tracking")
    radius_by_role: dict[str, set[str]] = {}
    for element in elements:
        radius = str(element.get("border_radius") or "")
        if radius:
            radius_by_role.setdefault(str(element.get("role") or ""), set()).add(radius)
    distinct_radii = {r for values in radius_by_role.values() for r in values}
    if len(distinct_radii) >= 2 and all(
        len(values) == 1 for values in radius_by_role.values()
    ):
        credits.add("radius_hierarchy")
    sheets = probe.get("stylesheets")
    if isinstance(sheets, list) and any(
        isinstance(sheet, dict) and sheet.get("focus_visible") for sheet in sheets
    ):
        credits.add("focus_state")
    return credits


def _brand_context(brand_tokens: dict[str, Any] | None) -> dict[str, Any]:
    """Owner-attested brand tokens, parsed for offset checks: palette
    hues/RGBs and attested font families (section 4.7)."""

    hues: list[float] = []
    rgbs: list[tuple[float, float, float]] = []
    families: set[str] = set()
    if isinstance(brand_tokens, dict):
        for raw in brand_tokens.get("palette_hexes") or []:
            rgb = _hex_rgb(str(raw))
            if rgb is not None:
                rgbs.append(rgb)
                hues.append(_hue_saturation(rgb)[0])
        for raw in brand_tokens.get("font_families") or []:
            families.add(str(raw).strip().lower())
    return {"hues": hues, "rgbs": rgbs, "families": families}


def _hue_near_brand(hue: float, brand: dict[str, Any], tolerance: float) -> bool:
    return any(
        min(abs(hue - brand_hue), 360 - abs(hue - brand_hue)) <= tolerance
        for brand_hue in brand["hues"]
    )


def measure_state(
    probe: dict[str, Any],
    *,
    brand_tokens: dict[str, Any] | None = None,
    slop_classes_enabled: Any = None,
) -> dict[str, Any]:
    """Judge one probed page. Returns the state verdict rows the
    evaluator aggregates: elements + page_signals.

    brand_tokens / slop_classes_enabled ride the run request (doc 24
    section 2.6): attested brand facts offset the tells the catalogue
    allows; a classes list, when given, is the allowlist of codes
    that may fire at all. Both default to today's behaviour exactly.
    """

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
    ai_terms = [term.lower() for term in _list_values(lists, "ai_chrome_terms")]
    placeholder_names = [
        name.lower() for name in _list_values(lists, "placeholder_names")
    ]
    fake_face_hosts = _list_values(lists, "fake_face_hosts")
    template_hosts = _list_values(lists, "template_asset_hosts")
    default_fonts = {name.lower() for name in _list_values(lists, "default_fonts")}
    brand = _brand_context(brand_tokens)
    hue_tolerance = float(
        (_thresholds("GRADIENT_SIGNATURE") or {}).get(
            "brand_hue_tolerance_deg", 10,
        )
    )
    if slop_classes_enabled is None:
        enabled: set[str] | None = None
    else:
        enabled = {bare_code(str(code)) for code in slop_classes_enabled}

    def on(code: str) -> bool:
        return enabled is None or code in enabled

    probe_elements = list(probe.get("elements", []))
    credits = _craft_credits(probe_elements, probe, lists)
    client_height = float(probe.get("client_height") or 0)
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for element in probe_elements:
        by_parent.setdefault(str(element.get("parent_key") or ""), []).append(element)
    headings = [
        e for e in probe_elements if e.get("tag") in {"h1", "h2", "h3"}
    ]

    # Eyebrow sections (template chrome arm a): a small uppercase,
    # letter-spaced label sitting immediately above a heading. The
    # count also feeds TEMPLATE_CHROME's conditional strong tier.
    eyebrow_elements: set[int] = set()
    chrome_thresholds = _thresholds("TEMPLATE_CHROME")
    for heading in headings:
        for element in probe_elements:
            if element is heading:
                continue
            gap = float(heading.get("y") or 0) - (
                float(element.get("y") or 0) + float(element.get("height") or 0)
            )
            text = str(element.get("text") or element.get("name") or "")
            if (
                0 <= gap <= 32
                and abs(float(element.get("x") or 0) - float(heading.get("x") or 0)) <= 40
                and float(element.get("font_size") or 0)
                <= float(chrome_thresholds.get("eyebrow_max_px", 13))
                and text and text == text.upper()
                and element.get("tag") != "time"
                and not _EDITORIAL_DATE_RE.fullmatch(text)
                and any(ch.isalpha() for ch in text)
                and _letter_spacing_em(element)
                >= float(chrome_thresholds.get("eyebrow_min_letter_spacing_em", 0.08))
            ):
                eyebrow_elements.add(id(element))

    viewport_phrases: set[str] = set()
    for element in probe_elements:
        if client_height and float(element.get("y") or 0) >= client_height:
            continue
        lowered = str(
            element.get("text") or element.get("name") or "",
        ).lower()
        viewport_phrases.update(
            phrase for phrase in generic_phrases if phrase in lowered
        )
    tier_context = {
        "gradient_brand_offset": False,
        "template_chrome_eyebrow_sections": len(eyebrow_elements),
        "generic_phrase_viewport_distinct": len(viewport_phrases),
    }

    glass_candidates: list[int] = []
    fired_by_index: list[list[dict[str, Any]]] = []
    label_clip_threshold = int(_thresholds("CLIPPED_CONTROL_LABEL").get("clip_px", 2))
    for index, element in enumerate(probe_elements):
        fired: list[dict[str, Any]] = []
        text = str(element.get("text") or element.get("name") or "")
        lowered = text.lower()
        horizontal_clip = int(element.get("label_clipped_horizontal_px") or 0)
        vertical_clip = int(element.get("label_clipped_vertical_px") or 0)
        if (on("CLIPPED_CONTROL_LABEL") and element.get("role") == "button"
                and max(horizontal_clip, vertical_clip) > label_clip_threshold):
            fired.append({
                "rule_id": "SLOP_CLIPPED_CONTROL_LABEL",
                "severity": "severe",
                "detail": "The button's visible label is partly hidden by its container.",
            })
        if on("PLACEHOLDER_TEXT") and any(
            pattern in lowered for pattern in placeholders
        ):
            fired.append({"rule_id": "SLOP_PLACEHOLDER_TEXT", "severity": "severe"})
        if on("GENERIC_PHRASES") and any(
            phrase in lowered for phrase in generic_phrases
        ):
            fired.append({"rule_id": "SLOP_GENERIC_PHRASES", "severity": "minor"})
        if (
            on("EMOJI_ICONS")
            and element.get("kind") == "interactive"
            and _emoji_share(text) >= 0.5
        ):
            fired.append({"rule_id": "SLOP_EMOJI_ICONS", "severity": "minor"})
        font_size = float(element.get("font_size") or 0)
        if on("ROUND_STATS") and text and font_size >= 28:
            first_token = text.split(" ")[0]
            if _ROUND_STAT_RE.match(first_token) or (
                _BIG_ROUND_RE.match(first_token)
                and int(first_token.replace(",", "").rstrip("+")) >= 10_000
            ):
                if any(label in lowered for label in stat_labels):
                    fired.append({"rule_id": "SLOP_ROUND_STATS", "severity": "minor"})
        if on("CONTRAST") and text and element.get("color") and element.get("background"):
            ratio = contrast_ratio(
                str(element["color"]), str(element["background"]),
            )
            large = font_size >= 24 or (
                font_size >= 18.66 and int(element.get("font_weight") or 400) >= 700
            )
            floor = 3.0 if large else 4.5
            if ratio is not None and ratio < floor:
                fired.append({"rule_id": "SLOP_CONTRAST", "severity": "minor"})
        if on("AI_CHROME") and any(term in lowered for term in ai_terms if term):
            fired.append({"rule_id": "SLOP_AI_CHROME", "severity": "minor"})
        width = int(element.get("width") or 0)
        height = int(element.get("height") or 0)
        background_image = str(element.get("background_image") or "none")
        if on("GRADIENT_SIGNATURE") and "linear-gradient" in background_image:
            gradient_thresholds = _thresholds("GRADIENT_SIGNATURE")
            colours = _gradient_colours(background_image)
            in_band = [
                hue for hue, _sat in (
                    _hue_saturation(colour) for colour in colours
                )
                if float(gradient_thresholds.get("hue_min_deg", 230))
                <= hue
                <= float(gradient_thresholds.get("hue_max_deg", 300))
            ]
            size_ok = (
                width >= int(gradient_thresholds.get("min_width_px", 200))
                and height >= int(gradient_thresholds.get("min_height_px", 60))
            )
            clip_text = str(element.get("background_clip") or "") == "text"
            if len(in_band) >= int(gradient_thresholds.get("min_stops", 2)) and (
                size_ok or clip_text
            ):
                entry: dict[str, Any] = {
                    "rule_id": "SLOP_GRADIENT_SIGNATURE", "severity": "minor",
                    "values": {"hues": [round(hue, 1) for hue in in_band]},
                }
                if in_band and _hue_near_brand(in_band[0], brand, hue_tolerance):
                    entry["offset_reason"] = "brand_token"
                    tier_context["gradient_brand_offset"] = True
                fired.append(entry)
        if on("SIDE_TAB_BORDER"):
            borders = element.get("borders") or {}
            widths = {
                side: _px((borders.get(side) or {}).get("width"))
                for side in ("top", "right", "bottom", "left")
            }
            wide = [side for side, value in widths.items() if value >= 3]
            if len(wide) == 1 and all(
                value <= 1 for side, value in widths.items() if side != wide[0]
            ):
                colour = _parse_rgb(
                    str((borders.get(wide[0]) or {}).get("color") or ""),
                )
                if colour is not None and _hue_saturation(colour)[1] >= _SATURATED_MIN:
                    entry = {
                        "rule_id": "SLOP_SIDE_TAB_BORDER", "severity": "minor",
                        "values": {"side": wide[0], "width_px": widths[wide[0]]},
                    }
                    if colour in brand["rgbs"] or _hue_near_brand(
                        _hue_saturation(colour)[0], brand, hue_tolerance,
                    ):
                        entry["offset_reason"] = "brand_token"
                    fired.append(entry)
        if on("GLASS_GLOW"):
            orb = re.search(
                r"blur\(([\d.]+)px\)", str(element.get("filter") or ""),
            )
            shadow = str(element.get("box_shadow") or "none")
            shadow_match = re.search(
                r"(-?[\d.]+)px\s+(-?[\d.]+)px\s+([\d.]+)px\s+([\d.]+)px\s+(.+)$",
                shadow,
            )
            backdrop = re.search(
                r"blur\(([\d.]+)px\)", str(element.get("backdrop_filter") or ""),
            )
            own_bg = _parse_rgba(str(element.get("own_background") or ""))
            if orb and float(orb.group(1)) >= 40:
                bg_rgb = _parse_rgb(str(element.get("background") or ""))
                if bg_rgb is not None and _hue_saturation(bg_rgb)[1] >= _SATURATED_MIN:
                    fired.append({"rule_id": "SLOP_GLASS_GLOW", "severity": "minor"})
            elif (
                shadow_match
                and float(shadow_match.group(1)) == 0
                and float(shadow_match.group(2)) == 0
                and float(shadow_match.group(3)) >= 40
                and float(shadow_match.group(4)) == 0
            ):
                shadow_rgb = _parse_rgb(shadow_match.group(5))
                if shadow_rgb is not None and _hue_saturation(shadow_rgb)[1] >= _SATURATED_MIN:
                    fired.append({"rule_id": "SLOP_GLASS_GLOW", "severity": "minor"})
            elif (
                backdrop and float(backdrop.group(1)) >= 8
                and own_bg is not None and own_bg[3] < 0.9
            ):
                # Glass proper fires only as a cluster (>= 3 panels):
                # decided after the loop, when the page count is known.
                glass_candidates.append(index)
        if on("MOCK_CHROME"):
            transform = str(element.get("transform") or "none")
            matrix = re.match(
                r"matrix\(([^)]*)\)", transform,
            )
            if matrix and (not client_height or float(element.get("y") or 0) < client_height):
                parts = [float(p) for p in matrix.group(1).split(",")]
                if len(parts) == 6:
                    angle = abs(math.degrees(math.atan2(parts[1], parts[0])))
                    if 0.5 <= angle <= 12:
                        fired.append({"rule_id": "SLOP_MOCK_CHROME", "severity": "minor"})
        if on("EMPTY_VISUAL") and width >= 300 and height >= 200:
            child_tags = [str(tag) for tag in element.get("child_tags") or []]
            decorative = (
                background_image != "none"
                or (
                    _parse_rgba(str(element.get("own_background") or ""))
                    or (0, 0, 0, 0)
                )[3] > 0
            )
            if (
                decorative
                and not {"img", "video", "canvas"} & set(child_tags)
                and len(text.split()) < 3
            ):
                fired.append({"rule_id": "SLOP_EMPTY_VISUAL", "severity": "minor"})
        if on("TEMPLATE_ASSETS") and element.get("region") != "footer":
            asset_url = ""
            url_match = re.search(r"url\(([^)]*)\)", background_image)
            if url_match:
                asset_url = url_match.group(1).strip("\"'")
            host = _host_of(asset_url)
            if host and any(
                host == listed or host.endswith("." + listed)
                for listed in template_hosts if listed
            ):
                fired.append({"rule_id": "SLOP_TEMPLATE_ASSETS", "severity": "minor"})
        if on("TEMPLATE_CHROME"):
            if id(element) in eyebrow_elements:
                fired.append({"rule_id": "SLOP_TEMPLATE_CHROME", "severity": "minor"})
            if len(text) <= 120 and text.count(" · ") >= 2:
                fired.append({"rule_id": "SLOP_TEMPLATE_CHROME", "severity": "minor"})
            if element.get("kind") == "interactive" and re.search(
                r"(->|→)\s*$", text,
            ):
                fired.append({"rule_id": "SLOP_TEMPLATE_CHROME", "severity": "minor"})
        if on("FABRICATED_PROOF") and text:
            name_hit = next(
                (name for name in placeholder_names if name and name in lowered),
                None,
            )
            if name_hit:
                siblings = by_parent.get(str(element.get("parent_key") or ""), [])
                role_line = any(
                    sibling is not element
                    and any(
                        marker in str(
                            sibling.get("text") or sibling.get("name") or "",
                        ).lower()
                        for marker in ("ceo", "founder", "manager", "director", "vp", "@", "inc.")
                    )
                    for sibling in siblings
                )
                if role_line:
                    fired.append({
                        "rule_id": "SLOP_FABRICATED_PROOF", "severity": "severe",
                    })
        fired_by_index.append(fired)
    if len(glass_candidates) >= 3:
        for index in glass_candidates:
            if on("GLASS_GLOW"):
                fired_by_index[index].append(
                    {"rule_id": "SLOP_GLASS_GLOW", "severity": "minor"},
                )


    def judge(
        fired: list[dict[str, Any]], width: int, height: int,
    ) -> tuple[str, list[dict[str, Any]]]:
        """The section 4.3 gate over one element's fired tells.

        Returns (verdict, lone_tells). Severe flags singly and is
        never offset; minor flags only through the gate, counted
        after offsets; an unflagged judged element is clean and its
        minor tells are recorded as lone tells, never deleted.
        """

        distinct: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        for entry in fired:
            code = bare_code(str(entry["rule_id"]))
            if code not in seen_codes:
                seen_codes.add(code)
                distinct.append(entry)
        severe = any(entry["severity"] == "severe" for entry in distinct)
        minors = [e for e in distinct if e["severity"] != "severe"]
        counting = [e for e in minors if not e.get("offset_reason")]
        gate_met = (
            any(
                tier_of(
                    str(e["rule_id"]),
                    brand_offset=bool(e.get("offset_reason") == "brand_token"),
                    eyebrow_sections=tier_context[
                        "template_chrome_eyebrow_sections"
                    ],
                    generic_phrase_viewport_distinct=tier_context[
                        "generic_phrase_viewport_distinct"
                    ],
                ) == "strong"
                for e in counting
            )
            or any(is_bundle_constituted(str(e["rule_id"])) for e in counting)
            or len(counting) >= 2
        )
        if severe:
            return "slop", []
        if gate_met:
            return "slop_minor", []
        if width > 0 and height > 0:
            lone = [
                {
                    "rule_id": entry["rule_id"],
                    "tier": tier_of(
                        str(entry["rule_id"]),
                        eyebrow_sections=tier_context[
                            "template_chrome_eyebrow_sections"
                        ],
                        generic_phrase_viewport_distinct=tier_context[
                            "generic_phrase_viewport_distinct"
                        ],
                    ),
                    "offset_reason": entry.get("offset_reason"),
                    "values": entry.get("values", {}),
                }
                for entry in minors
            ]
            return "clean", lone
        return "cant_tell", []

    elements: list[dict[str, Any]] = []
    for index, element in enumerate(probe_elements):
        fired = fired_by_index[index]
        text = str(element.get("text") or element.get("name") or "")
        width = int(element.get("width") or 0)
        height = int(element.get("height") or 0)
        verdict, lone_tells = judge(fired, width, height)
        record: dict[str, Any] = {
            "element_id": f"e{element.get('key')}",
            "component": {
                "role": element.get("role"), "name": element.get("name"),
                "region": element.get("region"), "disabled": element.get("disabled", False),
                "style": {key: element.get(key) for key in (
                    "font_size", "font_weight", "font_family", "color",
                    "background", "border_radius", "padding",
                )},
            },
            "verdict": verdict,
            "rules_fired": fired,
            "area": float(width * height) if width > 0 and height > 0 else None,
            "label": text[:80],
            "evidence": {**{key: element.get(key) for key in (
                "text", "name", "role", "x", "y", "width", "height", "color", "background",
                "font_size", "font_weight",
            )}, "contrast_ratio": contrast_ratio(
                element.get("color", ""), element.get("background", ""),
            )},
        }
        if lone_tells:
            record["lone_tells"] = lone_tells
        if any(rule["rule_id"] == "SLOP_CLIPPED_CONTROL_LABEL" for rule in fired):
            record["evidence"].update(
                label_clipped_horizontal_px=element.get("label_clipped_horizontal_px", 0),
                label_clipped_vertical_px=element.get("label_clipped_vertical_px", 0),
            )
        elements.append(record)
    dpr = float(probe.get("device_pixel_ratio") or 1)
    for image in probe.get("images", []):
        fired = []
        loaded = image.get("complete", True)
        natural_width = int(image.get("natural_width") or 0)
        response_status = image.get("response_status")
        origin_error = isinstance(response_status, int) and 400 <= response_status <= 599
        if on("BROKEN_MEDIA") and loaded and natural_width == 0 and origin_error:
            fired.append({"rule_id": "SLOP_BROKEN_MEDIA", "severity": "severe"})
        src = str(image.get("src") or "")
        if on("PLACEHOLDER_TEXT") and any(domain in src for domain in
               lists["placeholder_patterns"].get("domains_in_src_or_href", [])):
            fired.append({"rule_id": "SLOP_PLACEHOLDER_TEXT", "severity": "severe"})
        width = int(image.get("width") or 0)
        height = int(image.get("height") or 0)
        natural_height = int(image.get("natural_height") or 0)
        is_svg = ".svg" in src.split("?")[0].lower()
        if (
            on("LOW_RES_MEDIA") and not is_svg and natural_width > 0
            and width >= 100 and width * dpr > natural_width * 1.25
        ):
            fired.append({"rule_id": "SLOP_LOW_RES_MEDIA", "severity": "minor"})
        if (
            on("STRETCHED_IMAGE") and not is_svg
            and natural_width > 0 and natural_height > 0
            and width > 0 and height > 0
            and str(image.get("object_fit") or "fill") == "fill"
        ):
            display_aspect = width / height
            natural_aspect = natural_width / natural_height
            if abs(display_aspect - natural_aspect) / natural_aspect > 0.05:
                fired.append({"rule_id": "SLOP_STRETCHED_IMAGE", "severity": "minor"})
        host = _host_of(src)
        if (
            on("TEMPLATE_ASSETS") and host
            and any(
                host == listed or host.endswith("." + listed)
                for listed in template_hosts if listed
            )
        ):
            fired.append({"rule_id": "SLOP_TEMPLATE_ASSETS", "severity": "minor"})
        if (
            on("FABRICATED_PROOF") and host
            and any(
                host == listed or host.endswith("." + listed)
                for listed in fake_face_hosts if listed
            )
            and 0 < width <= 96 and 0 < height <= 96
        ):
            fired.append({"rule_id": "SLOP_FABRICATED_PROOF", "severity": "severe"})
        verdict, lone_tells = judge(fired, width, height)
        if not fired and not (loaded and natural_width > 0 and width > 0 and height > 0):
            verdict = "cant_tell"
        record = {
            "element_id": f"img{image.get('key')}",
            "verdict": verdict,
            "rules_fired": fired,
            "area": float(width * height) if width > 0 and height > 0 else None,
            "label": (image.get("alt") or src)[:80],
            "evidence": {key: image.get(key) for key in (
                "src", "alt", "complete", "natural_width", "natural_height", "width", "height",
                "response_status",
            )},
        }
        if lone_tells:
            record["lone_tells"] = lone_tells
        elements.append(record)

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
    page_signals.extend(_page_detectors(
        probe, probe_elements, credits=credits, on=on,
        client_height=client_height, by_parent=by_parent,
        headings=headings, default_fonts=default_fonts,
        brand_families=brand["families"],
    ))
    drawn_candidates = sum(
        1 for figure in probe.get("svg_figures") or []
        if isinstance(figure, dict)
        and (int(figure.get("width") or 0) >= 120 or int(figure.get("height") or 0) >= 120)
        and (int(figure.get("curves") or 0) >= 3 or int(figure.get("fills") or 0) >= 3)
        and not figure.get("has_text")
    )
    return {
        "url": probe.get("url"),
        "title": probe.get("title"),
        "elements": elements,
        "page_signals": page_signals,
        "measurement_evidence": {key: probe.get(key) for key in ("scroll_width", "client_width", "words")},
        "catalogue_version": load_catalogue().get("catalogue_version"),
        "tier_context": tier_context,
        "drawn_illustration_candidates": drawn_candidates,
    }


def _page_detectors(
    probe: dict[str, Any],
    elements: list[dict[str, Any]],
    *,
    credits: set[str],
    on: Any,
    client_height: float,
    by_parent: dict[str, list[dict[str, Any]]],
    headings: list[dict[str, Any]],
    default_fonts: set[str],
    brand_families: set[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Page-unit DET codes (doc 24 section 4.5, groups G3–G6): judged
    per page, reported as page signals, never gated, never attached
    to an element verdict. Every detector reads the extended probe
    fields defensively — a capture without them cannot fire."""

    signals: list[dict[str, Any]] = []

    def fire(code: str, detail: str, **extra: Any) -> None:
        if on(code):
            signals.append({
                "rule_id": f"SLOP_{code}", "severity": "minor",
                "detail": detail, **extra,
            })

    buttons = [e for e in elements if e.get("role") == "button"]
    if on("STYLE_INCONSISTENCY"):
        fingerprints = {
            (
                str(e.get("background") or ""),
                str(e.get("border_radius") or ""),
                _first_family(str(e.get("font_family") or "")),
            )
            for e in buttons
            if _parse_rgba(str(e.get("own_background") or "")) is not None
            and (_parse_rgba(str(e.get("own_background") or "")) or (0, 0, 0, 0))[3] > 0
        }
        if len(fingerprints) >= 2:
            fire(
                "STYLE_INCONSISTENCY",
                f"{len(fingerprints)} distinct primary-button styles on one page.",
            )
    if on("SPACING_RHYTHM"):
        thresholds = _thresholds("SPACING_RHYTHM")
        tolerance = float(thresholds.get("cluster_tolerance_px", 2))
        share_floor = float(thresholds.get("off_rhythm_share", 0.2))
        for role in ("button", "link", "textbox"):
            peers = [e for e in elements if e.get("role") == role]
            values = sorted(
                _px(str(e.get("padding") or "").split(" ")[0]) for e in peers
            )
            if len(values) < 5:
                continue
            clusters: list[list[float]] = []
            for value in values:
                if clusters and value - clusters[-1][-1] <= tolerance:
                    clusters[-1].append(value)
                else:
                    clusters.append([value])
            modal = max(clusters, key=len)
            off = sum(
                1 for value in values
                if all(abs(value - member) > tolerance for member in modal)
            )
            if off / len(values) >= share_floor:
                fire(
                    "SPACING_RHYTHM",
                    f"{off} of {len(values)} {role} paddings sit off the "
                    f"page's modal rhythm ({off / len(values):.0%}).",
                )
                break
    if on("ALIGNMENT"):
        missed = False
        for siblings in by_parent.values():
            for first in siblings:
                for second in siblings:
                    if first is second:
                        continue
                    if abs(float(first.get("y") or 0) - float(second.get("y") or 0)) > 2:
                        continue
                    for edge_a, edge_b in (
                        (float(first.get("x") or 0), float(second.get("x") or 0)),
                        (
                            float(first.get("x") or 0) + float(first.get("width") or 0),
                            float(second.get("x") or 0) + float(second.get("width") or 0),
                        ),
                    ):
                        if 2 <= abs(edge_a - edge_b) <= 6:
                            missed = True
            if missed:
                break
        if missed:
            fire(
                "ALIGNMENT",
                "Peer elements share a row but their shared edge misses "
                "by 2-6px.",
            )
    sections = probe.get("sections")
    if on("UNIFORM_RHYTHM") and isinstance(sections, list) and len(sections) >= 4:
        paddings = [
            float(s.get("padding_top") or 0) + float(s.get("padding_bottom") or 0)
            for s in sections
        ]
        gaps = [
            float(sections[i + 1].get("y") or 0)
            - (float(sections[i].get("y") or 0) + float(sections[i].get("height") or 0))
            for i in range(len(sections) - 1)
        ]
        if (
            max(paddings) - min(paddings) <= 1
            and gaps and max(gaps) - min(gaps) <= 1
        ):
            fire(
                "UNIFORM_RHYTHM",
                f"{len(sections)} sections share identical padding and gaps.",
            )
    client_width = float(probe.get("client_width") or 0)
    if on("CENTRED_HERO") and client_width and client_height:
        for heading in headings:
            if heading.get("tag") != "h1":
                continue
            bottom = float(heading.get("y") or 0) + float(heading.get("height") or 0)
            if bottom > client_height:
                continue
            centre = float(heading.get("x") or 0) + float(heading.get("width") or 0) / 2
            if abs(centre - client_width / 2) > 0.02 * client_width:
                continue
            signs = 0
            for element in elements:
                if element is heading:
                    continue
                e_centre = float(element.get("x") or 0) + float(element.get("width") or 0) / 2
                centred = abs(e_centre - client_width / 2) <= 0.02 * client_width
                e_bottom = float(element.get("y") or 0) + float(element.get("height") or 0)
                if (
                    e_bottom <= float(heading.get("y") or 0) and centred
                    and _px(str(element.get("border_radius") or "").split(" ")[0]) >= 12
                ):
                    signs += 1  # pill/badge directly above
                if (
                    element.get("tag") == "p" and centred
                    and float(element.get("y") or 0) >= bottom
                    and str(element.get("text_align") or "") == "center"
                ):
                    signs += 1  # centred paragraph under
                if (
                    element.get("role") == "button" and centred
                    and float(element.get("y") or 0) >= bottom
                ):
                    signs += 1  # centred CTA group
            if signs >= 2:
                fire(
                    "CENTRED_HERO",
                    "Centred hero: a centred h1 with at least two centred "
                    "supporting signs in the first viewport.",
                )
                break
    if on("CENTRED_LAYOUT"):
        blocks = [
            e for e in elements
            if e.get("tag") in {"p", "li", "blockquote"} and e.get("text")
        ]
        centred = [
            e for e in blocks if str(e.get("text_align") or "") == "center"
        ]
        if (
            blocks and len(centred) / len(blocks) >= 0.5
            and any(
                len(str(e.get("text") or "").split()) >= 25 for e in blocks
            )
        ):
            fire(
                "CENTRED_LAYOUT",
                f"{len(centred)} of {len(blocks)} text blocks are "
                "centre-aligned, including long-form body text.",
            )
    if on("CARD_GRID"):
        for siblings in by_parent.values():
            if len(siblings) < 3:
                continue
            widths = [float(e.get("width") or 0) for e in siblings]
            signatures = {
                ",".join(str(tag) for tag in e.get("child_tags") or [])
                for e in siblings
            }
            if (
                widths and min(widths) > 0
                and max(widths) / min(widths) <= 1.02
                and len(signatures) == 1
                and next(iter(signatures)) != ""
            ):
                first_child = (siblings[0].get("child_tags") or [""])[0]
                variant = (
                    "icon-first" if first_child in {"svg", "img", "i"}
                    else "structure-only"
                )
                fire(
                    "CARD_GRID",
                    f"{len(siblings)} sibling cards share width and "
                    f"structure ({variant} variant).",
                )
                break
    if on("UNIFORM_SURFACE"):
        elevated = []
        for element in elements:
            shadow = str(element.get("box_shadow") or "none")
            own_bg = _parse_rgba(str(element.get("own_background") or ""))
            borders = element.get("borders") or {}
            bordered = any(
                _px((borders.get(side) or {}).get("width")) >= 1
                for side in ("top", "right", "bottom", "left")
            )
            if shadow != "none" or (bordered and own_bg is not None and own_bg[3] > 0):
                elevated.append(element)
        pairs = {
            (str(e.get("border_radius") or ""), str(e.get("box_shadow") or "none"))
            for e in elevated
        }
        roles = {str(e.get("role") or "") for e in elevated}
        if len(elevated) >= 8 and len(roles) >= 3 and len(pairs) == 1:
            extra = (
                {"offset_reason": "craft_credit:radius_hierarchy"}
                if "radius_hierarchy" in credits else {}
            )
            fire(
                "UNIFORM_SURFACE",
                f"{len(elevated)} elevated elements across {len(roles)} "
                "roles share one radius/shadow pair.",
                **extra,
            )
    if on("FLAT_TYPE"):
        text_elements = [e for e in elements if e.get("kind") == "text"]
        weights = {int(e.get("font_weight") or 400) for e in text_elements}
        tracked = any(
            _px(e.get("letter_spacing")) < 0
            for e in text_elements
            if float(e.get("font_size") or 0) >= 24
        )
        if (
            len(text_elements) >= 8
            and weights <= {400, 500, 600}
            and not tracked
        ):
            extra = (
                {"offset_reason": "craft_credit:optical_tracking"}
                if "optical_tracking" in credits else {}
            )
            fire(
                "FLAT_TYPE",
                "Every sampled text weight sits in {400, 500, 600} and "
                "no large heading carries optical tracking.",
                **extra,
            )
    sheets = probe.get("stylesheets")
    interactive_count = sum(1 for e in elements if e.get("kind") == "interactive")
    if (
        on("NO_MICROSTATES") and isinstance(sheets, list) and sheets
        and interactive_count > 0
        and all(isinstance(s, dict) and s.get("readable") for s in sheets)
        and not any(s.get("hover_interactive") for s in sheets if isinstance(s, dict))
        and not any(s.get("focus_visible") for s in sheets if isinstance(s, dict))
    ):
        fire(
            "NO_MICROSTATES",
            "Readable stylesheets define no :hover rule for interactive "
            "elements and no :focus-visible rule at all.",
        )
    motion = probe.get("motion")
    if on("MOTION_TELLS") and isinstance(motion, dict):
        tells = [
            name for name in (
                "transition_all", "overshoot_timing", "infinite_animation",
            )
            if motion.get(name)
        ]
        if tells:
            fire(
                "MOTION_TELLS",
                f"Motion tells in the page's styles: {', '.join(tells)}.",
            )
    if on("TEMPLATE_CHROME"):
        numbered = 0
        mono_labels = 0
        for siblings in by_parent.values():
            starts = []
            for element in siblings:
                match = re.match(
                    r"^(0[1-9]|1[0-2])\b",
                    str(element.get("text") or element.get("name") or ""),
                )
                if match:
                    starts.append(int(match.group(1)))
            if any(
                starts[i:i + 3] == [n, n + 1, n + 2]
                for i in range(len(starts) - 2)
                for n in (starts[i],)
            ):
                numbered += 1
        for element in elements:
            family = str(element.get("font_family") or "").lower()
            if (
                "monospace" in family or "mono" in _first_family(family)
            ) and float(element.get("font_size") or 0) <= 12:
                mono_labels += 1
        if numbered:
            fire(
                "TEMPLATE_CHROME",
                "Numbered labels appear on successive sibling elements.",
                severity="info",
            )
        if mono_labels >= 3:
            fire(
                "TEMPLATE_CHROME",
                f"{mono_labels} small monospace labels appear on this page.",
                severity="info",
            )
    if on("MOCK_CHROME"):
        for siblings in by_parent.values():
            circles = [
                e for e in siblings
                if 8 <= float(e.get("width") or 0) <= 16
                and float(e.get("width") or 0) == float(e.get("height") or 0)
                and _round_radius(e)
            ]
            if len(circles) != 3:
                continue
            hues = sorted(
                _hue_saturation(
                    _parse_rgb(str(e.get("background") or "")) or (0, 0, 0),
                )[0]
                for e in circles
            )
            if (
                hues[0] <= 30 and 30 < hues[1] <= 90 and 90 < hues[2] <= 160
            ):
                fire(
                    "MOCK_CHROME",
                    "A bar of three red/yellow/green dots imitates "
                    "browser chrome.",
                )
                break
    document_rgb = _parse_rgb(str(probe.get("document_background") or ""))
    if document_rgb is not None:
        doc_lightness, _doc_chroma, doc_hue = _oklch(document_rgb)
        button_backgrounds = [
            _parse_rgb(str(e.get("background") or ""))
            for e in buttons
        ]
        button_backgrounds = [c for c in button_backgrounds if c is not None]
        if on("EDITORIAL_CLUSTER") and doc_lightness >= 0.90 and 40 <= doc_hue <= 100:
            serif = any(
                "serif" in str(e.get("font_family") or "").lower()
                and "sans" not in str(e.get("font_family") or "").lower()
                for e in headings
            )
            accent_ok = False
            if button_backgrounds:
                dominant = max(
                    set(button_backgrounds), key=button_backgrounds.count,
                )
                _l, accent_chroma, accent_hue = _oklch(dominant)
                accent_ok = 15 <= accent_hue <= 55 and accent_chroma >= 0.04
            if serif and accent_ok:
                fire(
                    "EDITORIAL_CLUSTER",
                    "Cream background, serif display headings and a "
                    "terracotta-band accent, measured together.",
                )
        if on("ACID_DARK") and _luminance(document_rgb) <= 0.02:
            distinct_accents = set(button_backgrounds)
            text_colours = [
                _parse_rgb(str(e.get("color") or ""))
                for e in elements if e.get("kind") == "text"
            ]
            light_text = [
                c for c in text_colours
                if c is not None and _luminance(c) > 0.4
            ]
            if (
                len(distinct_accents) == 1
                and _hue_saturation(next(iter(distinct_accents)))[1] >= 0.8
                and text_colours and len(light_text) * 2 >= len(text_colours)
            ):
                fire(
                    "ACID_DARK",
                    "Near-black page, one saturated accent carrying the "
                    "primary actions, light body text.",
                )
    if on("TYPE_DISCIPLINE"):
        families = {
            _first_family(str(e.get("font_family") or ""))
            for e in elements if e.get("kind") == "text"
        } - {""}
        sizes = [
            float(e.get("font_size") or 0)
            for e in elements if e.get("kind") == "text"
        ]
        outside = 0
        if sizes:
            counts: dict[float, int] = {}
            for size in sizes:
                counts[size] = counts.get(size, 0) + 1
            dominant = sorted(counts, key=lambda s: -counts[s])[:6]
            outside = sum(
                1 for size in set(sizes)
                if all(abs(size - keep) > 1 for keep in dominant)
            )
        if len(families) > 2 or outside >= 4:
            fire(
                "TYPE_DISCIPLINE",
                f"{len(families)} font families in use; {outside} sizes "
                "sit outside the dominant 6-value scale.",
            )
    if on("DEFAULT_FONT"):
        heading_family = next(
            (_first_family(str(e.get("font_family") or "")) for e in headings
             if _first_family(str(e.get("font_family") or ""))),
            "",
        )
        text_families = [
            _first_family(str(e.get("font_family") or ""))
            for e in elements if e.get("kind") == "text"
        ]
        body_family = (
            max((f for f in text_families if f), key=text_families.count, default="")
            if text_families else ""
        )
        if (
            heading_family and heading_family in default_fonts
            and body_family == heading_family
        ):
            extra: dict[str, Any] = {}
            if heading_family in brand_families:
                extra["offset_reason"] = "brand_token"
            elif "optical_tracking" in credits:
                extra["offset_reason"] = "craft_credit:optical_tracking"
            fire(
                "DEFAULT_FONT",
                f"Display and body text both use {heading_family}.",
                severity="info",
                **extra,
            )
    return signals


def compare_components(states: list[dict[str, Any]]) -> list[tuple[dict, dict, dict]]:
    """Surface differing repeated controls for review, not automatic penalties.

    Same label/role/region can still have intentional variants. Preserve both
    page references and measured differences rather than inventing a defect.
    """
    baseline: dict[tuple, tuple[dict, dict]] = {}
    comparisons: list[tuple[dict, dict, dict]] = []
    for state in states:
        for element in state.get("elements", []):
            component = element.get("component", {})
            if component.get("role") not in {"button", "textbox", "combobox"} or not component.get("name"):
                continue
            key = (component["role"], component["name"], component.get("region"), component.get("disabled"), state.get("viewport"))
            style = component["style"]
            previous = baseline.setdefault(key, (state, style))
            if previous[0]["url"] == state["url"]:
                continue
            differences = [name for name, value in style.items() if value != previous[1].get(name)]
            if differences:
                signal = {
                    "rule_id": "UI_COMPONENT_VARIANT_REVIEW", "severity": "review",
                    "detail": f"{component['name']}: {', '.join(differences)} differ from "
                              f"{previous[0]['url']}. Verify that this is an intentional variant.",
                    "evidence_artifact_ids": [
                        source["screenshot_artifact_id"] for source in (previous[0], state)
                        if source.get("screenshot_artifact_id")
                    ],
                }
                state["page_signals"].append(signal)
                comparisons.append((signal, previous[0], state))
    _app_scope_signals(states)
    return comparisons


def _app_scope_signals(states: list[dict[str, Any]]) -> None:
    """App-scope DET codes (doc 24 section 4.5, group G5 + the
    app-wide arm of COPY_CADENCE): judged across every captured state,
    reported once on the first state as page signals with scope "app"
    — a page roll-up only, never element counts, never gated."""

    if not states:
        return
    signals: list[dict[str, Any]] = []

    def fire(code: str, detail: str) -> None:
        signals.append({
            "rule_id": f"SLOP_{code}", "severity": "minor",
            "detail": detail, "scope": "app",
        })

    fingerprints: dict[str, set[tuple]] = {}
    colour_uses: dict[str, int] = {}
    button_backgrounds: set[str] = set()
    rebuttals = 0
    for state in states:
        for element in state.get("elements", []):
            component = element.get("component", {})
            style = component.get("style", {})
            role = component.get("role")
            if role in {"button", "textbox", "combobox"}:
                fingerprints.setdefault(str(role), set()).add((
                    style.get("background"), style.get("border_radius"),
                    style.get("font_family"), style.get("padding"),
                ))
            for key in ("color", "background"):
                colour = style.get(key)
                if isinstance(colour, str) and colour:
                    colour_uses[colour] = colour_uses.get(colour, 0) + 1
            if role == "button" and style.get("background"):
                button_backgrounds.add(str(style["background"]))
            text = str(element.get("label") or "")
            if any(pattern.search(text) for pattern in _REBUTTAL_RES):
                rebuttals += 1
    fp_thresholds = _thresholds("COMPONENT_FINGERPRINTS")
    if len(fingerprints.get("button", set())) >= int(
        fp_thresholds.get("buttons", 3),
    ):
        fire(
            "COMPONENT_FINGERPRINTS",
            f"{len(fingerprints['button'])} distinct button fingerprints "
            "across the app.",
        )
    for role in ("textbox", "combobox"):
        if len(fingerprints.get(role, set())) >= int(
            fp_thresholds.get("inputs_and_cards", 4),
        ):
            fire(
                "COMPONENT_FINGERPRINTS",
                f"{len(fingerprints[role])} distinct {role} fingerprints "
                "across the app.",
            )
    one_off = sum(1 for count in colour_uses.values() if count == 1)
    if one_off >= 5:
        fire(
            "COLOUR_DISCIPLINE",
            f"{one_off} colours are used exactly once across all captures.",
        )
    if len(button_backgrounds) >= 2:
        fire(
            "COLOUR_DISCIPLINE",
            f"{len(button_backgrounds)} distinct primary-button background "
            "colours across the app.",
        )
    if rebuttals >= 3:
        fire(
            "COPY_CADENCE",
            f"{rebuttals} rebuttal-cadence headlines ('Not a X. A Y.') "
            "across the app.",
        )
    states[0].setdefault("page_signals", []).extend(signals)


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
