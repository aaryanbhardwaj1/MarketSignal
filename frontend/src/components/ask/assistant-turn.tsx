"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { useRun, useRunVerification } from "@/lib/api/hooks/core";
import { isResultCard, type AnyCitationCard, type ChatMessage } from "@/lib/api/types";
import { formatCount, formatMs } from "@/lib/format";
import { modeLabel } from "@/lib/run-mode";
import { toSavedRunView, type SavedRunView } from "@/lib/saved-run";
import { AnswerView } from "./answer-view";
import { evidenceLibraryHref } from "@/lib/routes";
import { useAskSession } from "./ask-session";
import { useGenerationAvailable } from "./model-unavailable";
import { ResearchDetails } from "./research-details";

const LINK = "rounded-sm text-sm font-medium text-accent-text hover:underline";

function citedSourceCount(citations: readonly AnyCitationCard[]): number {
  return new Set(citations.filter((c) => !isResultCard(c)).map((c) => c.source_code)).size;
}

/** Deterministic follow-ups only: links into the product, never generated text. */
function NextSteps({ ws, question, citations, view }: { ws: string; question: string; citations: readonly AnyCitationCard[]; view: SavedRunView | null }) {
  const { fillComposer } = useAskSession();
  const { available } = useGenerationAvailable();
  const sources = citedSourceCount(citations);
  return (
    <ul className="flex flex-col gap-1.5">
      {sources > 0 && (
        <li>
          <Link href={evidenceLibraryHref(ws)} className={LINK}>
            Review the {sources === 1 ? "cited source" : `${sources} cited sources`} in the Evidence Library
          </Link>
        </li>
      )}
      {view?.modeCode === "standard" && question && (
        <li className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" size="sm" disabled={!available} onClick={() => fillComposer(question, "research")}>
            Ask again using {modeLabel("research")}
          </Button>
          {!available && <span className="text-sm text-muted">Available when the live model is on.</span>}
        </li>
      )}
    </ul>
  );
}

/** Plain run meta line under an answer: mode, verified status, duration and sources count. */
export function RunMeta({ view, sources }: { view: SavedRunView; sources: number }) {
  const parts = [
    view.mode,
    view.verifiedText,
    view.durationMs !== null ? formatMs(view.durationMs) : null,
    sources > 0 ? formatCount(sources, "source") : null,
  ].filter((p): p is string => Boolean(p));
  return (
    <p className="flex flex-wrap items-center gap-x-2 text-xs tabular-nums text-muted">
      <span className="sr-only">About this answer: </span>
      {parts.map((part, i) => (
        <span key={part} className="flex items-center gap-2">
          {i > 0 && <span aria-hidden className="h-0.5 w-0.5 rounded-full bg-border-strong" />}
          {part}
        </span>
      ))}
    </p>
  );
}

/** One saved answer: the report sections, its run meta line, then "Research steps" for its run. */
export function AssistantTurn({
  ws,
  message,
  question,
  sourceTitles,
}: {
  ws: string;
  message: ChatMessage;
  question: string;
  sourceTitles: Readonly<Record<string, string>>;
}) {
  const run = useRun(ws, message.run_id);
  const verification = useRunVerification(ws, message.run_id);
  const view = run.data ? toSavedRunView(run.data, verification.data ?? null, { sourceTitles }) : null;
  const citations = message.citations ?? [];

  if (message.status === "redacted") {
    return (
      <Callout tone="neutral" title="Answer removed">
        This answer was removed because a source it cited was purged from the workspace.
      </Callout>
    );
  }
  if (message.run_id && run.isPending) return <Skeleton lines={6} />;

  let body;
  if (view?.cancelled) {
    body = (
      <div className="flex flex-col gap-1">
        <StatusIndicator tone="neutral" label="Cancelled" />
        <p className="text-sm text-muted">This question was cancelled before an answer was saved.</p>
      </div>
    );
  } else if (message.status === "failed" || (view?.failed && !message.content)) {
    body = (
      <ErrorState
        title="This answer could not be completed"
        description="Something went wrong while preparing the answer. The question and any evidence found are kept."
        devDetail={view ? `${view.technical.status} · ${view.technical.terminationState ?? "–"}` : message.status}
      />
    );
  } else {
    body = (
      <AnswerView
        ws={ws}
        content={message.content}
        citations={citations}
        sections={message.sections}
        sourceTitles={sourceTitles}
        nextSteps={<NextSteps ws={ws} question={question} citations={citations} view={view} />}
      />
    );
  }

  const answered = !view?.cancelled && message.status !== "failed";
  return (
    <div className="flex flex-col gap-4">
      {body}
      {view && answered && (
        <div className="max-w-[46rem] border-t border-border pt-3">
          <RunMeta view={view} sources={citedSourceCount(citations)} />
        </div>
      )}
      {view ? (
        <ResearchDetails ws={ws} view={view} />
      ) : (
        message.run_id && <p className="text-sm text-muted">Research details are not available for this answer.</p>
      )}
    </div>
  );
}
