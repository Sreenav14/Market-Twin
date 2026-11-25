"""The skill catalogue renderer (doc 22 section 7.3).

Pure: renders level-1 lines only — ``Skill: <name> — <description>``
— platform skills first, then the gate journey's skill, then the
rest by name. The catalogue is capped by character estimate against
SKILL_CATALOGUE_MAX_TOKENS (no tokeniser exists in the codebase —
prep P-13: character-estimate discipline, as the brief's own
BRIEF_MAX_CHARS); on overflow exactly one summary line names the
remainder. Level 2 (body_md) NEVER renders here: it appears only in
the selected Board item's execution context.
"""

from typing import Any

SKILL_CATALOGUE_MAX_TOKENS = 2000  # [J] doc 22 section 7.3
_CHARS_PER_TOKEN = 4  # character-estimate discipline (prep P-13)


def _line(entry: dict[str, Any]) -> str:
    catalogue = entry.get("catalogue")
    if isinstance(catalogue, dict):
        name = catalogue.get("name") or entry.get("name") or ""
        description = catalogue.get("description") or ""
    else:
        # Pre-Phase-3 entries carry name/description at the top level.
        name = entry.get("name") or ""
        description = entry.get("description") or ""
    return f"Skill: {name} — {description}"


def render_skill_catalogue(
    entries: list[Any], *, gate_skill_id: str | None = None
) -> list[str]:
    """The catalogue lines for a snapshot's active skill entries."""
    skills = [entry for entry in entries if isinstance(entry, dict)]
    platform = [e for e in skills if e.get("skill_kind") == "platform"]
    rest = [e for e in skills if e.get("skill_kind") != "platform"]
    gate = [
        e
        for e in rest
        if gate_skill_id is not None and e.get("skill_id") == gate_skill_id
    ]
    others = sorted(
        (e for e in rest if e not in gate),
        key=lambda e: str(e.get("name") or ""),
    )
    ordered = platform + gate + others
    lines: list[str] = []
    total = 0
    shown = 0
    cap = SKILL_CATALOGUE_MAX_TOKENS * _CHARS_PER_TOKEN
    for entry in ordered:
        line = _line(entry)
        if shown and total + len(line) > cap:
            break
        lines.append(line)
        total += len(line)
        shown += 1
    remaining = len(ordered) - shown
    if remaining:
        lines.append(
            f"+ {remaining} more active skills (catalogue cap) "
            "— full list via get_skill lookup."
        )
    return lines
