"""All configuration, declared once, validated at startup.

Nothing else in the app calls os.getenv(). If a value comes from outside the
process, it is declared here or it does not exist.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------- app
    app_name: str = "Task Tracker API"
    environment: Literal["local", "staging", "production"] = "local"
    debug: bool = False
    log_level: str = "INFO"

    # Every route sits under this. Bumping to /api/v2 later means adding a
    # second router package, not editing 20 decorators.
    api_v1_prefix: str = "/api/v1"

    # ------------------------------------------------------------ database
    database_url: str

    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800

    # ----------------------------------------------------------- paging
    default_page_size: int = 20
    max_page_size: int = 100

    # ------------------------------------------------------------- auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    login_max_attempts: int = 5
    login_lockout_minutes: int = 15

    @field_validator("jwt_secret")
    @classmethod
    def secret_must_be_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "JWT_SECRET must be at least 32 characters. Generate one with:\n"
                '  python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        if v.lower() in {"changeme", "secret", "your-secret-key"}:
            raise ValueError("JWT_SECRET is still the placeholder value")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Built once, on first call. main.py calls it at import so a broken .env
    stops the app from starting instead of 500-ing on the first request."""
    return Settings()
