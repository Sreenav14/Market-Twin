"""Phase 3 consumption tests (doc 22 sections 8.3, 8.4):
execute_skill_replay records the consumption replay (context 'run',
run id + Board item ref, zero model calls) and its run_replay usage
event; an assertion-shaped divergence (steps complete, terminal
assertion fails) quarantines the active version with its quarantine
event (8.4.2); a locator-shaped divergence (a step fails to
execute) demotes the active version to suspect with its demotion
event (8.4.3); the execution-time mode re-check refuses a
mode-filtered skill without recording anything.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from markettwin_database.models import TestRun
from markettwin_database.models.knowledge import (
    SkillReplay,
    SkillUsageEvent,
    SkillVersion,
)
from markettwin_execution_orchestrator.workflow import case_execution


async def _passed_assertion(**kwargs):
    return None, SimpleNamespace(status="satisfied")


@pytest.mark.parametrize("identifier", [None, "", "not-a-uuid"])
async def test_malformed_skill_version_returns_named_refusal(identifier):
    session, request, _version, entry = _fixture()
    entry["skill_version_id"] = identifier
    result = await case_execution.execute_skill_replay(
        session=session, request=request, controller=object(), handle=object(),
        skill_entry=entry, board_item_ref="audit-fixture",
    )
    assert result == {"status": "refused", "reason": "invalid_skill_version_id"}
    assert session.added == []


class _FakeSession:
    def __init__(self, *, run, version):
        self._run = run
        self._version = version
        self.added: list = []

    async def get(self, model, ident):
        if model is TestRun:
            return self._run
        if model is SkillVersion:
            return self._version
        return None

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None


def _definition():
    return {
        "case_id": "reach_pricing_x",
        "feature_key": "map_journey_x",
        "title": "Journey: Reach pricing",
        "kind": "happy_path",
        "steps": [
            {"action": "navigate", "url": "https://example.com/"},
            {
                "action": "click",
                "target": {"role": "link", "name": "Pricing"},
            },
        ],
        "expected": [
            {
                "assertion_id": "terminal_url",
                "oracle": "url",
                "expected_value": "https://example.com/pricing",
                "origin": "inferred",
            }
        ],
        "safety": "non_destructive",
        "estimated_seconds": 30,
        "success_assertion": {
            "kind": "terminal_state",
            "url": "https://example.com/pricing",
            "state_id": "state-goal",
            "element_signature": [],
            "signature_superset_fallback": False,
        },
    }


def _fixture(*, snapshot_extra=None):
    run_id = uuid4()
    map_id = uuid4()
    snapshot = {"app_map": {"map_id": str(map_id)}}
    if snapshot_extra:
        snapshot.update(snapshot_extra)
    run = SimpleNamespace(
        id=run_id, configuration_snapshot=snapshot, run_kind="explore_test"
    )
    version = SkillVersion(
        id=uuid4(),
        workspace_id=uuid4(),
        skill_id=uuid4(),
        version_number=1,
        status="draft",
        definition_json=_definition(),
        generation_metadata={},
        lifecycle_status="active",
        package={},
        heal_count=0,
        replay_count=0,
    )
    session = _FakeSession(run=run, version=version)
    request = SimpleNamespace(
        test_run_id=run_id,
        journey_id=uuid4(),
        execution_id=uuid4(),
        allowed_origins=(
            SimpleNamespace(scheme="https", hostname="example.com", port=None),
        ),
    )
    entry = {
        "name": "reach-pricing",
        "skill_id": str(version.skill_id),
        "skill_version_id": str(version.id),
        "definition": _definition(),
    }
    return session, request, version, entry


def _events(session, kind):
    return [
        row
        for row in session.added
        if isinstance(row, SkillUsageEvent) and row.kind == kind
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome_status", ["satisfied", "not_satisfied", "unverified"])
async def test_assertion_divergence_records_and_quarantines(monkeypatch, outcome_status):
    from markettwin_execution_orchestrator.harvest import (
        harvest_capture,
        harvest_inventory,
    )

    async def fake_action(controller, handle, action, scope):
        return SimpleNamespace(ok=True)

    async def fake_capture(controller, handle, *, execution_id, journey_id):
        return SimpleNamespace(url=("https://example.com/elsewhere" if outcome_status == "satisfied"
                                    else "https://example.com/pricing"))

    async def read_assertion(**kwargs):
        return None, SimpleNamespace(status=outcome_status)

    monkeypatch.setattr(case_execution, "perform_case_action", fake_action)
    monkeypatch.setattr(harvest_capture, "capture_state", fake_capture)
    monkeypatch.setattr(harvest_inventory, "distil_elements", lambda c: [])
    monkeypatch.setattr(harvest_inventory, "distil_forms", lambda c: [])
    monkeypatch.setattr(
        harvest_inventory, "identity_for", lambda url, e, f: ("state-goal", None, None)
    )
    session, request, version, entry = _fixture()
    handle = SimpleNamespace(
        session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4()
    )
    outcome = await case_execution.execute_skill_replay(
        request=request,
        controller=SimpleNamespace(read_assertion=read_assertion),
        handle=handle,
        session=session,
        skill_entry=entry,
        board_item_ref="board:skill:1",
    )
    assert outcome["status"] == "diverged"
    assert outcome["terminal_state_match"] is False
    assert outcome["per_step"] == [
        {"order": 0, "result": "passed"},
        {"order": 1, "result": "passed"},
    ]
    replays = [row for row in session.added if isinstance(row, SkillReplay)]
    assert len(replays) == 1
    replay = replays[0]
    assert replay.context_kind == "run"
    assert replay.run_id == request.test_run_id
    assert replay.board_item_ref == "board:skill:1"
    assert replay.model_calls == 0
    assert replay.result == "failed"  # terminal assertion did not hold
    # Section 8.4.2: assertion-shaped divergence quarantines at once.
    assert version.lifecycle_status == "quarantined"
    assert version.replay_count == 1
    quarantines = _events(session, "quarantine")
    assert len(quarantines) == 1
    assert quarantines[0].from_status == "active"
    assert quarantines[0].to_status == "quarantined"
    assert quarantines[0].payload["kind"] == "assertion_divergence"
    assert _events(session, "demotion") == []
    run_replays = _events(session, "run_replay")
    assert len(run_replays) == 1
    assert run_replays[0].result == "failed"
    assert run_replays[0].run_id == request.test_run_id
    assert run_replays[0].payload["outcome"] == "diverged"


@pytest.mark.asyncio
async def test_locator_failure_records_and_demotes_to_suspect(monkeypatch):
    async def failing_action(controller, handle, action, scope):
        if action.action == "click":
            raise RuntimeError("element not found")
        return SimpleNamespace(ok=True)

    monkeypatch.setattr(case_execution, "perform_case_action", failing_action)
    session, request, version, entry = _fixture()
    handle = SimpleNamespace(
        session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4()
    )
    outcome = await case_execution.execute_skill_replay(
        request=request,
        controller=SimpleNamespace(),
        handle=handle,
        session=session,
        skill_entry=entry,
        board_item_ref="board:skill:1",
    )
    assert outcome["status"] == "failed"
    assert outcome["failure_step"] == 1
    assert outcome["failure_site"] == "case_execution:RuntimeError"
    assert outcome["terminal_state_match"] is None
    assert outcome["per_step"] == [
        {"order": 0, "result": "passed"},
        {"order": 1, "result": "failed"},
    ]
    replays = [row for row in session.added if isinstance(row, SkillReplay)]
    assert len(replays) == 1
    assert replays[0].result == "failed"
    assert replays[0].failure_step == 1
    # Section 8.4.3: locator-shaped divergence demotes to suspect.
    assert version.lifecycle_status == "suspect"
    demotions = _events(session, "demotion")
    assert len(demotions) == 1
    assert demotions[0].from_status == "active"
    assert demotions[0].to_status == "suspect"
    assert demotions[0].payload["kind"] == "locator_failure"
    assert demotions[0].payload["failure_site"] == "case_execution:RuntimeError"
    assert _events(session, "quarantine") == []
    run_replays = _events(session, "run_replay")
    assert len(run_replays) == 1
    assert run_replays[0].result == "failed"


@pytest.mark.asyncio
async def test_mode_filtered_replay_records_nothing():
    session, request, version, entry = _fixture()
    entry["definition"] = {
        **_definition(),
        "steps": [
            {"action": "navigate", "url": "https://example.com/"},
            {
                "action": "click",
                "target": {"role": "button", "name": "Delete account"},
            },
        ],
    }
    outcome = await case_execution.execute_skill_replay(
        request=request,
        controller=SimpleNamespace(),
        handle=SimpleNamespace(),
        session=session,
        skill_entry=entry,
        board_item_ref="board:skill:1",
    )
    assert outcome["status"] == "mode_filtered"
    assert outcome["reason"] is not None
    assert session.added == []
    assert version.lifecycle_status == "active"
