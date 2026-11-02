"""Seeded recall needs exact failed-check provenance, not journey-wide attribution."""

import copy
import json
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from markettwin_shared.contract_execution import contract_case
from markettwin_shared.deep_testing import AssertionResult, CaseExecutionResult
from markettwin_shared.discovery_contract import (
    ContractAssertion,
    DiscoveredFeature,
    DiscoveredJourney,
    DiscoveredStep,
    DiscoveryMap,
    FrozenJourneyContract,
    TestContract,
)
from markettwin_shared.feature_plan import CaseAction, SemanticTarget


def scorer():
    path = Path(__file__).parents[1] / "scripts/contract_benchmark_scoring.py"
    spec = spec_from_file_location("contract_scoring", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replay_harness():
    path = Path(__file__).parents[1] / "scripts/run_contract_fixture_benchmark.py"
    spec = spec_from_file_location("contract_fixture_replay_harness", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_fixture_policy_normalizes_optional_rule_scope_fields():
    harness = replay_harness()
    raw = [{
        "category": category,
        "role": role,
        "name": name,
        "resource_reference": resource,
        "test_data_reset_confirmed": True,
        "scope_role": None,
        "scope_name": None,
    } for category, role, name, resource in harness.FIXTURE_ACTION_RULES]

    assert harness.normalized_fixture_rules(raw) == [{
        key: value for key, value in rule.items() if value is not None
    } for rule in raw]
    assert all("scope_role" in rule and "scope_name" in rule for rule in raw)


def outcome(*, broken=True, all_checks=False):
    controls = (
        "Continue to next step",
        "Check contact address",
        "Open billing settings",
        "Generate preview",
    )
    steps = tuple(
        DiscoveredStep(
            ordinal=i,
            action="click",
            target_role="link" if i == 3 else "button",
            target_name=name,
            execution_step_id=1000 + i,
            name_source="playwright",
        )
        for i, name in enumerate(controls, start=1)
    )
    discovered = DiscoveredJourney(
        journey_key="all_controls",
        feature_key="fixture",
        title="Use fixture",
        completed=True,
        steps=steps,
    )
    discovery = DiscoveryMap(
        target_origin="https://fixture.test",
        journeys=(discovered,),
        features=(
            DiscoveredFeature(
                feature_key="fixture",
                title="Fixture",
                entry_url_path="/",
                journey_keys=("all_controls",),
            ),
        ),
    )
    checks = (
        ContractAssertion(
            assertion_id="primary",
            oracle="enabled",
            target_role="button",
            target_name=controls[0],
            expected_value=True,
            plain_language="Primary action is enabled.",
            source_step_ordinal=1,
            origin="user_approved",
        ),
        ContractAssertion(
            assertion_id="validation",
            oracle="visible_text",
            expected_value="Contact address is required",
            plain_language="Validation.",
            source_step_ordinal=2,
            origin="user_approved",
        ),
        ContractAssertion(
            assertion_id="navigation",
            oracle="visible_text",
            expected_value="Billing settings",
            plain_language="Billing destination.",
            source_step_ordinal=3,
            origin="user_approved",
        ),
        ContractAssertion(
            assertion_id="preview",
            oracle="visible_text",
            expected_value="Preview ready",
            plain_language="Preview ready.",
            source_step_ordinal=4,
            origin="user_approved",
        ),
    )
    journey = FrozenJourneyContract(
        journey_key=discovered.journey_key,
        feature_key="fixture",
        title="Use fixture",
        steps=tuple(
            CaseAction(
                action="click",
                target=SemanticTarget(
                    role=s.target_role,
                    name=s.target_name,
                ),
            )
            for s in steps
        ),
        assertions=checks if all_checks else (checks[-1],),
    )
    contract = TestContract(
        contract_id=uuid4(),
        test_run_id=uuid4(),
        status="frozen",
        approved_at=datetime.now(UTC),
        approved_by_user_id=uuid4(),
        journeys=(journey,),
    )
    case = contract_case(journey, discovery.target_origin)
    identity = {
        "contract_id": str(contract.contract_id),
        "contract_version": 1,
        "contract_hash": contract.content_hash(),
    }
    result = {
        "run_id": str(contract.test_run_id),
        "broken": broken,
        "repeat": 1,
        "status": "reported",
        "frozen_contract": contract.model_dump(mode="json"),
        "discovery_map": discovery.model_dump(mode="json"),
        "execution_plan": {**identity, "cases": [case.model_dump(mode="json")]},
        "case_results": [],
        "replay_links": [],
        "artifacts": [],
        "execution_steps": [
            {
                "id": s.execution_step_id,
                "execution_id": str(uuid4()),
                "status": "completed",
                "action_type": "click",
                "step_number": s.ordinal,
                "observation_summary": None,
            }
            for s in steps
        ],
        "source_discovery_steps": [],
        "source_discovery_step_source_run_id": None,
        "discovery_map_source_run_id": None,
        "discovery_event_counts": {"discovery.started": 0, "discovery.completed": 1},
        "manual_interventions": 0,
        "report_integrity_passed": True,
        "report": {**identity, "coverage": {"approved": 1}, "cases": [], "confirmed": []},
    }
    result["source_discovery_steps"] = [dict(s) for s in result["execution_steps"]]
    result["source_discovery_step_source_run_id"] = str(contract.test_run_id)
    result["discovery_map_source_run_id"] = str(contract.test_run_id)
    for persona in range(3):
        journey_id, original = str(uuid4()), None
        for attempt in (1, 2) if broken else (1,):
            execution_id = uuid4()
            saved_steps, action_ids, assertions = [], [], []
            for checkpoint in range(len(case.steps) + 1):
                step_id = len(result["execution_steps"]) + len(saved_steps) + 1
                action_ids.append(step_id)
                saved_steps.append(
                    {
                        "id": step_id,
                        "execution_id": str(execution_id),
                        "step_number": len(saved_steps) + 1,
                        "status": "completed",
                        "action_type": "navigate" if checkpoint == 0 else "click",
                        "observation_summary": None,
                    }
                )
                for expected in case.expected:
                    if expected.after_step_ordinal != checkpoint:
                        continue
                    artifact_id = uuid4()
                    step_id = len(result["execution_steps"]) + len(saved_steps) + 1
                    observed = (
                        (False if expected.oracle == "enabled" else "absent")
                        if broken
                        else (expected.expected_value)
                    )
                    assertion = AssertionResult(
                        case_id=case.case_id,
                        assertion_id=expected.assertion_id,
                        oracle=expected.oracle,
                        expected_value=expected.expected_value,
                        observed_value=observed,
                        status="not_satisfied" if broken else "satisfied",
                        origin="user_approved",
                        execution_id=execution_id,
                        step_id=step_id,
                        artifact_ids=(artifact_id,),
                        elapsed_ms=1,
                    )
                    assertions.append(assertion)
                    saved_steps.append(
                        {
                            "id": step_id,
                            "execution_id": str(execution_id),
                            "step_number": len(saved_steps) + 1,
                            "status": "completed",
                            "action_type": "assertion",
                            "observation_summary": json.dumps(
                                assertion.model_dump(mode="json"),
                            ),
                        }
                    )
                    result["artifacts"].append(
                        {
                            "id": str(artifact_id),
                            "execution_id": str(execution_id),
                            "step_id": step_id,
                            "artifact_type": "screenshot",
                        }
                    )
            result["execution_steps"].extend(saved_steps)
            executed = CaseExecutionResult(
                case_id=case.case_id,
                execution_id=execution_id,
                execution_status="completed",
                verdict="not_satisfied" if broken else "satisfied",
                action_step_ids=tuple(action_ids),
                assertion_results=tuple(assertions),
                elapsed_ms=1,
            )
            event = {
                **identity,
                "execution_id": str(execution_id),
                "journey_id": journey_id,
                "attempt": attempt,
                "persona_index": persona,
                "result": executed.model_dump(mode="json"),
            }
            result["case_results"].append(event)
            if attempt == 1:
                original = event
                result["report"]["cases"].append(
                    {
                        "journey_key": case.case_id,
                        "persona_index": persona,
                        "execution_id": str(execution_id),
                        "execution_status": "completed",
                        "verdict": executed.verdict,
                    }
                )
            else:
                result["replay_links"].append(
                    {
                        **identity,
                        "execution_id": str(execution_id),
                        "journey_id": journey_id,
                        "replay_of_execution_id": original["execution_id"],
                    }
                )
                for assertion in assertions:
                    result["report"]["confirmed"].append(
                        {
                            "finding_id": assertion.assertion_id,
                            "journey_key": case.case_id,
                            "assertion_id": assertion.assertion_id,
                            "execution_id": original["execution_id"],
                            "replay_execution_id": str(execution_id),
                            "verification": "verified_deterministic",
                            "reason": "reproduced",
                        }
                    )
    return result


def controlled_campaign():
    data = []
    for campaign_number, operational_number, broken, repeat in (
        (1, 1, True, 1), (2, 4, True, 2), (3, 5, True, 3),
        (4, 6, False, 1), (5, 7, False, 2), (6, 8, False, 3),
    ):
        row = outcome(broken=broken, all_checks=True)
        row["repeat"] = repeat
        row["campaign_run_number"] = campaign_number
        row["operational_run_number"] = operational_number
        data.append(row)
    source = TestContract.model_validate(data[0]["frozen_contract"])
    source_id = data[0]["run_id"]
    source_hash = source.content_hash()
    target_id = str(uuid4())
    target_snapshot = {"target_id": target_id, "base_url": "http://fixture.test/"}
    fixture_rules = [
        {"category": "form_submit", "role": "button", "name": "Continue to next step",
         "resource_reference": "fixture-continue", "test_data_reset_confirmed": True},
        {"category": "form_submit", "role": "button", "name": "Check contact address",
         "resource_reference": "fixture-contact", "test_data_reset_confirmed": True},
        {"category": "save", "role": "button", "name": "Save display name",
         "resource_reference": "fixture-display", "test_data_reset_confirmed": True},
    ]
    policy = {
        "synthetic_fixture_approval": True,
        "human_action_approvals": True,
        "sensitive_action_rules": fixture_rules,
    }
    for row in data:
        contract = TestContract.model_validate(row["frozen_contract"]).model_copy(update={
            "contract_id": source.contract_id,
            "approved_by_user_id": source.approved_by_user_id,
            "approved_at": source.approved_at,
        })
        row["frozen_contract"] = contract.model_dump(mode="json")
        identity = {
            "contract_id": str(contract.contract_id),
            "contract_version": contract.version,
            "contract_hash": contract.content_hash(),
        }
        for value in (row["execution_plan"], *row["case_results"], *row["replay_links"]):
            value.update(identity)
        row["report"].update(identity)
        row.update({
            "campaign_source_run_id": source_id,
            "campaign_source_contract_hash": source_hash,
            "frozen_contract_source_run_id": source_id,
            "frozen_contract_source_hash": source_hash,
            "target_id": target_id,
            "target_snapshot": target_snapshot,
            "synthetic_fixture_approval_enabled": True,
            "human_action_approvals_enabled": True,
            "fixture_action_policy": policy,
            "source_discovery_step_source_run_id": source_id,
            "discovery_map_source_run_id": source_id,
            "source_discovery_steps": copy.deepcopy(data[0]["source_discovery_steps"]),
            "discovery_event_counts": {
                "discovery.started": 0,
                "discovery.completed": 1 if row["run_id"] == source_id else 0,
            },
        })
    return data, {
        "protocol": "single_frozen_contract_replay_v1",
        "source_run_id": source_id,
        "source_contract_id": str(source.contract_id),
        "source_contract_version": source.version,
        "source_contract_hash": source_hash,
        "discovery_count": 1,
        "reused_target_id": target_id,
        "automatic_opaque_action_approval": False,
        "included_operational_run_numbers": [1, 4, 5, 6, 7, 8],
        "excluded_operational_runs": [
            {
                "operational_run_number": 2,
                "run_id": "44674ee0-9e8f-4af3-bbf9-cdffeb35120e",
                "classification": "discovery_reliability_protocol_deviation",
                "counts_as_replay": False,
            },
            {
                "operational_run_number": 3,
                "run_id": "5e39c03e-8a6d-4d9a-aa9b-012f7e82e74e",
                "classification": "interrupted_before_report",
                "counts_as_replay": False,
            },
        ],
        "source_fixture_action_policy": policy,
        "approved_fixture_action_rules": fixture_rules,
        "source_used_synthetic_fixture_approval": True,
    }


def test_one_failed_preview_check_does_not_confirm_other_controls_in_same_journey():
    scored = scorer().score_run(outcome())
    assert scored["provenance_errors"] == []
    assert scored["detected_defects"] == ["missing_confirmation"]
    assert scored["seeded_defect_recall"]["numerator"] == 1
    assert scored["journey_completion"] == {"numerator": 3, "denominator": 3, "rate": 1.0}


def test_replay_pass_or_foreign_artifact_never_confirms_a_seeded_defect():
    data = outcome()
    for artifact in data["artifacts"]:
        artifact["execution_id"] = str(uuid4())
    scored = scorer().score_run(data)
    assert scored["detected_defects"] == []
    assert scored["provenance_errors"]


def test_six_controlled_runs_pass_only_when_each_broken_run_has_independent_three_of_four():
    data, campaign = controlled_campaign()
    assert scorer().score_suite(data, campaign)["status"] == "passed"
    without_navigation = copy.deepcopy(data)
    for row in without_navigation:
        row["report"]["confirmed"] = [
            p for p in row["report"]["confirmed"] if p["assertion_id"] != "navigation"
        ]
    score = scorer().score_suite(without_navigation, campaign)
    assert score["gates"]["broken_recall_at_least_three_of_four"]
    assert not score["gates"]["navigation_confirmed_in_two_runs"]
    assert score["status"] == "not_passing"


def test_missing_runs_or_missing_provenance_never_pass_and_never_fabricate_recall():
    data = outcome()
    del data["frozen_contract"]
    scored = scorer().score_run(data)
    assert scored["detected_defects"] is None
    assert scored["seeded_defect_recall"] is None
    assert scorer().score_suite([data])["status"] == "not_passing"


def test_duplicate_extra_run_cannot_satisfy_six_run_acceptance():
    data, campaign = controlled_campaign()
    duplicate = copy.deepcopy(data[0])
    duplicate["repeat"] = 4
    data.append(duplicate)

    scored = scorer().score_suite(data, campaign)

    assert not scored["gates"]["six_consecutive_runs"]
    assert scored["status"] == "not_passing"


def test_unreported_good_run_cannot_pass_six_run_or_false_confirmation_gate():
    data, campaign = controlled_campaign()
    data[-1]["status"] = "executing"

    scored = scorer().score_suite(data, campaign)

    assert not scored["gates"]["six_consecutive_runs"]
    assert not scored["gates"]["zero_good_false_confirmations"]
    assert not scored["gates"]["report_integrity"]


def test_integrity_failed_report_cannot_pass_six_run_or_false_confirmation_gate():
    data, campaign = controlled_campaign()
    data[-1]["report_integrity_passed"] = False

    scored = scorer().score_suite(data, campaign)

    assert not scored["gates"]["six_consecutive_runs"]
    assert not scored["gates"]["zero_good_false_confirmations"]
    assert not scored["gates"]["report_integrity"]


def test_campaign_rejects_rehashed_contract_or_discovery_drift():
    data, campaign = controlled_campaign()
    changed = copy.deepcopy(data)
    changed[4]["discovery_map"]["coverage_notes"] = ["Changed after approval."]

    scored = scorer().score_suite(changed, campaign)

    assert not scored["gates"]["single_frozen_contract_reused"]
    assert scored["status"] == "not_passing"


def test_campaign_normalizes_optional_fixture_rule_scope_fields():
    data, campaign = controlled_campaign()
    rules_with_optional_defaults = [
        {**rule, "scope_role": None, "scope_name": None}
        for rule in campaign["approved_fixture_action_rules"]
    ]
    campaign["approved_fixture_action_rules"] = rules_with_optional_defaults
    campaign["source_fixture_action_policy"]["sensitive_action_rules"] = (
        rules_with_optional_defaults
    )
    for row in data:
        row["fixture_action_policy"]["sensitive_action_rules"] = (
            rules_with_optional_defaults
        )

    valid, errors = scorer()._same_contract_campaign(data, campaign)
    assert valid, errors


def test_campaign_requires_source_discovery_steps_separate_from_replay_evidence():
    data, campaign = controlled_campaign()
    del data[1]["source_discovery_steps"][0]

    scored = scorer().score_suite(data, campaign)

    assert not scored["gates"]["single_frozen_contract_reused"]
    assert not scored["gates"]["provenance_available"]
    assert scored["status"] == "not_passing"


def test_replay_campaign_rejects_any_new_discovery_event():
    data, campaign = controlled_campaign()
    data[1]["discovery_event_counts"]["discovery.completed"] = 1

    scored = scorer().score_suite(data, campaign)

    assert not scored["gates"]["single_frozen_contract_reused"]
    assert scored["status"] == "not_passing"


async def test_replay_harness_stops_on_persisted_policy_blocked_action():
    harness = replay_harness()
    blocked_step = SimpleNamespace(
        id=91, step_number=4, action_summary="Submit an opaque confirmation",
        observation_summary="An opaque confirmation requires human browser takeover.",
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def get(self, *_):
            return SimpleNamespace(
                status="running", configuration_snapshot={"discovery_stage": "executing"},
            )

        async def scalars(self, *_):
            return SimpleNamespace(first=lambda: blocked_step)

    class FakeFactory:
        def __call__(self):
            return FakeSession()

    with pytest.raises(harness.OpaqueActionApprovalRequired) as error:
        await harness.wait_for(
            FakeFactory(), uuid4(), "report", [], deadline_seconds=1,
        )

    assert error.value.approvals == [{
        "kind": "policy_blocked_action",
        "step_id": 91,
        "step_number": 4,
        "action_summary": "Submit an opaque confirmation",
        "reason": "An opaque confirmation requires human browser takeover.",
    }]


async def test_replay_harness_waits_for_all_preflight_checks_before_start():
    harness = replay_harness()
    responses = iter((
        SimpleNamespace(
            status_code=200,
            json=lambda: {"ready": False, "checks": [{"name": "execution", "ready": False}]},
            text="",
        ),
        SimpleNamespace(
            status_code=200,
            json=lambda: {"ready": True, "checks": [{"name": "execution", "ready": True}]},
            text="",
        ),
    ))

    class FakeClient:
        paths = []

        async def get(self, path):
            self.paths.append(path)
            return next(responses)

    client = FakeClient()
    run_id = uuid4()

    result = await harness.wait_for_run_preflight(
        client, run_id, timeout_seconds=1, poll_interval_seconds=0,
    )

    assert result["ready"] is True
    assert client.paths == [
        f"/api/v1/test-runs/{run_id}/preflight",
        f"/api/v1/test-runs/{run_id}/preflight",
    ]


async def test_replay_harness_preserves_preflight_failure_response():
    harness = replay_harness()
    failure = {"detail": {"code": "run_preflight_failed", "checks": []}}

    class FakeClient:
        async def get(self, _path):
            return SimpleNamespace(status_code=503, json=lambda: failure, text="")

    with pytest.raises(harness.RunPreflightFailed) as error:
        await harness.wait_for_run_preflight(FakeClient(), uuid4())

    assert error.value.status_code == 503
    assert error.value.payload == failure


async def test_replay_harness_approves_only_an_exact_declared_fixture_action():
    harness = replay_harness()

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [{
                "id": "approval-1", "status": "pending", "environment": "local",
                "action_summary": (
                    "Submit a form on the authorized target "
                    "(127.0.0.1; fixture-continue)"
                ),
            }]

    class FakeClient:
        posted = []

        async def get(self, *_):
            return FakeResponse()

        async def post(self, path, *, json):
            self.posted.append((path, json))
            return FakeResponse()

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def get(self, *_):
            return SimpleNamespace(
                status="completed", configuration_snapshot={"discovery_stage": "report"},
            )

        async def scalars(self, *_):
            return SimpleNamespace(first=lambda: None)

        async def scalar(self, *_):
            return None

    class FakeFactory:
        def __call__(self):
            return FakeSession()

    client = FakeClient()
    await harness.wait_for(
        FakeFactory(), uuid4(), "report", [], deadline_seconds=1,
        approval_client=client, approved_action_host="127.0.0.1",
    )

    assert client.posted == [
        ("/api/v1/action-approvals/approval-1/decision", {"approved": True}),
    ]


async def test_replay_harness_stops_without_deciding_an_undeclared_approval():
    harness = replay_harness()

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [{
                "id": "approval-2", "status": "pending", "environment": "local",
                "action_summary": (
                    "Save a change on the authorized target "
                    "(127.0.0.1; registration-fixture)"
                ),
            }]

    class FakeClient:
        async def get(self, *_):
            return FakeResponse()

        async def post(self, *_args, **_kwargs):
            pytest.fail("Undeclared approval must never be decided.")

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def get(self, *_):
            return SimpleNamespace(
                status="completed", configuration_snapshot={"discovery_stage": "report"},
            )

        async def scalars(self, *_):
            return SimpleNamespace(first=lambda: None)

        async def scalar(self, *_):
            return None

    class FakeFactory:
        def __call__(self):
            return FakeSession()

    with pytest.raises(harness.OpaqueActionApprovalRequired) as error:
        await harness.wait_for(
            FakeFactory(), uuid4(), "report", [], deadline_seconds=1,
            approval_client=FakeClient(), approved_action_host="127.0.0.1",
        )
    assert error.value.approvals[0]["kind"] == "undeclared_or_opaque_approval"


async def test_replay_harness_stops_on_pending_human_browser_takeover():
    harness = replay_harness()
    takeover = SimpleNamespace(
        id=uuid4(), request_type="other", requested_by_step_id=92,
        instructions="Prepare the page; do not perform the pending action.",
    )
    step = SimpleNamespace(action_summary="Click the unresolved confirmation")

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def scalars(self, *_):
            return SimpleNamespace(first=lambda: None)

        async def scalar(self, *_):
            return takeover

        async def get(self, *_):
            return step

    class FakeFactory:
        def __call__(self):
            return FakeSession()

    with pytest.raises(harness.OpaqueActionApprovalRequired) as error:
        await harness.wait_for(
            FakeFactory(), uuid4(), "report", [], deadline_seconds=1,
        )

    assert error.value.approvals == [{
        "kind": "human_browser_takeover",
        "request_id": str(takeover.id),
        "request_type": "other",
        "action_summary": "Click the unresolved confirmation",
        "instructions": "Prepare the page; do not perform the pending action.",
    }]
