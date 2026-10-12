"use client";

import { isResultCard } from "@/lib/api/types";
import { formatCount } from "@/lib/format";
import { isModelUnavailable } from "@/lib/model-availability";
import { PHASE_LABELS } from "@/lib/labels";
import type { RunStreamState } from "@/lib/run-stream";
import { useAskSession } from "./ask-session";
import type { StreamConnection } from "./use-run-stream";

const FAILED = new Set(["error", "tool_failure", "timeout", "interrupted"]);

/** One short, plain-language line for the screen-reader status region; "" when nothing to say. */
export function runAnnouncement(state: RunStreamState, connection: StreamConnection, active: boolean): string {
  if (!active) return "";
  const done = state.done;
  if (done) {
    if (done.terminationState === "cancelled") return "Question cancelled.";
    if (isModelUnavailable({ warnings: state.warnings, terminationState: done.terminationState, flags: done.flags })) {
      return "Live model unavailable. Showing the evidence found.";
    }
    if (state.final) {
      const passages = state.final.citations.filter((c) => !isResultCard(c)).length;
      return passages > 0 ? `Answer ready, ${formatCount(passages, "cited passage")}.` : "Answer ready.";
    }
    if (state.error || FAILED.has(done.terminationState)) return "The answer could not be completed.";
    return "Finished.";
  }
  if (connection === "closed") return ""; // RunPanel raises its own alert for a lost connection
  if (connection === "reconnecting") return "Connection interrupted, reconnecting.";
  return state.phase ? `${PHASE_LABELS[state.phase]}…` : "Starting…";
}

/**
 * Persistent, visually hidden status region for the live run. It is mounted for the whole Ask
 * session (layout level), so its first message is announced and so are the endings ("Answer
 * ready", "Question cancelled"). Visible status text elsewhere is not a live region.
 */
export function RunAnnouncer() {
  const { active, state, connection } = useAskSession();
  return (
    <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
      {runAnnouncement(state, connection, active !== null)}
    </div>
  );
}
