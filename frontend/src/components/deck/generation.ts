/**
 * Deck generation progress as a pure reducer driven by the real request lifecycle.
 *
 * Stages 1-4 are labels for the server's composition steps and cover the preview request:
 * a slow tick walks them while the request is in flight but never marks "Building slides" done
 * before the server answers; once it answers, the remaining stages complete in quick sequence
 * (or at once with reduced motion). Stage 5 is the .pptx request and is done only when the file
 * has been saved. Nothing here waits longer than the requests themselves.
 */

import type { Stage, StageState } from "@/components/motion/stage-progress";

export const GENERATION_STAGES = [
  { id: "structure", label: "Structuring findings" },
  { id: "evidence", label: "Selecting supporting evidence" },
  { id: "narrative", label: "Creating narrative" },
  { id: "slides", label: "Building slides" },
  { id: "finalize", label: "Finalizing presentation" },
] as const;

/** Composition stages (1-4) walked while the preview request runs. */
export const COMPOSE_STAGES = 4;
/** Tick while waiting for the server; and the quick catch-up once it has answered. */
export const SLOW_TICK_MS = 600;
export const FAST_TICK_MS = 140;

export type RequestState = "idle" | "pending" | "ok" | "failed";

export interface GenerationState {
  /** Composition stages shown as done (0..4). */
  shown: number;
  preview: RequestState;
  file: RequestState;
}

export type GenerationEvent =
  | { type: "start" }
  | { type: "tick" }
  | { type: "settle" }
  | { type: "preview_ok" }
  | { type: "preview_failed" }
  | { type: "file_start" }
  | { type: "file_ok" }
  | { type: "file_failed" }
  | { type: "reset" };

export const IDLE_GENERATION: GenerationState = { shown: 0, preview: "idle", file: "idle" };

export function generationReducer(state: GenerationState, event: GenerationEvent): GenerationState {
  switch (event.type) {
    case "start":
      return { shown: 0, preview: "pending", file: "idle" };
    case "tick": {
      // While the server composes, the last composition stage stays active.
      const cap = state.preview === "ok" ? COMPOSE_STAGES : state.preview === "pending" ? COMPOSE_STAGES - 1 : state.shown;
      return state.shown < cap ? { ...state, shown: state.shown + 1 } : state;
    }
    case "settle":
      return state.preview === "ok" ? { ...state, shown: COMPOSE_STAGES } : state;
    case "preview_ok":
      return state.preview === "pending" ? { ...state, preview: "ok" } : state;
    case "preview_failed":
      return state.preview === "pending" ? { ...state, preview: "failed" } : state;
    case "file_start":
      return state.preview === "ok" ? { ...state, file: "pending" } : state;
    case "file_ok":
      return state.file === "pending" ? { ...state, file: "ok" } : state;
    case "file_failed":
      return state.file === "pending" ? { ...state, file: "failed" } : state;
    case "reset":
      return IDLE_GENERATION;
  }
}

/** Whether the visible stages still need ticks (and how fast). Null: nothing to advance. */
export function nextTickMs(state: GenerationState): number | null {
  if (state.preview === "pending") return state.shown < COMPOSE_STAGES - 1 ? SLOW_TICK_MS : null;
  if (state.preview === "ok" && state.shown < COMPOSE_STAGES) return FAST_TICK_MS;
  return null;
}

export type GenerationPhase = "idle" | "running" | "done" | "failed";

/** Overall phase; "done"/"failed" only once the stage display has caught up with the requests. */
export function generationPhase(state: GenerationState): GenerationPhase {
  if (state.preview === "idle") return "idle";
  if (state.preview === "failed") return "failed";
  if (state.shown < COMPOSE_STAGES) return "running";
  if (state.file === "ok") return "done";
  if (state.file === "failed") return "failed";
  return "running";
}

function composeState(state: GenerationState, i: number): StageState {
  if (i < state.shown) return "done";
  if (i > state.shown) return "pending";
  if (state.preview === "failed") return "failed";
  return state.preview === "idle" ? "pending" : "active";
}

function fileState(state: GenerationState): StageState {
  if (state.shown < COMPOSE_STAGES) return "pending";
  if (state.file === "ok") return "done";
  if (state.file === "failed") return "failed";
  return state.file === "pending" ? "active" : "pending";
}

/** The five stages for `StageProgress`. */
export function generationStages(state: GenerationState): Stage[] {
  return GENERATION_STAGES.map((s, i) => ({
    id: s.id,
    label: s.label,
    state: i < COMPOSE_STAGES ? composeState(state, i) : fileState(state),
  }));
}

// ── download button ────────────────────────────────────────────────────────────────────────

export type DownloadState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "saved"; filename: string }
  | { status: "failed"; message: string };

export type DownloadEvent =
  | { type: "begin" }
  | { type: "saved"; filename: string }
  | { type: "failed"; message: string }
  | { type: "cancel" };

export function downloadReducer(state: DownloadState, event: DownloadEvent): DownloadState {
  switch (event.type) {
    case "begin":
      return state.status === "saving" ? state : { status: "saving" };
    case "saved":
      return state.status === "saving" ? { status: "saved", filename: event.filename } : state;
    case "failed":
      return state.status === "saving" ? { status: "failed", message: event.message } : state;
    case "cancel":
      return state.status === "saving" ? { status: "idle" } : state;
  }
}
