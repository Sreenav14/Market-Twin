"""Meta-generated plans must be useful inputs to the bounded sequential runtime."""

import json
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.agents.meta_agent import META_AGENT_MAX_TOKENS
from markettwin_execution_orchestrator.agents.schemas.plan import MetaAgentPlan
from markettwin_execution_orchestrator.workflow.planning import (
    MetaPlanningRequest,
    build_planning_prompt,
    validate_generated_plan,
)
from pydantic import ValidationError


def plan_data():
    return {
        "mission_summary": "Validate an account update through completion and recovery.",
        "personas": [
            {
                "persona_id": f"user_{number}", "name": f"User {number}",
                "perspective": f"Account user with familiarity level {number}",
                "behavior_traits": ["careful"], "priorities": ["accurate account data"],
            }
            for number in range(1, 4)
        ],
        "missions": [{
            "mission_id": "update_account", "name": "Update account address",
            "objective": "Open account, validate an empty address, correct it and verify outcome",
            "success_criteria": ["An empty address displays a required-field error."],
            "priority": "high",
        }],
    }


def test_planning_blueprint_carries_application_scope_and_end_to_end_requirements():
    prompt = build_planning_prompt(MetaPlanningRequest(
        test_run_id=uuid4(), study_brief="Validate account settings and address recovery",
        target_snapshot={"base_url": "https://example.invalid"}, testing_depth="high",
        knowledge_context=({"name": "Account guide", "content": "Address is required."},),
    ))
    context = json.loads(prompt[prompt.index("{"):])
    assert context["study_brief"] == "Validate account settings and address recovery"
    assert context["approved_knowledge"][0]["name"] == "Account guide"
    blueprint = context["planning_blueprint"]
    assert blueprint["execution"] == (
        "meta -> sequential journeys -> collector -> evaluation -> report"
    )
    assert "end-to-end" in blueprint["mission_design"]
    assert "coverage gaps" in blueprint["coverage"]
    assert META_AGENT_MAX_TOKENS >= 4096


@pytest.mark.parametrize("duplicate", ["persona_id", "mission_id", "objective"])
def test_ambiguous_or_duplicate_plan_assignments_are_rejected(duplicate):
    data = plan_data()
    if duplicate == "persona_id":
        data["personas"][1]["persona_id"] = data["personas"][0]["persona_id"]
    else:
        second = {**data["missions"][0], "mission_id": "other_task",
                  "name": "Other account task", "objective": "Review account details"}
        second[duplicate] = data["missions"][0][duplicate]
        data["missions"].append(second)
    with pytest.raises((ValidationError, ValueError)):
        validate_generated_plan(MetaAgentPlan.model_validate(data))


@pytest.mark.parametrize("criteria", [["   "], ["Address is required", " address is required "]])
def test_blank_or_duplicate_criteria_are_rejected(criteria):
    data = plan_data()
    data["missions"][0]["success_criteria"] = criteria
    with pytest.raises(ValidationError):
        MetaAgentPlan.model_validate(data)
