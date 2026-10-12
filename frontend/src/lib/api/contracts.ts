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
export interface Signal {
  id: string;
  category: string;
  title: string;
  statement: string;
  integrity: ItemIntegrity;
  evidence: EvidenceRef[];
  metrics: MetricRef[];
  caveats: string[];
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
  integrity: ItemIntegrity;
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
