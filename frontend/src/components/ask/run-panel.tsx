"use client";

import { useMemo } from "react";
import type { CitationContext } from "@/lib/citations";
import type { RunStreamState } from "@/lib/run-stream";
import { PulseNode } from "../motion/pulse-node";
import { Button } from "../ui/button";
import { AnswerView } from "./answer-view";
import { LiveResearchProgress, ResearchTimeline } from "./research-timeline";
import { RouteBadge } from "./route-badge";
import { RunNotices } from "./run-notices";
import { SafeMarkdown } from "./safe-markdown";
import type { StreamConnection } from "./use-run-stream";

function StatusLine({ state, connection }: { state: RunStreamState; connection: StreamConnection }) {
  const message =
    connection === "reconnecting"
      ? "Connection interrupted, reconnecting…"
      : (state.statusMessage ?? "Starting…");
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-secondary">
      <span className="flex items-center gap-2">
        <PulseNode size="sm" active />
        {message}
      </span>
      {state.evidence && (
        <span className="text-xs text-muted">
          {state.evidence.itemCount} evidence passage{state.evidence.itemCount === 1 ? "" : "s"} found
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
      <p className="text-sm text-muted">
        The first draft was discarded and is being rewritten.
      </p>
    );
  }
  return (
    <section aria-label="Unverified draft" className="rounded-lg border border-dashed border-border-strong bg-sunken px-4 py-3">
      <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted">Draft — not yet verified</p>
      <SafeMarkdown text={state.draft} ws={ws} citations={citations} className="text-secondary" />
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
    <div className="flex max-w-[46rem] flex-col gap-4">
      <RouteBadge route={state.route} />
      {running && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <StatusLine state={state} connection={connection} />
          <Button variant="secondary" size="sm" onClick={onCancel} loading={cancelling}>
            {cancelling ? "Cancelling…" : "Cancel"}
          </Button>
        </div>
      )}
      {!state.final && <LiveResearchProgress state={state} running={running} />}
      <ResearchTimeline tools={state.tools} phase={state.phase} running={running} />
      {state.final ? (
        <div className="ms-fade-in">
          <AnswerView
            ws={ws}
            content={state.final.content}
            citations={state.final.citations}
            sections={state.final.sections}
          />
        </div>
      ) : (
        running && <DraftPanel ws={ws} state={state} />
      )}
      {lost && (
        <p role="alert" className="rounded-md border border-warn/30 bg-warn-subtle px-3 py-2 text-sm text-warn">
          Lost the live connection. The answer is still being prepared; reload this conversation
          to see it once it is saved.
        </p>
      )}
      <RunNotices warnings={state.warnings} done={state.done} error={state.error} />
    </div>
  );
}
