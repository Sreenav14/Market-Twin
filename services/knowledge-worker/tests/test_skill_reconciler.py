"""Incremental Skill reconciliation is bounded and non-destructive."""

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from litellm.types.utils import ModelResponse  # pyright: ignore[reportMissingTypeStubs]
from markettwin_knowledge_worker import skill_reconciler
from markettwin_knowledge_worker.skill_reconciler import (
    ExistingApprovedSkill,
    SkillReconciler,
    SkillReconciliationDecision,
)
from markettwin_shared.knowledge import GeneratedSkillDraft, SkillDefinition


def _draft(name: str, ordinal: int) -> GeneratedSkillDraft:
    return GeneratedSkillDraft(
        name=name,
        definition=SkillDefinition(intent=name, expected_outcomes=(f"{name} succeeds",)),
        evidence_ordinals=(ordinal,),
        grounding_confidence="high",
    )


async def test_reconciler_rejects_duplicate_decisions_with_complete_index_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = (_draft("Upload Resume", 1), _draft("Download Report", 2))
    decisions = tuple(
        SkillReconciliationDecision(
            candidate_index=index,
            action="CREATE",
            proposed_skill=candidates[index - 1],
            confirming_evidence_ordinals=(index,),
            reason="Distinct capability",
        )
        for index in (1, 1, 2)
    )
    response = ModelResponse(
        choices=[
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {"decisions": [decision.model_dump(mode="json") for decision in decisions]}
                    ),
                },
            }
        ]
    )
    monkeypatch.setattr(skill_reconciler, "acompletion", AsyncMock(return_value=response))

    with pytest.raises(ValueError, match="exactly one decision per candidate"):
        await SkillReconciler().reconcile(existing=(), candidates=candidates)


async def test_reconciler_proposes_create_update_and_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_id, download_id = uuid4(), uuid4()
    existing = (
        ExistingApprovedSkill(
            id=upload_id,
            name="Upload Resume",
            definition=SkillDefinition(intent="Upload", expected_outcomes=("Accepted",)),
        ),
        ExistingApprovedSkill(
            id=download_id,
            name="Download Report",
            definition=SkillDefinition(intent="Download", expected_outcomes=("Downloaded",)),
        ),
    )
    candidates = (
        _draft("Upload Resume", 1),
        _draft("Share Report", 2),
        _draft("Download Report", 3),
    )
    decisions = {
        "decisions": [
            {
                "candidate_index": 1,
                "action": "UPDATE_EXISTING",
                "existing_skill_id": str(upload_id),
                "proposed_skill": candidates[0].model_dump(mode="json"),
                "confirming_evidence_ordinals": [1],
                "reason": "New upload constraint",
            },
            {
                "candidate_index": 2,
                "action": "CREATE",
                "existing_skill_id": None,
                "proposed_skill": candidates[1].model_dump(mode="json"),
                "confirming_evidence_ordinals": [2],
                "reason": "Distinct capability",
            },
            {
                "candidate_index": 3,
                "action": "UNCHANGED",
                "existing_skill_id": str(download_id),
                "proposed_skill": None,
                "confirming_evidence_ordinals": [3],
                "reason": "Confirms approved behavior",
            },
        ]
    }
    response = ModelResponse(
        choices=[
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(decisions)},
            }
        ]
    )
    completion = AsyncMock(return_value=response)
    monkeypatch.setattr(skill_reconciler, "acompletion", completion)

    result = await SkillReconciler().reconcile(existing=existing, candidates=candidates)

    assert [decision.action for decision in result] == [
        "UPDATE_EXISTING",
        "CREATE",
        "UNCHANGED",
    ]
    prompt = json.dumps(completion.call_args.kwargs["messages"])
    assert "DELETE" not in prompt
    assert "source_path" not in prompt


async def test_reconciler_rejects_unknown_skill_or_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _draft("Upload Resume", 1)
    invalid = {
        "decisions": [
            {
                "candidate_index": 1,
                "action": "UPDATE_EXISTING",
                "existing_skill_id": str(uuid4()),
                "proposed_skill": candidate.model_copy(
                    update={"evidence_ordinals": (99,)}
                ).model_dump(mode="json"),
                "confirming_evidence_ordinals": [99],
                "reason": "Invalid references",
            }
        ]
    }
    monkeypatch.setattr(
        skill_reconciler,
        "acompletion",
        AsyncMock(
            return_value=ModelResponse(
                choices=[
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(invalid)},
                    }
                ]
            )
        ),
    )

    with pytest.raises(ValueError, match="unknown candidate evidence"):
        await SkillReconciler().reconcile(existing=(), candidates=(candidate,))
