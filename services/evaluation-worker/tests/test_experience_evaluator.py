"""Tests for experience fact extraction and structural separation from findings."""

import pytest
from markettwin_evaluation_worker import experience_evaluator
from markettwin_evaluation_worker.experience_evaluator import (
    PersonaExperienceFacts,
    extract_persona_facts,
    score_persona_experience,
    validate_justification_cites_facts,
)


def test_experience_evaluator_has_no_findings_write_path():
    """Verify structural separation (§4.5.4): experience cannot create findings."""
    module_dict = experience_evaluator.__dict__
    assert "create_linked_finding" not in module_dict
    assert "EvaluationRepository" not in module_dict
    assert "Finding" not in module_dict


def test_extract_persona_facts_counts_accurately():
    records = [
        {
            "status": "completed",
            "duration_seconds": 15.2,
            "steps": [
                {"step_number": 1, "action_type": "navigate", "status": "completed"},
                {"step_number": 2, "action_type": "click", "status": "completed"},
            ],
        },
        {
            "status": "timed_out",
            "duration_seconds": 90.0,
            "steps": [
                {"step_number": 1, "action_type": "scroll", "status": "completed"},
                {"step_number": 2, "action_type": "scroll", "status": "completed"},
                {"step_number": 3, "action_type": "scroll", "status": "completed"},
                {"step_number": 4, "action_type": "click", "status": "failed"},
            ],
        },
    ]

    facts = extract_persona_facts(
        persona_key="shopper",
        persona_name="Shopper",
        journey_records=records,
    )

    assert facts.persona_key == "shopper"
    assert facts.journeys_attempted == 2
    assert facts.journeys_completed == 1
    assert facts.timeouts == 1
    assert facts.failed_actions == 1
    assert facts.total_steps == 6
    assert any("Repeated observation" in sp for sp in facts.stuck_points)
    assert any("failed" in sp for sp in facts.stuck_points)


def test_validate_justification_cites_facts():
    facts = PersonaExperienceFacts(
        persona_key="expert",
        persona_name="Expert",
        journeys_attempted=3,
        journeys_completed=2,
        total_steps=12,
        failed_actions=1,
        blocked_steps=0,
        timeouts=1,
        stuck_points=["Step 4 failed"],
        elapsed_seconds=45.0,
    )

    # Valid: cites step failures and timeouts
    assert validate_justification_cites_facts(
        "Completed 2 of 3 journeys with 1 timeout at step 4.", facts
    ) is True

    # Invalid: generic vague text without facts
    assert validate_justification_cites_facts(
        "I felt happy using this product overall.", facts
    ) is False


@pytest.mark.asyncio
async def test_score_persona_experience_handles_unavailable(monkeypatch):
    facts = PersonaExperienceFacts(
        persona_key="novice",
        persona_name="Novice",
        journeys_attempted=0,
        journeys_completed=0,
        total_steps=0,
        failed_actions=0,
        blocked_steps=0,
        timeouts=0,
        stuck_points=[],
        elapsed_seconds=0.0,
    )
    res = await score_persona_experience(facts)
    assert res.status == "unavailable"
    assert "No journeys attempted" in res.reason


@pytest.mark.parametrize("justification", [
    "It was easy to use.",
    "It was easy [persona_name=Expert].",
    "It was easy [total_steps=3]. Another sentence.",
])
def test_rubric_rejects_uncited_or_nonfact_or_multisentence_justification(justification):
    from markettwin_evaluation_worker.experience_evaluator import ExperienceScores, RubricScore

    scores = ExperienceScores(
        ease=RubricScore(score=4, justification=justification),
        clarity=RubricScore(score=4, justification="Three steps completed [total_steps=3]."),
        trust=RubricScore(score=4, justification="No failed actions [failed_actions=0]."),
    )
    with pytest.raises(ValueError):
        experience_evaluator.validate_citations(
            scores, {"total_steps": 3, "failed_actions": 0, "persona_name": "Expert"},
            has_images=False,
        )


def test_visual_score_never_exists_without_loaded_screenshot_input():
    from markettwin_evaluation_worker.experience_evaluator import ExperienceScores, RubricScore

    score = RubricScore(score=4, justification="Three steps completed [total_steps=3].")
    with pytest.raises(ValueError, match="screenshot"):
        experience_evaluator.validate_citations(
            ExperienceScores(ease=score, clarity=score, trust=score, visual_quality=score),
            {"total_steps": 3}, has_images=False,
        )
