"""Configuration for the Control API."""

from functools import lru_cache
from typing import Literal

from markettwin_shared.messaging import (
    KafkaProducerSettings,
)
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    "Environment based control API settings."
    
    app_name: str = "MarketTwin"
    app_env: Literal["local", "development", "test", "production"] = "local"
    log_level: str = "Info"
    
    control_api_host: str = "127.0.0.1"
    control_api_port: int = Field(default=8000, ge=1, le=65535)
    session_idle_timeout_minutes: int = Field(
    default = 30,
    ge=1,
    le=1440,
    )

    session_absolute_timeout_hours: int = Field(
    default = 8,
    ge=1,
    le=168,
    )
    
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "markettwin"
    postgres_user: str = "markettwin"
    postgres_password: str = "markettwin"
    outbox_relay_enabled: bool = False
    knowledge_worker_url: str = "http://127.0.0.1:8010"
    knowledge_model_timeout_seconds: float = Field(default=180, gt=0)
    knowledge_preview_timeout_seconds: float = Field(default=240, gt=0)
    knowledge_preview_max_bytes: int = Field(default=52428800, gt=0)
    kafka_bootstrap_servers: str = "localhost:9092"
    
    kafka_security_protocol: Literal[
        "PLAINTEXT",
        "SSL",
        "SASL_PLAINTEXT",
        "SASL_SSL",
    ] = "PLAINTEXT"
    
    kafka_sasl_mechanism: Literal[
        "PLAIN",
        "SCRAM-SHA-256",
        "SCRAM-SHA-512",
    ] | None = None
    
    kafka_username: str | None = None
    kafka_password: SecretStr | None = None
    kafka_ssl_ca_file: str | None = None
    
    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "markettwin-local"
    s3_region: str = "us-east-1"
    
    model_config = SettingsConfigDict(
        env_file = ".env",
        env_file_encoding = "utf-8",
        extra = "ignore",
        case_sensitive = False,
    )

    @model_validator(mode="after")
    def validate_knowledge_timeout(self) -> "Settings":
        if self.knowledge_preview_timeout_seconds <= self.knowledge_model_timeout_seconds:
            raise ValueError("Knowledge preview timeout must exceed model timeout.")
        return self
    @property
    def database_url(self) -> str:
        """Return the async PostgreSQL database URL."""
        return (
            "postgresql+asyncpg://"
            f"{self.postgres_user}:"
            f"{self.postgres_password}@"
            f"{self.postgres_host}:"
            f"{self.postgres_port}/"
            f"{self.postgres_db}"
        )
        
    @property
    def kafka_producer_settings(
        self
    )-> KafkaProducerSettings:
        "Return the Kafka producer configuration."
        
        bootstrap_servers = tuple(
            server.strip()
            for server in self.kafka_bootstrap_servers.split(",")
            if server.strip()
        )

        if not bootstrap_servers:
            raise ValueError("Kafka bootstrap servers are required.")
        
        password = (
            self.kafka_password.get_secret_value()
            if self.kafka_password is not None
            else None
        )
        
        return KafkaProducerSettings(
            bootstrap_servers = bootstrap_servers,
            security_protocol = self.kafka_security_protocol,
            sasl_mechanism = self.kafka_sasl_mechanism,
            username = self.kafka_username,
            password = password,
            ssl_ca_file = self.kafka_ssl_ca_file,
            client_id = "markettwin-control-api",
        )

@lru_cache
def get_settings() -> Settings:
    "Get the settings for the Control API."
    return Settings()

