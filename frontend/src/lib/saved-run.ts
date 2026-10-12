/**
 * Maps a saved run (`RunRecord` + `RunVerification`) into the plain-language view shown under
 * an answer ("Research details"). Codes and ids are kept apart in `technical`, which the UI
 * shows only inside "Technical details".
 */
import type { StatusTone } from "@/components/ui/tone";
import type { AgentTraceStep, ConversationSummary, RunRecord, RunVerification } from "./api/contracts";
import {
  userFacingFlags,
  runStatus,
  terminationState,
  toolStep,
  verificationDisposition,
  type Humanized,
} from "./labels";
import { isCitationFallback, isModelUnavailable } from "./model-availability";
import { describeModeDecision, modeCode, modeLabel } from "./run-mode";
import type { RouteMode } from "./run-stream";

export { describeModeDecision, modeLabel } from "./run-mode";

export interface Labelled {
  label: string;
  tone: StatusTone;
}
export interface VerificationView extends Labelled {
  /** Plain-language account for business readers, e.g. "Citations checked; 2 corrections made before saving". */
  summary: string;
}
export interface ResearchStepView {
  key: string;
  label: string;
  detail: string | null;
  failed: boolean;
  durationMs: number;
}
export interface RunNotice {
  label: string;
  description: string | null;
}
export interface SavedRunView {
  /** Display name of the mode that answered (labels.ts `runMode`). */
  mode: string;
  modeCode: RouteMode;
  /** Plain-language reason for the mode, e.g. "Automatic mode chose Research: the question needed computed figures." */
  modeReason: string | null;
  durationMs: number | null;
  verification: VerificationView | null;
  steps: ResearchStepView[];
  notices: RunNotice[];
  modelUnavailable: boolean;
  cancelled: boolean;
  failed: boolean;
  technical: {
    runId: string;
    status: string;
    terminationState: string | null;
    flags: string[];
    finalDisposition: string | null;
    route: RunRecord["route"];
  };
}

const ANALYTICS_TOOLS = new Set(["aggregate", "filter_rows", "group_compare", "describe_dataset"]);
const FAILED_TERMINATIONS = new Set(["error", "tool_failure", "timeout"]);

function labelled(entry: Humanized, fallbackTone: StatusTone = "neutral"): Labelled {
  return { label: entry.label, tone: entry.tone ?? fallbackTone };
}

function corrections(v: RunVerification | null): number {
  const last = v?.attempts[v.attempts.length - 1];
  return last?.repairs_n ?? 0;
}

const DISPOSITION_SUMMARY: Readonly<Record<string, string>> = {
  accepted: "Citations verified",
  regenerate: "Citations checked; the first draft was rewritten",
  rejected: "Did not pass citation checks",
  fallback: "Citation checks failed; evidence shown instead",
};

/**
 * Verification outcome, worded from labels.ts: "Verified", "Verified after corrections",
 * "Rewritten after checks", the citation-check "Fallback answer", or the model-unavailable state.
 */
export function verificationLabel(run: RunRecord, v: RunVerification | null): VerificationView | null {
  const disposition = v?.final_disposition ?? null;
  const flags = run.degradation_flags;
  const unavailable = isModelUnavailable({ terminationState: run.termination_state, flags });
  if (!unavailable && isCitationFallback({ flags, disposition })) {
    return { ...labelled(verificationDisposition("fallback"), "warn"), summary: DISPOSITION_SUMMARY.fallback };
  }
  if (unavailable) {
    return { ...labelled(terminationState("generation_unavailable"), "warn"), summary: "Evidence only; the live model was unavailable" };
  }
  if (!disposition) return null;
  const entry = verificationDisposition(disposition);
  if (!entry.known) return null;
  if (disposition === "repaired") {
    const n = corrections(v);
    const summary = n > 0 ? `Citations checked; ${n} ${n === 1 ? "correction" : "corrections"} made before saving` : "Citations checked; corrections made before saving";
    return { ...labelled(entry), summary };
  }
  return { ...labelled(entry), summary: DISPOSITION_SUMMARY[disposition] ?? entry.label };
}

/** "SURVEY-2026:1" → "SURVEY-2026"; dataset ids carry the source version after the colon. */
function datasetSource(args: unknown): string | null {
  if (typeof args !== "object" || args === null) return null;
  const dataset = (args as Record<string, unknown>).dataset;
  return typeof dataset === "string" && dataset ? dataset.split(":")[0] : null;
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function stepView(step: AgentTraceStep, titles: Readonly<Record<string, string>>): ResearchStepView {
  const base = toolStep(step.tool);
  let label = base.known ? base.label : "Ran a research step";
  let detail: string | null = null;
  if (ANALYTICS_TOOLS.has(step.tool)) {
    const code = datasetSource(step.args);
    const title = code ? titles[code] : undefined;
    if (title) label = `${label} from ${title}`;
  } else if (step.tool === "get_evidence") {
    label = step.handles.length > 1 ? `Read ${plural(step.handles.length, "evidence passage")}` : label;
  } else if (step.handles.length > 0) {
    detail = `${plural(step.handles.length, "passage")} found`;
  }
  const failed = step.status !== "ok";
  return { key: `${step.step}:${step.call_index}`, label, detail, failed, durationMs: step.duration_ms };
}

function notices(flags: readonly string[]): RunNotice[] {
  const seen = new Set<string>();
  const out: RunNotice[] = [];
  // Internal and unknown codes are skipped here; Technical details still lists them.
  for (const entry of userFacingFlags(flags)) {
    if (seen.has(entry.label)) continue;
    seen.add(entry.label);
    out.push({ label: entry.label, description: entry.description ?? null });
  }
  return out;
}

export interface SavedRunOptions {
  /** Source code → source title, used to name datasets in research steps. */
  sourceTitles?: Readonly<Record<string, string>>;
}

export function toSavedRunView(
  run: RunRecord,
  v: RunVerification | null,
  { sourceTitles = {} }: SavedRunOptions = {},
): SavedRunView {
  const flags = [...new Set([...run.degradation_flags, ...(run.agent?.flags ?? [])])];
  const total = run.timings.total_ms;
  return {
    mode: modeLabel(run.mode),
    modeCode: modeCode(run.mode),
    modeReason: describeModeDecision(run.route, run.mode),
    durationMs: typeof total === "number" ? total : null,
    verification: verificationLabel(run, v),
    steps: (run.agent?.trace ?? []).map((step) => stepView(step, sourceTitles)),
    notices: notices(flags),
    modelUnavailable: isModelUnavailable({ terminationState: run.termination_state, flags }),
    cancelled: run.status === "cancelled" || run.termination_state === "cancelled",
    failed: run.status === "failed" || FAILED_TERMINATIONS.has(run.termination_state ?? ""),
    technical: {
      runId: run.run_id,
      status: run.status,
      terminationState: run.termination_state,
      flags,
      finalDisposition: v?.final_disposition ?? null,
      route: run.route,
    },
  };
}

export type OutcomeKind =
  | "answered"
  | "limited"
  | "running"
  | "fallback"
  | "evidence_only"
  | "no_evidence"
  | "failed"
  | "cancelled";

export interface ConversationOutcome extends Labelled {
  kind: OutcomeKind;
}

const ANSWERED_KINDS: ReadonlySet<OutcomeKind> = new Set(["answered", "limited", "running"]);

/** Outcome indicator for a conversation row, from its last run only (labels.ts vocabulary). */
export function conversationOutcome(row: ConversationSummary): ConversationOutcome | null {
  const run = row.last_run;
  if (!run) return null;
  const state = run.termination_state ?? "";
  const flags = run.degradation_flags;
  if (run.status === "cancelled" || state === "cancelled") return { kind: "cancelled", ...labelled(terminationState("cancelled")) };
  if (run.status === "failed" || FAILED_TERMINATIONS.has(state)) return { kind: "failed", ...labelled(runStatus("failed"), "danger") };
  const unavailable = isModelUnavailable({ terminationState: state, flags });
  if (!unavailable && isCitationFallback({ flags })) return { kind: "fallback", ...labelled(verificationDisposition("fallback"), "warn") };
  if (unavailable) return { kind: "evidence_only", ...labelled(terminationState("generation_unavailable"), "warn") };
  if (state === "no_relevant_evidence") return { kind: "no_evidence", ...labelled(terminationState(state)) };
  if (run.status === "running" || run.status === "queued") return { kind: "running", ...labelled(runStatus("running"), "info") };
  if (state === "completed_with_limited_evidence") return { kind: "limited", ...labelled(terminationState(state), "warn") };
  return { kind: "answered", label: "Answered", tone: "success" };
}

/** Whether a conversation row counts as answered for the "Answered" list filter. */
export function isAnsweredConversation(row: ConversationSummary): boolean {
  const outcome = conversationOutcome(row);
  return outcome !== null && ANSWERED_KINDS.has(outcome.kind);
}
