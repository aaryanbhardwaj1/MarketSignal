"use client";

import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowDown } from "lucide-react";
import type { ServerLogEntry, ServerLogResponse } from "@/lib/api/contracts";
import { ApiError } from "@/lib/api/errors";
import { EmptyState, ErrorState, LoadingRegion } from "@/components/ui/states";
import { formatDateTime, formatNumber } from "@/lib/format";
import { DEFAULT_LOG_FILTERS, LOG_BUFFER_LIMIT, filterKey, filtersToParams, isAtBottom, type LogFilters } from "./log-model";
import { LogHeader, LogRow } from "./log-row";
import { LogToolbar } from "./log-toolbar";
import { useLogFeed } from "./use-log-feed";

export const LOG_EMPTY_TEXT = "No log entries match these filters.";
export const WORKER_NOTE = "worker logs are kept by the worker process";

/** "API process log · since … · size/capacity entries · dropped · worker note" (response fields only). */
export function logFooterText(meta: ServerLogResponse): string {
  const parts = [
    "API process log",
    `since ${formatDateTime(meta.process_started_at)}`,
    `${formatNumber(meta.size)}/${formatNumber(meta.capacity)} entries`,
    `${formatNumber(meta.dropped)} dropped`,
  ];
  if (meta.capture_errors > 0) parts.push(`${formatNumber(meta.capture_errors)} capture errors`);
  parts.push(WORKER_NOTE);
  return parts.join(" · ");
}

function LevelCounts({ levels }: { levels: ServerLogResponse["levels"] }) {
  const errors = (levels.ERROR ?? 0) + (levels.CRITICAL ?? 0);
  const warnings = levels.WARNING ?? 0;
  return (
    <span className="tabular-nums">
      <span className={errors ? "text-danger" : undefined}>{formatNumber(errors)} errors</span>
      {" · "}
      <span className={warnings ? "text-warn" : undefined}>{formatNumber(warnings)} warnings</span>
    </span>
  );
}

export interface ServerLogViewProps {
  entries: readonly ServerLogEntry[];
  meta: ServerLogResponse | null;
  ws: string | null;
  expanded: ReadonlySet<number>;
  onToggle: (seq: number) => void;
  onFilter: (id: string) => void;
  /** Scroll container wiring (absent in static renders). */
  scrollRef?: React.Ref<HTMLDivElement>;
  onScroll?: () => void;
  showJump?: boolean;
  onJump?: () => void;
}

/** The console surface: column header, rows, "Jump to latest" pill and the footer line. */
export function ServerLogView({ entries, meta, ws, expanded, onToggle, onFilter, scrollRef, onScroll, showJump, onJump }: ServerLogViewProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-sunken">
      <div className="relative">
        <div ref={scrollRef} onScroll={onScroll} className="max-h-[32rem] min-h-48 overflow-auto font-mono text-xs">
          <div className="min-w-[60rem]">
            <LogHeader />
            {entries.length === 0 ? (
              <p className="px-4 py-10 text-center font-sans text-sm text-muted">{LOG_EMPTY_TEXT}</p>
            ) : (
              <ol aria-label="Server log entries, oldest first">
                {entries.map((e) => (
                  <LogRow key={e.seq} entry={e} expanded={expanded.has(e.seq)} onToggle={onToggle} onFilter={onFilter} ws={ws} />
                ))}
              </ol>
            )}
          </div>
        </div>
        {showJump && (
          <button
            type="button"
            onClick={onJump}
            className="ms-pop-in absolute bottom-3 left-1/2 inline-flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-border bg-raised px-3 py-1 text-sm font-medium text-primary shadow-raised hover:bg-surface focus-visible:outline-2 focus-visible:outline-accent-ring"
          >
            <ArrowDown aria-hidden className="size-3.5" />
            Jump to latest
          </button>
        )}
      </div>
      {meta && (
        <p className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t border-border px-3 py-1.5 text-xs text-muted">
          <span>{logFooterText(meta)}</span>
          <span className="tabular-nums">
            {formatNumber(entries.length)} shown{entries.length >= LOG_BUFFER_LIMIT ? ` (latest ${formatNumber(LOG_BUFFER_LIMIT)} kept)` : ""} ·{" "}
            <LevelCounts levels={meta.levels} />
          </span>
        </p>
      )}
    </div>
  );
}

function useStickyScroll(count: number) {
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const [atBottom, setAtBottom] = useState(true);
  useLayoutEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [count]);
  const onScroll = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const bottom = isAtBottom(el);
    stick.current = bottom;
    setAtBottom(bottom);
  }, []);
  const jump = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    stick.current = true;
    setAtBottom(true);
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, []);
  return { ref, onScroll, atBottom, jump };
}

/**
 * Developer server log viewer for the API process (E12). Filters map 1:1 to query params; live
 * mode appends new entries every 2 s and pauses while the tab is hidden. Only fields present in
 * the response are rendered.
 */
export function ServerLogViewer({ ws: wsProp }: { ws?: string } = {}) {
  const params = useParams<{ ws?: string }>();
  const ws = wsProp ?? params?.ws ?? null;
  const [filters, setFilters] = useState<LogFilters>(DEFAULT_LOG_FILTERS);
  const [live, setLive] = useState(true);
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(new Set());
  const key = filterKey(filters);
  const feed = useLogFeed(filtersToParams(filters), key, live);
  const scroll = useStickyScroll(feed.entries.length);

  const toggle = useCallback((seq: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(seq)) next.delete(seq);
      else next.add(seq);
      return next;
    });
  }, []);
  const filterBy = useCallback((id: string) => setFilters((f) => ({ ...f, q: id })), []);

  let body: React.ReactNode;
  if (feed.isPending) {
    body = <LoadingRegion label="Loading server log" lines={6} />;
  } else if (feed.error && !feed.meta) {
    const notMounted = feed.error instanceof ApiError && feed.error.status === 404;
    body = notMounted ? (
      <EmptyState
        title="Server log is not available"
        description="The API process does not expose its log here. Developer endpoints are mounted only outside production."
        size="sm"
      />
    ) : (
      <ErrorState title="Server log could not be loaded" description="The API did not respond. Try again." retry={feed.refetch} />
    );
  } else {
    body = (
      <ServerLogView
        entries={feed.entries}
        meta={feed.meta}
        ws={ws}
        expanded={expanded}
        onToggle={toggle}
        onFilter={filterBy}
        scrollRef={scroll.ref}
        onScroll={scroll.onScroll}
        showJump={!scroll.atBottom && feed.entries.length > 0}
        onJump={scroll.jump}
      />
    );
  }

  return (
    <section aria-label="Server logs" className="flex flex-col gap-3">
      <LogToolbar
        filters={filters}
        routes={feed.meta?.routes ?? []}
        live={live}
        onChange={setFilters}
        onLiveChange={setLive}
        onRefresh={feed.refetch}
      />
      {body}
    </section>
  );
}
