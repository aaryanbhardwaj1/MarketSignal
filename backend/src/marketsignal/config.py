"""Application settings.

Every tunable lives here and is read from the environment (prefix ``MS_``). The repository-root
``.env`` is loaded automatically in local development; deployed environments inject variables
through the platform's secret store.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MS_",
        env_file=(_REPO_ROOT / ".env", _BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["dev", "test", "prod"] = "dev"

    # Runtime connection: the non-owner, non-superuser, non-BYPASSRLS application role.
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://ms_app:dev-only-insecure-app@localhost:5432/marketsignal"
    )
    # Schema-owner connection: used only by Alembic migrations.
    migrations_database_url: SecretStr = SecretStr(
        "postgresql+psycopg://ms_owner:dev-only-insecure-owner@localhost:5432/marketsignal"
    )
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_statement_timeout_ms: int = Field(default=15_000, ge=100)

    # Refuse to start when connected as a superuser / BYPASSRLS role (RLS would be silently
    # bypassed). Only tests that deliberately exercise the guard turn this on.
    allow_privileged_db_role: bool = False

    # Redis is optional for correctness: failures degrade (cache bypass), never block answering.
    redis_url: SecretStr | None = SecretStr("redis://localhost:6379/0")

    alembic_ini_path: Path = _BACKEND_DIR / "alembic.ini"
    min_pgvector_version: str = "0.8.0"

    cors_allowed_origins: list[str] = ["http://localhost:3000"]
    metrics_token: SecretStr | None = None

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
