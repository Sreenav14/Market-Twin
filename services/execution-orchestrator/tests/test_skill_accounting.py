"""Phase 3 usage accounting (doc 22 sections 12.1, 17): T-AC1 —
every model call the library makes is attributable on the usage
ledger to a skill and a version. The heal diagnosis is the only
model-calling path in the library; its spend must land as a
heal_diagnosis event carrying the call count and the suspect
version's identity — including when the diagnosis proposal is
refused by validation (the call was still spent).
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
from markettwin_execution_orchestrator.harvest.harvest_replay import (
    ReplayAttempt,
)
from markettwin_execution_orchestrator.harvest.skill_reverify import (
    heal_cycle_for_suspect,
)


class FakeRepository:
    """The heal cycle's repository surface (same shape as the
    reverify tests' fake): rows in dicts, usage events captured."""

    def __init__(self):
        self.skills: dict = {}
        self.versions: dict = {}
        self.journeys: dict = {}
        self.pages: list = []
        self.states: list = []
        self.replays: list = []
        self.events: list = []

    async def get_skill_version(self, version_id):
        return self.versions.get(version_id)

    async def get_journey(self, journey_id):
        return self.journeys.get(journey_id)

    async def apply_skill_transition(self, version_id, *, fields, event):
        version = self.versions[version_id]
        for key, value in fields.items():
            setattr(version, key, value)
        self.events.append(
            {
                **event,
                "skill_version_id": version_id,
                "skill_id": version.skill_id,
            }
        )
        return version

    async def insert_usage_event(
        self, version, *, kind, from_status, to_status, result=None,
        run_id=None, job_ref=None, model_calls=0, model_tokens=0,
        payload=None,
    ):
        self.events.append(
            {
                "kind": kind,
                "from_status": from_status,
                "to_status": to_status,
                "result": result,
                "model_calls": model_calls,
                "skill_id": version.skill_id,
                "skill_version_id": version.id,
                "payload": dict(payload or {}),
            }
        )

    async def update_skill_version(self, version_id, **fields):
        version = self.versions[version_id]
        for key, value in fields.items():
            setattr(version, key, value)

    async def insert_replay(
        self, app_map, *, skill_version_id, result, failure_step,
        failure_site, heal_cycle, context_kind, model_calls, started_at,
        finished_at,
    ):
        row = SimpleNamespace(
            id=uuid4(),
            skill_version_id=skill_version_id,
            result=result,
            failure_step=failure_step,
            failure_site=failure_site,
            started_at=started_at,
        )
        self.replays.append(row)
        return row

    async def list_replays_for_version(self, version_id):
        return [r for r in self.replays if r.skill_version_id == version_id]

    async def append_skill_version(
        self, skill, app_map, *, definition, package,
        heal_of_version_id=None, source="phase-3-compile",
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
        return version

    async def list_versions_for_skill(self, skill_id):
        return sorted(
            (v for v in self.versions.values() if v.skill_id == skill_id),
            key=lambda v: v.version_number,
        )

    async def work_list(self, app_map):
        return [p for p in self.pages if p.app_map_id == app_map.id]

    async def list_states_for_map(self, map_id):
        return [s for s in self.states if s.app_map_id == map_id]

    async def list_journeys(self, map_id):
        return [j for j in self.journeys.values() if j.app_map_id == map_id]


class FakeExecutor:
    async def run_once(self, *, definition):
        return ReplayAttempt(ok=True)


def _definition(source_journey_id):
    return {
        "case_id": "reach_pricing_x",
        "feature_key": "map_journey_x",
        "title": "Journey: Reach pricing",
        "kind": "happy_path",
        "steps": [
            {"action": "navigate", "url": "https://example.com/"},
            {"action": "click", "target": {"role": "link", "name": "Old"}},
        ],
        "expected": [],
        "safety": "non_destructive",
        "estimated_seconds": 30,
        "locator_bindings": [
            {
                "order": 2,
                "page_url": "https://example.com/",
                "element": {"role": "link", "name": "Old"},
                # One locator only, equal to the current target: the
                # code heal has nothing to pick, so the cycle must
                # spend a diagnosis call.
                "locators": [{"kind": "role_name", "value": "link|Old"}],
                "action": "click",
                "value_source": "none",
            }
        ],
        "success_assertion": {
            "kind": "terminal_state",
            "url": "https://example.com/pricing",
            "state_id": "state-goal",
            "element_signature": ["heading|Done"],
            "signature_superset_fallback": True,
        },
        "source_journey_id": str(source_journey_id),
        "source_map_id": "map",
        "source_map_version": 1,
    }


def _suspect_fixture():
    repo = FakeRepository()
    app_map = AppMap(
        id=uuid4(),
        workspace_id=uuid4(),
        application_id=uuid4(),
        target_id=uuid4(),
        version_number=2,
        status="ready",
        base_url="https://example.com/",
        builder_version="census-1a.1",
        census_config={},
        census_metrics={},
        pattern_stats={},
        gate_metrics={},
    )
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
        element_signature="link|Old",
    )
    terminal_state = MapPageState(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        app_map_id=app_map.id,
        map_page_id=uuid4(),
        state_key="default",
        state_id="state-goal",
        element_signature="heading|Done",
    )
    repo.states.extend([base_state, terminal_state])
    journey = MapJourney(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        app_map_id=app_map.id,
        name="Reach pricing",
        steps=[],
        preconditions=[],
        success_state_id=terminal_state.id,
        selection="rule",
    )
    repo.journeys[journey.id] = journey
    skill = Skill(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        name="reach-pricing",
        skill_kind="journey",
    )
    repo.skills[skill.id] = skill
    suspect = SkillVersion(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        skill_id=skill.id,
        version_number=1,
        status="draft",
        definition_json=_definition(journey.id),
        generation_metadata={},
        lifecycle_status="suspect",
        package={"name": "reach-pricing"},
        heal_count=0,
        replay_count=2,
        app_map_id=app_map.id,
    )
    repo.versions[suspect.id] = suspect
    repo.replays.append(
        SimpleNamespace(
            id=uuid4(),
            skill_version_id=suspect.id,
            result="failed",
            failure_step=1,
            failure_site="case_execution:ElementNotFound",
            started_at=None,
        )
    )
    return repo, app_map, skill, suspect


@pytest.mark.asyncio
async def test_t_ac1_diagnosis_spend_is_attributed_on_the_ledger(monkeypatch):
    from markettwin_execution_orchestrator.models import ask

    async def fake_model_json(system, user, *, max_tokens=512):
        return {"locator_index": 99}  # out of range: refused, still spent

    monkeypatch.setattr(ask, "_model_json", fake_model_json)
    repo, app_map, skill, suspect = _suspect_fixture()
    outcome = await heal_cycle_for_suspect(
        repo,
        app_map,
        skill,
        suspect,
        executor=FakeExecutor(),
        start_state_id="state-base",
        diagnosis_budget={"remaining": 5},
    )
    assert outcome == "quarantined"
    diagnosis = [e for e in repo.events if e["kind"] == "heal_diagnosis"]
    assert len(diagnosis) == 1
    event = diagnosis[0]
    assert event["model_calls"] == 1
    assert event["skill_version_id"] == suspect.id
    assert event["skill_id"] == skill.id
    # Nothing spent off-ledger: the diagnosis call is the ONLY model
    # call across every event the cycle wrote.
    assert sum(e.get("model_calls", 0) for e in repo.events) == 1
