"""Pure scoring for the live frozen-contract fixture benchmark.

Reported confirmations are not seeded-defect recall until their exact assertion,
observed source action, original execution, and replay evidence all agree.
"""

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

from markettwin_shared.action_approval import SensitiveActionRule
from markettwin_shared.case_evidence import ArtifactEvidence, StepEvidence, valid_case_evidence
from markettwin_shared.contract_execution import contract_case
from markettwin_shared.deep_testing import CaseExecutionResult
from markettwin_shared.discovery_contract import DiscoveryMap, TestContract
from markettwin_shared.feature_plan import TestCaseSpec

DEFECTS = (
    "disabled_primary_button",
    "missing_validation",
    "incorrect_navigation",
    "missing_confirmation",
)
FIXTURE_ACTION_RULES = [
    {"category": "form_submit", "role": "button", "name": "Continue to next step",
     "resource_reference": "fixture-continue", "test_data_reset_confirmed": True},
    {"category": "form_submit", "role": "button", "name": "Check contact address",
     "resource_reference": "fixture-contact", "test_data_reset_confirmed": True},
    {"category": "save", "role": "button", "name": "Save display name",
     "resource_reference": "fixture-display", "test_data_reset_confirmed": True},
]
EXCLUDED_OPERATIONAL_RUNS = [
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
]
PROVENANCE_FIELDS = (
    "frozen_contract",
    "discovery_map",
    "execution_plan",
    "case_results",
    "replay_links",
    "execution_steps",
    "source_discovery_steps",
    "source_discovery_step_source_run_id",
    "discovery_event_counts",
    "artifacts",
)


def fraction(numerator: int, denominator: int) -> dict[str, int | float | None]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else None,
    }


def _normalized_fixture_rules(value: object) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    try:
        return [
            rule.model_dump(mode="json", exclude_none=True)
            for rule in (SensitiveActionRule.model_validate(item) for item in value)
        ]
    except (TypeError, ValueError):
        return None


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], event.get("payload", event))


def _defect(check, discovered, journey_steps) -> str | None:
    """Attribute only the check's own recorded source action and expected observation."""
    if discovered.action != "click":
        return None
    name = discovered.target_name or discovered.target_label or discovered.target_text
    expected = check.expected_value
    if name == "Continue to next step" and (
        (check.oracle == "enabled" and expected is True)
        or (check.oracle == "visible_text" and expected == "Next step")
    ):
        return "disabled_primary_button"
    if (
        name == "Check contact address"
        and check.oracle == "visible_text"
        and expected == ("Contact address is required")
    ):
        prior_inputs = [
            s
            for s in journey_steps
            if s.ordinal < discovered.ordinal
            and s.action == "fill"
            and (s.target_label or s.target_name) == "Contact address"
        ]
        if not prior_inputs or prior_inputs[-1].input_key == "empty":
            return "missing_validation"
    if name == "Open billing settings" and (
        check.oracle == "visible_text"
        and expected == "Billing settings"
        or check.oracle == "title"
        and expected == "Billing settings"
    ):
        return "incorrect_navigation"
    if (
        name == "Generate preview"
        and check.oracle == "visible_text"
        and expected == "Preview ready"
    ):
        return "missing_confirmation"
    return None


def _verified_defects(outcome: dict[str, Any]) -> tuple[list[str], list[str]]:
    contract = TestContract.model_validate(outcome["frozen_contract"])
    discovery = DiscoveryMap.model_validate(outcome["discovery_map"])
    report = outcome["report"]
    identity = {
        "contract_id": str(contract.contract_id),
        "contract_version": contract.version,
        "contract_hash": contract.content_hash(),
    }
    if (
        contract.status != "frozen"
        or contract.approved_at is None
        or contract.approved_by_user_id is None
        or str(contract.test_run_id) != outcome["run_id"]
        or any(report.get(k) != v for k, v in identity.items())
        or any(_payload(outcome["execution_plan"]).get(k) != v for k, v in identity.items())
    ):
        raise ValueError("Frozen contract and executed plan identity do not match.")
    approved = {j.journey_key: j for j in contract.journeys if not j.excluded}
    observed_journeys = {j.journey_key: j for j in discovery.journeys if j.completed}
    cases = {}
    for value in _payload(outcome["execution_plan"]).get("cases", []):
        case = TestCaseSpec.model_validate(value)
        if case.case_id in cases or case != contract_case(
            approved[case.case_id], discovery.target_origin
        ):
            raise ValueError("Executed plan differs from approved journey.")
        cases[case.case_id] = case
    steps = {
        int(s["id"]): SimpleNamespace(**{**s, "execution_id": UUID(s["execution_id"])})
        for s in outcome["execution_steps"]
    }
    source_steps = {
        int(s["id"]): SimpleNamespace(**{**s, "execution_id": UUID(s["execution_id"])})
        for s in outcome["source_discovery_steps"]
    }
    discovery_source_run_id = outcome.get("source_discovery_step_source_run_id")
    expected_source_step_ids = {
        step.execution_step_id for journey in discovery.journeys for step in journey.steps
    }
    if (
        discovery_source_run_id != outcome.get("discovery_map_source_run_id")
        or set(source_steps) != expected_source_step_ids
        or any(
            source_steps[step.execution_step_id].status != "completed"
            or source_steps[step.execution_step_id].action_type != step.action
            for journey in discovery.journeys for step in journey.steps
        )
    ):
        raise ValueError("Discovery source actions lack exact persisted source-run evidence.")
    artifacts = {
        UUID(a["id"]): SimpleNamespace(
            **{
                **a,
                "execution_id": UUID(a["execution_id"]),
                "metadata_json": a.get("metadata_json", {}),
            }
        )
        for a in outcome["artifacts"]
    }
    detected: set[str] = set()
    issues: list[str] = []
    for proof in report.get("confirmed", []):
        try:
            key, check_id = proof["journey_key"], proof["assertion_id"]
            journey = approved[key]
            check = next(
                a
                for a in journey.assertions
                if a.assertion_id == check_id and a.origin == "user_approved" and not a.excluded
            )
            observed_journey = observed_journeys[key]
            source = next(
                s for s in observed_journey.steps if s.ordinal == check.source_step_ordinal
            )
            saved_source = source_steps.get(source.execution_step_id)
            if (
                saved_source is None
                or saved_source.status != "completed"
                or saved_source.action_type != source.action
            ):
                raise ValueError("Discovery source action lacks persisted evidence.")
            if not 1 <= check.source_step_ordinal <= len(journey.steps):
                raise ValueError("Check has no recorded source action.")
            planned_action = journey.steps[check.source_step_ordinal - 1]
            if (
                planned_action.action != source.action
                or planned_action.target is None
                or (
                    planned_action.target.role,
                    planned_action.target.name,
                    planned_action.target.label,
                    planned_action.target.text,
                )
                != (source.target_role, source.target_name, source.target_label, source.target_text)
            ):
                # Role targets can retain a redundant observed label; compare the used strategy.
                if not (
                    planned_action.action == source.action
                    and planned_action.target is not None
                    and planned_action.target.role == source.target_role
                    and planned_action.target.name == source.target_name
                ):
                    raise ValueError("Source target differs from the frozen action.")
            if (
                proof.get("reason") != "reproduced"
                or proof.get("verification") != "verified_deterministic"
            ):
                raise ValueError("Finding has no confirmation verdict.")
            first_id, second_id = proof["execution_id"], proof["replay_execution_id"]
            if first_id == second_id:
                raise ValueError("Replay reused the original execution.")
            matching = []
            for execution_id, attempt in ((first_id, 1), (second_id, 2)):
                rows = [
                    e
                    for e in outcome["case_results"]
                    if str(e.get("execution_id")) == execution_id
                    and _payload(e).get("attempt") == attempt
                ]
                if len(rows) != 1 or any(
                    _payload(rows[0]).get(k) != v for k, v in identity.items()
                ):
                    raise ValueError("Execution does not reference the frozen contract.")
                result = CaseExecutionResult.model_validate(_payload(rows[0])["result"])
                if result.execution_id != UUID(execution_id) or not valid_case_evidence(
                    cases[key],
                    result,
                    cast(Mapping[int, StepEvidence], steps),
                    cast(Mapping[UUID, ArtifactEvidence], artifacts),
                ):
                    raise ValueError("Execution lacks valid exact step and screenshot evidence.")
                assertion = next(a for a in result.assertion_results if a.assertion_id == check_id)
                if assertion.status != "not_satisfied" or assertion.origin != "user_approved":
                    raise ValueError("The same approved check did not fail twice.")
                matching.append(rows[0])
            if (
                matching[0].get("journey_id") != matching[1].get("journey_id")
                or _payload(matching[0]).get("persona_index")
                != _payload(matching[1]).get("persona_index")
                or not any(
                    str(e.get("execution_id")) == second_id
                    and e.get("journey_id") == matching[0].get("journey_id")
                    and _payload(e).get("replay_of_execution_id") == first_id
                    and all(_payload(e).get(k) == v for k, v in identity.items())
                    for e in outcome["replay_links"]
                )
            ):
                raise ValueError("Original and replay are not an independent linked pair.")
            defect = _defect(check, source, observed_journey.steps)
            if defect:
                detected.add(defect)
        except (KeyError, ValueError, TypeError, StopIteration) as error:
            issues.append(f"{proof.get('assertion_id', 'unknown')}: {type(error).__name__}")
    return sorted(detected), issues


def score_run(outcome: dict[str, Any]) -> dict[str, Any]:
    report = outcome.get("report", {})
    rows = report.get("cases", [])
    unique_rows = {(r.get("journey_key"), r.get("persona_index")): r for r in rows}
    approved = report.get("coverage", {}).get("approved", 0)
    missing = [key for key in PROVENANCE_FIELDS if key not in outcome]
    issues = []
    detected = None
    if not missing:
        try:
            detected, issues = _verified_defects(outcome)
            contract = TestContract.model_validate(outcome["frozen_contract"])
            approved = sum(
                not j.excluded and any(not a.excluded for a in j.assertions)
                for j in contract.journeys
            )
        except (KeyError, ValueError, TypeError, StopIteration) as error:
            issues.append(type(error).__name__)
    completed = sum(
        r.get("execution_status") == "completed"
        and r.get("verdict") in {"satisfied", "not_satisfied"}
        for r in unique_rows.values()
    )
    executed = [r for r in unique_rows.values() if r.get("execution_id")]
    inconclusive = sum(
        r.get("execution_status") != "completed"
        or r.get("verdict") not in {"satisfied", "not_satisfied"}
        for r in executed
    )
    claims = {str(p.get("finding_id")) for p in report.get("confirmed", [])}
    return {
        "run_id": outcome.get("run_id"),
        "broken": outcome.get("broken"),
        "repeat": outcome.get("repeat"),
        "operational_run_number": outcome.get("operational_run_number"),
        "campaign_run_number": outcome.get("campaign_run_number"),
        "status": outcome.get("status"),
        "detected_defects": detected,
        "seeded_defect_recall": fraction(len(detected), 4) if detected is not None else None,
        "reported_confirmed_findings": len(claims),
        "good_false_confirmations": len(claims) if outcome.get("broken") is False else None,
        "journey_completion": fraction(completed, approved * 3),
        "inconclusive_share": fraction(inconclusive, len(executed)),
        "manual_interventions": outcome.get("manual_interventions"),
        "report_integrity_passed": (
            outcome.get("status") == "reported"
            and outcome.get("report_integrity_passed") is True
            and not issues
        ),
        "missing_provenance": missing,
        "provenance_errors": issues,
        "measurement_source": (
            "saved_provenance" if not missing and not issues else "report_only_unvalidated"
        ),
    }


def _same_contract_campaign(
    outcomes: list[dict[str, Any]], campaign: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not campaign or campaign.get("protocol") != "single_frozen_contract_replay_v1":
        return False, ["missing_or_invalid_campaign_protocol"]
    if (
        campaign.get("included_operational_run_numbers") != [1, 4, 5, 6, 7, 8]
        or campaign.get("excluded_operational_runs") != EXCLUDED_OPERATIONAL_RUNS
    ):
        errors.append("operational_run_classification_mismatch")
    source_id = str(campaign.get("source_run_id", ""))
    source_hash = campaign.get("source_contract_hash")
    source_runs = [row for row in outcomes if row.get("run_id") == source_id]
    if len(source_runs) != 1:
        return False, ["campaign_source_run_missing_or_duplicated"]
    try:
        expected_slots = {
            (1, 1, True, 1), (2, 4, True, 2), (3, 5, True, 3),
            (4, 6, False, 1), (5, 7, False, 2), (6, 8, False, 3),
        }
        if {
            (row.get("campaign_run_number"), row.get("operational_run_number"),
             row.get("broken"), row.get("repeat")) for row in outcomes
        } != expected_slots:
            errors.append("campaign_run_slot_mismatch")
        if (
            source_runs[0].get("campaign_run_number") != 1
            or source_runs[0].get("operational_run_number") != 1
            or source_runs[0].get("broken") is not True
            or source_runs[0].get("repeat") != 1
        ):
            errors.append("source_baseline_slot_mismatch")
        source_contract = TestContract.model_validate(source_runs[0]["frozen_contract"])
        source_map = DiscoveryMap.model_validate(source_runs[0]["discovery_map"])
        if (
            campaign.get("discovery_count") != 1
            or source_runs[0].get("discovery_event_counts") != {
                "discovery.started": 0, "discovery.completed": 1,
            }
            or campaign.get("source_contract_id") != str(source_contract.contract_id)
            or campaign.get("source_contract_version") != source_contract.version
            or source_hash != source_contract.content_hash()
            or campaign.get("reused_target_id") != source_runs[0].get("target_id")
            or campaign.get("automatic_opaque_action_approval") is not False
            or _normalized_fixture_rules(campaign.get("approved_fixture_action_rules"))
            != _normalized_fixture_rules(FIXTURE_ACTION_RULES)
        ):
            errors.append("campaign_source_metadata_mismatch")
        source_approval = (source_contract.approved_by_user_id, source_contract.approved_at)
        source_journeys = source_contract.journeys
        source_target_snapshot = source_runs[0].get("target_snapshot")
        source_policy = source_runs[0].get("fixture_action_policy")
        expected_fixture_rules = _normalized_fixture_rules(FIXTURE_ACTION_RULES)
        source_fixture_rules = _normalized_fixture_rules(
            source_policy.get("sensitive_action_rules") if isinstance(source_policy, dict)
            else None
        )
        if (
            not isinstance(source_policy, dict)
            or source_fixture_rules != expected_fixture_rules
            or campaign.get("source_fixture_action_policy") != source_policy
            or _normalized_fixture_rules(campaign.get("approved_fixture_action_rules"))
            != expected_fixture_rules
        ):
            errors.append("source_fixture_policy_not_recorded_exactly")
        for row in outcomes:
            contract = TestContract.model_validate(row["frozen_contract"])
            discovery = DiscoveryMap.model_validate(row["discovery_map"])
            if (
                contract.contract_id != source_contract.contract_id
                or contract.version != source_contract.version
                or contract.content_hash() != source_hash
                or (contract.approved_by_user_id, contract.approved_at) != source_approval
                or contract.journeys != source_journeys
                or discovery != source_map
                or row.get("target_id") != campaign.get("reused_target_id")
                or row.get("target_snapshot") != source_target_snapshot
                or row.get("campaign_source_run_id") != source_id
                or row.get("campaign_source_contract_hash") != source_hash
                or row.get("frozen_contract_source_run_id") != source_id
                or row.get("frozen_contract_source_hash") != source_hash
                or row.get("discovery_map_source_run_id") != source_id
                or row.get("source_discovery_step_source_run_id") != source_id
                or row.get("fixture_action_policy") != source_policy
                or row.get("discovery_event_counts") != (
                    {"discovery.started": 0, "discovery.completed": 1}
                    if row.get("run_id") == source_id
                    else {"discovery.started": 0, "discovery.completed": 0}
                )
                or {
                    (int(step["id"]), str(step["execution_id"]), step["step_number"],
                     step["action_type"], step["status"])
                    for step in row.get("source_discovery_steps", [])
                } != {
                    (int(step["id"]), str(step["execution_id"]), step["step_number"],
                     step["action_type"], step["status"])
                    for step in source_runs[0].get("source_discovery_steps", [])
                }
            ):
                errors.append(f"source_contract_or_discovery_mismatch:{row.get('run_id')}")
            if row is not source_runs[0] and (
                row.get("synthetic_fixture_approval_enabled")
                != source_runs[0].get("synthetic_fixture_approval_enabled")
                or row.get("human_action_approvals_enabled")
                != source_runs[0].get("human_action_approvals_enabled")
            ):
                errors.append(f"fixture_policy_flags_changed:{row.get('run_id')}")
        source_used_approval = source_runs[0].get("synthetic_fixture_approval_enabled") is True
        if campaign.get("source_used_synthetic_fixture_approval") is not source_used_approval:
            errors.append("source_approval_protocol_deviation_not_recorded")
        return not errors, errors
    except (KeyError, ValueError, TypeError) as error:
        return False, [f"invalid_campaign_provenance:{type(error).__name__}"]


def score_suite(
    outcomes: list[dict[str, Any]], campaign: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runs = [score_run(run) for run in outcomes]
    campaign_valid, campaign_errors = _same_contract_campaign(outcomes, campaign)
    broken = [r for r in runs if r["broken"] is True]
    good = [r for r in runs if r["broken"] is False]
    complete = (
        len(runs) == 6
        and len(broken) == len(good) == 3
        and [r["repeat"] for r in broken] == [1, 2, 3]
        and [r["repeat"] for r in good] == [1, 2, 3]
        and len({r["run_id"] for r in runs}) == 6
        and sorted(r["campaign_run_number"] for r in runs) == [1, 2, 3, 4, 5, 6]
        and sorted(r["operational_run_number"] for r in runs) == [1, 4, 5, 6, 7, 8]
        and all(r["status"] == "reported" and r["report_integrity_passed"] for r in runs)
        and campaign_valid
    )
    measured = all(not r["missing_provenance"] and not r["provenance_errors"] for r in runs)
    gates = {
        "six_consecutive_runs": complete,
        "single_frozen_contract_reused": campaign_valid,
        "provenance_available": bool(runs) and measured,
        "broken_recall_at_least_three_of_four": len(broken) == 3
        and all(
            r["detected_defects"] is not None and len(r["detected_defects"]) >= 3 for r in broken
        ),
        "navigation_confirmed_in_two_runs": sum(
            "incorrect_navigation" in (r["detected_defects"] or []) for r in broken
        )
        >= 2,
        "zero_good_false_confirmations": len(good) == 3
        and all(
            r["status"] == "reported"
            and r["report_integrity_passed"]
            and r["good_false_confirmations"] == 0
            for r in good
        ),
        "journey_completion_at_least_80_percent": bool(runs)
        and all(
            r["journey_completion"]["rate"] is not None and r["journey_completion"]["rate"] >= 0.8
            for r in runs
        ),
        "inconclusive_at_most_20_percent": bool(runs)
        and all(
            r["inconclusive_share"]["rate"] is not None and r["inconclusive_share"]["rate"] <= 0.2
            for r in runs
        ),
        "zero_manual_interventions": bool(runs)
        and all(r["manual_interventions"] == 0 for r in runs),
        "report_integrity": bool(runs) and all(r["report_integrity_passed"] for r in runs),
    }
    return {
        "status": "passed" if all(gates.values()) else "not_passing",
        "gates": gates,
        "runs": runs,
        "completion_denominator": (
            "approved frozen journeys × three original persona executions; replays excluded"
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    data = json.loads(args.artifact.read_text(encoding="utf-8"))
    print(json.dumps(score_suite(data["runs"], data.get("campaign")), indent=2))
