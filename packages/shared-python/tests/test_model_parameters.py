"""Model changes must preserve token limits and forward supported API parameters."""

import pytest
from markettwin_shared.model_parameters import completion_parameters


@pytest.mark.parametrize("effort", ["none", "medium"])
def test_openai_reasoning_parameters(monkeypatch: pytest.MonkeyPatch, effort: str) -> None:
    monkeypatch.setenv("MODEL_REASONING_EFFORT", effort)
    parameters = completion_parameters("openai/gpt-6-luna", 32768, temperature=0)
    assert parameters["max_completion_tokens"] == 32768
    assert "max_tokens" not in parameters
    assert parameters["reasoning_effort"] == effort
    assert parameters["allowed_openai_params"] == ["reasoning_effort"]
    assert ("temperature" in parameters) == (effort == "none")


def test_reasoning_setting_does_not_leak_to_other_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_REASONING_EFFORT", "none")
    assert completion_parameters("gemini/video-model", 8192, temperature=0) == {
        "max_tokens": 8192, "temperature": 0,
    }


def test_legacy_openai_model_has_no_reasoning_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_REASONING_EFFORT", raising=False)
    assert completion_parameters("openai/gpt-4o-mini", 300, temperature=0) == {
        "max_completion_tokens": 300, "temperature": 0,
    }
