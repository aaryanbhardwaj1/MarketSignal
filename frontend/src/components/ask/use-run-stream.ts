"use client";

import { useEffect, useReducer } from "react";
import {
  RUN_EVENT_TYPES,
  initialRunStreamState,
  parseRunEvent,
  reduceRunEvent,
  type RunEvent,
  type RunStreamState,
} from "@/lib/run-stream";

export type StreamConnection = "connecting" | "open" | "reconnecting" | "closed";

/** Consecutive EventSource errors (without any event in between) before giving up. */
const MAX_RECONNECT_ERRORS = 6;

interface StreamStore {
  url: string | null;
  run: RunStreamState;
  connection: StreamConnection;
}

type StreamAction =
  | { url: string; kind: "event"; event: RunEvent }
  | { url: string; kind: "connection"; connection: StreamConnection };

const EMPTY: StreamStore = { url: null, run: initialRunStreamState, connection: "connecting" };

/** State is tagged with the stream URL so a new run starts from a clean slate without a reset. */
function streamReducer(store: StreamStore, action: StreamAction): StreamStore {
  const base = store.url === action.url ? store : { ...EMPTY, url: action.url };
  if (action.kind === "connection") {
    return base.connection === action.connection ? base : { ...base, connection: action.connection };
  }
  const run = reduceRunEvent(base.run, action.event);
  if (run === base.run && base === store) return store;
  return { ...base, run, connection: "open" };
}

export interface RunStream {
  state: RunStreamState;
  connection: StreamConnection;
}

/**
 * Subscribes to a run's SSE stream. Native EventSource reconnects with Last-Event-ID and the
 * server replays the missed events; the pure reducer drops any seq it has already applied.
 * The stream is closed on `done` (otherwise EventSource would reconnect forever).
 */
export function useRunStream(url: string | null): RunStream {
  const [store, dispatch] = useReducer(streamReducer, EMPTY);

  useEffect(() => {
    if (!url) return;
    const source = new EventSource(url);
    let errors = 0;
    const listeners = RUN_EVENT_TYPES.map((type) => {
      const listener = (message: MessageEvent<string>) => {
        errors = 0;
        const event = parseRunEvent(type, message.data, message.lastEventId);
        if (event) dispatch({ url, kind: "event", event });
        if (type === "done") {
          source.close();
          dispatch({ url, kind: "connection", connection: "closed" });
        }
      };
      source.addEventListener(type, listener);
      return [type, listener] as const;
    });
    source.onopen = () => dispatch({ url, kind: "connection", connection: "open" });
    source.onerror = () => {
      errors += 1;
      if (source.readyState === EventSource.CLOSED || errors >= MAX_RECONNECT_ERRORS) {
        source.close();
        dispatch({ url, kind: "connection", connection: "closed" });
      } else {
        dispatch({ url, kind: "connection", connection: "reconnecting" });
      }
    };
    return () => {
      for (const [type, listener] of listeners) source.removeEventListener(type, listener);
      source.close();
    };
  }, [url]);

  const current = url && store.url === url ? store : { ...EMPTY, url };
  return { state: current.run, connection: current.connection };
}
