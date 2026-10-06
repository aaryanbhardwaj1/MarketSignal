"use client";

import { useMemo } from "react";
import type { CitationContext } from "@/lib/citations";
import { humanize } from "@/lib/format";
import type { RunStreamState } from "@/lib/run-stream";
import { buttonClass } from "../ui/form-controls";
import { AnswerView } from "./answer-view";
import { RunNotices } from "./run-notices";
import { SafeMarkdown } from "./safe-markdown";
import type { StreamConnection } from "./use-run-stream";

function StatusLine({ state, connection }: { state: RunStreamState; connection: StreamConnection }) {
  const message =
    connection === "reconnecting"
      ? "Connection lost — reconnecting…"
      : (state.statusMessage ?? "Starting…");
  return (
    <div role="status" aria-live="polite" className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-600">
      <span className="flex items-center gap-2">
        <span
          aria-hidden
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600"
        />
        {message}
      </span>
      {state.evidence && (
        <span className="text-xs text-slate-500">
          {state.evidence.itemCount} evidence item{state.evidence.itemCount === 1 ? "" : "s"}
          {state.evidence.classes.length > 0 && ` · ${state.evidence.classes.join(", ")}`}
          {state.evidence.truncated && " · truncated"}
        </span>
      )}
    </div>
  );
}

function DraftPanel({ ws, state }: { ws: string; state: RunStreamState }) {
  const citations = useMemo<CitationContext>(
    () => ({ aliases: state.citationsByAlias }),
    [state.citationsByAlias],
  );
  if (!state.draft) {
    if (!state.draftResetReason) return null;
    return (
      <p className="text-xs text-slate-500">
        Draft discarded ({humanize(state.draftResetReason)}).
      </p>
    );
  }
  return (
    <section aria-label="Unverified draft" className="rounded-lg border border-dashed border-slate-300 bg-slate-50/70 p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Draft — verifying…</p>
      <SafeMarkdown text={state.draft} ws={ws} citations={citations} className="text-slate-600" />
    </section>
  );
}

export interface RunPanelProps {
  ws: string;
  state: RunStreamState;
  connection: StreamConnection;
  onCancel: () => void;
  cancelling: boolean;
}

/** Live view of the active run: status, unverified draft, then the verified final answer. */
export function RunPanel({ ws, state, connection, onCancel, cancelling }: RunPanelProps) {
  const running = !state.done && connection !== "closed";
  const lost = !state.done && connection === "closed";

  return (
    <div className="flex flex-col gap-3">
      {running && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <StatusLine state={state} connection={connection} />
          <button
            type="button"
            onClick={onCancel}
            disabled={cancelling}
            className={buttonClass("secondary", "sm")}
          >
            {cancelling ? "Cancelling…" : "Cancel"}
          </button>
        </div>
      )}
      {state.final ? (
        <AnswerView
          ws={ws}
          content={state.final.content}
          citations={state.final.citations}
          sections={state.final.sections}
        />
      ) : (
        running && <DraftPanel ws={ws} state={state} />
      )}
      {lost && (
        <p role="alert" className="text-sm text-amber-800">
          Lost connection to the run stream. The run continues on the server; reload this
          conversation to see the stored answer.
        </p>
      )}
      <RunNotices warnings={state.warnings} done={state.done} error={state.error} />
    </div>
  );
}
