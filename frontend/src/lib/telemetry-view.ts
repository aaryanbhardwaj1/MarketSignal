/**
 * Pure view helpers for the Telemetry developer pages: window ranges, URL filter state,
 * stage-timing segments, rate formatting and the observable run timeline. Everything here
 * derives from persisted telemetry fields; a value that was not recorded stays absent (never 0).
 */
import type {
  Disposition,
  StageKey,
  TelemetryRunRow,
  TelemetryToolCall,
  TimelineEntry,
} from "@/lib/api/contracts";
import type { TelemetryRunFilters, TelemetrySummaryFilters } from "@/lib/api/hooks/telemetry";
import { formatCount, formatPercent } from "@/lib/format";
import { degradationFlag } from "@/lib/labels";

// ── window + filters (URL state) ─────────────────────────────────────────────────────────────

export type TelemetryWindow = "all" | "7d" | "30d";

export const WINDOW_OPTIONS: { value: TelemetryWindow; label: string }[] = [
  { value: "all", label: "All time" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
];

const WINDOW_DAYS: Record<Exclude<TelemetryWindow, "all">, number> = { "7d": 7, "30d": 30 };
const MINUTE_MS = 60_000;
const DAY_MS = 24 * 60 * MINUTE_MS;

/**
 * ISO lower bound for a window, floored to the minute so the query key stays stable across
 * renders within that minute. `all` has no bound.
 */
export function windowSince(window: TelemetryWindow, now: Date = new Date()): string | undefined {
  if (window === "all") return undefined;
  const start = now.getTime() - WINDOW_DAYS[window] * DAY_MS;
  return new Date(Math.floor(start / MINUTE_MS) * MINUTE_MS).toISOString();
}

export interface TelemetryViewState {
  window: TelemetryWindow;
  includeTestRuns: boolean;
  mode: "" | "standard" | "research";
  /** `""`, `status:<code>` or `term:<code>`. */
  outcome: string;
  degraded: "" | "yes" | "no";
  disposition: "" | Disposition;
}

export const DEFAULT_VIEW: TelemetryViewState = {
  window: "all",
  includeTestRuns: false,
  mode: "",
  outcome: "",
  degraded: "",
  disposition: "",
};

const DISPOSITIONS: readonly Disposition[] = ["accepted", "repaired", "regenerate", "rejected", "fallback"];

type ParamReader = { get(name: string): string | null };

export function parseViewState(params: ParamReader): TelemetryViewState {
  const window = params.get("window");
  const mode = params.get("mode");
  const degraded = params.get("degraded");
  const disposition = params.get("disposition");
  const outcome = params.get("outcome") ?? "";
  return {
    window: window === "7d" || window === "30d" ? window : "all",
    includeTestRuns: params.get("test") === "1",
    mode: mode === "standard" || mode === "research" ? mode : "",
    outcome: /^(status|term):[a-z_]+$/.test(outcome) ? outcome : "",
    degraded: degraded === "yes" || degraded === "no" ? degraded : "",
    disposition: DISPOSITIONS.includes(disposition as Disposition) ? (disposition as Disposition) : "",
  };
}

/** Query string for the view state; defaults are omitted so the bare URL is the default view. */
export function serializeViewState(state: TelemetryViewState): string {
  const params = new URLSearchParams();
  if (state.window !== "all") params.set("window", state.window);
  if (state.includeTestRuns) params.set("test", "1");
  if (state.mode) params.set("mode", state.mode);
  if (state.outcome) params.set("outcome", state.outcome);
  if (state.degraded) params.set("degraded", state.degraded);
  if (state.disposition) params.set("disposition", state.disposition);
  return params.toString();
}

export function summaryFilters(state: TelemetryViewState, since: string | undefined): TelemetrySummaryFilters {
  return { since, include_test_runs: state.includeTestRuns };
}

export function runFilters(state: TelemetryViewState, since: string | undefined): TelemetryRunFilters {
  const [kind, code] = state.outcome ? state.outcome.split(":") : [null, null];
  return {
    since,
    include_test_runs: state.includeTestRuns,
    mode: state.mode || undefined,
    status: kind === "status" ? (code ?? undefined) : undefined,
    termination_state: kind === "term" ? (code ?? undefined) : undefined,
    degraded: state.degraded === "" ? undefined : state.degraded === "yes",
    disposition: state.disposition || undefined,
    limit: 25,
  };
}

// ── small formatters ─────────────────────────────────────────────────────────────────────────

/** First 8 characters of a UUID (the form used across the console). */
export function shortId(id: string): string {
  return id.slice(0, 8);
}

/** "6.9% of 407 runs": a rate always shown with its denominator. */
export function formatRate(fraction: number | null | undefined, total: number, noun = "runs"): string {
  if (total <= 0 || fraction == null || !Number.isFinite(fraction)) return `No ${noun} in window`;
  return `${formatPercent(fraction)} of ${total.toLocaleString("en-US")} ${noun}`;
}

/** "289 of 407": count with its denominator. */
export function ofTotal(n: number, total: number): string {
  return `${n.toLocaleString("en-US")} of ${total.toLocaleString("en-US")}`;
}

export function sumValues(record: Record<string, number> | undefined, keys?: readonly string[]): number {
  if (!record) return 0;
  return Object.entries(record).reduce((acc, [k, v]) => (!keys || keys.includes(k) ? acc + v : acc), 0);
}

// ── stage latency rows (summary) ─────────────────────────────────────────────────────────────

export const STAGE_ROWS: { key: StageKey; label: string; note: string }[] = [
  { key: "retrieval", label: "Retrieval", note: "Hybrid search before synthesis (standard runs and research fallbacks)" },
  { key: "agent", label: "Research steps", note: "Research agent planning and tool calls (research runs)" },
  { key: "pack", label: "Evidence pack", note: "Selecting and budgeting passages for synthesis" },
  { key: "synthesis", label: "Synthesis", note: "Answer generation, first attempt" },
  { key: "verification", label: "Verification", note: "Citation and number checks, first attempt" },
  { key: "first_token", label: "First token", note: "Measured from the start of synthesis, not the run" },
];

// ── stage timing segments (run detail) ───────────────────────────────────────────────────────

export interface StageSegment {
  key: string;
  label: string;
  ms: number;
  /** Share of the bar (0..100). */
  pct: number;
}

interface StageDef {
  key: string;
  label: string;
}

function stageDefs(mode: string, timings: Record<string, number>): StageDef[] {
  const attempts = Object.keys(timings)
    .map((k) => /^synthesis_ms_(\d+)$/.exec(k)?.[1])
    .filter((v): v is string => Boolean(v))
    .map(Number)
    .sort((a, b) => a - b);
  const multi = attempts.length > 1;
  const gen = attempts.flatMap((n) => [
    { key: `synthesis_ms_${n}`, label: multi ? `Synthesis (attempt ${n})` : "Synthesis" },
    { key: `verify_ms_${n}`, label: multi ? `Verification (attempt ${n})` : "Verification" },
  ]);
  const front =
    mode === "research"
      ? [
          { key: "agent_ms", label: "Research steps" },
          { key: "retrieval_ms", label: "Retrieval" },
        ]
      : [
          { key: "retrieval_ms", label: "Retrieval" },
          { key: "agent_ms", label: "Research steps" },
        ];
  return [...front, { key: "pack_ms", label: "Evidence pack" }, ...gen];
}

function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v) && v >= 0;
}

/**
 * Sequential stage segments for one run. Stages that were not recorded are omitted (never
 * zero-filled). Any recorded total beyond the stage sum becomes an "Other (unattributed)"
 * segment; widths are shares of max(total, sum), so they never exceed 100%.
 */
export function stageSegments(mode: string, timings: Record<string, number>): StageSegment[] {
  const parts = stageDefs(mode, timings)
    .filter((d) => isNum(timings[d.key]))
    .map((d) => ({ key: d.key, label: d.label, ms: timings[d.key] }));
  const sum = parts.reduce((acc, p) => acc + p.ms, 0);
  const total = isNum(timings.total_ms) ? timings.total_ms : null;
  const rest = total != null && total - sum >= 1 ? total - sum : 0;
  const all = rest > 0 ? [...parts, { key: "other", label: "Other (unattributed)", ms: rest }] : parts;
  const denom = Math.max(total ?? 0, sum);
  return all.map((p) => ({ ...p, pct: denom > 0 ? (p.ms / denom) * 100 : 0 }));
}

// ── observable timeline (run detail) ─────────────────────────────────────────────────────────

export type TimelineStepKind =
  | "start"
  | "mode"
  | "phase"
  | "retrieval"
  | "tool"
  | "analytics"
  | "evidence"
  | "synthesis"
  | "draft_reset"
  | "verification"
  | "final"
  | "warning"
  | "error"
  | "done";

export interface TimelineStep {
  id: string;
  t_ms: number;
  end_ms: number | null;
  /** Recorded duration (tool calls) or span (streaming); null when not recorded. */
  duration_ms: number | null;
  kind: TimelineStepKind;
  title: string;
  detail: string | null;
  tool: string | null;
  status: string | null;
}

const ANALYTICS_TOOLS = new Set(["aggregate", "filter_rows", "group_compare"]);

const PHASE_TITLES: Record<string, { title: string; kind: TimelineStepKind }> = {
  planning: { title: "Research planning started", kind: "phase" },
  searching: { title: "Evidence search started", kind: "phase" },
  analyzing: { title: "Evidence pack assembly started", kind: "phase" },
  synthesizing: { title: "Synthesis started", kind: "synthesis" },
  verifying: { title: "Verification started", kind: "verification" },
};

const str = (v: unknown): string | null => (typeof v === "string" && v ? v : null);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

function toolKey(d: Record<string, unknown>): string {
  return `${num(d.step) ?? "?"}:${num(d.call_index) ?? "-"}:${str(d.tool) ?? "?"}`;
}

function toolStep(
  start: TimelineEntry,
  end: TimelineEntry | undefined,
  index: number,
): TimelineStep {
  const d = start.detail ?? {};
  const e = end?.detail ?? {};
  const tool = str(d.tool);
  const step = num(d.step);
  // A search without a call index is the pipeline's own retrieval (standard runs, and research
  // runs that fell back when planning was unavailable), not a planned research step.
  const standardSearch = num(d.call_index) == null && (tool === "search_evidence" || tool == null);
  const kind: TimelineStepKind = standardSearch ? "retrieval" : tool && ANALYTICS_TOOLS.has(tool) ? "analytics" : "tool";
  const title = standardSearch
    ? "Retrieval performed"
    : kind === "analytics"
      ? `Analytics executed${step != null ? ` (step ${step})` : ""}`
      : `Research step ${step ?? "?"}: ${tool ?? "tool"} called`;
  const count = num(e.result_count);
  const parts = [start.label, count != null ? formatCount(count, "result") : null].filter(Boolean);
  return {
    id: `tool-${index}`,
    t_ms: start.t_ms,
    end_ms: end ? end.t_ms : null,
    duration_ms: num(e.duration_ms),
    kind,
    title,
    detail: parts.join(" · ") || null,
    tool,
    status: str(e.status),
  };
}

function simpleStep(entry: TimelineEntry, index: number, runMode: string): TimelineStep | null {
  const d = entry.detail ?? {};
  const base = { id: `${entry.kind}-${index}`, t_ms: entry.t_ms, end_ms: null, duration_ms: null, tool: null, status: null };
  switch (entry.kind) {
    case "run_started":
      return { ...base, kind: "start", title: "Run started", detail: str(d.persona) ? `Role: ${str(d.persona)}` : null };
    case "status": {
      const phase = str(d.phase);
      const hit = phase ? PHASE_TITLES[phase] : undefined;
      if (phase === "searching" && runMode === "research") {
        return { ...base, kind: "phase", title: "Research steps started", detail: null };
      }
      return { ...base, kind: hit?.kind ?? "phase", title: hit?.title ?? entry.label, detail: null };
    }
    case "evidence": {
      const items = num(d.item_count);
      const results = num(d.result_count);
      const detail = [items != null ? formatCount(items, "passage") : null, results ? formatCount(results, "computed result") : null]
        .filter(Boolean)
        .join(" · ");
      return { ...base, kind: "evidence", title: "Evidence pack created", detail: detail || null };
    }
    case "tokens": {
      const chunks = num(d.count);
      const cites = num(d.citations);
      const attempt = num(d.attempt);
      const detail = [
        chunks != null ? `${formatCount(chunks, "chunk")} streamed` : null,
        cites != null ? formatCount(cites, "citation marker") : null,
        attempt != null ? `attempt ${attempt}` : null,
      ]
        .filter(Boolean)
        .join(" · ");
      const last = num(d.last_t_ms);
      return { ...base, end_ms: last, duration_ms: last != null && last >= entry.t_ms ? last - entry.t_ms : null, kind: "synthesis", title: "Answer streamed", detail: detail || null };
    }
    case "draft_reset":
      return { ...base, kind: "draft_reset", title: "Draft discarded and rewritten", detail: str(d.reason) };
    case "final": {
      const cites = num(d.citations);
      return {
        ...base,
        kind: "final",
        title: "Final answer persisted",
        detail: cites != null ? `${formatCount(cites, "citation marker")} in the answer` : null,
      };
    }
    case "warning": {
      const code = str(d.code);
      const h = code ? degradationFlag(code) : null;
      return { ...base, kind: "warning", title: "Warning", detail: h?.known ? `${h.label} (${code})` : (code ?? entry.label) };
    }
    case "error":
      return { ...base, kind: "error", title: "Error", detail: str(d.code) ?? entry.label };
    case "done":
      return { ...base, kind: "done", title: "Run completed", detail: str(d.termination_state) };
    default:
      return null;
  }
}

/**
 * Observable timeline steps, in time order. Tool start/complete pairs merge into one step;
 * a "Mode selected" step is added at run start only when the run recorded its mode.
 */
export function buildTimeline(entries: TimelineEntry[], runMode: string): TimelineStep[] {
  const sorted = [...entries].sort((a, b) => a.t_ms - b.t_ms);
  const completions = new Map<string, TimelineEntry[]>();
  for (const e of sorted) {
    if (e.kind !== "tool_completed") continue;
    const key = toolKey(e.detail ?? {});
    completions.set(key, [...(completions.get(key) ?? []), e]);
  }
  const used = new Set<TimelineEntry>();
  const steps: TimelineStep[] = [];
  sorted.forEach((entry, i) => {
    if (entry.kind === "tool_started") {
      const queue = completions.get(toolKey(entry.detail ?? {})) ?? [];
      const end = queue.find((c) => !used.has(c) && c.t_ms >= entry.t_ms);
      if (end) used.add(end);
      steps.push(toolStep(entry, end, i));
      return;
    }
    if (entry.kind === "tool_completed") {
      if (!used.has(entry)) steps.push(toolStep(entry, entry, i));
      return;
    }
    const step = simpleStep(entry, i, runMode);
    if (!step) return;
    steps.push(step);
    const mode = entry.kind === "run_started" ? str(entry.detail?.mode) : null;
    if (mode) {
      steps.push({ id: `mode-${i}`, t_ms: entry.t_ms, end_ms: null, duration_ms: null, kind: "mode", title: "Mode selected", detail: mode, tool: null, status: null });
    }
  });
  return steps;
}

// ── tool calls ───────────────────────────────────────────────────────────────────────────────

export function toolStatusTone(status: string): "success" | "warn" | "danger" | "neutral" {
  if (status === "ok") return "success";
  if (status === "truncated") return "warn";
  if (status === "error" || status === "timeout" || status === "denied") return "danger";
  return "neutral";
}

/** Purge redaction marks args as `{"redacted": true}`; the API also sets `redacted`. */
export function isRedacted(call: Pick<TelemetryToolCall, "args" | "redacted">): boolean {
  if (call.redacted) return true;
  const args = call.args;
  return typeof args === "object" && args !== null && (args as Record<string, unknown>).redacted === true;
}

// ── run rows ─────────────────────────────────────────────────────────────────────────────────

/** Tokens for a run row ("5,254 in · 652 out"), or null when the run used no model tokens. */
export function rowTokens(row: Pick<TelemetryRunRow, "tokens_in" | "tokens_out">): string | null {
  if (row.tokens_in === 0 && row.tokens_out === 0) return null;
  return `${row.tokens_in.toLocaleString("en-US")} in · ${row.tokens_out.toLocaleString("en-US")} out`;
}

/** Token usage keys as persisted by the synthesis and agent usage records. */
export const USAGE_KEYS = {
  input: "input_tokens",
  output: "output_tokens",
  cacheRead: "cache_read_input_tokens",
  cacheWrite: "cache_creation_input_tokens",
  calls: "llm_attempts",
} as const;

/** Value of a usage key, or null when the run did not record it. */
export function usageValue(usage: Record<string, number> | null | undefined, key: string): number | null {
  const v = usage?.[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Share of the stage bar as text; tiny non-zero shares read "<0.1%" rather than "0.0%". */
export function formatShare(pct: number): string {
  if (pct > 0 && pct < 0.1) return "<0.1%";
  return `${pct.toFixed(1)}%`;
}

/** Offset from run start ("t+248 ms"); events logged just before the start marker read "t-2 ms". */
export function formatOffset(ms: number): string {
  const r = Math.round(ms);
  return `t${r < 0 ? "-" : "+"}${Math.abs(r).toLocaleString("en-US")} ms`;
}

/** "Step 1 · call 2": research step number with a 1-based call index within that step. */
export function toolStepLabel(call: Pick<TelemetryToolCall, "step" | "call_index">): string {
  return `Step ${call.step} · call ${call.call_index + 1}`;
}

/**
 * Result counts per tool call as reported on its `tool_completed` timeline event, keyed by
 * `step.call_index`. The audit row's `result_count` counts list results only (0 for analytics
 * tools), so the timeline count is the one the run detail shows in both places.
 */
export function timelineResultCounts(entries: TimelineEntry[]): Map<string, number> {
  const out = new Map<string, number>();
  for (const e of entries) {
    if (e.kind !== "tool_completed") continue;
    const d = e.detail ?? {};
    const step = num(d.step);
    const call = num(d.call_index);
    const count = num(d.result_count);
    if (step != null && call != null && count != null) out.set(`${step}.${call}`, count);
  }
  return out;
}

/** Result count for one tool call: the timeline's count, else the audit count, else null for analytics tools reporting 0. */
export function toolResultCount(call: Pick<TelemetryToolCall, "step" | "call_index" | "tool" | "result_count">, counts: Map<string, number>): number | null {
  const fromTimeline = counts.get(`${call.step}.${call.call_index}`);
  if (fromTimeline != null) return fromTimeline;
  if (call.result_count == null) return null;
  return ANALYTICS_TOOLS.has(call.tool) && call.result_count === 0 ? null : call.result_count;
}

/** Degradation flags a termination state already states, so the run list need not repeat them. */
const IMPLIED_FLAGS: Record<string, readonly string[]> = {
  generation_unavailable: ["LLM_SYNTHESIS_UNAVAILABLE", "PLANNER_UNAVAILABLE_FALLBACK", "AGENT_LLM_UNAVAILABLE"],
  no_relevant_evidence: ["EVIDENCE_EMPTY"],
  completed_with_limited_evidence: ["EVIDENCE_EMPTY"],
  retrieval_degraded: ["RETRIEVAL_LEXICAL_FALLBACK", "RETRIEVAL_DENSE_UNAVAILABLE", "RETRIEVAL_TIMEOUT"],
  timeout: ["RUN_TIMEOUT", "GATHER_TIMEOUT"],
  tool_failure: ["TOOL_CIRCUIT_OPEN"],
};

export interface OutcomeFlags {
  /** Flags the outcome label already implies (still listed in the outcome badge's tooltip). */
  implied: string[];
  /** Remaining flags, in recorded order. */
  extra: string[];
}

/** Split a run's flags into those its termination state implies and the rest. */
export function outcomeFlags(terminationState: string | null, flags: readonly string[]): OutcomeFlags {
  const implied = new Set(terminationState ? (IMPLIED_FLAGS[terminationState] ?? []) : []);
  return { implied: flags.filter((f) => implied.has(f)), extra: flags.filter((f) => !implied.has(f)) };
}

/** Plain label for a flag code, or the code itself when unknown (developer page). */
export function flagLabel(code: string): string {
  const h = degradationFlag(code);
  return h.known ? h.label : code;
}

/** Audited tool-call outcomes (governance audit `status`). Unknown codes fall back to the code. */
const TOOL_STATUS_LABELS: Record<string, string> = {
  ok: "Succeeded",
  truncated: "Truncated",
  error: "Error",
  denied: "Denied",
  timeout: "Timed out",
};

export function toolStatusLabel(status: string): string {
  return TOOL_STATUS_LABELS[status] ?? status;
}
