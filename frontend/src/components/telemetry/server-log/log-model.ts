/**
 * Pure helpers for the server log viewer (E12 `GET /api/dev/logs`): filters → query params,
 * incremental merge of polled entries, and the display mapping of levels, methods and status
 * codes to design-system tones. No React here, so everything is unit-testable.
 */

import type {
  ServerLogEntry,
  ServerLogKind,
  ServerLogLevel,
  ServerLogParams,
  ServerLogResponse,
  ServerLogStatusClass,
} from "@/lib/api/contracts";

/** Entries kept client-side; older ones fall off the top as new ones are appended. */
export const LOG_BUFFER_LIMIT = 1000;
/** Initial snapshot size (newest first on the wire). */
export const SNAPSHOT_LIMIT = 200;
/** Incremental page size while live; the server allows up to 500. */
export const POLL_LIMIT = 500;
export const POLL_MS = 2000;
export const SEARCH_DEBOUNCE_MS = 300;

export type LogTone = "success" | "warn" | "danger" | "info" | "neutral" | "accent";

export interface LogFilters {
  /** Minimum level; "" = all levels. */
  level: ServerLogLevel | "";
  kind: ServerLogKind | "";
  method: string;
  status_class: ServerLogStatusClass | "";
  route: string;
  q: string;
  include_noise: boolean;
}

export const DEFAULT_LOG_FILTERS: LogFilters = {
  level: "",
  kind: "",
  method: "",
  status_class: "",
  route: "",
  q: "",
  include_noise: false,
};

export const LEVEL_OPTIONS: { value: LogFilters["level"]; label: string }[] = [
  { value: "", label: "All levels" },
  { value: "INFO", label: "Info and above" },
  { value: "WARNING", label: "Warnings and above" },
  { value: "ERROR", label: "Errors only" },
];

export const KIND_OPTIONS: { value: LogFilters["kind"]; label: string }[] = [
  { value: "", label: "All kinds" },
  { value: "http", label: "HTTP" },
  { value: "run", label: "Run" },
  { value: "tool", label: "Tool" },
  { value: "verification", label: "Verification" },
  { value: "ingestion", label: "Ingestion" },
  { value: "analytics", label: "Analytics" },
  { value: "app", label: "App" },
];

export const METHOD_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "All methods" },
  ...["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => ({ value: m, label: m })),
];

export const STATUS_OPTIONS: { value: LogFilters["status_class"]; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "2xx", label: "2xx" },
  { value: "3xx", label: "3xx" },
  { value: "4xx", label: "4xx" },
  { value: "5xx", label: "5xx" },
];

/** Filters → query params (empty values omitted; `after_seq` and `limit` set by the caller). */
export function filtersToParams(filters: LogFilters): ServerLogParams {
  const q = filters.q.trim();
  const params: ServerLogParams = {};
  if (filters.level) params.level = filters.level;
  if (filters.kind) params.kind = filters.kind;
  if (filters.method) params.method = filters.method;
  if (filters.status_class) params.status_class = filters.status_class;
  if (filters.route) params.route = filters.route;
  if (q) params.q = q;
  if (filters.include_noise) params.include_noise = true;
  return params;
}

/** Stable identity of a filter set: a change resets the client buffer. */
export function filterKey(filters: LogFilters): string {
  return JSON.stringify(filtersToParams(filters));
}

export function hasActiveFilters(filters: LogFilters): boolean {
  return filterKey(filters) !== filterKey(DEFAULT_LOG_FILTERS);
}

/**
 * Merge entries by `seq` (no duplicates; later copies win), ascending, keeping only the newest
 * `cap`. Accepts either wire order (snapshot is newest first, polls are ascending).
 */
export function mergeLogEntries(
  existing: readonly ServerLogEntry[],
  incoming: readonly ServerLogEntry[],
  cap: number = LOG_BUFFER_LIMIT,
): ServerLogEntry[] {
  const bySeq = new Map<number, ServerLogEntry>();
  for (const e of existing) bySeq.set(e.seq, e);
  for (const e of incoming) bySeq.set(e.seq, e);
  const sorted = [...bySeq.values()].sort((a, b) => a.seq - b.seq);
  return sorted.length > cap ? sorted.slice(sorted.length - cap) : sorted;
}

/**
 * Next `after_seq` after a response. A full incremental page may have more behind it, so resume
 * from its last entry; otherwise skip to the buffer's `latest_seq` (non-matching entries need
 * not be rescanned). Never moves backwards.
 */
export function nextCursor(
  prev: number | null,
  response: Pick<ServerLogResponse, "entries" | "latest_seq">,
  requestedLimit: number,
  incremental: boolean,
): number | null {
  const seqs = response.entries.map((e) => e.seq);
  const lastSeen = seqs.length ? Math.max(...seqs) : null;
  const pageFull = incremental && response.entries.length >= requestedLimit;
  const candidate = pageFull ? lastSeen : (response.latest_seq ?? lastSeen);
  const values = [prev, candidate].filter((v): v is number => v != null);
  return values.length ? Math.max(...values) : null;
}

const pad = (n: number, width = 2): string => String(n).padStart(width, "0");

/** `HH:MM:SS.mmm` in local time (or UTC); "-" when unparseable. */
export function formatLogTime(iso: string, { utc = false }: { utc?: boolean } = {}): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  const [h, m, s, ms] = utc
    ? [d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds(), d.getUTCMilliseconds()]
    : [d.getHours(), d.getMinutes(), d.getSeconds(), d.getMilliseconds()];
  return `${pad(h)}:${pad(m)}:${pad(s)}.${pad(ms, 3)}`;
}

export function levelTone(level: string): LogTone {
  if (level === "ERROR" || level === "CRITICAL") return "danger";
  if (level === "WARNING") return "warn";
  return "neutral";
}

export function levelLabel(level: string): string {
  return level === "WARNING" ? "WARN" : level;
}

export function statusTone(status: number | null | undefined): LogTone {
  if (status == null) return "neutral";
  if (status >= 500) return "danger";
  if (status >= 400) return "warn";
  if (status >= 300) return "info";
  if (status >= 200) return "success";
  return "neutral";
}

const METHOD_TONES: Record<string, LogTone> = {
  GET: "info",
  HEAD: "info",
  OPTIONS: "neutral",
  POST: "success",
  PUT: "warn",
  PATCH: "warn",
  DELETE: "danger",
};

export function methodTone(method: string | null | undefined): LogTone {
  return (method && METHOD_TONES[method.toUpperCase()]) || "neutral";
}

/** Text colour per tone (token colours; legible on the sunken console surface). */
export const TONE_TEXT: Record<LogTone, string> = {
  success: "text-success",
  warn: "text-warn",
  danger: "text-danger",
  info: "text-info",
  neutral: "text-secondary",
  accent: "text-accent-text",
};

/** First 8 characters of an id (UUIDs and request ids). */
export function shortCorrelation(id: string): string {
  return id.length > 8 ? id.slice(0, 8) : id;
}

/** What the main column shows: route template for HTTP, raw path when unmatched, else the event. */
export function logSubject(entry: ServerLogEntry): string {
  if (entry.http) return entry.http.route ?? entry.http.path;
  return entry.event;
}

export type LogFieldValue = string | number | boolean | null;

/** Key/value rows for the expanded entry: only values present in the response. */
export function logDetailRows(entry: ServerLogEntry): { key: string; value: string }[] {
  const show = (v: LogFieldValue): string => (v === null ? "null" : String(v));
  const rows: { key: string; value: string }[] = [
    { key: "seq", value: String(entry.seq) },
    { key: "ts", value: entry.ts },
    { key: "event", value: entry.event },
  ];
  if (entry.logger) rows.push({ key: "logger", value: entry.logger });
  if (entry.workspace) rows.push({ key: "workspace", value: entry.workspace });
  if (entry.request_id) rows.push({ key: "request_id", value: entry.request_id });
  if (entry.run_id) rows.push({ key: "run_id", value: entry.run_id });
  if (entry.http) {
    rows.push({ key: "http.path", value: entry.http.path });
    if (entry.http.route) rows.push({ key: "http.route", value: entry.http.route });
  }
  for (const [k, v] of Object.entries(entry.fields ?? {}).sort(([a], [b]) => a.localeCompare(b))) {
    rows.push({ key: k, value: show(v) });
  }
  return rows;
}

/** Within `slack` px of the bottom counts as "at the bottom" (auto-scroll keeps sticking). */
export function isAtBottom(
  el: Pick<HTMLElement, "scrollHeight" | "scrollTop" | "clientHeight">,
  slack = 24,
): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= slack;
}
