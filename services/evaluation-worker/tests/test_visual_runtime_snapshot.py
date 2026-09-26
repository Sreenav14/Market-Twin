from markettwin_evaluation_worker.visual_verifier import (
    VISUAL_MAX_TOKENS,
    VISUAL_RATE_LIMIT_MAX_ATTEMPTS,
    VISUAL_TEMPERATURE,
    build_visual_runtime_snapshot_payload,
    build_visual_verifier_prompt,
)
from pytest import MonkeyPatch


def test_build_visual_runtime_snapshot_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "VISUAL_MODEL_NAME",
        "gpt-4o-mini",
    )

    monkeypatch.setenv(
        "MODEL_API_KEY",
        "must-not-appear",
    )

    payload = (
        build_visual_runtime_snapshot_payload()
    )

    assert (
        payload.agent_role
        == "visual_verifier"
    )

    assert (
        payload.runtime_kind
        == "litellm_direct"
    )

    assert (
        payload.runtime_agent_name
        == "markettwin_visual_verifier"
    )

    assert payload.model_provider == "openai"

    assert (
        payload.model_name
        == "openai/gpt-4o-mini"
    )

    assert payload.model_configuration[
        "temperature"
    ] == VISUAL_TEMPERATURE

    assert payload.model_configuration[
        "max_tokens"
    ] == VISUAL_MAX_TOKENS

    assert payload.model_configuration[
        "rate_limit_max_attempts"
    ] == VISUAL_RATE_LIMIT_MAX_ATTEMPTS

    assert payload.tools == ()

    assert payload.persona_snapshot is None
    assert payload.mission_snapshot is None

    assert "{{criterion}}" in (
        payload.runtime_prompt or ""
    )

    assert "must-not-appear" not in (
        payload.canonical_json()
    )


def test_visual_prompt_contains_actual_criterion() -> None:
    criterion = (
        "The pricing heading is visually readable."
    )

    prompt = build_visual_verifier_prompt(
        criterion
    )

    assert criterion in prompt

    assert (
        "Use only visible image evidence."
        in prompt
    )