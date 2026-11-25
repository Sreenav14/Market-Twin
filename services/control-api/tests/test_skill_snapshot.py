"""Phase 3 snapshot test (doc 22 section 7.2, 17): T-N1 — the
snapshot's skills block serves ACTIVE versions only, in the section
7.2 entry shape, with skills_withheld as the non-active version
COUNT (an int, not stubs); journey blocks carry skill_id; and the
byte cap strips skill packages before dropping entries, counting
every drop into skills_withheld.

The repository is faked at the module seam (the extension builds its
own MapRepository from the session); the fake answers in the
extension's pinned query order.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from markettwin_control_api.api import test_run as test_run_module


class _FakeRepository:
    def __init__(self, factory):
        self._factory = factory

    async def harvest_counts(self, map_id):
        return {"visited": 3}

    async def count_expectations(self, map_id):
        return 0

    async def snapshot_page_elements(self, state_ids):
        return []

    async def snapshot_journeys(self, map_id):
        return [
            SimpleNamespace(
                name="Reach pricing",
                skill_id=self._skill_id,
                intent="Buy",
                selection="rule",
                success_state_id=None,
                steps=[],
            )
        ]

    async def latest_active_skills(
        self, *, workspace_id, application_id, target_id
    ):
        skill = SimpleNamespace(
            id=self._skill_id,
            name="reach-pricing",
            skill_kind="journey",
        )
        version = SimpleNamespace(
            id=self._version_id,
            version_number=2,
            definition_json={"steps": []},
            package={
                "name": "reach-pricing",
                "description": "Reach the pricing page",
                "body_md": "## Steps",
            },
        )
        return [(skill, version)], 5


@pytest.mark.asyncio
async def test_t_n1_snapshot_serves_active_skills_and_counts_withheld(
    monkeypatch,
):
    skill_id = uuid4()
    version_id = uuid4()
    _FakeRepository._skill_id = skill_id
    _FakeRepository._version_id = version_id
    monkeypatch.setattr(
        test_run_module.map_repository, "MapRepository", _FakeRepository
    )
    monkeypatch.setattr(
        test_run_module.map_repository,
        "session_factory_for",
        lambda session: None,
    )
    app_map = SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        application_id=uuid4(),
        target_id=uuid4(),
        harvest_metrics=None,
    )
    page = SimpleNamespace(
        id=uuid4(), harvest_status="visited", canonical_url="https://x/"
    )
    block: dict[str, object] = {"counts": {}, "pages": [{}]}
    await test_run_module._extend_snapshot_block_with_harvest(
        SimpleNamespace(), app_map, block, [page], []
    )
    skills = block["skills"]
    assert len(skills) == 1
    entry = skills[0]
    assert entry["name"] == "reach-pricing"
    assert entry["skill_id"] == str(skill_id)
    assert entry["skill_version_id"] == str(version_id)
    assert entry["version_number"] == 2
    assert entry["skill_kind"] == "journey"
    assert entry["lifecycle_status"] == "active"
    assert entry["catalogue"] == {
        "name": "reach-pricing",
        "description": "Reach the pricing page",
    }
    assert entry["package"]["body_md"] == "## Steps"
    assert block["skills_withheld"] == 5
    assert isinstance(block["skills_withheld"], int)
    journeys = block["journeys"]
    assert journeys[0]["skill_id"] == str(skill_id)


def test_t_n1_byte_cap_strips_packages_then_counts_drops(monkeypatch):
    monkeypatch.setattr(
        test_run_module.map_repository, "SNAPSHOT_MAP_MAX_BYTES", 400
    )
    block: dict[str, object] = {
        "skills": [
            {
                "name": "a",
                "lifecycle_status": "active",
                "package": {"body_md": "x" * 300},
                "definition": {"steps": []},
            },
            {
                "name": "b",
                "lifecycle_status": "active",
                "package": {"body_md": "y" * 300},
                "definition": {"steps": []},
            },
        ],
        "skills_withheld": 5,
    }
    test_run_module._enforce_snapshot_byte_cap(block)
    # Packages are stripped first; entries survive if the block fits.
    assert all("package" not in entry for entry in block["skills"])
    if block["skills"]:
        assert block["skills_withheld"] == 5
    else:
        assert block["skills_withheld"] == 7
    assert block["skills_truncated"] is True
