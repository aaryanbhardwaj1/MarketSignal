"""Application settings.

Every tunable lives here and is read from the environment (prefix ``MS_``). The repository-root
``.env`` is loaded automatically in local development; deployed environments inject variables
through the platform's secret store.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import AliasChoices, Field, SecretStr, model_validator
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
    chunking_policy_version: str = "c3"  # child policy; changing it rebuilds children only
    # Policy c3 (Phase 2, measured then approved): row children's retrieval text is prefixed with
    # the row's identifier columns (e.g. review_id=RV-00655) so ID lookups match lexically. Child
    # text only - parent text, handles and spans are unchanged. False + "c2" reproduces c2.
    row_child_identifiers: bool = True
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
    embed_query_instruction: str = ""  # bge retrieval instruction: A/B'd in Phase 2, not adopted
    embed_query_timeout_s: float = Field(default=5.0, gt=0)  # then lexical-only, flagged
    model_load_retry_cooldown_s: float = Field(default=30.0, ge=0)  # after a failed model load
    query_embedding_cache_size: int = Field(default=512, ge=0)
    lexical_df_prune: float = Field(default=0.9, gt=0, le=1)  # drop near-universal terms
    lexical_phrase_bonus: float = Field(default=1.0, ge=0)
    lexical_idf_cache_size: int = Field(default=32, ge=1)  # (workspace, corpus_version) entries
    # Phase 2 decision: off by default. Dev gains did not hold on the held-out split (hit@10
    # 76.2 -> 57.1); kept for experiments that use new dev items and a new frozen holdout.
    rerank_enabled: bool = False
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

    # ── Grounded answering (Phase 3, plan §3, §19-21; ADR-0004/0008/0015) ──
    # The key is read from MS_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY; it is a SecretStr so it
    # never appears in reprs, logs or error messages, and it is never stored or traced.
    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("MS_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
    )
    llm_provider: str = "anthropic"  # anthropic | fake (tests, offline demo)
    llm_model: str = "claude-sonnet-5-5"  # synthesis model (plan §5)
    llm_effort: str = "low"  # output_config.effort
    llm_max_tokens: int = Field(default=8000, ge=256)
    llm_thinking: str = "disabled"  # disabled | adaptive (display omitted; never streamed)
    llm_timeout_s: float = Field(default=40.0, gt=0)
    # List prices (USD per million tokens) for approximate cost reporting only; claude-sonnet-5-5
    # as published on platform.claude.com/docs/en/about-claude/pricing (checked 2026-10-06).
    llm_price_input_per_mtok: float = Field(default=2.0, ge=0)
    llm_price_output_per_mtok: float = Field(default=10.0, ge=0)
    llm_price_cache_write_per_mtok: float = Field(default=2.5, ge=0)  # 5-minute cache write
    llm_price_cache_read_per_mtok: float = Field(default=0.2, ge=0)
    pack_max_items: int = Field(default=12, ge=1, le=12)  # aliases E1..E12
    pack_max_tokens: int = Field(default=9000, ge=500)
    pack_item_max_tokens: int = Field(default=900, ge=100)
    pack_candidates: int = Field(default=24, ge=1)
    run_deadline_s: float = Field(default=60.0, gt=0)
    run_gather_budget_s: float = Field(default=35.0, gt=0)
    regeneration_min_remaining_s: float = Field(default=15.0, ge=0)
    # Time kept back from the run deadline for verification + fallback: an LLM call is clamped
    # to (remaining - reserve), so a slow model degrades to evidence-only, not a run timeout.
    run_finalize_reserve_s: float = Field(default=3.0, ge=0)
    # A run still 'running' past run_deadline_s + run_reap_margin_s is an orphan (its process
    # died): the periodic reaper and the SSE stream close it with done(interrupted).
    run_reap_margin_s: float = Field(default=60.0, ge=0)
    # Finalization (persist -> final -> done) runs after the deadline but is bounded by this,
    # plus a best-effort done/row update of at most half the remaining margin, so a live run is
    # always concluded before it could be taken for an orphan.
    run_finalize_timeout_s: float = Field(default=20.0, gt=0)
    run_reaper_interval_s: float = Field(default=60.0, gt=0)
    # SSE keep-alive: FastAPI's native EventSourceResponse sends ': ping' every 15 s (plan §21).
    sse_token_coalesce_ms: int = Field(default=100, ge=0)
    sse_poll_interval_s: float = Field(default=1.0, gt=0)  # cross-process fallback
    # HS256 key: at least 32 bytes (RFC 7518 §3.2). The dev default is refused in prod.
    stream_token_secret: SecretStr = SecretStr("dev-only-insecure-stream-token-secret-0001")
    stream_token_replay_s: int = Field(default=900, ge=0)  # 15-minute replay window

    # --- Verifier (Phase 4 / former 3.1). The cap is stated in the prompt and the feedback. ---
    verifier_max_citations: int = Field(default=20, ge=4, le=60)

    # --- Research agent bounds (plan §19, ADR-0007). Every bound has a flag and a test. ---
    agent_step_limit: int = Field(default=4, ge=1, le=10)
    agent_max_tool_calls: int = Field(default=10, ge=1, le=30)
    agent_max_consecutive_tool_errors: int = Field(default=3, ge=1, le=10)
    agent_max_context_tokens: int = Field(default=40_000, ge=4_000)  # replayed input per step
    agent_max_output_tokens_total: int = Field(default=12_000, ge=1_000)  # summed over steps
    agent_max_tokens: int = Field(default=4_096, ge=256)  # per agent step
    agent_effort: str = "low"
    agent_gather_budget_s: float = Field(default=35.0, gt=0)
    # Phase 5 A3: hand a bounded, deterministic research summary to synthesis (on by default).
    research_summary: bool = True
    evidence_pool_max: int = Field(default=40, ge=1)

    # --- Structured analytics (Phase 5; plan §18). Deterministic engine limits. ---
    analytics_max_filters: int = Field(default=5, ge=1, le=10)
    analytics_max_filter_values: int = Field(default=20, ge=1, le=100)
    analytics_max_metrics: int = Field(default=4, ge=1, le=8)
    analytics_max_group_by: int = Field(default=2, ge=1, le=3)
    analytics_max_groups: int = Field(default=50, ge=1, le=500)
    analytics_max_rows: int = Field(default=20, ge=1, le=200)
    analytics_max_scan_rows: int = Field(default=20_000, ge=100)
    analytics_timeout_s: float = Field(default=5.0, gt=0)

    # --- Governed tools and MCP (plan §17-18, ADR-0006) ---
    tool_timeout_s: float = Field(default=8.0, gt=0)
    tool_statement_timeout_ms: int = Field(default=5_000, ge=100)
    obs_max_tokens: int = Field(default=1_000, ge=100)  # model-visible observation per call
    tools_transport: str = "inprocess"  # inprocess | http (Streamable HTTP over loopback)
    mcp_public: bool = False  # /mcp accepts loopback clients only unless true
    # Host header allowlist when mcp_public (exact "host[:port]" or "name:*"); empty = loopback.
    mcp_allowed_hosts: list[str] = Field(default_factory=list)
    mcp_base_url: str = "http://127.0.0.1:8000/mcp"
    # Dedicated HS256 key for run-scoped capability tokens (aud=mcp). Dev default refused in prod.
    mcp_token_key: SecretStr = SecretStr("dev-only-insecure-mcp-capability-key-00001")

    @model_validator(mode="after")
    def _finalize_fits_the_reap_margin(self) -> Self:
        if self.run_finalize_timeout_s >= self.run_reap_margin_s:
            raise ValueError("run_finalize_timeout_s must be less than run_reap_margin_s")
        return self


def check_production_secrets(settings: Settings) -> None:
    """Refuse to run in prod with development secrets or a short stream-token key."""
    secret = settings.stream_token_secret.get_secret_value()
    if len(secret.encode()) < 32:
        raise ValueError("MS_STREAM_TOKEN_SECRET must be at least 32 bytes")
    if settings.env == "prod" and secret.startswith("dev-only"):
        raise ValueError("MS_STREAM_TOKEN_SECRET must be set in production")
    mcp_key = settings.mcp_token_key.get_secret_value()
    if len(mcp_key.encode()) < 32:
        raise ValueError("MS_MCP_TOKEN_KEY must be at least 32 bytes")
    if settings.env == "prod" and mcp_key.startswith("dev-only"):
        raise ValueError("MS_MCP_TOKEN_KEY must be set in production")
    if mcp_key == secret:
        raise ValueError("MS_MCP_TOKEN_KEY must differ from MS_STREAM_TOKEN_SECRET")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
