/**
 * Maps a saved run (`RunRecord` + `RunVerification`) into the plain-language view shown under
 * an answer ("Research details"). Codes and ids are kept apart in `technical`, which the UI
 * shows only inside "Technical details".
 */
import type { StatusTone } from "@/components/ui/tone";
import type { AgentTraceStep, ConversationSummary, RunRecord, RunVerification } from "./api/contracts";
import { degradationFlag, routeReason, toolStep } from "./labels";
import { isModelUnavailable } from "./model-availability";

export type ModeLabel = "Standard" | "Research";
export interface Labelled {
  label: string;
  tone: StatusTone;
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
  mode: ModeLabel;
  /** Plain-language reason for the mode, e.g. "Auto chose Research: the question needed computed figures." */
  modeReason: string | null;
  durationMs: number | null;
  verification: Labelled | null;
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

const MODE: Record<string, ModeLabel> = { standard: "Standard", research: "Research" };
const ANALYTICS_TOOLS = new Set(["aggregate", "filter_rows", "group_compare", "describe_dataset"]);
const FAILED_TERMINATIONS = new Set(["error", "tool_failure", "timeout"]);

export function modeLabel(mode: string | null | undefined): ModeLabel {
  return MODE[mode ?? ""] ?? "Standard";
}

function sentence(text: string): string {
  return text ? text.charAt(0).toLowerCase() + text.slice(1) : text;
}

/** The mode decision in plain words (never a reason code). */
export function describeModeDecision(route: RunRecord["route"], mode: string): string | null {
  const used = modeLabel(route.decided ?? mode);
  const requested = route.requested;
  if (requested === "standard" || requested === "research") return `You chose ${modeLabel(requested)}.`;
  if (requested !== "auto") return null;
  const reason = routeReason(route.reason);
  return reason.known ? `Auto chose ${used}: ${sentence(reason.label)}.` : `Auto chose ${used}.`;
}

/** Verification outcome: "Verified", "Verified with repairs" or the evidence-only fallback. */
export function verificationLabel(run: RunRecord, v: RunVerification | null): Labelled | null {
  const unavailable = isModelUnavailable({ terminationState: run.termination_state, flags: run.degradation_flags });
  const disposition = v?.final_disposition ?? null;
  if (unavailable || disposition === "fallback") {
    return { label: "Evidence only – model unavailable", tone: "warn" };
  }
  if (disposition === "accepted") return { label: "Verified", tone: "success" };
  if (disposition === "repaired" || disposition === "regenerate") {
    return { label: "Verified with repairs", tone: "success" };
  }
  if (disposition === "rejected") return { label: "Did not pass checks", tone: "danger" };
  return null;
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
  for (const flag of flags) {
    const entry = degradationFlag(flag);
    const label = entry.known ? entry.label : "A processing notice was recorded";
    if (seen.has(label)) continue;
    seen.add(label);
    out.push({ label, description: entry.description ?? null });
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

/** Outcome indicator for a conversation row, from its last run only. */
export function conversationOutcome(row: ConversationSummary): Labelled | null {
  const run = row.last_run;
  if (!run) return null;
  if (run.status === "cancelled" || run.termination_state === "cancelled") return { label: "Cancelled", tone: "neutral" };
  if (run.status === "failed" || FAILED_TERMINATIONS.has(run.termination_state ?? "")) return { label: "Failed", tone: "danger" };
  if (isModelUnavailable({ terminationState: run.termination_state, flags: run.degradation_flags })) {
    return { label: "Evidence only", tone: "warn" };
  }
  if (run.termination_state === "no_relevant_evidence") return { label: "Not enough evidence", tone: "neutral" };
  if (run.status === "running" || run.status === "queued") return { label: "In progress", tone: "info" };
  if (run.termination_state === "completed_with_limited_evidence") return { label: "Limited evidence", tone: "warn" };
  return { label: "Answered", tone: "success" };
}
