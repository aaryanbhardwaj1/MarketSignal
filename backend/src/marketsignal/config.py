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

    # ── Identity (Phase 1: single demo principal; ADR-0014 adds real sessions) ──
    demo_principal: str = "demo"

    # ── Upload validation (plan §4) ──
    upload_max_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    zip_max_entries: int = Field(default=2_000, ge=1)
    zip_max_uncompressed_bytes: int = Field(default=200 * 1024 * 1024, ge=1)
    zip_max_compression_ratio: int = Field(default=100, ge=1)

    # ── Parsing limits ──
    parse_timeout_s: float = Field(default=120.0, gt=0)
    max_pdf_pages: int = Field(default=300, ge=1)
    max_slides: int = Field(default=500, ge=1)
    max_table_rows: int = Field(default=100_000, ge=1)
    pdf_min_words_per_page: int = Field(default=5, ge=0)  # below: PARTIAL_EXTRACTION warning

    # ── Pipeline versions: part of provenance and of the idempotency key ──
    parser_version: str = "p1"
    structure_version: str = "s1"  # parent policy; changing it mints new source versions
    chunking_policy_version: str = "c1"  # child policy; changing it rebuilds children only

    # ── Hierarchical chunking (ADR-0003) ──
    parent_max_tokens: int = Field(default=800, ge=64)
    child_window_tokens: int = Field(default=192, ge=16)
    child_overlap_tokens: int = Field(default=32, ge=0)
    table_summary_max_levels: int = Field(default=12, ge=1)

    # ── Embeddings (ADR-0012) ──
    embed_model_id: str = "bge-small-en-v1.5"
    embed_model_name: str = "BAAI/bge-small-en-v1.5"
    embed_dimensions: int = 384
    embed_batch_size: int = Field(default=64, ge=1)
    embed_threads: int | None = None  # None: onnxruntime default (container CPU quota)
    model_cache_dir: Path = _REPO_ROOT / ".cache" / "models"
    embedding_cache_dir: Path = _REPO_ROOT / ".cache" / "embeddings"

    # ── Ingestion health check (plan §4) ──
    health_sample_size: int = Field(default=5, ge=0)
    health_dense_top_k: int = Field(default=5, ge=1)

    # ── Dense smoke search (Phase 1 verification only; Phase 2 replaces it) ──
    hnsw_ef_search: int = Field(default=100, ge=1)
    dev_endpoints_enabled: bool = True  # forced off when env == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
