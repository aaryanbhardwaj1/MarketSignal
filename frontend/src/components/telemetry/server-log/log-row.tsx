"use client";

import Link from "next/link";
import { ArrowUpRight, ChevronRight } from "lucide-react";
import type { ServerLogEntry } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import { formatMs } from "@/lib/format";
import { telemetryRunHref } from "@/lib/routes";
import {
  TONE_TEXT,
  formatLogTime,
  levelLabel,
  levelTone,
  logDetailRows,
  logSubject,
  methodTone,
  shortCorrelation,
  statusTone,
} from "./log-model";

/** Shared column template for the header and every row. */
export const LOG_GRID =
  "grid grid-cols-[1.25rem_6.75rem_3.75rem_5.5rem_3.75rem_minmax(0,1fr)_3rem_4.5rem_9.5rem] items-center gap-x-3";

const LEVEL_CHIP: Record<string, string> = {
  neutral: "border-border-strong text-secondary",
  warn: "border-warn/40 bg-warn-subtle text-warn",
  danger: "border-danger/40 bg-danger-subtle text-danger",
};

export function LogHeader() {
  return (
    <div
      aria-hidden
      className={cx(
        LOG_GRID,
        "sticky top-0 z-10 border-b border-border bg-sunken px-3 py-1.5 font-sans text-2xs font-medium uppercase tracking-wide text-muted",
      )}
    >
      <span />
      <span>Time</span>
      <span>Level</span>
      <span>Kind</span>
      <span>Method</span>
      <span>Route or event</span>
      <span className="text-right">Status</span>
      <span className="text-right">Duration</span>
      <span>Correlation</span>
    </div>
  );
}

interface CorrelationProps {
  entry: ServerLogEntry;
  ws: string | null;
  onFilter: (id: string) => void;
}

function Correlation({ entry, ws, onFilter }: CorrelationProps) {
  const runWs = entry.workspace ?? ws;
  const id = entry.run_id ?? entry.request_id;
  if (!id) return <span className="text-muted">-</span>;
  const prefix = entry.run_id ? "run" : "req";
  return (
    <span className="flex min-w-0 items-center gap-1">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onFilter(id);
        }}
        className="truncate rounded-sm text-left text-secondary hover:text-accent-text hover:underline focus-visible:outline-2 focus-visible:outline-accent-ring"
        title={`Filter by ${entry.run_id ? "run" : "request"} ${id}`}
        aria-label={`Filter by ${entry.run_id ? "run" : "request"} ${id}`}
      >
        <span className="text-muted">{prefix} </span>
        {shortCorrelation(id)}
      </button>
      {entry.run_id && runWs && (
        <Link
          href={telemetryRunHref(runWs, entry.run_id)}
          onClick={(e) => e.stopPropagation()}
          className="shrink-0 rounded-sm text-muted hover:text-accent-text focus-visible:outline-2 focus-visible:outline-accent-ring"
          title="Open run trace"
          aria-label={`Open run trace ${shortCorrelation(entry.run_id)}`}
        >
          <ArrowUpRight aria-hidden className="size-3.5" />
        </Link>
      )}
    </span>
  );
}

function LogDetails({ entry }: { entry: ServerLogEntry }) {
  return (
    <dl className="ms-fade-in grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)] gap-x-4 gap-y-0.5 border-t border-border/70 bg-surface/60 py-2 pl-[2.5rem] pr-3">
      {logDetailRows(entry).map((r) => (
        <div key={r.key} className="contents">
          <dt className="truncate text-muted">{r.key}</dt>
          <dd className="break-all text-primary">{r.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export interface LogRowProps {
  entry: ServerLogEntry;
  expanded: boolean;
  onToggle: (seq: number) => void;
  onFilter: (id: string) => void;
  ws: string | null;
}

export function LogRow({ entry, expanded, onToggle, onFilter, ws }: LogRowProps) {
  const lt = levelTone(entry.level);
  const http = entry.http;
  const subject = logSubject(entry);
  return (
    <li className={cx("border-b border-border/60 last:border-b-0", expanded && "bg-surface/40")}>
      <div
        className={cx(LOG_GRID, "cursor-pointer px-3 py-1 hover:bg-surface/70")}
        onClick={() => onToggle(entry.seq)}
      >
        <button
          type="button"
          aria-expanded={expanded}
          aria-label={`${expanded ? "Hide" : "Show"} fields for ${subject}`}
          onClick={(e) => {
            e.stopPropagation();
            onToggle(entry.seq);
          }}
          className="flex size-5 items-center justify-center rounded-sm text-muted hover:text-primary focus-visible:outline-2 focus-visible:outline-accent-ring"
        >
          <ChevronRight aria-hidden className={cx("size-3.5 transition-transform duration-(--duration-fast)", expanded && "rotate-90")} />
        </button>
        <time dateTime={entry.ts} title={entry.ts} className="tabular-nums text-muted">
          {formatLogTime(entry.ts)}
        </time>
        <span>
          <span className={cx("inline-block rounded-sm border px-1 text-2xs font-medium leading-4", LEVEL_CHIP[lt])}>
            {levelLabel(entry.level)}
          </span>
        </span>
        <span className="truncate text-muted">{entry.kind}</span>
        <span className={cx("font-medium", http ? TONE_TEXT[methodTone(http.method)] : "text-muted")}>{http?.method ?? ""}</span>
        <span className="truncate text-primary" title={http ? `${subject} (${http.path})` : subject}>
          {subject}
          {http && entry.event !== "http.request" && <span className="text-muted"> · {entry.event}</span>}
        </span>
        <span className={cx("text-right tabular-nums font-medium", TONE_TEXT[statusTone(http?.status)])}>{http?.status ?? ""}</span>
        <span className="text-right tabular-nums text-secondary">{http?.duration_ms != null ? formatMs(http.duration_ms) : ""}</span>
        <Correlation entry={entry} ws={ws} onFilter={onFilter} />
      </div>
      {expanded && <LogDetails entry={entry} />}
    </li>
  );
}
