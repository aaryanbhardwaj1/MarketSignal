"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  cancelRun,
  createConversation,
  listMessages,
  runStreamUrl,
  startRun,
} from "@/lib/api/endpoints";
import type { RunMode } from "@/lib/api/types";
import { ApiError } from "@/lib/api/errors";
import { queryKeys } from "@/lib/api/query-keys";
import { isUuid } from "@/lib/handles";
import { PageHeader } from "../ui/card";
import { ErrorPanel, InlineError } from "../ui/error-panel";
import { buttonClass } from "../ui/form-controls";
import { Loading } from "../ui/loading";
import { AssistantCard, MessageList, UserBubble } from "./message-list";
import { QuestionForm } from "./question-form";
import { RunPanel } from "./run-panel";
import { useRunStream } from "./use-run-stream";

interface ActiveRun {
  conversationId: string;
  runId: string;
  question: string;
  streamUrl: string;
}

const TITLE_MAX = 200;

function chatHref(ws: string, conversationId?: string): string {
  const base = `/w/${encodeURIComponent(ws)}/chat`;
  return conversationId ? `${base}?c=${encodeURIComponent(conversationId)}` : base;
}

export function ChatView({ ws }: { ws: string }) {
  const searchParams = useSearchParams();
  const rawConversation = searchParams.get("c");
  const conversationId = rawConversation && isUuid(rawConversation) ? rawConversation : null;
  const invalidConversation = rawConversation !== null && conversationId === null;

  const queryClient = useQueryClient();
  const [active, setActive] = useState<ActiveRun | null>(null);
  // A run belongs to one conversation; navigating elsewhere detaches (but never cancels) it.
  const activeHere = active && active.conversationId === conversationId ? active : null;
  const { state, connection } = useRunStream(activeHere?.streamUrl ?? null);
  const running = activeHere !== null && !state.done && connection !== "closed";

  const history = useQuery({
    queryKey: queryKeys.messages(ws, conversationId ?? ""),
    queryFn: ({ signal }) => listMessages(ws, conversationId ?? "", signal),
    enabled: conversationId !== null,
  });

  // Once the run settles, the stored turn (user question + verified answer) is the history.
  const settled = activeHere !== null && (state.done !== null || connection === "closed");
  useEffect(() => {
    if (settled && conversationId) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.messages(ws, conversationId) });
    }
  }, [settled, conversationId, ws, queryClient]);

  const start = useMutation({
    mutationFn: async ({ question, mode }: { question: string; mode: RunMode }): Promise<ActiveRun> => {
      let cid = conversationId;
      if (!cid) {
        cid = (await createConversation(ws, { title: question.slice(0, TITLE_MAX) })).conversation_id;
        // Put the conversation in the URL right away so a reload restores it via GET messages.
        window.history.replaceState(null, "", chatHref(ws, cid));
      }
      const run = await startRun(ws, cid, { question, mode });
      const streamUrl = runStreamUrl(run.stream_url);
      if (!streamUrl) {
        throw new ApiError(0, "INVALID_STREAM_URL", "The API returned an unexpected stream URL.");
      }
      return { conversationId: cid, runId: run.run_id, question, streamUrl };
    },
    onSuccess: (run) => setActive(run),
  });

  const cancel = useMutation({ mutationFn: (runId: string) => cancelRun(ws, runId) });

  const ask = async (question: string, mode: RunMode): Promise<boolean> => {
    cancel.reset();
    try {
      await start.mutateAsync({ question, mode });
      return true;
    } catch {
      return false; // surfaced via start.error
    }
  };

  const messages = (history.data ?? []).filter(
    (m) => !activeHere || m.run_id !== activeHere.runId,
  );
  // A trailing question without an answer: the run is still going (e.g. after a reload) or died.
  const unansweredTail = !activeHere && messages.at(-1)?.role === "user";

  return (
    <>
      <PageHeader
        eyebrow={ws}
        title="Chat"
        description="Ask questions answered only from this workspace's evidence. Every claim links to its source span; inferences and gaps are labelled."
        actions={
          (conversationId || invalidConversation) && (
            <Link href={chatHref(ws)} className={buttonClass("secondary", "sm")}>
              New conversation
            </Link>
          )
        }
      />
      {invalidConversation && (
        <p role="alert" className="text-sm text-amber-700">
          Ignored conversation parameter: not a valid conversation id.
        </p>
      )}

      <div className="flex flex-col gap-4">
        {conversationId && history.isPending && <Loading label="Loading conversation..." />}
        {history.isError && <ErrorPanel error={history.error} title="Could not load this conversation" />}
        <MessageList ws={ws} messages={messages} />
        {unansweredTail && (
          <p className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
            No stored answer for the last question yet — it may still be running.
            <button
              type="button"
              onClick={() => void history.refetch()}
              disabled={history.isFetching}
              className={buttonClass("ghost", "sm")}
            >
              {history.isFetching ? "Refreshing…" : "Refresh"}
            </button>
          </p>
        )}
        {activeHere && (
          <>
            <UserBubble>{activeHere.question}</UserBubble>
            <AssistantCard>
              <RunPanel
                ws={ws}
                state={state}
                connection={connection}
                cancelling={cancel.isPending}
                onCancel={() => cancel.mutate(activeHere.runId)}
              />
              {cancel.isError && <InlineError error={cancel.error} />}
            </AssistantCard>
          </>
        )}
        {!conversationId && !activeHere && !invalidConversation && (
          <p className="text-sm text-slate-500">
            Start a conversation by asking a question below.
          </p>
        )}
      </div>

      <div className="sticky bottom-0 -mx-4 border-t border-slate-200 bg-background/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        {start.isError && <InlineError error={start.error} />}
        <QuestionForm disabled={running || history.isError} busy={start.isPending} onSubmit={ask} />
      </div>
    </>
  );
}
