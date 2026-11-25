"""Catalogue v2 measurement (doc 24 section 4, W4-P5-13..19):
the grouped DET detectors over the extended probe, the section 4.3
flag gate, section 4.7 offsets, calibration fixtures, and the G7
critic pinning. Pure-function tests over fake probes — the probe
itself is pinned against a real page in test_probe_v1_stability.
"""

from markettwin_shared.slop_aggregate import load_catalogue

from markettwin_execution_orchestrator.slop.measure import (
    _list_values,
    compare_components,
    measure_state,
)
from markettwin_execution_orchestrator.slop.visual_review import (
    validate_critic_notes,
)

LISTS = load_catalogue()["data_lists"]


def _first(key: str) -> str:
    values = _list_values(LISTS, key)
    assert values, f"catalogue data list {key} is empty"
    return values[0]


def el(**overrides):
    element = {
        "key": 0, "kind": "text", "tag": "p", "role": "p",
        "name": "", "text": "", "x": 0, "y": 0, "width": 100, "height": 20,
        "font_size": 16, "font_weight": 400,
        "font_family": "Inter, sans-serif",
        "color": "rgb(20, 20, 20)", "background": "rgb(255, 255, 255)",
        "border_radius": "0px", "padding": "0px", "disabled": False,
        "selected": None, "expanded": None, "invalid": None,
        "region": "body", "background_image": "none",
        "background_clip": "", "own_background": "rgba(0, 0, 0, 0)",
        "letter_spacing": "normal",
        "borders": {
            side: {"width": "0px", "color": "rgb(0, 0, 0)"}
            for side in ("top", "right", "bottom", "left")
        },
        "box_shadow": "none", "backdrop_filter": "none", "filter": "none",
        "text_align": "left", "transform": "none",
        "parent_key": "body:0", "child_tags": [],
    }
    element.update(overrides)
    return element


def img(**overrides):
    image = {
        "key": 0, "src": "https://cdn.example.test/hero.png", "alt": "Hero",
        "natural_width": 800, "natural_height": 400, "complete": True,
        "width": 400, "height": 200, "x": 0, "y": 0, "object_fit": "cover",
    }
    image.update(overrides)
    return image


def probe(elements=(), images=(), **page):
    base = {
        "url": "https://app.example.test/", "title": "App", "lang": "en",
        "scroll_width": 1280, "client_width": 1280, "words": 120,
        "elements": list(elements), "images": list(images),
        "client_height": 800, "device_pixel_ratio": 1,
        "document_background": "rgb(255, 255, 255)",
        "stylesheets": [], "motion": {
            "transition_all": False, "overshoot_timing": False,
            "infinite_animation": False,
        },
        "sections": [], "svg_figures": [],
    }
    base.update(page)
    return base


def fired_codes(state, element_id="e0"):
    record = next(e for e in state["elements"] if e["element_id"] == element_id)
    return [entry["rule_id"] for entry in record["rules_fired"]], record


def signal_codes(state):
    return [s["rule_id"] for s in state["page_signals"]]


def test_image_with_no_decoded_pixels_requires_an_http_error_to_flag() -> None:
    for status in (None, 200, 404):
        state = measure_state(probe(images=[img(
            complete=True, natural_width=0, response_status=status,
        )]))
        codes, record = fired_codes(state, "img0")
        assert ("SLOP_BROKEN_MEDIA" in codes) == (status == 404)
        assert record["verdict"] == ("slop" if status == 404 else "cant_tell")


# -- G1: copy (W4-P5-15) -------------------------------------------------

def test_ai_chrome_fires_on_catalogue_terms() -> None:
    term = _first("ai_chrome_terms")
    state = measure_state(probe([el(text=f"Try our {term} today")]))
    codes, _record = fired_codes(state)
    assert "SLOP_AI_CHROME" in codes


def test_copy_cadence_counts_rebuttals_app_wide() -> None:
    states = []
    for index in range(3):
        states.append({
            "url": f"https://app.example.test/{index}",
            "viewport": "desktop1280",
            "elements": [{
                "element_id": "e0", "verdict": "clean", "rules_fired": [],
                "area": 100.0, "label": "Not a tool. A platform.",
                "component": {"role": "p", "name": "", "region": "body",
                              "disabled": False, "style": {}},
            }],
            "page_signals": [],
        })
    compare_components(states)
    codes = [s["rule_id"] for s in states[0]["page_signals"]]
    assert "SLOP_COPY_CADENCE" in codes


# -- G2: media -----------------------------------------------------------

def test_low_res_and_stretched_media_fire() -> None:
    low = measure_state(probe([], [img(
        natural_width=100, natural_height=50, width=200, height=100,
    )]))
    codes, record = fired_codes(low, "img0")
    assert "SLOP_LOW_RES_MEDIA" in codes
    # One moderate tell alone never flags: clean, with the tell kept.
    assert record["verdict"] == "clean"
    assert record["lone_tells"][0]["rule_id"] == "SLOP_LOW_RES_MEDIA"

    stretched = measure_state(probe([], [img(
        natural_width=100, natural_height=100, width=200, height=100,
        object_fit="fill",
    )]))
    codes, _ = fired_codes(stretched, "img0")
    assert "SLOP_STRETCHED_IMAGE" in codes

    covered = measure_state(probe([], [img(
        natural_width=100, natural_height=100, width=200, height=100,
        object_fit="cover",
    )]))
    codes, _ = fired_codes(covered, "img0")
    assert "SLOP_STRETCHED_IMAGE" not in codes


def test_template_assets_fire_on_catalogue_hosts() -> None:
    host = _first("template_asset_hosts")
    state = measure_state(probe([], [img(src=f"https://{host}/hero.png")]))
    codes, _ = fired_codes(state, "img0")
    assert "SLOP_TEMPLATE_ASSETS" in codes


# -- G3: surface --------------------------------------------------------

def test_gradient_signature_fires_and_flags_via_strong_tier() -> None:
    state = measure_state(probe([el(
        width=800, height=200,
        background_image=(
            "linear-gradient(90deg, rgb(99, 102, 241) 0%, "
            "rgb(168, 85, 247) 100%)"
        ),
    )]))
    codes, record = fired_codes(state)
    assert "SLOP_GRADIENT_SIGNATURE" in codes
    # A single strong-tier minor satisfies the gate on its own.
    assert record["verdict"] == "slop_minor"


def test_glass_glow_needs_three_panels() -> None:
    panel = dict(
        backdrop_filter="blur(12px)",
        own_background="rgba(255, 255, 255, 0.5)",
        width=200, height=100,
    )
    two = measure_state(probe([el(**panel), el(**panel)]))
    assert "SLOP_GLASS_GLOW" not in fired_codes(two)[0]
    three = measure_state(probe([el(**panel), el(**panel), el(**panel)]))
    assert "SLOP_GLASS_GLOW" in fired_codes(three)[0]


def test_motion_tells_and_microstates_and_flat_type() -> None:
    state = measure_state(probe(
        [el(kind="interactive", tag="button", role="button", name="Buy")]
        + [el(text=f"Body copy {i}", font_weight=400) for i in range(8)],
        motion={"transition_all": True, "overshoot_timing": False,
                "infinite_animation": False},
        stylesheets=[{"readable": True, "hover_interactive": False,
                      "focus_visible": False}],
    ))
    codes = signal_codes(state)
    assert "SLOP_MOTION_TELLS" in codes
    assert "SLOP_NO_MICROSTATES" in codes
    assert "SLOP_FLAT_TYPE" in codes


def test_microstates_confidence_gate_suppresses_unreadable_sheets() -> None:
    state = measure_state(probe(
        [el(kind="interactive", tag="button", role="button", name="Buy")],
        stylesheets=[{"readable": False, "hover_interactive": False,
                      "focus_visible": False}],
    ))
    assert "SLOP_NO_MICROSTATES" not in signal_codes(state)


def test_editorial_cluster_and_acid_dark() -> None:
    editorial = measure_state(probe(
        [
            el(tag="h1", role="h1", text="Welcome",
               font_family="Georgia, serif", font_size=40),
            el(kind="interactive", tag="button", role="button", name="Buy",
               background="rgb(193, 95, 60)"),
        ],
        document_background="rgb(252, 248, 240)",
    ))
    assert "SLOP_EDITORIAL_CLUSTER" in signal_codes(editorial)

    acid = measure_state(probe(
        [
            el(text="Dark page copy", color="rgb(240, 240, 240)"),
            el(kind="interactive", tag="button", role="button", name="Buy",
               background="rgb(180, 255, 0)"),
        ],
        document_background="rgb(10, 10, 12)",
    ))
    assert "SLOP_ACID_DARK" in signal_codes(acid)


def test_side_tab_border_fires() -> None:
    borders = {
        side: {"width": "0px", "color": "rgb(0, 0, 0)"}
        for side in ("top", "right", "bottom")
    }
    borders["left"] = {"width": "4px", "color": "rgb(230, 60, 60)"}
    state = measure_state(probe([el(borders=borders, width=300, height=80)]))
    codes, _ = fired_codes(state)
    assert "SLOP_SIDE_TAB_BORDER" in codes


# -- G4: layout ----------------------------------------------------------

def test_alignment_and_spacing_rhythm() -> None:
    siblings = [
        el(x=0, y=0, parent_key="div:0"),
        el(x=4, y=0, parent_key="div:0"),
    ]
    state = measure_state(probe(siblings))
    assert "SLOP_ALIGNMENT" in signal_codes(state)

    buttons = [
        el(kind="interactive", tag="button", role="button",
           name=f"B{i}", padding="8px 16px")
        for i in range(4)
    ] + [el(kind="interactive", tag="button", role="button",
            name="Odd", padding="20px 16px")]
    state = measure_state(probe(buttons))
    assert "SLOP_SPACING_RHYTHM" in signal_codes(state)


def test_uniform_rhythm_and_centred_layout() -> None:
    sections = [
        {"tag": "section", "y": i * 300, "height": 200,
         "padding_top": 40, "padding_bottom": 40}
        for i in range(4)
    ]
    state = measure_state(probe([], sections=sections))
    assert "SLOP_UNIFORM_RHYTHM" in signal_codes(state)

    long_text = " ".join(["word"] * 30)
    blocks = [
        el(tag="p", text=long_text, text_align="center"),
        el(tag="p", text="Short centred", text_align="center"),
        el(tag="p", text="Left aligned body copy here"),
    ]
    state = measure_state(probe(blocks))
    assert "SLOP_CENTRED_LAYOUT" in signal_codes(state)


def test_centred_hero_and_card_grid_and_uniform_surface() -> None:
    hero = [
        el(tag="span", text="NEW", x=590, y=100, width=100, height=24,
           border_radius="999px"),
        el(tag="h1", role="h1", text="Big promise", x=340, y=140,
           width=600, height=60, font_size=48, text_align="center"),
        el(tag="p", text="A centred supporting paragraph", x=440, y=220,
           width=400, height=24, text_align="center"),
        el(kind="interactive", tag="button", role="button", name="Start",
           x=540, y=260, width=200, height=44),
    ]
    state = measure_state(probe(hero))
    assert "SLOP_CENTRED_HERO" in signal_codes(state)

    cards = [
        el(x=i * 320, width=300, height=180, parent_key="div:1",
           child_tags=["svg", "span"], text=f"Card {i}")
        for i in range(3)
    ]
    state = measure_state(probe(cards))
    assert "SLOP_CARD_GRID" in signal_codes(state)

    elevated = [
        el(role=role, kind="interactive" if role == "button" else "text",
           tag="div", box_shadow="0px 2px 8px 0px rgba(0, 0, 0, 0.2)",
           border_radius="12px", width=200, height=100)
        for role in ("button", "link", "textbox", "button", "link",
                     "textbox", "button", "link")
    ]
    state = measure_state(probe(elevated))
    assert "SLOP_UNIFORM_SURFACE" in signal_codes(state)


def test_mock_chrome_dots_and_empty_visual() -> None:
    dots = [
        el(width=12, height=12, border_radius="50%",
           background=colour, parent_key="div:2", x=i * 20)
        for i, colour in enumerate(
            ("rgb(255, 0, 0)", "rgb(255, 200, 0)", "rgb(0, 200, 0)"),
        )
    ]
    state = measure_state(probe(dots))
    assert "SLOP_MOCK_CHROME" in signal_codes(state)

    state = measure_state(probe([el(
        width=400, height=300, text="",
        background_image="linear-gradient(180deg, rgb(240, 240, 240), rgb(220, 220, 220))",
    )]))
    codes, _ = fired_codes(state)
    assert "SLOP_EMPTY_VISUAL" in codes


# -- G5: discipline ------------------------------------------------------

def test_style_inconsistency_and_type_discipline() -> None:
    buttons = [
        el(kind="interactive", tag="button", role="button", name="A",
           background="rgb(10, 10, 10)", own_background="rgb(10, 10, 10)",
           border_radius="4px"),
        el(kind="interactive", tag="button", role="button", name="B",
           background="rgb(200, 0, 0)", own_background="rgb(200, 0, 0)",
           border_radius="16px"),
    ]
    state = measure_state(probe(buttons))
    assert "SLOP_STYLE_INCONSISTENCY" in signal_codes(state)

    texts = [
        el(text="One", font_family="Inter, sans-serif"),
        el(text="Two", font_family="Georgia, serif"),
        el(text="Three", font_family="Roboto Mono, monospace"),
    ]
    state = measure_state(probe(texts))
    assert "SLOP_TYPE_DISCIPLINE" in signal_codes(state)


def test_component_fingerprints_and_colour_discipline_app_wide() -> None:
    states = []
    for index in range(5):
        colour = f"rgb({index + 1}, {index + 1}, {index + 1})"
        states.append({
            "url": f"https://app.example.test/{index}",
            "viewport": "desktop1280",
            "elements": [{
                "element_id": "e0", "verdict": "clean", "rules_fired": [],
                "area": 100.0, "label": "Buy",
                "component": {
                    "role": "button", "name": "Buy", "region": "body",
                    "disabled": False,
                    "style": {"background": colour, "border_radius": "4px",
                              "font_family": "Inter", "padding": "8px",
                              "color": "rgb(20, 20, 20)", "font_size": 16,
                              "font_weight": 400},
                },
            }],
            "page_signals": [],
        })
    compare_components(states)
    codes = [s["rule_id"] for s in states[0]["page_signals"]]
    assert "SLOP_COMPONENT_FINGERPRINTS" in codes
    assert "SLOP_COLOUR_DISCIPLINE" in codes


def test_default_font_bundle_form() -> None:
    family = _first("default_fonts")
    state = measure_state(probe([
        el(tag="h1", role="h1", text="Heading", font_size=40,
           font_family=f"{family}, sans-serif"),
        el(text="Body copy in the same family",
           font_family=f"{family}, sans-serif"),
        el(text="More body copy", font_family=f"{family}, sans-serif"),
    ]))
    assert "SLOP_DEFAULT_FONT" in signal_codes(state)


# -- G6: proof + chrome --------------------------------------------------

def test_fabricated_proof_avatar_and_name_arms() -> None:
    host = _first("fake_face_hosts")
    state = measure_state(probe([], [img(
        src=f"https://{host}/face-1.png", width=48, height=48,
    )]))
    codes, record = fired_codes(state, "img0")
    assert "SLOP_FABRICATED_PROOF" in codes
    assert record["verdict"] == "slop"

    name = _first("placeholder_names")
    block = [
        el(text=f"“This product changed everything for us.”",
           parent_key="div:7"),
        el(text=name, parent_key="div:7"),
        el(text="CEO, Example Inc.", parent_key="div:7"),
    ]
    state = measure_state(probe(block))
    all_codes = [
        entry["rule_id"]
        for element in state["elements"] for entry in element["rules_fired"]
    ]
    assert "SLOP_FABRICATED_PROOF" in all_codes


def test_template_chrome_arms() -> None:
    eyebrow = [
        el(text="FEATURES", font_size=11, letter_spacing="1.04px",
           x=0, y=100, width=120, height=14),
        el(tag="h2", role="h2", text="Everything you need", x=0, y=120,
           width=400, height=32, font_size=32),
    ]
    state = measure_state(probe(eyebrow))
    codes, _ = fired_codes(state)
    assert "SLOP_TEMPLATE_CHROME" in codes
    assert state["tier_context"]["template_chrome_eyebrow_sections"] == 1

    for text in ("SEPTEMBER 9, 2026 - PRODUCT NEWS", "FEBRUARY 24, 2026 - KLAVIYO NEWS"):
        metadata = {
            **eyebrow[0], "text": text, "color": "rgb(200, 200, 200)",
            "background": "rgb(255, 255, 255)",
        }
        state = measure_state(probe([metadata, eyebrow[1]]))
        codes, record = fired_codes(state)
        assert "SLOP_TEMPLATE_CHROME" not in codes
        assert "SLOP_CONTRAST" in codes
        assert record["verdict"] == "clean"
        assert state["tier_context"]["template_chrome_eyebrow_sections"] == 0

    dotted = measure_state(probe([el(text="Docs · Guides · API · Blog")]))
    codes, _ = fired_codes(dotted)
    assert "SLOP_TEMPLATE_CHROME" in codes

    arrow = measure_state(probe([
        el(kind="interactive", tag="a", role="link", name="Learn more →",
           text="Learn more →"),
    ]))
    codes, _ = fired_codes(arrow)
    assert "SLOP_TEMPLATE_CHROME" in codes


# -- The gate + offsets (W4-P5-17) ---------------------------------------

def test_single_weak_tell_is_a_lone_tell_not_a_flag() -> None:
    """T-P5-S8: one weak tell records as a lone tell on a clean
    element — measured, kept, and never counted as a flag."""
    phrase = _first("generic_phrases")
    state = measure_state(probe([el(text=f"Our platform: {phrase}")]))
    codes, record = fired_codes(state)
    assert "SLOP_GENERIC_PHRASES" in codes
    assert record["verdict"] == "clean"
    assert [t["rule_id"] for t in record["lone_tells"]] == [
        "SLOP_GENERIC_PHRASES",
    ]


def test_two_distinct_minor_codes_flag() -> None:
    """T-P5-S8: two distinct verified minor codes satisfy the gate."""
    phrase = _first("generic_phrases")
    text = "🚀" * 60 + " " + phrase
    state = measure_state(probe([
        el(kind="interactive", tag="button", role="button",
           name=text, text=text),
    ]))
    codes, record = fired_codes(state)
    assert "SLOP_GENERIC_PHRASES" in codes
    assert "SLOP_EMOJI_ICONS" in codes
    assert record["verdict"] == "slop_minor"


def test_severe_is_never_offset() -> None:
    """T-P5-S8: a severe tell flags singly even on a page whose brand
    tokens offset everything offsettable."""
    state = measure_state(probe([el(text="Lorem ipsum dolor sit amet")]))
    codes, record = fired_codes(state)
    assert "SLOP_PLACEHOLDER_TEXT" in codes
    assert record["verdict"] == "slop"


def test_brand_token_offsets_gradient_and_side_tab() -> None:
    """T-P5-S10: an attested brand hue offsets the gradient tell —
    recorded with its reason, removed from the gate count."""
    gradient = el(
        width=800, height=200,
        background_image=(
            "linear-gradient(90deg, rgb(99, 102, 241) 0%, "
            "rgb(168, 85, 247) 100%)"
        ),
    )
    state = measure_state(
        probe([gradient]),
        brand_tokens={"palette_hexes": ["#6366F1"], "font_families": []},
    )
    codes, record = fired_codes(state)
    assert "SLOP_GRADIENT_SIGNATURE" in codes
    assert record["verdict"] == "clean"
    lone = record["lone_tells"][0]
    assert lone["rule_id"] == "SLOP_GRADIENT_SIGNATURE"
    assert lone["offset_reason"] == "brand_token"
    assert state["tier_context"]["gradient_brand_offset"] is True


def test_classes_enabled_allowlist() -> None:
    """T-P5-S10: with a classes allowlist, unlisted codes cannot
    fire at all; listed ones behave as usual."""
    phrase = _first("generic_phrases")
    state = measure_state(
        probe([el(text=f"Lorem ipsum and {phrase}")]),
        slop_classes_enabled=["GENERIC_PHRASES"],
    )
    codes, _ = fired_codes(state)
    assert codes == ["SLOP_GENERIC_PHRASES"]


# -- Calibration (W4-P5-18) ----------------------------------------------

def _calibration_page(*, extra_copy: str = ""):
    elements = [
        el(tag="h1", role="h1", text="Payments infrastructure for the internet",
           font_size=40, font_weight=700, x=0, y=40, width=700, height=48),
        el(text="Millions of companies use our software and APIs to accept "
                "payments, send payouts, and manage their businesses online.",
           y=100, width=600, height=48),
        el(kind="interactive", tag="button", role="button", name="Start now",
           background="rgb(10, 37, 64)", own_background="rgb(10, 37, 64)",
           border_radius="6px", y=170, width=120, height=40),
        el(kind="interactive", tag="a", role="link", name="Contact sales",
           y=170, x=140, width=120, height=40),
        el(text="Global payments", font_weight=600, y=240),
        el(text="Accept cards, wallets, and local payment methods in 135 "
                "currencies and 195 countries.", y=264, width=500),
        el(text=extra_copy, y=320, width=500) if extra_copy else
        el(text="Radar fraud prevention", font_weight=600, y=320),
        el(text="Billing and revenue", font_weight=600, y=360),
        el(text="Issue invoices, manage subscriptions, and recognise "
                "revenue automatically.", y=384, width=500),
    ]
    return probe(elements, [], words=400)


def test_calibration_pages_flag_zero_elements() -> None:
    """T-P5-S11: well-crafted pages in the Stripe/Linear shape flag
    zero elements; a single generic phrase in real copy is a lone
    tell, not a flag."""
    state = measure_state(_calibration_page())
    assert all(e["verdict"] == "clean" for e in state["elements"])
    assert not any(
        entry["rule_id"].startswith("SLOP_")
        for e in state["elements"] for entry in e["rules_fired"]
        if entry["severity"] == "severe"
    )
    phrase = _first("generic_phrases")
    state = measure_state(_calibration_page(extra_copy=f"Teams say: {phrase}"))
    flagged = [e for e in state["elements"] if e["verdict"] != "clean"]
    assert flagged == []
    lone = [
        t for e in state["elements"] for t in e.get("lone_tells", [])
    ]
    assert any(t["rule_id"] == "SLOP_GENERIC_PHRASES" for t in lone)


# -- Critic pinning (W4-P5-16) -------------------------------------------

def test_critic_notes_are_pinned_to_the_contract() -> None:
    """T-P5-S13: notes survive only with an allowed code, the fields
    the code must name, and the length caps."""
    valid = {
        "code": "TEMPLATE_STRUCTURE", "quote": "Default template.",
        "observation": "Sections follow the stock order.",
        "fields": {"sections": ["hero", "logos", "features", "pricing"]},
    }
    assert validate_critic_notes([valid]) == [valid]
    assert validate_critic_notes([{
        **valid, "code": "HIERARCHY_SHOUT",
        "fields": {"competing": ["headline"]},
    }]) == []
    assert validate_critic_notes([{
        **valid, "code": "GENERIC_IMAGERY",
        "fields": {"image": "a smiling team in an office"},
    }]) == []
    assert validate_critic_notes([{
        **valid, "code": "TILTED_MOCKUP", "fields": {"basis": "real"},
    }]) == []
    assert validate_critic_notes([{
        **valid, "code": "TILTED_MOCKUP", "fields": {"basis": "drawn"},
    }]) != []
    assert validate_critic_notes([{**valid, "quote": "x" * 281}]) == []
    assert validate_critic_notes([{**valid, "code": "NOT_A_CODE"}]) == []
    assert validate_critic_notes("not a list") == []
