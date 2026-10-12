import { NON_TERMINAL_STATUSES, type SourceSummary } from "./api/types";

const NON_TERMINAL = new Set<string>(NON_TERMINAL_STATUSES);

export function isNonTerminalStatus(status: string | null | undefined): boolean {
  return typeof status === "string" && NON_TERMINAL.has(status);
}

/** True when any live source still has a version in the ingestion pipeline. */
export function hasInFlightSources(sources: readonly SourceSummary[] | undefined): boolean {
  return (sources ?? []).some((s) => !s.deleted && isNonTerminalStatus(s.latest?.status));
}

/* ---------------------------------------------------------------------------------------------
 * Evidence Library status buckets (plain-language labels for business pages).
 * ------------------------------------------------------------------------------------------- */

/** Coarse status a reader cares about; raw pipeline stages collapse into "processing". */
export type LibraryStatus = "ready" | "processing" | "failed" | "superseded" | "removed";

export const LIBRARY_STATUSES: readonly LibraryStatus[] = ["ready", "processing", "failed", "superseded"];

export interface StatusLabel {
  label: string;
  tone: "success" | "warn" | "danger" | "info" | "neutral";
}

const BUCKET_LABELS: Record<LibraryStatus, StatusLabel> = {
  ready: { label: "Ready", tone: "success" },
  processing: { label: "Processing", tone: "info" },
  failed: { label: "Failed", tone: "danger" },
  superseded: { label: "Superseded", tone: "neutral" },
  removed: { label: "Removed", tone: "neutral" },
};

/** Bucket for a version status; a deleted source is always "removed". Unknown codes are "processing" only when non-terminal. */
export function libraryStatus(status: string | null | undefined, deleted = false): LibraryStatus {
  if (deleted || status === "purged") return "removed";
  if (status === "ready" || status === "ready_degraded") return "ready";
  if (status === "failed") return "failed";
  if (status === "superseded") return "superseded";
  if (isNonTerminalStatus(status)) return "processing";
  return "failed";
}

export function libraryStatusLabel(bucket: LibraryStatus): StatusLabel {
  return BUCKET_LABELS[bucket];
}

/** Label for one version's status; "ready_degraded" reads as ready with a caution tone. */
export function versionStatusLabel(status: string | null | undefined, deleted = false): StatusLabel {
  if (!deleted && status === "ready_degraded") return { label: "Ready with warnings", tone: "warn" };
  return BUCKET_LABELS[libraryStatus(status, deleted)];
}
