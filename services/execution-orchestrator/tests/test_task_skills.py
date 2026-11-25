"""Task-skill pipeline tests (doc 29 section 9, T-TS1..T-TS9).

Each test pins one of the owner's completion criteria at the seam
the existing suites use: pure functions and module seams with fake
repositories/controllers, plus the real task_fixture app for the
end-to-end gate (T-TS6/T-TS10/T-TS11 drive a real browser).
"""

from markettwin_shared.task_skill import validate_task_skill


def test_task_reuse_requires_the_same_read_only_browser_contract():
    from uuid import uuid4

    from markettwin_shared.feature_plan import TestCaseSpec
    from markettwin_shared.task_skill import task_contract_digest

    from markettwin_execution_orchestrator.workflow.skill_filter import match_read_only_task_skill

    steps = [{"action": "navigate", "url": "https://example.com/agents"}]
    expected = [{
        "assertion_id": "agents_page", "oracle": "title",
        "expected_value": "Agents", "origin": "user_approved",
    }]
    native = {
        "case_id": "open_agents", "feature_key": "agents", "title": "Open agents",
        "kind": "happy_path", "steps": steps, "expected": expected,
    }
    case = TestCaseSpec.model_validate(native)
    task = {"cleanup": {"kind": "none_required"}}
    definition = {
        **native, "task": task, "safety": case.safety,
        "success_assertion": {"url": steps[0]["url"], "state_id": "observed-state"},
    }
    task["contract_digest"] = task_contract_digest(definition)
    version_id = uuid4()
    entry = {
        "skill_id": str(uuid4()), "skill_version_id": str(version_id),
        "skill_kind": "task", "lifecycle_status": "active", "definition": definition,
    }
    app_map = {"skills": [entry]}
    assert match_read_only_task_skill(app_map, case, mode="read_only") == (version_id, entry)

    changed = TestCaseSpec.model_validate({
        **native, "expected": [{**expected[0], "expected_value": "Different"}],
    })
    assert match_read_only_task_skill(app_map, changed, mode="read_only") is None
    changed_url = TestCaseSpec.model_validate({
        **native, "steps": [{"action": "navigate", "url": steps[0]["url"] + "?team=other"}],
    })
    assert match_read_only_task_skill(app_map, changed_url, mode="read_only") is None
    entry["lifecycle_status"] = "suspect"
    assert match_read_only_task_skill(app_map, case, mode="read_only") is None
    entry["lifecycle_status"] = "active"
    task["cleanup"] = {"kind": "compensating_steps"}
    task["contract_digest"] = task_contract_digest(definition)
    assert match_read_only_task_skill(app_map, case, mode="standard") is None

ORIGIN = "http://fixture.local"

INVENTORY = [
    {"role": "link", "name": "Agents"},
    {"role": "link", "name": "New agent"},
    {"role": "link", "name": "View agents"},
    {"role": "link", "name": "Sign out"},
    {"role": "button", "name": "Create agent"},
    {"role": "button", "name": "Delete agent"},
    {"role": "button", "name": "Search"},
    {"role": "button", "name": "Sign in"},
    {"label": "Agent name"},
    {"label": "Model"},
    {"label": "Agent name to delete"},
    {"label": "Username"},
    {"label": "Password"},
    {"label": "Search the fixture"},
]
PAGE_URLS = [
    f"{ORIGIN}/",
    f"{ORIGIN}/search",
    f"{ORIGIN}/agents",
    f"{ORIGIN}/agents/new",
    f"{ORIGIN}/agents/created",
    f"{ORIGIN}/login",
    f"{ORIGIN}/account",
]
STEP_SAFETY = ["read", "read", "reversible", "reversible", "read", "read"]


def make_task_definition():
    """The fixture create-an-agent task, compiled shape (doc 29 §3.2)."""
    return {
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
                    "key": "agent_name",
                    "label": "Agent name",
                    "kind": "text",
                    "required": True,
                    "disposable": True,
                },
                {
                    "key": "agent_model",
                    "label": "Model",
                    "kind": "selection",
                    "required": True,
                    "disposable": True,
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
    }


def make_trace(**overrides):
    """The TS-2 trace shape (consult C1): assertion records carry
    id + oracle + status only -- never expected values."""
    trace = {
        "case_id": "create_agent_one",
        "complete": True,
        "spec_steps": [
            {"ordinal": index, "action": action, "outcome": "completed"}
            for index, action in enumerate(
                ["navigate", "click", "fill", "select", "click", "click"], start=1
            )
        ],
        "assertions": [
            {
                "assertion_id": "agent_present",
                "oracle": "visible_text",
                "status": "satisfied",
            }
        ],
        "segments": [],
        "terminal": {
            "url": f"{ORIGIN}/agents",
            "state_id": "fixture-agents-state",
            "element_signature": ["link|Agents", "link|New agent"],
        },
    }
    trace.update(overrides)
    return trace


def evidence_for(definition, *, status="satisfied"):
    """The trusted evidence context a host assembles from the
    executed spec + trace results (consult B3): full predicates
    from the spec side, results from the trace side."""
    return {
        "assertions": [
            {
                "assertion_id": entry["assertion_id"],
                "after_step_ordinal": entry.get("after_step_ordinal"),
                "oracle": entry.get("oracle"),
                "target": entry.get("target"),
                "expected_value": entry.get("expected_value"),
                "status": status,
                "has_evidence": True,
            }
            for entry in definition.get("expected") or []
        ],
        "owner_decisions": [],
    }


def validate(definition, **kwargs):
    kwargs.setdefault("inventory", INVENTORY)
    kwargs.setdefault("page_urls", PAGE_URLS)
    kwargs.setdefault("step_safety", STEP_SAFETY)
    return validate_task_skill(definition, **kwargs)


# T-TS1: the contract validator (doc 29 section 3.3 + consult
# amendments A1/A2/B1-B7) -- a well-formed task skill validates, and
# every rejection code fires on its crafted violation.
def test_t_ts1_valid_task_skill_and_candidate_pass():
    definition = make_task_definition()
    assert validate(
        definition, trace=make_trace(), evidence=evidence_for(definition)
    ) == []
    candidate = {
        "title": "Create an agent (from docs)",
        "task": {
            "purpose": "Create an agent named {agent_name}",
            "feature_key": "agents_create",
            "source": {"kind": "document", "document_ref": "docs:create-agent"},
            "prerequisites": [{"kind": "authenticated"}],
            "inputs": [
                {
                    "key": "agent_name",
                    "label": "Agent name",
                    "kind": "text",
                    "required": False,
                    "disposable": True,
                }
            ],
            "documented_expectations": [
                {
                    "text": "Agents can be created from natural language.",
                    "origin": "documentation",
                    "source_ref": "docs:create-agent",
                }
            ],
            "evidence_refs": [],
        },
    }
    assert validate(candidate) == []


def test_t_ts1_missing_evidence_rejected():
    definition = make_task_definition()
    definition["task"]["evidence_refs"] = []
    assert "missing_evidence" in validate(definition)


def test_t_ts1_unsupported_target_rejected():
    definition = make_task_definition()
    definition["steps"][1]["target"] = {"role": "link", "name": "Teleport"}
    assert "unsupported_target" in validate(definition)
    bogus = make_task_definition()
    bogus["steps"][0] = {"action": "submit", "url": f"{ORIGIN}/agents"}
    assert "unsupported_target" in validate(bogus)


def test_t_ts1_missing_input_binding_rejected():
    definition = make_task_definition()
    definition["steps"][2]["test_value_key"] = "undeclared_key"
    assert "missing_input_binding" in validate(definition)


def test_t_ts1_uncheckable_outcome_rejected():
    definition = make_task_definition()
    definition["expected"] = [
        {"assertion_id": "agent_present", "text": "the agent shows up"}
    ]
    assert "uncheckable_outcome" in validate(definition)


def test_t_ts1_marketing_claim_outcome_rejected_by_origin_gate():
    definition = make_task_definition()
    definition["expected"][0]["origin"] = "documentation"
    definition["task"]["observed_assertions"] = []
    assert "marketing_claim_outcome" in validate(definition)


def test_t_ts1_marketing_claim_outcome_rejected_by_text_gate():
    definition = make_task_definition()
    definition["task"]["documented_expectations"] = [
        {
            "text": "Create an agent and see it in the list",
            "origin": "documentation",
            "source_ref": "fixture-docs",
        }
    ]
    definition["expected"] = [
        {
            "assertion_id": "create_an_agent_and_see_it_in_the_list",
            "oracle": "visible_text",
            "target": {"text": "Create an agent and see it in the list"},
            "expected_value": "Create an agent and see it in the list",
            "origin": "inferred",
        }
    ]
    definition["task"]["observed_assertions"] = []
    codes = validate(definition)
    assert "marketing_claim_outcome" in codes


def test_t_ts1_unobserved_outcome_rejected():
    definition = make_task_definition()
    definition["task"]["observed_assertions"] = []
    assert "unobserved_outcome" in validate(definition)


def test_t_ts1_missing_cleanup_rejected():
    definition = make_task_definition()
    definition["task"]["cleanup"] = {"kind": "none_required"}
    assert "missing_cleanup" in validate(definition)
    not_disposable = make_task_definition()
    not_disposable["task"]["inputs"][0]["disposable"] = False
    assert "missing_cleanup" in validate(not_disposable)


def test_observation_requires_explicit_declaration():
    definition = make_task_definition()
    definition["task"]["observed_assertions"] = []
    for entry in definition["expected"]:
        entry["origin"] = "observation"
    assert "unobserved_outcome" in validate(definition, evidence=evidence_for(definition))


def test_input_generator_is_closed_and_text_only():
    for kind, generator in (("text", "unknown"), ("selection", "unique_text"),
                            ("secret_ref", "unique_email")):
        definition = make_task_definition()
        definition["task"]["inputs"][0].update(kind=kind, generator=generator)
        assert "missing_input_binding" in validate(definition)


def test_t_ts1_incomplete_trace_rejected():
    codes = validate(make_task_definition(), trace=make_trace(complete=False))
    assert "incomplete_trace" in codes


def test_t_ts1_assisted_step_uncompilable_rejected():
    trace = make_trace(
        segments=[
            {"kind": "assisted_other", "from_step": 2, "to_step": 3,
             "reason_code": "absent_target"}
        ]
    )
    codes = validate(make_task_definition(), trace=trace)
    assert "assisted_step_uncompilable" in codes


# Consult B7: the four evidence-context cases.
def test_t_ts1_observation_must_resolve_in_evidence():
    definition = make_task_definition()
    # The recorded occurrence exists but did not hold.
    codes = validate(
        definition,
        trace=make_trace(),
        evidence=evidence_for(definition, status="not_satisfied"),
    )
    assert "outcome_evidence_mismatch" in codes
    # No trusted context at all: fail closed.
    codes = validate(definition, trace=make_trace())
    assert "outcome_evidence_mismatch" in codes


def test_t_ts1_borrowed_assertion_id_with_changed_value_rejected():
    definition = make_task_definition()
    evidence = evidence_for(definition)
    # Same assertion_id, different recorded value: ID membership is
    # not evidence (B3) -- the predicate no longer matches.
    evidence["assertions"][0]["expected_value"] = "Agent Two"
    codes = validate(definition, trace=make_trace(), evidence=evidence)
    assert "outcome_evidence_mismatch" in codes


def test_equivalent_predicate_evidence_requires_every_record_to_pass():
    definition = make_task_definition()
    evidence = evidence_for(definition)
    evidence["assertions"].append(dict(evidence["assertions"][0]))
    assert validate(definition, trace=make_trace(), evidence=evidence) == []
    evidence["assertions"][-1]["status"] = "not_satisfied"
    assert "outcome_evidence_mismatch" in validate(
        definition, trace=make_trace(), evidence=evidence,
    )


def test_t_ts1_owner_rule_requires_decision_record():
    definition = make_task_definition()
    definition["task"]["observed_assertions"] = [
        {
            "assertion_id": "agent_present",
            "origin": "owner-rule",
            "decision_ref": "decision-42",
            "oracle": "visible_text",
            "expected_value": "Agent One",
            "value_key": "agent_name",
        }
    ]
    # No decision record in the trusted context: reject (B2).
    codes = validate(
        definition, trace=make_trace(),
        evidence={"assertions": [], "owner_decisions": []},
    )
    assert "outcome_evidence_mismatch" in codes
    # The authenticated record for exactly this predicate: passes.
    evidence = {
        "assertions": [],
        "owner_decisions": [
            {
                "decision_ref": "decision-42",
                "after_step_ordinal": 6,
                "oracle": "visible_text",
                "target": {"text": "Agent One"},
                "expected_value": "Agent One",
            }
        ],
    }
    assert validate(definition, trace=make_trace(), evidence=evidence) == []


def test_t_ts1_inferred_origin_rejected():
    definition = make_task_definition()
    definition["task"]["observed_assertions"] = [
        {
            "assertion_id": "agent_present",
            "origin": "inferred",
            "oracle": "visible_text",
            "expected_value": "Agent One",
            "value_key": "agent_name",
        }
    ]
    codes = validate(
        definition, trace=make_trace(), evidence=evidence_for(definition)
    )
    assert "unobserved_outcome" in codes
    assert "outcome_evidence_mismatch" not in codes


def test_t_ts1_url_predicate_normalisation():
    definition = make_task_definition()
    definition["expected"] = [
        {
            "assertion_id": "on_agents_page",
            "oracle": "url",
            "expected_value": f"{ORIGIN}/agents",
            "origin": "inferred",
            "after_step_ordinal": 6,
        }
    ]
    definition["task"]["observed_assertions"] = [
        {
            "assertion_id": "on_agents_page",
            "origin": "observation",
            "oracle": "url",
            "expected_value": f"{ORIGIN}/agents",
        }
    ]
    # Differing only in query/fragment: the same predicate (B5).
    evidence = evidence_for(definition)
    evidence["assertions"][0]["expected_value"] = (
        f"{ORIGIN}/agents?utm_source=nav#top"
    )
    assert validate(definition, trace=make_trace(), evidence=evidence) == []
    # Differing in path: a different predicate.
    evidence = evidence_for(definition)
    evidence["assertions"][0]["expected_value"] = f"{ORIGIN}/agents-old?utm=x"
    codes = validate(definition, trace=make_trace(), evidence=evidence)
    assert "outcome_evidence_mismatch" in codes


# ---------------------------------------------------------------------
# T-TS2: capture (doc 29 section 4, consults C1-C3) -- the recorder's
# unit behaviour and the persisted test_case.task_trace event.
# ---------------------------------------------------------------------
import json

import pytest


def _trace_case():
    from markettwin_shared.feature_plan import (
        CaseAction,
        ExpectedAssertion,
        SemanticTarget,
        TestCaseSpec,
    )

    return TestCaseSpec(
        case_id="create_agent_one",
        feature_key="agents_create",
        title="Create an agent and see it in the list",
        kind="happy_path",
        steps=(
            CaseAction(
                action="fill",
                target=SemanticTarget(label="Agent name"),
                test_value_key="agent_name",
            ),
            CaseAction(
                action="click",
                target=SemanticTarget(role="button", name="Create agent"),
            ),
        ),
        expected=(
            ExpectedAssertion(
                assertion_id="agent_present",
                oracle="visible_text",
                target=SemanticTarget(text="Agent visible"),
                expected_value="Agent visible",
                origin="inferred",
            ),
        ),
    )


def test_t_ts2_recorder_captures_steps_assertions_terminal():
    from markettwin_execution_orchestrator.workflow.task_trace import (
        TaskTraceRecorder,
    )

    case = _trace_case()
    recorder = TaskTraceRecorder(case=case, start_url=f"{ORIGIN}/agents")
    recorder.record_step(
        action_type="navigate", case_action=None,
        locator_strategy=None, outcome="completed",
    )
    recorder.observe_url(f"{ORIGIN}/agents")
    recorder.record_step(
        action_type="fill", case_action=case.steps[0],
        locator_strategy=None, outcome="completed",
    )
    recorder.record_step(
        action_type="click", case_action=case.steps[1],
        locator_strategy="aria", outcome="completed",
    )
    recorder.observe_url(f"{ORIGIN}/agents")
    recorder.record_assertion(
        assertion_id="agent_present", oracle="visible_text", status="satisfied"
    )
    recorder.set_terminal(
        {
            "url": f"{ORIGIN}/agents",
            "state_id": "state-1",
            "element_signature": ["link|Agents"],
        }
    )
    payload = recorder.payload(case_status="completed")
    assert payload["complete"] is True
    steps = payload["spec_steps"]
    assert [step["action"] for step in steps] == ["navigate", "fill", "click"]
    assert steps[0]["url"] == f"{ORIGIN}/agents"
    assert steps[0]["source_page_url"] == f"{ORIGIN}/agents"
    assert steps[1]["target"] == {"label": "Agent name"}
    assert steps[1]["test_value_key"] == "agent_name"
    # C3: fill locator strategies are unrecorded today -- honestly None.
    assert steps[1]["locator_strategy"] is None
    assert steps[2]["target"] == {"role": "button", "name": "Create agent"}
    assert steps[2]["source_page_url"] == f"{ORIGIN}/agents"
    # C1: assertion records carry id + oracle + status only.
    assert payload["assertions"] == [
        {
            "assertion_id": "agent_present",
            "oracle": "visible_text",
            "status": "satisfied",
        }
    ]
    assert payload["terminal"]["state_id"] == "state-1"
    assert payload["spec"]["case_id"] == "create_agent_one"


@pytest.mark.asyncio
@pytest.mark.parametrize("trace_write_fails", [False, True])
async def test_t_ts2_case_execution_persists_task_trace(monkeypatch, trace_write_fails):
    from types import SimpleNamespace
    from uuid import uuid4

    from markettwin_execution_orchestrator.agents.schemas.test_case import (
        PlanBudget,
    )
    from markettwin_execution_orchestrator.browser.contracts import (
        AllowedOrigin,
        BrowserSessionHandle,
    )
    from markettwin_execution_orchestrator.harvest import (
        harvest_capture,
        harvest_inventory,
    )
    from markettwin_execution_orchestrator.workflow import case_execution
    from markettwin_execution_orchestrator.workflow.case_execution import (
        PersonaJourneyExecutionRequest,
    )
    from markettwin_execution_orchestrator.workflow.feature_scope import (
        case_journey,
    )
    from markettwin_shared.feature_plan import FeatureScope, SafeTestValue

    case = _trace_case()
    execution_id, journey_id, run_id = uuid4(), uuid4(), uuid4()
    scope = FeatureScope(
        feature_key="agents_create",
        goal="Create an agent",
        starting_url=f"{ORIGIN}/agents",
        allowed_origins=(ORIGIN,),
        safe_test_data=(
            SafeTestValue(key="agent_name", value="S3cret-Agent-Name"),
        ),
    )
    request = PersonaJourneyExecutionRequest(
        test_run_id=run_id,
        execution_id=execution_id,
        journey_id=journey_id,
        persona_id=uuid4(),
        mission_id=uuid4(),
        journey=case_journey(case),
        start_url=f"{ORIGIN}/agents",
        allowed_origins=(AllowedOrigin(scheme="http", hostname="fixture.local"),),
        max_duration_seconds=30,
    )

    class FakeSession:
        def __init__(self):
            self.added = []
            self.rollbacks = 0

        def add(self, row):
            self.added.append(row)

        async def flush(self):
            pass

        async def commit(self):
            pass

        async def rollback(self):
            self.rollbacks += 1

        async def scalars(self, query):
            if query.column_descriptions[0]["entity"] is case_execution.RunEvent:
                return []
            return [uuid4()]

    session = FakeSession()

    class FakeEvents:
        def __init__(self, _session):
            self.events = []

        async def create(self, *, event_type, payload, **_kwargs):
            self.events.append((event_type, payload))

    events = FakeEvents(session)

    class FakeExecutionRepository:
        def __init__(self, _session):
            pass

        async def create_browser_session(self, **_kwargs):
            pass

        async def mark_browser_session_closed(self, **_kwargs):
            pass

    class FakeRecorder:
        def __init__(self, _session, _execution_id, _storage):
            self.next_id = 0

        async def start_step(self, *, action_type, action_summary):
            self.next_id += 1
            return self.next_id

        async def record_evidence(self, *, step_id, result):
            pass

        async def record_failure_evidence(self, *, step_id, result):
            pass

        async def finish_step(self, *, step_id, status, observation_summary=None):
            pass

        async def begin_sensitive_action(self, **_kwargs):
            # The test plays the human approver the production
            # recorder waits for (the DB-backed approval gate has
            # its own suites); the controller still re-derives the
            # intent at dispatch and checks the fingerprint.
            return uuid4()

        async def finish_sensitive_action(self, **_kwargs):
            pass

    class FakeArtifacts:
        def __init__(self, *_args):
            pass

        async def record(self, _artifacts):
            pass

    class FakeController:
        def __init__(self):
            self.handle = BrowserSessionHandle(execution_id, journey_id, uuid4())

        async def create_session(self, **_kwargs):
            return self.handle

        def bind_cooperative_pause_handler(self, *_args):
            pass

        async def cooperative_checkpoint(self, _handle):
            pass

        async def navigate(self, **_kwargs):
            return SimpleNamespace(
                observation=SimpleNamespace(url=f"{ORIGIN}/agents"),
                locator_strategy=None,
            )

        async def inspect_click_approval(self, **_kwargs):
            return None

        async def read_assertion(self, *, assertion, **_kwargs):
            return (
                SimpleNamespace(),
                SimpleNamespace(
                    status="satisfied",
                    observed_value="Agent visible",
                    elapsed_ms=1,
                    reason=None,
                ),
            )

        async def close_session(self, **_kwargs):
            return SimpleNamespace()

    controller = FakeController()

    async def fake_perform(_controller, _handle, action, _scope):
        return SimpleNamespace(
            observation=SimpleNamespace(url=f"{ORIGIN}/agents"),
            locator_strategy="aria" if action.action == "click" else None,
        )

    async def fake_capture(_controller, _handle, *, execution_id, journey_id):
        return SimpleNamespace(url=f"{ORIGIN}/agents")

    async def no_pause(_session, _handle):
        pass

    monkeypatch.setattr(case_execution, "RunEventRepository", lambda _s: events)
    monkeypatch.setattr(
        case_execution, "ExecutionRepository", FakeExecutionRepository
    )
    monkeypatch.setattr(case_execution, "ExecutionStepRecorder", FakeRecorder)
    monkeypatch.setattr(case_execution, "SessionArtifactRecorder", FakeArtifacts)
    monkeypatch.setattr(
        case_execution.S3ArtifactStorage,
        "from_environment",
        classmethod(lambda _cls: object()),
    )
    monkeypatch.setattr(case_execution, "perform_case_action", fake_perform)
    monkeypatch.setattr(harvest_capture, "capture_state", fake_capture)
    monkeypatch.setattr(
        harvest_inventory, "distil_elements",
        lambda c: [{"role": "link", "name": "Agents"}],
    )
    monkeypatch.setattr(harvest_inventory, "distil_forms", lambda c: [])
    monkeypatch.setattr(
        harvest_inventory, "identity_for", lambda url, e, f: ("state-1", None, None)
    )
    from markettwin_execution_orchestrator.workflow import cooperative_pause

    monkeypatch.setattr(cooperative_pause, "finalize_browser_pauses", no_pause)
    if trace_write_fails:
        from markettwin_execution_orchestrator.workflow import task_spec_store

        async def fail_trace_write(*args, **kwargs):
            raise RuntimeError("Simulated optional trace flush failure")

        monkeypatch.setattr(task_spec_store, "store_task_spec", fail_trace_write)

    result = await case_execution.execute_test_case(
        request=request,
        case=case,
        scope=scope,
        budget=PlanBudget(max_steps=8),
        controller=controller,
        session=session,
    )
    assert result.execution_status == "completed"
    traces = [p for kind, p in events.events if kind == "test_case.task_trace"]
    if trace_write_fails:
        assert not traces
        assert session.rollbacks == 1
        assert any(kind == "test_case.completed" for kind, _ in events.events)
        return
    assert len(traces) == 1
    trace = traces[0]
    assert trace["complete"] is True
    assert [s["action"] for s in trace["spec_steps"]] == [
        "navigate",
        "fill",
        "click",
    ]
    assert trace["spec_steps"][1]["test_value_key"] == "agent_name"
    assert trace["spec_steps"][2]["target"] == {
        "role": "button",
        "name": "Create agent",
    }
    assert trace["assertions"] == [
        {
            "assertion_id": "agent_present",
            "oracle": "visible_text",
            "status": "satisfied",
        }
    ]
    assert trace["terminal"]["state_id"] == "state-1"
    # Keys, never values: the approved fill value appears nowhere.
    assert "S3cret-Agent-Name" not in json.dumps(trace)


# T-TS3 (capture half): failed / interrupted / assisted traces are
# incomplete and refused at compile; the compile half lands in TS-3.
def test_t_ts3_incomplete_traces_are_refused():
    from markettwin_execution_orchestrator.workflow.task_trace import (
        TaskTraceRecorder,
    )

    case = _trace_case()
    recorder = TaskTraceRecorder(case=case, start_url=f"{ORIGIN}/agents")
    recorder.record_step(
        action_type="navigate", case_action=None,
        locator_strategy=None, outcome="completed",
    )
    recorder.record_step(
        action_type="fill", case_action=case.steps[0],
        locator_strategy=None, outcome="failed",
    )
    payload = recorder.payload(case_status="failed")
    assert payload["complete"] is False
    codes = validate(make_task_definition(), trace=payload)
    assert "incomplete_trace" in codes

    assisted = TaskTraceRecorder(case=case, start_url=f"{ORIGIN}/agents")
    assisted.note_segment(
        kind="assisted_other", from_step=1, to_step=1,
        reason_code="absent_target",
    )
    codes = validate(
        make_task_definition(), trace=assisted.payload(case_status="completed")
    )
    assert "assisted_step_uncompilable" in codes


# ---------------------------------------------------------------------
# T-TS3 (compile half) / T-TS4 / T-TS5: harvest/task_compile.py
# against a fake repository over the fixture-shaped map.
# ---------------------------------------------------------------------
from types import SimpleNamespace
from uuid import uuid4


def _fixture_spec():
    from markettwin_shared.feature_plan import (
        CaseAction,
        ExpectedAssertion,
        SemanticTarget,
        TestCaseSpec,
    )

    return TestCaseSpec(
        case_id="create_agent_one",
        feature_key="agents_create",
        title="Create an agent and see it in the list",
        kind="happy_path",
        steps=(
            CaseAction(
                action="click",
                target=SemanticTarget(role="link", name="New agent"),
            ),
            CaseAction(
                action="fill",
                target=SemanticTarget(label="Agent name"),
                test_value_key="agent_name",
            ),
            CaseAction(
                action="select",
                target=SemanticTarget(label="Model"),
                test_value_key="agent_model",
            ),
            CaseAction(
                action="click",
                target=SemanticTarget(role="button", name="Create agent"),
            ),
            CaseAction(
                action="click",
                target=SemanticTarget(role="link", name="View agents"),
            ),
        ),
        expected=(
            ExpectedAssertion(
                assertion_id="agent_present",
                oracle="visible_text",
                target=SemanticTarget(text="Agent One"),
                expected_value="Agent One",
                origin="inferred",
                after_step_ordinal=5,
            ),
        ),
    )


def _fixture_trace(spec, *, assertion_status="satisfied"):
    from markettwin_execution_orchestrator.workflow.task_trace import (
        TaskTraceRecorder,
    )

    recorder = TaskTraceRecorder(case=spec, start_url=f"{ORIGIN}/agents")
    recorder.record_step(
        action_type="navigate", case_action=None,
        locator_strategy=None, outcome="completed",
    )
    recorder.observe_url(f"{ORIGIN}/agents")
    recorder.record_step(
        action_type="click", case_action=spec.steps[0],
        locator_strategy="aria", outcome="completed",
    )
    recorder.observe_url(f"{ORIGIN}/agents/new")
    recorder.record_step(
        action_type="fill", case_action=spec.steps[1],
        locator_strategy=None, outcome="completed",
    )
    recorder.record_step(
        action_type="select", case_action=spec.steps[2],
        locator_strategy=None, outcome="completed",
    )
    recorder.record_step(
        action_type="click", case_action=spec.steps[3],
        locator_strategy="aria", outcome="completed",
    )
    recorder.observe_url(f"{ORIGIN}/agents/created")
    recorder.record_step(
        action_type="click", case_action=spec.steps[4],
        locator_strategy="aria", outcome="completed",
    )
    recorder.observe_url(f"{ORIGIN}/agents")
    recorder.record_assertion(
        assertion_id="agent_present",
        oracle="visible_text",
        status=assertion_status,
    )
    recorder.set_terminal(
        {
            "url": f"{ORIGIN}/agents",
            "state_id": "fixture-agents-state",
            "element_signature": ["link|Agents", "link|New agent"],
        }
    )
    return recorder.payload(case_status="completed")


class _FakeCompileRepository:
    """The HarvestRepository surface compile_task_trace uses."""

    def __init__(self, *, with_candidate=True):
        self.pages = [
            SimpleNamespace(id=uuid4(), canonical_url=f"{ORIGIN}/agents"),
            SimpleNamespace(id=uuid4(), canonical_url=f"{ORIGIN}/agents/new"),
        ]
        self.states = [
            SimpleNamespace(
                id=uuid4(), map_page_id=self.pages[0].id,
                state_id="fixture-agents-state",
            ),
            SimpleNamespace(
                id=uuid4(), map_page_id=self.pages[1].id,
                state_id="fixture-new-state",
            ),
        ]
        self.elements = {
            self.states[0].id: [
                SimpleNamespace(
                    role="link", name="Agents", label_text=None,
                    locators=[{"kind": "role_name"}],
                ),
                SimpleNamespace(
                    role="link", name="New agent", label_text=None,
                    locators=[{"kind": "role_name"}],
                ),
                SimpleNamespace(
                    role="link", name="View agents", label_text=None,
                    locators=[{"kind": "role_name"}],
                ),
            ],
            self.states[1].id: [
                SimpleNamespace(
                    role="textbox", name="Agent name",
                    label_text="Agent name",
                    locators=[{"kind": "label"}],
                ),
                SimpleNamespace(
                    role="combobox", name="Model", label_text="Model",
                    locators=[{"kind": "label"}],
                ),
                SimpleNamespace(
                    role="button", name="Create agent", label_text=None,
                    locators=[{"kind": "role_name"}],
                ),
            ],
        }
        self.skills = []
        self.versions = {}
        self.usage = []
        self.created = []
        self.appended = []
        self.packages = []
        if with_candidate:
            skill = SimpleNamespace(
                id=uuid4(), skill_kind="task", name="create-an-agent",
            )
            version = SimpleNamespace(
                id=uuid4(),
                skill_id=skill.id,
                workspace_id=uuid4(),
                app_map_id=uuid4(),
                version_number=1,
                lifecycle_status="draft",
                definition_json={
                    "task": {
                        "feature_key": "agents_create",
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
                                    "target": {
                                        "role": "button",
                                        "name": "Delete agent",
                                    },
                                },
                            ],
                        },
                        "documented_expectations": [
                            {
                                "text": "Agents can be created from natural language.",
                                "origin": "documentation",
                                "source_ref": "fixture-docs",
                            }
                        ],
                    }
                },
            )
            self.skills.append(skill)
            self.versions[skill.id] = [version]

    async def list_skills_for_scope(self, *, workspace_id, application_id, target_id):
        return list(self.skills)

    async def list_versions_for_skill(self, skill_id):
        return list(self.versions.get(skill_id, []))

    async def work_list(self, app_map):
        return list(self.pages)

    async def list_journeys(self, map_id):
        return []

    async def get_journey(self, journey_id):
        return None

    async def list_states_for_map(self, map_id):
        return list(self.states)

    async def list_elements_for_state(self, state_id):
        return list(self.elements.get(state_id, []))

    async def create_task_skill(self, app_map, *, name, definition, package):
        skill = SimpleNamespace(id=uuid4(), skill_kind="task", name=name)
        version = SimpleNamespace(
            id=uuid4(), skill_id=skill.id, workspace_id=app_map.workspace_id,
            app_map_id=app_map.id, version_number=1,
            lifecycle_status="draft", definition_json=definition,
        )
        self.skills.append(skill)
        self.versions[skill.id] = [version]
        self.created.append((skill, version))
        self.packages.append(package)
        return skill, version

    async def append_skill_version(
        self, skill, app_map, *, definition, package, heal_of_version_id=None,
        source="phase-3-compile",
    ):
        version = SimpleNamespace(
            id=uuid4(), skill_id=skill.id, workspace_id=app_map.workspace_id,
            app_map_id=app_map.id,
            version_number=len(self.versions.get(skill.id, [])) + 1,
            lifecycle_status="draft", definition_json=definition,
        )
        self.versions.setdefault(skill.id, []).append(version)
        self.appended.append(version)
        self.packages.append(package)
        return version

    async def insert_usage_event(self, version, **kwargs):
        self.usage.append((version, kwargs))
        return SimpleNamespace()


def _fake_app_map():
    return SimpleNamespace(
        id=uuid4(), workspace_id=uuid4(), application_id=uuid4(),
        target_id=uuid4(), version_number=2, base_url=ORIGIN,
    )


@pytest.mark.asyncio
async def test_t_ts4_compile_fidelity_against_the_trace():
    from markettwin_execution_orchestrator.harvest.task_compile import (
        compile_task_trace,
    )
    from markettwin_shared.task_skill import task_contract_digest

    spec = _fixture_spec()
    trace = _fixture_trace(spec)
    repository = _FakeCompileRepository()
    run_id = uuid4()
    app_map = _fake_app_map()
    outcome = await compile_task_trace(
        trace=trace,
        spec=spec,
        app_map=app_map,
        repository=repository,
        run_id=run_id,
        approved_values={"agent_name": "Agent One", "agent_model": "GPT-6 Luna"},
    )
    assert outcome.status == "compiled", outcome.codes
    # The candidate received the new version; no duplicate skill.
    assert repository.created == []
    assert len(repository.appended) == 1
    assert len(repository.skills) == 1
    definition = outcome.definition
    # D2: the initial navigation leads; the spec steps follow in order.
    assert [s["action"] for s in definition["steps"]] == [
        "navigate", "click", "fill", "select", "click", "click",
    ]
    assert definition["steps"][0]["url"] == f"{ORIGIN}/agents"
    assert definition["steps"][2]["test_value_key"] == "agent_name"
    assert definition["steps"][2]["target"] == {"label": "Agent name"}
    bindings = definition["locator_bindings"]
    assert [b["order"] for b in bindings] == [2, 3, 4, 5, 6]
    assert bindings[0]["page_url"] == f"{ORIGIN}/agents"
    assert bindings[0]["locators"][0] == {"kind": "aria"}  # trace first
    assert bindings[1]["value_source"] == "agent_name"
    assert {"kind": "label"} in bindings[1]["locators"]  # map-ranked next
    # Expected: the spec's assertion, checkpoint remapped past the
    # prepended navigation; native origin kept as history, the
    # observation declared in the task block with its value key.
    assert definition["expected"][0]["after_step_ordinal"] == 6
    assert definition["expected"][0]["origin"] == "inferred"
    observed = definition["task"]["observed_assertions"]
    assert observed[0]["origin"] == "observation"
    assert observed[0]["value_key"] == "agent_name"
    assert definition["success_assertion"]["state_id"] == "fixture-agents-state"
    task = definition["task"]
    assert task["source"] == {
        "kind": "run_execution", "run_id": str(run_id),
        "case_id": "create_agent_one",
    }
    # Owner knowledge inherited verbatim from the candidate.
    assert task["cleanup"]["kind"] == "compensating_steps"
    assert task["documented_expectations"][0]["text"] == (
        "Agents can be created from natural language."
    )
    assert task["contract_digest"] == task_contract_digest(definition)
    # The compile attempt is on the usage ledger.
    assert [kw["kind"] for _, kw in repository.usage] == ["compile"]
    assert repository.usage[0][1]["result"] == "applied"
    duplicate = await compile_task_trace(
        trace=trace, spec=spec, app_map=app_map, repository=repository, run_id=run_id,
        approved_values={"agent_name": "Agent One", "agent_model": "GPT-6 Luna"},
    )
    assert duplicate.status == "unchanged"
    assert duplicate.version is outcome.version
    assert len(repository.appended) == 1


@pytest.mark.asyncio
async def test_t_ts4_doctored_traces_are_rejected_not_repaired():
    from markettwin_execution_orchestrator.harvest.task_compile import (
        compile_task_trace,
    )

    spec = _fixture_spec()
    # A failed step: refused with the trace code, no rows written.
    trace = _fixture_trace(spec)
    trace["spec_steps"][2]["outcome"] = "failed"
    trace["complete"] = False
    repository = _FakeCompileRepository()
    outcome = await compile_task_trace(
        trace=trace, spec=spec, app_map=_fake_app_map(),
        repository=repository, run_id=uuid4(),
        approved_values={"agent_name": "Agent One"},
    )
    assert outcome.status == "rejected"
    assert "incomplete_trace" in outcome.codes
    assert repository.appended == [] and repository.created == []

    # A target the map has never seen: refused, never approximated.
    from markettwin_shared.feature_plan import SemanticTarget

    bad_spec = spec.model_copy(
        update={
            "steps": (
                spec.steps[0].model_copy(
                    update={"target": SemanticTarget(role="link", name="Teleport")}
                ),
            )
            + spec.steps[1:]
        }
    )
    trace = _fixture_trace(bad_spec)
    repository = _FakeCompileRepository()
    outcome = await compile_task_trace(
        trace=trace, spec=bad_spec, app_map=_fake_app_map(),
        repository=repository, run_id=uuid4(),
        approved_values={"agent_name": "Agent One"},
    )
    assert outcome.status == "rejected"
    assert "unsupported_target" in outcome.codes
    assert repository.appended == [] and repository.created == []


@pytest.mark.asyncio
async def test_t_ts3_compile_completeness_rule():
    """Consult D1's trap: every action completed, but one business
    assertion is unverified -- compile refuses; expected is built
    from the spec, never from the trace's passed subset."""
    from markettwin_execution_orchestrator.harvest.task_compile import (
        compile_task_trace,
    )

    spec = _fixture_spec()
    trace = _fixture_trace(spec, assertion_status="unverified")
    repository = _FakeCompileRepository()
    outcome = await compile_task_trace(
        trace=trace, spec=spec, app_map=_fake_app_map(),
        repository=repository, run_id=uuid4(),
        approved_values={"agent_name": "Agent One"},
    )
    assert outcome.status == "rejected"
    assert outcome.codes == ["incomplete_assertions"]
    assert repository.appended == [] and repository.created == []


@pytest.mark.asyncio
async def test_t_ts5_procedure_renders_from_the_definition():
    from markettwin_execution_orchestrator.harvest.harvest_skill import (
        render_definition_package,
    )
    from markettwin_execution_orchestrator.harvest.task_compile import (
        compile_task_trace,
    )

    spec = _fixture_spec()
    repository = _FakeCompileRepository()
    outcome = await compile_task_trace(
        trace=_fixture_trace(spec), spec=spec, app_map=_fake_app_map(),
        repository=repository, run_id=uuid4(),
        approved_values={"agent_name": "Agent One", "agent_model": "GPT-6 Luna"},
    )
    assert outcome.status == "compiled", outcome.codes
    definition = outcome.definition
    package = render_definition_package(definition)
    # The stored package IS this render (one source, rendered once).
    assert repository.packages[0] == package
    body = package["body_md"]
    assert "## Documented expectations (claims -- not executed)" in body
    assert "Agents can be created from natural language." in body
    assert "Fill Agent name using input agent_name." in body
    # Mutate the definition; the re-render changes identically.
    import copy

    mutated = copy.deepcopy(definition)
    mutated["steps"][2]["target"] = {"label": "Agent full name"}
    mutated["expected"][0]["expected_value"] = "Agent Two"
    mutated_body = render_definition_package(mutated)["body_md"]
    assert "Fill Agent full name using input agent_name." in mutated_body
    assert "Agent Two" in mutated_body
    assert mutated_body != body


# ---------------------------------------------------------------------
# T-TS6..T-TS9: verification against the live task fixture (real
# browser, real controller, fake repositories).
# ---------------------------------------------------------------------
import threading
import urllib.parse
import urllib.request
from pathlib import Path


def _start_fixture():
    import importlib.util

    path = Path(__file__).parent / "fixtures" / "task_fixture" / "server.py"
    module_spec = importlib.util.spec_from_file_location(
        "task_fixture_server", path
    )
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    server = module.TaskFixtureServer(0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def _fixture_state(origin):
    with urllib.request.urlopen(f"{origin}/__state", timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _fixture_post(origin, path, data):
    body = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(f"{origin}{path}", data=body, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status


class _FakeVerifyRepository:
    """The repository surface compile + verify + activation use,
    over a fixture-shaped map at a live origin."""

    def __init__(self, origin, *, candidate_task=None):
        self.origin = origin
        page_urls = [
            f"{origin}/",
            f"{origin}/agents",
            f"{origin}/agents/new",
            f"{origin}/login",
            f"{origin}/account",
        ]
        self.pages = [
            SimpleNamespace(id=uuid4(), canonical_url=url) for url in page_urls
        ]
        self.states = [
            SimpleNamespace(
                id=uuid4(), map_page_id=page.id, state_key="default",
                state_id=f"fixture-state-{index}",
            )
            for index, page in enumerate(self.pages)
        ]
        by_url = {page.canonical_url: page for page in self.pages}
        state_of = {
            page.id: state
            for page, state in zip(self.pages, self.states)
        }
        elements = {
            by_url[f"{origin}/agents"].id: [
                ("link", "Agents", None),
                ("link", "New agent", None),
                ("link", "View agents", None),
                ("button", "Delete agent", None),
                ("textbox", "Agent name to delete", "Agent name to delete"),
            ],
            by_url[f"{origin}/agents/new"].id: [
                ("textbox", "Agent name", "Agent name"),
                ("combobox", "Model", "Model"),
                ("button", "Create agent", None),
            ],
            by_url[f"{origin}/login"].id: [
                ("textbox", "Username", "Username"),
                ("textbox", "Password", "Password"),
                ("button", "Sign in", None),
            ],
            by_url[f"{origin}/account"].id: [
                ("link", "Sign out", None),
            ],
            by_url[f"{origin}/"].id: [
                ("link", "Agents", None),
                ("link", "Account", None),
                ("textbox", "Search the fixture", "Search the fixture"),
                ("button", "Search", None),
            ],
        }
        self.elements = {}
        for page in self.pages:
            state = state_of[page.id]
            self.elements[state.id] = [
                SimpleNamespace(
                    role=role, name=name, label_text=label,
                    locators=[
                        {
                            "kind": "label" if label else "role_name",
                            "value": label or f"{role}|{name}",
                        }
                    ],
                )
                for role, name, label in elements.get(page.id, [])
            ]
        self.skills = []
        self.versions = {}
        self.usage = []
        self.replays = []
        self.created = []
        self.appended = []
        self.packages = []
        if candidate_task is not None:
            skill = SimpleNamespace(
                id=uuid4(), skill_kind="task", name="candidate",
            )
            version = self._version(
                skill, 1, {"task": candidate_task},
            )
            self.skills.append(skill)
            self.versions[skill.id] = [version]

    def _version(self, skill, number, definition, app_map_id=None):
        return SimpleNamespace(
            id=uuid4(), skill_id=skill.id, workspace_id=uuid4(),
            app_map_id=app_map_id, version_number=number,
            lifecycle_status="draft", definition_json=definition,
            package={}, heal_count=0, replay_count=0,
            verified_fingerprint=None, last_replay_result=None,
            last_replay_at=None,
        )

    async def list_skills_for_scope(self, *, workspace_id, application_id, target_id):
        return list(self.skills)

    async def list_versions_for_skill(self, skill_id):
        return list(self.versions.get(skill_id, []))

    async def work_list(self, app_map):
        return list(self.pages)

    async def list_journeys(self, map_id):
        return []

    async def get_journey(self, journey_id):
        return None

    async def list_states_for_map(self, map_id):
        return list(self.states)

    async def list_elements_for_state(self, state_id):
        return list(self.elements.get(state_id, []))

    async def create_task_skill(self, app_map, *, name, definition, package):
        skill = SimpleNamespace(id=uuid4(), skill_kind="task", name=name)
        version = self._version(skill, 1, definition, app_map_id=app_map.id)
        version.package = package
        self.skills.append(skill)
        self.versions[skill.id] = [version]
        self.created.append((skill, version))
        self.packages.append(package)
        return skill, version

    async def append_skill_version(
        self, skill, app_map, *, definition, package, heal_of_version_id=None,
        source="phase-3-compile",
    ):
        version = self._version(
            skill, len(self.versions.get(skill.id, [])) + 1, definition,
            app_map_id=app_map.id,
        )
        version.package = package
        self.versions.setdefault(skill.id, []).append(version)
        self.appended.append(version)
        self.packages.append(package)
        return version

    async def insert_usage_event(self, version, **kwargs):
        self.usage.append((version, kwargs))
        return SimpleNamespace()

    async def insert_replay(self, app_map, **kwargs):
        row = SimpleNamespace(id=uuid4(), **kwargs)
        self.replays.append(row)
        return row

    async def update_skill_version(self, version_id, **fields):
        for versions in self.versions.values():
            for version in versions:
                if version.id == version_id:
                    for key, value in fields.items():
                        setattr(version, key, value)
                    return version
        raise KeyError(version_id)

    async def get_skill_version(self, version_id):
        for versions in self.versions.values():
            for version in versions:
                if version.id == version_id:
                    return version
        return None

    async def apply_skill_transition(self, version_id, *, fields, event):
        version = await self.get_skill_version(version_id)
        from markettwin_shared.app_map_common import check_skill_transition

        assert check_skill_transition(
            version.lifecycle_status, fields["lifecycle_status"], event["evidence"],
        ), "illegal lifecycle transition"
        for key, value in fields.items():
            setattr(version, key, value)
        self.usage.append((version, {"kind": event["kind"], **event}))
        return version


def _verify_app_map(origin):
    return SimpleNamespace(
        id=uuid4(), workspace_id=uuid4(), application_id=uuid4(),
        target_id=uuid4(), version_number=2, base_url=f"{origin}/",
    )


def _fixture_action_rules():
    """The owner-declared synthetic-effect contract for the fixture:
    the exact Create-agent effect, with its reset contract. This is
    the same rule shape the run approval gate matches; the learn
    case's session and every verification session carry it."""
    from markettwin_shared.action_approval import SensitiveActionRule

    return (
        SensitiveActionRule(
            category="create",
            role="button",
            name="Create agent",
            resource_reference="create-agent-fixture",
            test_data_reset_confirmed=True,
        ),
    )


def _candidate_task_block():
    return {
        "feature_key": "agents_create",
        # Cleanup is the fixture's reset action: the delete-by-name
        # control is hard-denied to agent clicks by the sensitive
        # action policy (delete is never approvable), so the
        # compensating-steps shape can never dispatch against the
        # real controller; the reset link is the dispatchable
        # owner-declared cleanup (doc 29 section 9's safety net).
        "cleanup": {
            "kind": "reset_action",
            "action": "Reset fixture data",
            "target": {"role": "link", "name": "Reset fixture data"},
        },
        "inputs": [
            {
                "key": "agent_name", "label": "Agent name", "kind": "text",
                "required": True, "disposable": True,
                "generator": "unique_text", "prefix": "Verify agent",
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
    }


async def _execute_case_live(monkeypatch, *, origin, case, values, start_url):
    """Run one case for real (TS-2's scaffolding, real controller)
    and return (result, events, trace_payload)."""
    from markettwin_execution_orchestrator.agents.schemas.test_case import (
        PlanBudget,
    )
    from markettwin_execution_orchestrator.browser.contracts import (
        AllowedOrigin,
    )
    from markettwin_execution_orchestrator.browser.controller import (
        BrowserController,
    )
    from markettwin_execution_orchestrator.workflow import case_execution
    from markettwin_execution_orchestrator.workflow.case_execution import (
        PersonaJourneyExecutionRequest,
    )
    from markettwin_execution_orchestrator.workflow.feature_scope import (
        case_journey,
    )
    from markettwin_shared.feature_plan import FeatureScope, SafeTestValue

    execution_id, journey_id, run_id = uuid4(), uuid4(), uuid4()
    parts = urllib.parse.urlsplit(origin)
    scope = FeatureScope(
        feature_key=case.feature_key,
        goal=case.title,
        starting_url=start_url,
        allowed_origins=(origin,),
        safe_test_data=tuple(
            SafeTestValue(key=key, value=value) for key, value in values.items()
        ),
    )
    request = PersonaJourneyExecutionRequest(
        test_run_id=run_id,
        execution_id=execution_id,
        journey_id=journey_id,
        persona_id=uuid4(),
        mission_id=uuid4(),
        journey=case_journey(case),
        start_url=start_url,
        allowed_origins=(
            AllowedOrigin(
                scheme=parts.scheme, hostname=parts.hostname, port=parts.port
            ),
        ),
        max_duration_seconds=300,
        network_policy="local_development",
        fixture_action_rules=_fixture_action_rules(),
    )

    class FakeSession:
        def __init__(self):
            self.added = []

        def add(self, row):
            self.added.append(row)

        async def flush(self):
            pass

        async def commit(self):
            pass

        async def rollback(self):
            pass

        async def scalars(self, _query):
            return [uuid4()]

        async def scalar(self, _query):
            return None

    session = FakeSession()

    class FakeEvents:
        def __init__(self, _session):
            self.events = []

        async def create(self, *, event_type, payload, **_kwargs):
            self.events.append((event_type, payload))

    events = FakeEvents(session)

    class FakeExecutionRepository:
        def __init__(self, _session):
            pass

        async def create_browser_session(self, **_kwargs):
            pass

        async def mark_browser_session_closed(self, **_kwargs):
            pass

    class FakeRecorder:
        def __init__(self, _session, _execution_id, _storage):
            self.next_id = 0

        async def start_step(self, *, action_type, action_summary):
            self.next_id += 1
            return self.next_id

        async def record_evidence(self, *, step_id, result):
            pass

        async def record_failure_evidence(self, *, step_id, result):
            pass

        async def finish_step(self, *, step_id, status, observation_summary=None):
            pass

        async def begin_sensitive_action(self, **_kwargs):
            # The test plays the human approver the production
            # recorder waits for (the DB-backed approval gate has
            # its own suites); the controller still re-derives the
            # intent at dispatch and checks the fingerprint.
            return uuid4()

        async def finish_sensitive_action(self, **_kwargs):
            pass

    class FakeArtifacts:
        def __init__(self, *_args):
            pass

        async def record(self, _artifacts):
            pass

    async def no_pause(_session, _handle):
        pass

    monkeypatch.setattr(case_execution, "RunEventRepository", lambda _s: events)
    monkeypatch.setattr(
        case_execution, "ExecutionRepository", FakeExecutionRepository
    )
    monkeypatch.setattr(case_execution, "ExecutionStepRecorder", FakeRecorder)
    monkeypatch.setattr(case_execution, "SessionArtifactRecorder", FakeArtifacts)
    monkeypatch.setattr(
        case_execution.S3ArtifactStorage,
        "from_environment",
        classmethod(lambda _cls: object()),
    )
    from markettwin_execution_orchestrator.workflow import cooperative_pause

    monkeypatch.setattr(cooperative_pause, "finalize_browser_pauses", no_pause)

    controller = BrowserController()
    result = await case_execution.execute_test_case(
        request=request,
        case=case,
        scope=scope,
        budget=PlanBudget(max_steps=24, max_total_seconds=300),
        controller=controller,
        session=session,
    )
    traces = [p for kind, p in events.events if kind == "test_case.task_trace"]
    from markettwin_execution_orchestrator.workflow.task_spec_store import restore_task_trace

    async def get_snapshot(model, ident):
        return next((row for row in session.added if row.id == ident), None)

    session.get = get_snapshot
    trace = (await restore_task_trace(
        session, payload=traces[0], run_id=run_id, execution_id=execution_id,
    )) if traces else None
    return result, events, trace, controller


def _create_agent_case(origin):
    from markettwin_shared.feature_plan import (
        CaseAction,
        ExpectedAssertion,
        SemanticTarget,
        TestCaseSpec,
    )

    return TestCaseSpec(
        case_id="create_agent_one",
        feature_key="agents_create",
        title="Create an agent and see it in the list",
        kind="happy_path",
        estimated_seconds=180,
        steps=(
            CaseAction(
                action="click",
                target=SemanticTarget(role="link", name="New agent"),
            ),
            CaseAction(
                action="fill",
                target=SemanticTarget(label="Agent name"),
                test_value_key="agent_name",
            ),
            CaseAction(
                action="select",
                target=SemanticTarget(label="Model"),
                test_value_key="agent_model",
            ),
            CaseAction(
                action="click",
                target=SemanticTarget(role="button", name="Create agent"),
            ),
            CaseAction(
                action="click",
                target=SemanticTarget(role="link", name="View agents"),
            ),
        ),
        expected=(
            ExpectedAssertion(
                assertion_id="agent_present",
                oracle="visible_text",
                target=SemanticTarget(text="Agent One"),
                expected_value="Agent One",
                origin="inferred",
            ),
        ),
    )


async def _compiled_create_draft(monkeypatch, origin):
    """Learn + compile the create-agent task against the good
    fixture; returns (repository, app_map, draft_version, trace)."""
    from markettwin_execution_orchestrator.harvest.task_compile import (
        compile_task_trace,
    )

    case = _create_agent_case(origin)
    result, _events, trace, controller = await _execute_case_live(
        monkeypatch,
        origin=origin,
        case=case,
        values={"agent_name": "Agent One", "agent_model": "Fixture Model A"},
        start_url=f"{origin}/agents",
    )
    assert result.execution_status == "completed", result
    assert trace is not None and trace["complete"] is True
    repository = _FakeVerifyRepository(
        origin, candidate_task=_candidate_task_block()
    )
    app_map = _verify_app_map(origin)
    outcome = await compile_task_trace(
        trace=trace,
        spec=case,
        app_map=app_map,
        repository=repository,
        run_id=uuid4(),
        approved_values={
            "agent_name": "Agent One",
            "agent_model": "Fixture Model A",
        },
    )
    assert outcome.status == "compiled", outcome.codes
    return repository, app_map, outcome.version, trace, controller


@pytest.mark.asyncio
async def test_t_ts6_verify_promote_and_cleanup(monkeypatch):
    from markettwin_execution_orchestrator.harvest.skill_library import (
        activate_current_versions,
    )
    from markettwin_execution_orchestrator.harvest.task_verify import (
        verify_task_draft,
    )

    server, origin = _start_fixture()
    controller = None
    try:
        repository, app_map, draft, trace, controller = (
            await _compiled_create_draft(monkeypatch, origin)
        )
        outcome = await verify_task_draft(
            repository=repository,
            app_map=app_map,
            skill_version=draft,
            controller=controller,
            profile={"agent_model": "Fixture Model A"},
            trace=trace,
            network_policy="local_development",
            fixture_action_rules=_fixture_action_rules(),
        )
        assert outcome["status"] == "replay_verified", outcome
        assert draft.lifecycle_status == "replay_verified"
        # Exactly two clean-context passes, zero model calls.
        assert len(repository.replays) == 2
        assert all(row.model_calls == 0 for row in repository.replays)
        assert all(row.context_kind == "clean" for row in repository.replays)
        assert all(row.result == "passed" for row in repository.replays)
        # Fresh generated names per pass, both recorded as evidence.
        generated = [
            kw["payload"]["generated"]
            for _version, kw in repository.usage
            if kw.get("kind") == "verification_replay"
            and "generated" in (kw.get("payload") or {})
        ]
        assert len(generated) == 1 and len(generated[0]) == 2
        names = [entry["agent_name"] for entry in generated[0]]
        assert names[0] != names[1]
        # Cleanup ran after each pass: the list is back to the seed,
        # proven by a third read of the fixture's own state.
        state = _fixture_state(origin)
        assert [item["name"] for item in state["agents"]] == [
            "Fixture Agent Alpha"
        ]
        # Currency pass -> active.
        agents_page = next(
            page for page in repository.pages
            if page.canonical_url == f"{origin}/agents"
        )
        for state_row in repository.states:
            if state_row.map_page_id == agents_page.id:
                state_row.state_id = draft.definition_json[
                    "success_assertion"
                ]["state_id"]
        counts = await activate_current_versions(repository, app_map)
        assert counts["activated"] == 1, counts
        assert draft.lifecycle_status == "active"
    finally:
        if controller is not None:
            await controller.close()
        server.shutdown()


@pytest.mark.asyncio
async def test_t_ts7_broken_outcome_fails_verification(monkeypatch):
    """The broken variant: the create appears to succeed, the item
    never reaches the list. Verification must fail on the outcome
    assertion -- the page looks unchanged, the skill does not
    promote, and the draft stays a draft with failed replay rows."""
    from markettwin_execution_orchestrator.harvest.task_verify import (
        verify_task_draft,
    )

    server, origin = _start_fixture()
    controller = None
    try:
        repository, app_map, draft, trace, controller = (
            await _compiled_create_draft(monkeypatch, origin)
        )
        _fixture_post(origin, "/__variant", {"variant": "broken"})
        outcome = await verify_task_draft(
            repository=repository,
            app_map=app_map,
            skill_version=draft,
            controller=controller,
            profile={"agent_model": "Fixture Model A"},
            trace=trace,
            network_policy="local_development",
            fixture_action_rules=_fixture_action_rules(),
        )
        assert outcome["status"] == "draft", outcome
        assert draft.lifecycle_status == "draft"
        assert repository.replays
        assert all(row.result == "failed" for row in repository.replays)
        assert any(
            "skill_assertion" in (row.failure_site or "")
            for row in repository.replays
        )
        state = _fixture_state(origin)
        assert [item["name"] for item in state["agents"]] == [
            "Fixture Agent Alpha"
        ]
    finally:
        if controller is not None:
            await controller.close()
        server.shutdown()


@pytest.mark.asyncio
async def test_t_ts8_removed_target_stays_unverified(monkeypatch):
    """The moved variant renames the submit control: the step's
    element no longer resolves, no binding heals it (the renamed
    control is a different element), and the version stays
    unverified in draft."""
    from markettwin_execution_orchestrator.harvest.task_verify import (
        verify_task_draft,
    )

    server, origin = _start_fixture()
    controller = None
    try:
        repository, app_map, draft, trace, controller = (
            await _compiled_create_draft(monkeypatch, origin)
        )
        _fixture_post(origin, "/__variant", {"variant": "moved"})
        outcome = await verify_task_draft(
            repository=repository,
            app_map=app_map,
            skill_version=draft,
            controller=controller,
            profile={"agent_model": "Fixture Model A"},
            trace=trace,
            network_policy="local_development",
            fixture_action_rules=_fixture_action_rules(),
        )
        assert outcome["status"] == "draft", outcome
        assert draft.lifecycle_status == "draft"
        assert repository.replays
        assert all(row.result == "failed" for row in repository.replays)
        assert any(
            row.failure_step is not None for row in repository.replays
        )
    finally:
        if controller is not None:
            await controller.close()
        server.shutdown()


@pytest.mark.asyncio
async def test_t_ts9_authenticated_prerequisite(monkeypatch):
    """An account task compiled from a handover trace carries the
    authenticated prerequisite: with the login skill + profile
    credentials it verifies -- established by installing the
    handover auth snapshot into each clean pass, never by agent
    credential fills (policy-blocked product-wide); with the
    credentials withheld it is refused before any browser opens
    (the version stays draft and no replay rows are written)."""
    from markettwin_execution_orchestrator.browser.contracts import (
        AllowedOrigin,
    )
    from markettwin_execution_orchestrator.browser.controller import (
        BrowserController,
    )
    from markettwin_execution_orchestrator.harvest.harvest_capture import (
        capture_state,
    )
    from markettwin_execution_orchestrator.harvest.harvest_inventory import (
        distil_elements,
        distil_forms,
        identity_for,
    )
    from markettwin_execution_orchestrator.harvest.task_compile import (
        compile_task_trace,
    )
    from markettwin_execution_orchestrator.harvest.task_verify import (
        verify_task_draft,
    )
    from markettwin_execution_orchestrator.workflow.case_execution import (
        perform_case_action,
    )
    from markettwin_execution_orchestrator.workflow.task_trace import (
        TaskTraceRecorder,
    )
    from markettwin_shared.feature_plan import (
        CaseAction,
        ExpectedAssertion,
        FeatureScope,
        SafeTestValue,
        SemanticTarget,
        TestCaseSpec,
    )

    server, origin = _start_fixture()
    controller = None
    try:
        parts = urllib.parse.urlsplit(origin)
        origin_obj = AllowedOrigin(
            scheme=parts.scheme, hostname=parts.hostname, port=parts.port
        )
        login_definition = {
            "steps": [
                {"action": "navigate", "url": f"{origin}/login"},
                {
                    "action": "fill",
                    "target": {"label": "Username"},
                    "test_value_key": "login_username",
                },
                {
                    "action": "fill",
                    "target": {"label": "Password"},
                    "test_value_key": "login_password",
                },
                {
                    "action": "click",
                    "target": {"role": "button", "name": "Sign in"},
                },
            ]
        }
        credentials = {
            "login_username": "fixture-user",
            "login_password": "fixture-pass",
        }
        # Prologue: a human signs in for real -- the test drives the
        # session's page directly, the same hands a login handover
        # gives the browser to -- and the resulting auth state is
        # captured as a handover snapshot. Agent fills never touch
        # credential fields (the fill policy blocks them on every
        # path in this product), so the snapshot is the only honest
        # establishment route; the account page's terminal identity
        # is captured from the signed-in page, exactly what a
        # handover trace holds.
        controller = BrowserController()
        execution_id, journey_id = uuid4(), uuid4()
        handle = await controller.create_session(
            execution_id=execution_id,
            journey_id=journey_id,
            allowed_origins=[origin_obj],
            network_policy="local_development",
            js_capture=True,
        )
        session = controller._sessions[handle.session_id]
        page = session.page
        await page.goto(f"{origin}/login")
        await page.fill("#username", credentials["login_username"])
        await page.fill("#password", credentials["login_password"])
        await page.get_by_role("button", name="Sign in").click()
        await page.wait_for_url(f"{origin}/account")
        capture = await capture_state(
            controller, handle,
            execution_id=execution_id, journey_id=journey_id,
        )
        account_state_id, _, _ = identity_for(
            capture.url, distil_elements(capture), distil_forms(capture)
        )
        from datetime import UTC, datetime, timedelta

        from markettwin_execution_orchestrator.browser.auth_session_broker import (
            AuthSessionSnapshot,
            HumanSessionScope,
        )

        auth_snapshot = AuthSessionSnapshot(
            scope=HumanSessionScope(
                run_id=uuid4(), target_id=uuid4(), origin=origin
            ),
            browser_storage_state=await session.context.storage_state(),
            session_storage={},
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        await controller.close_session(session_id=handle.session_id)

        spec = TestCaseSpec(
            case_id="view_account",
            feature_key="account_view",
            title="View the account page",
            kind="happy_path",
            estimated_seconds=120,
            steps=(
                CaseAction(
                    action="click",
                    target=SemanticTarget(role="link", name="Account"),
                ),
            ),
            expected=(
                ExpectedAssertion(
                    assertion_id="signed_in_banner",
                    oracle="visible_text",
                    target=SemanticTarget(text="Signed in as fixture-user"),
                    expected_value="Signed in as fixture-user",
                    origin="inferred",
                ),
            ),
        )
        recorder = TaskTraceRecorder(case=spec, start_url=f"{origin}/")
        recorder.record_step(
            action_type="navigate", case_action=None,
            locator_strategy=None, outcome="completed",
        )
        recorder.observe_url(f"{origin}/")
        recorder.record_step(
            action_type="click", case_action=spec.steps[0],
            locator_strategy="aria", outcome="completed",
        )
        recorder.observe_url(f"{origin}/account")
        recorder.record_assertion(
            assertion_id="signed_in_banner",
            oracle="visible_text",
            status="satisfied",
        )
        recorder.note_segment(
            kind="assisted_login", from_step=None, to_step=None
        )
        recorder.set_terminal(
            {
                "url": f"{origin}/account",
                "state_id": account_state_id,
                "element_signature": [],
            }
        )
        trace = recorder.payload(case_status="completed")
        assert trace["complete"] is True

        repository = _FakeVerifyRepository(origin)
        app_map = _verify_app_map(origin)
        outcome = await compile_task_trace(
            trace=trace, spec=spec, app_map=app_map,
            repository=repository, run_id=uuid4(), approved_values={},
        )
        assert outcome.status == "compiled", outcome.codes
        draft = outcome.version
        assert draft.definition_json["task"]["prerequisites"] == [
            {"kind": "authenticated"}
        ]

        # The fixture resolves the executed spec host-side, as the production
        # loader does through the runtime snapshot reference.
        trace = {**trace, "spec": spec.model_dump(mode="json")}
        # Withheld auth snapshot: refused pre-browser, stays draft.
        refused = await verify_task_draft(
            repository=repository,
            app_map=app_map,
            skill_version=draft,
            controller=controller,
            profile={},
            login_definition=login_definition,
            trace=trace,
            network_policy="local_development",
        )
        assert refused["status"] == "refused"
        assert refused["reason"] == "prerequisite_unavailable"
        assert repository.replays == []
        assert draft.lifecycle_status == "draft"

        # With the login skill + credentials: verifies.
        verified = await verify_task_draft(
            repository=repository,
            app_map=app_map,
            skill_version=draft,
            controller=controller,
            profile=credentials,
            login_definition=login_definition,
            trace=trace,
            network_policy="local_development",
            auth_snapshot=auth_snapshot,
        )
        assert verified["status"] == "replay_verified", verified
        assert draft.lifecycle_status == "replay_verified"
        assert len(repository.replays) == 2
        assert all(row.model_calls == 0 for row in repository.replays)
    finally:
        if controller is not None:
            await controller.close()
        server.shutdown()
