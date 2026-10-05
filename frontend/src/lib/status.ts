import {
  NON_TERMINAL_STATUSES,
  TERMINAL_STATUSES,
  type SourceSummary,
  type VersionStatus,
} from "./api/types";

const NON_TERMINAL = new Set<string>(NON_TERMINAL_STATUSES);
const TERMINAL = new Set<string>(TERMINAL_STATUSES);

export function isNonTerminalStatus(status: string | null | undefined): boolean {
  return typeof status === "string" && NON_TERMINAL.has(status);
}

export function isTerminalStatus(status: string | null | undefined): boolean {
  return typeof status === "string" && TERMINAL.has(status);
}

/** True when any live source still has a version in the ingestion pipeline. */
export function hasInFlightSources(sources: readonly SourceSummary[] | undefined): boolean {
  return (sources ?? []).some((s) => !s.deleted && isNonTerminalStatus(s.latest?.status));
}

export type StatusTone = "success" | "warning" | "danger" | "progress" | "muted";

const TONES: Record<VersionStatus, StatusTone> = {
  queued: "progress",
  parsing: "progress",
  chunking: "progress",
  embedding: "progress",
  indexing: "progress",
  ready: "success",
  ready_degraded: "warning",
  failed: "danger",
  superseded: "muted",
  purged: "muted",
};

export function statusTone(status: string | null | undefined): StatusTone {
  if (!status) return "muted";
  return TONES[status as VersionStatus] ?? "muted";
}

export function retryable(status: string | null | undefined): boolean {
  return status === "failed";
}
