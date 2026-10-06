import { humanize } from "./format";
import type { RunMode } from "./api/types";
import type { RunRoute, ToolStep } from "./run-stream";

export interface RunModeOption {
  value: RunMode;
  label: string;
  help: string;
}

/** Mode choices on the question form. The user's explicit choice always wins over the router. */
export const RUN_MODE_OPTIONS: readonly RunModeOption[] = [
  { value: "auto", label: "Auto", help: "Deterministic routing picks the mode." },
  { value: "standard", label: "Standard", help: "One evidence search. Fastest." },
  { value: "research", label: "Research", help: "Multi-step agent with tool calls. Slower." },
];

export interface RouteDescription {
  label: string;
  tone: "info" | "neutral";
}

const MODE_LABELS = { standard: "Standard", research: "Research" } as const;

/** Badge text for the routing decision; null when the run carries no route (older runs). */
export function describeRoute(route: RunRoute | null): RouteDescription | null {
  if (!route) return null;
  const mode = `${MODE_LABELS[route.decided]} mode`;
  if (route.requested === "standard" || route.requested === "research") {
    return { label: `${mode} · chosen by you`, tone: "neutral" };
  }
  const reason = route.reason ? `: ${humanize(route.reason)}` : "";
  return { label: `${mode} · auto-routed${reason}`, tone: "info" };
}

const KIND_FALLBACKS: Record<string, string> = {
  search: "Searching evidence",
  keyword: "Checking exact identifiers",
  lookup: "Opening evidence items",
  catalog: "Listing sources",
  analytics: "Computing analytics",
};

/** Plain-text label for a tool call: the server summary, else a fixed label by kind. */
export function toolSummaryText(step: ToolStep): string {
  return step.summary || KIND_FALLBACKS[step.kind] || humanize(step.tool) || "Tool call";
}
