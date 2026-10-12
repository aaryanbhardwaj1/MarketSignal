"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { useRun, useRunVerification } from "@/lib/api/hooks/core";
import { isResultCard, type AnyCitationCard, type ChatMessage } from "@/lib/api/types";
import { modeLabel } from "@/lib/run-mode";
import { toSavedRunView, type SavedRunView } from "@/lib/saved-run";
import { AnswerView } from "./answer-view";
import { evidenceLibraryHref } from "./ask-routes";
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

/** One saved answer: the answer sections, then "Research details" for its run. */
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

  return (
    <div className="flex flex-col gap-5">
      {body}
      {view ? (
        <ResearchDetails ws={ws} view={view} />
      ) : (
        message.run_id && <p className="text-sm text-muted">Research details are not available for this answer.</p>
      )}
    </div>
  );
}
