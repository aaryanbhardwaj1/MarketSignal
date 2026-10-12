/**
 * Display formatters. Every formatter returns "-" for null, undefined or non-finite input so
 * a missing value is never shown as 0. A fixed locale keeps server and client output identical.
 */
const LOCALE = "en-US";
const EMPTY = "-";

function isNum(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function formatMs(ms: number | null | undefined): string {
  if (!isNum(ms)) return EMPTY;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!isNum(bytes)) return EMPTY;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function truncateHash(hash: string | null | undefined, keep = 12): string {
  if (!hash) return EMPTY;
  return hash.length > keep ? `${hash.slice(0, keep)}...` : hash;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return EMPTY;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(LOCALE, { dateStyle: "medium", timeStyle: "short" });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return EMPTY;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(LOCALE, { dateStyle: "medium" });
}

/** Grouped integer or decimal: 12,480 or 3.25 (at most `maxDigits` decimals, default 0 for integers, 2 otherwise). */
export function formatNumber(value: number | null | undefined, maxDigits?: number): string {
  if (!isNum(value)) return EMPTY;
  const digits = maxDigits ?? (Number.isInteger(value) ? 0 : 2);
  return value.toLocaleString(LOCALE, { maximumFractionDigits: digits });
}

/** Compact counts for dense tables: 1.2K, 3.4M. */
export function formatCompact(value: number | null | undefined): string {
  if (!isNum(value)) return EMPTY;
  return value.toLocaleString(LOCALE, { notation: "compact", maximumFractionDigits: 1 });
}

/**
 * Percent. By default `value` is a ratio (0.42 -> "42.0%"); pass `{ ratio: false }` when the
 * value is already in percent units (42 -> "42.0%").
 */
export function formatPercent(
  value: number | null | undefined,
  { digits = 1, ratio = true }: { digits?: number; ratio?: boolean } = {},
): string {
  if (!isNum(value)) return EMPTY;
  const pct = ratio ? value * 100 : value;
  return `${pct.toFixed(digits)}%`;
}

/** US dollars. Sub-cent amounts keep 4 decimals so tiny per-run estimates are not shown as $0.00. */
export function formatUsd(value: number | null | undefined, { digits }: { digits?: number } = {}): string {
  if (!isNum(value)) return EMPTY;
  const d = digits ?? (Math.abs(value) > 0 && Math.abs(value) < 0.01 ? 4 : 2);
  return value.toLocaleString(LOCALE, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
}

const RELATIVE_UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

/** "3 hours ago", "yesterday", "just now". `now` is injectable for tests. */
export function formatRelativeDate(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return EMPTY;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const seconds = Math.round((date.getTime() - now.getTime()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(LOCALE, { numeric: "auto" });
  for (const [unit, size] of RELATIVE_UNITS) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.trunc(seconds / size), unit);
  }
  return "just now";
}

export function humanize(value: string): string {
  return value.replace(/_/g, " ");
}
