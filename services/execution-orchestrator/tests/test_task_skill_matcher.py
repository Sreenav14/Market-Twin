"""T-TS10 — task-skill matching and reuse (doc 29 section 7, as
amended by the 2026-11-16 Codex consult 3, which wins over the
plan text):

matching = scope pre-filter -> contract-digest equivalence ->
action-containment gate -> prerequisites -> inputs -> mode/data
selectability. feature_key is FEATURE-scoped, so it is only the
pre-filter; equivalence is decided on the canonical contract
(steps / targets / input bindings / expected predicates), and the
stored contract_digest must recompute exactly (a definition
mutated after stamping is stale and never matches). A matched
replay must satisfy the REQUESTING case's expected outcomes, with
value-bound outcomes rebound to this run's approved values. The
token-overlap fallback only NOMINATES: it never authorises a
state-changing replay, and an exact-key candidate failing a gate
suppresses it. A non-match records its reason on the result (the
harness.skill.not_selected record), never silence.

The browser-level reuse gate (a full second run against the
fixture) is T-TS10's B7 form; here the matcher and the
consumption-selection seam are pinned with the fake-session
pattern the consumption suites already use.
"""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from markettwin_database.models import TestRun
from markettwin_database.models.knowledge import SkillReplay, SkillVersion
from markettwin_execution_orchestrator.workflow import case_execution
from markettwin_execution_orchestrator.workflow.skill_filter import (
    match_task_skill,
    rebind_task_assertions,
)
from markettwin_shared.feature_plan import TestCaseSpec
from markettwin_shared.task_skill import task_contract_digest

ORIGIN = "http://fixture.local"
RUN2_VALUES = {"agent_name": "Agent Two", "agent_model": "Fixture Model B"}


def _stamp(definition):
    definition["task"]["contract_digest"] = task_contract_digest(definition)
    return definition


def _create_definition():
    """The fixture create-an-agent task, compiled shape (the same
    shape tests/test_task_skills.py::make_task_definition pins),
    with the contract digest stamped as compile stamps it."""
    return _stamp({
        "case_id": "create_agent_one",
        "feature_key": "agents_create",
        "title": "Create an agent and see it in the list",
        "kind": "happy_path",
        "steps": [
            {"action": "navigate", "url": f"{ORIGIN}/agents"},
            {"action": "click", "target": {"role": "link", "name": "New agent"}},
            {
                "action": "fill",
                "target": {"label": "Agent name"},
                "test_value_key": "agent_name",
            },
            {
                "action": "select",
                "target": {"label": "Model"},
                "test_value_key": "agent_model",
            },
            {"action": "click", "target": {"role": "button", "name": "Create agent"}},
            {"action": "click", "target": {"role": "link", "name": "View agents"}},
        ],
        "expected": [
            {
                "assertion_id": "agent_present",
                "oracle": "visible_text",
                "target": {"text": "Agent One"},
                "expected_value": "Agent One",
                "origin": "inferred",
                "after_step_ordinal": 6,
            }
        ],
        "safety": "non_destructive",
        "estimated_seconds": 60,
        "locator_bindings": [],
        "success_assertion": {
            "kind": "terminal_state",
            "url": f"{ORIGIN}/agents",
            "state_id": "fixture-agents-state",
            "element_signature": ["link|Agents", "link|New agent"],
            "signature_superset_fallback": True,
        },
        "task": {
            "purpose": "Create an agent named {agent_name} and see it in the list",
            "feature_key": "agents_create",
            "source": {
                "kind": "run_execution",
                "run_id": "11111111-1111-4111-8111-111111111111",
                "case_id": "create_agent_one",
            },
            "prerequisites": [],
            "inputs": [
                {
                    "key": "agent_name", "label": "Agent name", "kind": "text",
                    "required": True, "disposable": True,
                },
                {
                    "key": "agent_model", "label": "Model", "kind": "selection",
                    "required": True, "disposable": True,
                },
            ],
            "documented_expectations": [
                {
                    "text": "Agents can be created from natural language.",
                    "origin": "documentation",
                    "source_ref": "fixture-docs",
                }
            ],
            "cleanup": {
                "kind": "compensating_steps",
                "steps": [
                    {
                        "action": "fill",
                        "target": {"label": "Agent name to delete"},
                        "test_value_key": "agent_name",
                    },
                    {
                        "action": "click",
                        "target": {"role": "button", "name": "Delete agent"},
                    },
                ],
            },
            "evidence_refs": [
                {
                    "kind": "run_execution",
                    "run_id": "11111111-1111-4111-8111-111111111111",
                    "case_id": "create_agent_one",
                }
            ],
            "observed_assertions": [
                {
                    "assertion_id": "agent_present",
                    "origin": "observation",
                    "oracle": "visible_text",
                    "expected_value": "Agent One",
                    "value_key": "agent_name",
                }
            ],
        },
    })


def _create_case(*, name_value="Agent Two", drop_last_step=False):
    """The second run's compatible case: same feature, no initial
    navigate (the run starts at start_url; compile prepended the
    navigate inside the skill), and its outcome asserts THIS run's
    value, not the compiling run's."""
    steps = [
        {"action": "click", "target": {"role": "link", "name": "New agent"}},
        {
            "action": "fill",
            "target": {"label": "Agent name"},
            "test_value_key": "agent_name",
        },
        {
            "action": "select",
            "target": {"label": "Model"},
            "test_value_key": "agent_model",
        },
        {"action": "click", "target": {"role": "button", "name": "Create agent"}},
        {"action": "click", "target": {"role": "link", "name": "View agents"}},
    ]
    if drop_last_step:
        steps = steps[:-1]
    return TestCaseSpec.model_validate({
        "case_id": "create_agent_two",
        "feature_key": "agents_create",
        "title": "Create an agent and see it in the list",
        "kind": "happy_path",
        "steps": steps,
        "expected": [
            {
                "assertion_id": "agent_present",
                "oracle": "visible_text",
                "target": {"text": name_value},
                "expected_value": name_value,
                "origin": "inferred",
                "after_step_ordinal": len(steps),
            }
        ],
    })


def _readonly_definition(*, feature_key, purpose, digest_break=False):
    definition = _stamp({
        "case_id": "view_agents_one",
        "feature_key": feature_key,
        "title": "View agents list",
        "kind": "happy_path",
        "steps": [
            {"action": "navigate", "url": f"{ORIGIN}/agents"},
            {"action": "click", "target": {"role": "link", "name": "View agents"}},
        ],
        "expected": [
            {
                "assertion_id": "agents_title",
                "oracle": "title",
                "expected_value": "Agents",
                "origin": "inferred",
                "after_step_ordinal": 2,
            }
        ],
        "safety": "non_destructive",
        "estimated_seconds": 30,
        "locator_bindings": [],
        "success_assertion": {
            "kind": "terminal_state",
            "url": f"{ORIGIN}/agents",
            "state_id": "fixture-agents-state",
            "element_signature": ["link|Agents"],
            "signature_superset_fallback": True,
        },
        "task": {
            "purpose": purpose,
            "feature_key": feature_key,
            "source": {
                "kind": "run_execution",
                "run_id": "11111111-1111-4111-8111-111111111111",
                "case_id": "view_agents_one",
            },
            "prerequisites": [],
            "inputs": [],
            "documented_expectations": [],
            "cleanup": {"kind": "none_required"},
            "evidence_refs": [
                {
                    "kind": "run_execution",
                    "run_id": "11111111-1111-4111-8111-111111111111",
                    "case_id": "view_agents_one",
                }
            ],
            "observed_assertions": [],
        },
    })
    if digest_break:
        # Mutated after stamping (locator bindings are digest
        # inputs but not equivalence inputs): stale, never matches.
        definition["locator_bindings"] = [{"page_url": f"{ORIGIN}/agents"}]
    return definition


def _readonly_case(*, feature_key):
    return TestCaseSpec.model_validate({
        "case_id": "view_agents_two",
        "feature_key": feature_key,
        "title": "View agents list",
        "kind": "happy_path",
        "steps": [
            {"action": "click", "target": {"role": "link", "name": "View agents"}},
        ],
        "expected": [
            {
                "assertion_id": "agents_title",
                "oracle": "title",
                "expected_value": "Agents",
                "origin": "inferred",
                "after_step_ordinal": 1,
            }
        ],
    })


def _entry(definition, **overrides):
    entry = {
        "skill_id": str(uuid4()),
        "skill_version_id": str(uuid4()),
        "name": "create-agent",
        "skill_kind": "task",
        "lifecycle_status": "active",
        "definition": definition,
    }
    entry.update(overrides)
    return entry


def _app_map(*entries):
    return {"map_id": str(uuid4()), "skills": list(entries)}


def test_t_ts10_exact_match_reuses_skill_with_different_inputs():
    definition = _create_definition()
    entry = _entry(definition)
    result = match_task_skill(
        _app_map(entry),
        _create_case(),
        mode="standard",
        approved_values=RUN2_VALUES,
        start_url=f"{ORIGIN}/agents",
    )
    assert result.status == "matched"
    assert result.via == "exact"
    assert result.reason is None
    assert result.skill_version_id == UUID(entry["skill_version_id"])
    # Reuse with DIFFERENT inputs: the handed-over definition is
    # rebound to this run's values; the stored one is untouched.
    rebound = result.entry["definition"]
    assert rebound["expected"][0]["expected_value"] == "Agent Two"
    assert rebound["expected"][0]["target"]["text"] == "Agent Two"
    assert definition["expected"][0]["expected_value"] == "Agent One"


def test_t_ts10_stale_digest_is_not_matched():
    definition = _create_definition()
    definition["steps"][3]["target"] = {"label": "Model name"}  # no restamp
    result = match_task_skill(
        _app_map(_entry(definition)),
        _create_case(),
        mode="standard",
        approved_values=RUN2_VALUES,
        start_url=f"{ORIGIN}/agents",
    )
    assert result.status == "not_selected"
    assert result.reason == "digest_mismatch"
    assert result.entry is None


def test_t_ts10_contract_mismatch_and_no_candidate_reasons():
    entry = _entry(_create_definition())
    mismatched = match_task_skill(
        _app_map(entry),
        _create_case(drop_last_step=True),
        mode="standard",
        approved_values=RUN2_VALUES,
        start_url=f"{ORIGIN}/agents",
    )
    assert mismatched.status == "not_selected"
    assert mismatched.reason == "contract_mismatch"

    unrelated = TestCaseSpec.model_validate({
        "case_id": "search_case",
        "feature_key": "search_fixture",
        "title": "Search the fixture",
        "kind": "happy_path",
        "steps": [
            {"action": "click", "target": {"role": "button", "name": "Search"}},
        ],
        "expected": [
            {
                "assertion_id": "results_title",
                "oracle": "title",
                "expected_value": "Results",
                "origin": "inferred",
                "after_step_ordinal": 1,
            }
        ],
    })
    result = match_task_skill(
        _app_map(entry),
        unrelated,
        mode="standard",
        approved_values=RUN2_VALUES,
        start_url=f"{ORIGIN}/",
    )
    assert result.status == "not_selected"
    assert result.reason == "no_candidate"


def test_t_ts10_missing_inputs_recorded():
    result = match_task_skill(
        _app_map(_entry(_create_definition())),
        _create_case(),
        mode="standard",
        approved_values={"agent_name": "Agent Two"},  # agent_model withheld
        start_url=f"{ORIGIN}/agents",
    )
    assert result.status == "not_selected"
    assert result.reason == "missing_inputs"


def test_t_ts10_prerequisite_gate():
    definition = _create_definition()
    definition["task"]["prerequisites"] = [
        {"kind": "input_available", "input_key": "api_token"}
    ]
    _stamp(definition)
    entry = _entry(definition)
    refused = match_task_skill(
        _app_map(entry),
        _create_case(),
        mode="standard",
        approved_values=RUN2_VALUES,
        start_url=f"{ORIGIN}/agents",
    )
    assert refused.status == "not_selected"
    assert refused.reason == "prerequisite"

    allowed = match_task_skill(
        _app_map(entry),
        _create_case(),
        mode="standard",
        approved_values={**RUN2_VALUES, "api_token": "token-value"},
        start_url=f"{ORIGIN}/agents",
    )
    assert allowed.status == "matched"


def test_t_ts10_exact_key_gate_failure_suppresses_token_fallback():
    # An exact-key candidate exists but its stored digest is stale;
    # a token-overlapping read-only candidate fully matches. The
    # fallback is suppressed: the recorded reason is the exact
    # candidate's gate failure, not a nomination.
    exact = _entry(
        _readonly_definition(
            feature_key="agents_view", purpose="View the agents list page",
            digest_break=True,
        ),
        name="view-agents",
    )
    token = _entry(
        _readonly_definition(
            feature_key="agents_browse", purpose="View the agents list page",
        ),
        name="view-agents-list",
    )
    result = match_task_skill(
        _app_map(exact, token),
        _readonly_case(feature_key="agents_view"),
        mode="read_only",
        approved_values={},
        start_url=f"{ORIGIN}/agents",
    )
    assert result.status == "not_selected"
    assert result.reason == "digest_mismatch"


def test_t_ts10_token_nomination_matches_read_only_only():
    token = _entry(
        _readonly_definition(
            feature_key="agents_browse", purpose="View the agents list page",
        ),
        name="view-agents-list",
    )
    result = match_task_skill(
        _app_map(token),
        _readonly_case(feature_key="agents_view"),
        mode="read_only",
        approved_values={},
        start_url=f"{ORIGIN}/agents",
    )
    assert result.status == "matched"
    assert result.via == "token_nomination"

    # The same overlap for a STATE-CHANGING skill never authorises
    # replay: nomination only, and here not even selection. The
    # case's feature_key has no candidate (the skill's key
    # differs), so the skill is reachable only via nomination.
    changing = _entry(_create_definition(), name="create-agent")
    case = _create_case().model_copy(update={"feature_key": "agents_create_v2"})
    refused = match_task_skill(
        _app_map(changing),
        case,
        mode="standard",
        approved_values=RUN2_VALUES,
        start_url=f"{ORIGIN}/agents",
    )
    assert refused.status == "not_selected"
    assert refused.reason == "nomination_state_changing"


# --- consumption selection (case_execution.execute_skill_replay) ---


class _FakeSession:
    def __init__(self, *, run, version):
        self._run = run
        self._version = version
        self.added: list = []

    async def get(self, model, ident, **_kwargs):
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


def _consumption_fixture(definition):
    run_id = uuid4()
    map_id = uuid4()
    snapshot = {
        "app_map": {"map_id": str(map_id)},
        "harness_run_mode": "standard",
        "approved_test_data": [
            {"key": key, "value": value} for key, value in RUN2_VALUES.items()
        ],
    }
    run = SimpleNamespace(
        id=run_id, configuration_snapshot=snapshot, run_kind="explore_test"
    )
    version = SkillVersion(
        id=uuid4(),
        workspace_id=uuid4(),
        skill_id=uuid4(),
        version_number=1,
        status="draft",
        definition_json=definition,
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
        start_url=f"{ORIGIN}/agents",
        allowed_origins=(
            SimpleNamespace(scheme="http", hostname="fixture.local", port=None),
        ),
    )
    entry = {
        "name": "create-agent",
        "skill_id": str(version.skill_id),
        "skill_version_id": str(version.id),
        "skill_kind": "task",
        "lifecycle_status": "active",
        "definition": definition,
    }
    return session, request, version, entry


@pytest.mark.asyncio
async def test_t_ts10_replay_selection_refuses_mismatched_case(monkeypatch):
    definition = _create_definition()
    session, request, version, entry = _consumption_fixture(definition)
    calls = []

    async def fake_action(controller, handle, action, scope):
        calls.append(action)
        return SimpleNamespace(ok=True)

    monkeypatch.setattr(case_execution, "perform_case_action", fake_action)
    outcome = await case_execution.execute_skill_replay(
        request=request,
        controller=SimpleNamespace(),
        handle=SimpleNamespace(),
        session=session,
        skill_entry=entry,
        board_item_ref="board:task:1",
        requesting_case=_create_case(drop_last_step=True),
    )
    # The requesting case's contract is not the skill's: the
    # replay refuses BEFORE any browser action and records
    # nothing -- a replay can never silently satisfy a case whose
    # outcomes it does not check (consult 3, worst failure).
    assert outcome == {"status": "refused", "reason": "contract_mismatch"}
    assert calls == []
    assert session.added == []
    assert version.lifecycle_status == "active"


@pytest.mark.asyncio
async def test_t_ts10_replay_with_requesting_case_passes_zero_model_calls(monkeypatch):
    from markettwin_execution_orchestrator.harvest import (
        harvest_capture,
        harvest_inventory,
    )

    # The entry the matcher hands over: stored definition rebound
    # to this run's approved values.
    definition = rebind_task_assertions(_create_definition(), RUN2_VALUES)
    session, request, version, entry = _consumption_fixture(definition)

    async def fake_action(controller, handle, action, scope):
        return SimpleNamespace(ok=True)

    async def fake_capture(controller, handle, *, execution_id, journey_id):
        return SimpleNamespace(url=f"{ORIGIN}/agents")

    async def read_assertion(**kwargs):
        return None, SimpleNamespace(status="satisfied")

    monkeypatch.setattr(case_execution, "perform_case_action", fake_action)
    monkeypatch.setattr(harvest_capture, "capture_state", fake_capture)
    monkeypatch.setattr(harvest_inventory, "distil_elements", lambda c: [])
    monkeypatch.setattr(harvest_inventory, "distil_forms", lambda c: [])
    monkeypatch.setattr(
        harvest_inventory, "identity_for",
        lambda url, e, f: ("fixture-agents-state", None, None),
    )
    handle = SimpleNamespace(
        session_id=uuid4(), execution_id=uuid4(), journey_id=uuid4()
    )
    outcome = await case_execution.execute_skill_replay(
        request=request,
        controller=SimpleNamespace(read_assertion=read_assertion),
        handle=handle,
        session=session,
        skill_entry=entry,
        board_item_ref="board:task:1",
        requesting_case=_create_case(),
    )
    assert outcome["status"] == "passed"
    assert outcome["terminal_state_match"] is True
    replays = [row for row in session.added if isinstance(row, SkillReplay)]
    assert len(replays) == 1
    assert replays[0].result == "passed"
    assert replays[0].model_calls == 0
    assert replays[0].context_kind == "run"
