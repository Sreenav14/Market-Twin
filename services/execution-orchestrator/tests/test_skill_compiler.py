"""Phase 3 compiler tests (doc 22 sections 6.1, 6.3, 17):
T-CM1 — compile-all compiles every journey of the map (1b compiled
only the gate journey), each version bound to the compiling map,
journey.skill_id set, a compile event per version. T-CM2 — a second
map version appends NEW versions to the SAME skill rows. T-CM3 —
platform registration is idempotent and kind 'platform'. T-CM4 — a
journey-compiled definition shape is refused at platform
registration.

The repository fake is an in-memory implementation of the
HarvestRepository surface the library uses.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from markettwin_database.models.knowledge import (
    AppMap,
    MapJourney,
    MapPage,
    MapPageState,
    Skill,
    SkillVersion,
)
from markettwin_execution_orchestrator.harvest.skill_library import (
    compile_all_journeys,
    register_platform_skill,
)


class FakeRepository:
    def __init__(self):
        self.skills: dict = {}
        self.versions: dict = {}
        self.journeys: dict = {}
        self.pages: list = []
        self.states: list = []
        self.states_by_id: dict = {}
        self.elements: dict = {}
        self.events: list = []

    # -- reads used by the library --
    async def list_journeys(self, map_id):
        return [j for j in self.journeys.values() if j.app_map_id == map_id]

    async def work_list(self, app_map):
        return [p for p in self.pages if p.app_map_id == app_map.id]

    async def list_states_for_map(self, map_id):
        return [s for s in self.states if s.app_map_id == map_id]

    async def get_state(self, state_id):
        return self.states_by_id.get(state_id)

    async def get_element(self, element_id):
        return self.elements.get(element_id)

    async def find_graph_skill(
        self, *, workspace_id, application_id, target_id, name
    ):
        for skill in self.skills.values():
            if (
                skill.workspace_id == workspace_id
                and skill.application_id == application_id
                and skill.target_id == target_id
                and skill.name == name
            ):
                return skill
        return None

    async def list_versions_for_skill(self, skill_id):
        return sorted(
            (v for v in self.versions.values() if v.skill_id == skill_id),
            key=lambda v: v.version_number,
        )

    async def latest_skill_version(self, skill_id):
        versions = await self.list_versions_for_skill(skill_id)
        return versions[-1] if versions else None

    # -- writes used by the library --
    async def create_skill_with_version(
        self, app_map, *, name, definition, package, created_by_user_id
    ):
        skill = Skill(
            id=uuid4(),
            workspace_id=app_map.workspace_id,
            name=name,
            status="active",
            application_id=app_map.application_id,
            target_id=app_map.target_id,
            app_map_id=app_map.id,
            skill_kind="journey",
        )
        version = SkillVersion(
            id=uuid4(),
            workspace_id=app_map.workspace_id,
            skill_id=skill.id,
            version_number=1,
            status="draft",
            definition_json=definition,
            generation_metadata={},
            lifecycle_status="draft",
            package=package,
            heal_count=0,
            replay_count=0,
        )
        self.skills[skill.id] = skill
        self.versions[version.id] = version
        return skill, version

    async def create_platform_skill(
        self, app_map, *, name, definition, package
    ):
        skill, version = await self.create_skill_with_version(
            app_map,
            name=name,
            definition=definition,
            package=package,
            created_by_user_id=None,
        )
        skill.skill_kind = "platform"
        version.app_map_id = app_map.id
        return skill, version

    async def append_skill_version(
        self,
        skill,
        app_map,
        *,
        definition,
        package,
        heal_of_version_id=None,
        source="phase-3-compile",
    ):
        versions = await self.list_versions_for_skill(skill.id)
        version = SkillVersion(
            id=uuid4(),
            workspace_id=skill.workspace_id,
            skill_id=skill.id,
            version_number=(versions[-1].version_number + 1) if versions else 1,
            status="draft",
            definition_json=definition,
            generation_metadata={"source": source},
            lifecycle_status="draft",
            package=package,
            heal_count=0,
            replay_count=0,
            app_map_id=app_map.id,
            heal_of_version_id=heal_of_version_id,
        )
        self.versions[version.id] = version
        skill.app_map_id = app_map.id
        return version

    async def attach_journey_skill(self, journey_id, skill_id):
        self.journeys[journey_id].skill_id = skill_id

    async def update_skill_version(self, version_id, **fields):
        version = self.versions[version_id]
        for key, value in fields.items():
            setattr(version, key, value)

    async def insert_usage_event(
        self,
        version,
        *,
        kind,
        from_status,
        to_status,
        result=None,
        run_id=None,
        job_ref=None,
        model_calls=0,
        model_tokens=0,
        payload=None,
    ):
        self.events.append(
            {
                "kind": kind,
                "from_status": from_status,
                "to_status": to_status,
                "result": result,
                "skill_version_id": version.id,
                "payload": dict(payload or {}),
            }
        )


def _map(version_number=1):
    return AppMap(
        id=uuid4(),
        workspace_id=uuid4(),
        application_id=uuid4(),
        target_id=uuid4(),
        version_number=version_number,
        status="ready",
        base_url="https://example.com/",
        builder_version="census-1a.1",
        census_config={},
        census_metrics={},
        pattern_stats={},
        gate_metrics={},
    )


def _seed_graph(repo: FakeRepository, app_map, *, journey_names):
    """Base page + one terminal page per journey, default states,
    one clickable element per journey, and the journey rows."""
    base_page = MapPage(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        app_map_id=app_map.id,
        canonical_url="https://example.com/",
        route_pattern="/",
        source_kinds=["seed"],
        crawl_status="fetch_ok",
    )
    repo.pages.append(base_page)
    base_state = MapPageState(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        app_map_id=app_map.id,
        map_page_id=base_page.id,
        state_key="default",
        state_id="state-base",
        element_signature="link|Home",
    )
    repo.states.append(base_state)
    repo.states_by_id[base_state.id] = base_state
    journeys = []
    for index, name in enumerate(journey_names):
        terminal_page = MapPage(
            id=uuid4(),
            workspace_id=app_map.workspace_id,
            application_id=app_map.application_id,
            target_id=app_map.target_id,
            app_map_id=app_map.id,
            canonical_url=f"https://example.com/goal-{index}",
            route_pattern=f"/goal-{index}",
            source_kinds=["link"],
            crawl_status="fetch_ok",
        )
        repo.pages.append(terminal_page)
        terminal_state = MapPageState(
            id=uuid4(),
            workspace_id=app_map.workspace_id,
            app_map_id=app_map.id,
            map_page_id=terminal_page.id,
            state_key="default",
            state_id=f"state-goal-{index}",
            element_signature="heading|Done",
        )
        repo.states.append(terminal_state)
        repo.states_by_id[terminal_state.id] = terminal_state
        element = SimpleNamespace(
            id=uuid4(),
            role="link",
            name=f"Goal {index}",
            locators=[{"kind": "role_name", "value": f"link|Goal {index}"}],
        )
        repo.elements[element.id] = element
        journey = MapJourney(
            id=uuid4(),
            workspace_id=app_map.workspace_id,
            application_id=app_map.application_id,
            target_id=app_map.target_id,
            app_map_id=app_map.id,
            name=name,
            steps=[
                {
                    "map_page_state_id": str(base_state.id),
                    "element_id": str(element.id),
                    "action": "click",
                    "value_source": "none",
                }
            ],
            preconditions=[],
            success_state_id=terminal_state.id,
            selection="rule",
        )
        repo.journeys[journey.id] = journey
        journeys.append(journey)
    return journeys


@pytest.mark.asyncio
async def test_t_cm1_compile_all_compiles_every_journey():
    repo = FakeRepository()
    app_map = _map()
    journeys = _seed_graph(
        repo, app_map, journey_names=["Reach pricing", "Reach demo", "Reach signup"]
    )
    counts = await compile_all_journeys(
        repo, app_map, application_name="Example"
    )
    assert counts == {"compiled": 3, "skipped": 0, "failed": 0}
    assert len(repo.skills) == 3
    assert len(repo.versions) == 3
    for journey in journeys:
        assert journey.skill_id is not None
    for version in repo.versions.values():
        assert version.lifecycle_status == "draft"
        assert version.app_map_id == app_map.id
        assert version.definition_json["source_journey_id"] is not None
    compile_events = [e for e in repo.events if e["kind"] == "compile"]
    assert len(compile_events) == 3
    # A second pass over the same map compiles nothing again.
    counts = await compile_all_journeys(
        repo, app_map, application_name="Example"
    )
    assert counts == {"compiled": 0, "skipped": 3, "failed": 0}


@pytest.mark.asyncio
async def test_t_cm2_second_map_appends_versions_to_the_same_skills():
    repo = FakeRepository()
    map_v1 = _map(version_number=1)
    _seed_graph(repo, map_v1, journey_names=["Reach pricing"])
    await compile_all_journeys(repo, map_v1, application_name="Example")
    map_v2 = _map(version_number=2)
    map_v2.workspace_id = map_v1.workspace_id
    map_v2.application_id = map_v1.application_id
    map_v2.target_id = map_v1.target_id
    _seed_graph(repo, map_v2, journey_names=["Reach pricing"])
    counts = await compile_all_journeys(
        repo, map_v2, application_name="Example"
    )
    assert counts == {"compiled": 1, "skipped": 0, "failed": 0}
    assert len(repo.skills) == 1  # found-or-created, never duplicated
    versions = await repo.list_versions_for_skill(
        next(iter(repo.skills.values())).id
    )
    assert [v.version_number for v in versions] == [1, 2]
    assert versions[1].app_map_id == map_v2.id
    assert versions[1].lifecycle_status == "draft"


@pytest.mark.asyncio
async def test_t_cm3_platform_registration_is_idempotent():
    repo = FakeRepository()
    app_map = _map()
    definition = {"kind": "login_skill", "form_signature": "abc"}
    package = {"kind": "login_skill"}
    skill, version = await register_platform_skill(
        repo, app_map, name="login", definition=definition, package=package
    )
    assert skill.skill_kind == "platform"
    assert version.lifecycle_status == "draft"
    again_skill, again_version = await register_platform_skill(
        repo, app_map, name="login", definition=definition, package=package
    )
    assert again_skill.id == skill.id
    assert again_version.id == version.id
    assert len(repo.skills) == 1


@pytest.mark.asyncio
async def test_t_cm4_platform_registration_refuses_a_journey_shape():
    repo = FakeRepository()
    app_map = _map()
    journey_shaped = {
        "source_journey_id": str(uuid4()),
        "locator_bindings": [],
        "steps": [],
    }
    with pytest.raises(ValueError, match="platform_registration_refused"):
        await register_platform_skill(
            repo,
            app_map,
            name="sneaky",
            definition=journey_shaped,
            package={},
        )
    assert repo.skills == {}
