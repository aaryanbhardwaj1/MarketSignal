/**
 * Run-mode vocabulary for Ask MarketSignal. Mode names come from `runMode()` in labels.ts so the
 * composer, the live run, saved answers, the conversation list and Overview all use one name per
 * mode. Router reason codes are shown only through `routeReason()`; raw codes and cues never reach
 * the business page.
 */
import type { RunMode } from "./api/types";
import { routeReason, runMode, toolStep } from "./labels";
import type { RouteMode, RunPhase, ToolStep } from "./run-stream";

/** Display name of a mode ("standard" | "research" | "auto"); unknown modes read as Standard. */
export function modeLabel(mode: string | null | undefined): string {
  const entry = runMode(mode);
  return entry.known ? entry.label : runMode("standard").label;
}

/** The mode that answered, as a code: anything other than "research" is a standard answer. */
export function modeCode(mode: string | null | undefined): RouteMode {
  return mode === "research" ? "research" : "standard";
}

export interface RunModeOption {
  value: RunMode;
  label: string;
  help: string;
}

/** Mode choices on the question form. The user's explicit choice always wins over the router. */
export const RUN_MODE_OPTIONS: readonly RunModeOption[] = [
  {
    value: "auto",
    label: modeLabel("auto"),
    help: `Picks ${modeLabel("standard")} or ${modeLabel("research")} from the question; questions that need calculations get ${modeLabel("research")}.`,
  },
  { value: "standard", label: modeLabel("standard"), help: "Fast answer from the current evidence base." },
  {
    value: "research",
    label: modeLabel("research"),
    help: "Searches across multiple sources and analysis tools before answering.",
  },
];

/** The router's decision fields shared by the live `run_started.route` and a saved run's route. */
export interface RouteDecision {
  requested?: string | null;
  decided?: string | null;
  reason?: string | null;
}

function lowerFirst(text: string): string {
  return text ? text.charAt(0).toLowerCase() + text.slice(1) : text;
}

/** The mode decision in plain words (never a reason code), e.g. "Automatic mode chose Research: …". */
export function describeModeDecision(route: RouteDecision, mode: string): string | null {
  const used = modeLabel(route.decided ?? mode);
  const requested = route.requested;
  if (requested === "standard" || requested === "research") return `You chose ${modeLabel(requested)}.`;
  if (requested !== "auto") return null;
  const reason = routeReason(route.reason);
  const auto = `${modeLabel("auto")} mode chose ${used}`;
  return reason.known ? `${auto}: ${lowerFirst(reason.label)}.` : `${auto}.`;
}

export interface RouteDescription {
  /** Mode that answered, e.g. "Research". */
  mode: string;
  /** Why, in plain words; null when the route carries no usable decision. */
  reason: string | null;
  tone: "info" | "neutral";
}

/** Badge content for the live routing decision; null when the run carries no route (older runs). */
export function describeRoute(route: RouteDecision | null): RouteDescription | null {
  if (!route || !route.decided) return null;
  const explicit = route.requested === "standard" || route.requested === "research";
  return {
    mode: modeLabel(route.decided),
    reason: describeModeDecision(route, route.decided),
    tone: explicit ? "neutral" : "info",
  };
}

/** Live research phases (SSE `status.phase`). "analyzing" is evidence-pack assembly, not analytics. */
export const PHASE_LABELS: Readonly<Record<RunPhase, string>> = {
  routing: "Choosing a mode",
  planning: "Planning research",
  searching: "Searching evidence",
  analyzing: "Selecting evidence",
  synthesizing: "Writing the answer",
  verifying: "Checking citations",
};

const KIND_FALLBACKS: Readonly<Record<string, string>> = {
  search: "Searching evidence",
  keyword: "Searching for exact terms",
  lookup: "Reading evidence passages",
  catalog: "Reviewing available sources",
  analytics: "Computing a figure",
};

/** Plain-text label for a research step: the server summary, else the step's plain label. */
export function toolSummaryText(step: ToolStep): string {
  if (step.summary) return step.summary;
  const known = toolStep(step.tool);
  if (known.known) return known.label;
  return KIND_FALLBACKS[step.kind] ?? "Research step";
}
