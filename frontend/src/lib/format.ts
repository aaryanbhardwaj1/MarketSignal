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

/** "1 source", "12,480 passages": a grouped count with the right noun form. */
export function formatCount(n: number, one: string, many = `${one}s`): string {
  return `${formatNumber(n)} ${n === 1 ? one : many}`;
}

/** Words that keep a fixed spelling when a snake_case key is shown in plain words. */
const KEY_WORDS: Readonly<Record<string, string>> = {
  genz: "Gen Z",
  aov: "average order value",
  avg: "average",
  pnl: "P&L",
  sku: "SKU",
  skus: "SKUs",
  nps: "NPS",
  usd: "USD",
  qoq: "QoQ",
  yoy: "YoY",
  id: "ID",
  dtc: "DTC",
  us: "US",
};

const KEY_SUFFIXES: ReadonlyArray<[RegExp, string]> = [
  [/_pct$/i, " (%)"],
  [/_usd$/i, " (USD)"],
];

function sentenceCase(text: string): string {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

function wordsOf(base: string): string {
  return base
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => KEY_WORDS[w.toLowerCase()] ?? w.toLowerCase())
    .join(" ");
}

/** A dataset column or grouping key in plain words: `top_pain_point` -> "Top pain point", `return_rate_pct` -> "Return rate (%)". */
export function humanizeColumn(key: string): string {
  let base = key.trim();
  let suffix = "";
  for (const [re, label] of KEY_SUFFIXES) {
    if (re.test(base)) {
      suffix = label;
      base = base.replace(re, "");
      break;
    }
  }
  return sentenceCase(wordsOf(base)) + suffix;
}

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/**
 * A data value in plain words: snake_case codes become sentence case ("knit_upper_durability"
 * -> "Knit upper durability"), "2026-09" -> "September 2026", "2026-Q3" -> "Q3 2026"; numbers are
 * grouped; anything else is returned unchanged.
 */
export function humanizeValue(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") return EMPTY;
  if (typeof value === "number") return formatNumber(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  const month = /^(\d{4})-(\d{2})$/.exec(value);
  if (month) {
    const index = Number(month[2]) - 1;
    if (index >= 0 && index < 12) return `${MONTHS[index]} ${month[1]}`;
  }
  const quarter = /^(\d{4})-Q([1-4])$/.exec(value);
  if (quarter) return `Q${quarter[2]} ${quarter[1]}`;
  if (/^[a-z0-9]+(_[a-z0-9]+)+$/.test(value)) return sentenceCase(wordsOf(value));
  return value;
}

/** Stored table names ("SKU_Performance", "PnL_Summary") in words: "SKU performance", "P&L summary". */
export function tableLabel(table: string): string {
  return humanizeColumn(table.replace(/[^A-Za-z0-9]+/g, "_"));
}

/** One locator part in plain words: `Sheet 'Market_Sizing'` -> "Market sizing sheet"; others unchanged. */
function locatorPart(part: string): string {
  const sheet = /^sheet\s+'(.*)'$/i.exec(part);
  if (!sheet) return part;
  const name = tableLabel(sheet[1]);
  return name ? `${name} sheet` : "Sheet";
}

/**
 * Business locator for an evidence passage: keeps pages, sections, slides, sheets and rows, and
 * drops parser-internal parts ("Page 4, Block 2" -> "Page 4"). A block-only locator reads as a
 * passage number ("Block 6" -> "Passage 6"). Named sheets read as words
 * ("Sheet 'Market_Sizing', Row 7" -> "Market sizing sheet, Row 7").
 */
export function businessLocator(label: string | null | undefined): string {
  if (!label) return "";
  // A quoted sheet name may itself contain commas, so match it as one part.
  const parts = (label.match(/sheet\s+'.*?'(?=\s*,|\s*$)|[^,]+/gi) ?? []).map((p) => p.trim()).filter(Boolean);
  const kept = parts.filter((p) => !/^block\s+\d+$/i.test(p));
  if (kept.length > 0) return kept.map(locatorPart).join(", ");
  return parts.map((p) => p.replace(/^block\b/i, "Passage")).join(", ");
}

export interface RowField {
  label: string;
  value: string;
  /** Character range of the raw value within the passage text (for highlighting). */
  start: number;
  end: number;
}

const ROW_KEY = /^[A-Za-z][A-Za-z0-9_ ()%/-]{0,63}$/;

/**
 * A spreadsheet or CSV passage ("reason: Fit - runs small; share_of_sku_returns_pct: 41") as
 * labelled fields with plain column names and formatted numbers. Returns null for prose, so
 * callers fall back to quoting the text.
 */
export function parseRowPassage(text: string | null | undefined): RowField[] | null {
  if (!text || text.includes("\n")) return null;
  const parts = text.split("; ");
  if (parts.length < 2) return null;
  const fields: RowField[] = [];
  let offset = 0;
  for (const part of parts) {
    const at = part.indexOf(": ");
    if (at <= 0) return null;
    const key = part.slice(0, at);
    const raw = part.slice(at + 2).trim();
    if (!ROW_KEY.test(key)) return null;
    const start = offset + at + 2;
    fields.push({ label: humanizeColumn(key.replace(/_(pct|usd)$/i, "")), value: rowValue(key, raw), start, end: start + raw.length });
    offset += part.length + 2;
  }
  return fields;
}

function rowValue(key: string, raw: string): string {
  const numeric = /^-?\d+(\.\d+)?$/.test(raw) ? Number(raw) : null;
  if (numeric === null) return humanizeValue(raw);
  if (/_pct$/i.test(key)) return `${formatNumber(numeric, 2)}%`;
  if (/_usd$/i.test(key)) return formatUsd(numeric);
  // Identifier-like columns (years, codes) keep their digits ungrouped.
  if (/(^|_)(id|year|code|number|no)$/i.test(key)) return raw;
  return formatNumber(numeric, 2);
}

/** "Northstar Athletics - Gen Z Growth Engagement" -> { name: "Northstar Athletics", detail: "Gen Z Growth Engagement" }. */
export function splitWorkspaceName(full: string): { name: string; detail: string | null } {
  const match = /^(.+?)\s+[-–—]\s+(.+)$/.exec(full.trim());
  return match ? { name: match[1], detail: match[2] } : { name: full.trim(), detail: null };
}
