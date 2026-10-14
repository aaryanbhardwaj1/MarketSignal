"use client";

/**
 * Grounded deck hooks (E14): preview a deck composed from selected brief items
 * (`POST /decks/preview`) and download it as PowerPoint (`POST /decks/pptx`). The backend
 * re-verifies the brief on every request, so a preview can list `excluded` items; a download
 * whose every item failed re-verification is a 422 `DECK_EMPTY`. Unknown ids are a 422
 * `DECK_ITEMS_NOT_FOUND` with `details.unknown`. All failures surface as `ApiError`.
 */

import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import { filenameFromDisposition, saveBlob } from "../../download";
import { apiRequest, buildUrl } from "../client";
import { API_BASE_URL } from "../config";
import type { DeckPreviewResponse, DeckRequest } from "../contracts";
import { ApiError, NETWORK_ERROR, parseApiError } from "../errors";

export const PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation";
export const DEFAULT_DECK_FILENAME = "marketsignal-deck.pptx";

const decksPath = (ws: string): string => `/api/workspaces/${encodeURIComponent(ws)}/decks`;

export async function previewDeck(
  ws: string,
  body: DeckRequest,
  signal?: AbortSignal,
): Promise<DeckPreviewResponse> {
  const res = await apiRequest<DeckPreviewResponse>(`${decksPath(ws)}/preview`, {
    method: "POST",
    json: body,
    signal,
  });
  return res.data;
}

/** Composes the deck without rendering it; call `mutate(body)` / `mutateAsync(body)`. */
export function useDeckPreview(ws: string): UseMutationResult<DeckPreviewResponse, Error, DeckRequest> {
  return useMutation({ mutationFn: (body: DeckRequest) => previewDeck(ws, body) });
}

async function errorBody(res: Response): Promise<unknown> {
  try {
    const text = await res.text();
    return text ? (JSON.parse(text) as unknown) : null;
  } catch {
    return null;
  }
}

export interface DeckDownload {
  filename: string;
  bytes: number;
}

/** Renders the deck server-side and saves it through a temporary object URL. */
export async function downloadDeckPptx(ws: string, body: DeckRequest, signal?: AbortSignal): Promise<DeckDownload> {
  let res: Response;
  try {
    res = await fetch(buildUrl(`${decksPath(ws)}/pptx`), {
      method: "POST",
      headers: { Accept: `${PPTX_MIME}, application/json`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
      cache: "no-store",
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, NETWORK_ERROR, `Cannot reach the API at ${API_BASE_URL}`);
  }
  if (!res.ok) throw parseApiError(res.status, await errorBody(res), res.statusText);
  const blob = await res.blob();
  const filename = filenameFromDisposition(res.headers.get("content-disposition"), DEFAULT_DECK_FILENAME);
  saveBlob(blob, filename);
  return { filename, bytes: blob.size };
}
