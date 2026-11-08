"""Persona definitions (U-P5-02): condition types, canonical blocks,
and the YAML contract.

A persona is a profile of REAL conditions, not an invented character.
The five types are fixed; the condition block for each type is built
BY CODE from the type alone, and validation rejects any definition
whose conditions differ from the canonical block — an owner editing
the YAML can change the voice (prompt text), the name, and whether
the persona is enabled, but can never invent conditions or smuggle
in a score: any score-like key anywhere in the document is rejected.
"""

from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

PersonaType = Literal[
    "first_time", "expert", "impatient_mobile", "keyboard_only", "non_native",
]

PERSONA_TYPES: tuple[str, ...] = (
    "first_time", "expert", "impatient_mobile", "keyboard_only", "non_native",
)

# Keys that would turn an impression into a score. Their presence
# anywhere in a definition document is a hard validation failure.
BANNED_KEYS = frozenset({
    "score", "scores", "rating", "ratings", "grade", "grades",
    "verdict", "mean", "average", "points", "rank_score",
})


class NetworkCondition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    latency_ms: int = Field(ge=0)
    download_bps: int = Field(gt=0)
    upload_bps: int = Field(gt=0)


class PersonaConditions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    viewport_width: int = Field(gt=0)
    viewport_height: int = Field(gt=0)
    locale: str
    input: Literal["pointer", "touch", "keyboard"]
    network: NetworkCondition | None = None


def canonical_conditions(persona_type: str) -> PersonaConditions:
    """The one true condition block per type. Built by code; a YAML
    document restating anything else is invalid."""

    if persona_type == "first_time":
        return PersonaConditions(
            viewport_width=1280, viewport_height=800, locale="en-US",
            input="pointer",
        )
    if persona_type == "expert":
        return PersonaConditions(
            viewport_width=1440, viewport_height=900, locale="en-US",
            input="pointer",
        )
    if persona_type == "impatient_mobile":
        return PersonaConditions(
            viewport_width=320, viewport_height=800, locale="en-US",
            input="touch",
            network=NetworkCondition(
                label="Slow 4G", latency_ms=150,
                download_bps=200_000, upload_bps=93_750,
            ),
        )
    if persona_type == "keyboard_only":
        return PersonaConditions(
            viewport_width=1280, viewport_height=800, locale="en-US",
            input="keyboard",
        )
    if persona_type == "non_native":
        return PersonaConditions(
            viewport_width=1280, viewport_height=800, locale="es-ES",
            input="pointer",
        )
    raise ValueError(f"Unknown persona type: {persona_type}")


class PersonaVoice(BaseModel):
    """The editable prompt text: who is speaking and what they notice.
    Words only — the validator guarantees no numbers-as-judgement can
    hide here either (voice values are plain strings)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    perspective: str = Field(min_length=1, max_length=400)
    focus: str = Field(min_length=1, max_length=400)


class PersonaDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    persona_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    type: PersonaType
    enabled: bool = True
    voice: PersonaVoice
    conditions: PersonaConditions
    journeys: tuple[str, ...] = ()

    @model_validator(mode="after")
    def conditions_must_be_canonical(self) -> "PersonaDefinition":
        if self.conditions != canonical_conditions(self.type):
            raise ValueError(
                "Conditions must be the canonical block for the persona "
                "type; they are chosen by the type, never edited.",
            )
        return self


def _reject_banned_keys(node: Any, path: str = "") -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key).lower() in BANNED_KEYS:
                raise ValueError(
                    f"Score-like key {key!r} at {path or '<root>'} is not "
                    "allowed in a persona definition.",
                )
            _reject_banned_keys(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _reject_banned_keys(value, f"{path}[{index}]")


def parse_definition_yaml(document: str) -> PersonaDefinition:
    """Parse + fully validate one YAML definition document."""

    data = yaml.safe_load(document)
    if not isinstance(data, dict):
        raise ValueError("A persona definition must be a YAML mapping.")
    _reject_banned_keys(data)
    return PersonaDefinition.model_validate(data)


def dump_definition_yaml(definition: PersonaDefinition) -> str:
    data = definition.model_dump(mode="json")
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
