"use client";

import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type { Deck, DeckPreviewResponse, DeckRequest } from "@/lib/api/contracts";
import { downloadDeckPptx, previewDeck } from "@/lib/api/hooks/decks";
import { deckErrorMessage, isAbort } from "./deck-view";
import {
  generationPhase,
  generationReducer,
  generationStages,
  IDLE_GENERATION,
  nextTickMs,
  type DownloadState,
  type GenerationPhase,
} from "./generation";
import type { Stage } from "@/components/motion/stage-progress";

export const OUTLINE_DEBOUNCE_MS = 450;

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

/** Server preview behind the live outline, re-requested (debounced) as the selection changes. */
export function useOutlinePreview(ws: string, body: DeckRequest | null): UseQueryResult<DeckPreviewResponse> & { settling: boolean } {
  const key = body ? JSON.stringify(body) : null;
  const debounced = useDebounced(key, OUTLINE_DEBOUNCE_MS);
  const query = useQuery({
    queryKey: ["workspace", ws, "decks", "preview", debounced],
    queryFn: ({ signal }) => previewDeck(ws, JSON.parse(debounced as string) as DeckRequest, signal),
    enabled: Boolean(ws && debounced),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    retry: false,
  });
  return Object.assign(query, { settling: key !== debounced });
}

function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

export interface DeckGeneration {
  phase: GenerationPhase;
  stages: Stage[];
  deck: Deck | null;
  /** Download outcome of the generation run (seeds the Download button). */
  file: DownloadState;
  error: string | null;
  start: (body: DeckRequest) => void;
  cancel: () => void;
}

/**
 * Generate = compose the deck (`/decks/preview`, stages 1-4) then render and save the file
 * (`/decks/pptx`, stage 5). Stages advance from the real request lifecycle (see `generation`).
 */
export function useDeckGeneration(ws: string): DeckGeneration {
  const [state, dispatch] = useReducer(generationReducer, IDLE_GENERATION);
  const [deck, setDeck] = useState<Deck | null>(null);
  const [file, setFile] = useState<DownloadState>({ status: "idle" });
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  useEffect(() => {
    const ms = nextTickMs(state);
    if (ms === null) return;
    if (state.preview === "ok" && prefersReducedMotion()) {
      dispatch({ type: "settle" });
      return;
    }
    const id = setTimeout(() => dispatch({ type: "tick" }), ms);
    return () => clearTimeout(id);
  }, [state]);

  const start = useCallback(
    (body: DeckRequest) => {
      controller.current?.abort();
      const ctrl = new AbortController();
      controller.current = ctrl;
      setDeck(null);
      setError(null);
      setFile({ status: "idle" });
      dispatch({ type: "start" });
      void (async () => {
        try {
          const res = await previewDeck(ws, body, ctrl.signal);
          setDeck(res.deck);
          dispatch({ type: "preview_ok" });
        } catch (cause) {
          if (isAbort(cause)) return;
          setError(deckErrorMessage(cause));
          dispatch({ type: "preview_failed" });
          return;
        }
        dispatch({ type: "file_start" });
        setFile({ status: "saving" });
        try {
          const saved = await downloadDeckPptx(ws, body, ctrl.signal);
          setFile({ status: "saved", filename: saved.filename });
          dispatch({ type: "file_ok" });
        } catch (cause) {
          if (isAbort(cause)) return;
          setFile({ status: "failed", message: deckErrorMessage(cause) });
          dispatch({ type: "file_failed" });
        }
      })();
    },
    [ws],
  );

  const cancel = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    dispatch({ type: "reset" });
  }, []);

  return { phase: generationPhase(state), stages: generationStages(state), deck, file, error, start, cancel };
}
