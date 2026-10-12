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

const TITLE_MAX = 80;
const FOCUS_GAP_PX = 16;

function Header({ title, meta, headingRef }: { title: string; meta?: string; headingRef: RefObject<HTMLHeadingElement | null> }) {
  return (
    <header className="border-b border-border pb-4">
      <p className="text-sm text-muted">Ask MarketSignal</p>
      <h1 ref={headingRef} tabIndex={-1} className="mt-1 text-lg font-semibold leading-snug text-primary focus:outline-none">
        {title}
      </h1>
      {meta && <p className="mt-1 text-sm text-muted">{meta}</p>}
    </header>
  );
}

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
  const first = history.data[0];
  const meta = first ? `Asked ${formatDateTime(first.created_at)}` : undefined;

  return (
    <div className="flex flex-col gap-8">
      <Header title={title} meta={meta} headingRef={headingRef} />
      {turns.length === 0 && !active && (
        <EmptyState title="No questions yet" description="Ask a question below to start this conversation." />
      )}
      {turns.map((turn, i) => {
        const question = turn.question?.content ?? "";
        return (
          <article key={turn.question?.message_id ?? turn.answer?.message_id} className="flex flex-col gap-5">
            <h2 className="sr-only">{i === 0 ? "Answer" : `Follow-up question ${i}`}</h2>
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
          <h2 className="sr-only">{turns.length > 0 ? "Latest question" : "Answer"}</h2>
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
      <div ref={composerRef} className={available ? "sticky bottom-0 -mx-1 border-t border-border bg-canvas px-1 pb-4 pt-3" : "border-t border-border pt-6"}>
        <Composer conversationId={conversationId} />
      </div>
    </div>
  );
}
