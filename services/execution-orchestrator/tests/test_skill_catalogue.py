"""Phase 3 catalogue tests (doc 22 section 7.3, 17): T-CT1 — the
catalogue renders level-1 lines only, platform first, then the gate
journey's skill, then name order, and the cap produces exactly one
summary line. T-CT2 — body_md (level 2) appears in NO brief or
catalogue context; it exists only in the served entry itself (the
selected item's execution context reads the entry, not a render).
"""

from types import SimpleNamespace

from markettwin_execution_orchestrator.workflow.app_plan import build_map_brief
from markettwin_execution_orchestrator.workflow.skill_catalogue import (
    SKILL_CATALOGUE_MAX_TOKENS,
    render_skill_catalogue,
)

BODY_MARKER = "SECRET-BODY-CONTENT"


def _entry(name, *, kind="journey", skill_id=None, description=None):
    return {
        "name": name,
        "skill_id": skill_id or f"id-{name}",
        "skill_kind": kind,
        "lifecycle_status": "active",
        "catalogue": {
            "name": name,
            "description": description or f"Does {name}",
        },
        "package": {
            "name": name,
            "description": description or f"Does {name}",
            "body_md": f"## Steps\n{BODY_MARKER} for {name}",
            "resources": [],
        },
        "definition": {"steps": []},
    }


def test_t_ct1_catalogue_ordering_platform_gate_then_name():
    entries = [
        _entry("zebra-journey"),
        _entry("login", kind="platform"),
        _entry("alpha-journey"),
        _entry("gate-journey", skill_id="gate-id"),
    ]
    lines = render_skill_catalogue(entries, gate_skill_id="gate-id")
    assert lines == [
        "Skill: login — Does login",
        "Skill: gate-journey — Does gate-journey",
        "Skill: alpha-journey — Does alpha-journey",
        "Skill: zebra-journey — Does zebra-journey",
    ]


def test_t_ct1_catalogue_cap_emits_exactly_one_summary_line():
    entries = [
        _entry(f"skill-{index:03d}", description="x" * 400)
        for index in range(100)
    ]
    lines = render_skill_catalogue(entries)
    summaries = [line for line in lines if line.startswith("+ ")]
    assert len(summaries) == 1
    shown = len(lines) - 1
    assert summaries[0] == (
        f"+ {100 - shown} more active skills (catalogue cap) "
        "— full list via get_skill lookup."
    )
    total_chars = sum(len(line) for line in lines if not line.startswith("+ "))
    assert total_chars <= SKILL_CATALOGUE_MAX_TOKENS * 4 + 500


def test_equal_gate_entries_are_each_rendered():
    entry = _entry("gate", skill_id="gate-id")
    lines = render_skill_catalogue([entry, dict(entry)], gate_skill_id="gate-id")
    assert len(lines) == 2
    assert lines[0] == lines[1]


def test_t_ct2_body_md_never_renders_in_catalogue_or_brief():
    entries = [_entry("checkout"), _entry("login", kind="platform")]
    lines = render_skill_catalogue(entries)
    assert all(BODY_MARKER not in line for line in lines)
    app_map = {
        "counts": {"expected": 2, "reachable": 2},
        "pages": [],
        "journeys": [],
        "skills": entries,
        "skills_withheld": 0,
        "release_state": "partial",
        "release_scope": "inventory",
    }
    request = SimpleNamespace(app_map=app_map)
    brief = build_map_brief({}, request)
    assert BODY_MARKER not in brief
    assert "Skill: login — Does login" in brief
    assert "Skill: checkout — Does checkout" in brief
    # The body exists only on the served entry itself — the selected
    # item's execution context reads the entry, never a render.
    assert entries[0]["package"]["body_md"].count(BODY_MARKER) == 1
