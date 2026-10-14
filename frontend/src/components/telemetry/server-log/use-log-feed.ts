"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ServerLogEntry, ServerLogParams, ServerLogResponse } from "@/lib/api/contracts";
import { getServerLogs, useServerLogs } from "@/lib/api/hooks/telemetry";
import { POLL_LIMIT, POLL_MS, SNAPSHOT_LIMIT, mergeLogEntries, nextCursor } from "./log-model";

interface Appended {
  key: string;
  entries: ServerLogEntry[];
  meta: ServerLogResponse | null;
}

export interface LogFeed {
  entries: ServerLogEntry[];
  meta: ServerLogResponse | null;
  isPending: boolean;
  error: unknown;
  refetch: () => void;
}

const isHidden = (): boolean => typeof document !== "undefined" && document.visibilityState === "hidden";

/**
 * Server log feed: a newest-first snapshot (React Query), then, while `live`, incremental polls
 * with `after_seq` every 2 s, appended into a bounded, de-duplicated, ascending buffer. Polling
 * pauses while the tab is hidden; a new filter set (`key`) starts a fresh buffer.
 */
export function useLogFeed(params: ServerLogParams, key: string, live: boolean): LogFeed {
  const snapshot = useServerLogs({ ...params, limit: SNAPSHOT_LIMIT });
  const [appended, setAppended] = useState<Appended>({ key, entries: [], meta: null });
  const cursor = useRef<number | null>(null);
  const startedAt = useRef<string | null>(null);
  const { refetch } = snapshot;

  // A new filter set: forget the previous cursor (the snapshot effect below sets the next one;
  // declared first so a cached snapshot for the new key is not wiped).
  useEffect(() => {
    cursor.current = null;
    startedAt.current = null;
  }, [key]);

  // The snapshot defines the starting cursor for this filter set.
  useEffect(() => {
    const data = snapshot.data;
    if (!data) return;
    cursor.current = nextCursor(cursor.current, data, SNAPSHOT_LIMIT, false);
    startedAt.current = data.process_started_at;
  }, [snapshot.data]);

  const paramsJson = JSON.stringify(params);
  useEffect(() => {
    if (!live) return;
    const query = JSON.parse(paramsJson) as ServerLogParams;
    let inFlight = false;
    const controller = new AbortController();
    const tick = async () => {
      if (inFlight || isHidden() || cursor.current == null) return;
      inFlight = true;
      try {
        const res = await getServerLogs({ ...query, after_seq: cursor.current, limit: POLL_LIMIT }, controller.signal);
        if (startedAt.current && res.process_started_at !== startedAt.current) {
          // The API process restarted: sequence numbers began again. Start over.
          cursor.current = null;
          setAppended({ key, entries: [], meta: null });
          void refetch();
          return;
        }
        cursor.current = nextCursor(cursor.current, res, POLL_LIMIT, true);
        setAppended((prev) => ({
          key,
          entries: mergeLogEntries(prev.key === key ? prev.entries : [], res.entries),
          meta: res,
        }));
      } catch {
        // A failed poll is retried on the next tick; the snapshot query reports hard errors.
      } finally {
        inFlight = false;
      }
    };
    const id = window.setInterval(() => void tick(), POLL_MS);
    const onVisible = () => {
      if (!isHidden()) void tick();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      controller.abort();
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [live, key, paramsJson, refetch]);

  const own = appended.key === key ? appended : null;
  const entries = useMemo(
    () => mergeLogEntries(snapshot.data?.entries ?? [], own?.entries ?? []),
    [snapshot.data, own?.entries],
  );
  const meta = own?.meta ?? snapshot.data ?? null;

  return {
    entries,
    meta,
    isPending: snapshot.isPending,
    error: snapshot.error,
    refetch: () => void refetch(),
  };
}
