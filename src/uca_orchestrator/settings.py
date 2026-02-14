from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Enterprise pattern:
    - Strict env-driven configuration
    - Defaults safe for local dev
    - Single settings object injected across layers
    """

    model_config = SettingsConfigDict(env_prefix="UCA_", case_sensitive=False)

    env: Literal["dev", "test", "prod"] = "dev"
    service_name: str = "uca-orchestrator"
    log_level: str = "INFO"

    api_host: str = "0.0.0.0"
    api_port: int = 8080

    # Auth
    jwt_alg: str = "HS256"
    jwt_issuer: str = "uca-orchestrator"
    jwt_audience: str = "uca-api"
    jwt_secret: str = Field(default="dev-secret-change-me", repr=False)

    # Persistence
    database_url: str = "sqlite+aiosqlite:///./uca.db"

    # Dummy/internal API base url (used by orchestrator clients)
    internal_api_base_url: str = "http://localhost:8080"

    # Orchestrator
    max_remediation_attempts: int = 5


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
