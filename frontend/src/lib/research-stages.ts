/**
 * Observable research stages for a run: what the system did, never how the model reasoned.
 * Built from the live SSE reducer state (`liveStages`) or a persisted run record (`savedStages`).
 * A stage is listed only when it actually occurs, e.g. "Running analysis" only when a calculation
 * ran. Stages follow execution order: the answer is written first and its citations are then
 * checked, so "Preparing answer" precedes "Verifying sources".
 */
import type { StageState } from "@/components/motion/stage-progress";
import type { RunRecord } from "./api/contracts";
import { formatCount, formatMs } from "./format";
import { isCitationFallback, isModelUnavailable } from "./model-availability";
import type { RunStreamState, ToolStep } from "./run-stream";

export type ResearchStageId = "understand" | "search" | "analyze" | "compare" | "prepare" | "verify";

export const RESEARCH_STAGE_LABEL: Readonly<Record<ResearchStageId, string>> = {
  understand: "Understanding question",
  search: "Searching evidence",
  analyze: "Running analysis",
  compare: "Comparing findings",
  prepare: "Preparing answer",
  verify: "Verifying sources",
};

export interface ResearchStage {
  id: ResearchStageId;
  label: string;
  state: StageState;
  /** Measured duration; null when the run did not record one. */
  durationMs: number | null;
  /** One short plain-language line, e.g. "3 searches · 26 passages". */
  detail: string | null;
}

export type StageOutcome = "completed" | "failed" | "cancelled" | "running";

export interface StagesSummary {
  stages: ResearchStage[];
  outcome: StageOutcome;
  /** "4 steps · 5 tool calls · 17.8 s" (research) or "4 stages · 9.38 s" (standard). */
  summary: string;
  totalMs: number | null;
}

/** Calculations over a dataset. `describe_dataset` only reads a dataset's shape. */
const COMPUTE_TOOLS: ReadonlySet<string> = new Set(["aggregate", "filter_rows", "group_compare"]);
const ANALYTICS_TOOLS: ReadonlySet<string> = new Set([...COMPUTE_TOOLS, "describe_dataset"]);
const FAILED_TERMINATIONS: ReadonlySet<string> = new Set(["error", "tool_failure", "timeout"]);

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Sum of every `<prefix>_<attempt>` timing (synthesis and verification run once per attempt). */
function attemptTotal(timings: Readonly<Record<string, number>>, prefix: string): number | null {
  const values = Object.entries(timings)
    .filter(([key, value]) => key.startsWith(`${prefix}_`) && isNum(value))
    .map(([, value]) => value);
  return values.length > 0 ? values.reduce((a, b) => a + b, 0) : null;
}

function stage(id: ResearchStageId, state: StageState, durationMs: number | null = null, detail: string | null = null): ResearchStage {
  return { id, label: RESEARCH_STAGE_LABEL[id], state, durationMs, detail };
}

function searchDetail(searches: number, passages: number): string | null {
  const parts = [searches > 0 ? formatCount(searches, "search", "searches") : null, passages > 0 ? formatCount(passages, "passage") : null];
  const text = parts.filter(Boolean).join(" · ");
  return text || null;
}

/** Marks the last stage as failed (failed run) or drops nothing and stops (cancelled run). */
function applyOutcome(stages: ResearchStage[], outcome: StageOutcome): ResearchStage[] {
  if (outcome !== "failed" || stages.length === 0) return stages;
  return stages.map((s, i) => (i === stages.length - 1 ? { ...s, state: "failed" as const } : s));
}

function savedOutcome(run: RunRecord): StageOutcome {
  if (run.status === "cancelled" || run.termination_state === "cancelled") return "cancelled";
  if (run.status === "failed" || FAILED_TERMINATIONS.has(run.termination_state ?? "")) return "failed";
  if (run.status === "running" || run.status === "queued") return "running";
  return "completed";
}

function summaryText(run: RunRecord, stages: readonly ResearchStage[], totalMs: number | null, outcome: StageOutcome): string {
  const agent = run.agent;
  const parts =
    agent && agent.steps > 0
      ? [formatCount(agent.steps, "step"), formatCount(agent.tool_calls, "tool call")]
      : [formatCount(stages.length, "stage")];
  if (totalMs !== null) parts.push(formatMs(totalMs));
  if (outcome === "failed") parts.push("Did not complete");
  if (outcome === "cancelled") parts.push("Cancelled");
  return parts.join(" · ");
}

/** Stages of a saved run, all completed (or the last one failed), with their recorded timings. */
export function savedStages(run: RunRecord): StagesSummary {
  const t = run.timings ?? {};
  const trace = run.agent?.trace ?? [];
  const outcome = savedOutcome(run);
  const totalMs = isNum(t.total_ms) ? t.total_ms : null;
  const stages: ResearchStage[] = [stage("understand", "done")];

  const computes = trace.filter((s) => COMPUTE_TOOLS.has(s.tool));
  const analysed = computes.length > 0;
  const analysisSteps = analysed ? trace.filter((s) => ANALYTICS_TOOLS.has(s.tool)) : [];
  const searchSteps = trace.filter((s) => !analysisSteps.includes(s));
  const passages = new Set(searchSteps.flatMap((s) => s.handles)).size;

  if (run.agent) {
    const analysisMs = analysisSteps.reduce((sum, s) => sum + (isNum(s.duration_ms) ? s.duration_ms : 0), 0);
    const agentMs = isNum(t.agent_ms) ? t.agent_ms : isNum(run.agent.duration_ms) ? run.agent.duration_ms : null;
    // The agent loop is searching (and planning its next search) except for time spent calculating.
    const searchMs = agentMs !== null ? Math.max(0, agentMs - analysisMs) : null;
    stages.push(stage("search", "done", searchMs, searchDetail(searchSteps.length, passages)));
    if (analysed) stages.push(stage("analyze", "done", analysisMs, formatCount(computes.length, "calculation")));
  } else if (isNum(t.retrieval_ms) || run.pack_handles.length > 0) {
    stages.push(stage("search", "done", isNum(t.retrieval_ms) ? t.retrieval_ms : null, searchDetail(0, run.pack_handles.length)));
  }

  if (isNum(t.pack_ms)) {
    const n = run.pack_handles.length;
    stages.push(stage("compare", "done", t.pack_ms, n > 0 ? `${formatCount(n, "passage")} selected` : null));
  }

  const flags = [...run.degradation_flags, ...(run.agent?.flags ?? [])];
  const synthesisMs = attemptTotal(t, "synthesis_ms");
  const unavailable = isModelUnavailable({ terminationState: run.termination_state, flags });
  if (synthesisMs !== null && !unavailable) {
    const attempts = isNum(t.attempts) ? t.attempts : 1;
    stages.push(stage("prepare", "done", synthesisMs, attempts > 1 ? "Rewritten after citation checks" : null));
  }
  const verifyMs = attemptTotal(t, "verify_ms");
  if (verifyMs !== null) {
    const detail = isCitationFallback({ flags }) ? "Citation checks failed; evidence shown instead" : null;
    stages.push(stage("verify", "done", verifyMs, detail));
  }

  const final = applyOutcome(stages, outcome);
  return { stages: final, outcome, totalMs, summary: summaryText(run, final, totalMs, outcome) };
}

const PHASE_STAGE: Readonly<Record<string, ResearchStageId>> = {
  routing: "understand",
  planning: "search",
  searching: "search",
  // The "analyzing" phase selects the evidence passages for the answer (evidence-pack assembly).
  analyzing: "compare",
  synthesizing: "prepare",
  verifying: "verify",
};

function toolMs(tools: readonly ToolStep[]): number | null {
  const done = tools.filter((t) => isNum(t.durationMs));
  return done.length > 0 ? done.reduce((sum, t) => sum + (t.durationMs as number), 0) : null;
}

function liveOutcome(state: RunStreamState): StageOutcome {
  const term = state.done?.terminationState ?? state.terminationState ?? "";
  if (term === "cancelled") return "cancelled";
  if (state.error || FAILED_TERMINATIONS.has(term)) return "failed";
  return state.final || state.done ? "completed" : "running";
}

/**
 * Stages of the active run from the SSE reducer state. Only stages that are known to occur are
 * listed: "Running analysis" appears once a calculation starts. The current stage is `active`;
 * timings come from completed tool calls while running and from the `done` event's timings at the end.
 */
export function liveStages(state: RunStreamState): ResearchStage[] {
  const outcome = liveOutcome(state);
  const analytics = state.tools.filter((t) => t.kind === "analytics");
  const searches = state.tools.filter((t) => t.kind !== "analytics");
  const timings = state.done?.timings ?? {};

  const ids: ResearchStageId[] = ["understand", "search"];
  if (analytics.length > 0) ids.push("analyze");
  ids.push("compare", "prepare", "verify");

  let current: ResearchStageId = state.route ? "search" : "understand";
  if (state.phase) current = PHASE_STAGE[state.phase] ?? current;
  if (analytics.some((t) => t.status === "running")) current = "analyze";
  if (state.evidence && ids.indexOf(current) < ids.indexOf("compare")) current = "prepare";
  if (state.draft && ids.indexOf(current) < ids.indexOf("prepare")) current = "prepare";
  const finished = outcome === "completed" && (state.final !== null || state.done !== null);
  const currentIndex = finished ? ids.length : ids.indexOf(current);

  const durations: Record<ResearchStageId, number | null> = {
    understand: null,
    search: isNum(timings.retrieval_ms) ? timings.retrieval_ms : toolMs(searches),
    analyze: toolMs(analytics),
    compare: isNum(timings.pack_ms) ? timings.pack_ms : null,
    prepare: attemptTotal(timings, "synthesis_ms"),
    verify: attemptTotal(timings, "verify_ms"),
  };
  const details: Record<ResearchStageId, string | null> = {
    understand: null,
    search: searchDetail(searches.length, 0),
    analyze: analytics.length > 0 ? formatCount(analytics.length, "calculation") : null,
    compare: state.evidence ? `${formatCount(state.evidence.itemCount, "passage")} selected` : null,
    prepare: state.attempt > 1 ? "Rewriting after citation checks" : null,
    verify: null,
  };

  return ids.map((id, i) => {
    let s: StageState = i < currentIndex ? "done" : i === currentIndex ? "active" : "pending";
    if (s === "active" && outcome === "failed") s = "failed";
    if (s === "active" && outcome === "cancelled") s = "skipped";
    return stage(id, s, s === "done" ? durations[id] : null, details[id]);
  });
}

export interface ReplayFrame {
  /** Index of the stage that becomes active at `atMs` (stages before it are done). */
  index: number;
  atMs: number;
}

const REPLAY_MAX_MS = 6000;
const REPLAY_MIN_STAGE_MS = 350;

/**
 * Schedule for replaying saved stages at their recorded relative timings, compressed to at most
 * ~6 s. Each stage gets at least a short beat so instant stages stay visible. The last frame
 * (index === stages.length) marks the replay as finished.
 */
export function replaySchedule(stages: readonly ResearchStage[]): ReplayFrame[] {
  const known = stages.map((s) => (isNum(s.durationMs) ? s.durationMs : 0));
  const total = known.reduce((a, b) => a + b, 0);
  const budget = REPLAY_MAX_MS - REPLAY_MIN_STAGE_MS * stages.length;
  const scale = total > 0 ? Math.min(1, Math.max(0, budget) / total) : 0;
  const frames: ReplayFrame[] = [];
  let at = 0;
  stages.forEach((_, i) => {
    frames.push({ index: i, atMs: Math.round(at) });
    at += REPLAY_MIN_STAGE_MS + known[i] * scale;
  });
  frames.push({ index: stages.length, atMs: Math.round(at) });
  return frames;
}

/** Stage states while a replay is at `index` (stages before it done, it active, after it pending). */
export function replayStages(stages: readonly ResearchStage[], index: number): ResearchStage[] {
  return stages.map((s, i) => {
    if (i < index) return s.state === "failed" && i === stages.length - 1 ? s : { ...s, state: "done" as const };
    if (i === index) return { ...s, state: "active" as const };
    return { ...s, state: "pending" as const };
  });
}
