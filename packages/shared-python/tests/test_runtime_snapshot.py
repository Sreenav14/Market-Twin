from markettwin_shared.runtime_snapshot import (
    AgentRuntimeSnapshotPayload,
    sanitize_snapshot_value,
)


def _persona_snapshot(
    *,
    model_configuration: dict[str, object] | None = None,
    model_name: str = "openai/gpt-4o-mini",
) -> AgentRuntimeSnapshotPayload:
    return AgentRuntimeSnapshotPayload(
        agent_role="persona",
        runtime_kind="google_adk",
        runtime_agent_name="markettwin_p1__m1",
        agent_version=1,
        snapshot_schema_version=1,
        model_provider="openai",
        model_name=model_name,
        model_configuration=(
            model_configuration
            if model_configuration is not None
            else {
                "max_tokens": 512,
                "num_retries": 2,
            }
        ),
        base_instruction="You are a MarketTwin simulated user.",
        effective_instruction=("You are a MarketTwin simulated user.\nPersona: First-time user"),
        runtime_prompt="Execute your assigned MarketTwin Journey.",
        persona_snapshot={
            "persona_id": "p1",
            "name": "First-time user",
        },
        mission_snapshot={
            "mission_id": "m1",
            "objective": "Find pricing.",
        },
        success_criteria=("Pricing is discoverable.",),
        tools=(
            "browser_get_state",
            "browser_click",
        ),
        policy_references=("sensitive_input_policy_v1",),
    )


def test_snapshot_hash_is_stable_for_mapping_key_order() -> None:
    first = _persona_snapshot(
        model_configuration={
            "max_tokens": 512,
            "nested": {
                "temperature": 0,
                "num_retries": 2,
            },
        }
    )

    second = _persona_snapshot(
        model_configuration={
            "nested": {
                "num_retries": 2,
                "temperature": 0,
            },
            "max_tokens": 512,
        }
    )

    assert first.canonical_json() == second.canonical_json()
    assert first.sha256() == second.sha256()


def test_snapshot_hash_changes_when_semantic_configuration_changes() -> None:
    first = _persona_snapshot(
        model_name="openai/gpt-4o-mini",
    )
    second = _persona_snapshot(
        model_name="openai/gpt-4.1-mini",
    )

    assert first.sha256() != second.sha256()


def test_sensitive_values_are_removed_recursively() -> None:
    value = {
        "model": "openai/gpt-4o-mini",
        "api_key": "do-not-store-me",
        "nested": {
            "Authorization": "Bearer secret",
            "client_secret": "also-secret",
            "max_tokens": 512,
        },
    }

    sanitized = sanitize_snapshot_value(value)

    assert isinstance(sanitized, dict)

    assert sanitized["model"] == "openai/gpt-4o-mini"
    assert "api_key" not in sanitized

    nested = sanitized["nested"]

    assert isinstance(nested, dict)
    assert "Authorization" not in nested
    assert "client_secret" not in nested
    assert nested["max_tokens"] == 512


def test_secret_values_do_not_change_snapshot_hash() -> None:
    first = _persona_snapshot(
        model_configuration={
            "max_tokens": 512,
            "api_key": "secret-one",
        }
    )

    second = _persona_snapshot(
        model_configuration={
            "api_key": "secret-two",
            "max_tokens": 512,
        }
    )

    assert first.sha256() == second.sha256()


def test_safe_token_configuration_is_not_removed() -> None:
    sanitized = sanitize_snapshot_value(
        {
            "max_tokens": 512,
            "token_budget": 10_000,
            "access_token": "secret",
        }
    )

    assert isinstance(sanitized, dict)

    assert sanitized["max_tokens"] == 512
    assert sanitized["token_budget"] == 10_000
    assert "access_token" not in sanitized


def test_snapshot_rejects_non_json_runtime_values() -> None:
    snapshot = _persona_snapshot(
        model_configuration={
            "unsupported": object(),
        }
    )

    try:
        snapshot.sha256()
    except TypeError as exc:
        assert "JSON-compatible" in str(exc)
    else:
        raise AssertionError("Expected unsupported runtime value to raise TypeError.")


def test_snapshot_rejects_invalid_versions() -> None:
    try:
        AgentRuntimeSnapshotPayload(
            agent_role="meta",
            runtime_kind="google_adk",
            agent_version=0,
        )
    except ValueError as exc:
        assert "agent_version" in str(exc)
    else:
        raise AssertionError("Expected invalid agent_version to raise ValueError.")
