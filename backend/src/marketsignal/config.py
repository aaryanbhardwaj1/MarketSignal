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
    chunking_policy_version: str = "c2"  # child policy; changing it rebuilds children only
    # Experiment switch (Phase 2, off = policy c2): prefix row children's retrieval text with the
    # row's identifier columns (e.g. review_id=RV-00655) so ID lookups can match lexically. Child
    # text only - parent text, handles and spans are unchanged. Pair with a new policy version.
    row_child_identifiers: bool = False
    # c2: identifier columns are never free text (numeric rows are not retrieval units)

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

    # ── Dense search (smoke lanes and production dense lane) ──
    hnsw_ef_search: int = Field(default=100, ge=1)
    dev_endpoints_enabled: bool = True  # forced off when env == "prod"

    # ── Retrieval (plan §11-15, ADR-0002/0005); every value is tunable, Phase 2 measures them ──
    retrieval_lane_k: int = Field(default=100, ge=1)  # children per lane (§13)
    retrieval_class_lane_k: int = Field(default=40, ge=1)  # per-class lanes, >= 2 classes (§12)
    retrieval_rrf_k: int = Field(default=60, ge=1)  # Cormack et al. 2009
    retrieval_dense_weight: float = Field(default=1.0, ge=0)
    retrieval_lexical_weight: float = Field(default=1.0, ge=0)
    retrieval_pool_size: int = Field(default=20, ge=1)  # rerank pool, Recall@pool
    retrieval_top_k: int = Field(default=10, ge=1)
    retrieval_dense_exact: bool = False  # exact scan instead of HNSW (CI gate, ANN check)
    embed_query_instruction: str = ""  # bge retrieval instruction: decided by the Phase 2 A/B
    query_embedding_cache_size: int = Field(default=512, ge=0)
    lexical_df_prune: float = Field(default=0.9, gt=0, le=1)  # drop near-universal terms
    lexical_phrase_bonus: float = Field(default=1.0, ge=0)
    lexical_idf_cache_size: int = Field(default=32, ge=1)  # (workspace, corpus_version) entries
    rerank_enabled: bool = True
    rerank_model_name: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    rerank_max_pairs: int = Field(default=40, ge=1)
    rerank_parent_max_tokens: int = Field(default=350, ge=1)  # larger parents: anchor pairs
    rerank_anchors_per_parent: int = Field(default=2, ge=1)
    rerank_max_chars: int = Field(default=2000, ge=100)  # passage cap before tokenizer truncation
    rerank_timeout_s: float = Field(default=8.0, gt=0)  # set from target p95 at the deploy spike
    rerank_threads: int | None = None  # onnxruntime intra-op threads (None: runtime default)
    rerank_concurrency: int = Field(default=1, ge=1)  # simultaneous rerank calls per process
    balance_enabled: bool = False  # decided by the Phase 2 measurement
    balance_per_source_max: int = Field(default=3, ge=1)  # final list (§15)
    balance_pool_source_cap: int = Field(default=7, ge=1)  # fused pool, about 1/3 of 20 (§13)
    retrieval_trace_persist: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
