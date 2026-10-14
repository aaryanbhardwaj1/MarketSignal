"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { cancelRun, createConversation, runStreamUrl, startRun } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/errors";
import { coreKeys } from "@/lib/api/hooks/core";
import { queryKeys } from "@/lib/api/query-keys";
import type { RunMode } from "@/lib/api/types";
import { isProviderUnavailableError } from "@/lib/model-availability";
import type { RunStreamState } from "@/lib/run-stream";
import { askHref } from "@/lib/routes";
import { AttachmentsProvider } from "./attachments/attachments-context";
import { useRunStream, type StreamConnection } from "./use-run-stream";

const TITLE_MAX = 200;

export interface ActiveRun {
  conversationId: string;
  runId: string;
  question: string;
  streamUrl: string;
}

export interface Prefill {
  text: string;
  mode: RunMode;
  /** Changes on every request so the composer remounts with the new text. */
  nonce: number;
  /** Move focus to the composer when it remounts (set by an explicit "fill the composer" action). */
  focus: boolean;
}

export interface AskSession {
  ws: string;
  active: ActiveRun | null;
  state: RunStreamState;
  connection: StreamConnection;
  running: boolean;
  starting: boolean;
  /** A start failed for a reason other than the model being unavailable. */
  startError: unknown;
  /** `POST /conversations` or `POST /runs` came back 503 `PROVIDER_UNAVAILABLE`: show the calm "Live model unavailable" state, never an error. */
  providerUnavailable: boolean;
  cancelling: boolean;
  cancelError: unknown;
  prefill: Prefill;
  ask: (question: string, mode: RunMode, conversationId: string | null) => Promise<boolean>;
  cancel: () => void;
  fillComposer: (text: string, mode?: RunMode) => void;
  /** Conversation that was just opened by starting a run; its view moves focus to its heading. */
  focusTarget: string | null;
  clearFocusTarget: () => void;
  /** The composer took focus after a fill; later remounts (e.g. navigation) must not steal it. */
  composerFocused: () => void;
}

const AskSessionContext = createContext<AskSession | null>(null);

export function useAskSession(): AskSession {
  const value = useContext(AskSessionContext);
  if (!value) throw new Error("useAskSession must be used inside AskSessionProvider");
  return value;
}

/**
 * Holds the live run for Ask MarketSignal. It lives in the Ask layout, so a run started from the
 * intro page keeps streaming after navigating to its new conversation.
 */
export function AskSessionProvider({ ws, children }: { ws: string; children: ReactNode }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [active, setActive] = useState<ActiveRun | null>(null);
  const [providerUnavailable, setProviderUnavailable] = useState(false);
  const [prefill, setPrefill] = useState<Prefill>({ text: "", mode: "auto", nonce: 0, focus: false });
  const [focusTarget, setFocusTarget] = useState<string | null>(null);
  const { state, connection } = useRunStream(active?.streamUrl ?? null);
  const running = active !== null && !state.done && connection !== "closed";
  const settled = active !== null && (state.done !== null || connection === "closed");

  useEffect(() => {
    if (!settled || !active) return;
    void queryClient.invalidateQueries({ queryKey: queryKeys.messages(ws, active.conversationId) });
    void queryClient.invalidateQueries({ queryKey: coreKeys.conversationLists(ws) });
  }, [settled, active, ws, queryClient]);

  const start = useMutation({
    mutationFn: async (input: { question: string; mode: RunMode; conversationId: string | null }) => {
      const cid =
        input.conversationId ??
        (await createConversation(ws, { title: input.question.slice(0, TITLE_MAX) })).conversation_id;
      const run = await startRun(ws, cid, { question: input.question, mode: input.mode });
      const streamUrl = runStreamUrl(run.stream_url);
      if (!streamUrl) throw new ApiError(0, "INVALID_STREAM_URL", "The API returned an unexpected stream URL.");
      return { conversationId: cid, runId: run.run_id, question: input.question, streamUrl };
    },
    onSuccess: (run, input) => {
      setActive(run);
      if (input.conversationId !== run.conversationId) {
        setFocusTarget(run.conversationId);
        router.push(askHref(ws, run.conversationId));
      }
    },
    onError: (error) => {
      if (isProviderUnavailableError(error)) setProviderUnavailable(true);
    },
  });
  const cancelMutation = useMutation({ mutationFn: (runId: string) => cancelRun(ws, runId) });

  const { mutateAsync } = start;
  const { reset: resetCancel, mutate: mutateCancel } = cancelMutation;
  const ask = useCallback(
    async (question: string, mode: RunMode, conversationId: string | null) => {
      resetCancel();
      try {
        await mutateAsync({ question, mode, conversationId });
        return true;
      } catch {
        return false; // surfaced via startError / providerUnavailable
      }
    },
    [mutateAsync, resetCancel],
  );
  const cancel = useCallback(() => {
    if (active) mutateCancel(active.runId);
  }, [active, mutateCancel]);
  const fillComposer = useCallback((text: string, mode: RunMode = "auto") => {
    setPrefill((p) => ({ text, mode, nonce: p.nonce + 1, focus: true }));
  }, []);
  const clearFocusTarget = useCallback(() => setFocusTarget(null), []);
  const composerFocused = useCallback(() => setPrefill((p) => (p.focus ? { ...p, focus: false } : p)), []);

  const startError = start.error && !isProviderUnavailableError(start.error) ? start.error : null;
  const value = useMemo<AskSession>(
    () => ({
      ws,
      active,
      state,
      connection,
      running,
      starting: start.isPending,
      startError,
      providerUnavailable,
      cancelling: cancelMutation.isPending,
      cancelError: cancelMutation.error,
      prefill,
      ask,
      cancel,
      fillComposer,
      focusTarget,
      clearFocusTarget,
      composerFocused,
    }),
    [ws, active, state, connection, running, start.isPending, startError, providerUnavailable, cancelMutation.isPending, cancelMutation.error, prefill, ask, cancel, fillComposer, focusTarget, clearFocusTarget, composerFocused],
  );
  return (
    <AskSessionContext.Provider value={value}>
      <AttachmentsProvider ws={ws}>{children}</AttachmentsProvider>
    </AskSessionContext.Provider>
  );
}
