/**
 * Execution flow of one run, derived purely from its persisted telemetry (`TelemetryRunDetail`):
 * Request → Routing → Retrieval → Tool execution → Analytics → Evidence pack → Generation →
 * Verification → Final answer → Completed. Only stages with recorded evidence appear; nothing is
 * inferred or invented, and model reasoning is never part of the record.
 */

import type { TelemetryRunDetail, TimelineEntry } from "@/lib/api/contracts";
import { formatMs, formatNumber } from "@/lib/format";
import {
  degradationFlag,
  routeReason,
  runMode,
  stopReason,
  terminationState,
  verificationDisposition,
  verificationFailure,
  type Humanized,
} from "@/lib/labels";
import { timelineResultCounts, toolResultCount } from "@/lib/telemetry-view";

type Detail = TelemetryRunDetail;

export type FlowStageId =
  | "request"
  | "routing"
  | "retrieval"
  | "tools"
  | "analytics"
  | "evidence"
  | "generation"
  | "verification"
  | "final"
  | "completed";

export type FlowState = "done" | "degraded" | "failed";

export interface FlowMeta {
  label: string;
  value: string;
}

export interface FlowToolCall {
  key: string;
  step: number;
  tool: string;
  status: string;
  error_code: string | null;
  duration_ms: number | null;
  result_count: number | null;
  truncated: boolean;
  warnings: string[];
}

export interface FlowStage {
  id: FlowStageId;
  label: string;
  state: FlowState;
  /** Offset from run start (ms) when the timeline records it. */
  start_ms: number | null;
  duration_ms: number | null;
  summary: string;
  meta: FlowMeta[];
  calls?: FlowToolCall[];
  resultIds?: string[];
}

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const label = (h: Humanized): string => (h.known ? h.label : h.code);
const plural = (n: number, one: string, many = `${one}s`) => `${formatNumber(n)} ${n === 1 ? one : many}`;

function sumKeys(record: Record<string, number> | null | undefined, prefix: string): number | null {
  const values = Object.entries(record ?? {})
    .filter(([k, v]) => k.startsWith(prefix) && isNum(v))
    .map(([, v]) => v);
  return values.length ? values.reduce((a, b) => a + b, 0) : null;
}

const detailOf = (e: TimelineEntry): Record<string, unknown> => e.detail ?? {};

function phaseAt(timeline: readonly TimelineEntry[], phase: string): number | null {
  const hit = timeline.find((e) => e.kind === "status" && detailOf(e).phase === phase);
  return hit ? hit.t_ms : null;
}

function firstOf(timeline: readonly TimelineEntry[], kind: TimelineEntry["kind"]): TimelineEntry | null {
  return timeline.find((e) => e.kind === kind) ?? null;
}

const clampStart = (t: number | null): number | null => (t == null ? null : Math.max(0, t));

function toneState(tone: string | undefined): FlowState {
  if (tone === "danger") return "failed";
  if (tone === "warn") return "degraded";
  return "done";
}

const modeText = (code: string | null | undefined): string => (code ? label(runMode(code)) : "Not recorded");

function requestStage(d: Detail): FlowStage {
  const started = firstOf(d.timeline, "run_started");
  const persona = started ? detailOf(started).persona : undefined;
  const meta: FlowMeta[] = [{ label: "Requested mode", value: modeText(d.run.route?.requested ?? null) }];
  if (typeof persona === "string") meta.push({ label: "Role", value: persona });
  return {
    id: "request",
    label: "Request",
    state: "done",
    start_ms: clampStart(started?.t_ms ?? 0),
    duration_ms: null,
    summary: "Question received",
    meta,
  };
}

function routingStage(d: Detail): FlowStage | null {
  const r = d.run.route;
  if (!r || (!r.decided && !r.reason)) return null;
  const meta: FlowMeta[] = [
    { label: "Requested", value: modeText(r.requested) },
    { label: "Decided", value: modeText(r.decided) },
    { label: "Reason", value: r.reason ? label(routeReason(r.reason)) : "Not recorded" },
  ];
  if (r.cues && r.cues.length) meta.push({ label: "Cues", value: r.cues.join(", ") });
  if (r.task_type) meta.push({ label: "Task type", value: r.task_type });
  return {
    id: "routing",
    label: "Routing",
    state: "done",
    start_ms: null,
    duration_ms: null,
    summary: `${modeText(r.requested)} → ${modeText(r.decided)}`,
    meta,
  };
}

function retrievalStage(d: Detail): FlowStage | null {
  const r = d.retrieval;
  const ms = d.run.timings?.retrieval_ms;
  if (!r && !isNum(ms)) return null;
  const searchStart = d.timeline.find((e) => e.kind === "tool_started" && detailOf(e).tool === "search_evidence" && detailOf(e).call_index == null);
  const meta: FlowMeta[] = [];
  if (r) {
    meta.push(
      { label: "Candidates", value: `lexical ${formatNumber(r.lanes.lexical)} · dense ${formatNumber(r.lanes.dense)} · fused ${formatNumber(r.lanes.fused)}` },
      { label: "Kept", value: formatNumber(r.lanes.final) },
      { label: "Embedding cache", value: r.embedding_cache_hit == null ? "Not recorded" : r.embedding_cache_hit ? "Hit" : "Miss" },
    );
    const sub = (["embed_ms", "lexical_ms", "dense_ms", "fusion_ms"] as const)
      .filter((k) => isNum(r.timings[k]))
      .map((k) => `${k.replace("_ms", "")} ${formatMs(r.timings[k])}`);
    if (sub.length) meta.push({ label: "Sub-stages", value: sub.join(" · ") });
  }
  if (d.agent?.flags.includes("PLANNER_UNAVAILABLE_FALLBACK")) meta.push({ label: "Trigger", value: "Fallback search (research planning unavailable)" });
  return {
    id: "retrieval",
    label: "Retrieval",
    state: "done",
    start_ms: clampStart(searchStart?.t_ms ?? phaseAt(d.timeline, "searching")),
    duration_ms: isNum(ms) ? ms : (r?.timings.total_ms ?? null),
    summary: r ? `${formatNumber(r.lanes.final)} passages kept from hybrid search` : "Hybrid search ran (no lane trace recorded)",
    meta,
  };
}

function flowCalls(d: Detail): FlowToolCall[] {
  const counts = timelineResultCounts(d.timeline);
  return d.tools.map((t) => ({
    key: `${t.step}-${t.call_index}-${t.tool}`,
    step: t.step,
    tool: t.tool,
    status: t.status,
    error_code: t.error_code,
    duration_ms: t.duration_ms,
    result_count: toolResultCount(t, counts),
    truncated: t.truncated,
    warnings: t.warnings,
  }));
}

function toolsStage(d: Detail): FlowStage | null {
  const a = d.agent;
  if (!a && d.tools.length === 0) return null;
  const calls = flowCalls(d);
  const errors = a?.tool_errors ?? calls.filter((c) => c.error_code).length;
  const stop = a ? stopReason(a.stop_reason) : null;
  const state: FlowState = errors > 0 || (stop && stop.tone === "warn") ? "degraded" : stop?.tone === "danger" ? "failed" : "done";
  const meta: FlowMeta[] = [];
  if (a) {
    meta.push(
      { label: "Steps", value: formatNumber(a.steps) },
      { label: "Stop reason", value: stop ? label(stop) : "Not recorded" },
      { label: "Tool errors", value: formatNumber(errors) },
      { label: "Evidence pool", value: plural(a.pool_size, "passage") },
    );
  }
  const firstCall = firstOf(d.timeline, "tool_started");
  return {
    id: "tools",
    label: "Tool execution",
    state,
    start_ms: clampStart(phaseAt(d.timeline, "planning") ?? firstCall?.t_ms ?? null),
    duration_ms: a?.duration_ms ?? d.run.timings?.agent_ms ?? null,
    summary: `${plural(calls.length, "tool call")}${a ? ` in ${plural(a.steps, "step")}` : ""}${stop ? ` · ${label(stop).toLowerCase()}` : ""}`,
    meta,
    calls,
  };
}

function analyticsStage(d: Detail): FlowStage | null {
  const starts = d.timeline.filter((e) => e.kind === "tool_started" && detailOf(e).kind === "analytics");
  const ids = d.analytics_result_ids;
  if (starts.length === 0 && ids.length === 0) return null;
  const keys = new Set(starts.map((e) => `${detailOf(e).step}-${detailOf(e).call_index}`));
  const durations = d.tools.filter((t) => keys.has(`${t.step}-${t.call_index}`)).map((t) => t.duration_ms).filter(isNum);
  return {
    id: "analytics",
    label: "Analytics",
    state: "done",
    start_ms: clampStart(starts[0]?.t_ms ?? null),
    duration_ms: durations.length ? durations.reduce((a, b) => a + b, 0) : null,
    summary: `${plural(starts.length, "analytics call")} · ${plural(ids.length, "computed result")} used`,
    // duration_ms is the summed call time (calls may be spread across steps).
    meta: [
      { label: "Analytics calls", value: formatNumber(starts.length) },
      { label: "Computed results", value: formatNumber(ids.length) },
    ],
    resultIds: ids,
  };
}

function evidenceStage(d: Detail): FlowStage | null {
  const ev = firstOf(d.timeline, "evidence");
  const pack = d.run.timings?.pack_ms;
  if (!ev && !isNum(pack)) return null;
  const det = ev ? detailOf(ev) : {};
  const meta: FlowMeta[] = [
    { label: "Pack size", value: formatNumber(d.run.evidence_count) },
    { label: "Cited", value: formatNumber(d.run.cited_count) },
  ];
  if (d.run.result_count) meta.push({ label: "Computed results in pack", value: formatNumber(d.run.result_count) });
  if (Array.isArray(det.classes) && det.classes.length) meta.push({ label: "Source classes", value: det.classes.join(", ") });
  if (typeof det.truncated === "boolean") meta.push({ label: "Truncated", value: det.truncated ? "Yes" : "No" });
  return {
    id: "evidence",
    label: "Evidence pack",
    state: det.truncated === true ? "degraded" : "done",
    start_ms: clampStart(ev?.t_ms ?? phaseAt(d.timeline, "analyzing")),
    duration_ms: isNum(pack) ? pack : null,
    summary: `${plural(d.run.evidence_count, "item")} · ${formatNumber(d.run.cited_count)} cited`,
    meta,
  };
}

function generationStage(d: Detail): FlowStage | null {
  const { run } = d;
  const synth = sumKeys(run.timings, "synthesis_ms");
  const attempts = run.usage?.llm_attempts ?? run.timings?.attempts;
  const started = phaseAt(d.timeline, "synthesizing");
  if (synth == null && !isNum(attempts) && !run.model && started == null) return null;
  const failures = run.usage?.llm_failures;
  const unavailable = run.flags.includes("LLM_SYNTHESIS_UNAVAILABLE") || run.termination_state === "generation_unavailable";
  const model = run.model ?? run.models?.synthesis ?? null;
  const meta: FlowMeta[] = [
    { label: "Model", value: model ?? "Not recorded" },
    { label: "Attempts", value: isNum(attempts) ? formatNumber(attempts) : "Not recorded" },
  ];
  if (isNum(failures)) meta.push({ label: "Failed attempts", value: formatNumber(failures) });
  if (isNum(run.usage?.input_tokens) || isNum(run.usage?.output_tokens)) {
    meta.push({ label: "Tokens in / out", value: `${formatNumber(run.usage.input_tokens ?? 0)} / ${formatNumber(run.usage.output_tokens ?? 0)}` });
  }
  if (isNum(run.timings?.first_token_ms)) meta.push({ label: "First token", value: formatMs(run.timings.first_token_ms) });
  if (run.regenerated) meta.push({ label: "Regenerated", value: "Yes" });
  return {
    id: "generation",
    label: "Generation",
    state: unavailable ? "failed" : "done",
    start_ms: clampStart(started),
    duration_ms: synth,
    summary: unavailable ? "Live model unavailable; no answer text was generated" : `${model ?? "Model"} · ${plural(run.usage?.output_tokens ?? 0, "output token")}`,
    meta,
  };
}

function verificationStage(d: Detail): FlowStage | null {
  const v = d.verification;
  if (v.length === 0) return null;
  const last = v[v.length - 1];
  const disp = verificationDisposition(last.disposition);
  const repairs = v.reduce((n, a) => n + a.repairs_n, 0);
  return {
    id: "verification",
    label: "Verification",
    state: toneState(disp.tone),
    start_ms: clampStart(phaseAt(d.timeline, "verifying")),
    duration_ms: sumKeys(d.run.timings, "verify_ms"),
    summary: `${plural(v.length, "attempt")} · ${label(disp)} · ${plural(repairs, "repair")}`,
    meta: v.map((a) => ({
      label: `Attempt ${a.attempt}`,
      value: `${label(verificationDisposition(a.disposition))} · ${plural(a.repairs_n, "repair")} · ${plural(a.citations, "reference")} checked${a.failure_categories.length ? ` · ${a.failure_categories.map((c) => label(verificationFailure(c))).join(", ")}` : ""}`,
    })),
  };
}

function finalStage(d: Detail): FlowStage | null {
  const f = firstOf(d.timeline, "final");
  if (!f) return null;
  const det = detailOf(f);
  const meta: FlowMeta[] = [];
  if (isNum(det.citations)) meta.push({ label: "Citations", value: formatNumber(det.citations) });
  meta.push({ label: "Verification", value: det.passed === true ? "Passed" : det.passed === false ? "Did not pass" : "Not verified" });
  return {
    id: "final",
    label: "Final answer",
    state: det.passed === false ? "failed" : "done",
    start_ms: clampStart(f.t_ms),
    duration_ms: null,
    summary: isNum(det.citations) ? `Answer finalized with ${plural(det.citations, "citation")}` : "Answer finalized",
    meta,
  };
}

function completedStage(d: Detail): FlowStage | null {
  const done = firstOf(d.timeline, "done");
  const code = d.run.termination_state ?? (done ? (detailOf(done).termination_state as string | undefined) : undefined);
  if (!done && !code) return null;
  const term = terminationState(code);
  const meta: FlowMeta[] = [{ label: "Total time", value: formatMs(d.run.total_ms) }];
  if (d.run.flags.length) meta.push({ label: "Flags", value: d.run.flags.map((f) => label(degradationFlag(f))).join(", ") });
  return {
    id: "completed",
    label: "Completed",
    state: toneState(term.tone),
    start_ms: clampStart(done?.t_ms ?? d.run.total_ms),
    duration_ms: null,
    summary: code ? label(term) : "Done",
    meta,
  };
}

/** Ordered stages that actually occurred in this run. */
export function deriveRunFlow(detail: Detail): FlowStage[] {
  return [
    requestStage(detail),
    routingStage(detail),
    retrievalStage(detail),
    toolsStage(detail),
    analyticsStage(detail),
    evidenceStage(detail),
    generationStage(detail),
    verificationStage(detail),
    finalStage(detail),
    completedStage(detail),
  ].filter((s): s is FlowStage => s !== null);
}

/** Stages whose duration is a sum of separate calls, not one contiguous span. */
const SUMMED: ReadonlySet<FlowStageId> = new Set(["analytics"]);

/** Gantt rows: contiguous stages with both a recorded start and duration. */
export function flowGantt(stages: readonly FlowStage[]): { label: string; start: number; duration: number }[] {
  return stages
    .filter((s) => !SUMMED.has(s.id) && s.start_ms != null && s.duration_ms != null && s.duration_ms > 0)
    .map((s) => ({ label: s.label, start: s.start_ms as number, duration: s.duration_ms as number }));
}

export interface DegradedInfo {
  degraded: boolean;
  reasons: { code: string; label: string; description: string | null }[];
}

/** Why a run is degraded: its flags plus a non-completed termination state. */
export function degradedInfo(detail: Detail): DegradedInfo {
  const reasons: DegradedInfo["reasons"] = [];
  const term = detail.run.termination_state;
  if (term && term !== "completed") {
    const h = terminationState(term);
    reasons.push({ code: term, label: label(h), description: h.description ?? null });
  }
  for (const f of detail.run.flags) {
    const h = degradationFlag(f);
    reasons.push({ code: f, label: label(h), description: h.description ?? null });
  }
  return { degraded: reasons.length > 0, reasons };
}
