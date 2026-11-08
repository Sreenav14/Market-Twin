"""The persona factory (U-P5-03): generate definitions from the Board.

Given the states a completed Explore & Test run found, the factory
produces one definition per persona type. Journeys come from the
Board's state URLs (the pages that actually exist); conditions come
from the type alone (canonical, by code); the voice is a fixed
per-type template the owner can then edit. Generation is
deterministic — the same Board yields the same definitions — and it
never overwrites a definition the owner already has: existing
persona_ids are skipped, so re-running the factory after a re-test
only ADDS types the application does not have yet.
"""

from markettwin_shared.persona_definitions import (
    PERSONA_TYPES,
    PersonaDefinition,
    PersonaVoice,
    canonical_conditions,
)

_TYPE_VOICES: dict[str, tuple[str, str, str]] = {
    # type: (display name, perspective, focus)
    "first_time": (
        "First-time user",
        "I have never used this product before and I do not read help text.",
        "Whether each page explains what to do next, in plain words.",
    ),
    "expert": (
        "Expert user",
        "I use tools like this every day and I move fast.",
        "Whether anything slows down a task I already know how to do.",
    ),
    "impatient_mobile": (
        "Impatient mobile user",
        "I am on a small phone with a slow connection and little patience.",
        "Whether the important things load fast and stay tappable.",
    ),
    "keyboard_only": (
        "Keyboard-only user",
        "I navigate with Tab and Enter only; I cannot use a mouse.",
        "Whether everything important can be reached and used by keyboard.",
    ),
    "non_native": (
        "Non-native speaker",
        "English is not my first language; I read slowly and literally.",
        "Whether labels and messages are simple and unambiguous.",
    ),
}

_MAX_JOURNEYS = 12


def generate_definitions(
    *, state_urls: list[str], existing_persona_ids: set[str],
) -> list[PersonaDefinition]:
    """One definition per type the application does not have yet."""

    journeys = tuple(dict.fromkeys(state_urls))[:_MAX_JOURNEYS]
    generated: list[PersonaDefinition] = []
    for persona_type in PERSONA_TYPES:
        persona_id = f"{persona_type}-1"
        if persona_id in existing_persona_ids:
            continue
        name, perspective, focus = _TYPE_VOICES[persona_type]
        generated.append(PersonaDefinition(
            persona_id=persona_id,
            name=name,
            type=persona_type,  # type: ignore[arg-type]
            enabled=True,
            voice=PersonaVoice(perspective=perspective, focus=focus),
            conditions=canonical_conditions(persona_type),
            journeys=journeys,
        ))
    return generated
