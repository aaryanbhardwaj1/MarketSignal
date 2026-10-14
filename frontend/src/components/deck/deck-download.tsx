"use client";

import { CircleCheck, Download } from "lucide-react";
import { useEffect, useReducer, useRef } from "react";
import { Button } from "@/components/ui/button";
import type { DeckRequest } from "@/lib/api/contracts";
import { downloadDeckPptx } from "@/lib/api/hooks/decks";
import { deckErrorMessage, isAbort } from "./deck-view";
import { downloadReducer, type DownloadState } from "./generation";

export type DeckDownloader = typeof downloadDeckPptx;

/**
 * "Download .pptx": renders the deck on the server and saves it. The saved state appears only
 * after the browser was handed the file; failures are shown in plain words with a retry.
 */
export function DeckDownload({
  ws,
  body,
  initial = { status: "idle" },
  download = downloadDeckPptx,
}: {
  ws: string;
  body: DeckRequest;
  initial?: DownloadState;
  download?: DeckDownloader;
}) {
  const [state, dispatch] = useReducer(downloadReducer, initial);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  const start = async () => {
    controller.current?.abort();
    const ctrl = new AbortController();
    controller.current = ctrl;
    dispatch({ type: "begin" });
    try {
      const saved = await download(ws, body, ctrl.signal);
      dispatch({ type: "saved", filename: saved.filename });
    } catch (error) {
      dispatch(isAbort(error) ? { type: "cancel" } : { type: "failed", message: deckErrorMessage(error) });
    }
  };

  const saving = state.status === "saving";
  return (
    <div className="flex flex-col items-start gap-2 sm:items-end">
      <Button
        variant={state.status === "saved" ? "secondary" : "primary"}
        loading={saving}
        iconLeft={<Download aria-hidden size={16} />}
        onClick={() => void start()}
      >
        {saving ? "Preparing file…" : state.status === "saved" ? "Download again" : "Download .pptx"}
      </Button>
      <p role="status" aria-live="polite" className="text-sm">
        {state.status === "saved" && (
          <span className="inline-flex items-center gap-1.5 text-secondary">
            <CircleCheck aria-hidden size={14} className="text-success" />
            Saved <span className="font-medium text-primary">{state.filename}</span>
          </span>
        )}
        {state.status === "failed" && <span className="text-danger">The file could not be created. {state.message}</span>}
      </p>
    </div>
  );
}
