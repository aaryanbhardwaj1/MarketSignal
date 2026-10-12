"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, type ReactNode } from "react";
import { Button, LinkButton } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingRegion } from "@/components/ui/states";
import { useDatasets } from "@/lib/api/hooks/core";
import { listMessages } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/errors";
import { queryKeys } from "@/lib/api/query-keys";
import type { ChatMessage } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { isUuid } from "@/lib/handles";
import { askHref } from "./ask-routes";
import { useAskSession } from "./ask-session";
import { AssistantTurn } from "./assistant-turn";
import { Composer, useGenerationAvailable } from "./composer";
import { RunPanel } from "./run-panel";

interface Turn {
  question: ChatMessage | null;
  answer: ChatMessage | null;
}

function toTurns(messages: readonly ChatMessage[]): Turn[] {
  const turns: Turn[] = [];
  for (const m of messages) {
    if (m.role === "user") turns.push({ question: m, answer: null });
    else if (turns.length > 0 && turns[turns.length - 1].answer === null) turns[turns.length - 1].answer = m;
    else turns.push({ question: null, answer: m });
  }
  return turns;
}

function Question({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface-muted px-4 py-3">
      <p className="text-xs font-medium text-muted">Question</p>
      <p className="mt-0.5 whitespace-pre-wrap text-base text-primary">{children}</p>
    </div>
  );
}

function NotFound({ ws }: { ws: string }) {
  return (
    <EmptyState
      title="Conversation not found"
      description="This conversation does not exist in this workspace, or it was removed."
      action={<LinkButton href={askHref(ws)}>Start a new conversation</LinkButton>}
    />
  );
}

function Header({ title, meta }: { title: string; meta?: string }) {
  return (
    <header className="border-b border-border pb-4">
      <p className="text-sm text-muted">Ask MarketSignal</p>
      <h1 className="mt-1 text-lg font-semibold leading-snug text-primary">{title}</h1>
      {meta && <p className="mt-1 text-sm text-muted">{meta}</p>}
    </header>
  );
}

/** A saved conversation: each question and its answer, the live run if one is going, and the composer. */
export function ConversationView({ ws, conversationId }: { ws: string; conversationId: string }) {
  const valid = isUuid(conversationId);
  const session = useAskSession();
  const { available } = useGenerationAvailable();
  const datasets = useDatasets(ws);
  const history = useQuery({
    queryKey: queryKeys.messages(ws, conversationId),
    queryFn: ({ signal }) => listMessages(ws, conversationId, signal),
    enabled: valid,
  });
  const sourceTitles = useMemo(() => {
    const map: Record<string, string> = {};
    for (const d of datasets.data?.datasets ?? []) map[d.source_code] = d.title;
    return map;
  }, [datasets.data]);

  if (!valid || (history.error instanceof ApiError && history.error.status === 404)) return <NotFound ws={ws} />;
  if (history.isPending) {
    return (
      <LoadingRegion label="Loading conversation" lines={8} />
    );
  }
  if (history.isError) {
    return (
      <ErrorState
        title="This conversation could not be loaded"
        description="Check your connection and try again."
        retry={() => void history.refetch()}
        devDetail={history.error instanceof ApiError ? history.error.code : undefined}
      />
    );
  }

  const active = session.active?.conversationId === conversationId ? session.active : null;
  const messages = history.data.filter((m) => !active || m.run_id !== active.runId);
  const turns = toTurns(messages);
  const title = turns.find((t) => t.question)?.question?.content ?? active?.question ?? "Conversation";
  const unansweredTail = !active && turns.length > 0 && turns[turns.length - 1].answer === null;
  const first = history.data[0];
  const meta = first ? `Asked ${formatDateTime(first.created_at)}` : undefined;

  return (
    <div className="flex flex-col gap-8">
      <Header title={title} meta={meta} />
      {turns.length === 0 && !active && (
        <EmptyState title="No questions yet" description="Ask a question below to start this conversation." />
      )}
      {turns.map((turn, i) => {
        const question = turn.question?.content ?? "";
        return (
          <article key={turn.question?.message_id ?? turn.answer?.message_id} className="flex flex-col gap-5">
            {turn.question && i > 0 && <Question>{question}</Question>}
            {turn.answer && <AssistantTurn ws={ws} message={turn.answer} question={question} sourceTitles={sourceTitles} />}
          </article>
        );
      })}
      {unansweredTail && (
        <div className="flex flex-wrap items-center gap-3 text-sm text-muted">
          No saved answer for the last question yet. It may still be in progress.
          <Button variant="ghost" size="sm" loading={history.isFetching} onClick={() => void history.refetch()}>
            Refresh
          </Button>
        </div>
      )}
      {active && (
        <article className="flex flex-col gap-5">
          {turns.length > 0 && <Question>{active.question}</Question>}
          <RunPanel
            ws={ws}
            state={session.state}
            connection={session.connection}
            cancelling={session.cancelling}
            onCancel={session.cancel}
          />
        </article>
      )}
      {/* Sticky only while asking is possible; a disabled composer should not cover the answer. */}
      <div className={available ? "sticky bottom-0 -mx-1 border-t border-border bg-canvas px-1 pb-4 pt-3" : "border-t border-border pt-6"}>
        <Composer conversationId={conversationId} />
      </div>
    </div>
  );
}
