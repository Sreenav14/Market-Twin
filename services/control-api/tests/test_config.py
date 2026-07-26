"""Tests for Control API configuration."""

from markettwin_control_api.config import Settings


def test_default_settings() -> None:
    """Settings should provide safe local defaults."""

    settings = Settings(_env_file=None)

    assert settings.app_name == "MarketTwin"
    assert settings.app_env == "local"
    assert settings.control_api_port == 8000
    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 5432
    assert settings.kafka_bootstrap_servers == "localhost:9092"
    assert settings.s3_endpoint_url == "http://localhost:9000"
    assert settings.s3_bucket == "markettwin-local"