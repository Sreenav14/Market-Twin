"""Phase 1b replay verification (doc 16 section 5.8, tests T-RPL1 to
T-RPL5). Executors are fakes except T-RPL5, which drives the real
executor against a fake controller to pin the superset fallback.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from markettwin_execution_orchestrator.harvest import harvest_capture
from markettwin_execution_orchestrator.harvest.harvest_replay import (
    CaseExecutionReplayExecutor,
    ReplayAttempt,
    verify_skill,
)
from markettwin_execution_orchestrator.workflow import case_execution


def make_definition():
    return {
        "case_id": "get_a_demo_ab12cd34",
        "feature_key": "map_journey_ab12cd34",
        "title": "Journey: Get a demo",
        "kind": "happy_path",
        "steps": [
            {"action": "navigate", "url": "https://example.com/"},
            {
                "action": "click",
                "target": {"role": "link", "name": "Get a demo"},
            },
        ],
        "expected": [
            {
                "assertion_id": "terminal_url",
                "oracle": "url",
                "expected_value": "https://example.com/get-a-demo",
                "origin": "inferred",
            }
        ],
        "safety": "non_destructive",
        "estimated_seconds": 35,
        "locator_bindings": [
            {
                "order": 2,
                "page_url": "https://example.com/",
                "element": {"role": "link", "name": "Get a demo"},
                "locators": [
                    {"kind": "role_name", "value": "link|Get a demo", "stability": 1},
                    {"kind": "label", "value": "Book a demo", "stability": 2},
                    {"kind": "structural", "value": "div:nth-of-type(2)", "stability": 3},
                ],
                "action": "click",
                "value_source": "none",
            }
        ],
        "success_assertion": {
            "kind": "terminal_state",
            "url": "https://example.com/get-a-demo",
            "state_id": "terminal-state-id",
            "element_signature": ["link|Home"],
            "signature_superset_fallback": True,
        },
    }


class FakeRepository:
    def __init__(self):
        self.replays = []
        self.version_updates = []
        self.transitions = []
        self._versions = {}

    async def insert_replay(self, app_map, **kwargs):
        self.replays.append(kwargs)
        return SimpleNamespace(id=uuid4())

    async def update_skill_version(self, version_id, **fields):
        self.version_updates.append(fields)

    async def get_skill_version(self, version_id):
        # The transition authority reads the version back (doc 22
        # section 5.1); the fake's versions start in draft.
        return self._versions.setdefault(
            version_id,
            SimpleNamespace(id=version_id, lifecycle_status="draft"),
        )

    async def apply_skill_transition(self, version_id, *, fields, event):
        self.transitions.append({"fields": fields, "event": event})
        version = await self.get_skill_version(version_id)
        version.lifecycle_status = fields["lifecycle_status"]
        return version


class FakeExecutor:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.definitions_seen = []

    async def run_once(self, *, definition):
        self.definitions_seen.append(definition)
        return self._outcomes.pop(0)


def make_version():
    return SimpleNamespace(
        id=uuid4(), heal_count=0, replay_count=0, lifecycle_status="draft")


def make_map():
    return SimpleNamespace(id=uuid4(), base_url="https://example.com/")


PASS = ReplayAttempt(ok=True, final_state_id="terminal-state-id")
FAIL_STEP_1 = ReplayAttempt(
    ok=False, failure_step=1, failure_site="case_execution:ElementNotFound"
)


# T-RPL1: two clean passes verify the skill; both replays are
# recorded with zero model calls.
async def test_two_clean_passes_verify_the_skill():
    repository = FakeRepository()
    result = await verify_skill(
        repository=repository,
        app_map=make_map(),
        skill_version=make_version(),
        definition=make_definition(),
        executor=FakeExecutor([PASS, PASS]),
    )
    assert result.lifecycle_status == "replay_verified"
    assert result.heal is None
    assert result.attempts == 2
    assert len(repository.replays) == 2
    assert all(replay["model_calls"] == 0 for replay in repository.replays)
    assert all(replay["context_kind"] == "clean" for replay in repository.replays)
    final_update = repository.version_updates[-1]
    assert final_update["last_replay_result"] == "passed"
    assert final_update["verified_fingerprint"] == "terminal-state-id"
    # The lifecycle itself moves through the shared transition
    # authority (doc 22 section 5.1), not update_skill_version.
    transition = repository.transitions[-1]
    assert transition["fields"]["lifecycle_status"] == "replay_verified"
    assert transition["event"]["kind"] == "verification_replay"
    assert transition["event"]["from_status"] == "draft"


# T-RPL2: a failed step heals by walking its own bindings to the
# label locator; the healed definition then passes twice.
async def test_failure_heals_via_binding_walk_then_verifies():
    repository = FakeRepository()
    executor = FakeExecutor([FAIL_STEP_1, PASS, PASS])
    result = await verify_skill(
        repository=repository,
        app_map=make_map(),
        skill_version=make_version(),
        definition=make_definition(),
        executor=executor,
    )
    assert result.lifecycle_status == "replay_verified"
    assert result.heal is not None
    assert result.heal.step == 1
    assert result.heal.from_locator == {"role": "link", "name": "Get a demo"}
    assert result.heal.to_locator == {"label": "Book a demo"}
    healed_definition = executor.definitions_seen[1]
    assert healed_definition["steps"][1]["target"] == {"label": "Book a demo"}
    # The heal never touches the success assertion or the step set.
    assert healed_definition["success_assertion"] == make_definition()[
        "success_assertion"
    ]
    assert len(healed_definition["steps"]) == 2
    heal_updates = [
        update for update in repository.version_updates if "heal_count" in update
    ]
    assert heal_updates[0]["heal_count"] == 1


async def test_task_verification_can_refuse_healing_without_mutating_contract():
    repository = FakeRepository()
    executor = FakeExecutor([FAIL_STEP_1])
    result = await verify_skill(
        repository=repository, app_map=make_map(), skill_version=make_version(),
        definition=make_definition(), executor=executor, allow_heal=False,
        on_failure="leave_draft",
    )
    assert result.lifecycle_status == "draft"
    assert result.heal is None
    assert len(executor.definitions_seen) == 1
    assert executor.definitions_seen[0] == make_definition()


# T-RPL3: a failure after the heal quarantines the skill.
async def test_second_failure_quarantines():
    repository = FakeRepository()
    executor = FakeExecutor([FAIL_STEP_1, FAIL_STEP_1])
    result = await verify_skill(
        repository=repository,
        app_map=make_map(),
        skill_version=make_version(),
        definition=make_definition(),
        executor=executor,
    )
    assert result.lifecycle_status == "quarantined"
    assert result.heal is not None
    final_update = repository.version_updates[-1]
    assert final_update["last_replay_result"] == "failed"
    transition = repository.transitions[-1]
    assert transition["fields"]["lifecycle_status"] == "quarantined"
    assert transition["event"]["kind"] == "quarantine"


# T-RPL4: with nothing healable (the only alternative locator is the
# structural path, which the executor cannot express), the first
# failure quarantines without a second round.
async def test_unhealable_failure_quarantines_after_first_round():
    definition = make_definition()
    definition["locator_bindings"][0]["locators"] = [
        {"kind": "role_name", "value": "link|Get a demo", "stability": 1},
        {"kind": "structural", "value": "div:nth-of-type(2)", "stability": 2},
    ]
    repository = FakeRepository()
    executor = FakeExecutor([FAIL_STEP_1])
    result = await verify_skill(
        repository=repository,
        app_map=make_map(),
        skill_version=make_version(),
        definition=definition,
        executor=executor,
    )
    assert result.lifecycle_status == "quarantined"
    assert result.heal is None
    assert result.attempts == 1


# T-RPL5: the production executor accepts the terminal when the live
# element signature is a SUPERSET of the harvested one, and records
# that the fallback was used.
async def test_executor_superset_fallback(monkeypatch):
    async def fake_perform(controller, handle, action, scope, approval=None):
        return SimpleNamespace(action=action.action)

    monkeypatch.setattr(
        case_execution, "perform_case_action", fake_perform
    )

    async def fake_capture(controller, handle, *, execution_id, journey_id):
        return harvest_capture.StateCapture(
            url="https://example.com/get-a-demo",
            title="Demo",
            aria_snapshot="- link \"Home\"\n- link \"Extra\"",
            aria_entries=[
                {"role": "link", "name": "Home"},
                {"role": "link", "name": "Extra"},
            ],
            probe={},
            dom_elements=[],
            forms=[],
            dom_structure_hash="x",
            aria_hash="y",
            screenshot_path="",
        )

    monkeypatch.setattr(harvest_capture, "capture_state", fake_capture)

    class FakeController:
        def __init__(self):
            self.closed = False

        async def create_session(self, **kwargs):
            return SimpleNamespace(session_id=uuid4(), execution_id=kwargs["execution_id"],
                                   journey_id=kwargs["journey_id"])

        async def read_assertion(self, **kwargs):
            return None, SimpleNamespace(status="satisfied")

        async def close_session(self, *, session_id):
            self.closed = True

    controller = FakeController()
    executor = CaseExecutionReplayExecutor(controller, app_map=make_map())
    attempt = await executor.run_once(definition=make_definition())
    assert attempt.ok is True
    assert attempt.superset_used is True
    assert attempt.final_state_id is not None
    assert attempt.final_state_id != "terminal-state-id"
    assert controller.closed is True


# A-50: a heal mutates the definition; every persist of the mutated
# definition must carry a freshly computed contract digest, or the
# read-only matcher (which recomputes and compares) fails closed on
# the healed skill forever.
async def test_healed_task_skill_is_restamped_and_matchable():
    from markettwin_execution_orchestrator.workflow.skill_filter import (
        match_read_only_task_skill,
    )
    from markettwin_shared.feature_plan import TestCaseSpec
    from markettwin_shared.task_skill import task_contract_digest

    native = {
        "case_id": "open_agents", "feature_key": "agents",
        "title": "Open agents", "kind": "happy_path",
        "steps": [
            {"action": "wait", "milliseconds": 500},
            {"action": "navigate", "url": "https://example.com/agents"},
        ],
        "expected": [{
            "assertion_id": "agents_page", "oracle": "title",
            "expected_value": "Agents", "origin": "user_approved",
        }],
    }
    probe = TestCaseSpec.model_validate(native)
    definition = {
        **native,
        "task": {"cleanup": {"kind": "none_required"}},
        "safety": probe.safety,
        "success_assertion": {
            "url": "https://example.com/agents", "state_id": "observed-state",
        },
    }
    definition["task"]["contract_digest"] = task_contract_digest(definition)
    version = make_version()
    repository = FakeRepository()
    executor = FakeExecutor([
        ReplayAttempt(
            ok=False, failure_step=1,
            failure_site="case_execution:TimeoutError",
        ),
        PASS, PASS,
    ])
    result = await verify_skill(
        repository=repository, app_map=make_map(), skill_version=version,
        definition=definition, executor=executor,
    )
    assert result.lifecycle_status == "replay_verified"
    assert result.heal is not None
    stored = [
        update["definition_json"] for update in repository.version_updates
        if "definition_json" in update
    ]
    assert stored, "the mutated definition was never persisted"
    for persisted in stored:
        assert persisted["task"]["contract_digest"] == task_contract_digest(
            persisted
        )
    healed_definition = stored[-1]
    assert healed_definition["steps"][0]["milliseconds"] == 1000
    case = TestCaseSpec.model_validate({
        **native,
        "steps": [
            {"action": "wait", "milliseconds": 1000},
            {"action": "navigate", "url": "https://example.com/agents"},
        ],
    })
    entry = {
        "skill_id": str(uuid4()), "skill_version_id": str(version.id),
        "skill_kind": "task", "lifecycle_status": "active",
        "definition": healed_definition,
    }
    assert match_read_only_task_skill(
        {"skills": [entry]}, case, mode="read_only"
    ) == (version.id, entry)
