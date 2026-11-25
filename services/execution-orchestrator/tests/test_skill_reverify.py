"""Phase 3 heal-cycle tests (doc 22 sections 9.1, 9.3, 17):
T-HL1 — a suspect's heal mints a NEW draft (the suspect's definition
is never edited); the healed draft verifies, activates, and the
suspect retires superseded. T-HL2 — the healed draft fails: the
suspect is quarantined with the draft named in the event, and the
draft STAYS in draft. T-HL3 — the diagnosis cap binds (no call at
zero budget) and an out-of-range proposal is refused by validation.
T-HL4 — the diff validator refuses assertion/step-set changes; a
suspect with no failure evidence is skipped, not quarantined.
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
    diagnose_heal,
    heal_cycle_for_suspect,
    validate_heal_diff,
)


class FakeRepository:
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
            {**event, "skill_version_id": version_id, "skill_id": version.skill_id}
        )
        return version

    async def insert_usage_event(
        self, version, *, kind, from_status, to_status, result=None,
        run_id=None, job_ref=None, model_calls=0, model_tokens=0, payload=None,
    ):
        self.events.append(
            {
                "kind": kind,
                "from_status": from_status,
                "to_status": to_status,
                "result": result,
                "model_calls": model_calls,
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

    async def list_skills_for_scope(self, *, workspace_id, application_id, target_id):
        return [
            s
            for s in self.skills.values()
            if s.workspace_id == workspace_id
            and s.application_id == application_id
            and s.target_id == target_id
        ]

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
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)

    async def run_once(self, *, definition):
        if self._outcomes:
            return self._outcomes.pop(0)
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
                "locators": [
                    {"kind": "role_name", "value": "link|Old"},
                    {"kind": "role_name", "value": "link|New"},
                ],
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


def _fixture(*, with_failed_replay=True):
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
    if with_failed_replay:
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
async def test_t_hl1_heal_mints_a_new_draft_and_the_suspect_retires():
    repo, app_map, skill, suspect = _fixture()
    original_definition = suspect.definition_json
    executor = FakeExecutor([ReplayAttempt(ok=True), ReplayAttempt(ok=True)])
    outcome = await heal_cycle_for_suspect(
        repo,
        app_map,
        skill,
        suspect,
        executor=executor,
        start_state_id="state-base",
        diagnosis_budget={"remaining": 20},
    )
    assert outcome == "healed_and_active"
    versions = await repo.list_versions_for_skill(skill.id)
    assert len(versions) == 2
    draft = versions[1]
    assert draft.heal_of_version_id == suspect.id
    assert draft.lifecycle_status == "active"
    assert draft.definition_json["steps"][1]["target"] == {
        "role": "link",
        "name": "New",
    }
    # The served suspect's definition was never edited.
    assert suspect.definition_json is original_definition
    assert suspect.definition_json["steps"][1]["target"] == {
        "role": "link",
        "name": "Old",
    }
    assert suspect.lifecycle_status == "retired"
    assert suspect.retired_reason == "superseded"
    assert suspect.heal_count == 1


@pytest.mark.asyncio
async def test_t_hl2_failed_healed_draft_quarantines_the_suspect_only():
    repo, app_map, skill, suspect = _fixture()
    failing = ReplayAttempt(
        ok=False, failure_step=1, failure_site="case_execution:Boom"
    )
    executor = FakeExecutor([failing, failing, failing])
    outcome = await heal_cycle_for_suspect(
        repo,
        app_map,
        skill,
        suspect,
        executor=executor,
        start_state_id="state-base",
        diagnosis_budget={"remaining": 20},
    )
    assert outcome == "quarantined"
    assert suspect.lifecycle_status == "quarantined"
    versions = await repo.list_versions_for_skill(skill.id)
    draft = versions[1]
    assert draft.lifecycle_status == "draft"  # left in draft, named below
    quarantine_events = [
        e
        for e in repo.events
        if e["kind"] == "quarantine"
        and e["skill_version_id"] == suspect.id
    ]
    assert len(quarantine_events) == 1
    payload = quarantine_events[0]["payload"]
    assert payload["heal_record"]["healed_draft_id"] == str(draft.id)


@pytest.mark.asyncio
async def test_t_hl3_diagnosis_cap_binds_and_proposals_are_validated(
    monkeypatch,
):
    from markettwin_execution_orchestrator.models import ask

    calls: list = []

    async def fake_model_json(system, user, *, max_tokens=512):
        calls.append((system, user))
        return {"locator_index": 99}

    monkeypatch.setattr(ask, "_model_json", fake_model_json)
    definition = _definition(uuid4())
    failure = ReplayAttempt(
        ok=False, failure_step=1, failure_site="case_execution:X"
    )
    # Out-of-range proposal: refused by validation, one call spent.
    assert await diagnose_heal(definition, failure, aria_excerpt="ctx") is None
    assert len(calls) == 1

    async def good_model_json(system, user, *, max_tokens=512):
        calls.append((system, user))
        return {"locator_index": 1}

    monkeypatch.setattr(ask, "_model_json", good_model_json)
    healed = await diagnose_heal(definition, failure, aria_excerpt="ctx")
    assert healed is not None
    healed_definition, record = healed
    assert healed_definition["steps"][1]["target"] == {
        "role": "link",
        "name": "New",
    }
    assert validate_heal_diff(definition, healed_definition) is True

    # Zero budget: the heal cycle never reaches the door.
    repo, app_map, skill, suspect = _fixture()
    suspect.definition_json["locator_bindings"][0]["locators"] = [
        {"kind": "role_name", "value": "link|Old"}  # code heal impossible
    ]
    calls.clear()
    outcome = await heal_cycle_for_suspect(
        repo,
        app_map,
        skill,
        suspect,
        executor=FakeExecutor([]),
        start_state_id="state-base",
        diagnosis_budget={"remaining": 0},
    )
    assert outcome == "quarantined"
    assert calls == []


def test_t_hl4_diff_validator_refuses_assertion_and_step_set_changes():
    before = _definition(uuid4())
    target_only = _definition(uuid4())
    target_only["steps"] = [
        dict(step) for step in before["steps"]
    ]
    target_only["steps"][1] = {
        **before["steps"][1],
        "target": {"role": "link", "name": "New"},
    }
    assert validate_heal_diff(before, target_only) is True

    assertion_changed = _definition(uuid4())
    assertion_changed["success_assertion"] = {
        **before["success_assertion"],
        "state_id": "state-other",
    }
    assert validate_heal_diff(before, assertion_changed) is False

    steps_changed = _definition(uuid4())
    steps_changed["steps"] = list(before["steps"]) + [
        {"action": "wait", "milliseconds": 100}
    ]
    assert validate_heal_diff(before, steps_changed) is False

    value_key_changed = _definition(uuid4())
    value_key_changed["steps"] = [dict(step) for step in before["steps"]]
    value_key_changed["steps"][1] = {
        **before["steps"][1],
        "test_value_key": "other",
    }
    assert validate_heal_diff(before, value_key_changed) is False


@pytest.mark.asyncio
async def test_t_hl4_suspect_without_failure_evidence_is_skipped():
    repo, app_map, skill, suspect = _fixture(with_failed_replay=False)
    outcome = await heal_cycle_for_suspect(
        repo,
        app_map,
        skill,
        suspect,
        executor=FakeExecutor([]),
        start_state_id="state-base",
        diagnosis_budget={"remaining": 20},
    )
    assert outcome == "heal_skipped_no_evidence"
    assert suspect.lifecycle_status == "suspect"


class _MetricsRepository(FakeRepository):
    """FakeRepository + the durable per-map metrics ledger the A5
    budget persists through: merge-write, as HarvestRepository."""

    def __init__(self):
        super().__init__()
        self.maps: dict = {}

    async def save_harvest_metrics(self, map_id, updates):
        app_map = self.maps[map_id]
        merged = {**(app_map.harvest_metrics or {}), **updates}
        app_map.harvest_metrics = merged
        return merged


def _diagnosis_only_suspect(repo, app_map, journey, *, name):
    """A suspect whose ONLY heal path is the model diagnosis: the
    failing step is a navigate (the code heal rewrites click targets
    and waits only), with a ranked replacement locator bound to that
    step for the diagnosis to pick."""
    skill = Skill(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        name=name,
        skill_kind="journey",
    )
    repo.skills[skill.id] = skill
    definition = _definition(journey.id)
    definition["steps"] = [
        {"action": "navigate", "url": "https://example.com/"},
        {"action": "click", "target": {"role": "link", "name": "Old"}},
    ]
    definition["locator_bindings"] = [
        {
            "order": 1,
            "page_url": "https://example.com/",
            "element": {"role": "link", "name": "Old"},
            "locators": [
                {"kind": "role_name", "value": "link|Old"},
                {"kind": "role_name", "value": "link|New"},
            ],
            "action": "navigate",
            "value_source": "none",
        },
        *definition["locator_bindings"],
    ]
    suspect = SkillVersion(
        id=uuid4(),
        workspace_id=app_map.workspace_id,
        skill_id=skill.id,
        version_number=1,
        status="draft",
        definition_json=definition,
        generation_metadata={},
        lifecycle_status="suspect",
        package={"name": name},
        heal_count=0,
        replay_count=1,
        app_map_id=app_map.id,
    )
    repo.versions[suspect.id] = suspect
    repo.replays.append(
        SimpleNamespace(
            id=uuid4(),
            skill_version_id=suspect.id,
            result="failed",
            failure_step=0,
            failure_site="case_execution:ElementNotFound",
            started_at=None,
        )
    )
    return skill, suspect


@pytest.mark.asyncio
async def test_a5_heal_diagnosis_budget_is_durable_per_map(monkeypatch):
    """Astra A5: diagnosis calls used to be bounded only by a
    per-pass in-memory counter — nothing durable recorded them, so
    the cap reset every pass and every restart. The budget is now
    keyed to the app map: the charge merge-writes
    harvest_metrics["heal_diagnosis_calls"] BEFORE the provider call,
    and a pass rebuilt from the updated metrics (exactly as the next
    poll builds it) refuses at the cap with NO provider request and
    a heal_diagnosis/refused usage event naming the exhaustion."""
    from markettwin_execution_orchestrator.harvest.skill_reverify import (
        _diagnosis_budget,
    )
    from markettwin_execution_orchestrator.models import ask

    monkeypatch.setenv("MARKETTWIN_HEAL_DIAGNOSIS_MAP_CALL_CAP", "1")
    calls: list = []

    async def fake_model_json(system, user, *, max_tokens=512):
        calls.append((system, user))
        return {"locator_index": 1}

    monkeypatch.setattr(ask, "_model_json", fake_model_json)
    repo = _MetricsRepository()
    # Re-home the fixture's map/pages/states/journey onto the
    # metrics repository (its own skill/suspect stay behind).
    fixture_repo, app_map, _skill, _suspect = _fixture()
    repo.pages = fixture_repo.pages
    repo.states = fixture_repo.states
    repo.journeys = fixture_repo.journeys
    repo.maps[app_map.id] = app_map
    journey = next(iter(repo.journeys.values()))
    skill1, suspect1 = _diagnosis_only_suspect(
        repo, app_map, journey, name="diagnosis-one",
    )
    budget = _diagnosis_budget(app_map)
    assert budget["remaining"] == 1
    outcome = await heal_cycle_for_suspect(
        repo,
        app_map,
        skill1,
        suspect1,
        executor=FakeExecutor([ReplayAttempt(ok=True), ReplayAttempt(ok=True)]),
        start_state_id="state-base",
        diagnosis_budget=budget,
    )
    assert outcome == "healed_and_active"
    assert len(calls) == 1
    # The charge is durable on the map, not just in the pass dict.
    assert app_map.harvest_metrics["heal_diagnosis_calls"] == 1
    applied = [
        e for e in repo.events
        if e["kind"] == "heal_diagnosis" and e["result"] == "applied"
    ]
    assert len(applied) == 1 and applied[0]["model_calls"] == 1

    # Second cycle under the same map identity: the budget rebuilt
    # from the updated metrics is exhausted, so the diagnosis is
    # refused BEFORE any provider request.
    skill2, suspect2 = _diagnosis_only_suspect(
        repo, app_map, journey, name="diagnosis-two",
    )
    budget2 = _diagnosis_budget(app_map)
    assert budget2["remaining"] == 0
    outcome2 = await heal_cycle_for_suspect(
        repo,
        app_map,
        skill2,
        suspect2,
        executor=FakeExecutor([]),
        start_state_id="state-base",
        diagnosis_budget=budget2,
    )
    assert outcome2 == "quarantined"
    assert len(calls) == 1  # no second provider request
    assert app_map.harvest_metrics["heal_diagnosis_calls"] == 1
    refused = [
        e for e in repo.events
        if e["kind"] == "heal_diagnosis" and e["result"] == "refused"
        and e["skill_version_id"] == suspect2.id
    ]
    assert len(refused) == 1
    assert refused[0]["payload"]["reason"] == "heal_diagnosis_map_cap_exhausted"
