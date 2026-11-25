"""Phase 3 lookup test (doc 22 section 7.4, 17): T-CT3 — get_skill
returns the full package for a served (active) skill, returns a
withheld skill AS withheld (lifecycle named, no package), and
returns None for an unknown name.
"""

from markettwin_execution_orchestrator.workflow.map_lookup import get_skill

BLOCK = {
    "skills": [
        {
            "name": "checkout",
            "skill_id": "s-1",
            "skill_version_id": "v-3",
            "version_number": 3,
            "skill_kind": "journey",
            "lifecycle_status": "active",
            "catalogue": {"name": "checkout", "description": "Buys"},
            "definition": {"steps": [{"action": "navigate", "url": "/"}]},
            "package": {"body_md": "## Steps\n...", "resources": []},
        },
        {
            "name": "old-journey",
            "skill_id": "s-2",
            "lifecycle_status": "suspect",
            "definition": {"steps": []},
            "package": {"body_md": "must not leak"},
        },
    ],
    "skills_withheld": 4,
}


def test_t_ct3_served_skill_returns_the_full_package():
    entry = get_skill(BLOCK, "checkout")
    assert entry is not None
    assert entry["package"]["body_md"] == "## Steps\n..."
    assert entry["skill_version_id"] == "v-3"
    assert entry["lifecycle_status"] == "active"


def test_t_ct3_withheld_skill_is_returned_as_withheld():
    entry = get_skill(BLOCK, "old-journey")
    assert entry == {
        "name": "old-journey",
        "lifecycle_status": "suspect",
        "withheld": True,
    }
    assert "package" not in entry


def test_t_ct3_unknown_skill_returns_none():
    assert get_skill(BLOCK, "nope") is None
    assert get_skill({}, "checkout") is None
    assert get_skill(None, "checkout") is None
