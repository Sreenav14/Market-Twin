"""U-P5-02: canonical conditions + the score-key rejection battery."""

import pytest

from markettwin_shared.persona_definitions import (
    PERSONA_TYPES,
    canonical_conditions,
    dump_definition_yaml,
    parse_definition_yaml,
)

VOICE = {"perspective": "I have never seen this product before.",
         "focus": "Whether each step explains itself."}


def _yaml(persona_type: str, **overrides: object) -> str:
    conditions = canonical_conditions(persona_type).model_dump(mode="json")
    document = {
        "persona_id": f"{persona_type}-1", "name": "Test persona",
        "type": persona_type, "enabled": True, "voice": VOICE,
        "conditions": conditions, "journeys": [],
    }
    document.update(overrides)
    import yaml

    return yaml.safe_dump(document)


@pytest.mark.parametrize("persona_type", PERSONA_TYPES)
def test_every_type_round_trips(persona_type: str) -> None:
    definition = parse_definition_yaml(_yaml(persona_type))
    assert definition.type == persona_type
    assert definition.conditions == canonical_conditions(persona_type)
    assert parse_definition_yaml(dump_definition_yaml(definition)) == definition


def test_impatient_mobile_carries_the_slow_4g_block() -> None:
    conditions = canonical_conditions("impatient_mobile")
    assert (conditions.viewport_width, conditions.viewport_height) == (320, 800)
    assert conditions.network is not None
    assert conditions.network.latency_ms == 150
    assert conditions.network.download_bps == 200_000


def test_edited_conditions_are_rejected() -> None:
    conditions = canonical_conditions("expert").model_dump(mode="json")
    conditions["viewport_width"] = 999
    with pytest.raises(ValueError, match="canonical"):
        parse_definition_yaml(_yaml("expert", conditions=conditions))


@pytest.mark.parametrize("banned", ["score", "rating", "verdict", "mean", "grade"])
def test_score_keys_are_rejected_anywhere(banned: str) -> None:
    with pytest.raises(ValueError, match="not allowed"):
        parse_definition_yaml(_yaml("expert", **{banned: 4}))
    nested = {"perspective": "x", "focus": "y", banned: 1}
    with pytest.raises(ValueError, match="not allowed"):
        parse_definition_yaml(_yaml("expert", voice=nested))


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ValueError):
        parse_definition_yaml(_yaml("expert", nickname="Speedy"))


def test_unknown_type_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_definition_yaml(_yaml("expert", type="impatient_desktop"))
