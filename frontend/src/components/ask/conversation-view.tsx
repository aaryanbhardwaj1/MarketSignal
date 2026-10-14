"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, type ReactNode, type RefObject } from "react";
import { Button, LinkButton } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingRegion } from "@/components/ui/states";
import { useDatasets } from "@/lib/api/hooks/core";
import { listMessages } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/errors";
import { queryKeys } from "@/lib/api/query-keys";
import type { ChatMessage } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { isUuid } from "@/lib/handles";
import { askHref } from "@/lib/routes";
import { useAskSession } from "./ask-session";
import { AssistantTurn } from "./assistant-turn";
import { Composer } from "./composer";
import { useGenerationAvailable } from "./model-unavailable";
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

/**
 * The user's question as a quiet query header: small "You asked" meta with the time, then the
 * question in 16px medium. The first question is the page heading (focus target after a new run).
 */
function QueryHeader({
  children,
  at,
  level = 2,
  headingRef,
}: {
  children: ReactNode;
  at?: string | null;
  level?: 1 | 2;
  headingRef?: RefObject<HTMLHeadingElement | null>;
}) {
  const Heading = level === 1 ? "h1" : "h2";
  return (
    <header className="flex flex-col gap-1">
      <p className="flex items-center gap-2 text-xs text-muted">
        <span className="font-medium uppercase tracking-wide">You asked</span>
        {at && (
          <>
            <span aria-hidden className="h-0.5 w-0.5 rounded-full bg-border-strong" />
            <time dateTime={at} className="tabular-nums">{formatDateTime(at)}</time>
          </>
        )}
      </p>
      <Heading ref={headingRef} tabIndex={headingRef ? -1 : undefined} className="whitespace-pre-wrap text-base font-medium leading-snug text-primary focus:outline-none">
        {children}
      </Heading>
    </header>
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

const TITLE_MAX = 80;
const FOCUS_GAP_PX = 16;

/**
 * Keeps keyboard focus clear of the sticky composer (WCAG 2.4.11): sets scroll-padding-bottom to
 * the composer's height and scrolls a newly focused element above it when it lands underneath.
 */
function useComposerClearance(composerRef: RefObject<HTMLElement | null>, enabled: boolean) {
  useEffect(() => {
    const composer = composerRef.current;
    if (!enabled || !composer) return;
    const root = document.documentElement;
    const previous = root.style.scrollPaddingBottom;
    const update = () => {
      root.style.scrollPaddingBottom = `${composer.offsetHeight + FOCUS_GAP_PX}px`;
    };
    update();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(composer);
    const onFocusIn = (event: FocusEvent) => {
      const target = event.target;
      if (!(target instanceof HTMLElement) || composer.contains(target)) return;
      const overlap = target.getBoundingClientRect().bottom - composer.getBoundingClientRect().top;
      if (overlap > 0) window.scrollBy({ top: overlap + FOCUS_GAP_PX });
    };
    document.addEventListener("focusin", onFocusIn);
    return () => {
      observer?.disconnect();
      document.removeEventListener("focusin", onFocusIn);
      root.style.scrollPaddingBottom = previous;
    };
  }, [composerRef, enabled]);
}

/** Names the browser tab after the conversation, so switching conversations is announced. */
function useDocumentTitle(title: string | null) {
  useEffect(() => {
    if (!title) return;
    const short = title.length > TITLE_MAX ? `${title.slice(0, TITLE_MAX - 1)}…` : title;
    document.title = `${short} · Ask MarketSignal · MarketSignal`;
  }, [title]);
}

/** A saved conversation: each question and its answer, the live run if one is going, and the composer. */
export function ConversationView({ ws, conversationId }: { ws: string; conversationId: string }) {
  const valid = isUuid(conversationId);
  const session = useAskSession();
  const { available } = useGenerationAvailable();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const composerRef = useRef<HTMLDivElement>(null);
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

  const active = session.active?.conversationId === conversationId ? session.active : null;
  const firstQuestion = history.data?.find((m) => m.role === "user")?.content ?? active?.question ?? null;
  useDocumentTitle(firstQuestion);
  useComposerClearance(composerRef, available && history.isSuccess);

  // A run started from the intro page navigates here: move focus to the conversation heading.
  const { focusTarget, clearFocusTarget } = session;
  useEffect(() => {
    if (focusTarget !== conversationId || !history.isSuccess) return;
    headingRef.current?.focus();
    clearFocusTarget();
  }, [focusTarget, conversationId, history.isSuccess, clearFocusTarget]);

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
        error={history.error}
      />
    );
  }

  const messages = history.data.filter((m) => !active || m.run_id !== active.runId);
  const turns = toTurns(messages);
  const title = turns.find((t) => t.question)?.question?.content ?? active?.question ?? "Conversation";
  const unansweredTail = !active && turns.length > 0 && turns[turns.length - 1].answer === null;
  return (
    <div className="mx-auto flex w-full max-w-[46rem] flex-col gap-12">
      {turns.length === 0 && (
        <QueryHeader level={1} headingRef={headingRef} at={null}>
          {title}
        </QueryHeader>
      )}
      {turns.length === 0 && !active && (
        <EmptyState title="No questions yet" description="Ask a question below to start this conversation." />
      )}
      {turns.map((turn, i) => {
        const question = turn.question?.content ?? "";
        return (
          <article key={turn.question?.message_id ?? turn.answer?.message_id} className="flex flex-col gap-6">
            {turn.question ? (
              <QueryHeader level={i === 0 ? 1 : 2} headingRef={i === 0 ? headingRef : undefined} at={turn.question.created_at}>
                {question}
              </QueryHeader>
            ) : (
              <h2 className="sr-only">Answer</h2>
            )}
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
        <article className="flex flex-col gap-6">
          {turns.length > 0 && <QueryHeader at={null}>{active.question}</QueryHeader>}
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
      <div ref={composerRef} className={available ? "sticky bottom-0 -mx-1 border-t border-border bg-canvas px-1 pb-4 pt-3" : "border-t border-border pt-6"}>
        <Composer conversationId={conversationId} />
      </div>
    </div>
  );
}
