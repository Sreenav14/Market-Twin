"""Configuration for the Control API."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    "Environment based control API settings."
    
    app_name: str = "MarketTwin"
    app_env: Literal["local", "development", "test", "production"] = "local"
    log_level: str = "Info"
    
    control_api_host: str = "127.0.0.1"
    control_api_port: int = Field(default=8000, ge=1, le=65535)
    
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "markettwin"
    postgres_user: str = "markettwin"
    postgres_password: str = "markettwin"
    
    kafka_bootstrap_servers: str = "localhost:9092"
    
    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "markettwin-local"
    s3_region: str = "us-east-1"
    
    model_config = SettingsConfigDict(
        env_file = ".env",
        env_file_encoding = "utf-8",
        extra = "ignore",
        case_sensitive = False,
    )
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

@lru_cache
def get_settings() -> Settings:
    "Get the settings for the Control API."
    return Settings()