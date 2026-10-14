/**
 * Frozen API contract for the productized UI (final phase). Backend endpoints return exactly
 * these shapes; pages build against them. Changes go through the lead, never ad hoc.
 *
 * Every endpoint is read-only except the run pre-check (503 PROVIDER_UNAVAILABLE). Workspace
 * endpoints are scoped by forced RLS; developer endpoints (`/api/dev/eval/*`) exist only in
 * development builds.
 */

import type { WorkspaceDetail } from "./types";

export type Cursor = string | null; // opaque base64("<iso>|<uuid>")
export interface Page<T> {
  items: T[];
  next_cursor: Cursor;
}

// ── E1 GET /api/capabilities ────────────────────────────────────────────────────────────────
export type GenerationUnavailableReason = "DISABLED" | "NOT_CONFIGURED" | "PROVIDER_REJECTED";
export interface Capabilities {
  generation: { available: boolean; reason: GenerationUnavailableReason | null };
}

// ── E3 GET /api/workspaces/{ws} (extends the existing detail) ───────────────────────────────
export interface WorkspaceOverview extends WorkspaceDetail {
  sources_by_type: Record<string, number>;
  sources_by_class: Record<string, number>;
  dataset_count: number;
  analytics_result_count: number;
  conversation_count: number; // excludes test-harness runs
  runs: {
    total: number;
    by_mode: Record<string, number>;
    by_termination_state: Record<string, number>;
    last_run_at: string | null;
  };
  last_ready_at: string | null;
}

// ── E4 GET /api/workspaces/{ws}/conversations ───────────────────────────────────────────────
// ?limit=1..100 (25) &cursor &q &featured=bool &include_test_runs=false
export type RunModeUsed = "standard" | "research";
export interface ConversationSummary {
  conversation_id: string;
  title: string;
  title_source: "title" | "first_question";
  created_at: string;
  updated_at: string;
  message_count: number;
  featured: boolean;
  last_run: null | {
    run_id: string;
    mode: RunModeUsed;
    status: string;
    termination_state: string | null;
    degradation_flags: string[];
    created_at: string;
    finished_at: string | null;
  };
}

// ── existing GET /api/workspaces/{ws}/runs/{run_id}, typed ──────────────────────────────────
export interface AgentTraceStep {
  step: number;
  call_index: number;
  tool: string;
  args: unknown; // sanitized by the governance audit
  status: string;
  error_code: string | null;
  handles: string[];
  duration_ms: number;
}
export interface RunRecord {
  run_id: string;
  conversation_id: string;
  mode: RunModeUsed;
  status: string;
  termination_state: string | null;
  degradation_flags: string[];
  original_query: string;
  pack_handles: string[];
  cited_handles: string[];
  usage: Record<string, number>;
  timings: Record<string, number>;
  models: Record<string, string>;
  route: Partial<{
    requested: string;
    persona_default: string;
    decided: string;
    reason: string;
    cues: string[];
    task_type: string;
  }>;
  agent: null | {
    stop_reason: string;
    steps: number;
    tool_calls: number;
    tool_errors: number;
    pool_size: number;
    sufficient: boolean | null; // null when the planner never ran (e.g. planner_unavailable)
    gap_count: number;
    duration_ms: number;
    flags: string[];
    usage: Record<string, number>;
    trace: AgentTraceStep[];
  };
  tool_calls: unknown;
  created_at: string;
  finished_at: string | null;
}

// ── E5 GET /api/workspaces/{ws}/runs/{run_id}/verification (never includes rejected spans) ──
export type Disposition = "accepted" | "repaired" | "regenerate" | "rejected" | "fallback";
export interface VerificationAttemptSummary {
  attempt: number;
  disposition: Disposition;
  passed: boolean;
  citations: number;
  failure_categories: string[];
  repairs_n: number;
  rejected: { reason: string; section: string | null; aliases: string[] }[];
  result_ids: string[];
}
export interface RunVerification {
  run_id: string;
  final_disposition: Disposition | null;
  attempts: VerificationAttemptSummary[];
}

// ── E6 GET /api/workspaces/{ws}/analytics/datasets, /datasets/{dataset_id} ──────────────────
export interface DatasetColumn {
  name: string;
  type: string;
  unit: string;
  scale: string;
  levels: string[];
  non_empty: number;
}
export interface DatasetInfo {
  dataset: string;
  source_code: string;
  source_version: number;
  title: string;
  table: string;
  source_class: string;
  row_count: number;
  columns: DatasetColumn[];
}
export interface DatasetList {
  datasets: DatasetInfo[];
  truncated: boolean;
}

// ── E7 GET /api/workspaces/{ws}/analytics/results ───────────────────────────────────────────
// ?limit &cursor &tool &run_id &include_test_runs=false
export interface AnalyticsResultSummary {
  result_id: string;
  tool: "aggregate" | "filter_rows" | "group_compare";
  dataset: string;
  source_code: string;
  source_version: number;
  summary: string | null;
  metrics: string[];
  query_run_id: string | null;
  conversation_id: string | null;
  created_at: string;
}

// ── shared by E8 / E9 (curated brief, recomputed on request) ────────────────────────────────
export type Integrity = "verified" | "stale" | "withdrawn";
export interface EvidenceRef {
  handle: string;
  integrity: Integrity;
  role: "support" | "contradict";
  quote: string | null; // null unless verified
  char_start: number | null;
  char_end: number | null;
  child_id: string | null;
  source: { code: string; title: string; source_type: string; source_class: string; version: number };
  locator_label: string;
  note: string | null;
  states_projection: boolean; // the quoted passage itself states a forward projection
}
export interface AnalysisFilter {
  column: string;
  label: string;
  op: string;
  values: (string | number)[];
}
export interface AnalysisRow {
  group: Record<string, string>;
  value: number | null;
  numerator?: number;
  denominator?: number;
  display: string | null;
}
export type AnalysisUnit = "percent" | "count" | "usd" | "score" | "ratio";
export interface Analysis {
  id: string;
  title: string;
  question: string;
  category: string;
  status: "computed" | "mismatch" | "unavailable";
  op: "aggregate" | "filter_rows" | "group_compare";
  unit: AnalysisUnit;
  presentation: "bar" | "table" | "single";
  denominator: { label: string; value: number } | null;
  filters: AnalysisFilter[];
  group_by: string[];
  value: number | null;
  display: string | null;
  rows: AnalysisRow[]; // rows/value empty unless computed
  columns?: string[];
  provenance: {
    dataset: string;
    source_code: string;
    source_title: string;
    version: number;
    table: string;
    rows_matched: number | null;
    computed_at: string;
  };
  caveats: string[];
  spec: unknown; // shown only in developer details
  // curated brief v2 (null / "absent" for a v1 brief)
  business_area: BusinessArea | null;
  summary: string | null; // null unless every number in it is a computed figure
  summary_status: "verified" | "unverified" | "absent";
  interpretation: ClaimText | null; // always an inference; null unless computed and every number checks
  interpretation_status?: "verified" | "unverified" | "absent"; // always sent; optional for older captures
  used_by:{ signals: string[]; opportunities: string[] };
}
export interface MetricRef {
  analysis_id: string;
  label: string;
  value: number | null;
  display: string | null;
  unit: AnalysisUnit;
  denominator_label: string | null;
  derived: null | { op: "diff" | "pct_change"; of: string[] };
}
export type ItemIntegrity = "verified" | "partial" | "unverified";
export type ClaimType = "observed" | "derived" | "inference" | "hypothesis" | "forecast";
export interface ClaimText {
  text: string;
  claim_type: ClaimType;
}
export interface Related {
  analyses: string[];
  opportunities: string[];
  signals: string[];
}
export type BusinessArea =
  | "Customer friction"
  | "Willingness to pay"
  | "Customer satisfaction"
  | "Product performance"
  | "Channels and growth";
export type SignalKind =
  | "emerging_signal"
  | "risk_blocker"
  | "competitor_finding"
  | "optimization"
  | "future_outlook";
export type SignalStatus = "strong_evidence" | "emerging" | "mixed_evidence" | "needs_validation";
export interface OpportunityRisk {
  text: string;
  claim_type: ClaimType;
  evidence: EvidenceRef[];
  integrity: ItemIntegrity;
}
export interface Signal {
  id: string;
  category: string;
  title: string;
  statement: string;
  integrity: ItemIntegrity;
  evidence: EvidenceRef[];
  metrics: MetricRef[];
  caveats: string[];
  // curated brief v2 (null / empty for a v1 brief)
  kind: SignalKind | null;
  status: SignalStatus | null;
  claim_type: ClaimType | null; // of `statement`
  implication: ClaimText | null;
  gaps: string[];
  related: Related;
  support_count: number; // verified supporting references
  contradiction_count: number; // verified contradicting references
}
export type OpportunityStatus = "supported" | "mixed_evidence" | "emerging" | "needs_research";
export interface Opportunity {
  id: string;
  title: string;
  status: OpportunityStatus;
  status_rationale: string;
  thesis: string;
  supporting: EvidenceRef[];
  contradicting: EvidenceRef[];
  metrics: MetricRef[];
  gaps: string[];
  next_step: string;
  caveats: string[];
  integrity: ItemIntegrity; // includes risk evidence
  // curated brief v2 (null / empty for a v1 brief)
  thesis_claim_type: ClaimType | null;
  why_it_matters: ClaimText | null;
  risks: OpportunityRisk[];
  next_investigation: string | null;
  related: Related;
  support_count: number;
  contradiction_count: number;
}
// E9 GET /api/workspaces/{ws}/insights
export interface InsightsBrief {
  fixture_version: string | null; // null: no brief for this workspace
  label: "Curated analyst brief";
  computed_at: string;
  corpus_check: { status: "ok" | "drift"; drifted_sources: string[] };
  signals: Signal[];
  opportunities: Opportunity[];
}
// E8 GET /api/workspaces/{ws}/analytics/analyses, /analyses/{id}
export interface AnalysesResponse {
  fixture_version: string | null;
  computed_at: string;
  analyses: Analysis[];
}

// ── E10 telemetry ───────────────────────────────────────────────────────────────────────────
// shared query: since, until, mode, include_test_runs=false
export interface Pct {
  p50: number | null;
  p95: number | null;
  n: number;
}
/** Cost is never persisted: it is estimated from persisted token usage at the configured
 * list prices (USD per million tokens) and always labelled as an estimate in the UI. */
export interface CostEstimate {
  total_usd: number | null;
  per_run_usd: number | null;
  n_runs_with_usage: number;
  prices_per_mtok: { input: number; output: number; cache_write: number; cache_read: number };
  basis: "list_prices_from_persisted_usage";
}
export type StageKey = "retrieval" | "agent" | "pack" | "synthesis" | "verification" | "first_token";
export interface TelemetrySummary {
  window: { since: string | null; until: string | null };
  runs: {
    total: number;
    by_mode: Record<string, number>;
    by_status: Record<string, number>;
    by_termination_state: Record<string, number>;
  };
  latency_ms: { total_by_mode: Record<string, Pct>; stages: Record<StageKey, Pct> };
  tokens: {
    input: number;
    output: number;
    cache_read: number;
    cache_write: number;
    per_run_mean: { input: number | null; output: number | null };
    by_source: { synthesis: Record<string, number>; agent: Record<string, number> };
  };
  model_calls: { total: number; per_run_mean: number | null; n_runs_missing: number };
  tool_calls: {
    total: number;
    per_run_mean: number | null;
    by_tool: {
      tool: string;
      n: number;
      ok: number;
      truncated: number;
      error: number;
      denied: number;
      timeout: number;
      p50_ms: number | null;
      p95_ms: number | null;
    }[];
  };
  cost: CostEstimate;
  rates: {
    regeneration: number;
    verification_fallback: number;
    planner_fallback: number;
    degraded: number;
  }; // fraction of runs.total
  flags: { code: string; n: number }[];
  route_reasons: { reason: string; n: number }[];
  verification: {
    dispositions: { disposition: Disposition; attempt: number; n: number }[];
    failure_categories: { category: string; n: number }[];
  };
  retrieval: {
    n: number;
    timings: Record<
      "embed_ms" | "lexical_prep_ms" | "lexical_ms" | "dense_ms" | "fusion_ms" | "total_ms",
      Pct
    >;
    candidates: { lexical: Pct; dense: Pct; fused: Pct; final: Pct };
    embedding_cache_hit_rate: number | null;
  };
  governance: {
    tool_status: Record<string, number>;
    redacted_tool_args: number;
    redacted_messages: number;
  };
  coverage: { runs_with_route: number; runs_with_agent: number; runs_with_verification: number };
  test_runs_excluded: number;
}
// GET /telemetry/runs ?mode&status&termination_state&degraded&model&disposition&since&until
//                     &include_test_runs&limit<=100&cursor
export interface TelemetryRunRow {
  id: string;
  conversation_id: string | null;
  created_at: string;
  question: string;
  mode: string;
  status: string;
  termination_state: string | null;
  flags: string[];
  route_reason: string | null;
  task_type: string | null;
  model: string | null;
  total_ms: number | null;
  tool_calls: number;
  model_calls: number | null;
  tokens_in: number;
  tokens_out: number;
  est_cost_usd: number | null;
  evidence_count: number; // pack size
  cited_count: number;
  verification_disposition: Disposition | null;
  regenerated: boolean;
  result_count: number;
}
export type TimelineKind =
  | "run_started"
  | "status"
  | "tool_started"
  | "tool_completed"
  | "evidence"
  | "draft_reset"
  | "warning"
  | "final"
  | "error"
  | "done"
  | "tokens";
export interface TimelineEntry {
  t_ms: number;
  kind: TimelineKind;
  label: string;
  detail: Record<string, unknown> | null; // never answer content
}
export interface TelemetryToolCall {
  step: number;
  call_index: number;
  tool: string;
  status: string;
  error_code: string | null;
  result_count: number | null;
  total_matches: number | null;
  truncated: boolean;
  warnings: string[];
  duration_ms: number | null;
  transport: string;
  args: unknown;
  redacted: boolean;
}
export interface TelemetryRunDetail {
  run: TelemetryRunRow & {
    timings: Record<string, number>;
    usage: Record<string, number>;
    route: RunRecord["route"];
    models: Record<string, string>;
  };
  agent: (Omit<NonNullable<RunRecord["agent"]>, "trace"> & { states: string[] }) | null;
  timeline: TimelineEntry[];
  tools: TelemetryToolCall[];
  verification: VerificationAttemptSummary[];
  retrieval: null | {
    timings: Record<string, number>;
    lanes: { lexical: number; dense: number; fused: number; final: number };
    embedding_cache_hit: boolean | null;
    active_versions: number;
    top_final: {
      rank: number;
      handle: string;
      source: string;
      lanes: Record<string, number | null>;
      rrf: number;
    }[];
  };
  analytics_result_ids: string[];
}

// ── E11 evaluation catalog (dev only) ───────────────────────────────────────────────────────
export type MetricUnit = "ratio" | "percent" | "ms" | "s" | "usd" | "count" | "tokens";
export type EvalSource =
  | { kind: "json"; path: string; pointer: string }
  | { kind: "report_md"; path: string; anchor: string };
export interface EvalMetric {
  id: string;
  label: string;
  value: number | null;
  unit: MetricUnit;
  ci_low?: number;
  ci_high?: number;
  n?: number;
  k?: number;
  source: EvalSource;
}
export interface EvalProvenance {
  path: string;
  git: string | null;
  at: string | null;
  model: string | null;
  split: string | null;
  config_hash: string | null;
  dataset: { name: string; version: string | null; sha256: string | null };
}
export type EvalRunId =
  | "p2-dev-final"
  | "p2-test-c3"
  | "p3-grounded-live"
  | "p4-research-dev"
  | "p4-research-test"
  | "p5-analytics-dev"
  | "p5-analytics-holdout";
export interface EvalCatalog {
  schema_version: 1;
  built_at: string;
  sources: { path: string; sha256: string; bytes: number }[];
  caveats: { id: string; text: string; applies_to: string[] }[];
  overview: { headline: EvalMetric[]; phases: { id: string; title: string; summary: string }[] };
  retrieval: {
    runs: {
      run_id: EvalRunId;
      label: string;
      provenance: EvalProvenance;
      n: number;
      n_eligible: number;
      arms: {
        arm: string;
        label: string;
        is_default: boolean;
        all: Record<string, EvalMetric>;
        eligible: Record<string, EvalMetric>;
        latency_ms: { p50: number; p95: number };
      }[];
    }[];
    comparisons: {
      run_id: EvalRunId;
      a: string;
      b: string;
      n: number;
      metrics: EvalMetric[];
      hit_at_10: { gains: number; losses: number; p: number | null };
    }[];
    decisions: {
      id: string;
      title: string;
      outcome: "adopted" | "rejected" | "not_adopted";
      text: string;
      metrics: EvalMetric[];
      source: EvalSource;
    }[];
  };
  grounded: {
    provenance: EvalProvenance;
    hard_gates: { id: string; label: string; k: number; n: number; pass: boolean; source: EvalSource }[];
    metrics: EvalMetric[];
    by_category: { category: string; metrics: EvalMetric[] }[];
    verifier: { split: "dev" | "holdout"; before: EvalMetric[]; after: EvalMetric[] }[];
  };
  research_tradeoff: {
    split: "dev" | "test";
    provenance: EvalProvenance;
    n_pairs: number;
    rows: {
      id: string;
      label: string;
      standard: EvalMetric;
      research: EvalMetric;
      delta: EvalMetric | null;
    }[];
  }[];
  analytics: { split: "dev" | "holdout"; provenance: EvalProvenance; metrics: EvalMetric[] }[];
  superseded: { path: string; label: string; reason: string }[];
  failure_runs: {
    run_id: EvalRunId;
    label: string;
    item_count: number;
    bucket_field: string;
    buckets: { id: string; label: string; n: number }[];
  }[];
}
// GET /api/dev/eval/runs/{run_id}/items ?offset&limit<=50&bucket
export interface EvalItemsPage {
  run_id: EvalRunId;
  total: number;
  items: EvalItem[];
}
export type EvalItem =
  | {
      phase: "retrieval";
      item_id: string;
      question: string;
      category: string;
      bucket: string | null;
      expected_handles: string[];
      by_arm: Record<string, { fact_ranks: (number | null)[]; hit_at_10: boolean; top: string[] }>;
    }
  | {
      phase: "grounded";
      item_id: string;
      question: string;
      category: string;
      answer_markdown: string;
      cited_handles: string[];
      gold_handles: string[];
      checks: Record<string, number | boolean | null>;
      termination_state: string;
      failure: null | { final_classification: string; root_cause: string; user_impact: string };
    }
  | {
      phase: "research";
      item_id: string;
      question: string;
      delta: Record<string, number | null>;
      standard: { answer_markdown: string; metrics: Record<string, number | null> };
      research: {
        answer_markdown: string;
        stop_reason: string;
        tool_calls: number;
        trace: { step: number; tool: string; status: string }[];
        metrics: Record<string, number | null>;
      };
    }
  | {
      phase: "analytics";
      item_id: string;
      question: string;
      task_type: string;
      routed_task_type: string | null;
      task_type_correct: boolean;
      values_matched: boolean | null;
      exact_result_accuracy: number | null;
      answer_markdown: string;
      gold_values: unknown;
      computed: unknown;
    };

/** Error codes used by the new endpoints (inside the existing error envelope). */
export const PRODUCT_ERROR_CODES = [
  "CONVERSATION_NOT_FOUND",
  "RUN_NOT_FOUND",
  "DATASET_NOT_FOUND",
  "ANALYSIS_NOT_FOUND",
  "EVAL_RUN_NOT_FOUND",
  "EVAL_CATALOG_UNAVAILABLE",
  "VALIDATION_ERROR",
  "PROVIDER_UNAVAILABLE",
] as const;

// ============================================================================================
// E12 server log + telemetry series (developer tools; dev-only, not mounted in prod)
// ============================================================================================

export type ServerLogLevel = "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
export type ServerLogKind =
  | "http"
  | "run"
  | "tool"
  | "verification"
  | "ingestion"
  | "analytics"
  | "app";
export type ServerLogStatusClass = "2xx" | "3xx" | "4xx" | "5xx";

/** HTTP access details of an `http.request` entry: route *template*, path without query. */
export interface ServerLogHttp {
  method: string;
  route: string | null; // e.g. "/api/workspaces/{ws}/runs/{run_id}"; null when unmatched
  path: string; // raw path, never the query string
  status: number | null;
  duration_ms: number | null; // SSE streams: the stream's lifetime
}

/** One sanitized log event. `fields` holds scalars only (ids, enums, counts, durations): never
 * questions, answers, passages, tool arguments, prompts, headers or credentials.
 * `fields.noise === true` marks health/metrics/log-polling requests (hidden by default). */
export interface ServerLogEntry {
  seq: number;
  ts: string;
  level: ServerLogLevel;
  logger: string | null;
  event: string;
  kind: ServerLogKind;
  request_id: string | null;
  run_id: string | null;
  workspace: string | null;
  http: ServerLogHttp | null;
  fields: Record<string, string | number | boolean | null>;
}

// GET /api/dev/logs ?level(minimum)&kind&method&status_class&route&q&include_noise&after_seq
//                   &limit(1..500, default 200)
export interface ServerLogParams {
  level?: ServerLogLevel;
  kind?: ServerLogKind;
  method?: string;
  status_class?: ServerLogStatusClass;
  route?: string;
  q?: string;
  include_noise?: boolean;
  /** Incremental polling: entries with seq > after_seq, ascending. Omitted: newest first. */
  after_seq?: number;
  limit?: number;
}

/** In-memory ring buffer of the API process only (the ingestion worker logs elsewhere).
 * `dropped` counts evicted entries; `levels` counts entries matching every filter but `level`. */
export interface ServerLogResponse {
  entries: ServerLogEntry[];
  capacity: number;
  size: number;
  dropped: number;
  capture_errors: number;
  oldest_seq: number | null;
  latest_seq: number | null;
  process_started_at: string;
  scope: "api_process";
  routes: string[];
  levels: Record<ServerLogLevel, number>;
}

// GET /api/workspaces/{ws}/telemetry/series ?since&until&mode&include_test_runs&limit<=2000
/** One run as a chart point. Anything not recorded is null, never zero. */
export interface TelemetrySeriesPoint {
  id: string;
  created_at: string;
  mode: string;
  status: string;
  termination_state: string | null;
  degraded: boolean;
  total_ms: number | null;
  stages: Record<StageKey, number | null>;
  tokens_in: number | null;
  tokens_out: number | null;
  est_cost_usd: number | null; // estimate from persisted usage at list prices
  model_calls: number | null;
  tool_calls: number;
  evidence_count: number;
  cited_count: number;
  disposition: Disposition | null;
  regenerated: boolean;
}

/** Oldest first; when more runs match than `limit`, the most recent are kept (`truncated`). */
export interface TelemetrySeries {
  window: { since: string | null; until: string | null };
  points: TelemetrySeriesPoint[];
  n: number;
  truncated: boolean;
  test_runs_excluded: number;
}

/** Additive summary fields (E12). Optional in the type so older payloads still fit. */
export interface TelemetryOutcomeRates {
  success: number; // fraction of runs.total with status "completed"
  failed: number;
  cancelled: number;
}
export type TelemetrySummaryWithOutcomes = TelemetrySummary & {
  rates: TelemetrySummary["rates"] & Partial<TelemetryOutcomeRates>;
  errors?: { error_class: string | null; n: number }[]; // failed runs by error class
  evidence_pack?: { size: Pct; cited: Pct }; // pack size and cited handles per run
};

// ============================================================================================
// E13 RAGAS (developer tools; additive `ragas` section of GET /api/dev/eval/catalog)
// Model-free heuristics computed on persisted outputs. Every computed summary carries a JSON
// pointer into its results.json; not-run metrics carry no numbers.
// ============================================================================================
export type RagasRunId = "ragas-p3-live-v0" | "ragas-p4-research-test";
export type RagasMetricFamily = "ragas_non_llm" | "ragas_llm_judge";
export type RagasNotRunReason = "model_credits_unavailable" | "no_reference_answers";
export interface RagasMetricDefinition {
  key: string;
  label: string;
  family: RagasMetricFamily;
  needs_llm: boolean;
  needs_reference_answer: boolean;
  what_it_measures: string;
  ragas_class: string;
}
export interface RagasSummary {
  mean: number;
  median: number;
  p25: number;
  p75: number;
  min: number;
  max: number;
  n: number; // scored samples with a defined value
  n_nan: number; // samples where the metric is undefined (e.g. nothing cited)
  histogram: { lo: number; hi: number; n: number }[];
}
export type RagasMetricResult =
  | {
      key: string;
      status: "computed";
      summary: RagasSummary;
      not_run_reason: null;
      source: { kind: "json"; path: string; pointer: string };
    }
  | {
      key: string;
      status: "not_run";
      summary: null;
      not_run_reason: RagasNotRunReason;
      source: { kind: "json"; path: string; pointer: string };
    };
export interface RagasConfiguration {
  name: string; // "standard" | "research"; also the items `bucket` filter
  n_samples: number;
  n_excluded: number;
  excluded_reasons: { reason: string; n: number }[];
  metrics: RagasMetricResult[];
}
export interface RagasRun {
  id: RagasRunId;
  title: string;
  source_run: EvalRunId; // the catalog run whose persisted outputs were scored
  dataset: { name: string; version: string | null; sha256: string | null };
  split: string | null;
  configurations: RagasConfiguration[];
  created_at: string;
}
export interface RagasCaveat {
  id: string;
  applies_to: RagasRunId[];
  text: string;
  metrics: EvalMetric[]; // e.g. RAGAS ID recall beside the historical per-fact recall
  source: EvalSource;
}
export interface RagasSection {
  ragas_version: string;
  telemetry_disabled: boolean;
  definitions: RagasMetricDefinition[];
  runs: RagasRun[];
  caveats: RagasCaveat[];
}
// Declaration merge: optional so catalogs built before E13 still fit.
export interface EvalCatalog {
  ragas?: RagasSection;
}
// GET /api/dev/eval/runs/{RagasRunId}/items ?offset&limit<=50&bucket=<configuration name>
export interface RagasItem {
  phase: "ragas";
  item_id: string;
  configuration: string;
  category: string;
  question: string;
  scores: Record<string, number | null>; // null: undefined for this sample
}
export interface RagasItemsPage {
  run_id: RagasRunId;
  total: number;
  items: RagasItem[];
}

// E14 decks (business route)
// POST /api/workspaces/{ws}/decks/preview -> DeckPreviewResponse
// POST /api/workspaces/{ws}/decks/pptx    -> .pptx binary (Content-Disposition: attachment)
// Errors: 422 VALIDATION_ERROR (empty selection, extra fields, limits),
//         422 DECK_ITEMS_NOT_FOUND (`unknown: string[]`), 422 DECK_EMPTY (pptx only; `excluded`).
/** At least one id; ≤ 30 signals, ≤ 10 opportunities, ≤ 10 analyses; title ≤ 120, question ≤ 300. */
export interface DeckRequest {
  title?: string;
  question?: string;
  signal_ids?: string[];
  opportunity_ids?: string[];
  analysis_ids?: string[];
}
export type DeckSlideKind =
  | "title"
  | "summary"
  | "customer_findings"
  | "quantitative"
  | "market_findings"
  | "opportunity"
  | "risks"
  | "next_steps"
  | "appendix";
/** `label` is the visible claim tag ("Inference" | "Hypothesis" | "Forecast"); null for facts. */
export interface DeckBullet {
  heading: string | null;
  text: string;
  claim_type: ClaimType | null;
  label: string | null;
  cites: number[]; // DeckSource.n
  level: 0 | 1;
}
export interface DeckStatusRow {
  title: string;
  kind_label: string;
  status: string | null;
  status_label: string | null;
  claim_type: ClaimType | null;
  label: string | null;
  cites: number[];
}
export interface DeckMetric {
  label: string;
  display: string;
  base: string | null;
  cites: number[];
}
export interface DeckSourceItem {
  n: number;
  source_title: string;
  locator: string;
  quote: string | null;
}
export type DeckBlock =
  | { type: "bullets"; items: DeckBullet[] }
  | { type: "statuses"; items: DeckStatusRow[] }
  | { type: "metrics"; items: DeckMetric[] }
  | { type: "sources"; items: DeckSourceItem[] }
  | {
      type: "chart";
      chart: "bar";
      title: string;
      unit: AnalysisUnit | null;
      categories: string[];
      values: number[];
      displays: string[];
      emphasis: number; // index of the accent bar
      base: string | null;
      cites: number[];
    }
  | {
      type: "table";
      title: string;
      columns: string[];
      rows: string[][];
      truncated: boolean;
      note: string | null;
      base: string | null;
      cites: number[];
    };
/** Speaker-note entry; `handle` is for audit only and never shown on a slide. */
export interface DeckNote {
  n: number;
  source_title: string;
  locator: string;
  quote: string | null;
  handle: string;
}
export interface DeckSlide {
  index: number;
  kind: DeckSlideKind;
  title: string;
  subtitle: string | null;
  meta?: string[]; // title slide only
  blocks: DeckBlock[];
  notes: DeckNote[];
}
export interface DeckSource extends DeckNote {
  kind: "passage" | "analysis";
}
export interface DeckExclusion {
  id: string;
  reason: string;
}
export interface Deck {
  title: string;
  question: string | null;
  workspace: { code: string; name: string };
  generated_at: string;
  fixture_version: string | null;
  slides: DeckSlide[];
  sources: DeckSource[];
  excluded: DeckExclusion[];
  counts: { items: number; sources: number; slides: number };
}
export interface DeckPreviewResponse {
  deck: Deck;
}
