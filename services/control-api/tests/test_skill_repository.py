"""Phase 3 skill-library repository tests (doc 22 sections 5.1, 5.2,
5.3, 7.1, 11.1): T-LB3 (a transition and its usage event commit
together; a refused transition writes nothing), T-LB5 (serving
returns exactly the active version; the withheld count is the
non-active denominator), T-LB6's repository half (activation retires
the superseded sibling in the same pass), the activation pass's
currency-failure and journey-absent routings, and T-PC1 (the persona
fence refuses a journey skill and records the refusal).

Fake sessions follow the Phase 2 pattern: queued execute results in
the repository's pinned call order, get() programmed per model+id,
added rows captured.
"""

from collections import deque
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from markettwin_control_api.knowledge.map_repository import MapRepository
from markettwin_database.models.knowledge import (
    AppMap,
    MapJourney,
    MapPage,
    MapPageState,
    Skill,
    SkillUsageEvent,
    SkillVersion,
)

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def _fake_result(rows):
    rows = list(rows)
    return SimpleNamespace(
        scalars=lambda: SimpleNamespace(
            all=lambda: list(rows),
            first=lambda: rows[0] if rows else None,
        ),
    )


class _Context:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


class _FakeSession:
    def __init__(self, *, get_results=None, execute_results=()):
        self._get_results = dict(get_results or {})
        self._execute_results = deque(execute_results)
        self.added: list[object] = []

    def begin(self):
        return _Context(None)

    async def get(self, model, ident):
        return self._get_results.get((model, ident))

    async def execute(self, statement):
        rows = self._execute_results.popleft() if self._execute_results else []
        return _fake_result(rows)

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        return None


def _repo(*sessions) -> MapRepository:
    queue = deque(sessions)
    return MapRepository(session_factory=lambda: _Context(queue.popleft()))


def _skill(*, kind="journey", name="checkout"):
    return Skill(
        id=uuid4(),
        workspace_id=uuid4(),
        application_id=uuid4(),
        target_id=uuid4(),
        name=name,
        skill_kind=kind,
    )


def _version(skill, *, number=1, lifecycle="draft", **overrides):
    values = dict(
        id=uuid4(),
        workspace_id=skill.workspace_id,
        skill_id=skill.id,
        version_number=number,
        status="draft",
        definition_json={},
        package={},
        lifecycle_status=lifecycle,
        heal_count=0,
        replay_count=0,
    )
    values.update(overrides)
    return SkillVersion(**values)


@pytest.mark.asyncio
async def test_t_lb3_transition_and_usage_event_commit_together():
    skill = _skill()
    version = _version(skill, lifecycle="draft")
    session = _FakeSession(get_results={(SkillVersion, version.id): version})
    repo = _repo(session)
    result = await repo.transition_skill_version(
        version_id=version.id,
        to_status="replay_verified",
        kind="verification_replay",
        evidence={"two_clean_replays": ["r-1", "r-2"]},
        result="passed",
    )
    assert result.lifecycle_status == "replay_verified"
    events = [row for row in session.added if isinstance(row, SkillUsageEvent)]
    assert len(events) == 1
    event = events[0]
    assert event.kind == "verification_replay"
    assert event.from_status == "draft"
    assert event.to_status == "replay_verified"
    assert event.result == "passed"
    assert event.skill_id == skill.id
    assert event.skill_version_id == version.id


@pytest.mark.asyncio
async def test_t_lb3_refused_transition_writes_nothing():
    skill = _skill()
    version = _version(skill, lifecycle="draft")
    session = _FakeSession(get_results={(SkillVersion, version.id): version})
    repo = _repo(session)
    with pytest.raises(ValueError, match="skill_transition_refused"):
        await repo.transition_skill_version(
            version_id=version.id,
            to_status="active",
            kind="activation",
            evidence={"currency_pass": {"app_map_id": "x"}},
        )
    assert version.lifecycle_status == "draft"
    assert session.added == []


@pytest.mark.asyncio
async def test_t_lb5_serving_returns_only_active_and_counts_withheld():
    skill = _skill()
    states = [
        "draft",
        "replay_verified",
        "active",
        "suspect",
        "quarantined",
        "retired",
    ]
    versions = [
        _version(skill, number=index + 1, lifecycle=state)
        for index, state in enumerate(states)
    ]
    session = _FakeSession(execute_results=[[skill], versions])
    repo = _repo(session)
    served, withheld = await repo.latest_active_skills(
        workspace_id=skill.workspace_id,
        application_id=skill.application_id,
        target_id=skill.target_id,
    )
    assert [(s.name, v.lifecycle_status) for s, v in served] == [
        ("checkout", "active")
    ]
    assert withheld == 5


@pytest.mark.asyncio
async def test_serving_refuses_corrupt_duplicate_active_versions():
    skill = _skill()
    versions = [_version(skill, number=number, lifecycle="active") for number in (1, 2)]
    session = _FakeSession(execute_results=[[skill], versions])
    with pytest.raises(ValueError, match="multiple_active_skill_versions"):
        await _repo(session).latest_active_skills(
            workspace_id=skill.workspace_id, application_id=skill.application_id, target_id=skill.target_id,
        )


def _activation_fixture(*, fingerprint_terminal: str, journey_present=True):
    """One scope: map v-current, a base page + default states, the
    current journey, the source journey, an active v1 and a
    replay_verified v2 of one journey skill."""
    workspace_id, application_id, target_id = uuid4(), uuid4(), uuid4()
    app_map = AppMap(
        id=uuid4(),
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=target_id,
        version_number=3,
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
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=target_id,
        app_map_id=app_map.id,
        canonical_url="https://example.com/",
        route_pattern="/",
        source_kinds=["seed"],
        crawl_status="fetch_ok",
    )
    start_state = MapPageState(
        id=uuid4(),
        workspace_id=workspace_id,
        app_map_id=app_map.id,
        map_page_id=base_page.id,
        state_key="default",
        state_id="state-start",
    )
    terminal_state_id = uuid4()
    terminal_state = MapPageState(
        id=terminal_state_id,
        workspace_id=workspace_id,
        app_map_id=app_map.id,
        map_page_id=uuid4(),  # the terminal page, not the base page
        state_key="default",
        state_id="state-terminal",
    )
    current_journey = MapJourney(
        id=uuid4(),
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=target_id,
        app_map_id=app_map.id,
        name="checkout",
        steps=[],
        preconditions=[],
        success_state_id=terminal_state_id,
        selection="rule",
    )
    source_journey = MapJourney(
        id=uuid4(),
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=target_id,
        app_map_id=uuid4(),
        name="checkout",
        steps=[],
        preconditions=[],
        success_state_id=uuid4(),
        selection="rule",
    )
    skill = Skill(
        id=uuid4(),
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=target_id,
        name="checkout",
        skill_kind="journey",
    )
    v1 = _version(skill, number=1, lifecycle="active")
    v1.workspace_id = workspace_id
    v2 = _version(
        skill,
        number=2,
        lifecycle="replay_verified",
        definition_json={"source_journey_id": str(source_journey.id)},
        verified_fingerprint={
            "start_state_id": "state-start",
            "terminal_state_id": fingerprint_terminal,
        },
    )
    v2.workspace_id = workspace_id
    journeys = [current_journey] if journey_present else []
    session = _FakeSession(
        get_results={(AppMap, app_map.id): app_map},
        execute_results=[
            [skill],  # skills in scope
            [v1, v2],  # all versions
            [base_page],  # current map pages
            [start_state, terminal_state],  # map states
            journeys,  # current map journeys
            [source_journey],  # source journeys by id
        ],
    )
    return _repo(session), session, app_map, skill, v1, v2, "state-terminal"


@pytest.mark.asyncio
async def test_t_lb6_activation_retires_the_superseded_sibling():
    repo, session, app_map, skill, v1, v2, terminal_id = _activation_fixture(
        fingerprint_terminal="placeholder"
    )
    v2.verified_fingerprint["terminal_state_id"] = terminal_id
    counts = await repo.run_activation_pass(
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        current_map_id=app_map.id,
    )
    assert counts == {
        "activated": 1,
        "retired_superseded": 1,
        "retired_journey_absent": 0,
        "currency_failed": 0,
    }
    assert v2.lifecycle_status == "active"
    assert v1.lifecycle_status == "retired"
    assert v1.retired_reason == "superseded"
    assert v1.retired_at is not None
    kinds = [
        row.kind for row in session.added if isinstance(row, SkillUsageEvent)
    ]
    assert kinds == ["retirement", "activation"]


@pytest.mark.asyncio
async def test_activation_currency_mismatch_stays_replay_verified():
    repo, session, app_map, skill, v1, v2, terminal_id = _activation_fixture(
        fingerprint_terminal="state-other"  # not the current terminal
    )
    counts = await repo.run_activation_pass(
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        current_map_id=app_map.id,
    )
    assert counts["currency_failed"] == 1
    assert counts["activated"] == 0
    assert v2.lifecycle_status == "replay_verified"
    assert v1.lifecycle_status == "active"
    events = [row for row in session.added if isinstance(row, SkillUsageEvent)]
    assert len(events) == 1
    assert events[0].kind == "activation"
    assert events[0].result == "failed"
    assert events[0].payload == {"reason": "currency_mismatch"}


@pytest.mark.asyncio
async def test_activation_journey_absent_retires_with_reason():
    repo, session, app_map, skill, v1, v2, terminal_id = _activation_fixture(
        fingerprint_terminal="irrelevant", journey_present=False
    )
    counts = await repo.run_activation_pass(
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        current_map_id=app_map.id,
    )
    assert counts["retired_journey_absent"] == 1
    assert v2.lifecycle_status == "retired"
    assert v2.retired_reason == "journey_absent"


@pytest.mark.asyncio
async def test_t_pc1_persona_consumer_refused_a_journey_skill():
    skill = _skill(kind="journey")
    version = _version(skill, lifecycle="active")
    read_session = _FakeSession(
        get_results={(Skill, skill.id): skill},
        execute_results=[[version]],
    )
    ledger_session = _FakeSession()
    repo = _repo(read_session, ledger_session)
    served = await repo.serve_skill_for_consumer(
        skill_id=skill.id, consumer="persona_setup", run_id=uuid4()
    )
    assert served is None
    events = [
        row for row in ledger_session.added if isinstance(row, SkillUsageEvent)
    ]
    assert len(events) == 1
    assert events[0].kind == "run_replay"
    assert events[0].result == "refused"
    assert events[0].payload["reason"] == "persona_fence"


@pytest.mark.asyncio
async def test_t_pc1_persona_consumer_served_a_platform_skill():
    skill = _skill(kind="platform", name="login")
    version = _version(skill, lifecycle="active")
    read_session = _FakeSession(
        get_results={(Skill, skill.id): skill},
        execute_results=[[version]],
    )
    repo = _repo(read_session)
    served = await repo.serve_skill_for_consumer(
        skill_id=skill.id, consumer="persona_setup"
    )
    assert served is version


@pytest.mark.asyncio
async def test_run_consumer_served_a_journey_skill():
    skill = _skill(kind="journey")
    version = _version(skill, lifecycle="active")
    read_session = _FakeSession(
        get_results={(Skill, skill.id): skill},
        execute_results=[[version]],
    )
    repo = _repo(read_session)
    served = await repo.serve_skill_for_consumer(
        skill_id=skill.id, consumer="run"
    )
    assert served is version
