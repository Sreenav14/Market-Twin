"""Contract checks for the information-preserving research codec."""

import json
from copy import deepcopy

import pytest
from compact_observation import LEGEND, compile_request, make_compiler, pack, unpack
from google.adk.models.llm_request import LlmRequest
from google.genai import types


def payload() -> dict:
    return {
        "step_id": 81,
        "observation": {
            "visible_elements": [{
                "role": "heading", "name": "NOT $10 / month — 年", "tag": "h1",
                "enabled": False, "level": 1,
                "bounding_box": {"x": -1, "y": 0, "width": 190, "height": 24},
            }],
            "aria_snapshot": "Do not delete this unique paragraph",
            "page_errors_since_last_action": ["Payment failed"],
        },
    }


def test_codec_round_trip_preserves_all_fields_and_input() -> None:
    raw = payload()
    before = deepcopy(raw)
    assert unpack(pack(raw)) == raw
    assert raw == before
    assert pack(pack(raw)) == pack(raw)


def test_unknown_field_uses_original_representation() -> None:
    raw = payload()
    raw["observation"]["visible_elements"][0]["new_important_field"] = "blocking"
    assert pack(raw) == raw


def test_corrupt_rows_fail_instead_of_dropping_values() -> None:
    encoded = pack(payload())
    encoded["observation"]["visible_elements"]["rows"][0].pop()
    with pytest.raises(ValueError):
        unpack(encoded)


def test_callback_preserves_original_event_and_tool_identity() -> None:
    original = types.Content(role="user", parts=[types.Part(
        function_response=types.FunctionResponse(id="call_1", name="observe", response=payload())
    )])
    request = LlmRequest(contents=[original], config=types.GenerateContentConfig(
        system_instruction="Keep the user's mission and all safety rules."
    ))
    compile_request(None, request)
    response = request.contents[0].parts[0].function_response
    assert response.id == "call_1"
    assert response.name == "observe"
    assert unpack(response.response) == payload()
    assert original.parts[0].function_response.response == payload()
    assert request.config.system_instruction.count(LEGEND) == 1
    compile_request(None, request)
    assert request.config.system_instruction.count(LEGEND) == 1


@pytest.mark.asyncio
async def test_whole_request_guard_retains_smaller_original() -> None:
    request = LlmRequest(contents=[types.Content(role="user", parts=[types.Part(
        function_response=types.FunctionResponse(id="call_1", name="observe", response=payload())
    )])], config=types.GenerateContentConfig(system_instruction="Keep rules."))
    original = request.model_dump()

    async def measure(candidate):
        return len(json.dumps(candidate.model_dump(mode="json")))

    await make_compiler(measure)(None, request)
    assert request.model_dump() == original


@pytest.mark.asyncio
async def test_measurement_failure_restores_original_request() -> None:
    request = LlmRequest(contents=[types.Content(role="user", parts=[types.Part(
        function_response=types.FunctionResponse(id="call_1", name="observe", response=payload())
    )])], config=types.GenerateContentConfig(system_instruction="Keep rules."))
    original = request.model_dump()
    calls = 0

    async def measure(candidate):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ValueError("Measurement failed")
        return 100

    with pytest.raises(ValueError, match="Measurement failed"):
        await make_compiler(measure)(None, request)
    assert request.model_dump() == original
