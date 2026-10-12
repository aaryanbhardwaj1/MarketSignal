/**
 * Business wording for named analyses (`GET /analytics/analyses`). Everything here reshapes or
 * labels values the endpoint returned; nothing computes a new figure.
 */
import type { Analysis, AnalysisFilter, AnalysisRow, AnalysisUnit } from "@/lib/api/contracts";
import { formatNumber, formatUsd } from "@/lib/format";

const WORDS: Record<string, string> = {
  genz: "Gen Z",
  aov: "average order value",
  avg: "average",
  pnl: "P&L",
  sku: "SKU",
  nps: "NPS",
  qoq: "QoQ",
  yoy: "YoY",
  id: "ID",
};

const SUFFIXES: Array<[RegExp, string]> = [
  [/_pct$/, " (%)"],
  [/_usd$/, " (USD)"],
];

function sentenceCase(text: string): string {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

/** Column or grouping key in plain words: `return_rate_pct` -> "Return rate (%)". */
export function humanizeKey(key: string): string {
  let suffix = "";
  let base = key;
  for (const [re, label] of SUFFIXES) {
    if (re.test(base)) {
      suffix = label;
      base = base.replace(re, "");
      break;
    }
  }
  const words = base.split("_").filter(Boolean).map((w) => WORDS[w.toLowerCase()] ?? w.toLowerCase());
  return sentenceCase(words.join(" ")) + suffix;
}

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** Data value in plain words: "2026-09" -> "September 2026", "2026-Q3" -> "Q3 2026", "fit_inconsistency" -> "Fit inconsistency". */
export function humanizeValue(value: string | number): string {
  if (typeof value === "number") return formatNumber(value);
  const month = /^(\d{4})-(\d{2})$/.exec(value);
  if (month) {
    const index = Number(month[2]) - 1;
    if (index >= 0 && index < 12) return `${MONTHS[index]} ${month[1]}`;
  }
  const quarter = /^(\d{4})-Q([1-4])$/.exec(value);
  if (quarter) return `Q${quarter[2]} ${quarter[1]}`;
  if (/^[a-z0-9]+(_[a-z0-9]+)+$/.test(value)) return sentenceCase(value.replace(/_/g, " "));
  return value;
}

function joinOr(values: string[]): string {
  if (values.length <= 1) return values.join("");
  return `${values.slice(0, -1).join(", ")} or ${values[values.length - 1]}`;
}

const OP_WORDS: Record<string, string> = {
  ne: "not",
  not_in: "not",
  gt: "more than",
  gte: "at least",
  lt: "less than",
  lte: "at most",
  contains: "contains",
};

/** "Age group: 18-21, 22-24 or 25-27", "Quarter: Q3 2026", "Rating: at least 4". */
export function describeFilter(filter: AnalysisFilter): string {
  const label = filter.label || humanizeKey(filter.column);
  const values = filter.values.map(humanizeValue);
  if (filter.op === "between" && values.length === 2) return `${label}: ${values[0]} to ${values[1]}`;
  const prefix = OP_WORDS[filter.op];
  return `${label}: ${prefix ? `${prefix} ` : ""}${joinOr(values)}`;
}

export const UNIT_LABELS: Record<AnalysisUnit, string> = {
  percent: "Share (%)",
  count: "Count",
  usd: "Amount (USD)",
  score: "Average score",
  ratio: "Ratio",
};

export function unitLabel(unit: AnalysisUnit): string {
  return UNIT_LABELS[unit] ?? sentenceCase(unit);
}

const CATEGORY_LABELS: Record<string, string> = {
  customer: "Customer",
  product: "Product",
  channel: "Channel",
  pricing: "Pricing",
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? humanizeKey(category);
}

function isNumeric(value: string): boolean {
  return value.trim() !== "" && Number.isFinite(Number(value));
}

/** Label for one result row from its group values (all of them for grouped aggregates). */
export function rowLabel(row: AnalysisRow, keys?: readonly string[]): string {
  const order = keys && keys.length > 0 ? keys : Object.keys(row.group);
  return order
    .map((k) => row.group[k])
    .filter((v): v is string => typeof v === "string" && v !== "")
    .map(humanizeValue)
    .join(" · ");
}

/** For listings (`filter_rows`): the non-numeric cells identify the row ("NS-KR2 · Knit Runner 2"). */
export function listingRowLabel(row: AnalysisRow, columns: readonly string[]): string {
  return columns
    .map((c) => row.group[c])
    .filter((v): v is string => typeof v === "string" && v !== "" && !isNumeric(v))
    .join(" · ");
}

/** Base behind one row: "108 of 400" for shares, "7 of 30 return records" or "n = 400" otherwise. */
export function rowBase(row: AnalysisRow, analysis: Pick<Analysis, "denominator">): string | null {
  if (row.numerator != null && row.denominator != null) {
    return `${formatNumber(row.numerator)} of ${formatNumber(row.denominator)}`;
  }
  if (row.denominator == null) return null;
  if (analysis.denominator) {
    return `${formatNumber(row.denominator)} of ${formatNumber(analysis.denominator.value)} ${analysis.denominator.label}`;
  }
  return `n = ${formatNumber(row.denominator)}`;
}

/** A listing cell, formatted by its column suffix; text is shown as given. */
export function formatListingCell(column: string, raw: string | undefined): string {
  if (raw == null || raw === "") return "-";
  if (!isNumeric(raw)) return raw;
  const n = Number(raw);
  if (column.endsWith("_pct")) return `${n.toFixed(1)}%`;
  if (column.endsWith("_usd")) return formatUsd(n, { digits: Number.isInteger(n) ? 0 : 2 });
  return formatNumber(n);
}

export interface Headline {
  /** What the figure describes ("Fit inconsistency"). */
  label: string;
  display: string;
  /** Base or denominator ("108 of 400 Gen Z respondents"), when the endpoint gives one. */
  context: string | null;
}

/**
 * The figure a card leads with: the single value when there is one, otherwise the first row as the
 * endpoint ordered it. Null unless the analysis was recomputed and matched (numbers are withheld otherwise).
 */
export function analysisHeadline(analysis: Analysis): Headline | null {
  if (analysis.status !== "computed") return null;
  if (analysis.value != null && analysis.display) {
    return {
      label: analysis.title,
      display: analysis.display,
      context: analysis.denominator ? `${formatNumber(analysis.denominator.value)} ${analysis.denominator.label}` : null,
    };
  }
  const first = analysis.rows[0];
  if (!first || first.display == null) return null;
  const label =
    analysis.op === "filter_rows" && analysis.columns
      ? listingRowLabel(first, analysis.columns)
      : rowLabel(first, analysis.group_by);
  return { label, display: first.display, context: rowBase(first, analysis) };
}

export interface AnalysisState {
  kind: "computed" | "mismatch" | "unavailable";
  label: string;
  tone: "success" | "warn" | "neutral";
  message: string | null;
}

export function analysisState(analysis: Pick<Analysis, "status">): AnalysisState {
  switch (analysis.status) {
    case "computed":
      return { kind: "computed", label: "Recomputed", tone: "success", message: null };
    case "mismatch":
      return {
        kind: "mismatch",
        label: "Numbers withheld",
        tone: "warn",
        message: "Result changed since curation; numbers withheld until the analysis is reviewed.",
      };
    default:
      return {
        kind: "unavailable",
        label: "Unavailable",
        tone: "neutral",
        message: "This dataset is not currently available, so the analysis could not be recomputed.",
      };
  }
}

/** Plain-language scope line: filters, then the dataset ("Age group: 18-21, 22-24 or 25-27 · Northstar Customer Survey 2026"). */
export function scopeLine(analysis: Pick<Analysis, "filters" | "provenance">): string {
  return [...analysis.filters.map(describeFilter), analysis.provenance.source_title].join(" · ");
}

/** Table names arrive as stored ("SKU_Performance"); business pages show them in words. */
export function tableLabel(table: string): string {
  return humanizeKey(table.replace(/[^A-Za-z0-9]+/g, "_"));
}

/** A listing column is numeric when every non-empty cell parses as a number. */
export function isNumericColumn(rows: readonly AnalysisRow[], column: string): boolean {
  const cells = rows.map((r) => r.group[column]).filter((v): v is string => typeof v === "string" && v !== "");
  return cells.length > 0 && cells.every(isNumeric);
}
