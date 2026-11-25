"""Tests for Control API configuration."""

import pytest
from markettwin_control_api.config import Settings
from sqlalchemy.engine import make_url


@pytest.mark.parametrize("field", ["census_processor_slots", "census_poll_seconds", "census_orphan_minutes"])
@pytest.mark.parametrize("value", [0, -1])
def test_census_loop_settings_require_positive_values(field, value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_default_settings() -> None:
    """Settings should provide safe local defaults."""

    settings = Settings.model_construct()

    assert settings.app_env == "local"
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


@pytest.mark.parametrize(
    "field",
    ["preflight_wait_seconds", "preflight_wait_poll_seconds", "preflight_reuse_hours"],
)
@pytest.mark.parametrize("value", [0, -1])
def test_preflight_wait_settings_require_positive_values(field, value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(**{field: value})
