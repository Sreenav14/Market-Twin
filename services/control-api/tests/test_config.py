"""Tests for Control API configuration."""

import pytest
from markettwin_control_api.config import Settings
from pydantic import ValidationError
from sqlalchemy.engine import make_url


def test_default_settings() -> None:
    """Settings should provide safe local defaults."""

    settings = Settings.model_construct()

    assert settings.app_name == "MarketTwin"
    assert settings.app_env == "local"
    assert settings.control_api_port == 8000
    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 5432
    assert settings.kafka_bootstrap_servers == "localhost:9092"
    assert settings.s3_endpoint_url == "http://localhost:9000"
    assert settings.s3_bucket == "markettwin-local"


def test_database_url_round_trips_reserved_credentials() -> None:
    settings = Settings.model_construct(postgres_user="user@host", postgres_password="p@ss:/%word")
    parsed = make_url(settings.database_url)
    assert parsed.username == "user@host"
    assert parsed.password == "p@ss:/%word"


def test_hitl_secret_uses_worker_environment_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETTWIN_HITL_INTERNAL_SECRET", "canonical" * 4)
    monkeypatch.setenv("HITL_INTERNAL_SECRET", "legacy" * 6)
    settings = Settings()
    assert settings.hitl_internal_secret is not None
    assert settings.hitl_internal_secret.get_secret_value() == "canonical" * 4


@pytest.mark.parametrize("environment", ["development", "production"])
def test_nonlocal_knowledge_worker_requires_secret(environment: str) -> None:
    with pytest.raises(ValidationError, match="required outside local/test"):
        Settings.model_validate({"app_env": environment, "knowledge_internal_secret": None})


@pytest.mark.parametrize("environment", ["local", "test", "production"])
def test_configured_knowledge_secret_must_be_long_enough(environment: str) -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings.model_validate({"app_env": environment, "knowledge_internal_secret": "short"})



def test_knowledge_secret_rejects_whitespace_only() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings.model_validate({"knowledge_internal_secret": " " * 32})
