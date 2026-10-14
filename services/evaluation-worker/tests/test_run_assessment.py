"""Model assessment must stay grounded and cannot replace runtime evidence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_evaluation_worker import run_assessment as assessment


def result_payload(journey_id):
    return {
        "individual_results": [
            {
                "journey_id": str(journey_id),
                "goal_outcome": "met",
                "ease_of_use": "easy",
                "summary": "The recorded mission completed.",
                "recommendations": [],
            }
        ],
        "overall": {
            "goal_outcome": "met",
            "ease_of_use": "easy",
            "summary": "The tested flow supports the goal.",
            "supporting_journey_ids": [str(journey_id)],
            "recommendations": [],
            "limitations": ["Only the assigned flow was tested."],
        },
    }


@pytest.mark.parametrize("invalid", ["duplicate", "unknown", "citation", "runtime", "missing"])
def test_assessment_rejects_missing_duplicate_foreign_and_runtime_verdicts(invalid):
    journey_id = uuid4()
    payload = result_payload(journey_id)
    journeys = [{"journey_id": str(journey_id), "execution_status": "completed"}]
    if invalid == "duplicate":
        payload["individual_results"] *= 2
    elif invalid == "unknown":
        payload["individual_results"][0]["journey_id"] = str(uuid4())
    elif invalid == "citation":
        payload["overall"]["supporting_journey_ids"] = [str(uuid4())]
    elif invalid == "runtime":
        journeys[0]["execution_status"] = "failed"
    else:
        journeys.append({"journey_id": str(uuid4()), "execution_status": "completed"})
    with pytest.raises(ValueError):
        assessment.validate_assessment(assessment.RunAssessment.model_validate(payload), journeys)


@pytest.mark.parametrize("response_mode", ["valid", "malformed", "length", "timeout"])
async def test_single_configured_model_call_preserves_results_on_failure(
    monkeypatch, response_mode
):
    run_id, journey_id, execution_id, persona_id, mission_id = (uuid4() for _ in range(5))
    monkeypatch.setenv("MODEL_NAME", "generic/provider-model")
    monkeypatch.setenv("EVALUATION_MODEL_MAX_OUTPUT_TOKENS", "2048")
    monkeypatch.delenv("EVALUATION_MODEL_NAME", raising=False)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_API_BASE", raising=False)
    repository = SimpleNamespace(
        list_journey_results=AsyncMock(
            return_value=(
                SimpleNamespace(
                    journey_id=journey_id,
                    execution_id=execution_id,
                    persona_id=persona_id,
                    mission_id=mission_id,
                    payload={"status": "completed", "outcome": "passed"},
                ),
            )
        )
    )
    snapshot = SimpleNamespace(ensure_run_level_snapshot=AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(assessment, "EvaluationRepository", lambda _: repository)
    monkeypatch.setattr(assessment, "EvaluationRuntimeSnapshotRepository", lambda _: snapshot)
    monkeypatch.setattr(
        assessment.litellm, "get_supported_openai_params", lambda **_: ["response_format"]
    )
    payload = assessment.RunAssessment.model_validate(result_payload(journey_id))
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="length" if response_mode == "length" else "stop",
                message=SimpleNamespace(
                    content="{" if response_mode == "malformed" else payload.model_dump_json()
                ),
            )
        ]
    )
    model = AsyncMock(return_value=response)
    if response_mode == "timeout":
        model.side_effect = TimeoutError("Provider timeout")
    monkeypatch.setattr(assessment.litellm, "acompletion", model)

    class Session:
        async def get(self, *_):
            return SimpleNamespace(
                status="completed", configuration_snapshot={"study_brief": "Check a flow"}
            )

        async def scalars(self, statement):
            rows = (
                [SimpleNamespace(id=persona_id, name="Assigned user")]
                if "run_personas" in str(statement)
                else [SimpleNamespace(id=mission_id, title="Assigned mission")]
            )
            return SimpleNamespace(all=lambda: rows)

    result = await assessment.assess_completed_run(
        test_run_id=run_id,
        session=Session(),
        evaluation_records=(),
    )
    assert result["status"] == ("completed" if response_mode == "valid" else "unavailable")
    assert result["runtime"]["duration_seconds"] >= 0
    assert result["runtime"]["completed_at"]
    if response_mode == "valid":
        assert result["individual_results"][0]["persona_name"] == "Assigned user"
        assert result["individual_results"][0]["mission_title"] == "Assigned mission"
    model.assert_awaited_once()
    assert model.call_args.kwargs["model"] == "generic/provider-model"
    assert model.call_args.kwargs["max_tokens"] == 2048
    snapshot_payload = snapshot.ensure_run_level_snapshot.call_args.kwargs["payload"]
    assert snapshot_payload.agent_role == "evaluator"
    assert snapshot_payload.effective_instruction == assessment.ASSESSMENT_INSTRUCTION
    assert str(journey_id) in snapshot_payload.runtime_prompt
